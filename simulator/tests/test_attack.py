import json
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from flood_simulator import attack_sim
from flood_simulator.model import STATIONS, topic
from flood_simulator.runtime import Config


@pytest.mark.parametrize("env", [
    {}, {"ATTACK_SIM_CONFIRM": "yes"},
    {"ATTACK_SIM_CONFIRM": "lab", "MQTT_HOST": "example.com"},
    {"ATTACK_SIM_CONFIRM": "lab", "ATTACK_SCENARIO": "unknown"},
    {"ATTACK_SIM_CONFIRM": "lab", "ATTACK_IDMZ_BROKER_HOST": "example.com"},
    {"ATTACK_SIM_CONFIRM": "lab", "ATTACK_IDMZ_BROKER_HOST": "172.30.10.10"},
    {"ATTACK_SIM_CONFIRM": "lab", "ATTACK_IDMZ_BROKER_HOST": "172.30.20.0"},
    {"ATTACK_SIM_CONFIRM": "lab", "ATTACK_IDMZ_BROKER_HOST": "172.30.20.255"},
])
def test_attack_guard(env):
    with pytest.raises(ValueError):
        attack_sim.require_lab(env)


def test_refusal_before_any_credentials_or_network(monkeypatch, capsys):
    monkeypatch.delenv("ATTACK_SIM_CONFIRM", raising=False)
    monkeypatch.setattr(attack_sim.Config, "load", lambda: pytest.fail("read secrets"))
    assert attack_sim.main() == 1
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "LAB ONLY" in lines[0]["banner"]
    assert lines[-1]["event"] == "attack.refused_or_failed"


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now

    def wait(self, seconds):
        self.now += seconds
        return False

    def is_set(self):
        return False


@pytest.mark.parametrize("scenario,count", [
    ("bruteforce", 8), ("acl_violation", 1), ("flood", 1), ("spoof", 1),
    ("foreign_network", 1), ("implausible_jump", 1),
])
def test_bounded_attack_scenarios(monkeypatch, scenario, count):
    clients = []
    clock = Clock()
    monkeypatch.delenv("ATTACK_IDMZ_BROKER_HOST", raising=False)
    if scenario == "implausible_jump":
        started = datetime.now(UTC)
        monkeypatch.setattr(attack_sim, "datetime", SimpleNamespace(
            now=lambda tz: started + timedelta(seconds=clock.now),
        ))

    class FakeClient:
        def __init__(self, config, device_id, *, password, reconnect, connect_host=None):
            self.device_id = device_id
            self.password = password
            self.connect_host = connect_host
            assert not reconnect
            self.accepted = password is None
            self.messages = []
            self.closed = False
            clients.append(self)

        def start(self):
            pass

        def publish(self, destination, payload, **kwargs):
            self.messages.append((destination, payload, clock.now))
            return True

        def close(self):
            self.closed = True

    monkeypatch.setattr(attack_sim, "DeviceClient", FakeClient)
    monkeypatch.setattr(attack_sim, "wait_response", lambda *args: True)
    monkeypatch.setattr(attack_sim.time, "monotonic", clock.monotonic)
    config = Config(passwords={s.device_id: "test-only" for s in STATIONS})
    assert attack_sim.run_scenario(scenario, config, clock)
    assert len(clients) == count
    assert all(c.closed for c in clients)
    if scenario == "foreign_network":
        client = clients[0]
        assert client.device_id == "DEV-P03-A"
        assert client.password is None
        assert client.connect_host == "172.30.20.10"
        assert len(client.messages) == 1
        destination, payload, _ = client.messages[0]
        assert destination == topic(STATIONS[2])
        assert payload["deviceId"] == "DEV-P03-A"
        assert payload["pointId"] == "P03"
    else:
        assert all(c.connect_host is None for c in clients)
    if scenario == "bruteforce":
        assert all(c.device_id == "DEV-P01-A" and c.password != "test-only" for c in clients)
        assert clock.now < 60
    if scenario == "acl_violation":
        assert clients[0].device_id == "DEV-P02-A"
        assert [m[0] for m in clients[0].messages] == [
            topic(STATIONS[0]), "merida/flood/P01/DEV-P01-A/command",
        ]
    if scenario == "spoof":
        destination, payload, _ = clients[0].messages[0]
        assert destination == topic(STATIONS[0])
        assert payload["deviceId"] == "DEV-P02-A"
        assert payload["pointId"] == "P02"
    if scenario == "flood":
        assert len(clients[0].messages) == 30
        assert clients[0].messages[-1][2] < 10
        assert all(m[0] == topic(STATIONS[0]) for m in clients[0].messages)
    if scenario == "implausible_jump":
        client = clients[0]
        assert client.device_id == "DEV-P04-A"
        assert client.password is None
        assert [m[0] for m in client.messages] == [topic(STATIONS[3])] * 2
        assert [m[1]["waterDepthCm"] for m in client.messages] == [5.0, 151.0]
        assert [m[2] for m in client.messages] == [0, 20]
        assert client.messages[0][1]["messageId"] != client.messages[1][1]["messageId"]
        assert all(m[1]["deviceId"] == client.device_id for m in client.messages)
        timestamps = [datetime.fromisoformat(m[1]["capturedAt"]) for m in client.messages]
        assert (timestamps[1] - timestamps[0]).total_seconds() == 20


def test_stopped_attack_opens_no_connection(monkeypatch):
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(attack_sim, "DeviceClient", lambda *a, **kw: pytest.fail("connected"))
    assert not attack_sim.run_scenario("flood", Config(), stop)


def test_connection_timeout_is_bounded(monkeypatch):
    from types import SimpleNamespace

    clock = Clock()

    class NoResponse:
        def wait(self, seconds):
            clock.now += seconds
            return False

    monkeypatch.setattr(attack_sim.time, "monotonic", clock.monotonic)
    assert not attack_sim.wait_response(SimpleNamespace(responded=NoResponse()), clock)
    assert clock.now == pytest.approx(8)


def test_idmz_broker_host_override():
    assert attack_sim.idmz_broker_host({"ATTACK_IDMZ_BROKER_HOST": "172.30.20.11"}) == "172.30.20.11"


def test_all_includes_foreign_network(monkeypatch):
    monkeypatch.setenv("ATTACK_SIM_CONFIRM", "lab")
    monkeypatch.setenv("ATTACK_SCENARIO", "all")
    monkeypatch.delenv("ATTACK_IDMZ_BROKER_HOST", raising=False)
    monkeypatch.setattr(attack_sim.Config, "load", lambda: Config())
    monkeypatch.setattr(attack_sim, "stop_event", threading.Event)
    names = []
    monkeypatch.setattr(attack_sim, "run_scenario", lambda name, *_: names.append(name) or True)
    assert attack_sim.main() == 0
    assert names == ["bruteforce", "acl_violation", "flood", "spoof", "foreign_network",
                     "implausible_jump"]


@pytest.mark.parametrize("accepted,published", [(False, True), (True, False)])
def test_foreign_network_failure_closes_client(monkeypatch, accepted, published):
    from unittest.mock import MagicMock

    client = MagicMock(accepted=accepted)
    client.publish.return_value = published
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(attack_sim, "DeviceClient", factory)
    monkeypatch.setattr(attack_sim, "wait_response", lambda *_: True)
    monkeypatch.setenv("ATTACK_IDMZ_BROKER_HOST", "172.30.20.11")
    config = Config()
    assert not attack_sim.run_scenario("foreign_network", config, threading.Event())
    factory.assert_called_once_with(
        config, "DEV-P03-A", password=None, reconnect=False, connect_host="172.30.20.11",
    )
    client.close.assert_called_once()
    assert client.publish.call_count == int(accepted)
