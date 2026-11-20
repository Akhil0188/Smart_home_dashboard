import paho.mqtt.client as mqtt
import json

client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="test_controller"
)

client.connect("localhost", 1883, 60)

client.publish(
    "home/devices/commands",
    json.dumps({"device": "light", "state": "ON"}),
    qos=1
)

print("Light ON command sent!")

client.disconnect()