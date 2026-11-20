"""HavenIQ - Smart Home Monitoring & Control dashboard (Flask backend).

Sensors : reads the EXISTING SQLite database (read-only). Data collection stays in your
          own MQTT-to-SQLite writer.
Devices : publishes commands to MQTT and shows the state the device reports back.
"""
import logging
import sqlite3
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

import config
from device_control import DEVICES, STATES, DeviceRegistry
from mqtt_monitor import MQTTMonitor

app = Flask(__name__)
app.json.sort_keys = False
STARTED_AT = time.time()
devices = DeviceRegistry(config.DEVICE_COMMAND_TIMEOUT_SECONDS, config.DEVICE_STATUS_STALE_SECONDS)
monitor = MQTTMonitor(devices)

COLUMNS = ["id", "temperature", "humidity", "light", "door", "power", "energy", "timestamp"]
SELECT_SQL = f"SELECT {', '.join(COLUMNS)} FROM {config.TABLE_NAME}"


class DBUnavailable(Exception):
    def __init__(self, state: str, message: str):
        super().__init__(message)
        self.state = state
        self.message = message


# ----------------------------------------------------------------- database
def open_db() -> sqlite3.Connection:
    path = config.DB_PATH
    if not path.is_file():
        raise DBUnavailable("missing", f"Database file '{path.name}' was not found. Check DB_PATH in .env.")
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        raise DBUnavailable("error", "The database file could not be opened.")
    try:
        found = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (config.TABLE_NAME,)
        ).fetchone()
        if not found:
            raise DBUnavailable("no_table", f"Table '{config.TABLE_NAME}' does not exist in the database yet.")
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({config.TABLE_NAME})")}
        missing = [c for c in COLUMNS if c not in cols]
        if missing:
            raise DBUnavailable("schema", "Table is missing column(s): " + ", ".join(missing))
    except sqlite3.Error:
        conn.close()
        raise DBUnavailable("error", "The database could not be read.")
    except DBUnavailable:
        conn.close()
        raise
    return conn


def fetch(sql: str, params: tuple = ()) -> list:
    conn = open_db()
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        raise DBUnavailable("error", "The database query failed (is another program locking it?).")
    finally:
        conn.close()


def parse_ts(text):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(str(text), fmt)
        except ValueError:
            continue
    return None


def age_seconds(ts_text):
    parsed = parse_ts(ts_text)
    if parsed is None:
        return None
    if config.TIMESTAMP_IS_UTC:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        now = datetime.now()
    return max(0, round((now - parsed).total_seconds()))


def enrich(row) -> dict:
    item = {c: row[c] for c in COLUMNS}
    is_open = item["door"] is not None and int(item["door"]) == config.DOOR_OPEN_VALUE
    item["door_open"] = is_open
    item["door_label"] = "Open" if is_open else "Closed"
    return item


def clamp(value, low, high, default):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------- status
def database_status() -> dict:
    try:
        row = fetch(f"SELECT COUNT(*) AS n, MAX(timestamp) AS last FROM {config.TABLE_NAME}")[0]
        return {"state": "ok", "message": "Database reachable", "file": config.DB_PATH.name,
                "rows": row["n"], "last_timestamp": row["last"]}
    except DBUnavailable as exc:
        return {"state": exc.state, "message": exc.message, "file": config.DB_PATH.name,
                "rows": None, "last_timestamp": None}


def build_status() -> dict:
    db = database_status()
    last_ts = db["last_timestamp"]
    age = age_seconds(last_ts) if last_ts else None
    if db["state"] != "ok":
        data_state = "unavailable"
    elif not db["rows"]:
        data_state = "empty"
    elif age is not None and age > config.STALE_AFTER_SECONDS:
        data_state = "stale"
    else:
        data_state = "live"
    mqtt_info = monitor.snapshot()
    dev = devices.snapshot()
    return {
        "backend": {"state": "ok", "uptime_seconds": round(time.time() - STARTED_AT)},
        "mqtt": mqtt_info,
        "device_control": {"state": mqtt_info["state"], "status_received": dev["status_received"],
                           "status_age_seconds": dev["status_age_seconds"],
                           "command_topic": config.MQTT_DEVICE_COMMAND_TOPIC,
                           "status_topic": config.MQTT_DEVICE_STATUS_TOPIC},
        "database": db,
        "data": {"state": data_state, "last_update": last_ts, "age_seconds": age,
                 "stale_after_seconds": config.STALE_AFTER_SECONDS},
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ------------------------------------------------------------------- routes
@app.after_request
def no_cache(resp):
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/")
def index():
    return render_template("index.html", refresh_ms=config.REFRESH_SECONDS * 1000,
                           history_points=config.HISTORY_POINTS)


@app.route("/api/status")
def api_status():
    return jsonify(build_status())


@app.route("/api/data")
def api_data():
    status = build_status()
    try:
        rows = fetch(SELECT_SQL + " ORDER BY id DESC LIMIT 1")
    except DBUnavailable as exc:
        return jsonify({"error": exc.message, "latest": None, "status": status}), 503
    latest = enrich(rows[0]) if rows else None
    if latest:
        latest["age_seconds"] = age_seconds(latest["timestamp"])
    return jsonify({"latest": latest, "status": status})


@app.route("/api/history")
def api_history():
    limit = clamp(request.args.get("limit"), 1, 1000, config.HISTORY_POINTS)
    try:
        rows = fetch(SELECT_SQL + " ORDER BY id DESC LIMIT ?", (limit,))
    except DBUnavailable as exc:
        return jsonify({"error": exc.message, "readings": []}), 503
    readings = [enrich(r) for r in reversed(rows)]  # oldest -> newest for charts
    return jsonify({"count": len(readings), "readings": readings})


@app.route("/api/recent")
def api_recent():
    limit = clamp(request.args.get("limit"), 1, 50, 15)
    try:
        rows = fetch(SELECT_SQL + " ORDER BY id DESC LIMIT ?", (limit,))
    except DBUnavailable as exc:
        return jsonify({"error": exc.message, "readings": []}), 503
    return jsonify({"count": len(rows), "readings": [enrich(r) for r in rows]})  # newest first


# ------------------------------------------------------------ device control
def devices_payload() -> dict:
    """Body of GET /api/devices."""
    snap = devices.snapshot()
    mqtt_info = monitor.snapshot()
    connected = mqtt_info["state"] == "connected"
    if mqtt_info["state"] == "disabled":
        error = "MQTT is disabled (MQTT_ENABLED=false)"
    elif not connected:
        error = mqtt_info["error"] or "MQTT broker is not connected"
    else:
        error = snap["status_error"]
    return {
        "connected": connected,
        "error": error,
        "devices": snap["devices"],
        "pending": snap["pending"],
        "status_received": snap["status_received"],
        "status_age_seconds": snap["status_age_seconds"],
        "status_stale": snap["status_stale"],
        "command_topic": config.MQTT_DEVICE_COMMAND_TOPIC,
        "status_topic": config.MQTT_DEVICE_STATUS_TOPIC,
    }


@app.route("/api/devices")
def api_devices():
    return jsonify(devices_payload())


@app.route("/api/devices/<device>", methods=["POST"])
def api_device_command(device):
    """Publish a command to MQTT. The state shown on the dashboard changes ONLY when the
    device itself reports it on home/devices/status."""
    key = device.lower()
    if key not in DEVICES:
        return jsonify({"ok": False, "error": "Invalid device. Use: " + ", ".join(DEVICES)}), 400
    body = request.get_json(silent=True)  # needs Content-Type: application/json
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": 'Send JSON like {"state": "ON"} with Content-Type: application/json'}), 400
    raw = body.get("state")
    state = raw.strip().upper() if isinstance(raw, str) else None
    if state not in STATES:
        return jsonify({"ok": False, "error": "Invalid state. Use ON or OFF"}), 400
    ok, error, code = monitor.send_command(key, state)
    if not ok:
        return jsonify({"ok": False, "error": error}), code
    return jsonify({"ok": True, "device": key, "requested_state": state,
                    "message": "Command sent. Waiting for the device to confirm."}), 202


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Unknown API endpoint"}), 404
    return "Page not found", 404


@app.errorhandler(405)
def method_not_allowed(_):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(500)
def server_error(_):
    return jsonify({"error": "Unexpected server error"}), 500


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # keep the terminal readable
    monitor.start()
    print(f"HavenIQ dashboard -> http://{config.HOST}:{config.PORT}")
    print(f"Database file     -> {config.DB_PATH}")
    app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False, threaded=True)
