"""HavenIQ configuration. Values come from environment variables or a .env file."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    """Tiny .env reader (no extra dependency). Real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _db_path() -> Path:
    raw = os.environ.get("DB_PATH", "").strip() or "smarthome.db"
    path = Path(os.path.expandvars(raw)).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


DB_PATH = _db_path()
TABLE_NAME = "sensor_data"  # fixed on purpose: table names cannot be SQL parameters
DOOR_OPEN_VALUE = _int("DOOR_OPEN_VALUE", 1)
TIMESTAMP_IS_UTC = _bool("TIMESTAMP_IS_UTC", True)  # SQLite CURRENT_TIMESTAMP is stored in UTC

MQTT_ENABLED = _bool("MQTT_ENABLED", True)
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = _int("MQTT_PORT", 1883)
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "home/sensors")

# Device control (Light / Fan / AC). Same topics for the simulator and a real ESP32.
MQTT_DEVICE_COMMAND_TOPIC = os.environ.get("MQTT_DEVICE_COMMAND_TOPIC", "home/devices/commands")
MQTT_DEVICE_STATUS_TOPIC = os.environ.get("MQTT_DEVICE_STATUS_TOPIC", "home/devices/status")
# How long to wait for the device to confirm a command before the dashboard says "no confirmation".
DEVICE_COMMAND_TIMEOUT_SECONDS = max(2, _int("DEVICE_COMMAND_TIMEOUT_SECONDS", 8))
# If the device sends no status for this long, the dashboard marks it "no recent update".
DEVICE_STATUS_STALE_SECONDS = max(10, _int("DEVICE_STATUS_STALE_SECONDS", 120))

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = _int("PORT", 5000)
REFRESH_SECONDS = max(1, _int("REFRESH_SECONDS", 3))
HISTORY_POINTS = max(10, min(1000, _int("HISTORY_POINTS", 60)))
STALE_AFTER_SECONDS = max(5, _int("STALE_AFTER_SECONDS", 30))
