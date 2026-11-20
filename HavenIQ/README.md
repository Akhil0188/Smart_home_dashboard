# HavenIQ — Smart Home Monitoring & Control

Dark, responsive web dashboard for the college project **IoT-Based Smart Home Automation and Monitoring System**: live sensor data from SQLite plus **Device Control** (Light / Fan / AC) over MQTT, built to work with the simulator today and a real ESP32 later.
Stack: Python · Flask · SQLite · MQTT (Mosquitto + Paho) · HTML/CSS/JavaScript · Chart.js.
Windows 10/11, Python 3.14.

## How it connects to your existing pipeline

```
Python simulator --publishes JSON--> Mosquitto (home/sensors) --> your MQTT-to-SQLite writer --> smarthome.db
                                          |                                                      |
                                          | (status only: is broker up? are messages arriving?)  | (read-only SELECT queries)
                                          +------------------------> HavenIQ Flask app <--------+
                                                                              |
                                                                  Browser dashboard (polls every 3 s)
```

* **Data source = your `smarthome.db`, table `sensor_data`.** HavenIQ opens it **read-only**, so it cannot change or corrupt your data. It never creates a database and never generates sensor values.
* **Your simulator and database writer are not touched.** They keep running exactly as before.
* **MQTT status is real.** HavenIQ keeps one MQTT connection (client id `haveniq-xxxxxxxx`, auto-reconnect) that knows whether Mosquitto is reachable, counts messages on `home/sensors`, publishes device commands and receives device status. It never writes to the sensor database. If Mosquitto stops, the dashboard stays up and shows **MQTT Disconnected**. Set `MQTT_ENABLED=false` to turn this off.
* Door mapping (`1 = open`) and the database path are configurable in `.env`.

## Project structure

```
HavenIQ/
├── app.py               Flask app + API endpoints
├── config.py            settings (reads .env)
├── mqtt_monitor.py      MQTT client: status, device commands out, device status in
├── device_control.py    device state logic (UNKNOWN / ON / OFF, pending commands)
├── requirements.txt
├── .env.example         copy to .env and edit
├── start_dashboard.bat  double-click launcher (after setup)
├── templates/index.html
├── static/ (style.css, app.js, logo.svg)
├── simulator/sensor_simulator.py   your simulator + device behaviour (replaces your old file)
├── esp32/               ESP32 example sketch + README (wiring and mains safety)
├── tools/mqtt_test.py   watch / publish MQTT messages without PowerShell quoting
├── tests/               offline test of the whole device flow (no broker needed)
└── screenshots/         put your own screenshots here
```

API: `GET /api/data` (latest reading + status) · `GET /api/history?limit=60` (charts) · `GET /api/recent?limit=15` (table) · `GET /api/status` (backend, MQTT, database) · `GET /api/devices` (device states) · `POST /api/devices/light|fan|ac` (send a command).

## Setup on Windows (step by step)

**1. Extract.** Right-click `HavenIQ.zip` → *Extract All…* → choose e.g. `C:\Users\<you>\Desktop`. You get a folder `HavenIQ`.

**2. Open in VS Code.** Open VS Code → *File → Open Folder…* → select `HavenIQ`. Open a terminal: *Terminal → New Terminal* (PowerShell).

**3. Create and activate a virtual environment.**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
If PowerShell says scripts are disabled, run this once, then activate again:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
You should now see `(venv)` at the start of the prompt.

**4. Install dependencies.**
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**5. Set your database path.**
```powershell
Copy-Item .env.example .env
notepad .env
```
Change the `DB_PATH=` line to where **your** `smarthome.db` is. To find it: in File Explorer, Shift + right-click the file → *Copy as path*, then paste it **without the quotes**, e.g.
```
DB_PATH=C:\Users\YourName\Desktop\SmartHomeMQTT\smarthome.db
```
Save and close. (A relative path such as `DB_PATH=smarthome.db` is read from inside the HavenIQ folder.)

**6. Make sure Mosquitto is running** (needed for the MQTT status only). Check in PowerShell:
```powershell
Get-Service mosquitto
```
If it is stopped: `net start mosquitto` (PowerShell as Administrator). If you start the broker manually, keep that window open.

**7. Run your existing project** (in separate terminals, as you already do): your **database writer / MQTT subscriber** and your **simulator**. Use the same commands you used before, for example `python <your_file>.py`.

**8. Run the dashboard** (in the HavenIQ terminal with `(venv)` active):
```powershell
python app.py
```
Or double-click `start_dashboard.bat`. Stop with **Ctrl + C**.

**9. Open the dashboard:** <http://127.0.0.1:5000>

> The charts load Chart.js from a CDN, so the browser needs internet access. Test this before your presentation.

## `.env` options

| Setting | Meaning | Default |
|---|---|---|
| `DB_PATH` | path to your `smarthome.db` | `smarthome.db` in project folder |
| `DOOR_OPEN_VALUE` | value in `door` column meaning OPEN | `1` |
| `TIMESTAMP_IS_UTC` | `true` if timestamps are UTC (SQLite `CURRENT_TIMESTAMP` is UTC) | `true` |
| `MQTT_ENABLED / HOST / PORT / USERNAME / PASSWORD / TOPIC` | broker for the status check | enabled, `localhost`, `1883`, none, `home/sensors` |
| `HOST`, `PORT` | where the dashboard listens | `127.0.0.1`, `5000` |
| `REFRESH_SECONDS` | browser refresh interval | `3` |
| `HISTORY_POINTS` | readings shown in charts | `60` |
| `STALE_AFTER_SECONDS` | age after which data is "Stale" | `30` |

Restart `python app.py` after editing `.env`. To open the dashboard from a phone on the same Wi-Fi, set `HOST=0.0.0.0` and visit `http://<your-pc-ip>:5000` (allow it in Windows Firewall).

## Device Control (Light / Fan / AC)

```
Dashboard click -> POST /api/devices/<device> -> Flask publishes MQTT command  -> simulator / ESP32 switches the device
Dashboard shows <- GET /api/devices           <- Flask stores MQTT status     <- simulator / ESP32 publishes its REAL state
```

**The dashboard never assumes a command worked.** A click only sends the command ("Sending…", then "Waiting for device…"). The ON/OFF shown changes **only** when the device publishes its status. A device stays **UNKNOWN** until a real status message arrives. If no confirmation comes within 8 s you see "No confirmation from the device" and the old state stays. If MQTT is down, the controls are disabled and a banner explains why.

### The two MQTT messages (different formats on purpose)
| Topic | Direction | JSON |
|---|---|---|
| `home/devices/commands` | dashboard &rarr; device | `{"device": "light", "state": "ON"}` (`light`, `fan`, `ac`; `ON`/`OFF`; not retained) |
| `home/devices/status` | device &rarr; dashboard | `{"light": "ON", "fan": "OFF", "ac": "OFF"}` (published **retained**) |

Commands are deliberately **not retained**: a retained command would be replayed to a device that reconnects later. Status is retained so HavenIQ gets the last known state immediately when it starts.

### API
`GET /api/devices` returns
```json
{"connected": true, "error": null, "devices": {"light": "ON", "fan": "OFF", "ac": "OFF"},
 "pending": {}, "status_received": true, "status_age_seconds": 4.2, "status_stale": false,
 "command_topic": "home/devices/commands", "status_topic": "home/devices/status"}
```
`POST /api/devices/light` with `{"state": "ON"}` (header `Content-Type: application/json`) returns **202** `{"ok": true, "requested_state": "ON", ...}` (202 = sent, *not yet confirmed*). Errors are JSON: **400** invalid device/state/body, **503** MQTT not connected or disabled, **502/504** publish failed or not acknowledged by the broker.

### Run everything (Windows PowerShell, from the HavenIQ folder, venv active)
```powershell
# 1. Install dependencies (once)
pip install -r requirements.txt

# 2. Start Mosquitto - EITHER as a service (PowerShell as Administrator):
net start mosquitto
#    OR in its own window:
& "C:\Program Files\mosquitto\mosquitto.exe" -v

# 3. Start your database writer exactly as before (new window), e.g.:  python mqtt_to_database.py

# 4. Start the simulator (new window). Use the file from the simulator folder:
python simulator\sensor_simulator.py

# 5. Start HavenIQ (new window)
python app.py
```
Open **http://127.0.0.1:5000**, scroll to **Device Control** and press **ON** under Light.
Press **Enter** in the simulator window to publish sensor readings as before (sensors and devices are independent).

### Test each device from the command line
In a spare window, watch all device traffic: `python tools\mqtt_test.py watch`

```powershell
# Light
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/devices/light -ContentType "application/json" -Body '{"state":"ON"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/devices/light -ContentType "application/json" -Body '{"state":"OFF"}'
# Fan
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/devices/fan -ContentType "application/json" -Body '{"state":"ON"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/devices/fan -ContentType "application/json" -Body '{"state":"OFF"}'
# AC
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/devices/ac -ContentType "application/json" -Body '{"state":"ON"}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/devices/ac -ContentType "application/json" -Body '{"state":"OFF"}'
# What Flask currently believes
Invoke-RestMethod http://127.0.0.1:5000/api/devices | ConvertTo-Json
```
Expected messages (what `tools\mqtt_test.py watch` prints) after `light ON`:
```
home/devices/commands  {"device": "light", "state": "ON"}  (retained=False)
home/devices/status    {"light": "ON", "fan": "OFF", "ac": "OFF"}  (retained=True)
```
Skip Flask and talk to MQTT directly: `python tools\mqtt_test.py command fan ON`, or pretend to be the device: `python tools\mqtt_test.py status light=ON fan=OFF ac=OFF`. With Mosquitto's own tools (quoting for PowerShell):
```powershell
& "C:\Program Files\mosquitto\mosquitto_sub.exe" -h localhost -t "home/devices/#" -v
& "C:\Program Files\mosquitto\mosquitto_pub.exe" -h localhost -t home/devices/commands -m '{\"device\":\"ac\",\"state\":\"ON\"}'
```

### Testing without hardware or a broker
`python tests\test_device_flow.py` runs the whole chain (Flask API &rarr; command &rarr; the real simulator code &rarr; status &rarr; `/api/devices`, plus broker outage, reconnect, bad messages, publish failures) against an in-memory stand-in for Mosquitto. It proves the logic and JSON formats are consistent; it does **not** replace one run with real Mosquitto (steps above).

### Replacing the simulator with an ESP32 later
Nothing in HavenIQ changes. Stop the simulator, flash `esp32/esp32_device_controller/esp32_device_controller.ino` (set WiFi and `MQTT_HOST` = your PC's LAN IP; pins `LIGHT_PIN`, `FAN_PIN`, `AC_PIN` are configurable). It uses the same two topics and JSON. Read `esp32/README_ESP32.md` first: **never connect mains devices directly to ESP32 pins**; use isolated relay modules, and get a qualified person to do mains wiring. The sketch has not been compiled or run on hardware by the author.

**Mosquitto and the ESP32:** Mosquitto 2.x only accepts local connections by default. To accept the ESP32 on your Wi-Fi, add to `mosquitto.conf` (then restart the service) and allow TCP port 1883 in Windows Firewall:
```
listener 1883
allow_anonymous true
```
This is fine on a private test network; for anything else create a password file and set `MQTT_USERNAME` / `MQTT_PASSWORD` in `.env` and in the sketch.

### Troubleshooting Device Control
**Dashboard shows UNKNOWN**
1. UNKNOWN means *no status message has been received yet*. Is the simulator (or ESP32) running? The simulator prints `[device] status published: {...}`.
2. Run `python tools\mqtt_test.py watch`. If you never see a `home/devices/status` line, the device is not publishing; restart the simulator.
3. If you see status lines but the dashboard stays UNKNOWN, check the format: it must be `{"light":"ON","fan":"OFF","ac":"OFF"}`. A banner shows "Malformed device status" or "command-format message" if it is wrong.
4. Check `.env`: `MQTT_DEVICE_STATUS_TOPIC` must match what the device publishes, and `MQTT_HOST/PORT` must reach the broker.
5. Look at the HavenIQ terminal for `DEVICE MQTT STATUS:` lines. Open `http://127.0.0.1:5000/api/devices` to see `connected`, `error` and `status_received`.

**MQTT is Connected but the buttons do nothing / state does not change**
1. The message "Waiting for device…" followed by "No confirmation" means the command was sent but the device did not answer. Run `python tools\mqtt_test.py watch` and click a button: you must see a `home/devices/commands` line.
2. No commands line? Check the HavenIQ terminal for `DEVICE MQTT COMMAND:` and the browser's red message ("Command failed: ...").
3. Commands line present but no status line: the device is not subscribed to `home/devices/commands` (simulator: restart it; ESP32: check Serial Monitor and the `MQTT_HOST`).
4. The device must publish status after every command, even if the state did not change; the simulator and the ESP32 sketch both do.
5. Buttons greyed out means the dashboard's MQTT connection is down (see the red banner); start Mosquitto. It reconnects by itself, no Flask restart needed.
6. Wrong topic names in `.env`, or two copies of HavenIQ/simulators using different topics, are the usual cause of silent failures.

## Verification checklist

- [ ] `python app.py` prints the dashboard URL and the database path you expect.
- [ ] The page opens at http://127.0.0.1:5000 with the dark layout and no red banner.
- [ ] Header shows **MQTT Connected** (green) while Mosquitto runs.
- [ ] System Status: Flask **Running**, Database **Connected**, Last Sensor Update **Live**.
- [ ] The six cards show numbers matching the newest row: `SELECT * FROM sensor_data ORDER BY id DESC LIMIT 1;`
- [ ] With the simulator running, values and charts update every few seconds.
- [ ] The recent-readings table lists newest first; door badge matches the card.
- [ ] Stop the simulator → status becomes **Stale** after ~30 s. Stop Mosquitto → header shows **MQTT Disconnected** and the page keeps working.
- [ ] Stop `python app.py` → page shows "Cannot reach the HavenIQ backend" (never fake data).
- [ ] Check raw API: <http://127.0.0.1:5000/api/data>, `/api/history`, `/api/recent`, `/api/status`, `/api/devices`.
- [ ] Device Control: all three show **UNKNOWN** before the simulator runs, then **OFF**; pressing **ON** shows "Waiting for device…" and then **ON**; stopping Mosquitto disables the buttons.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not recognized | Reinstall Python with *Add python.exe to PATH*, or try `py -m venv venv`. |
| `Activate.ps1 cannot be loaded` | Run the `Set-ExecutionPolicy` command from step 3. |
| `ModuleNotFoundError: flask` / `paho` | The venv is not active, or step 4 was skipped. Activate it and run `pip install -r requirements.txt`. |
| Banner: *Database file '…' was not found* | Fix `DB_PATH` in `.env` (copy the real path, no quotes), restart the app. |
| Banner: *Table 'sensor_data' does not exist* | The writer has not created the table yet. Run your database writer first. |
| *Missing column(s)* | The table must have `id, temperature, humidity, light, door, power, energy, timestamp`. |
| *No sensor readings yet* | Start the simulator **and** the database writer. |
| Status stays **Stale** with correct data | Timestamps from `DEFAULT CURRENT_TIMESTAMP` are UTC, so keep `TIMESTAMP_IS_UTC=true`; also check that the writer is running and that you pressed Enter in the simulator (it publishes only on Enter). |
| **MQTT Disconnected** | Start Mosquitto; check `MQTT_HOST`/`MQTT_PORT`; fill `MQTT_USERNAME/PASSWORD` if the broker needs login. |
| Door shows the wrong state | Set `DOOR_OPEN_VALUE=0` (or `1`) in `.env`. |
| Charts empty with a "Chart.js could not be loaded" message | No internet access to cdn.jsdelivr.net. |
| `Address already in use` | Change `PORT` in `.env` (e.g. `5001`). |
| "database is locked" | Rare; the next refresh (3 s) recovers on its own. |
