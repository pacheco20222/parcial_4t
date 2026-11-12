import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import fakeredis.aioredis
import httpx
import pytest

from telemetry_service.config import Settings, read_secret
from telemetry_service.domain import StatusMachine
from telemetry_service.models import CleanReading, Device, MonitoringPoint, RawReading
from telemetry_service.runtime import Runtime, rate_count


def payload(depth=20, **changes):
    return json.dumps(
        {
            "messageId": str(uuid4()),
            "pointId": "P01",
            "deviceId": "DEV-P01-A",
            "capturedAt": datetime.now(UTC).isoformat(),
            "waterDepthCm": depth,
            "rainMm5min": None,
            "batteryPct": 80,
            "fwVersion": "1.2.0",
            **changes,
        }
    ).encode()


@pytest.fixture
async def setup_runtime():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    db = AsyncMock()
    db.add = MagicMock()
    point = MonitoringPoint(
        id="P01", name="Simulado", zone="Centro", status="Normal", watch_threshold_cm=15, alert_threshold_cm=25
    )
    device = Device(id="DEV-P01-A", point_id="P01")

    async def get(model, key):
        return device if model == Device else point if model == MonitoringPoint else None

    db.get.side_effect = get
    db.scalar.return_value = None
    sessions = MagicMock()
    sessions.return_value.__aenter__.return_value = db
    runtime = Runtime(sessions, redis, Settings(open_meteo_enabled=False))
    yield runtime, db, redis, point
    await redis.aclose()


async def test_ingestion_storage_events_dedup(setup_runtime):
    runtime, db, redis, point = setup_runtime
    topic = "merida/flood/P01/DEV-P01-A/telemetry"
    body = payload()
    await runtime.ingest(topic, body)
    records = [call.args[0] for call in db.add.call_args_list]
    assert isinstance(records[0], RawReading)
    assert isinstance(records[1], CleanReading) and records[1].quality_flag == "ok"
    assert records[1].rain_mm5min is None
    latest = await redis.hgetall("latest:P01")
    assert latest["rainMm5min"] == "null" and latest["status"] == "Watch"
    stream = await redis.xrange("stream:point-status")
    data = json.loads(stream[0][1]["data"])
    assert data["previous"] == "Normal" and data["current"] == "Watch"
    assert data["pointId"] == "P01" and data["pointName"] == "Simulado"
    assert data["watchThresholdCm"] == 15 and data["alertThresholdCm"] == 25
    assert point.status == "Watch"
    await runtime.ingest(topic, body)
    assert db.add.call_count == 2
    assert len(await redis.xrange("stream:point-status")) == 1
    assert await redis.ttl("dedup:" + json.loads(body)["messageId"]) > 0


@pytest.mark.parametrize(
    "body,topic",
    [(b"bad", "merida/flood/P01/DEV-P01-A/telemetry"), (payload(), "merida/flood/P02/DEV-P01-A/telemetry")],
)
async def test_invalid_or_mismatched_dropped(setup_runtime, body, topic):
    runtime, db, redis, _ = setup_runtime
    await runtime.ingest(topic, body)
    db.add.assert_not_called()
    assert await redis.keys("dedup:*") == []


async def test_device_must_belong_to_point(setup_runtime):
    runtime, db, _, _ = setup_runtime
    db.get.side_effect = None
    db.get.return_value = Device(id="DEV-P01-A", point_id="P02")
    await runtime.ingest("merida/flood/P01/DEV-P01-A/telemetry", payload())
    db.add.assert_not_called()


async def test_rate_exceeded_dropped_without_side_effects(setup_runtime):
    runtime, db, redis, point = setup_runtime
    await redis.set("rl:telemetry:device:DEV-P01-A", 10, ex=60)
    with patch("telemetry_service.runtime.event") as log:
        await runtime.ingest("merida/flood/P01/DEV-P01-A/telemetry", payload(100))
    log.assert_called_once_with("telemetry.rate_exceeded", device_id="DEV-P01-A")
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    assert await redis.keys("dedup:*") == []
    assert await redis.hgetall("latest:P01") == {}
    assert point.status == "Normal"
    assert runtime.states == {}
    assert await redis.xrange("stream:point-status") == []


async def test_database_failure_releases_dedup(setup_runtime):
    runtime, db, redis, _ = setup_runtime
    db.commit.side_effect = RuntimeError("unavailable")
    body = payload()
    with pytest.raises(RuntimeError):
        await runtime.ingest("merida/flood/P01/DEV-P01-A/telemetry", body)
    assert await redis.get("dedup:" + json.loads(body)["messageId"]) is None


async def test_fixed_window_not_sliding(setup_runtime):
    _, _, redis, _ = setup_runtime
    assert await rate_count(redis, "rl:test", 60) == 1
    await redis.expire("rl:test", 10)
    assert await rate_count(redis, "rl:test", 60) == 2
    assert await redis.ttl("rl:test") <= 10


async def test_watchdog_emits_once(setup_runtime):
    runtime, db, redis, point = setup_runtime
    runtime.started_at = datetime.now(UTC) - timedelta(minutes=4)
    runtime.states["P01"] = StatusMachine()
    db.scalars.return_value = MagicMock()
    db.scalars.return_value.all.return_value = [point]
    calls = 0

    async def stop_after_two_rounds(seconds):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise asyncio.CancelledError

    with patch("telemetry_service.runtime.asyncio.sleep", side_effect=stop_after_two_rounds):
        with pytest.raises(asyncio.CancelledError):
            await runtime.watchdog_loop()
    assert point.status == "NoData"
    assert len(await redis.xrange("stream:point-status")) == 1


async def test_forecast_persistence_and_cache(setup_runtime):
    runtime, db, redis, point = setup_runtime
    point.lat, point.lon = 20.97, -89.62

    def respond(request):
        assert request.url.host == "api.open-meteo.com"
        return httpx.Response(
            200, json={"hourly": {"time": ["2026-11-12T08:00", "2026-11-12T09:00"], "precipitation": [None, 2.5]}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), timeout=10) as client:
        await runtime.forecast_point(client, point)
    assert db.execute.await_count == 1
    assert db.commit.await_count == 1
    forecast = await redis.hgetall("forecast:P01")
    assert json.loads(forecast["data"])[0]["precipMm"] is None
    assert await redis.ttl("forecast:P01") > 0


async def test_forecast_bounded_failure(setup_runtime):
    runtime, db, redis, point = setup_runtime
    point.lat, point.lon = 20.97, -89.62
    requests = []

    def fail(request):
        requests.append(request)
        return httpx.Response(503)

    with patch("telemetry_service.runtime.asyncio.sleep", new_callable=AsyncMock):
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail), timeout=10) as client:
            await runtime.forecast_point(client, point)
    assert len(requests) == 3
    db.commit.assert_not_called()
    assert not await redis.exists("forecast:P01")


def test_secret_file_and_encoded_db_url(tmp_path):
    path = tmp_path / "secret"
    path.write_text("test:@/password\n")
    settings = Settings(database_password_file=path)
    assert settings.database_url().password == "test:@/password"
    assert "test:@/password" not in str(settings.database_url())
    assert read_secret(path).get_secret_value() == "test:@/password"
    path.write_text("")
    with pytest.raises(ValueError):
        read_secret(path)


async def test_status_publish_retry_reuses_event_id(setup_runtime):
    runtime, db, redis, point = setup_runtime
    runtime.states["P01"] = StatusMachine("Watch")
    db.commit.side_effect = RuntimeError("database unavailable")
    now = datetime.now(UTC)
    with pytest.raises(RuntimeError):
        await runtime.status_changed(db, point, "Normal", 20, now)
    # Next DB session reads the unchanged persisted status.
    point.status = "Normal"
    db.commit.side_effect = None
    await runtime.status_changed(db, point, "Normal", None, now + timedelta(seconds=30))
    stream = await redis.xrange("stream:point-status")
    assert len(stream) == 2
    first, retry = [json.loads(entry[1]["data"]) for entry in stream]
    assert first["eventId"] == retry["eventId"]
    assert retry["waterDepthCm"] == 20


@pytest.mark.parametrize("limit", [10, 2])
async def test_configurable_device_rate_boundary(setup_runtime, limit):
    runtime, db, redis, _ = setup_runtime
    runtime.settings = Settings(max_msgs_per_device_per_min=limit)
    await redis.set("rl:telemetry:device:DEV-P01-A", limit - 1, ex=60)
    await runtime.ingest("merida/flood/P01/DEV-P01-A/telemetry", payload(10))
    assert db.add.call_args.args[0].quality_flag == "ok"
    db.reset_mock()
    await runtime.ingest("merida/flood/P01/DEV-P01-A/telemetry", payload(10))
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


def test_rate_limit_env(monkeypatch):
    monkeypatch.delenv("MAX_MSGS_PER_DEVICE_PER_MIN", raising=False)
    assert Settings().max_msgs_per_device_per_min == 10
    monkeypatch.setenv("MAX_MSGS_PER_DEVICE_PER_MIN", "20")
    assert Settings().max_msgs_per_device_per_min == 20
    monkeypatch.setenv("MAX_MSGS_PER_DEVICE_PER_MIN", "0")
    with pytest.raises(ValueError):
        Settings()
