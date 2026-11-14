"""Offline demo scheduling, HTTP boundaries and interruption checks."""

import json
import signal
import threading
from datetime import datetime
from http.client import HTTPException
from unittest.mock import MagicMock

import pytest

from flood_simulator import attack_sim
from flood_simulator.runtime import Config, stop_event


@pytest.mark.parametrize("status,count,success", [(401, 10, True), (429, 1, False),
                                                  (403, 1, False), (200, 1, False)])
def test_login_failures_fixed_target_and_bounded(monkeypatch, capsys, status, count, success):
    connection = MagicMock()
    connection.getresponse.return_value.status = status
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr(attack_sim, "HTTPConnection", factory)
    monkeypatch.setattr(attack_sim.secrets, "token_urlsafe", lambda _: "wrong-test-only")
    stop = MagicMock()
    stop.is_set.return_value = False
    stop.wait.return_value = False
    assert attack_sim.run_scenario("login_failures", Config(), stop) is success
    assert factory.call_count == count
    factory.assert_called_with("ops-service", 8080, timeout=5)
    assert connection.close.call_count == count
    assert connection.getresponse.return_value.close.call_count == count
    for call in connection.request.call_args_list:
        assert call.args == ("POST", "/auth/login")
        assert json.loads(call.kwargs["body"]) == {
            "email": "intruso@example.invalid", "password": "wrong-test-only",
        }
        assert call.kwargs["headers"] == {
            "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest",
        }
    assert stop.wait.call_count == (9 if success else 0)
    if success:
        stop.wait.assert_called_with(3)
    output = capsys.readouterr().out
    assert "wrong-test-only" not in output
    assert "intruso@example.invalid" not in output
    assert all(json.loads(line)["service"] == "attack-sim" for line in output.splitlines())


@pytest.mark.parametrize("error", [OSError("private-test-only"), HTTPException("private-test-only")])
def test_login_failure_transport_cleanup(monkeypatch, capsys, error):
    connection = MagicMock()
    connection.getresponse.side_effect = error
    monkeypatch.setattr(attack_sim, "HTTPConnection", lambda *a, **kw: connection)
    assert not attack_sim.login_failures(threading.Event())
    connection.close.assert_called_once()
    assert "private-test-only" not in capsys.readouterr().out


def test_login_failure_stop_before_or_between_requests(monkeypatch):
    factory = MagicMock()
    factory.return_value.getresponse.return_value.status = 401
    monkeypatch.setattr(attack_sim, "HTTPConnection", factory)
    stopped = threading.Event()
    stopped.set()
    assert not attack_sim.login_failures(stopped)
    factory.assert_not_called()
    stop = MagicMock()
    stop.is_set.return_value = False
    stop.wait.return_value = True
    assert not attack_sim.login_failures(stop)
    assert factory.call_count == 1


@pytest.mark.parametrize("value", ["4.99", "0", "-5", "nan", "inf", "no", "1e308"])
def test_scheduler_invalid_interval(value):
    with pytest.raises(ValueError):
        attack_sim.schedule_interval({"ATTACK_INTERVAL_MINUTES": value})


def test_scheduler_default_and_minimum_interval():
    assert attack_sim.schedule_interval({}) == 720
    assert attack_sim.schedule_interval({"ATTACK_INTERVAL_MINUTES": "5"}) == 300


@pytest.mark.parametrize("jitter", [0.7, 1.3])
def test_scheduler_jitter_weights_and_failure_survival(monkeypatch, capsys, jitter):
    stop = MagicMock()
    stop.wait.side_effect = [False, False, False, True]
    stop.is_set.return_value = False
    rng = MagicMock()
    rng.uniform.return_value = jitter
    rng.choices.return_value = ["spoof"]
    run = MagicMock(side_effect=[RuntimeError("secret-test-only"), False, True])
    monkeypatch.setattr(attack_sim, "run_scenario", run)
    config = Config()
    attack_sim.run_schedule(config, stop, 720, rng)
    assert run.call_count == 3
    run.assert_called_with("spoof", config, stop)
    assert all(call.args == (720 * jitter,) for call in stop.wait.call_args_list)
    rng.uniform.assert_called_with(0.7, 1.3)
    rng.choices.assert_called_with(attack_sim.SCENARIOS, weights=attack_sim.SCHEDULE_WEIGHTS, k=1)
    weights = dict(zip(attack_sim.SCENARIOS, attack_sim.SCHEDULE_WEIGHTS, strict=True))
    assert weights["flood"] < min(v for k, v in weights.items() if k != "flood")
    output = capsys.readouterr().out
    assert "secret-test-only" not in output
    events = [json.loads(line) for line in output.splitlines()]
    assert len([e for e in events if e["event"] == "attack.scheduled_run"]) == 3
    assert len([e for e in events if e["event"] == "attack.scenario_failed"]) == 2


@pytest.mark.parametrize("argv,env", [(["--schedule"], "off"), ([], "on")])
def test_schedule_entrypoints(monkeypatch, argv, env):
    monkeypatch.setenv("ATTACK_SIM_CONFIRM", "lab")
    monkeypatch.setenv("ATTACK_SCHEDULE", env)
    monkeypatch.delenv("ATTACK_INTERVAL_MINUTES", raising=False)
    monkeypatch.setattr(attack_sim.Config, "load", lambda: Config())
    monkeypatch.setattr(attack_sim, "stop_event", threading.Event)
    run = MagicMock()
    monkeypatch.setattr(attack_sim, "run_schedule", run)
    assert attack_sim.main(argv) == 0
    assert run.call_args.args[2] == 720


def test_scheduler_requires_guard_before_credentials(monkeypatch):
    monkeypatch.delenv("ATTACK_SIM_CONFIRM", raising=False)
    monkeypatch.setattr(attack_sim.Config, "load", lambda: pytest.fail("read secrets"))
    assert attack_sim.main(["--schedule"]) == 1


def test_sigterm_interrupts_scheduler_wait(monkeypatch):
    handlers = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.update({sig: handler}))
    stop = stop_event()
    handlers[signal.SIGTERM](signal.SIGTERM, None)
    monkeypatch.setattr(attack_sim, "run_scenario", lambda *a: pytest.fail("ran after SIGTERM"))
    attack_sim.run_schedule(Config(), stop, 720, MagicMock())


def test_jump_cancelled_wait_closes_client(monkeypatch):
    client = MagicMock(accepted=True)
    monkeypatch.setattr(attack_sim, "DeviceClient", lambda *a, **kw: client)
    monkeypatch.setattr(attack_sim, "wait_response", lambda *a: True)
    stop = MagicMock()
    stop.is_set.return_value = False
    stop.wait.return_value = True
    assert not attack_sim.run_scenario("implausible_jump", Config(), stop)
    assert client.publish.call_count == 1
    client.close.assert_called_once()
    payload = client.publish.call_args.args[1]
    elapsed = datetime.now().astimezone() - datetime.fromisoformat(payload["capturedAt"])
    assert abs(elapsed.total_seconds()) < 5
