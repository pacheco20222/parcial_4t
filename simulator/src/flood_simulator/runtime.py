"""Configuration, safe JSON logging and TLS MQTT transport."""

import json
import math
import os
import signal
import socket
import ssl
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import paho.mqtt.client as mqtt

from .model import SCENARIOS, STATIONS


def log(event: str, *, level: str = "INFO", service: str = "simulator", **context) -> None:
    print(json.dumps({
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "level": level, "service": service, "event": event, **context,
    }, allow_nan=False), flush=True)


@dataclass(frozen=True)
class Config:
    host: str = "mosquitto"
    port: int = 8883
    ca_file: str = "/run/secrets/ca.crt"
    devices_file: str = "/run/secrets/mqtt_devices.json"
    scenario: str = "cycle"
    interval: float = 60
    seed: int | None = None
    passwords: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls) -> "Config":
        host = os.getenv("MQTT_HOST", "mosquitto")
        port = int(os.getenv("MQTT_PORT", "8883"))
        interval = float(os.getenv("INTERVAL_SECONDS", "60"))
        scenario = os.getenv("SCENARIO", "cycle")
        if host != "mosquitto" or not 1 <= port <= 65535:
            raise ValueError("broker must use TLS hostname mosquitto and a valid port")
        if not math.isfinite(interval) or interval < 1:
            raise ValueError("INTERVAL_SECONDS must be finite and at least 1")
        if scenario not in SCENARIOS:
            raise ValueError("unknown SCENARIO")
        ca = os.getenv("MQTT_CA_FILE", "/run/secrets/ca.crt")
        devices = os.getenv("MQTT_DEVICES_FILE", "/run/secrets/mqtt_devices.json")
        passwords = json.loads(Path(devices).read_text())
        if not isinstance(passwords, dict) or any(
            not isinstance(passwords.get(s.device_id), str) or not passwords[s.device_id]
            for s in STATIONS
        ):
            raise ValueError("device credentials missing or invalid")
        seed = os.getenv("SEED")
        return cls(host, port, ca, devices, scenario, interval,
                   int(seed) if seed is not None else None, passwords)


def stop_event() -> threading.Event:
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    return stop


class RoutedClient(mqtt.Client):
    """Override TCP destination only; Paho retains its TLS hostname and checks."""

    def __init__(self, *args, connect_host: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.connect_host = connect_host

    def _create_socket_connection(self):
        # Paho has no public option separating TCP destination from TLS SNI.
        return socket.create_connection(
            (self.connect_host, self.port), timeout=self.connect_timeout,
        )


class DeviceClient:
    def __init__(self, config: Config, device_id: str, *, password: str | None = None,
                 reconnect: bool = True, connect_host: str | None = None):
        self.config = config
        self.device_id = device_id
        self.connected = threading.Event()
        self.responded = threading.Event()
        self.accepted = False
        self.service = "simulator" if reconnect else "attack-sim"
        client_class = mqtt.Client if connect_host is None else RoutedClient
        route = {} if connect_host is None else {"connect_host": connect_host}
        self.client = client_class(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"sim-{device_id}-{uuid4().hex[:10]}",
            protocol=mqtt.MQTTv5, reconnect_on_failure=reconnect,
            **route,
        )
        self.client.username_pw_set(
            device_id, config.passwords[device_id] if password is None else password,
        )
        context = ssl.create_default_context(cafile=config.ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.client.tls_set_context(context)
        self.client.tls_insecure_set(False)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.connect_timeout = 5
        self.client.max_queued_messages_set(50)
        self.client.max_inflight_messages_set(10)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        self.accepted = not reason_code.is_failure
        if self.accepted:
            self.connected.set()
        self.responded.set()
        log("mqtt.connected" if self.accepted else "mqtt.rejected",
            service=self.service, device_id=self.device_id)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected.clear()
        log("mqtt.disconnected", service=self.service, device_id=self.device_id)

    def _on_publish(self, client, userdata, mid, reason_code, properties):
        log("mqtt.publish_denied" if reason_code.is_failure else "mqtt.acknowledged",
            service=self.service, device_id=self.device_id, status=reason_code.value)

    def start(self) -> None:
        self.client.connect_async(self.config.host, self.config.port, keepalive=30)
        self.client.loop_start()

    def publish(self, destination: str, payload: dict, *, timeout: float = 3) -> bool:
        if not self.connected.is_set():
            log("mqtt.offline", level="WARNING", service=self.service, device_id=self.device_id)
            return False
        info = self.client.publish(destination, json.dumps(payload, allow_nan=False), qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log("mqtt.publish_failed", level="WARNING", service=self.service,
                device_id=self.device_id)
            return False
        try:
            info.wait_for_publish(timeout=timeout)
            if info.is_published():
                return True
            log("mqtt.publish_timeout", level="WARNING", service=self.service,
                device_id=self.device_id)
        except (ValueError, RuntimeError):
            log("mqtt.publish_failed", level="WARNING", service=self.service,
                device_id=self.device_id)
        return False

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()
