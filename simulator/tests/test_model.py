from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from flood_simulator.model import (
    STATIONS,
    advance_depth,
    build_payload,
    null_depth,
    rain_intensity,
    rain_last_five_minutes,
    silent,
    topic,
)


@pytest.mark.parametrize("station", STATIONS)
def test_cycle_crosses_thresholds_and_drains_with_hysteresis(station):
    depth = 0.0
    values = []
    for elapsed in range(0, 1800, 60):
        before = depth
        depth = advance_depth(depth, rain_intensity("cycle", elapsed), 60, station)
        assert depth >= 0
        assert abs(depth - before) <= 30
        values.append(depth)
    assert values[0] == 0
    assert any(15 <= value < 25 for value in values)
    assert max(values) >= 25
    assert all(value < 15 for value in values[-5:])
    assert values[-1] == 0


@pytest.mark.parametrize("seconds", [1, 15, 60, 600])
@pytest.mark.parametrize("rain", [0, 30, 120, 10000])
def test_model_bounds(seconds, rain):
    for station in STATIONS:
        depth = advance_depth(20, rain, seconds, station)
        assert depth >= 0
        assert abs(depth - 20) <= 30 * seconds / 60


def test_scenario_behavior_and_point_variation():
    assert rain_intensity("dry", 0) == 0
    assert 0 < rain_intensity("light_rain", 0) < rain_intensity("storm", 0)
    assert advance_depth(20, 0, 60, STATIONS[0]) < 20
    assert len({advance_depth(0, 120, 60, s) for s in STATIONS}) == 5
    assert rain_intensity("cycle", 1800) == rain_intensity("cycle", 0)
    assert rain_last_five_minutes("storm", 300) == pytest.approx(10)
    assert rain_last_five_minutes("storm", 60) == pytest.approx(2)
    assert rain_last_five_minutes("cycle", 1200) == 0


def test_fault_is_exactly_five_minutes_and_only_one_device_silent():
    for elapsed, expected in [(59, False), (60, True), (359, True), (360, False)]:
        assert silent("sensor_fault", STATIONS[0], elapsed) is expected
    assert not silent("sensor_fault", STATIONS[1], 120)
    assert not silent("storm", STATIONS[0], 120)
    assert null_depth("sensor_fault", STATIONS[1], 420)
    assert not null_depth("sensor_fault", STATIONS[1], 480)


@pytest.mark.parametrize("station", STATIONS)
@pytest.mark.parametrize("depth", [None, 0.0, 25.5])
def test_payload_schema_and_topic(station, depth):
    timestamp = datetime(2026, 11, 12, 10, tzinfo=timezone(timedelta(hours=-6)))
    message_id = uuid4()
    payload = build_payload(station, depth, None, timestamp, message_id)
    assert set(payload) == {
        "messageId", "deviceId", "pointId", "capturedAt", "waterDepthCm",
        "rainMm5min", "batteryPct", "fwVersion",
    }
    assert UUID(payload["messageId"]) == message_id
    assert payload["capturedAt"] == "2026-11-12T16:00:00Z"
    assert payload["waterDepthCm"] == depth
    assert payload["rainMm5min"] is None
    assert type(payload["batteryPct"]) is int
    assert payload["fwVersion"] == "sim-1.0.0"
    assert topic(station) == f"merida/flood/{station.point_id}/{station.device_id}/telemetry"


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_invalid_model_and_payload_values_rejected(bad):
    with pytest.raises(ValueError):
        advance_depth(bad, 10, 60, STATIONS[0])
    with pytest.raises(ValueError):
        build_payload(STATIONS[0], bad, 0, datetime.now(UTC), uuid4())


def test_naive_timestamp_and_invalid_battery_rejected():
    with pytest.raises(ValueError):
        build_payload(STATIONS[0], 0, 0, datetime.now(), uuid4())
    with pytest.raises(ValueError):
        build_payload(STATIONS[0], 0, 0, datetime.now(UTC), uuid4(), 101)


@pytest.mark.parametrize("factor", [0.97, 1.03])
@pytest.mark.parametrize("station", STATIONS)
def test_cycle_allows_sequential_five_minute_downward_transitions(station, factor):
    depth = 0.0
    status = "Normal"
    pending_since = None
    seen = set()
    for elapsed in range(1801):
        depth = advance_depth(depth, rain_intensity("cycle", elapsed) * factor, 1, station)
        target = "Alert" if depth >= 25 else "Watch" if depth >= 15 else "Normal"
        rank = {"Normal": 0, "Watch": 1, "Alert": 2}
        if rank[target] >= rank[status]:
            status = target
            pending_since = None
        elif pending_since is None:
            pending_since = elapsed
        elif elapsed - pending_since >= 300:
            status = "Watch" if status == "Alert" else "Normal"
            pending_since = None
        seen.add(status)
    assert seen == {"Normal", "Watch", "Alert"}
    assert status == "Normal"


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf")])
def test_rain_integration_rejects_invalid_time(bad):
    with pytest.raises(ValueError):
        rain_last_five_minutes("cycle", bad)


@pytest.mark.parametrize("station", STATIONS)
def test_storm_saturates_below_sensor_range(station):
    depth = 0.0
    peak = 0.0
    for _ in range(6 * 60):
        before = depth
        depth = advance_depth(depth, rain_intensity("storm", 0), 60, station)
        assert abs(depth - before) < 30
        peak = max(peak, depth)
    assert 60 <= peak <= 100
    assert max(peak, depth) <= 120
