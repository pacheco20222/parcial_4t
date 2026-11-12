import json

from flood_simulator import simulator
from flood_simulator.model import STATIONS
from flood_simulator.runtime import Config


def test_main_publishes_five_identities_and_closes_on_stop(monkeypatch):
    clients = []

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def wait(self, seconds):
            self.stopped = True

    class Client:
        def __init__(self, config, device_id):
            self.device_id = device_id
            self.messages = []
            self.closed = False
            clients.append(self)

        def start(self):
            pass

        def publish(self, destination, payload):
            self.messages.append((destination, payload))
            return True

        def close(self):
            self.closed = True

    monkeypatch.setattr(simulator.Config, "load", lambda: Config(seed=42))
    monkeypatch.setattr(simulator, "stop_event", Stop)
    monkeypatch.setattr(simulator, "DeviceClient", Client)
    assert simulator.main() == 0
    assert len(clients) == 5
    for station, client in zip(STATIONS, clients, strict=True):
        assert client.closed
        destination, payload = client.messages[0]
        assert client.device_id == payload["deviceId"] == station.device_id
        assert destination.endswith(f"/{station.device_id}/telemetry")


def test_config_failure_logs_no_secret_details(monkeypatch, capsys):
    def fail():
        raise ValueError("credential-content-must-never-appear")

    monkeypatch.setattr(simulator.Config, "load", fail)
    assert simulator.main() == 1
    out = capsys.readouterr().out
    assert "credential-content" not in out
    assert json.loads(out.splitlines()[0])["event"] == "simulator.failed"
