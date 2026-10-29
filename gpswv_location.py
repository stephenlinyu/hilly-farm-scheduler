"""Synchronize real device positions from the GPSWV/FIGPS open API."""

from __future__ import annotations

import atexit
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import ssl
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import truststore
except ImportError:
    truststore = None


BASE_DIR = Path(__file__).resolve().parent
BEIJING_TZ = timezone(timedelta(hours=8))
DEFAULT_DATABASE = BASE_DIR / "farm_management.sqlite"
DEFAULT_CONFIG_FILE = BASE_DIR / "gpswv_config.json"
DEFAULT_SERVICE_URL = "https://open.figps.com/api"
DEFAULT_IMEI = "862000000000001"
DEFAULT_MACHINE_ID = "R-001"
MAX_RESPONSE_BYTES = int(os.environ.get("GPSWV_MAX_RESPONSE_BYTES", str(16 * 1024 * 1024)))


class GpsWvApiError(RuntimeError):
    pass


def env_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_device_id(value):
    return "".join(character for character in str(value or "") if character.isdigit())


def load_json_config(path):
    try:
        with Path(path).open("r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise GpsWvApiError(f"GPSWV 配置文件读取失败：{exc}") from exc
    if not isinstance(value, dict):
        raise GpsWvApiError("GPSWV 配置文件必须是 JSON 对象")
    return value


def config_value(config, env_name, *keys, default=None):
    environment_value = os.environ.get(env_name)
    if environment_value is not None:
        return environment_value
    for key in keys:
        if key in config:
            return config[key]
    return default


def _item_value(config, env_name, *keys, default=None, use_environment=False):
    if use_environment:
        return config_value(config, env_name, *keys, default=default)
    for key in keys:
        if key in config:
            return config[key]
    return default


def _build_settings(config, config_path, *, use_environment=False, inherited=None, primary=False):
    inherited = inherited or {}
    settings = {
        "config_path": config_path,
        "enabled": env_bool(
            _item_value(
                config, "GPSWV_ENABLED", "enabled", default=False,
                use_environment=use_environment,
            )
        ),
        "service_url": str(_item_value(
            config, "GPSWV_SERVICE_URL", "serviceUrl", "service_url",
            default=inherited.get("service_url", DEFAULT_SERVICE_URL),
            use_environment=use_environment,
        )).strip().rstrip("/"),
        "appid": str(_item_value(
            config, "GPSWV_APPID", "appid", default="",
            use_environment=use_environment,
        )).strip(),
        "key": str(_item_value(
            config, "GPSWV_KEY", "key", default="",
            use_environment=use_environment,
        )),
        "imei": normalize_device_id(_item_value(
            config, "GPSWV_IMEI", "imei", default=DEFAULT_IMEI if primary else "",
            use_environment=use_environment,
        )),
        "machine_id": str(_item_value(
            config, "GPSWV_MACHINE_ID", "machineId", "machine_id",
            default=DEFAULT_MACHINE_ID if primary else "",
            use_environment=use_environment,
        )).strip(),
        "poll_interval": max(5, safe_int(_item_value(
            config, "GPSWV_POLL_INTERVAL_SECONDS", "pollIntervalSeconds", "poll_interval_seconds",
            default=inherited.get("poll_interval", 10),
            use_environment=use_environment,
        ), 10)),
        "coord_type": str(_item_value(
            config, "GPSWV_COORD_TYPE", "coordType", "coord_type",
            default=inherited.get("coord_type", "gcj02"),
            use_environment=use_environment,
        )).strip().lower(),
        "request_timeout": max(5, safe_int(_item_value(
            config, "GPSWV_REQUEST_TIMEOUT_SECONDS", "requestTimeoutSeconds",
            "request_timeout_seconds", default=inherited.get("request_timeout", 20),
            use_environment=use_environment,
        ), 20)),
        "online_timeout": max(60, safe_int(_item_value(
            config, "GPSWV_ONLINE_TIMEOUT_SECONDS", "onlineTimeoutSeconds",
            "online_timeout_seconds", default=inherited.get("online_timeout", 180),
            use_environment=use_environment,
        ), 180)),
        "store_history": env_bool(_item_value(
            config, "GPSWV_STORE_HISTORY", "storeHistory", "store_history",
            default=inherited.get("store_history", False),
            use_environment=use_environment,
        )),
        "database_path": Path(os.environ.get(
            "FARM_SQLITE_DB", inherited.get("database_path", DEFAULT_DATABASE)
        )),
    }
    if settings["coord_type"] not in {"wgs84", "gcj02", "bd09ll"}:
        raise GpsWvApiError("GPSWV coordType 只能是 wgs84、gcj02 或 bd09ll")
    if not settings["service_url"].startswith("https://"):
        raise GpsWvApiError("GPSWV 服务地址必须使用 HTTPS")
    return settings


def load_settings():
    """读取兼容旧版单设备配置的主设备设置。"""
    config_path = Path(os.environ.get("GPSWV_CONFIG_FILE", DEFAULT_CONFIG_FILE))
    config = load_json_config(config_path)
    return _build_settings(
        config, config_path, use_environment=True, primary=True,
    )


def load_settings_list():
    """读取主设备和 additionalDevices 中的附加真实定位设备。"""
    config_path = Path(os.environ.get("GPSWV_CONFIG_FILE", DEFAULT_CONFIG_FILE))
    config = load_json_config(config_path)
    primary_settings = _build_settings(
        config, config_path, use_environment=True, primary=True,
    )
    settings_list = [primary_settings]
    additional_devices = config.get("additionalDevices", config.get("additional_devices", []))
    if additional_devices is None:
        additional_devices = []
    if not isinstance(additional_devices, list):
        raise GpsWvApiError("GPSWV additionalDevices 必须是 JSON 数组")

    inherited = {
        "service_url": primary_settings["service_url"],
        "poll_interval": primary_settings["poll_interval"],
        "coord_type": primary_settings["coord_type"],
        "request_timeout": primary_settings["request_timeout"],
        "online_timeout": primary_settings["online_timeout"],
        "store_history": primary_settings["store_history"],
        "database_path": primary_settings["database_path"],
    }
    for index, device_config in enumerate(additional_devices, 1):
        if not isinstance(device_config, dict):
            raise GpsWvApiError(f"GPSWV additionalDevices 第 {index} 项必须是 JSON 对象")
        settings_list.append(_build_settings(
            device_config, config_path, inherited=inherited,
        ))

    machine_ids = set()
    device_ids = set()
    for settings in settings_list:
        if not settings["enabled"]:
            continue
        machine_id = settings["machine_id"]
        device_id = settings["imei"]
        if machine_id and machine_id in machine_ids:
            raise GpsWvApiError(f"GPSWV 农机编号重复：{machine_id}")
        if device_id and device_id in device_ids:
            raise GpsWvApiError(f"GPSWV IMEI 重复：{device_id}")
        if machine_id:
            machine_ids.add(machine_id)
        if device_id:
            device_ids.add(device_id)
    return settings_list


def build_signature(key, timestamp):
    first_md5 = hashlib.md5(str(key).encode("utf-8")).hexdigest()
    return hashlib.md5(f"{first_md5}{int(timestamp)}".encode("utf-8")).hexdigest()


def epoch_to_beijing_text(value):
    timestamp = safe_float(value, None)
    if timestamp is None or timestamp <= 0:
        return None
    if timestamp > 10_000_000_000:
        timestamp /= 1000.0
    try:
        return datetime.fromtimestamp(timestamp, BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return None


def beijing_now_text():
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


def create_ssl_context():
    if truststore is not None:
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return ssl.create_default_context()


def map_vendor_status(status_text, speed, source_timestamp, online_timeout):
    normalized = str(status_text or "").strip().lower()
    now_timestamp = time.time()
    if source_timestamp and now_timestamp - source_timestamp > online_timeout:
        return "offline"
    if any(word in normalized for word in ("离线", "休眠", "未启用", "offline")):
        return "offline"
    if safe_float(speed, 0) > 0.5 or any(word in normalized for word in ("行驶", "运动", "working")):
        return "working"
    return "idle"


class GpsWvClient:
    def __init__(self, settings):
        self.settings = settings
        self._token = None
        self._token_expires_at = 0
        self._token_lock = threading.Lock()
        self._ssl_context = create_ssl_context()
        self._use_curl_transport = False

    @staticmethod
    def _is_certificate_error(exc):
        """Return True only for TLS certificate-chain compatibility errors."""
        message = str(exc).lower()
        return any(marker in message for marker in (
            "certificate_verify_failed",
            "certificate has expired",
            "certificate is not yet valid",
            "certificate chain",
            "证书不在有效期",
            "证书链",
        ))

    def _request_json_with_curl(self, method, url, headers, body):
        """Use Windows' HTTPS stack fallback without disabling TLS checks."""
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise GpsWvApiError("GPSWV Python 证书校验失败，且系统中未找到 curl.exe")

        marker = b"\n__FARM_SYSTEM_HTTP_STATUS__:"
        command = [
            curl,
            "--silent",
            "--show-error",
            "--max-time",
            str(self.settings["request_timeout"]),
            "--proto",
            "=https",
            "--request",
            method,
            "--write-out",
            "\n__FARM_SYSTEM_HTTP_STATUS__:%{http_code}",
            "--url",
            url,
        ]
        for name, value in headers.items():
            command.extend(("--header", f"{name}: {value}"))
        if body is not None:
            command.extend(("--data-binary", "@-"))

        try:
            completed = subprocess.run(
                command,
                input=body,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.settings["request_timeout"] + 5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise GpsWvApiError(f"GPSWV curl 请求失败：{exc}") from exc

        output = completed.stdout
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise GpsWvApiError(f"GPSWV curl 请求失败：{detail or completed.returncode}")
        if marker not in output:
            raise GpsWvApiError("GPSWV curl 返回格式无效")
        raw, status_bytes = output.rsplit(marker, 1)
        try:
            status = int(status_bytes.strip())
        except ValueError as exc:
            raise GpsWvApiError("GPSWV curl 未返回有效 HTTP 状态码") from exc
        if status >= 400:
            raise GpsWvApiError(f"GPSWV HTTP 错误：{status}")
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GpsWvApiError("GPSWV 返回数据过大")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GpsWvApiError("GPSWV 返回的不是有效 JSON") from exc
        if not isinstance(result, dict):
            raise GpsWvApiError("GPSWV 返回格式无效")
        return result

    def _request_json(self, method, path, query=None, payload=None):
        url = f"{self.settings['service_url']}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        body = None
        headers = {
            "Accept": "application/json",
            "User-Agent": "FarmSystem-GPSWV/1.0",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._use_curl_transport:
            return self._request_json_with_curl(method, url, headers, body)
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(
                request,
                timeout=self.settings["request_timeout"],
                context=self._ssl_context,
            ) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise GpsWvApiError(f"GPSWV HTTP 错误：{exc.code}") from exc
        except (OSError, URLError) as exc:
            if self._is_certificate_error(exc):
                self._use_curl_transport = True
                print("GPSWV 已切换到 Windows 安全 HTTPS 通道（TLS 校验保持启用）")
                return self._request_json_with_curl(method, url, headers, body)
            raise GpsWvApiError(f"GPSWV 网络连接失败：{exc}") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GpsWvApiError("GPSWV 返回数据过大")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GpsWvApiError("GPSWV 返回的不是有效 JSON") from exc
        if not isinstance(result, dict):
            raise GpsWvApiError("GPSWV 返回格式无效")
        return result

    def clear_token(self):
        with self._token_lock:
            self._token = None
            self._token_expires_at = 0

    def get_access_token(self):
        with self._token_lock:
            if self._token and time.time() < self._token_expires_at:
                return self._token
            timestamp = int(time.time())
            result = self._request_json("POST", "/auth", payload={
                "appid": self.settings["appid"],
                "time": timestamp,
                "signature": build_signature(self.settings["key"], timestamp),
            })
            auth_data = result.get("data") if isinstance(result.get("data"), dict) else {}
            access_token = result.get("accessToken") or auth_data.get("accessToken")
            if safe_int(result.get("code"), -1) != 0 or not access_token:
                raise GpsWvApiError(
                    f"GPSWV 认证失败：{result.get('result') or result.get('message') or result.get('msg') or result.get('code') or '未知错误'}"
                )
            expires_value = result.get("expiresIn", auth_data.get("expiresIn", 7_200_000))
            expires_seconds = max(900, safe_int(expires_value, 7_200_000) // 1000 - 600)
            self._token = str(access_token)
            self._token_expires_at = time.time() + min(expires_seconds, 5_400)
            return self._token

    def get_device_status(self):
        for attempt in range(2):
            token = self.get_access_token()
            result = self._request_json("GET", "/device/status", query={
                "accessToken": token,
                "imei": self.settings["imei"],
                "coordType": self.settings["coord_type"],
            })
            if safe_int(result.get("code"), -1) == 0:
                data = result.get("data") or []
                if isinstance(data, dict):
                    nested_items = data.get("items") or data.get("list") or data.get("records")
                    data = nested_items if isinstance(nested_items, list) else [data]
                if not isinstance(data, list):
                    raise GpsWvApiError("GPSWV 设备状态 data 字段不是列表")
                wanted_imei = self.settings["imei"]
                for item in data:
                    if isinstance(item, dict) and normalize_device_id(item.get("imei")) == wanted_imei:
                        return item
                raise GpsWvApiError(f"GPSWV 返回中未找到设备 {wanted_imei}")

            message = str(result.get("result") or result.get("message") or result.get("msg") or "")
            token_error = any(word in message.lower() for word in ("token", "令牌", "认证", "登录", "过期"))
            if attempt == 0 and token_error:
                self.clear_token()
                continue
            raise GpsWvApiError(
                f"GPSWV 查询设备失败：{message or result.get('code') or '未知错误'}"
            )
        raise GpsWvApiError("GPSWV 查询设备失败")

    def get_device_track_history(self, start_time, end_time, *, only_gps=0):
        for attempt in range(2):
            token = self.get_access_token()
            result = self._request_json("GET", "/device/track/history", query={
                "accessToken": token,
                "imei": self.settings["imei"],
                "startTime": int(start_time),
                "endTime": int(end_time),
                "coordType": self.settings["coord_type"],
                "onlyGps": int(only_gps),
            })
            if safe_int(result.get("code"), -1) == 0:
                data = result.get("data") or []
                if not isinstance(data, list):
                    raise GpsWvApiError("GPSWV 历史轨迹 data 字段不是列表")
                return data

            message = str(result.get("result") or result.get("message") or result.get("msg") or "")
            token_error = any(word in message.lower() for word in ("token", "令牌", "认证", "登录", "过期"))
            if attempt == 0 and token_error:
                self.clear_token()
                continue
            raise GpsWvApiError(
                f"GPSWV 历史轨迹查询失败：{message or result.get('code') or '未知错误'}"
            )
        raise GpsWvApiError("GPSWV 历史轨迹查询失败")


class GpsWvLocationPoller:
    def __init__(self, settings=None):
        self.settings = settings or load_settings()
        self.enabled = bool(self.settings["enabled"])
        self.client = GpsWvClient(self.settings)
        self._stop_event = threading.Event()
        self._thread = None
        self._last_error = None

    def start(self):
        if not self.enabled:
            print("GPSWV 云平台定位同步未启用（GPSWV_ENABLED=0）")
            return False
        missing = [name for name in ("appid", "key", "imei", "machine_id") if not self.settings.get(name)]
        if missing:
            print(f"GPSWV 云平台定位同步未启动，缺少配置：{', '.join(missing)}")
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"gpswv-location-{self.settings['machine_id']}",
            daemon=True,
        )
        self._thread.start()
        print(
            f"GPSWV 云平台定位同步已启动：设备 {self.settings['imei']} -> "
            f"{self.settings['machine_id']}，间隔 {self.settings['poll_interval']} 秒"
        )
        return True

    def stop(self):
        self._stop_event.set()

    def _loop(self):
        delay = 0
        while not self._stop_event.wait(delay):
            try:
                changed = self.sync_once()
                if changed:
                    print(f"GPSWV 已更新 {self.settings['machine_id']} 最新定位")
                self._last_error = None
                delay = self.settings["poll_interval"]
            except (GpsWvApiError, sqlite3.Error, ValueError) as exc:
                message = str(exc)
                if message != self._last_error:
                    print(f"GPSWV {self.settings['machine_id']} 定位同步失败：{message}")
                    self._last_error = message
                delay = max(60, self.settings["poll_interval"])

    def sync_once(self):
        item = self.client.get_device_status()
        longitude = safe_float(item.get("lng"), None)
        latitude = safe_float(item.get("lat"), None)
        if longitude is None or latitude is None:
            raise GpsWvApiError("GPSWV 返回中缺少有效经纬度")
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise GpsWvApiError("GPSWV 返回的经纬度超出范围")

        source_epoch = safe_float(item.get("gpsTime"), None)
        signal_epoch = safe_float(item.get("signalTime"), source_epoch)
        if source_epoch is None:
            source_epoch = signal_epoch
        if source_epoch and source_epoch > 10_000_000_000:
            source_epoch /= 1000.0
        if signal_epoch and signal_epoch > 10_000_000_000:
            signal_epoch /= 1000.0
        source_time = epoch_to_beijing_text(source_epoch) or beijing_now_text()
        received_at = beijing_now_text()
        last_seen = epoch_to_beijing_text(signal_epoch) or received_at
        speed = safe_float(item.get("speed"), 0) or 0
        direction = safe_int(item.get("course"), 0)
        status = map_vendor_status(
            item.get("status"), speed, signal_epoch, self.settings["online_timeout"]
        )
        return self._record_position({
            "lng": longitude,
            "lat": latitude,
            "speed": speed,
            "direction": direction,
            "status": status,
            "source_time": source_time,
            "last_seen": last_seen,
            "received_at": received_at,
        })

    def _record_position(self, position):
        database_path = Path(self.settings["database_path"])
        conn = sqlite3.connect(database_path, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("PRAGMA busy_timeout = 10000")
            machine_id = self.settings["machine_id"]
            machine = cursor.execute(
                "SELECT id, lng, lat, last_seen FROM machines WHERE id = ?", (machine_id,)
            ).fetchone()
            if not machine:
                raise ValueError(f"数据库中不存在农机 {machine_id}")

            changed = (
                str(machine["last_seen"] or "") != position["last_seen"]
                or abs(float(machine["lng"] or 0) - position["lng"]) > 0.0000001
                or abs(float(machine["lat"] or 0) - position["lat"]) > 0.0000001
            )
            if changed and self.settings.get("store_history"):
                cursor.execute("""
                    INSERT INTO machine_positions (
                        machine_id, device_no, lng, lat, altitude, speed, direction,
                        alarm, terminal_status, signal, source_time, received_at
                    ) VALUES (?, ?, ?, ?, 0, ?, ?, 0, 0, 0, ?, ?)
                """, (
                    machine_id, self.settings["imei"], position["lng"], position["lat"],
                    position["speed"], position["direction"], position["source_time"],
                    position["received_at"],
                ))

            cursor.execute("""
                UPDATE machines
                SET lng = ?, lat = ?, speed = ?, direction = ?, status = ?,
                    last_seen = ?, position_source = 'gpswv', device_no = ?,
                    auto_schedulable = 0
                WHERE id = ?
            """, (
                position["lng"], position["lat"], position["speed"],
                position["direction"], position["status"], position["last_seen"],
                self.settings["imei"], machine_id,
            ))
            conn.commit()
            return changed
        finally:
            conn.close()


class InactiveGpsWvLocationPoller:
    enabled = False

    def stop(self):
        return None


class GpsWvLocationPollerGroup:
    def __init__(self, settings_list=None):
        self.pollers = [
            GpsWvLocationPoller(settings)
            for settings in (settings_list or load_settings_list())
        ]
        self.enabled = any(poller.enabled for poller in self.pollers)

    def start(self):
        started = 0
        for poller in self.pollers:
            if poller.start():
                started += 1
        return started > 0

    def stop(self):
        for poller in self.pollers:
            poller.stop()


_POLLER = None
_POLLER_LOCK = threading.Lock()


def start_gpswv_location_poller():
    global _POLLER
    with _POLLER_LOCK:
        if _POLLER is None:
            try:
                _POLLER = GpsWvLocationPollerGroup()
                _POLLER.start()
            except GpsWvApiError as exc:
                print(f"GPSWV 云平台定位同步已停用：{exc}")
                _POLLER = InactiveGpsWvLocationPoller()
            atexit.register(_POLLER.stop)
        return _POLLER
