"""HavenIQ MQTT client (one connection, background thread, auto-reconnect).

It does three jobs and never writes to the sensor database:
  1. Shows the REAL broker connection state (dashboard status pill).
  2. Watches the sensor topic (home/sensors) so the dashboard knows data is arriving.
  3. Device control: subscribes to home/devices/status and publishes commands to
     home/devices/commands.

Written for paho-mqtt 2.x (CallbackAPIVersion.VERSION2) with a fallback for 1.x.
Every callback uses *args so a different signature can not crash the MQTT thread.
"""
import json
import logging
import threading
import time
import uuid

import paho.mqtt.client as mqtt

import config
from device_control import DeviceRegistry

log = logging.getLogger("haveniq.mqtt")


class MQTTMonitor:
    def __init__(self, devices: DeviceRegistry) -> None:
        self.devices = devices
        self._lock = threading.Lock()
        self._client = None
        self._connected = False
        self._last_error = None
        self._last_message_at = None
        self._messages = 0

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    # ---- paho callbacks ----
    def _on_connect(self, client, userdata, flags, rc, *args):
        failed = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
        with self._lock:
            self._connected = not failed
            self._last_error = f"Broker refused the connection ({rc})" if failed else None
        if failed:
            log.warning("MQTT connect failed: %s", rc)
            return
        log.info("MQTT connected to %s:%s", config.MQTT_HOST, config.MQTT_PORT)
        try:  # (re)subscribe on EVERY connect, so reconnects restore the subscriptions
            client.subscribe([(config.MQTT_TOPIC, 0), (config.MQTT_DEVICE_STATUS_TOPIC, 1)])
        except Exception as exc:
            log.warning("MQTT subscribe failed: %s", exc)

    def _on_disconnect(self, client, userdata, *args):
        with self._lock:
            was = self._connected
            self._connected = False
            self._last_error = "Disconnected from the broker (reconnecting automatically)"
        if was:
            log.warning("MQTT disconnected; reconnecting automatically")

    def _on_message(self, client, userdata, msg):
        try:
            if msg.topic == config.MQTT_DEVICE_STATUS_TOPIC:
                self.devices.apply_status(msg.payload)   # combined format {"light": ..}
            else:
                with self._lock:                         # sensor topic: only count it
                    self._messages += 1
                    self._last_message_at = time.time()
        except Exception:
            log.exception("Error while handling an MQTT message")

    # ---- lifecycle ----
    def start(self) -> None:
        if not config.MQTT_ENABLED or self._client is not None:
            return
        try:
            client_id = f"haveniq-{uuid.uuid4().hex[:8]}"
            if hasattr(mqtt, "CallbackAPIVersion"):
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
            else:
                client = mqtt.Client(client_id=client_id)
            if config.MQTT_USERNAME:
                client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD or None)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            client.reconnect_delay_set(min_delay=1, max_delay=15)
            client.connect_async(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
            client.loop_start()  # background thread; keeps retrying if the broker is down
            self._client = client
        except Exception as exc:  # never crash Flask because of MQTT
            with self._lock:
                self._last_error = f"MQTT client could not start: {type(exc).__name__}"
            log.exception("MQTT client could not start")

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass

    # ---- device commands ----
    def send_command(self, device: str, state: str):
        """Publish {"device": .., "state": ..}. Returns (ok, error_message, http_status)."""
        if not config.MQTT_ENABLED:
            return False, "MQTT is disabled (MQTT_ENABLED=false); command not sent", 503
        client = self._client
        if client is None or not self.connected:
            return False, "MQTT broker is not connected; command not sent", 503
        payload = json.dumps({"device": device, "state": state})
        # Register BEFORE publishing: a fast device can answer before publish() returns.
        self.devices.command_sent(device, state)
        try:
            info = client.publish(config.MQTT_DEVICE_COMMAND_TOPIC, payload, qos=1, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self.devices.command_failed(device)
                return False, f"MQTT publish failed (code {info.rc}); command not sent", 502
            info.wait_for_publish(timeout=3)
            if not info.is_published():
                self.devices.command_failed(device)
                return False, "The broker did not acknowledge the command in time", 504
        except (ValueError, RuntimeError, OSError) as exc:
            self.devices.command_failed(device)
            return False, f"MQTT publish failed ({type(exc).__name__}); command not sent", 502
        log.info("DEVICE MQTT COMMAND: %s", payload)
        return True, None, 202

    # ---- status for the API ----
    def snapshot(self) -> dict:
        with self._lock:
            if not config.MQTT_ENABLED:
                state = "disabled"
            else:
                state = "connected" if self._connected else "disconnected"
            age = None if self._last_message_at is None else round(time.time() - self._last_message_at, 1)
            return {
                "state": state,
                "host": config.MQTT_HOST,
                "port": config.MQTT_PORT,
                "topic": config.MQTT_TOPIC,
                "messages_seen": self._messages,
                "last_message_age_seconds": age,
                "error": self._last_error if state != "connected" else None,
            }
