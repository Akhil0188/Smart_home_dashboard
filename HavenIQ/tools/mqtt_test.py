"""Small MQTT helper so you do not have to fight PowerShell quoting.

  python tools\mqtt_test.py watch                      # print every device message
  python tools\mqtt_test.py command light ON           # publish a COMMAND message
  python tools\mqtt_test.py status light=ON fan=OFF ac=OFF   # pretend to be the device
"""
import json
import sys
import time

import paho.mqtt.client as mqtt

HOST, PORT = "localhost", 1883
COMMANDS, STATUS = "home/devices/commands", "home/devices/status"


def client(on_message=None):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"haveniq-test-{int(time.time())}")
    if on_message:
        c.on_message = on_message
    c.connect(HOST, PORT, 30)
    return c


def main(argv):
    if not argv:
        print(__doc__); return 1
    mode = argv[0]
    if mode == "watch":
        c = client(lambda cl, ud, m: print(f"{m.topic}  {m.payload.decode(errors='replace')}  (retained={bool(m.retain)})"))
        c.subscribe([(COMMANDS, 1), (STATUS, 1)])
        print(f"Watching {COMMANDS} and {STATUS}  (Ctrl+C to stop)")
        try:
            c.loop_forever()
        except KeyboardInterrupt:
            pass
    elif mode == "command" and len(argv) == 3:
        c = client(); c.loop_start()
        payload = json.dumps({"device": argv[1].lower(), "state": argv[2].upper()})
        c.publish(COMMANDS, payload, qos=1).wait_for_publish(timeout=3)
        print("published to", COMMANDS, payload); c.loop_stop()
    elif mode == "status" and len(argv) >= 2:
        states = dict(a.split("=", 1) for a in argv[1:])
        c = client(); c.loop_start()
        payload = json.dumps({k.lower(): v.upper() for k, v in states.items()})
        c.publish(STATUS, payload, qos=1, retain=True).wait_for_publish(timeout=3)
        print("published (retained) to", STATUS, payload); c.loop_stop()
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
