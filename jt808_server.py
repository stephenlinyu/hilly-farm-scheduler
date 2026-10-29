"""Dependency-free JT/T 808 TCP receiver for the independent real tractor."""

import atexit
from datetime import datetime, timezone, timedelta
import os
import socket
import sqlite3
import threading

from coordinate_converter import wgs84_to_gcj02
from jt808_codec import Jt808Codec


BASE_DIR = os.path.dirname(__file__)
BEIJING_TZ = timezone(timedelta(hours=8))
DEFAULT_DATABASE = os.path.join(BASE_DIR, "farm_management.sqlite")
DEFAULT_BINDINGS = "31110789281:R-001"


def env_enabled(name, default="1"):
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def parse_bindings(binding_text):
    bindings = {}
    for item in (binding_text or "").split(","):
        terminal_id, separator, machine_id = item.strip().partition(":")
        terminal_id = "".join(character for character in terminal_id if character.isdigit())
        machine_id = machine_id.strip()
        if separator and terminal_id and machine_id:
            bindings[terminal_id] = machine_id
    return bindings


def ensure_jt808_schema(database_path):
    conn = sqlite3.connect(database_path, timeout=10)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout = 10000")
        machine_columns = {row[1] for row in cursor.execute("PRAGMA table_info(machines)")}
        if "device_no" not in machine_columns:
            cursor.execute("ALTER TABLE machines ADD COLUMN device_no TEXT DEFAULT NULL")
        if "direction" not in machine_columns:
            cursor.execute("ALTER TABLE machines ADD COLUMN direction INTEGER DEFAULT 0")
        if "auto_schedulable" not in machine_columns:
            cursor.execute("ALTER TABLE machines ADD COLUMN auto_schedulable INTEGER NOT NULL DEFAULT 1")
        if "position_source" not in machine_columns:
            cursor.execute("ALTER TABLE machines ADD COLUMN position_source TEXT NOT NULL DEFAULT 'demo'")
        cursor.execute("""
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
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_machine_positions_machine_time
            ON machine_positions(machine_id, id DESC)
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO machines (
                id, name, type, org, operator, status, lng, lat, altitude,
                speed, area, `signal`, last_seen, alerts, work_time,
                auto_schedulable, position_source, device_no, direction
            ) VALUES (
                'R-001', '北斗实机 R-001', 'tractor', '真实农机接入', '实机操作员',
                'offline', 106.235, 29.785, 0, 0, 0, 0, '2000-01-01 00:00:00',
                0, 0, 0, 'jt808', '31110789281', 0
            )
        """)
        cursor.execute("""
            UPDATE machines
            SET auto_schedulable = 0, position_source = 'jt808', device_no = '31110789281'
            WHERE id = 'R-001'
        """)
        conn.commit()
    finally:
        conn.close()


def parse_location(codec, message):
    body = message.body
    if len(body) < 28:
        raise ValueError("0x0200 body is too short")

    alarm = codec.read_dword(body, 0)
    terminal_status = codec.read_dword(body, 4)
    latitude = codec.read_dword(body, 8) / 1_000_000.0
    longitude = codec.read_dword(body, 12) / 1_000_000.0
    altitude = codec.read_word(body, 16)
    speed = codec.read_word(body, 18) / 10.0
    direction = codec.read_word(body, 20)
    source_time = codec.decode_bcd_time(body, 22)

    if terminal_status & (1 << 2):
        latitude = -latitude
    if terminal_status & (1 << 3):
        longitude = -longitude
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("location coordinate is outside the valid range")

    signal = 0
    offset = 28
    while offset + 2 <= len(body):
        item_id = body[offset]
        item_length = body[offset + 1]
        item_start = offset + 2
        item_end = item_start + item_length
        if item_end > len(body):
            break
        if item_id == 0x30 and item_length >= 1:
            signal = body[item_start]
        offset = item_end

    lng_gcj, lat_gcj = wgs84_to_gcj02(longitude, latitude)
    return {
        "lng": lng_gcj,
        "lat": lat_gcj,
        "altitude": altitude,
        "speed": speed,
        "direction": direction,
        "alarm": alarm,
        "terminal_status": terminal_status,
        "signal": signal,
        "source_time": source_time,
        "positioned": bool(terminal_status & (1 << 1)),
    }


class Jt808TcpServer:
    def __init__(self):
        self.enabled = env_enabled("JT808_ENABLED", "1")
        self.host = os.environ.get("JT808_HOST", "0.0.0.0")
        self.port = int(os.environ.get("JT808_PORT", "8088"))
        self.auth_code = os.environ.get("JT808_AUTH_CODE", "123456")
        self.database_path = os.environ.get("FARM_SQLITE_DB", DEFAULT_DATABASE)
        self.bindings = parse_bindings(os.environ.get("JT808_DEVICE_BINDINGS", DEFAULT_BINDINGS))
        self.codec = Jt808Codec()
        self._running = threading.Event()
        self._socket = None
        self._accept_thread = None
        self._client_threads = set()
        self._client_lock = threading.Lock()

    def start(self):
        if not self.enabled:
            print("JT808 TCP 服务已关闭（JT808_ENABLED=0）")
            return False
        if self._accept_thread and self._accept_thread.is_alive():
            return True
        ensure_jt808_schema(self.database_path)
        self._running.set()
        self._accept_thread = threading.Thread(target=self._accept_loop, name="jt808-accept", daemon=True)
        self._accept_thread.start()
        return True

    def stop(self):
        self._running.clear()
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _accept_loop(self):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen(20)
            server_socket.settimeout(1.0)
            self._socket = server_socket
            print(f"JT808 TCP 服务正在监听 {self.host}:{self.port}，绑定终端 {sorted(self.bindings)}")
            while self._running.is_set():
                try:
                    client, address = server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client, address),
                    name=f"jt808-client-{address[0]}:{address[1]}",
                    daemon=True,
                )
                with self._client_lock:
                    self._client_threads.add(thread)
                thread.start()
        except OSError as exc:
            print(f"JT808 TCP 服务启动失败：{exc}")
        finally:
            self._running.clear()

    def _handle_client(self, client, address):
        authenticated = False
        frame = bytearray()
        in_frame = False
        client.settimeout(120)
        try:
            with client:
                while self._running.is_set():
                    try:
                        chunk = client.recv(4096)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    for value in chunk:
                        if value == 0x7E:
                            if in_frame and len(frame) > 1:
                                frame.append(value)
                                response, authenticated, keep_connected = self._handle_frame(bytes(frame), authenticated)
                                if response:
                                    client.sendall(response)
                                frame = bytearray((0x7E,))
                                if not keep_connected:
                                    return
                            else:
                                frame = bytearray((0x7E,))
                                in_frame = True
                        elif in_frame:
                            frame.append(value)
        except OSError as exc:
            print(f"JT808 客户端 {address[0]}:{address[1]} 已断开：{exc}")
        finally:
            with self._client_lock:
                self._client_threads.discard(threading.current_thread())

    def _handle_frame(self, frame, authenticated):
        try:
            message = self.codec.decode(frame)
        except ValueError as exc:
            print(f"JT808 报文解析失败：{exc}")
            return None, authenticated, True

        machine_id = self.bindings.get(message.terminal_id)
        if not machine_id:
            print(f"拒绝未知 JT808 终端：{message.terminal_id}")
            if message.message_id == 0x0100:
                response = self.codec.encode_register_response(message, result=1, auth_code="")
            else:
                response = self.codec.encode_general_response(message, result=1)
            return response, False, False

        if message.message_id == 0x0100:
            return self.codec.encode_register_response(message, 0, self.auth_code), False, True

        if message.message_id == 0x0102:
            supplied_auth = message.body.decode("ascii", errors="ignore").strip("\x00")
            success = supplied_auth == self.auth_code
            if not success:
                print(f"拒绝 JT808 终端 {message.terminal_id}：鉴权码错误")
            return self.codec.encode_general_response(message, 0 if success else 1), success, success

        if message.message_id == 0x0003:
            return self.codec.encode_general_response(message, 0), authenticated, False

        if message.message_id == 0x0200:
            if not authenticated:
                print(f"拒绝 JT808 终端 {message.terminal_id} 的未鉴权定位报文")
                return self.codec.encode_general_response(message, 1), False, False
            try:
                position = parse_location(self.codec, message)
                self._record_position(machine_id, message.terminal_id, position)
            except (ValueError, sqlite3.Error) as exc:
                print(f"JT808 定位写入失败：{exc}")
                return self.codec.encode_general_response(message, 1), authenticated, True
            return self.codec.encode_general_response(message, 0), authenticated, True

        return self.codec.encode_general_response(message, 0), authenticated, True

    def _record_position(self, machine_id, terminal_id, position):
        received_at = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(self.database_path, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA busy_timeout = 10000")
            cursor.execute(
                "SELECT id FROM machines WHERE id = ? AND position_source = 'jt808' AND device_no = ?",
                (machine_id, terminal_id),
            )
            if not cursor.fetchone():
                raise ValueError(f"terminal {terminal_id} is not bound to {machine_id} in the database")

            signal = position["signal"]
            if position["positioned"]:
                cursor.execute("""
                    INSERT INTO machine_positions (
                        machine_id, device_no, lng, lat, altitude, speed, direction,
                        alarm, terminal_status, signal, source_time, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    machine_id, terminal_id, position["lng"], position["lat"],
                    position["altitude"], position["speed"], position["direction"],
                    position["alarm"], position["terminal_status"], signal,
                    position["source_time"], received_at,
                ))
                cursor.execute("""
                    UPDATE machines
                    SET lng = ?, lat = ?, altitude = ?, speed = ?, direction = ?,
                        `signal` = CASE WHEN ? > 0 THEN ? ELSE `signal` END,
                        status = ?, last_seen = ?
                    WHERE id = ?
                """, (
                    position["lng"], position["lat"], position["altitude"], position["speed"],
                    position["direction"], signal, signal,
                    "working" if position["speed"] > 0.5 else "idle", received_at, machine_id,
                ))
            else:
                cursor.execute("""
                    UPDATE machines
                    SET `signal` = CASE WHEN ? > 0 THEN ? ELSE `signal` END,
                        last_seen = ?
                    WHERE id = ?
                """, (signal, signal, received_at, machine_id))
            conn.commit()
        finally:
            conn.close()


_SERVER = None
_SERVER_LOCK = threading.Lock()


def start_jt808_server():
    global _SERVER
    with _SERVER_LOCK:
        if _SERVER is None:
            _SERVER = Jt808TcpServer()
            _SERVER.start()
            atexit.register(_SERVER.stop)
        return _SERVER
