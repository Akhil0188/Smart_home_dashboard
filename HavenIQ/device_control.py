"""Device state handling for HavenIQ (Light / Fan / AC).

Pure Python, no MQTT code here. The MQTT client (mqtt_monitor.py) feeds status messages in,
and the Flask routes read snapshots out.

Two DIFFERENT JSON formats are used (keep them separate!):
  COMMAND  topic home/devices/commands : {"device": "light", "state": "ON"}
  STATUS   topic home/devices/status   : {"light": "ON", "fan": "OFF", "ac": "OFF"}

A device is UNKNOWN until a real status message has been received. The dashboard never
assumes a command worked; only a status message from the device changes a state.
"""
import json
import logging
import threading
import time

log = logging.getLogger("haveniq.devices")

DEVICES = ("light", "fan", "ac")
STATES = ("ON", "OFF")


class DeviceRegistry:
    def __init__(self, command_timeout: float, stale_after: float) -> None:
        self._lock = threading.Lock()
        self._command_timeout = command_timeout
        self._stale_after = stale_after
        self._states = {d: "UNKNOWN" for d in DEVICES}
        self._updated_at = None      # time of the last VALID status message
        self._status_error = None    # problem with the last status message, if any
        self._pending = {}           # device -> {"state": "ON", "sent_at": float}

    # ------------------------------------------------------------ status in
    def apply_status(self, payload) -> bool:
        """Parse a message from home/devices/status. Returns True if it was valid."""
        try:
            text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
            data = json.loads(text)
        except (UnicodeDecodeError, ValueError):
            return self._reject("Malformed device status (not valid JSON) was ignored")
        if not isinstance(data, dict):
            return self._reject("Device status must be a JSON object like {\"light\": \"ON\", \"fan\": \"OFF\", \"ac\": \"OFF\"}")
        if "device" in data and "state" in data and not any(d in data for d in DEVICES):
            return self._reject("A command-format message was received on the status topic and ignored")

        updates, problems = {}, []
        for dev in DEVICES:
            if dev in data:
                value = data[dev]
                if isinstance(value, str) and value.strip().upper() in STATES:
                    updates[dev] = value.strip().upper()
                else:
                    problems.append(f"invalid value for {dev}")
        if not updates:
            return self._reject("Device status has no valid light / fan / ac fields")

        with self._lock:
            changed = any(self._states[d] != s for d, s in updates.items()) or self._updated_at is None
            self._states.update(updates)
            self._updated_at = time.time()
            self._status_error = ("Partly invalid status: " + ", ".join(problems)) if problems else None
            for dev, state in updates.items():  # a matching status confirms the command
                pend = self._pending.get(dev)
                if pend and pend["state"] == state:
                    del self._pending[dev]
        compact = json.dumps(data, separators=(",", ":"))
        if changed:
            log.info("DEVICE MQTT STATUS: %s", compact)
        else:
            log.debug("DEVICE MQTT STATUS (unchanged): %s", compact)
        return True

    def _reject(self, message: str) -> bool:
        with self._lock:
            self._status_error = message
        log.warning("DEVICE MQTT STATUS rejected: %s", message)
        return False

    # ----------------------------------------------------------- commands out
    def command_sent(self, device: str, state: str) -> None:
        with self._lock:
            self._pending[device] = {"state": state, "sent_at": time.time()}

    def command_failed(self, device: str) -> None:
        with self._lock:
            self._pending.pop(device, None)

    # --------------------------------------------------------------- readout
    def snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            pending = {}
            for dev, p in self._pending.items():
                age = now - p["sent_at"]
                pending[dev] = {"requested": p["state"], "age_seconds": round(age, 1),
                                "timed_out": age > self._command_timeout}
            age = None if self._updated_at is None else round(now - self._updated_at, 1)
            return {
                "devices": dict(self._states),
                "pending": pending,
                "status_received": self._updated_at is not None,
                "status_age_seconds": age,
                "status_stale": age is not None and age > self._stale_after,
                "status_error": self._status_error,
            }
