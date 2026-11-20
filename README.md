# 🏠 HavenIQ – Smart Home Monitoring & Control

![Python](https://img.shields.io/badge/Python-3.14-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-Backend-black?logo=flask)
![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-purple)
![SQLite](https://img.shields.io/badge/Database-SQLite-blue?logo=sqlite)

**HavenIQ** is an IoT-based Smart Home Monitoring and Control System developed to monitor household conditions and control smart devices through a modern web dashboard.

Built using Python, Flask, MQTT and SQLite, HavenIQ provides centralized monitoring, interactive visualizations and device automation.

## ✨ Features

- 🌡️ Real-time temperature and humidity monitoring.
- 💡 Light intensity monitoring.
- 🚪 Door open/closed status detection.
- ⚡ Power and energy consumption tracking.
- 📊 Interactive graphs using Chart.js.
- 🎛️ MQTT-based Light, Fan and AC control.
- 🗄️ SQLite database integration with read-only dashboard access.
- 📱 Responsive dark-themed dashboard.
- 🔄 Automatic MQTT reconnection and connection monitoring.

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core programming |
| Flask | Backend and APIs |
| MQTT + Mosquitto | Communication |
| SQLite | Database |
| HTML, CSS, JavaScript | Frontend |
| Chart.js | Data visualization |

## 🏗️ System Architecture

```text
Sensor Simulator
       |
       v
    Mosquitto
       |
       v
 MQTT Database Writer
       |
       v
    SQLite DB
       |
       v
   Flask Backend
       |
       v
  HavenIQ Dashboard
```

Device commands and status updates use separate MQTT topics:

- `home/devices/commands`
- `home/devices/status`

## 🎛️ Device Control

HavenIQ supports three devices:

| Device | Commands |
|---|---|
| 💡 Light | ON / OFF |
| 🌀 Fan | ON / OFF |
| ❄️ AC | ON / OFF |

Commands are published through MQTT, and the dashboard updates device states only after receiving confirmation.

## 📁 Project Structure

```text
HavenIQ/
├── app.py
├── config.py
├── mqtt_monitor.py
├── device_control.py
├── requirements.txt
├── templates/
├── static/
├── simulator/
├── esp32/
├── tools/
├── tests/
└── screenshots/
```

## 🚀 Getting Started

**Requirements:** Python 3.14, VS Code and Mosquitto.

1. Clone the repository:

   ```bash
   git clone https://github.com/Akhil0188/Smart_home_dashboard.git
   ```

2. Open the project folder in VS Code.

3. Create and activate a virtual environment:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Configure `.env` using `.env.example`. Set `DB_PATH` to your existing `smarthome.db`.

6. Start Mosquitto, your existing database writer and sensor simulator.

7. Start HavenIQ:

   ```bash
   python app.py
   ```

8. Open **http://127.0.0.1:5000**

## 🔒 Data Integrity

HavenIQ reads sensor records from the existing SQLite database in read-only mode. Sensor simulation and database writing operate independently.

The dashboard does not generate fake sensor readings or modify existing sensor records.

## 🔮 Future Scope

- Real ESP32 hardware integration.
- Physical relay-based automation.
- Remote smart-home access.
- Energy analytics and smart notifications.

## 👨‍💻 Author

**Akhil Yadav**  
ABES Engineering College  
Electronics and Communication Engineering

---

**HavenIQ – Making Smart Homes Smarter.** 🏠
