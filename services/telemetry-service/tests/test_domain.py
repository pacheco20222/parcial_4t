from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from telemetry_service.domain import Payload, Status, StatusMachine, Thresholds, quality

NOW = datetime.now(UTC)


def message(**changes):
    return {
        "messageId": str(uuid4()),
        "pointId": "P01",
        "deviceId": "DEV-P01-A",
        "capturedAt": NOW.isoformat(),
        "waterDepthCm": 12,
        "rainMm5min": None,
        "batteryPct": 90,
        "fwVersion": "1.0.0",
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"messageId": "bad"},
        {"pointId": "../"},
        {"deviceId": "bad"},
        {"batteryPct": 101},
        {"batteryPct": 1.5},
        {"batteryPct": True},
        {"capturedAt": "2026-01-01T00:00:00"},
        {"capturedAt": "2026-01-01T00:00:00+01:00"},
        {"waterDepthCm": float("nan")},
        {"waterDepthCm": True},
        {"rainMm5min": "12"},
        {"rainMm5min": float("inf")},
        {"fwVersion": ""},
        {"extra": "no"},
        {"capturedAt": (NOW + timedelta(hours=1)).isoformat()},
    ],
)
def test_payload_rejects(changes):
    with pytest.raises(ValidationError):
        Payload.model_validate(message(**changes))


def test_missing_values_preserved():
    payload = Payload.model_validate(message(waterDepthCm=None))
    assert payload.water_depth_cm is None and payload.rain_mm5min is None
    assert quality(payload, now=NOW) == "ok"


@pytest.mark.parametrize(
    "depth,rain,expected",
    [(0, 0, "ok"), (150, 100, "ok"), (-1, 0, "suspect"), (151, 0, "suspect"), (1, -1, "suspect"), (1, 101, "suspect")],
)
def test_range_quality(depth, rain, expected):
    assert quality(Payload.model_validate(message(waterDepthCm=depth, rainMm5min=rain)), now=NOW) == expected


def test_jump_rate_and_stale_quality():
    payload = Payload.model_validate(message(waterDepthCm=41))
    assert quality(payload, (NOW - timedelta(minutes=1), 10), now=NOW) == "suspect"
    assert quality(payload, (NOW - timedelta(minutes=1), 11), now=NOW) == "ok"
    assert quality(payload, (NOW - timedelta(minutes=2), 0), now=NOW) == "ok"
    assert quality(payload, rate_exceeded=True, now=NOW) == "suspect"
    assert quality(payload, now=NOW + timedelta(minutes=3)) == "suspect"
    assert quality(payload, (NOW, 41), now=NOW) == "suspect"


def observe(state, depth, minute, suspect=False):
    return state.observe(depth, NOW + timedelta(minutes=minute), 15, 25, suspect)


def test_escalation_boundaries():
    state = StatusMachine()
    assert observe(state, 14.9, 0) == Status.NORMAL
    assert observe(state, 15, 1) == Status.WATCH
    assert observe(state, 25, 2) == Status.ALERT
    assert observe(StatusMachine(), 40, 0) == Status.ALERT


def test_hysteresis_all_downgrades_and_reset():
    state = StatusMachine("Alert")
    for minute in range(5):
        assert observe(state, 20, minute) == Status.ALERT
    assert observe(state, 25, 5) == Status.ALERT  # breaks continuous low period
    for minute in range(6, 11):
        assert observe(state, 0, minute) == Status.ALERT
    assert observe(state, 0, 11) == Status.WATCH
    for minute in range(12, 17):
        assert observe(state, 0, minute) == Status.WATCH
    assert observe(state, 0, 17) == Status.NORMAL


@pytest.mark.parametrize("initial", ["Normal", "Watch", "Alert"])
def test_nodata_and_recovery(initial):
    state = StatusMachine(initial)
    assert state.watchdog(NOW + timedelta(seconds=179), NOW) == initial
    assert state.watchdog(NOW + timedelta(minutes=3), NOW) == Status.NO_DATA
    assert observe(state, 50, 4, True) == Status.NO_DATA
    assert observe(state, None, 4) == Status.NO_DATA
    assert observe(state, 50, 4) == Status.NORMAL
    assert observe(state, 50, 5) == Status.ALERT


def test_suspect_missing_and_out_of_order_ignored():
    state = StatusMachine()
    assert observe(state, 90, 0, True) == Status.NORMAL
    assert state.last_valid is None
    observe(state, 10, 1)
    assert observe(state, None, 2) == Status.NORMAL
    assert observe(state, 90, 0) == Status.NORMAL
    assert state.last_valid == NOW + timedelta(minutes=1)
    assert state.watchdog(NOW + timedelta(minutes=4), NOW) == Status.NO_DATA


@pytest.mark.parametrize("watch,alert", [(0, 25), (25, 25), (30, 25), (15, 151), (-1, 25), (float("nan"), 25)])
def test_threshold_validation(watch, alert):
    with pytest.raises(ValidationError):
        Thresholds(watch_threshold_cm=watch, alert_threshold_cm=alert)
