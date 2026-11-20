"""Offline end-to-end test of the device-control flow (no broker, no hardware needed).

    python tests\test_device_flow.py

Flow under test:  Flask API -> MQTT command -> simulator (device) -> MQTT status -> Flask -> /api/devices
"""
import importlib.util
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import fake_paho
paho_client = fake_paho.install()
BROKER = fake_paho.BROKER

tmp = Path(tempfile.mkdtemp())
os.environ.update({"DB_PATH": str(tmp / "test.db"), "DEVICE_COMMAND_TIMEOUT_SECONDS": "2"})
con = sqlite3.connect(tmp / "test.db")
con.execute("CREATE TABLE sensor_data (id INTEGER PRIMARY KEY AUTOINCREMENT, temperature REAL, humidity REAL, light INTEGER, door INTEGER, power REAL, energy REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)")
for i in range(5):
    con.execute("INSERT INTO sensor_data (temperature,humidity,light,door,power,energy) VALUES (?,?,?,?,?,?)", (25 + i, 60, 100 + i, i % 2, 300, 1.5))
con.commit(); con.close()

import app as haveniq            # noqa: E402  (imports config, device_control, mqtt_monitor)
import config                    # noqa: E402

class Capture(logging.Handler):
    def __init__(self): super().__init__(); self.lines = []
    def emit(self, r): self.lines.append(r.getMessage())
cap = Capture(); logging.getLogger("haveniq").addHandler(cap); logging.getLogger("haveniq").setLevel(logging.INFO)

passed = 0
def check(name, cond, extra=""):
    global passed
    if not cond:
        print(f"FAIL  {name} {extra}"); sys.exit(1)
    passed += 1; print(f"PASS  {name}")

web = haveniq.app.test_client()
get = lambda url: web.get(url).get_json()
post = lambda dev, body, **kw: web.post(f"/api/devices/{dev}", json=body, **kw)

# spy = another MQTT client that records exactly what is on the wire
spy = paho_client.Client(client_id="spy"); wire = []
spy.on_message = lambda c, u, m: wire.append((m.topic, json.loads(m.payload) if m.payload.startswith(b"{") else m.payload, m.retain))
spy.loop_start(); spy.subscribe([(config.MQTT_DEVICE_COMMAND_TOPIC, 1), (config.MQTT_DEVICE_STATUS_TOPIC, 1)])
haveniq.monitor.start()

# 1. Nothing has ever published a status -> UNKNOWN (never a fake OFF)
d = get("/api/devices")
check("starts connected, all devices UNKNOWN", d["connected"] and d["devices"] == {"light": "UNKNOWN", "fan": "UNKNOWN", "ac": "UNKNOWN"} and d["status_received"] is False and d["error"] is None)

# 2. input validation
check("invalid device -> 400", post("heater", {"state": "ON"}).status_code == 400)
check("invalid state -> 400", post("light", {"state": "MAYBE"}).status_code == 400)
check("missing JSON -> 400", web.post("/api/devices/light", data="state=ON").status_code == 400)
check("GET on command route -> 405 JSON", web.get("/api/devices/light").status_code == 405 and web.get("/api/devices/light").is_json)

# 3. no device online: command is sent, state must NOT change, then 'no confirmation'
r = post("light", {"state": "on"})
check("command accepted (202) and normalised", r.status_code == 202 and r.get_json()["requested_state"] == "ON")
cmd = [w for w in wire if w[0] == config.MQTT_DEVICE_COMMAND_TOPIC][-1]
check('wire format of COMMAND is exactly {"device","state"}', cmd[1] == {"device": "light", "state": "ON"} and cmd[2] is False)
d = get("/api/devices")
check("no device -> light stays UNKNOWN (UI cannot fake ON)", d["devices"]["light"] == "UNKNOWN" and d["pending"]["light"]["requested"] == "ON" and not d["pending"]["light"]["timed_out"])
time.sleep(2.2)
d = get("/api/devices")
check("no confirmation -> pending timed_out, state still UNKNOWN", d["pending"]["light"]["timed_out"] and d["devices"]["light"] == "UNKNOWN")

# 4. start the REAL simulator module as the device
spec = importlib.util.spec_from_file_location("sim", ROOT / "simulator" / "sensor_simulator.py")
sim = importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
dev = sim.mqtt.Client(callback_api_version=sim.mqtt.CallbackAPIVersion.VERSION2, client_id="smart_home_simulator")
dev.on_connect, dev.on_message = sim.on_connect, sim.on_message
dev.connect("localhost", 1883, 60); dev.loop_start()
d = get("/api/devices")
st = [w for w in wire if w[0] == config.MQTT_DEVICE_STATUS_TOPIC][-1]
check('wire format of STATUS is exactly {"light","fan","ac"} and retained', set(st[1]) == {"light", "fan", "ac"} and st[2] is True)
check("simulator start-up status received -> all OFF", d["devices"] == {"light": "OFF", "fan": "OFF", "ac": "OFF"} and d["status_received"])

# 5. full round trip for every device, ON then OFF
for name in ("light", "fan", "ac"):
    for state in ("ON", "OFF"):
        r = post(name, {"state": state})
        d = get("/api/devices")
        others = {k: v for k, v in d["devices"].items() if k != name}
        check(f"{name} {state}: 202, device confirmed, pending cleared, others untouched",
              r.status_code == 202 and d["devices"][name] == state and name not in d["pending"] and all(v == "OFF" for v in others.values()))
        c = [w for w in wire if w[0] == config.MQTT_DEVICE_COMMAND_TOPIC][-1][1]
        check(f"{name} {state}: command on wire is {{device,state}}", c == {"device": name, "state": state})

# 6. bad messages from the device side
before = get("/api/devices")["devices"]
spy.publish(config.MQTT_DEVICE_STATUS_TOPIC, b"this is not json")
d = get("/api/devices")
check("malformed status ignored, error reported, states kept", d["devices"] == before and "Malformed" in d["error"])
spy.publish(config.MQTT_DEVICE_STATUS_TOPIC, json.dumps({"device": "light", "state": "ON"}))
d = get("/api/devices")
check("COMMAND-format message on STATUS topic is ignored", d["devices"] == before and "command-format" in d["error"])
spy.publish(config.MQTT_DEVICE_STATUS_TOPIC, json.dumps({"light": "ON", "fan": "BROKEN"}))
d = get("/api/devices")
check("partly invalid status: valid field applied, bad field ignored", d["devices"]["light"] == "ON" and d["devices"]["fan"] == before["fan"] and "invalid value for fan" in d["error"])
spy.publish(config.MQTT_DEVICE_STATUS_TOPIC, json.dumps({"light": "OFF", "fan": "OFF", "ac": "OFF"}))
check("a good status clears the error", get("/api/devices")["error"] is None)

# 7. simulator ignores bad commands and does not crash
n = len(wire)
for junk in (b"nope", b'{"device":"heater","state":"ON"}', b'{"device":"fan","state":"HALF"}', b'{"x":1}'):
    spy.publish(config.MQTT_DEVICE_COMMAND_TOPIC, junk)
check("simulator ignores malformed/invalid commands (no status published)", all(w[0] == config.MQTT_DEVICE_COMMAND_TOPIC for w in wire[n:]) and sim.device_states == {"light": "OFF", "fan": "OFF", "ac": "OFF"})

# 8. logging: command + status lines, unchanged heartbeat not logged at INFO
cmd_logs = [l for l in cap.lines if l.startswith("DEVICE MQTT COMMAND:")]
status_logs = [l for l in cap.lines if l.startswith("DEVICE MQTT STATUS:")]
n_status = len(status_logs)
sim.publish_device_status(dev); sim.publish_device_status(dev)
check("log lines for commands and status; unchanged heartbeat is quiet",
      cmd_logs and '{"device": "ac", "state": "OFF"}' in cmd_logs[-1] and len([l for l in cap.lines if l.startswith("DEVICE MQTT STATUS:")]) == n_status)

# 9. publish problems
BROKER.fail_publish = True
r = post("fan", {"state": "ON"}); BROKER.fail_publish = False
check("publish failure -> 502, nothing pending", r.status_code == 502 and "fan" not in get("/api/devices")["pending"])
BROKER.no_ack = True
r = post("fan", {"state": "ON"}); BROKER.no_ack = False
check("no broker acknowledgement -> 504, nothing pending", r.status_code == 504 and "fan" not in get("/api/devices")["pending"])

# 10. broker outage and automatic reconnect
sim.device_states["ac"] = "ON"; sim.publish_device_status(dev)          # retained status now has ac=ON
BROKER.go_down()
d = get("/api/devices"); r = post("light", {"state": "ON"})
check("broker down: connected=false, error shown, last known states kept", d["connected"] is False and d["error"] and d["devices"]["ac"] == "ON")
check("broker down: command -> 503 'not connected', nothing pending", r.status_code == 503 and "not connected" in r.get_json()["error"] and "light" not in get("/api/devices")["pending"])
check("broker down: /api/status still answers, other API unaffected", web.get("/api/status").status_code == 200 and web.get("/api/data").status_code == 200)
BROKER.go_up()
d = get("/api/devices")
check("auto-reconnect: connected again, re-subscribed, retained status re-applied", d["connected"] and d["devices"]["ac"] == "ON")
r = post("light", {"state": "ON"})
check("commands work again after reconnect", r.status_code == 202 and get("/api/devices")["devices"]["light"] == "ON")

# 11. MQTT disabled
config.MQTT_ENABLED = False
check("MQTT disabled -> 503 and clear error", post("light", {"state": "OFF"}).status_code == 503 and "disabled" in get("/api/devices")["error"])
config.MQTT_ENABLED = True

# 12. existing sensor features still work
data, hist, rec, status = get("/api/data"), get("/api/history?limit=3"), get("/api/recent?limit=2"), get("/api/status")
check("existing sensor endpoints intact", data["latest"]["id"] == 5 and hist["count"] == 3 and rec["count"] == 2 and rec["readings"][0]["id"] == 5)
check("/api/status keeps backend/mqtt/database/data and adds device_control",
      all(k in status for k in ("backend", "mqtt", "database", "data", "device_control")) and status["data"]["state"] in ("live", "stale"))
check("sensor list has no motion", not any("motion" in json.dumps(x).lower() for x in (data, hist, rec)))

# 13. static checks: duplicate routes, motion leftovers, topics consistent everywhere
rules = [(r.rule, tuple(sorted(r.methods - {"HEAD", "OPTIONS"}))) for r in haveniq.app.url_map.iter_rules()]
check("no duplicate Flask routes", len(rules) == len(set(rules)), str(rules))
leftovers = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and p.suffix in (".py", ".js", ".html", ".css", ".ino", ".md", ".example") and "tests" not in p.parts
             and re.search(r"motion|\bpir\b", p.read_text(encoding="utf-8", errors="ignore"), re.I) and "prefers-reduced-motion" not in p.read_text(encoding="utf-8", errors="ignore")]
check("no motion-sensor code left", not leftovers, str(leftovers))
for f in ("simulator/sensor_simulator.py", "esp32/esp32_device_controller/esp32_device_controller.ino", "config.py"):
    t = (ROOT / f).read_text()
    check(f"{f} uses home/devices/commands and home/devices/status", "home/devices/commands" in t and "home/devices/status" in t)

print(f"\nALL {passed} CHECKS PASSED")
