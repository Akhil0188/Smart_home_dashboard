
import json
import random
import threading
import time
import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883

SENSOR_TOPIC = "home/sensors"
COMMAND_TOPIC = "home/devices/commands"
STATUS_TOPIC = "home/devices/status"

devices = {
    "light": "OFF",
    "fan": "OFF",
    "ac": "OFF"
}

door_status = 0
lock = threading.Lock()


def publish_device_status(client):
    with lock:
        status = devices.copy()

    client.publish(
        STATUS_TOPIC,
        json.dumps(status),
        qos=1,
        retain=True
    )
    print("Device status:", status)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to Mosquitto!")
        client.subscribe(COMMAND_TOPIC, qos=1)
        publish_device_status(client)
        print("Listening for device commands...")
    else:
        print("MQTT connection failed:", reason_code)


def on_message(client, userdata, msg):
    try:
        command = json.loads(msg.payload.decode())

        device = command.get("device", "").lower()
        state = command.get("state", "").upper()

        if device not in devices:
            print("Unknown device:", device)
            return

        if state not in ["ON", "OFF"]:
            print("Invalid device state:", state)
            return

        with lock:
            devices[device] = state

        print(f"{device.upper()} changed to {state}")
        publish_device_status(client)

    except (json.JSONDecodeError, UnicodeDecodeError):
        print("Invalid command received")


client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="smart_home_simulator"
)

client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)
client.loop_start()


def door_input():
    global door_status

    while True:
        try:
            command = input(
                "\nDoor: enter 1=open, 0=closed, q=quit simulator: "
            ).strip().lower()

            if command == "1":
                door_status = 1
                print("Door OPEN")
            elif command == "0":
                door_status = 0
                print("Door CLOSED")
            elif command == "q":
                print("Use Ctrl+C in the main terminal to stop.")
            elif command:
                print("Invalid input")

        except EOFError:
            break


threading.Thread(target=door_input, daemon=True).start()

print("Publishing sensor readings every 3 seconds.")

try:
    while True:
        data = {
            "temperature": round(random.uniform(20, 35), 2),
            "humidity": round(random.uniform(30, 80), 2),
            "light": random.randint(0, 1000),
            "door": door_status,
            "power": round(random.uniform(50, 500), 2),
            "energy": round(random.uniform(0, 10), 2)
        }

        result = client.publish(
            SENSOR_TOPIC,
            json.dumps(data),
            qos=1
        )

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print("Sensor data published:", data)
        else:
            print("Sensor publish failed")

        time.sleep(3)

except KeyboardInterrupt:
    print("\nSimulator stopped.")

finally:
    client.loop_stop()
    client.disconnect()