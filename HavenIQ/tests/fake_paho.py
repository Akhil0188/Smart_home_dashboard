"""In-memory stand-in for paho-mqtt 2.x + a Mosquitto-like broker, used ONLY by the offline test.

It follows the paho 2.x callback signatures (VERSION2), delivers retained messages on subscribe,
re-runs on_connect after a reconnect, and can simulate a broker outage or publish failures.
It is not a replacement for a real broker test (see README, "Testing without hardware").
"""
import sys
import threading
import types

MQTT_ERR_SUCCESS, MQTT_ERR_NO_CONN = 0, 4


class _RC:                      # looks like paho 2.x ReasonCode
    def __init__(self, value=0): self.value = value
    @property
    def is_failure(self): return self.value >= 128
    def __eq__(self, other): return self.value == other
    def __repr__(self): return f"Success" if self.value == 0 else f"Error {self.value}"


class _Msg:
    def __init__(self, topic, payload, retain, qos):
        self.topic, self.payload, self.retain, self.qos = topic, payload, retain, qos


class _Info:
    def __init__(self, rc, published=True): self.rc, self._pub = rc, published
    def wait_for_publish(self, timeout=None): return None
    def is_published(self): return self._pub


class Broker:
    def __init__(self):
        self.up, self.clients, self.retained = True, [], {}
        self.fail_publish, self.no_ack, self.log = False, False, []
        self._lock = threading.RLock()

    def go_down(self):
        self.up = False
        for c in list(self.clients):
            if c._connected:
                c._connected = False; c._subs = []
                if c.on_disconnect: c.on_disconnect(c, None, None, _RC(0), None)

    def go_up(self):
        self.up = True
        for c in list(self.clients):
            if c._looping and not c._connected:
                c._do_connect()

    def deliver(self, topic, payload, retain, qos, sender):
        self.log.append((topic, payload, retain))
        if retain:
            self.retained[topic] = payload
        for c in list(self.clients):
            if c._connected and any(t == topic for t, _ in c._subs) and c.on_message:
                c.on_message(c, None, _Msg(topic, payload, retain, qos))


BROKER = Broker()


class Client:
    def __init__(self, *args, callback_api_version=None, client_id="", **kw):
        self.client_id = client_id
        self.on_connect = self.on_disconnect = self.on_message = None
        self._connected = self._looping = False
        self._subs = []
        BROKER.clients.append(self)

    def username_pw_set(self, *a, **k): pass
    def reconnect_delay_set(self, *a, **k): pass
    def connect_async(self, *a, **k): pass
    def connect(self, *a, **k): pass
    def is_connected(self): return self._connected
    def disconnect(self): self._connected = False; self._looping = False
    def loop_stop(self): self._looping = False

    def loop_start(self):
        self._looping = True
        if BROKER.up:
            self._do_connect()

    def _do_connect(self):
        self._connected = True
        if self.on_connect:
            self.on_connect(self, None, {}, _RC(0), None)

    def subscribe(self, topic, qos=0):
        items = topic if isinstance(topic, list) else [(topic, qos)]
        self._subs += items
        for t, _ in items:                              # retained messages arrive on subscribe
            if t in BROKER.retained and self.on_message:
                self.on_message(self, None, _Msg(t, BROKER.retained[t], True, 1))
        return (0, 1)

    def publish(self, topic, payload=None, qos=0, retain=False):
        if not self._connected or not BROKER.up:
            return _Info(MQTT_ERR_NO_CONN, False)
        if BROKER.fail_publish:
            return _Info(1, False)
        BROKER.deliver(topic, payload.encode() if isinstance(payload, str) else payload, retain, qos, self)
        return _Info(MQTT_ERR_SUCCESS, not BROKER.no_ack)


def install():
    paho = types.ModuleType("paho"); mqtt = types.ModuleType("paho.mqtt"); client = types.ModuleType("paho.mqtt.client")
    client.Client = Client
    client.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
    client.MQTT_ERR_SUCCESS, client.MQTT_ERR_NO_CONN = MQTT_ERR_SUCCESS, MQTT_ERR_NO_CONN
    paho.mqtt, mqtt.client = mqtt, client
    sys.modules.update({"paho": paho, "paho.mqtt": mqtt, "paho.mqtt.client": client})
    return client
