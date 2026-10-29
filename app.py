from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for, make_response
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash
import pymysql
import sqlite3
import json
import csv
import math
import os
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

from ga_solver import solve_schedule

BASE_DIR = os.path.dirname(__file__)
BEIJING_TZ = timezone(timedelta(hours=8))

def load_secret_key():
    env_secret = os.environ.get('FARM_SYSTEM_SECRET_KEY')
    if env_secret:
        return env_secret

    secret_path = os.path.join(BASE_DIR, '.farm_secret_key')
    try:
        if os.path.exists(secret_path):
            with open(secret_path, 'r', encoding='utf-8') as f:
                secret = f.read().strip()
            if len(secret) >= 32:
                return secret

        secret = secrets.token_urlsafe(48)
        with open(secret_path, 'w', encoding='utf-8') as f:
            f.write(secret)
        return secret
    except OSError:
        return 'farm-system-dev-secret-change-me'

app = Flask(__name__, static_folder='static')
app.secret_key = load_secret_key()

CSRF_COOKIE_NAME = 'farm_csrf_token'

app.config.update(
    MAX_CONTENT_LENGTH=int(os.environ.get('FARM_MAX_REQUEST_BYTES', str(2 * 1024 * 1024))),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_NAME='farm_session',
)

if os.environ.get('FARM_ENABLE_CORS', '').lower() in ('1', 'true', 'yes'):
    configured_origins = [
        item.strip()
        for item in os.environ.get('FARM_CORS_ORIGINS', '').split(',')
        if item.strip()
    ]
    if configured_origins:
        CORS(app, resources={r'/api/*': {'origins': configured_origins}})

AUTH_SCHEMA_READY = False
SCHEDULE_SCHEMA_READY = False
LOGIN_FAILURE_LIMIT = int(os.environ.get('FARM_LOGIN_FAILURE_LIMIT', '5'))
LOGIN_FAILURE_WINDOW_SECONDS = int(os.environ.get('FARM_LOGIN_FAILURE_WINDOW_SECONDS', '900'))
LOGIN_LOCK_SECONDS = int(os.environ.get('FARM_LOGIN_LOCK_SECONDS', '900'))
TRUST_PROXY_HEADERS = os.environ.get('FARM_TRUST_PROXY_HEADERS', '').lower() in ('1', 'true', 'yes')
REALTIME_ONLINE_TIMEOUT_SECONDS = int(os.environ.get('JT808_ONLINE_TIMEOUT_SECONDS', '180'))
GPSWV_ONLINE_TIMEOUT_SECONDS = int(os.environ.get('GPSWV_ONLINE_TIMEOUT_SECONDS', '600'))
REALTIME_POSITION_SOURCES = frozenset(('jt808', 'gpswv'))
LOGIN_FAILURES = {}
LOGIN_FAILURES_LOCK = threading.Lock()
DB_DRIVER = os.environ.get('FARM_DB_DRIVER', 'sqlite').lower()
SQLITE_DB_PATH = os.environ.get(
    'FARM_SQLITE_DB',
    os.path.join(BASE_DIR, 'farm_management.sqlite')
)
AMAP_CONFIG_ENV_PATH = os.environ.get('FARM_AMAP_CONFIG', '').strip()
AMAP_LOCAL_CONFIG_PATHS = (
    [AMAP_CONFIG_ENV_PATH]
    if AMAP_CONFIG_ENV_PATH
    else [
        os.path.join(BASE_DIR, '.amap_config.json'),
        os.path.join(BASE_DIR, 'amap_config.json'),
    ]
)

@app.before_request
def enforce_csrf_token():
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    if request.path == '/api/auth/login' or not session.get('user_id'):
        return None

    expected_token = session.get('csrf_token') or ''
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME) or ''
    supplied_token = request.headers.get('X-CSRF-Token') or ''
    if not expected_token or not (
        secrets.compare_digest(expected_token, cookie_token)
        and secrets.compare_digest(expected_token, supplied_token)
    ):
        return jsonify({'error': '安全令牌无效，请刷新页面后重试'}), 403
    return None

@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault('Content-Security-Policy', "object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
    return response

def load_amap_runtime_config():
    """读取高德本机配置；安全密钥只供服务端代理使用。"""
    key = os.environ.get('AMAP_JSAPI_KEY', '').strip()
    security_js_code = os.environ.get('AMAP_SECURITY_JSCODE', '').strip()

    for config_path in AMAP_LOCAL_CONFIG_PATHS:
        if key and security_js_code:
            break
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                local_config = json.load(f)
            key = key or str(local_config.get('key') or '').strip()
            security_js_code = security_js_code or str(
                local_config.get('securityJsCode') or local_config.get('security_js_code') or ''
            ).strip()
        except (OSError, ValueError, TypeError):
            continue

    return {
        'key': key,
        'security_js_code': security_js_code,
        'configured': bool(key and security_js_code),
    }

def get_client_ip():
    if TRUST_PROXY_HEADERS:
        for header in ('CF-Connecting-IP', 'X-Real-IP', 'X-Forwarded-For'):
            value = request.headers.get(header)
            if value:
                return value.split(',')[0].strip()
    return request.remote_addr or 'unknown'

def format_wait_seconds(seconds):
    minutes = max(1, int((seconds + 59) // 60))
    return f'{minutes} 分钟'

def login_failure_keys(username):
    normalized_username = (username or '').strip().lower() or 'empty'
    return (f'user:{normalized_username}', f'ip:{get_client_ip()}')

def get_login_block_seconds(username):
    now = time.time()
    blocked_until = 0
    with LOGIN_FAILURES_LOCK:
        for key in login_failure_keys(username):
            item = LOGIN_FAILURES.get(key)
            if not item:
                continue
            if item.get('locked_until', 0) > now:
                blocked_until = max(blocked_until, item['locked_until'])
                continue
            if now - item.get('first_failed_at', now) > LOGIN_FAILURE_WINDOW_SECONDS:
                LOGIN_FAILURES.pop(key, None)
    return max(0, int(blocked_until - now))

def register_login_failure(username):
    now = time.time()
    with LOGIN_FAILURES_LOCK:
        for key in login_failure_keys(username):
            item = LOGIN_FAILURES.get(key)
            if not item or now - item.get('first_failed_at', now) > LOGIN_FAILURE_WINDOW_SECONDS:
                item = {'count': 0, 'first_failed_at': now, 'locked_until': 0}

            item['count'] += 1
            if item['count'] >= LOGIN_FAILURE_LIMIT:
                item['locked_until'] = now + LOGIN_LOCK_SECONDS
            LOGIN_FAILURES[key] = item

def clear_login_failures(username):
    with LOGIN_FAILURES_LOCK:
        for key in login_failure_keys(username):
            LOGIN_FAILURES.pop(key, None)

def to_float(value, default=0):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def convert_sql_params(sql):
    if DB_DRIVER == 'sqlite':
        return sql.replace('%s', '?')
    return sql

class SQLiteCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=None):
        params = params or ()
        self.cursor.execute(convert_sql_params(sql), params)
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

class SQLiteConnection:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def cursor(self):
        return SQLiteCursor(self.conn.cursor())

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def format_time_value(value):
    if not value:
        return '--:--'
    if hasattr(value, 'strftime'):
        return value.strftime('%H:%M')
    text = str(value)
    if len(text) >= 16 and ' ' in text:
        return text[11:16]
    return text[:5]

def format_date_value(value):
    if not value:
        return None
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return str(value)[:10]

def format_datetime_value(value):
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d %H:%M')
    return str(value)[:16]

def beijing_now_text():
    return datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

def parse_database_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()[:19]
        try:
            parsed = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING_TZ)
    return parsed.astimezone(BEIJING_TZ)

def realtime_position_is_fresh(last_seen, position_source=None):
    parsed = parse_database_datetime(last_seen)
    if not parsed:
        return False
    age_seconds = (datetime.now(BEIJING_TZ) - parsed).total_seconds()
    timeout_seconds = (
        GPSWV_ONLINE_TIMEOUT_SECONDS
        if str(position_source or '').strip().lower() == 'gpswv'
        else REALTIME_ONLINE_TIMEOUT_SECONDS
    )
    return -60 <= age_seconds <= timeout_seconds

def is_realtime_position_source(source):
    return str(source or '').strip().lower() in REALTIME_POSITION_SOURCES

def gpswv_settings_for_machine(machine_id):
    try:
        from gpswv_location import load_settings_list
    except Exception as exc:
        raise RuntimeError(f'GPSWV 配置模块不可用：{exc}') from exc

    for settings in load_settings_list():
        if settings.get('enabled') and str(settings.get('machine_id')) == str(machine_id):
            return settings
    return None

def fetch_gpswv_history_track(machine_id, start_dt, end_dt):
    try:
        from gpswv_location import GpsWvClient, GpsWvApiError, safe_float
    except Exception as exc:
        raise RuntimeError(f'GPSWV 客户端不可用：{exc}') from exc

    settings = gpswv_settings_for_machine(machine_id)
    if not settings:
        raise RuntimeError(f'未找到 {machine_id} 的 GPSWV 历史轨迹配置')

    settings = dict(settings)
    settings['request_timeout'] = max(int(settings.get('request_timeout') or 20), 60)
    client = GpsWvClient(settings)
    raw_items = client.get_device_track_history(
        int(start_dt.timestamp()),
        int(end_dt.timestamp()),
        only_gps=0,
    )
    valid_items = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        lng = safe_float(item.get('lng'), None)
        lat = safe_float(item.get('lat'), None)
        if lng is None or lat is None or not (-180 <= lng <= 180 and -90 <= lat <= 90):
            continue
        gps_epoch = safe_float(item.get('gpsTime'), None)
        if gps_epoch is not None and gps_epoch > 10_000_000_000:
            gps_epoch /= 1000.0
        point_time = (
            datetime.fromtimestamp(gps_epoch, BEIJING_TZ)
            if gps_epoch is not None
            else None
        )
        valid_items.append({
            'lng': lng,
            'lat': lat,
            'speed': safe_float(item.get('speed'), 0) or 0,
            'direction': int(to_float(item.get('course'), 0)),
            'time': point_time,
            'positionType': item.get('positionType') or '',
        })

    valid_items.sort(key=lambda item: item['time'] or start_dt)
    raw_point_count = len(valid_items)
    sampled = False
    if raw_point_count > 5000:
        step = math.ceil(raw_point_count / 5000)
        last_item = valid_items[-1]
        valid_items = valid_items[::step]
        if valid_items and valid_items[-1] is not last_item:
            valid_items.append(last_item)
        sampled = True

    points = [[item['lat'], item['lng']] for item in valid_items]
    point_times = [item['time'] for item in valid_items]
    distance = 0.0
    for index in range(1, len(points)):
        distance += geographic_distance_km(
            points[index - 1][1], points[index - 1][0],
            points[index][1], points[index][0]
        )
    first_time = point_times[0] if point_times else None
    last_time = point_times[-1] if point_times else None
    duration = max(0, int((last_time - first_time).total_seconds())) if first_time and last_time else 0
    elapsed_seconds = []
    for index, point_time in enumerate(point_times):
        elapsed = max(0, int((point_time - first_time).total_seconds())) if first_time and point_time else index * 5
        if elapsed_seconds:
            elapsed = max(elapsed, elapsed_seconds[-1])
        elapsed_seconds.append(elapsed)

    return {
        'machineId': machine_id,
        'queryStart': start_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'queryEnd': end_dt.strftime('%Y-%m-%d %H:%M:%S'),
        'rawPointCount': raw_point_count,
        'sampled': sampled,
        'points': points,
        'timestamps': [format_datetime_value(item['time']) for item in valid_items],
        'elapsedSeconds': elapsed_seconds,
        'distance': round(distance, 3),
        'duration': duration,
        'trackDate': format_date_value(last_time) if last_time else None,
        'start_lng': points[0][1] if points else None,
        'start_lat': points[0][0] if points else None,
        'end_lng': points[-1][1] if points else None,
        'end_lat': points[-1][0] if points else None,
        'realtime': True,
        'trackSource': 'gpswv-history',
    }

def update_machine_operating_status(cursor, machine_id, status):
    cursor.execute('SELECT position_source FROM machines WHERE id = %s', (machine_id,))
    machine = cursor.fetchone() or {}
    if is_realtime_position_source(machine.get('position_source')):
        cursor.execute('UPDATE machines SET status = %s WHERE id = %s', (status, machine_id))
    else:
        cursor.execute(
            'UPDATE machines SET status = %s, last_seen = %s WHERE id = %s',
            (status, beijing_now_text(), machine_id)
        )

def get_effective_machine_status_rows(cursor):
    cursor.execute('''
        SELECT id, status, position_source, last_seen, `signal`
        FROM machines
        ORDER BY id
    ''')
    machines = cursor.fetchall()
    cursor.execute('''
        SELECT machine_id,
               SUM(CASE WHEN status = '已接收' THEN 1 ELSE 0 END) AS received_count,
               SUM(CASE WHEN status = '待接收' THEN 1 ELSE 0 END) AS pending_count
        FROM tasks
        WHERE status != '已撤销'
        GROUP BY machine_id
    ''')
    task_counts = {row['machine_id']: row for row in cursor.fetchall()}

    status_rows = []
    for machine in machines:
        counts = task_counts.get(machine['id'], {})
        position_source = machine.get('position_source') or 'demo'
        status = 'idle' if machine.get('status') == 'online' else (machine.get('status') or 'offline')
        if is_realtime_position_source(position_source) and not realtime_position_is_fresh(machine.get('last_seen'), position_source):
            status = 'offline'
        elif int(counts.get('received_count') or 0) > 0:
            status = 'working'
        elif int(counts.get('pending_count') or 0) > 0:
            status = 'idle'
        status_rows.append({
            'id': machine['id'],
            'status': status,
            'signal': int(to_float(machine.get('signal'))),
        })
    return status_rows

def get_machine_task_status(cursor, machine_id):
    """任务状态优先级：已接收=作业中，待接收=待命，无未完成任务则不覆盖设备状态。"""
    cursor.execute('''
        SELECT
            SUM(CASE WHEN status = '已接收' THEN 1 ELSE 0 END) AS received_count,
            SUM(CASE WHEN status = '待接收' THEN 1 ELSE 0 END) AS pending_count
        FROM tasks
        WHERE machine_id = %s
    ''', (machine_id,))
    row = cursor.fetchone() or {}
    if int(row.get('received_count') or 0) > 0:
        return 'working'
    if int(row.get('pending_count') or 0) > 0:
        return 'idle'
    return None

def sync_machine_status_from_tasks(cursor, machine_id):
    status = get_machine_task_status(cursor, machine_id)
    if status:
        update_machine_operating_status(cursor, machine_id, status)
    return status

def get_db_connection():
    if DB_DRIVER == 'sqlite':
        return SQLiteConnection(SQLITE_DB_PATH)

    return pymysql.connect(
        host=os.environ.get('FARM_MYSQL_HOST', 'localhost'),
        port=int(os.environ.get('FARM_MYSQL_PORT', '3306')),
        user=os.environ.get('FARM_MYSQL_USER', 'root'),
        password=os.environ.get('FARM_MYSQL_PASSWORD', ''),
        database=os.environ.get('FARM_MYSQL_DATABASE', 'farm_management'),
        charset='utf8',
        cursorclass=pymysql.cursors.DictCursor
    )

def ensure_schedule_schema():
    """为候选调度方案和未来真实定位农机补齐兼容字段。"""
    global SCHEDULE_SCHEMA_READY
    if SCHEDULE_SCHEMA_READY:
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    if DB_DRIVER == 'sqlite':
        cursor.execute('PRAGMA table_info(machines)')
        machine_columns = {row['name'] for row in cursor.fetchall()}
        cursor.execute('PRAGMA table_info(tasks)')
        task_columns = {row['name'] for row in cursor.fetchall()}
        if 'auto_schedulable' not in machine_columns:
            cursor.execute('ALTER TABLE machines ADD COLUMN auto_schedulable INTEGER NOT NULL DEFAULT 1')
        if 'position_source' not in machine_columns:
            cursor.execute("ALTER TABLE machines ADD COLUMN position_source TEXT NOT NULL DEFAULT 'demo'")
        if 'device_no' not in machine_columns:
            cursor.execute('ALTER TABLE machines ADD COLUMN device_no TEXT DEFAULT NULL')
        if 'direction' not in machine_columns:
            cursor.execute('ALTER TABLE machines ADD COLUMN direction INTEGER DEFAULT 0')
        if 'schedule_plan_id' not in task_columns:
            cursor.execute('ALTER TABLE tasks ADD COLUMN schedule_plan_id INTEGER DEFAULT NULL')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                algorithm TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                total_cost REAL DEFAULT 0.00,
                total_distance_km REAL DEFAULT 0.00,
                total_estimated_hours REAL DEFAULT 0.00,
                total_energy REAL DEFAULT 0.00,
                machine_count INTEGER DEFAULT 0,
                task_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                published_at TEXT DEFAULT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule_plan_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                machine_id TEXT NOT NULL,
                farmland_id TEXT NOT NULL,
                operation_type TEXT DEFAULT '智能调度',
                task_order INTEGER DEFAULT 0,
                distance_km REAL DEFAULT 0.00,
                estimated_hours REAL DEFAULT 0.00,
                estimated_energy REAL DEFAULT 0.00
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS machine_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT NOT NULL,
                device_no TEXT NOT NULL,
                lng REAL NOT NULL,
                lat REAL NOT NULL,
                altitude REAL DEFAULT 0.00,
                speed REAL DEFAULT 0.00,
                direction INTEGER DEFAULT 0,
                alarm INTEGER DEFAULT 0,
                terminal_status INTEGER DEFAULT 0,
                signal INTEGER DEFAULT 0,
                source_time TEXT DEFAULT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_machine_positions_machine_time
            ON machine_positions(machine_id, id DESC)
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO machines (
                id, name, type, org, operator, status, lng, lat, altitude,
                speed, area, `signal`, last_seen, alerts, work_time,
                auto_schedulable, position_source, device_no, direction
            ) VALUES (
                'R-001', '北斗实机 R-001', 'tractor', '真实农机接入', '实机操作员',
                'offline', 106.235, 29.785, 0, 0, 0, 0, '2000-01-01 00:00:00',
                0, 0, 0, 'jt808', '31110789281', 0
            )
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO machines (
                id, name, type, org, operator, status, lng, lat, altitude,
                speed, area, `signal`, last_seen, alerts, work_time,
                auto_schedulable, position_source, device_no, direction
            ) VALUES (
                'R-002', '北斗实机 R-002', 'tractor', '真实农机接入', '实机操作员 2',
                'offline', 106.236, 29.786, 0, 0, 0, 0, '2000-01-01 00:00:00',
                0, 0, 0, 'gpswv', '862000000000002', 0
            )
        ''')
    else:
        cursor.execute('SHOW COLUMNS FROM machines')
        machine_columns = {row['Field'] for row in cursor.fetchall()}
        cursor.execute('SHOW COLUMNS FROM tasks')
        task_columns = {row['Field'] for row in cursor.fetchall()}
        if 'auto_schedulable' not in machine_columns:
            cursor.execute('ALTER TABLE machines ADD COLUMN auto_schedulable TINYINT(1) NOT NULL DEFAULT 1')
        if 'position_source' not in machine_columns:
            cursor.execute("ALTER TABLE machines ADD COLUMN position_source VARCHAR(20) NOT NULL DEFAULT 'demo'")
        if 'device_no' not in machine_columns:
            cursor.execute('ALTER TABLE machines ADD COLUMN device_no VARCHAR(30) DEFAULT NULL')
        if 'direction' not in machine_columns:
            cursor.execute('ALTER TABLE machines ADD COLUMN direction INT DEFAULT 0')
        if 'schedule_plan_id' not in task_columns:
            cursor.execute('ALTER TABLE tasks ADD COLUMN schedule_plan_id INT DEFAULT NULL')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule_plans (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                algorithm VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft',
                total_cost DECIMAL(14,4) DEFAULT 0,
                total_distance_km DECIMAL(12,3) DEFAULT 0,
                total_estimated_hours DECIMAL(12,3) DEFAULT 0,
                total_energy DECIMAL(12,3) DEFAULT 0,
                machine_count INT DEFAULT 0,
                task_count INT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                published_at DATETIME DEFAULT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule_plan_items (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                plan_id INT NOT NULL,
                machine_id VARCHAR(50) NOT NULL,
                farmland_id VARCHAR(50) NOT NULL,
                operation_type VARCHAR(50) DEFAULT '智能调度',
                task_order INT DEFAULT 0,
                distance_km DECIMAL(12,3) DEFAULT 0,
                estimated_hours DECIMAL(12,3) DEFAULT 0,
                estimated_energy DECIMAL(12,3) DEFAULT 0,
                KEY plan_id (plan_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS machine_positions (
                id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                machine_id VARCHAR(50) NOT NULL,
                device_no VARCHAR(30) NOT NULL,
                lng DECIMAL(11,7) NOT NULL,
                lat DECIMAL(10,7) NOT NULL,
                altitude DECIMAL(10,2) DEFAULT 0,
                speed DECIMAL(10,2) DEFAULT 0,
                direction INT DEFAULT 0,
                alarm BIGINT DEFAULT 0,
                terminal_status BIGINT DEFAULT 0,
                signal INT DEFAULT 0,
                source_time DATETIME DEFAULT NULL,
                received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                KEY idx_machine_positions_machine_time (machine_id, id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        cursor.execute('''
            INSERT IGNORE INTO machines (
                id, name, type, org, operator, status, lng, lat, altitude,
                speed, area, `signal`, last_seen, alerts, work_time,
                auto_schedulable, position_source, device_no, direction
            ) VALUES (
                'R-001', '北斗实机 R-001', 'tractor', '真实农机接入', '实机操作员',
                'offline', 106.235, 29.785, 0, 0, 0, 0, '2000-01-01 00:00:00',
                0, 0, 0, 'jt808', '31110789281', 0
            )
        ''')
        cursor.execute('''
            INSERT IGNORE INTO machines (
                id, name, type, org, operator, status, lng, lat, altitude,
                speed, area, `signal`, last_seen, alerts, work_time,
                auto_schedulable, position_source, device_no, direction
            ) VALUES (
                'R-002', '北斗实机 R-002', 'tractor', '真实农机接入', '实机操作员 2',
                'offline', 106.236, 29.786, 0, 0, 0, 0, '2000-01-01 00:00:00',
                0, 0, 0, 'gpswv', '862000000000002', 0
            )
        ''')

    cursor.execute('''
        UPDATE machines
        SET auto_schedulable = 0,
            position_source = CASE
                WHEN position_source = 'gpswv' THEN 'gpswv'
                ELSE 'jt808'
            END,
            device_no = '31110789281'
        WHERE id = 'R-001'
    ''')
    cursor.execute('''
        UPDATE machines
        SET name = '北斗实机 R-002', type = 'tractor', org = '真实农机接入',
            operator = '实机操作员 2', auto_schedulable = 0,
            position_source = 'gpswv', device_no = '862000000000002'
        WHERE id = 'R-002'
    ''')

    conn.commit()
    conn.close()
    SCHEDULE_SCHEMA_READY = True

def normalize_machine_username(machine_id):
    return f"worker_{machine_id.lower().replace('-', '')}"

def default_worker_password(machine_id):
    return f"Worker@{machine_id.replace('-', '')}"

def ensure_auth_schema():
    global AUTH_SCHEMA_READY
    if AUTH_SCHEMA_READY:
        return

    ensure_schedule_schema()

    conn = get_db_connection()
    cursor = conn.cursor()
    if DB_DRIVER == 'sqlite':
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'worker',
                machine_id TEXT DEFAULT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                auth_version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('PRAGMA table_info(users)')
        user_columns = {row['name'] for row in cursor.fetchall()}
        if 'auth_version' not in user_columns:
            cursor.execute('ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 1')
    else:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT NOT NULL AUTO_INCREMENT,
                username VARCHAR(50) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'worker',
                machine_id VARCHAR(50) DEFAULT NULL,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                auth_version INT NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY username (username),
                KEY machine_id (machine_id),
                KEY role (role)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
        ''')
        cursor.execute("SHOW COLUMNS FROM users LIKE 'auth_version'")
        if not cursor.fetchone():
            cursor.execute('ALTER TABLE users ADD COLUMN auth_version INT NOT NULL DEFAULT 1')

    cursor.execute('SELECT id FROM users WHERE username = %s', ('admin',))
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (username, password_hash, display_name, role, machine_id)
            VALUES (%s, %s, %s, %s, NULL)
        ''', (
            'admin',
            generate_password_hash('Admin@123456'),
            '系统管理员',
            'admin'
        ))

    cursor.execute('SELECT id, name, operator FROM machines ORDER BY id')
    machines = cursor.fetchall()
    for machine in machines:
        username = normalize_machine_username(machine['id'])
        display_name = machine['operator'] or f"{machine['name']} 工作人员"
        cursor.execute('SELECT id FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            cursor.execute('''
                UPDATE users
                SET display_name = %s, machine_id = %s, role = 'worker'
                WHERE username = %s
            ''', (display_name, machine['id'], username))
            continue

        cursor.execute('''
            INSERT INTO users (username, password_hash, display_name, role, machine_id)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            username,
            generate_password_hash(default_worker_password(machine['id'])),
            display_name,
            'worker',
            machine['id']
        ))

    conn.commit()
    conn.close()
    AUTH_SCHEMA_READY = True

def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    conn = None
    try:
        ensure_auth_schema()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, display_name, role, machine_id, is_active, auth_version
            FROM users
            WHERE id = %s
        ''', (user_id,))
        user = cursor.fetchone()
    except Exception:
        session.clear()
        return None
    finally:
        if conn is not None:
            conn.close()

    if not user or not user['is_active'] or int(user.get('auth_version') or 1) != int(session.get('auth_version') or 0):
        session.clear()
        return None

    return {
        'id': user['id'],
        'username': user['username'],
        'display_name': user['display_name'],
        'role': user['role'],
        'machine_id': user['machine_id']
    }

def wants_json_response():
    return request.path.startswith('/api/')

def is_worker_path(path):
    return (
        path in {'/worker', '/worker.html'}
        or path.startswith('/api/worker/')
    )

@app.before_request
def require_login_for_admin_app():
    if request.method == 'OPTIONS':
        return None

    path = request.path
    public_paths = {
        '/login',
        '/login.html',
        '/worker/login',
        '/worker-login.html',
        '/login.css',
        '/api/auth/login',
        '/api/auth/me'
    }
    shared_auth_paths = {'/api/auth/logout', '/api/auth/change_password'}
    shared_map_paths = {'/api/map/config'}
    public_asset_exts = ('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.map')

    if path in public_paths:
        return None
    if path != '/index.html' and path.endswith(public_asset_exts):
        return None

    user = current_user()
    if not user:
        if wants_json_response():
            redirect_target = '/worker/login' if is_worker_path(path) else '/login'
            return jsonify({'error': '未登录', 'redirect': redirect_target}), 401
        if is_worker_path(path):
            return redirect(url_for('serve_worker_login'))
        return redirect(url_for('serve_login'))

    if path in shared_auth_paths:
        return None

    if path in shared_map_paths or path.startswith('/_AMapService/'):
        return None

    if is_worker_path(path):
        if user['role'] != 'worker':
            if wants_json_response():
                return jsonify({'error': '当前页面仅工作人员账号可访问'}), 403
            return '当前页面仅工作人员账号可访问，管理员请进入电脑端管理页面。', 403
        return None

    if user['role'] != 'admin':
        if wants_json_response():
            return jsonify({'error': '当前电脑端仅管理员可访问'}), 403
        return '当前电脑端仅管理员可访问，工作人员请进入手机端页面。', 403

# ============================================================
#  静态文件服务（前端页面）
# ============================================================

@app.route('/login')
def serve_login():
    response = make_response(send_from_directory('static', 'login.html'))
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response

@app.route('/worker/login')
def serve_worker_login():
    response = make_response(send_from_directory('static', 'worker-login.html'))
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response

@app.route('/worker')
def serve_worker_app():
    response = make_response(send_from_directory('static', 'worker.html'))
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response

@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

# ============================================================
#  登录认证 API
# ============================================================

def attach_csrf_cookie(response):
    token = session.get('csrf_token')
    if token:
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            secure=False,
            httponly=False,
            samesite='Lax',
            path='/'
        )
    return response

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        ensure_auth_schema()
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        requested_role = (data.get('role') or 'admin').strip().lower()

        if not username or not password:
            return jsonify({'error': '请输入账号和密码'}), 400
        if len(username) > 100 or len(password) > 256:
            return jsonify({'error': '账号或密码长度无效'}), 400
        if requested_role not in ('admin', 'worker'):
            return jsonify({'error': '登录角色无效'}), 400
        blocked_seconds = get_login_block_seconds(username)
        if blocked_seconds:
            return jsonify({
                'error': f'登录失败次数过多，请 {format_wait_seconds(blocked_seconds)} 后再试'
            }), 429

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, password_hash, display_name, role, machine_id, is_active, auth_version
            FROM users
            WHERE username = %s
        ''', (username,))
        user = cursor.fetchone()
        conn.close()

        if not user or not user['is_active'] or not check_password_hash(user['password_hash'], password):
            register_login_failure(username)
            return jsonify({'error': '账号或密码错误'}), 401

        if user['role'] != requested_role:
            if requested_role == 'admin':
                return jsonify({'error': '该账号是工作人员账号，请使用手机端工作人员入口登录'}), 403
            return jsonify({'error': '该账号是管理员账号，请使用电脑端管理入口登录'}), 403

        clear_login_failures(username)
        session.clear()
        session['user_id'] = user['id']
        session['auth_version'] = int(user.get('auth_version') or 1)
        session['csrf_token'] = secrets.token_urlsafe(32)

        response = jsonify({
            'message': '登录成功',
            'redirect': '/worker' if user['role'] == 'worker' else '/',
            'user': current_user()
        })
        return attach_csrf_cookie(response)
    except Exception as exc:
        print(f'登录初始化失败：{exc}')
        return jsonify({'error': '登录初始化失败'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    response = jsonify({'message': '已退出登录'})
    response.delete_cookie(CSRF_COOKIE_NAME, path='/')
    return response

@app.route('/api/auth/change_password', methods=['POST'])
def change_password():
    user = current_user()
    if not user:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json() or {}
    current_password = data.get('current_password') or ''
    new_password = data.get('new_password') or ''

    if not current_password or not new_password:
        return jsonify({'error': '请输入当前密码和新密码'}), 400
    if len(current_password) > 256 or len(new_password) > 256:
        return jsonify({'error': '密码长度无效'}), 400
    if len(new_password) < 12:
        return jsonify({'error': '新密码至少需要 12 位'}), 400
    if current_password == new_password:
        return jsonify({'error': '新密码不能和当前密码相同'}), 400

    try:
        ensure_auth_schema()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT password_hash, auth_version FROM users WHERE id = %s', (user['id'],))
        row = cursor.fetchone()

        if not row or not check_password_hash(row['password_hash'], current_password):
            conn.close()
            return jsonify({'error': '当前密码不正确'}), 401

        new_auth_version = int(row.get('auth_version') or 1) + 1
        cursor.execute('''
            UPDATE users
            SET password_hash = %s, auth_version = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (generate_password_hash(new_password), new_auth_version, user['id']))
        conn.commit()
        conn.close()
        session['auth_version'] = new_auth_version
        session['csrf_token'] = secrets.token_urlsafe(32)
        return attach_csrf_cookie(jsonify({'message': '密码已更新，其他已登录会话已失效'}))
    except Exception as exc:
        print(f'修改密码失败：{exc}')
        return jsonify({'error': '修改密码失败'}), 500

@app.route('/api/auth/me')
def auth_me():
    user = current_user()
    return jsonify({
        'authenticated': bool(user),
        'user': user
    })

@app.route('/api/map/config')
def map_runtime_config():
    amap_config = load_amap_runtime_config()
    return jsonify({
        'provider': 'amap' if amap_config['configured'] else 'leaflet',
        'configured': amap_config['configured'],
        'key': amap_config['key'] if amap_config['configured'] else '',
        'service_host': request.host_url.rstrip('/') + '/_AMapService',
        'version': '2.0',
    })

@app.route('/_AMapService/<path:service_path>', methods=['GET'])
def amap_service_proxy(service_path):
    amap_config = load_amap_runtime_config()
    if not amap_config['configured']:
        return jsonify({'error': '高德地图尚未完成本机配置'}), 503

    clean_path = service_path.strip('/')
    if not clean_path or '..' in clean_path.split('/'):
        return jsonify({'error': '无效的高德服务路径'}), 400

    target_origin = (
        'https://webapi.amap.com'
        if clean_path.startswith('v4/map/styles')
        else 'https://restapi.amap.com'
    )
    query_items = []
    for key in request.args:
        if key.lower() == 'jscode':
            continue
        query_items.extend((key, value) for value in request.args.getlist(key))
    query_items.append(('jscode', amap_config['security_js_code']))
    target_url = f"{target_origin}/{clean_path}?{urlencode(query_items)}"

    try:
        upstream_request = UrlRequest(
            target_url,
            headers={
                'Accept': request.headers.get('Accept', '*/*'),
                'User-Agent': 'FarmManagementMapProxy/1.0',
            },
        )
        with urlopen(upstream_request, timeout=12) as upstream:
            body = upstream.read()
            response = make_response(body, upstream.status)
            for header_name in ('Content-Type', 'Cache-Control', 'Expires', 'ETag'):
                header_value = upstream.headers.get(header_name)
                if header_value:
                    response.headers[header_name] = header_value
            return response
    except HTTPError as exc:
        body = exc.read()
        response = make_response(body, exc.code)
        response.headers['Content-Type'] = exc.headers.get('Content-Type', 'application/json')
        return response
    except (URLError, TimeoutError, OSError):
        return jsonify({'error': '高德地图服务暂时不可用'}), 502

# ============================================================
#  工作人员手机端 API
# ============================================================

def worker_machine_id():
    user = current_user()
    return user.get('machine_id') if user else None

def build_worker_task_list(cursor, machine_id):
    cursor.execute('''
        SELECT
            t.id, t.machine_id, t.farmland_id, t.operation_type, t.status,
            t.task_order, t.created_at,
            f.name AS farmland_name, f.crop, f.status AS field_status,
            f.lng AS farmland_lng, f.lat AS farmland_lat, f.altitude AS farmland_altitude,
            f.area_sqm
        FROM tasks t
        LEFT JOIN fields f ON f.id = t.farmland_id
        WHERE t.machine_id = %s AND t.status != '已撤销'
        ORDER BY t.task_order, t.id
    ''', (machine_id,))
    rows = cursor.fetchall()

    tasks = []
    for i, row in enumerate(rows, 1):
        area_sqm = to_float(row.get('area_sqm'))
        tasks.append({
            'id': row['id'],
            'machine_id': row['machine_id'],
            'farmland_id': row['farmland_id'],
            'farmland_name': row.get('farmland_name') or row['farmland_id'],
            'crop': row.get('crop') or '待定',
            'field_status': row.get('field_status') or '待作业',
            'farmland_lng': to_float(row.get('farmland_lng'), None),
            'farmland_lat': to_float(row.get('farmland_lat'), None),
            'farmland_altitude': to_float(row.get('farmland_altitude')),
            'area_sqm': area_sqm,
            'area_mu': round(area_sqm / 666.67, 2) if area_sqm else 0,
            'operation_type': row.get('operation_type') or '作业',
            'status': row.get('status') or '待接收',
            'task_order': row.get('task_order') or i,
            'created_at': format_datetime_value(row.get('created_at'))
        })
    return tasks

def build_worker_machine_payload(row, tasks=None):
    if not row:
        return None

    tasks = tasks or []
    total_area_mu = sum(to_float(task.get('area_mu')) for task in tasks)
    position_source = row.get('position_source') or 'demo'
    effective_status = 'idle' if row.get('status') == 'online' else (row.get('status') or 'offline')
    if is_realtime_position_source(position_source):
        if not realtime_position_is_fresh(row.get('last_seen'), position_source):
            effective_status = 'offline'
        elif any(task.get('status') == '已接收' for task in tasks):
            effective_status = 'working'
    return {
        'id': row['id'],
        'name': row['name'],
        'type': row.get('type') or 'tractor',
        'org': row.get('org') or '',
        'operator': row.get('operator') or '',
        'status': effective_status,
        'lng': to_float(row.get('lng')),
        'lat': to_float(row.get('lat')),
        'altitude': to_float(row.get('altitude')),
        'speed': to_float(row.get('speed')),
        'area': round(total_area_mu, 2),
        'work_time': to_float(row.get('work_time')),
        'signal': int(to_float(row.get('signal'))),
        'alerts': int(to_float(row.get('alerts'))),
        'last_seen': format_time_value(row.get('last_seen')),
        'position_source': position_source,
        'auto_schedulable': bool(row.get('auto_schedulable', 1)),
        'device_no': row.get('device_no') or '',
        'position_device_no': row.get('position_device_no') or '',
        'direction': int(to_float(row.get('direction'))),
        'position_fresh': realtime_position_is_fresh(row.get('last_seen'), position_source) if is_realtime_position_source(position_source) else True,
    }

def build_worker_messages(machine, tasks):
    messages = []
    pending_tasks = [task for task in tasks if task['status'] == '待接收']
    received_tasks = [task for task in tasks if task['status'] == '已接收']
    completed_tasks = [task for task in tasks if task['status'] == '已完成']

    if pending_tasks:
        messages.append({
            'title': '新任务待确认',
            'time': pending_tasks[0].get('created_at')[-5:] or '--:--',
            'body': f"你有 {len(pending_tasks)} 个任务待接收，请及时查看。",
            'level': 'warning'
        })
    if received_tasks:
        messages.append({
            'title': '任务接收进度',
            'time': datetime.now().strftime('%H:%M'),
            'body': f"已接收 {len(received_tasks)}/{len(tasks)} 个任务。",
            'level': 'success'
        })
    if completed_tasks:
        messages.append({
            'title': '任务完成进度',
            'time': datetime.now().strftime('%H:%M'),
            'body': f"已完成 {len(completed_tasks)}/{len(tasks)} 个任务。",
            'level': 'success'
        })
    if machine and machine.get('alerts', 0) > 0:
        messages.append({
            'title': '农机预警',
            'time': machine.get('last_seen') or '--:--',
            'body': f"{machine['name']} 当前有 {machine['alerts']} 条预警，请留意设备状态。",
            'level': 'danger'
        })
    if machine and machine.get('signal', 100) < 60:
        messages.append({
            'title': '信号较弱',
            'time': machine.get('last_seen') or '--:--',
            'body': f"{machine['name']} 当前信号 {machine['signal']}%，请确认终端在线情况。",
            'level': 'warning'
        })
    if not messages:
        messages.append({
            'title': '暂无异常通知',
            'time': datetime.now().strftime('%H:%M'),
            'body': '当前任务和农机状态正常。',
            'level': 'normal'
        })
    return messages

def fetch_worker_data():
    machine_id = worker_machine_id()
    if not machine_id:
        return None, None, [], '当前工作人员账号未绑定农机'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, type, org, operator, status,
               lng, lat, altitude, speed, area, `signal`, alerts, last_seen, work_time,
               auto_schedulable, position_source, device_no, direction,
               (SELECT mp.device_no
                FROM machine_positions mp
                WHERE mp.machine_id = machines.id
                ORDER BY mp.id DESC
                LIMIT 1) AS position_device_no
        FROM machines
        WHERE id = %s
    ''', (machine_id,))
    machine_row = cursor.fetchone()
    tasks = build_worker_task_list(cursor, machine_id)
    conn.close()

    if not machine_row:
        return machine_id, None, tasks, '未找到绑定农机'

    machine = build_worker_machine_payload(machine_row, tasks)
    return machine_id, machine, tasks, None

@app.route('/api/worker/overview')
def worker_overview():
    machine_id, machine, tasks, error = fetch_worker_data()
    if error:
        return jsonify({'error': error, 'machine_id': machine_id}), 404

    pending = len([task for task in tasks if task['status'] == '待接收'])
    received = len([task for task in tasks if task['status'] == '已接收'])
    completed = len([task for task in tasks if task['status'] == '已完成'])
    route_points = [[machine['lat'], machine['lng']]]
    route_points.extend([
        [task['farmland_lat'], task['farmland_lng']]
        for task in tasks
        if task['farmland_lat'] is not None and task['farmland_lng'] is not None
    ])
    if len(route_points) > 1:
        route_points.append([machine['lat'], machine['lng']])

    return jsonify({
        'user': current_user(),
        'machine': machine,
        'tasks': tasks,
        'summary': {
            'total_tasks': len(tasks),
            'pending_tasks': pending,
            'received_tasks': received,
            'completed_tasks': completed,
            'completion_rate': round(completed / len(tasks) * 100, 1) if tasks else 0,
            'total_area_mu': round(sum(to_float(task.get('area_mu')) for task in tasks), 2)
        },
        'map': {
            'machine': machine,
            'fields': tasks,
            'route_points': route_points
        },
        'messages': build_worker_messages(machine, tasks)
    })

@app.route('/api/worker/machine')
def worker_machine():
    machine_id, machine, tasks, error = fetch_worker_data()
    if error:
        return jsonify({'error': error, 'machine_id': machine_id}), 404
    return jsonify({'machine': machine})

@app.route('/api/worker/tasks')
def worker_tasks():
    machine_id, machine, tasks, error = fetch_worker_data()
    if error:
        return jsonify({'error': error, 'machine_id': machine_id}), 404
    return jsonify({'machine': machine, 'tasks': tasks})

@app.route('/api/worker/tasks/<int:task_id>/confirm', methods=['POST'])
def worker_confirm_task(task_id):
    machine_id = worker_machine_id()
    if not machine_id:
        return jsonify({'error': '当前工作人员账号未绑定农机'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, status FROM tasks WHERE id = %s AND machine_id = %s', (task_id, machine_id))
    task = cursor.fetchone()
    if not task:
        conn.close()
        return jsonify({'error': '未找到当前农机对应的任务'}), 404

    if task['status'] == '已完成':
        conn.close()
        return jsonify({'error': '已完成任务不能重新确认接收'}), 400

    if task['status'] not in ('待接收', '已接收'):
        conn.close()
        return jsonify({'error': f"当前任务状态为 {task['status']}，不能确认接收"}), 400

    if task['status'] == '待接收':
        cursor.execute('UPDATE tasks SET status = "已接收" WHERE id = %s AND machine_id = %s', (task_id, machine_id))
    update_machine_operating_status(cursor, machine_id, 'working')
    conn.commit()
    conn.close()
    return jsonify({'message': '任务已确认接收，农机已进入作业中状态', 'task_id': task_id, 'machine_status': 'working'})

@app.route('/api/worker/tasks/<int:task_id>/complete', methods=['POST'])
def worker_complete_task(task_id):
    machine_id = worker_machine_id()
    if not machine_id:
        return jsonify({'error': '当前工作人员账号未绑定农机'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.id, t.status, f.lng, f.lat, f.altitude,
               m.position_source
        FROM tasks t
        LEFT JOIN fields f ON f.id = t.farmland_id
        INNER JOIN machines m ON m.id = t.machine_id
        WHERE t.id = %s AND t.machine_id = %s
    ''', (task_id, machine_id))
    task = cursor.fetchone()
    if not task:
        conn.close()
        return jsonify({'error': '未找到当前农机对应的任务'}), 404

    if task['status'] == '待接收':
        conn.close()
        return jsonify({'error': '请先确认接收任务，再提交完成'}), 400

    if task['status'] != '已完成':
        cursor.execute('UPDATE tasks SET status = "已完成" WHERE id = %s AND machine_id = %s', (task_id, machine_id))

    cursor.execute('''
        SELECT COUNT(*) AS active_count
        FROM tasks
        WHERE machine_id = %s AND status = '已接收' AND id != %s
    ''', (machine_id, task_id))
    active_count = int(cursor.fetchone()['active_count'] or 0)
    next_machine_status = 'working' if active_count > 0 else 'idle'
    last_seen = beijing_now_text()

    if not is_realtime_position_source(task.get('position_source')) and task.get('lng') is not None and task.get('lat') is not None:
        cursor.execute('''
            UPDATE machines
            SET lng = %s, lat = %s, altitude = %s, status = %s, last_seen = %s
            WHERE id = %s
        ''', (task['lng'], task['lat'], task.get('altitude') or 0, next_machine_status, last_seen, machine_id))
    else:
        update_machine_operating_status(cursor, machine_id, next_machine_status)
    conn.commit()
    conn.close()
    return jsonify({
        'message': '任务已提交完成',
        'task_id': task_id,
        'machine_status': next_machine_status,
        'remaining_active_tasks': active_count,
    })

@app.route('/api/worker/tasks/<int:task_id>', methods=['DELETE'])
def worker_delete_task(task_id):
    machine_id = worker_machine_id()
    if not machine_id:
        return jsonify({'error': '当前工作人员账号未绑定农机'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, status FROM tasks WHERE id = %s AND machine_id = %s', (task_id, machine_id))
    task = cursor.fetchone()
    if not task:
        conn.close()
        return jsonify({'error': '未找到当前农机对应的任务'}), 404

    if task['status'] != '已完成':
        conn.close()
        return jsonify({'error': '只能删除已完成的任务'}), 400

    cursor.execute('DELETE FROM tasks WHERE id = %s AND machine_id = %s', (task_id, machine_id))
    conn.commit()
    conn.close()
    return jsonify({'message': '已完成任务已删除', 'task_id': task_id})

@app.route('/api/worker/messages')
def worker_messages():
    machine_id, machine, tasks, error = fetch_worker_data()
    if error:
        return jsonify({'error': error, 'machine_id': machine_id}), 404
    return jsonify({'messages': build_worker_messages(machine, tasks)})

# ============================================================
#  任务管理 API
# ============================================================

@app.route('/api/tasks')
def get_tasks():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, machine_id, farmland_id, operation_type, status FROM tasks ORDER BY id DESC')
    results = cursor.fetchall()
    conn.close()
    return jsonify(results)

@app.route('/api/tasks/confirm/<int:task_id>', methods=['POST'])
def confirm_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, machine_id, status FROM tasks WHERE id = %s', (task_id,))
    task = cursor.fetchone()
    if not task:
        conn.close()
        return jsonify({'error': '未找到要确认的任务'}), 404

    if task['status'] == '已完成':
        conn.close()
        return jsonify({'error': '已完成任务不能重新确认接收'}), 400

    if task['status'] not in ('待接收', '已接收'):
        conn.close()
        return jsonify({'error': f"当前任务状态为 {task['status']}，不能确认接收"}), 400

    if task['status'] == '待接收':
        cursor.execute('UPDATE tasks SET status = "已接收" WHERE id = %s', (task_id,))
    update_machine_operating_status(cursor, task['machine_id'], 'working')
    conn.commit()
    conn.close()
    return jsonify({
        'message': '任务已确认，农机已进入作业中状态！',
        'task_id': task_id,
        'machine_id': task['machine_id'],
        'machine_status': 'working',
    })

@app.route('/api/tasks/add', methods=['POST'])
def add_task():
    data = request.get_json()
    machine_id = data.get('machine_id')
    farmland_id = data.get('farmland_id')
    operation_type = data.get('operation_type') or '手动作业'
    if not machine_id or not farmland_id:
        return jsonify({'error': '缺少必要字段'}), 400
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM machines WHERE id = %s', (machine_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': '农机不存在'}), 404

    cursor.execute('SELECT id FROM fields WHERE id = %s', (farmland_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': '地块不存在'}), 404

    cursor.execute('SELECT MAX(task_order) AS max_order FROM tasks WHERE machine_id = %s', (machine_id,))
    max_order = cursor.fetchone()['max_order'] or 0
    task_order = int(max_order) + 1
    created_at = beijing_now_text()

    cursor.execute(
        'INSERT INTO tasks (machine_id, farmland_id, operation_type, status, task_order, created_at) VALUES (%s, %s, %s, "待接收", %s, %s)',
        (machine_id, farmland_id, operation_type, task_order, created_at)
    )
    machine_status = sync_machine_status_from_tasks(cursor, machine_id)
    conn.commit()
    conn.close()
    return jsonify({
        'message': '任务添加成功！',
        'task': {
            'machine_id': machine_id,
            'farmland_id': farmland_id,
            'operation_type': operation_type,
            'status': '待接收',
            'task_order': task_order,
            'created_at': created_at,
            'machine_status': machine_status,
        }
    })

@app.route('/api/tasks/delete/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, status FROM tasks WHERE id = %s', (task_id,))
    task = cursor.fetchone()
    if not task:
        conn.close()
        return jsonify({'error': '未找到要删除的任务'}), 404

    if task['status'] != '已完成':
        conn.close()
        return jsonify({'error': '只能删除已完成的任务'}), 400

    cursor.execute('DELETE FROM tasks WHERE id = %s', (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': '已完成任务已删除！', 'task_id': task_id})

# ============================================================
#  农机 API
# ============================================================

@app.route('/api/machines')
def get_machines():
    ensure_schedule_schema()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 获取农机基础信息（包含 work_time）
    cursor.execute('''
        SELECT id, name, type, org, operator, status,
               lng, lat, altitude, speed, area, `signal`, alerts, last_seen, work_time,
               auto_schedulable, position_source, device_no, direction,
               (SELECT mp.device_no
                FROM machine_positions mp
                WHERE mp.machine_id = machines.id
                ORDER BY mp.id DESC
                LIMIT 1) AS position_device_no
        FROM machines
        ORDER BY id
    ''')
    results = cursor.fetchall()
    
    # 2. 获取所有任务（用于计算面积）
    cursor.execute('''
        SELECT machine_id, farmland_id, status
        FROM tasks
        WHERE status != '已撤销'
    ''')
    tasks = cursor.fetchall()
    
    # 3. 获取所有农田的面积
    cursor.execute('SELECT id, area_sqm FROM fields')
    fields = cursor.fetchall()
    field_area_map = {f['id']: float(f['area_sqm'] or 0) for f in fields}

    cursor.execute('SELECT DISTINCT machine_id FROM machine_positions')
    realtime_position_ids = {row['machine_id'] for row in cursor.fetchall()}
    
    # 4. 按农机分组计算总面积（亩）
    machine_area_map = {}
    machine_task_status_map = {}
    for task in tasks:
        machine_id = task['machine_id']
        farmland_id = task['farmland_id']
        area_sqm = field_area_map.get(farmland_id, 0)
        machine_area_map[machine_id] = machine_area_map.get(machine_id, 0) + area_sqm
        status_counts = machine_task_status_map.setdefault(machine_id, {'received': 0, 'pending': 0})
        if task['status'] == '已接收':
            status_counts['received'] += 1
        elif task['status'] == '待接收':
            status_counts['pending'] += 1
    
    conn.close()
    
    # 5. 组装返回数据
    machines = []
    for row in results:
        machine_id = row['id']
        total_area_sqm = machine_area_map.get(machine_id, 0)
        total_area_mu = total_area_sqm / 666.67  # 转换为亩
        task_status_counts = machine_task_status_map.get(machine_id, {})
        position_source = row.get('position_source') or 'demo'
        position_fresh = realtime_position_is_fresh(row.get('last_seen'), position_source) if is_realtime_position_source(position_source) else True
        effective_status = 'idle' if row['status'] == 'online' else row['status']
        if is_realtime_position_source(position_source) and not position_fresh:
            effective_status = 'offline'
        elif task_status_counts.get('received', 0) > 0:
            effective_status = 'working'
        elif task_status_counts.get('pending', 0) > 0:
            effective_status = 'idle'
        
        machines.append({
            'id': machine_id,
            'name': row['name'],
            'type': row['type'],
            'org': row['org'],
            'operator': row['operator'],
            'status': effective_status,
            'lng': float(row['lng']),
            'lat': float(row['lat']),
            'altitude': float(row['altitude']) if row['altitude'] else 0,
            'speed': float(row['speed']) if row['speed'] else 0,
            'area': round(total_area_mu, 2),
            'work_time': float(row['work_time']) if row['work_time'] else 0,
            'signal': row['signal'],
            'alerts': row['alerts'],
            'lastSeen': format_time_value(row['last_seen']),
            'lastSeenAt': format_datetime_value(row['last_seen']),
            'auto_schedulable': bool(row.get('auto_schedulable', 1)),
            'position_source': position_source,
            'device_no': row.get('device_no') or '',
            'position_device_no': row.get('position_device_no') or row.get('device_no') or '',
            'direction': int(to_float(row.get('direction'))),
            'position_fresh': position_fresh,
            'has_realtime_position': machine_id in realtime_position_ids
                                     or (
                                         is_realtime_position_source(position_source)
                                         and bool(row.get('device_no'))
                                         and row.get('last_seen') != '2000-01-01 00:00:00'
                                     ),
            'is_demo': position_source == 'demo',
        })
    return jsonify(machines)

# ============================================================
#  农田 API
# ============================================================

@app.route('/api/fields')
def get_fields():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, crop, status, lng, lat, altitude, area_sqm, polygon FROM fields ORDER BY id')
    results = cursor.fetchall()
    conn.close()
    
    fields = []
    for row in results:
        if row['polygon']:
            polygon = json.loads(row['polygon'])
        else:
            lng = float(row['lng'])
            lat = float(row['lat'])
            area_sqm = max(100.0, float(row['area_sqm'] or 500.0))
            width_m = math.sqrt(area_sqm * 1.5)
            height_m = area_sqm / width_m
            lng_delta = width_m / (2 * 111_320 * math.cos(math.radians(lat)))
            lat_delta = height_m / (2 * 111_320)
            polygon = [
                [lat - lat_delta, lng - lng_delta],
                [lat + lat_delta, lng - lng_delta],
                [lat + lat_delta, lng + lng_delta],
                [lat - lat_delta, lng + lng_delta]
            ]
        fields.append({
            'id': row['id'],
            'name': row['name'],
            'crop': row['crop'],
            'status': row['status'],
            'lng': float(row['lng']),
            'lat': float(row['lat']),
            'altitude': float(row['altitude']) if row['altitude'] else 0,
            'area_sqm': float(row['area_sqm']) if row['area_sqm'] else 0,
            'polygon': polygon
        })
    return jsonify(fields)

# ============================================================
#  轨迹 API
# ============================================================

@app.route('/api/tracks/<machine_id>')
def get_track(machine_id):
    ensure_schedule_schema()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT position_source FROM machines WHERE id = %s', (machine_id,))
    machine = cursor.fetchone()
    if machine and is_realtime_position_source(machine.get('position_source')):
        query_start = request.args.get('start')
        query_end = request.args.get('end')
        range_requested = bool(query_start or query_end)
        if range_requested and (not query_start or not query_end):
            conn.close()
            return jsonify({'error': '开始时间和结束时间必须同时提供'}), 400
        start_dt = end_dt = None
        if range_requested:
            try:
                start_dt = datetime.fromisoformat(query_start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(query_end.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=BEIJING_TZ)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=BEIJING_TZ)
                start_dt = start_dt.astimezone(BEIJING_TZ)
                end_dt = end_dt.astimezone(BEIJING_TZ)
            except ValueError:
                conn.close()
                return jsonify({'error': '时间格式无效'}), 400
            if start_dt >= end_dt:
                conn.close()
                return jsonify({'error': '开始时间必须早于结束时间'}), 400
            if end_dt - start_dt > timedelta(days=7):
                conn.close()
                return jsonify({'error': '单次最多查询 7 天'}), 400

        vendor_history_error = None
        if range_requested and str(machine.get('position_source') or '').strip().lower() == 'gpswv':
            conn.close()
            try:
                return jsonify(fetch_gpswv_history_track(machine_id, start_dt, end_dt))
            except Exception as exc:
                vendor_history_error = str(exc)
                app.logger.warning('GPSWV history query failed for %s: %s', machine_id, vendor_history_error)
                conn = get_db_connection()
                cursor = conn.cursor()

        if range_requested:
            start_text = start_dt.strftime('%Y-%m-%d %H:%M:%S')
            end_text = end_dt.strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                SELECT lng, lat, speed, direction, source_time, received_at
                FROM machine_positions
                WHERE machine_id = %s
                  AND COALESCE(source_time, received_at) >= %s
                  AND COALESCE(source_time, received_at) <= %s
                ORDER BY COALESCE(source_time, received_at) ASC, id ASC
            ''', (machine_id, start_text, end_text))
            position_rows = cursor.fetchall()
        else:
            cursor.execute('''
                SELECT lng, lat, speed, direction, source_time, received_at
                FROM machine_positions
                WHERE machine_id = %s
                ORDER BY id DESC
                LIMIT 500
            ''', (machine_id,))
            position_rows = cursor.fetchall()
            position_rows.reverse()

        raw_point_count = len(position_rows)
        if range_requested and not raw_point_count and vendor_history_error:
            conn.close()
            return jsonify({'error': f'商家历史轨迹接口失败：{vendor_history_error}'}), 502
        sampled = False
        if range_requested and raw_point_count > 5000:
            step = math.ceil(raw_point_count / 5000)
            last_row = position_rows[-1]
            position_rows = position_rows[::step]
            if position_rows and position_rows[-1] != last_row:
                position_rows.append(last_row)
            sampled = True
        conn.close()
        points = [[to_float(row.get('lat')), to_float(row.get('lng'))] for row in position_rows]
        point_times = [
            parse_database_datetime(row.get('source_time') or row.get('received_at'))
            for row in position_rows
        ]
        distance = 0.0
        for index in range(1, len(points)):
            distance += geographic_distance_km(
                points[index - 1][1], points[index - 1][0],
                points[index][1], points[index][0]
            )
        start_time = point_times[0] if point_times else None
        end_time = point_times[-1] if point_times else None
        duration = max(0, int((end_time - start_time).total_seconds())) if start_time and end_time else 0
        elapsed_seconds = []
        for index, point_time in enumerate(point_times):
            if start_time and point_time:
                elapsed = max(0, int((point_time - start_time).total_seconds()))
            else:
                elapsed = index * 5
            if elapsed_seconds:
                elapsed = max(elapsed, elapsed_seconds[-1])
            elapsed_seconds.append(elapsed)
        return jsonify({
            'machineId': machine_id,
            'queryStart': start_dt.strftime('%Y-%m-%d %H:%M:%S') if start_dt else None,
            'queryEnd': end_dt.strftime('%Y-%m-%d %H:%M:%S') if end_dt else None,
            'rawPointCount': raw_point_count,
            'sampled': sampled,
            'points': points,
            'timestamps': [format_datetime_value(row.get('source_time') or row.get('received_at')) for row in position_rows],
            'elapsedSeconds': elapsed_seconds,
            'distance': round(distance, 3),
            'duration': duration,
            'trackDate': format_date_value(position_rows[-1].get('source_time') or position_rows[-1].get('received_at')) if position_rows else None,
            'start_lng': points[0][1] if points else None,
            'start_lat': points[0][0] if points else None,
            'end_lng': points[-1][1] if points else None,
            'end_lat': points[-1][0] if points else None,
            'realtime': True,
        })

    cursor.execute('''
        SELECT points, distance, duration, track_date,
               start_lng, start_lat, end_lng, end_lat
        FROM tracks
        WHERE machine_id = %s
        ORDER BY track_date DESC, id DESC
        LIMIT 1
    ''', (machine_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        points = json.loads(result['points'])
        return jsonify({
            'machineId': machine_id,
            'points': points,
            'timestamps': [f'09:{str(i*3).zfill(2)}' for i in range(len(points))],
            'distance': float(result['distance']),
            'duration': result['duration'],
            'trackDate': format_date_value(result['track_date']),
            'start_lng': float(result['start_lng']),
            'start_lat': float(result['start_lat']),
            'end_lng': float(result['end_lng']),
            'end_lat': float(result['end_lat']),
            'realtime': False,
        })
    else:
        return jsonify({
            'machineId': machine_id,
            'points': [],
            'timestamps': [],
            'distance': 0,
            'duration': 0,
            'trackDate': None,
            'start_lng': None,
            'start_lat': None,
            'end_lng': None,
            'end_lat': None,
            'realtime': False,
        })

# ============================================================
#  终端统计 API
# ============================================================

@app.route('/api/tracks/<machine_id>/history')
def get_track_history(machine_id):
    """Return selectable historical tracks for the left track panel."""
    ensure_schedule_schema()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT position_source FROM machines WHERE id = %s', (machine_id,))
    machine = cursor.fetchone()
    if not machine:
        conn.close()
        return jsonify([])
    if is_realtime_position_source(machine.get('position_source')):
        # Realtime positions are exposed as the current continuous track. Once
        # archived position batches are available, this endpoint can return
        # one record per day without changing the frontend contract.
        cursor.execute('''
            SELECT lng, lat, speed, direction, source_time, received_at
            FROM machine_positions
            WHERE machine_id = %s
            ORDER BY id ASC
            LIMIT 500
        ''', (machine_id,))
        rows = cursor.fetchall()
        conn.close()
        points = [[to_float(row.get('lat')), to_float(row.get('lng'))] for row in rows]
        if not points:
            return jsonify([])
        return jsonify([{
            'id': 'realtime-current',
            'label': '当前实时轨迹',
            'trackDate': format_date_value(rows[-1].get('source_time') or rows[-1].get('received_at')),
            'points': points,
            'distance': 0,
            'duration': 0,
            'realtime': True,
        }])
    cursor.execute('''
        SELECT id, points, distance, duration, track_date,
               start_lng, start_lat, end_lng, end_lat
        FROM tracks
        WHERE machine_id = %s
        ORDER BY track_date DESC, id DESC
        LIMIT 30
    ''', (machine_id,))
    rows = cursor.fetchall()
    conn.close()
    history = []
    for row in rows:
        try:
            points = json.loads(row['points'])
        except (TypeError, ValueError):
            points = []
        history.append({
            'id': row['id'],
            'label': format_date_value(row['track_date']) or f"轨迹 {row['id']}",
            'trackDate': format_date_value(row['track_date']),
            'points': points,
            'distance': float(row['distance'] or 0),
            'duration': int(row['duration'] or 0),
            'start_lng': float(row['start_lng']),
            'start_lat': float(row['start_lat']),
            'end_lng': float(row['end_lng']),
            'end_lat': float(row['end_lat']),
            'realtime': False,
        })
    return jsonify(history)

@app.route('/api/terminal/stats')
def get_terminal_stats():
    ensure_schedule_schema()
    conn = get_db_connection()
    cursor = conn.cursor()
    status_rows = get_effective_machine_status_rows(cursor)
    conn.close()
    working = len([row for row in status_rows if row['status'] == 'working'])
    idle = len([row for row in status_rows if row['status'] == 'idle'])
    offline = len([row for row in status_rows if row['status'] == 'offline'])
    online_rows = [row for row in status_rows if row['status'] != 'offline']
    avg_signal = sum(row['signal'] for row in online_rows) / len(online_rows) if online_rows else 0
    return jsonify({
        'online': len(online_rows),
        'working': working,
        'idle': idle,
        'offline': offline,
        'avgSignal': round(avg_signal)
    })

# ============================================================
#  仪表盘 API
# ============================================================

@app.route('/api/dashboard')
def get_dashboard():
    ensure_schedule_schema()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as total FROM tasks')
    total = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as received FROM tasks WHERE status IN ('已接收', '已完成')")
    received = cursor.fetchone()['received']
    cursor.execute("SELECT COUNT(*) as completed FROM tasks WHERE status = '已完成'")
    completed = cursor.fetchone()['completed']
    status_rows = get_effective_machine_status_rows(cursor)
    machine_count = len([row for row in status_rows if row['status'] != 'offline'])
    conn.close()
    return jsonify({
        'total_tasks': total,
        'received_tasks': received,
        'completed_tasks': completed,
        'pending_tasks': total - received,
        'machine_count': machine_count,
        'total_machine_count': len(status_rows),
        'completion_rate': round(completed / total * 100, 1) if total > 0 else 0
    })

@app.route('/api/stats')
def get_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as total FROM tasks')
    total = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as received FROM tasks WHERE status IN ('已接收', '已完成')")
    received = cursor.fetchone()['received']
    cursor.execute("SELECT COUNT(*) as completed FROM tasks WHERE status = '已完成'")
    completed = cursor.fetchone()['completed']
    cursor.execute("SELECT COUNT(*) as pending FROM tasks WHERE status = '待接收'")
    pending = cursor.fetchone()['pending']
    conn.close()
    return jsonify({
        'total': total,
        'received': received,
        'completed': completed,
        'pending': pending,
        'completion': round(completed / total * 100, 1) if total > 0 else 0
    })

# ============================================================
#  视频、消息、指令 API
# ============================================================

@app.route('/api/video/streams')
def get_video_streams():
    return jsonify([
        {'id': 'V-1', 'machineId': 'M-001', 'machineName': '耕牛 1号', 'channel': '前视摄像头', 'protocol': 'WebRTC', 'status': '待接入'},
        {'id': 'V-2', 'machineId': 'M-002', 'machineName': '耕牛 2号', 'channel': '驾驶室摄像头', 'protocol': 'WebRTC', 'status': '待接入'}
    ])

@app.route('/api/messages')
def get_messages():
    return jsonify([
        {'title': '新任务分配', 'time': '09:14', 'body': '农机 M-001 已分配至农田 F-001'},
        {'title': '任务完成', 'time': '09:10', 'body': '农机 M-001 已完成犁地作业'},
        {'title': '低电量提醒', 'time': '08:55', 'body': '农机 M-003 电量低于20%，请及时充电'}
    ])

@app.route('/api/command', methods=['POST'])
def send_command():
    data = request.get_json()
    machine_id = data.get('machineId')
    command = data.get('command')
    return jsonify({
        'accepted': True,
        'machineId': machine_id,
        'command': command,
        'reason': '指令已下发'
    })

# ============================================================
#  调度管理 API（方案B：文件交换）
# ============================================================

# 调度文件夹路径
SCHEDULER_DIR = os.path.join(os.path.dirname(__file__), 'scheduler')
os.makedirs(SCHEDULER_DIR, exist_ok=True)
AUTO_SCHEDULE_LOCK = threading.Lock()
SCHEDULABLE_MACHINE_STATUSES = ('online', 'idle')

def get_schedule_progress(cursor):
    cursor.execute('''
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN t.status = '已完成' THEN 1 ELSE 0 END) AS completed,
            SUM(CASE WHEN t.status = '已接收' THEN 1 ELSE 0 END) AS received,
            SUM(CASE WHEN t.status = '待接收' THEN 1 ELSE 0 END) AS pending
        FROM tasks t
        INNER JOIN machines m ON m.id = t.machine_id
        WHERE COALESCE(m.auto_schedulable, 1) = 1
    ''')
    row = cursor.fetchone() or {}
    total = int(row.get('total') or 0)
    completed = int(row.get('completed') or 0)
    received = int(row.get('received') or 0)
    pending = int(row.get('pending') or 0)

    cursor.execute('''
        SELECT
            COUNT(*) AS total_machines,
            SUM(CASE WHEN status IN ('online', 'idle') AND COALESCE(alerts, 0) = 0
                AND EXISTS (
                    SELECT 1 FROM users u
                    WHERE u.machine_id = machines.id AND u.role = 'worker' AND u.is_active = 1
                ) THEN 1 ELSE 0 END) AS eligible_machines,
            SUM(CASE WHEN NOT EXISTS (
                SELECT 1 FROM users u
                WHERE u.machine_id = machines.id AND u.role = 'worker' AND u.is_active = 1
            ) THEN 1 ELSE 0 END) AS unbound_machines
        FROM machines
        WHERE COALESCE(auto_schedulable, 1) = 1
    ''')
    machine_row = cursor.fetchone() or {}
    total_machines = int(machine_row.get('total_machines') or 0)
    eligible_machines = int(machine_row.get('eligible_machines') or 0)
    unbound_machines = int(machine_row.get('unbound_machines') or 0)
    blocking_tasks = max(0, total - completed)

    return {
        'total_tasks': total,
        'completed_tasks': completed,
        'received_tasks': received,
        'pending_tasks': pending,
        'blocking_tasks': blocking_tasks,
        'completion_rate': round(completed / total * 100, 1) if total else 100.0,
        'ready': total == 0 or blocking_tasks == 0,
        'total_machines': total_machines,
        'eligible_machines': eligible_machines,
        'excluded_machines': max(0, total_machines - eligible_machines),
        'unbound_machines': unbound_machines,
    }

def geographic_distance_km(lng1, lat1, lng2, lat2):
    """使用 Haversine 公式计算经纬度之间的实际地表距离。"""
    lng1, lat1, lng2, lat2 = map(math.radians, (lng1, lat1, lng2, lat2))
    delta_lng = lng2 - lng1
    delta_lat = lat2 - lat1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(value)))

def build_auto_schedule(machines, fields):
    """生成近似最优路线，并在任务足够时保证每台参与农机至少一项任务。"""
    routes = []
    for machine in machines:
        routes.append({
            'machine_id': machine['id'],
            'machine_name': machine.get('name') or machine['id'],
            'tail_lng': to_float(machine.get('lng')),
            'tail_lat': to_float(machine.get('lat')),
            'tail_altitude': to_float(machine.get('altitude')),
            'speed': max(0.5, to_float(machine.get('nom_vel'), 4)),
            'fuel': max(0, to_float(machine.get('fuel'), 0.06)),
            'fueltask': max(0, to_float(machine.get('fueltask'), 2)),
            'efficiency': max(1, to_float(machine.get('work_efficiency'), 7000)),
            'predicted_hours': 0.0,
            'estimated_energy': 0.0,
            'tasks': [],
        })

    def calculate_option(route_index, field):
        route = routes[route_index]
        field_lng = to_float(field.get('lng'))
        field_lat = to_float(field.get('lat'))
        field_altitude = to_float(field.get('altitude'))
        area_sqm = max(0, to_float(field.get('area_sqm')))
        distance_km = geographic_distance_km(
            route['tail_lng'], route['tail_lat'], field_lng, field_lat
        )
        uphill_m = max(0, field_altitude - route['tail_altitude'])
        travel_hours = distance_km / route['speed']
        work_hours = area_sqm / route['efficiency']
        terrain_hours = uphill_m / 2000
        energy = distance_km * route['fuel'] + work_hours * route['fueltask']
        incremental_hours = travel_hours + work_hours + terrain_hours
        score = route['predicted_hours'] + incremental_hours + energy * 0.03
        return score, route_index, distance_km, incremental_hours, energy

    def assign_field(route_index, field, option):
        _, _, distance_km, incremental_hours, energy = option
        route = routes[route_index]
        route['tasks'].append({
            'farmland_id': field['id'],
            'distance_km': round(distance_km, 3),
            'estimated_hours': round(incremental_hours, 3),
            'estimated_energy': round(energy, 3),
        })
        route['predicted_hours'] += incremental_hours
        route['estimated_energy'] += energy
        route['tail_lng'] = to_float(field.get('lng'))
        route['tail_lat'] = to_float(field.get('lat'))
        route['tail_altitude'] = to_float(field.get('altitude'))

    remaining = [dict(field) for field in fields]

    # 第一轮采用遗憾值匹配，先为每台参与调度的农机分配一个不同的地块。
    # 这样对应的每个有效工作人员账号都能在手机端至少收到一个任务。
    unseeded_routes = set(range(len(routes)))
    while unseeded_routes and remaining:
        selected = None
        for route_index in unseeded_routes:
            options = [
                (calculate_option(route_index, field), field_index, field)
                for field_index, field in enumerate(remaining)
            ]
            options.sort(key=lambda item: item[0][0])
            best_option, field_index, field = options[0]
            regret = options[1][0][0] - best_option[0] if len(options) > 1 else 0
            candidate = (regret, -best_option[0], route_index, field_index, field, best_option)
            if selected is None or candidate[:2] > selected[:2]:
                selected = candidate

        _, _, route_index, field_index, field, best_option = selected
        assign_field(route_index, field, best_option)
        remaining.pop(field_index)
        unseeded_routes.remove(route_index)

    # 剩余地块继续按位置、能耗和负载进行平衡分配。
    while remaining:
        selected = None
        for field_index, field in enumerate(remaining):
            area_sqm = max(0, to_float(field.get('area_sqm')))
            options = [calculate_option(route_index, field) for route_index in range(len(routes))]
            options.sort(key=lambda item: item[0])
            best = options[0]
            regret = options[1][0] - best[0] if len(options) > 1 else 0
            candidate = (regret, area_sqm, field_index, field, best)
            if selected is None or candidate[:2] > selected[:2]:
                selected = candidate

        _, _, field_index, field, best = selected
        route_index = best[1]
        assign_field(route_index, field, best)
        remaining.pop(field_index)

    return routes

def calculate_plan_metrics(routes):
    total_distance = sum(
        to_float(task.get('distance_km'))
        for route in routes for task in route.get('tasks', [])
    )
    total_hours = sum(to_float(route.get('predicted_hours')) for route in routes)
    total_energy = sum(to_float(route.get('estimated_energy')) for route in routes)
    makespan = max((to_float(route.get('predicted_hours')) for route in routes), default=0)
    total_cost = 0.42 * total_distance + 0.56 * total_energy + 0.42 * 60 * makespan
    return {
        'total_cost': round(total_cost, 4),
        'total_distance_km': round(total_distance, 3),
        'total_estimated_hours': round(total_hours, 3),
        'total_energy': round(total_energy, 3),
        'machine_count': len([route for route in routes if route.get('tasks')]),
        'task_count': sum(len(route.get('tasks', [])) for route in routes),
    }

def save_schedule_plan(cursor, routes, algorithm):
    metrics = calculate_plan_metrics(routes)
    created_at = beijing_now_text()
    cursor.execute('''
        INSERT INTO schedule_plans (
            algorithm, status, total_cost, total_distance_km,
            total_estimated_hours, total_energy, machine_count, task_count, created_at
        ) VALUES (%s, 'draft', %s, %s, %s, %s, %s, %s, %s)
    ''', (
        algorithm,
        metrics['total_cost'],
        metrics['total_distance_km'],
        metrics['total_estimated_hours'],
        metrics['total_energy'],
        metrics['machine_count'],
        metrics['task_count'],
        created_at,
    ))
    plan_id = cursor.lastrowid
    for route in routes:
        for order, task in enumerate(route.get('tasks', []), 1):
            cursor.execute('''
                INSERT INTO schedule_plan_items (
                    plan_id, machine_id, farmland_id, operation_type, task_order,
                    distance_km, estimated_hours, estimated_energy
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                plan_id,
                route['machine_id'],
                task['farmland_id'],
                '智能调度',
                order,
                to_float(task.get('distance_km')),
                to_float(task.get('estimated_hours')),
                to_float(task.get('estimated_energy')),
            ))
    return plan_id

def get_schedule_plan_payload(cursor, plan_id):
    cursor.execute('SELECT * FROM schedule_plans WHERE id = %s', (plan_id,))
    plan = cursor.fetchone()
    if not plan:
        return None

    cursor.execute('''
        SELECT i.machine_id, i.farmland_id, i.operation_type, i.task_order,
               i.distance_km, i.estimated_hours, i.estimated_energy,
               m.name AS machine_name, m.lng AS machine_lng, m.lat AS machine_lat,
               f.name AS farmland_name, f.lng AS farmland_lng, f.lat AS farmland_lat
        FROM schedule_plan_items i
        LEFT JOIN machines m ON m.id = i.machine_id
        LEFT JOIN fields f ON f.id = i.farmland_id
        WHERE i.plan_id = %s
        ORDER BY i.machine_id, i.task_order, i.id
    ''', (plan_id,))
    items = cursor.fetchall()
    assignment = []
    for machine_id in sorted({item['machine_id'] for item in items}):
        machine_items = [item for item in items if item['machine_id'] == machine_id]
        first = machine_items[0]
        assignment.append({
            'machine_id': machine_id,
            'machine_name': first.get('machine_name') or machine_id,
            'machine_lng': to_float(first.get('machine_lng')),
            'machine_lat': to_float(first.get('machine_lat')),
            'task_count': len(machine_items),
            'estimated_hours': round(sum(to_float(item.get('estimated_hours')) for item in machine_items), 3),
            'tasks': [{
                'farmland_id': item['farmland_id'],
                'farmland_name': item.get('farmland_name') or item['farmland_id'],
                'farmland_lng': to_float(item.get('farmland_lng')),
                'farmland_lat': to_float(item.get('farmland_lat')),
                'operation_type': item.get('operation_type') or '智能调度',
                'task_order': item.get('task_order') or index + 1,
                'distance_km': round(to_float(item.get('distance_km')), 3),
                'estimated_hours': round(to_float(item.get('estimated_hours')), 3),
                'estimated_energy': round(to_float(item.get('estimated_energy')), 3),
                'status': '候选',
            } for index, item in enumerate(machine_items)],
        })

    return {
        'id': plan['id'],
        'algorithm': plan['algorithm'],
        'status': plan['status'],
        'total_cost': round(to_float(plan.get('total_cost')), 4),
        'total_distance_km': round(to_float(plan.get('total_distance_km')), 3),
        'total_estimated_hours': round(to_float(plan.get('total_estimated_hours')), 3),
        'total_energy': round(to_float(plan.get('total_energy')), 3),
        'machine_count': int(plan.get('machine_count') or 0),
        'task_count': int(plan.get('task_count') or 0),
        'created_at': format_datetime_value(plan.get('created_at')),
        'published_at': format_datetime_value(plan.get('published_at')),
        'assignment': assignment,
    }

@app.route('/api/schedule/status')
def schedule_status():
    ensure_schedule_schema()
    conn = get_db_connection()
    cursor = conn.cursor()
    progress = get_schedule_progress(cursor)
    cursor.execute("SELECT id, algorithm, created_at FROM schedule_plans WHERE status = 'draft' ORDER BY id DESC LIMIT 1")
    latest_draft = cursor.fetchone()
    conn.close()
    return jsonify({
        'status': 'success',
        'can_calculate': progress['eligible_machines'] > 0,
        'can_publish': progress['received_tasks'] == 0,
        'latest_draft': latest_draft,
        **progress,
    })

@app.route('/api/schedule/calculate', methods=['POST'])
@app.route('/api/schedule/auto_assign', methods=['POST'])
def auto_assign_schedule():
    if not AUTO_SCHEDULE_LOCK.acquire(blocking=False):
        return jsonify({'status': 'error', 'message': '智能分配正在计算中，请勿重复提交'}), 409

    conn = None
    try:
        ensure_schedule_schema()
        conn = get_db_connection()
        cursor = conn.cursor()
        progress = get_schedule_progress(cursor)

        # 读取农机数据
        cursor.execute('''
            SELECT id, lng as x, lat as y, altitude as h, 
                   nom_vel, fuel, fueltask, work_efficiency as w
            FROM machines
            WHERE COALESCE(auto_schedulable, 1) = 1
              AND EXISTS (
                  SELECT 1 FROM users u
                  WHERE u.machine_id = machines.id AND u.role = 'worker' AND u.is_active = 1
              )
            ORDER BY id
        ''')
        machines = cursor.fetchall()
        
        # 读取农田数据
        cursor.execute('''
            SELECT id, lng as x, lat as y, altitude as h, area_sqm as S
            FROM fields 
            ORDER BY id
        ''')
        fields = cursor.fetchall()
        
        if not machines:
            conn.close()
            conn = None
            return jsonify({'status': 'error', 'message': '没有可参与调度的农机'}), 400
        if not fields:
            conn.close()
            conn = None
            return jsonify({'status': 'error', 'message': '没有可分配的农田数据'}), 400

        # ============================================================
        # ✅ 调用 Python GA 算法
        # ============================================================
        from ga_solver.solver import solve_schedule
        result = solve_schedule(machines, fields)

        # 转换为 routes 格式
        routes = []
        for agent in result.get('agents', []):
            machine_id = agent.get('machine_id')
            machine = next((m for m in machines if m['id'] == machine_id), None)
            if not machine:
                continue
            route = {
                'machine_id': machine_id,
                'machine_name': machine_id,
                'tail_lng': to_float(machine.get('x')),
                'tail_lat': to_float(machine.get('y')),
                'tail_altitude': to_float(machine.get('h')),
                'speed': max(0.5, to_float(machine.get('nom_vel'), 4.0)),
                'fuel': max(0, to_float(machine.get('fuel'), 0.06)),
                'fueltask': max(0, to_float(machine.get('fueltask'), 2.0)),
                'efficiency': max(1, to_float(machine.get('w'), 7000)),
                'predicted_hours': float(agent.get('total_time', 0)),
                'estimated_energy': 0,
                'tasks': []
            }
            for order, task_id in enumerate(agent.get('task_sequence', []), 1):
                farmland_id = f'F-{str(task_id).zfill(3)}'
                field = next((f for f in fields if f['id'] == farmland_id), None)
                if not field:
                    continue
                # 计算实际距离
                distance_km = geographic_distance_km(
                    route['tail_lng'], route['tail_lat'],
                    to_float(field.get('x')), to_float(field.get('y'))
                )
                area_sqm = max(0, to_float(field.get('S'), 500))
                uphill_m = max(0, to_float(field.get('h'), 0) - route['tail_altitude'])
                travel_hours = distance_km / route['speed']
                work_hours = area_sqm / route['efficiency']
                terrain_hours = uphill_m / 2000
                estimated_hours = travel_hours + work_hours + terrain_hours
                energy = distance_km * route['fuel'] + work_hours * route['fueltask']
                
                route['tasks'].append({
                    'farmland_id': farmland_id,
                    'distance_km': round(distance_km, 3),
                    'estimated_hours': round(estimated_hours, 3),
                    'estimated_energy': round(energy, 3),
                })
                route['predicted_hours'] += estimated_hours
                route['estimated_energy'] += energy
                route['tail_lng'] = to_float(field.get('x'))
                route['tail_lat'] = to_float(field.get('y'))
                route['tail_altitude'] = to_float(field.get('h'))
            routes.append(route)

        # 保存到 schedule_plans 表
        if not routes or not any(route['tasks'] for route in routes):
            conn.close()
            conn = None
            return jsonify({'status': 'error', 'message': 'Python GA 算法没有生成有效的调度方案'}), 400

        plan_id = save_schedule_plan(cursor, routes, 'python_ga')
        conn.commit()
        plan = get_schedule_plan_payload(cursor, plan_id)
        conn.close()
        conn = None
        
        return jsonify({
            'status': 'success',
            'message': f"已生成候选方案 #{plan_id}，尚未派发到手机端",
            'algorithm': 'Python 遗传算法',
            'excluded_machines': progress.get('excluded_machines', 0),
            'can_publish': progress.get('received_tasks', 0) == 0,
            'plan': plan,
        })
    except Exception as exc:
        if conn is not None:
            conn.close()
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(exc)}), 500
    finally:
        AUTO_SCHEDULE_LOCK.release()

@app.route('/api/schedule/plans/<int:plan_id>')
def get_schedule_plan(plan_id):
    ensure_schedule_schema()
    conn = get_db_connection()
    cursor = conn.cursor()
    plan = get_schedule_plan_payload(cursor, plan_id)
    conn.close()
    if not plan:
        return jsonify({'status': 'error', 'message': '未找到候选调度方案'}), 404
    return jsonify({'status': 'success', 'plan': plan})

@app.route('/api/schedule/plans/<int:plan_id>/publish', methods=['POST'])
def publish_schedule_plan(plan_id):
    if not AUTO_SCHEDULE_LOCK.acquire(blocking=False):
        return jsonify({'status': 'error', 'message': '调度方案正在处理，请勿重复提交'}), 409

    conn = None
    try:
        ensure_schedule_schema()
        conn = get_db_connection()
        cursor = conn.cursor()
        progress = get_schedule_progress(cursor)
        if progress['received_tasks'] > 0:
            conn.close()
            conn = None
            return jsonify({
                'status': 'blocked',
                'message': f"已有 {progress['received_tasks']} 个任务被工作人员接收；可以继续计算候选方案，但不能覆盖正在执行的任务",
                **progress,
            }), 409

        cursor.execute('SELECT id, status FROM schedule_plans WHERE id = %s', (plan_id,))
        plan_row = cursor.fetchone()
        if not plan_row:
            conn.close()
            conn = None
            return jsonify({'status': 'error', 'message': '未找到候选调度方案'}), 404
        if plan_row['status'] not in ('draft', 'published'):
            conn.close()
            conn = None
            return jsonify({'status': 'error', 'message': '该候选方案已失效，不能派发'}), 400

        cursor.execute('''
            SELECT COUNT(*) AS conflict_count
            FROM schedule_plan_items item
            INNER JOIN tasks active_task ON active_task.farmland_id = item.farmland_id
            INNER JOIN machines active_machine ON active_machine.id = active_task.machine_id
            WHERE item.plan_id = %s
              AND active_task.status IN ('待接收', '已接收')
              AND COALESCE(active_machine.auto_schedulable, 1) = 0
        ''', (plan_id,))
        conflict_count = int((cursor.fetchone() or {}).get('conflict_count') or 0)
        if conflict_count:
            conn.close()
            conn = None
            return jsonify({'status': 'error', 'message': f'候选方案中有 {conflict_count} 块地已被独立农机占用，请重新计算'}), 409

        cursor.execute('''
            SELECT machine_id, farmland_id, operation_type, task_order, estimated_hours
            FROM schedule_plan_items
            WHERE plan_id = %s
            ORDER BY machine_id, task_order, id
        ''', (plan_id,))
        items = cursor.fetchall()
        if not items:
            conn.close()
            conn = None
            return jsonify({'status': 'error', 'message': '候选方案中没有可派发任务'}), 400

        cursor.execute('''
            DELETE FROM tasks
            WHERE machine_id IN (
                SELECT id FROM machines WHERE COALESCE(auto_schedulable, 1) = 1
            )
        ''')
        created_at = beijing_now_text()
        machine_hours = {}
        for item in items:
            cursor.execute('''
                INSERT INTO tasks (
                    machine_id, farmland_id, operation_type, status,
                    task_order, created_at, schedule_plan_id
                ) VALUES (%s, %s, %s, '待接收', %s, %s, %s)
            ''', (
                item['machine_id'], item['farmland_id'], item['operation_type'],
                item['task_order'], created_at, plan_id,
            ))
            machine_hours[item['machine_id']] = (
                machine_hours.get(item['machine_id'], 0) + to_float(item.get('estimated_hours'))
            )

        for machine_id, estimated_hours in machine_hours.items():
            cursor.execute('''
                UPDATE machines
                SET work_time = %s, status = 'idle', last_seen = %s
                WHERE id = %s
            ''', (round(estimated_hours, 3), created_at, machine_id))

        cursor.execute("UPDATE schedule_plans SET status = 'superseded' WHERE status = 'published' AND id != %s", (plan_id,))
        cursor.execute('''
            UPDATE schedule_plans
            SET status = 'published', published_at = %s
            WHERE id = %s
        ''', (created_at, plan_id))
        conn.commit()
        plan = get_schedule_plan_payload(cursor, plan_id)
        conn.close()
        conn = None
        return jsonify({
            'status': 'success',
            'message': f"候选方案 #{plan_id} 已确认派发，共 {len(items)} 个任务",
            'plan': plan,
        })
    except Exception as exc:
        if conn is not None:
            conn.close()
        return jsonify({'status': 'error', 'message': str(exc)}), 500
    finally:
        AUTO_SCHEDULE_LOCK.release()

# ============================================================
#  调度管理 API（方案B：文件交换）
# ============================================================

@app.route('/api/export_for_matlab', methods=['POST'])
def export_for_matlab():
    """导出农机和农田数据供 Matlab 读取（JSON + CSV）"""
    try:
        ensure_schedule_schema()
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 读取农机
        cursor.execute('''
            SELECT id, lng as x, lat as y, altitude as h, 
                   nom_vel, fuel, fueltask, work_efficiency as w
            FROM machines
            WHERE status IN ('online', 'idle') AND COALESCE(alerts, 0) = 0
                  AND COALESCE(auto_schedulable, 1) = 1
                  AND EXISTS (
                      SELECT 1 FROM users u
                      WHERE u.machine_id = machines.id AND u.role = 'worker' AND u.is_active = 1
                  )
            ORDER BY id
        ''')
        machines = cursor.fetchall()
        
        # 读取农田
        cursor.execute('''
            SELECT id, lng as x, lat as y, altitude as h, area_sqm as S
            FROM fields 
            ORDER BY id
        ''')
        fields = cursor.fetchall()
        conn.close()

        # Matlab 成本函数按公里计算欧氏距离，因此先把经纬度投影为本地公里坐标。
        all_points = machines + fields
        reference_lng = sum(to_float(point.get('x')) for point in all_points) / max(1, len(all_points))
        reference_lat = sum(to_float(point.get('y')) for point in all_points) / max(1, len(all_points))
        lng_km = 111.32 * math.cos(math.radians(reference_lat))
        for point in all_points:
            point['x'] = round((to_float(point.get('x')) - reference_lng) * lng_km, 6)
            point['y'] = round((to_float(point.get('y')) - reference_lat) * 111.32, 6)
        
        # ===== 保存 JSON（用于其他用途） =====
        data = {
            'machines': machines,
            'fields': fields,
            'coordinate_system': 'local_km',
            'reference_lng': reference_lng,
            'reference_lat': reference_lat,
            'export_time': datetime.now().isoformat()
        }
        filepath = os.path.join(SCHEDULER_DIR, 'input_data.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        # ===== 保存 CSV（供 Matlab 读取） =====
        # machines.csv
        with open(os.path.join(SCHEDULER_DIR, 'machines.csv'), 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'x', 'y', 'h'])
            for m in machines:
                writer.writerow([m['id'], m['x'], m['y'], m['h']])
        
        # fields.csv
        with open(os.path.join(SCHEDULER_DIR, 'fields.csv'), 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'x', 'y', 'h', 'S'])
            for fld in fields:
                writer.writerow([fld['id'], fld['x'], fld['y'], fld['h'], fld['S']])
        
        return jsonify({
            'status': 'success',
            'message': f'已导出 {len(machines)} 台农机和 {len(fields)} 块农田',
            'machines_count': len(machines),
            'fields_count': len(fields)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/load_schedule_result', methods=['POST'])
def load_schedule_result():
    """加载 Matlab 结果为候选方案，不直接覆盖手机端正式任务。"""
    try:
        ensure_schedule_schema()
        filepath = os.path.join(SCHEDULER_DIR, 'result.json')
        
        if not os.path.exists(filepath):
            return jsonify({
                'status': 'error',
                'message': '未找到 result.json，请先在 Matlab 中运行调度算法'
            }), 404
        
        # 读取结果
        with open(filepath, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        if result.get('status') == 'error':
            return jsonify({
                'status': 'error',
                'message': result.get('message', 'Matlab 计算出错')
            }), 500
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, name, lng, lat, altitude, nom_vel, fuel, fueltask, work_efficiency
            FROM machines
            WHERE COALESCE(auto_schedulable, 1) = 1
        ''')
        machine_map = {row['id']: row for row in cursor.fetchall()}
        cursor.execute('SELECT id, lng, lat, altitude, area_sqm FROM fields ORDER BY id')
        field_map = {row['id']: row for row in cursor.fetchall()}

        routes = []
        for agent in result.get('agents', []):
            machine_id = agent.get('machine_id')
            machine = machine_map.get(machine_id)
            if not machine:
                continue
            route = {
                'machine_id': machine_id,
                'machine_name': machine.get('name') or machine_id,
                'tail_lng': to_float(machine.get('lng')),
                'tail_lat': to_float(machine.get('lat')),
                'tail_altitude': to_float(machine.get('altitude')),
                'speed': max(0.5, to_float(machine.get('nom_vel'), 4)),
                'fuel': max(0, to_float(machine.get('fuel'), 0.06)),
                'fueltask': max(0, to_float(machine.get('fueltask'), 2)),
                'efficiency': max(1, to_float(machine.get('work_efficiency'), 7000)),
                'predicted_hours': 0.0,
                'estimated_energy': 0.0,
                'tasks': [],
            }
            task_sequence = agent.get('task_sequence', [])
            for task_id in task_sequence:
                farmland_id = str(task_id)
                if not farmland_id.startswith('F-'):
                    farmland_id = f"F-{int(task_id):03d}"
                field = field_map.get(farmland_id)
                if not field:
                    continue
                distance_km = geographic_distance_km(
                    route['tail_lng'], route['tail_lat'],
                    to_float(field.get('lng')), to_float(field.get('lat')),
                )
                area_sqm = max(0, to_float(field.get('area_sqm')))
                uphill_m = max(0, to_float(field.get('altitude')) - route['tail_altitude'])
                travel_hours = distance_km / route['speed']
                work_hours = area_sqm / route['efficiency']
                terrain_hours = uphill_m / 2000
                estimated_hours = travel_hours + work_hours + terrain_hours
                energy = distance_km * route['fuel'] + work_hours * route['fueltask']
                route['tasks'].append({
                    'farmland_id': farmland_id,
                    'distance_km': round(distance_km, 3),
                    'estimated_hours': round(estimated_hours, 3),
                    'estimated_energy': round(energy, 3),
                })
                route['predicted_hours'] += estimated_hours
                route['estimated_energy'] += energy
                route['tail_lng'] = to_float(field.get('lng'))
                route['tail_lat'] = to_float(field.get('lat'))
                route['tail_altitude'] = to_float(field.get('altitude'))
            routes.append(route)

        if not routes or not any(route['tasks'] for route in routes):
            conn.close()
            return jsonify({'status': 'error', 'message': 'Matlab 结果中没有有效的农机任务'}), 400

        plan_id = save_schedule_plan(cursor, routes, 'matlab_ga')
        conn.commit()
        plan = get_schedule_plan_payload(cursor, plan_id)
        conn.close()
        
        # 备份结果文件
        backup_path = os.path.join(SCHEDULER_DIR, f'result_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        os.rename(filepath, backup_path)
        
        return jsonify({
            'status': 'success',
            'message': f"Matlab 候选方案 #{plan_id} 已导入，尚未派发到手机端",
            'total_cost': result.get('total_cost', 0),
            'agents_count': len(result.get('agents', [])),
            'plan': plan,
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============================================================
#  任务分配结果 API（用于前端展示）
# ============================================================

@app.route('/api/task_assignment')
def get_task_assignment():
    """获取格式化后的任务分配结果"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取所有任务，按农机和顺序排序
        cursor.execute('''
            SELECT machine_id, farmland_id, operation_type, status, task_order
            FROM tasks 
            ORDER BY machine_id, task_order, id
        ''')
        tasks = cursor.fetchall()
        
        # 获取农机信息
        cursor.execute('SELECT id, name, lng, lat FROM machines ORDER BY id')
        machines = cursor.fetchall()
        machine_map = {m['id']: {'name': m['name'], 'lng': m['lng'], 'lat': m['lat']} for m in machines}
        
        # 获取农田信息
        cursor.execute('SELECT id, name, lng, lat FROM fields ORDER BY id')
        fields = cursor.fetchall()
        field_map = {f['id']: {'name': f['name'], 'lng': f['lng'], 'lat': f['lat']} for f in fields}
        conn.close()
        
        # 按农机分组
        assignment = []
        machine_ids = set([t['machine_id'] for t in tasks])
        
        for machine_id in sorted(machine_ids):
            machine_tasks = [t for t in tasks if t['machine_id'] == machine_id]
            machine_tasks.sort(key=lambda x: x.get('task_order', 0))
            
            assignment.append({
                'machine_id': machine_id,
                'machine_name': machine_map.get(machine_id, {}).get('name', machine_id),
                'machine_lng': float(machine_map.get(machine_id, {}).get('lng', 0)),
                'machine_lat': float(machine_map.get(machine_id, {}).get('lat', 0)),
                'task_count': len(machine_tasks),
                'tasks': [
                    {
                        'farmland_id': t['farmland_id'],
                        'farmland_name': field_map.get(t['farmland_id'], {}).get('name', t['farmland_id']),
                        'farmland_lng': float(field_map.get(t['farmland_id'], {}).get('lng', 0)),
                        'farmland_lat': float(field_map.get(t['farmland_id'], {}).get('lat', 0)),
                        'operation_type': t['operation_type'],
                        'status': t['status'],
                        'task_order': t.get('task_order', i+1)
                    }
                    for i, t in enumerate(machine_tasks)
                ]
            })
        
        return jsonify({
            'status': 'success',
            'total_machines': len(assignment),
            'total_tasks': len(tasks),
            'assignment': assignment
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
    # ============================================================
#  一键调度 API（使用 Python GA 算法）
# ============================================================

from ga_solver.solver import solve_schedule

@app.route('/api/auto_schedule', methods=['POST'])
def auto_schedule():
    """一键自动调度：读取数据 → 运行 Python GA → 加载结果"""
    try:
        # 1. 从数据库读取农机和农田数据
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, lng as x, lat as y, altitude as h, 
                   nom_vel, fuel, fueltask, work_efficiency as w
            FROM machines 
            ORDER BY id
        ''')
        machines = cursor.fetchall()
        
        cursor.execute('''
            SELECT id, lng as x, lat as y, altitude as h, area_sqm as S
            FROM fields 
            ORDER BY id
        ''')
        fields = cursor.fetchall()
        conn.close()
        
        if not machines:
            return jsonify({'status': 'error', 'message': '没有农机数据'}), 400
        if not fields:
            return jsonify({'status': 'error', 'message': '没有农田数据'}), 400
        
        # 2. 运行 Python GA 算法
        print(f"开始调度: {len(machines)} 台农机, {len(fields)} 块农田")
        result = solve_schedule(machines, fields)
        
         # ===== 新增：保存到历史文件夹 =====
        history_dir = os.path.join(SCHEDULER_DIR, 'history')
        os.makedirs(history_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        history_file = os.path.join(history_dir, f'{timestamp}.json')
        
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # 同时保存为当前最新的 result.json
        with open(os.path.join(SCHEDULER_DIR, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # 3. 保存 result.json
        with open(os.path.join(SCHEDULER_DIR, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # 4. 加载结果到数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM tasks')
        
        inserted_count = 0
        for agent in result.get('agents', []):
            machine_id = agent.get('machine_id')
            task_sequence = agent.get('task_sequence', [])
            total_time = agent.get('total_time', 0)
            
            for order, task_id in enumerate(task_sequence, 1):
                farmland_id = f'F-{str(task_id).zfill(3)}'
                cursor.execute('''
                    INSERT INTO tasks (machine_id, farmland_id, operation_type, status, task_order)
                    VALUES (%s, %s, %s, "待接收", %s)
                ''', (machine_id, farmland_id, '智能调度', order))
                inserted_count += 1
            
            # 更新工作时间
            cursor.execute('''
                UPDATE machines SET work_time = %s WHERE id = %s
            ''', (total_time, machine_id))
        
        conn.commit()
        conn.close()
        
        # 5. 备份 result.json
        backup_path = os.path.join(SCHEDULER_DIR, f'result_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        os.rename(os.path.join(SCHEDULER_DIR, 'result.json'), backup_path)
        
        return jsonify({
            'status': 'success',
            'message': f'调度完成！已分配 {len(result.get("agents", []))} 台农机，共 {inserted_count} 个任务',
            'total_cost': result.get('total_cost', 0),
            'agents_count': len(result.get('agents', []))
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/api/load_history', methods=['POST'])
def load_history():
    """加载历史调度结果"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'status': 'error', 'message': '缺少文件名'}), 400
        
        history_dir = os.path.join(SCHEDULER_DIR, 'history')
        filepath = os.path.join(history_dir, filename)
        
        if not os.path.exists(filepath):
            return jsonify({'status': 'error', 'message': '历史文件不存在'}), 404
        
        # 读取历史结果
        with open(filepath, 'r', encoding='utf-8') as f:
            result = json.load(f)
        
        # 加载到数据库
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM tasks')
        
        inserted_count = 0
        for agent in result.get('agents', []):
            machine_id = agent.get('machine_id')
            task_sequence = agent.get('task_sequence', [])
            total_time = agent.get('total_time', 0)
            
            for order, task_id in enumerate(task_sequence, 1):
                farmland_id = f'F-{str(task_id).zfill(3)}'
                cursor.execute('''
                    INSERT INTO tasks (machine_id, farmland_id, operation_type, status, task_order)
                    VALUES (%s, %s, %s, "待接收", %s)
                ''', (machine_id, farmland_id, '历史调度', order))
                inserted_count += 1
            
            cursor.execute('''
                UPDATE machines SET work_time = %s WHERE id = %s
            ''', (total_time, machine_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'message': f'已加载历史结果，共 {inserted_count} 个任务',
            'total_cost': result.get('total_cost', 0)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/history_list', methods=['GET'])
def get_history_list():
    """获取所有历史结果文件列表"""
    try:
        history_dir = os.path.join(SCHEDULER_DIR, 'history')
        os.makedirs(history_dir, exist_ok=True)
        
        files = []
        for f in os.listdir(history_dir):
            if f.endswith('.json'):
                filepath = os.path.join(history_dir, f)
                # 读取文件中的部分信息用于显示
                with open(filepath, 'r', encoding='utf-8') as fp:
                    try:
                        data = json.load(fp)
                        total_cost = data.get('total_cost', 0)
                        agent_count = len(data.get('agents', []))
                        task_count = sum(len(a.get('task_sequence', [])) for a in data.get('agents', []))
                    except:
                        total_cost = 0
                        agent_count = 0
                        task_count = 0
                
                stat = os.stat(filepath)
                files.append({
                    'filename': f,
                    'timestamp': f.replace('.json', '').replace('_', ' '),
                    'size_kb': round(stat.st_size / 1024, 1),
                    'total_cost': round(total_cost, 4),
                    'agent_count': agent_count,
                    'task_count': task_count
                })
        
        # 按时间倒序排列（最新的在前）
        files.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({
            'status': 'success',
            'files': files
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    from gpswv_location import start_gpswv_location_poller
    from jt808_server import start_jt808_server
    gpswv_poller = start_gpswv_location_poller()
    jt808_server = start_jt808_server()
    try:
        app.run(
            debug=False,
            use_reloader=False,
            host=os.environ.get('FARM_SYSTEM_HOST', '127.0.0.1'),
            port=int(os.environ.get('FARM_SYSTEM_PORT', '5000')),
        )
    finally:
        gpswv_poller.stop()
        jt808_server.stop()
