
import json
import sqlite3
from pathlib import Path
import paho.mqtt.client as mqtt

# MQTT configuration
BROKER = "localhost"
PORT = 1883
TOPIC = "home/sensors"

# Exact database location
DB_PATH = Path(
    r"C:\Users\Suraj\Desktop\SmartHomeMQTT\smarthome.db"
)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to MQTT broker!")
        client.subscribe(TOPIC)
        print(f"Subscribed to: {TOPIC}")
        print(f"Database: {DB_PATH}")
    else:
        print("Connection failed:", reason_code)


def on_message(client, userdata, message):
    try:
        data = json.loads(message.payload.decode())

        required_fields = [
            "temperature",
            "humidity",
            "light",
            "door",
            "power",
            "energy"
        ]

        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing field: {field}")

        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO sensor_data
                (temperature, humidity, light, door, power, energy)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                data["temperature"],
                data["humidity"],
                data["light"],
                data["door"],
                data["power"],
                data["energy"]
            ))

        print("Data saved successfully:", data)

    except (json.JSONDecodeError, ValueError, KeyError,
            sqlite3.Error) as e:
        print("Error:", e)


client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="smart_home_database"
)

client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(BROKER, PORT, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\nDatabase writer stopped.")
    client.disconnect()
except Exception as e:
    print("MQTT connection error:", e)