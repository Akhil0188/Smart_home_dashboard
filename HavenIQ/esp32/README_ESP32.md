# ESP32 device controller for HavenIQ

`esp32_device_controller/esp32_device_controller.ino` replaces the **simulator**. The dashboard, Flask API and MQTT topics stay exactly the same.

> The sketch was written to the same protocol the simulator and dashboard use, but it has **not been compiled or run on real hardware** here. Compile it and test with LEDs first.

## What the ESP32 needs to know
| Item | Value |
|---|---|
| MQTT broker | IP address of the PC running Mosquitto (not `localhost`) |
| Subscribe | `home/devices/commands` &rarr; `{"device": "light", "state": "ON"}` |
| Publish (retained) | `home/devices/status` &rarr; `{"light":"ON","fan":"OFF","ac":"OFF"}` |

## Configurable pins
`LIGHT_PIN`, `FAN_PIN`, `AC_PIN` (defaults 26, 27, 25 are placeholders) and `RELAY_ACTIVE_LOW` at the top of the sketch. Avoid GPIO 6-11 (flash), 34-39 (input only) and the boot pins 0, 2, 5, 12, 15.

## Replacing the simulator
1. Stop `simulator\sensor_simulator.py`'s device part: simplest is to close the simulator (the sensor readings are separate from device control; keep your sensor writer as it is).
2. Edit the settings at the top of the `.ino` (WiFi, `MQTT_HOST`), upload it with the Arduino IDE.
3. Allow Mosquitto to accept LAN connections (see README, "Mosquitto and the ESP32"), and allow port 1883 in Windows Firewall.
4. Open the Serial Monitor (115200 baud) and click a button on the dashboard.

## SAFETY - mains devices
- **Never connect a light, fan or AC supply directly to an ESP32 pin.** GPIO pins give 3.3 V at a few mA.
- The ESP32 drives a **relay module / SSR / contactor** that is rated for the load. Use a module with optocoupler isolation and keep the mains side fully enclosed and separate from the low-voltage side.
- Mains wiring can kill. Have a qualified electrician do or check anything above low voltage. Start with LEDs or a 5 V/12 V lamp and fan.
- An **air conditioner** should not be switched by cutting its power with a plain relay (compressor damage, high inrush current). Use the AC's own remote interface (IR transmitter or the manufacturer's smart module) or a suitably rated contactor installed by a professional. The `AC_PIN` should only drive such a control circuit.
- Outputs boot **OFF**. After a power cut the devices stay off until a new command arrives.
