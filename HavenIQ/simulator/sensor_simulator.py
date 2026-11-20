"""HavenIQ sensor + device simulator (test tool, replaces nothing in the dashboard).

Sensors : unchanged from your original file. One reading is published to home/sensors
          every time you press Enter (door: 1 = open, 0 = closed, q = quit).
Devices : NEW. Behaves like the future ESP32:
            - subscribes to  home/devices/commands   {"device": "light", "state": "ON"}
            - keeps its own light / fan / ac state
            - publishes      home/devices/status     {"light": "ON", "fan": "OFF", "ac": "OFF"}
              (retained) after every command, at start-up and every 30 seconds.
"""
import json
import random
import threading
import time

import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883
TOPIC = "home/sensors"
DEVICE_COMMAND_TOPIC = "home/devices/commands"
DEVICE_STATUS_TOPIC = "home/devices/status"
STATUS_HEARTBEAT_SECONDS = 30

DEVICES = ("light", "fan", "ac")
device_states = {name: "OFF" for name in DEVICES}   # a real device boots with everything OFF
state_lock = threading.Lock()
stop_event = threading.Event()


def publish_device_status(client):
    """Publish the combined status message (retained, so a late dashboard still gets it)."""
    with state_lock:
        payload = json.dumps(device_states)
    client.publish(DEVICE_STATUS_TOPIC, payload, qos=1, retain=True)
    print("\n[device] status published:", payload)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(DEVICE_COMMAND_TOPIC, qos=1)   # re-subscribes after every reconnect
        print(f"\n[device] listening on {DEVICE_COMMAND_TOPIC}")
        publish_device_status(client)
    else:
        print("\n[device] connection failed:", reason_code)


def on_message(client, userdata, message):
    """Handle a COMMAND message: {"device": "light", "state": "ON"}."""
    try:
        data = json.loads(message.payload.decode())
        device = str(data["device"]).strip().lower()
        state = str(data["state"]).strip().upper()
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print("\n[device] ignored malformed command:", exc)
        return
    if device not in DEVICES or state not in ("ON", "OFF"):
        print(f"\n[device] ignored invalid command: device={device!r} state={state!r}")
        return
    with state_lock:
        device_states[device] = state            # a real ESP32 would switch its GPIO / relay here
    print(f"\n[device] command received: {device} -> {state}")
    publish_device_status(client)                # report the ACTUAL state back


def heartbeat(client):
    while not stop_event.wait(STATUS_HEARTBEAT_SECONDS):
        if client.is_connected():
            publish_device_status(client)


def main():
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="smart_home_simulator"
    )
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    client.loop_start()
    threading.Thread(target=heartbeat, args=(client,), daemon=True).start()

    print("Connected to Mosquitto!")
    print("Enter 1 for door OPEN")
    print("Enter 0 for door CLOSED")
    print("Enter q to quit")

    door_status = 0

    try:
        while True:
            command = input(
                "\nDoor status (1=open, 0=closed, Enter=keep, q=quit): "
            ).strip().lower()

            if command == "q":
                break
            elif command == "1":
                door_status = 1
            elif command == "0":
                door_status = 0

            data = {
                "temperature": round(random.uniform(20, 35), 2),
                "humidity": round(random.uniform(30, 80), 2),
                "light": random.randint(0, 1000),
                "door": door_status,
                "power": round(random.uniform(50, 500), 2),
                "energy": round(random.uniform(0, 10), 2)
            }

            payload = json.dumps(data)
            result = client.publish(TOPIC, payload)

            result.wait_for_publish()

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print("Published:", payload)
            else:
                print("Publish failed")

    except KeyboardInterrupt:
        print("\nSimulator stopped.")

    finally:
        stop_event.set()
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
