import json
import ssl
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from flood_simulator.model import STATIONS
from flood_simulator.runtime import Config, DeviceClient, log


@pytest.fixture
def credentials(tmp_path, monkeypatch):
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({s.device_id: f"test-only-{s.point_id}" for s in STATIONS}))
    monkeypatch.setenv("MQTT_DEVICES_FILE", str(path))
    for key in ("MQTT_HOST", "MQTT_PORT", "SCENARIO", "INTERVAL_SECONDS", "SEED"):
        monkeypatch.delenv(key, raising=False)
    return path


def test_config_defaults_and_seed(credentials, monkeypatch):
    config = Config.load()
    assert (config.host, config.port, config.scenario, config.interval) == (
        "mosquitto", 8883, "cycle", 60,
    )
    assert config.ca_file == "/run/secrets/ca.crt"
    assert "test-only" not in repr(config)
    monkeypatch.setenv("SEED", "42")
    assert Config.load().seed == 42


@pytest.mark.parametrize("key,value", [
    ("MQTT_HOST", "example.com"), ("MQTT_PORT", "0"), ("SCENARIO", "unknown"),
    ("INTERVAL_SECONDS", "0.9"), ("INTERVAL_SECONDS", "nan"), ("INTERVAL_SECONDS", "inf"),
])
def test_invalid_config(credentials, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        Config.load()


@pytest.mark.parametrize("data", [{}, [], {"DEV-P01-A": None}])
def test_missing_credentials_rejected(credentials, data):
    credentials.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        Config.load()


def test_json_logging(capsys):
    log("simulator.started", point_id="P01")
    data = json.loads(capsys.readouterr().out)
    assert {"ts", "level", "service", "event"} <= data.keys()
    assert data["ts"].endswith("Z")
    assert data["service"] == "simulator"


def test_device_identity_tls_qos_and_reconnect(credentials, monkeypatch):
    mqtt_client = MagicMock()
    factory = MagicMock(return_value=mqtt_client)
    context = ssl.create_default_context()
    monkeypatch.setattr("flood_simulator.runtime.mqtt.Client", factory)
    monkeypatch.setattr("flood_simulator.runtime.ssl.create_default_context",
                        lambda **kwargs: context)
    config = Config.load()
    devices = [DeviceClient(config, s.device_id) for s in STATIONS]
    assert factory.call_count == 5
    assert len({call.kwargs["client_id"] for call in factory.call_args_list}) == 5
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert mqtt_client.username_pw_set.call_count == 5
    mqtt_client.reconnect_delay_set.assert_called_with(min_delay=1, max_delay=30)
    mqtt_client.tls_insecure_set.assert_called_with(False)
    device = devices[0]
    device.start()
    mqtt_client.connect_async.assert_called_with("mosquitto", 8883, keepalive=30)
    assert not device.publish("topic", {})
    device._on_connect(None, None, None, SimpleNamespace(is_failure=False), None)
    info = MagicMock(rc=0)
    info.is_published.return_value = True
    mqtt_client.publish.return_value = info
    assert device.publish("merida/flood/P01/DEV-P01-A/telemetry", {"pointId": "P01"})
    assert mqtt_client.publish.call_args.kwargs == {"qos": 1}
    device._on_disconnect(None, None, None, None, None)
    assert not device.connected.is_set()
    device.close()
    mqtt_client.disconnect.assert_called_once()
    mqtt_client.loop_stop.assert_called_once()


def test_sigterm_and_sigint_request_stop(monkeypatch):
    import signal

    from flood_simulator.runtime import stop_event

    handlers = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.update({sig: handler}))
    stop = stop_event()
    assert not stop.is_set()
    handlers[signal.SIGTERM](signal.SIGTERM, None)
    assert stop.is_set()
    stop.clear()
    handlers[signal.SIGINT](signal.SIGINT, None)
    assert stop.is_set()


def test_publish_timeout_is_visible_and_contains_no_payload(monkeypatch, capsys):
    import threading

    client = DeviceClient.__new__(DeviceClient)
    client.connected = threading.Event()
    client.connected.set()
    client.device_id = "DEV-P01-A"
    client.service = "simulator"
    client.client = MagicMock()
    info = MagicMock(rc=0)
    info.is_published.return_value = False
    client.client.publish.return_value = info
    assert not client.publish("topic", {"private": "must-not-appear"}, timeout=0.2)
    info.wait_for_publish.assert_called_with(timeout=0.2)
    output = capsys.readouterr().out
    assert "must-not-appear" not in output
    assert json.loads(output)["event"] == "mqtt.publish_timeout"


def test_routed_client_connects_to_ip_but_verifies_mosquitto(monkeypatch):
    from flood_simulator.runtime import RoutedClient

    tcp_socket = MagicMock()
    tls_socket = MagicMock()
    context = ssl.create_default_context()
    create_connection = MagicMock(return_value=tcp_socket)
    wrap_socket = MagicMock(return_value=tls_socket)
    monkeypatch.setattr("flood_simulator.runtime.socket.create_connection", create_connection)
    monkeypatch.setattr("flood_simulator.runtime.ssl.create_default_context", lambda **_: context)
    monkeypatch.setattr(context, "wrap_socket", wrap_socket)
    config = Config(passwords={"DEV-P03-A": "test-only"})
    device = DeviceClient(config, "DEV-P03-A", reconnect=False, connect_host="172.30.20.10")
    assert isinstance(device.client, RoutedClient)
    # Use installed Paho's real socket/TLS path, with only network I/O mocked.
    device.client.connect_async("mosquitto", 8883, keepalive=30)
    assert device.client._create_socket() is tls_socket
    create_connection.assert_called_once_with(("172.30.20.10", 8883), timeout=5)
    wrap_socket.assert_called_once_with(
        tcp_socket, server_hostname="mosquitto", do_handshake_on_connect=False,
    )
    tls_socket.do_handshake.assert_called_once()
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert not device.client._tls_insecure
    wrap_socket.side_effect = ssl.SSLCertVerificationError("untrusted certificate")
    with pytest.raises(ssl.SSLCertVerificationError):
        device.client._create_socket()
