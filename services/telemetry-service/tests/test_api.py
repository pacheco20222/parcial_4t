import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Row
from sqlalchemy.engine.result import SimpleResultMetaData

from telemetry_service.api import create_app, database, redis_client
from telemetry_service.config import Settings

PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC = PRIVATE.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)


def token(**changes):
    return jwt.encode(
        {
            "sub": "user-1",
            "email": "test@example.invalid",
            "role": "Operator",
            "amr": "pwd",
            "iss": "flood-ops",
            "aud": "flood-platform",
            "exp": datetime.now(UTC) + timedelta(minutes=15),
            **changes,
        },
        PRIVATE,
        algorithm="RS256",
    )


@pytest.fixture
async def setup():
    app = create_app(Settings(open_meteo_enabled=False))
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id="P01", watch_threshold_cm=15, alert_threshold_cm=25)
    app.state.public_key = PUBLIC
    app.state.runtime = SimpleNamespace(lock=asyncio.Lock(), states={})

    async def fake_db():
        yield db

    app.dependency_overrides[database] = fake_db
    app.dependency_overrides[redis_client] = lambda: redis
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, db, redis, app
    await redis.aclose()


async def test_health_ready(setup):
    client, db, _, _ = setup
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    assert (await client.get("/readyz")).status_code == 200
    db.execute.side_effect = RuntimeError()
    assert (await client.get("/readyz")).status_code == 503
    assert (await client.get("/healthz")).status_code == 200


@pytest.mark.parametrize(
    "claims",
    [{"exp": datetime.now(UTC) - timedelta(seconds=1)}, {"aud": "wrong"}, {"iss": "wrong"}, {"role": "Unknown"}],
)
async def test_jwt_rejections(setup, claims):
    client, _, _, _ = setup
    response = await client.get("/kpis", headers={"Authorization": f"Bearer {token(**claims)}"})
    assert response.status_code == 401


async def test_missing_token(setup):
    assert (await setup[0].get("/kpis")).status_code == 401


async def test_kpi_cookie_and_cache(setup):
    client, db, redis, _ = setup
    await redis.set(
        "cache:kpis:telemetry",
        '{"pointsByStatus":{"Normal":5},"maxDepthCm":null,"rainLast60minMm":null,"dataFreshnessSeconds":null}',
    )
    client.cookies.set("flood_at", token())
    response = await client.get("/kpis")
    assert response.status_code == 200
    assert response.json()["maxDepthCm"] is None
    db.execute.assert_not_called()


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
async def test_csrf(setup, method):
    response = await setup[0].request(method, "/points/P01/thresholds")
    assert response.status_code == 403


@pytest.mark.parametrize(
    "role,mfa,enforce,expected",
    [
        ("Operator", "pwd", False, 403),
        ("Supervisor", "pwd", False, 200),
        ("Admin", "pwd", False, 200),
        ("Supervisor", "pwd", True, 403),
        ("Admin", "mfa", True, 200),
    ],
)
async def test_threshold_roles_mfa(setup, role, mfa, enforce, expected):
    client, db, _, app = setup
    app.state.settings.enforce_mfa = enforce
    response = await client.patch(
        "/points/P01/thresholds",
        json={"watchThresholdCm": 20, "alertThresholdCm": 30},
        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": f"Bearer {token(role=role, amr=mfa)}"},
    )
    assert response.status_code == expected
    if expected == 200:
        assert response.json() == {"watchThresholdCm": 20, "alertThresholdCm": 30}
        db.commit.assert_awaited_once()
    else:
        db.commit.assert_not_called()


async def test_threshold_api_invalid(setup):
    response = await setup[0].patch(
        "/points/P01/thresholds",
        json={"watchThresholdCm": 30, "alertThresholdCm": 20},
        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": f"Bearer {token(role='Supervisor')}"},
    )
    assert response.status_code == 422


async def test_public_thresholds_after_patch_nulls_and_rate_limit(setup):
    client, db, redis, _ = setup
    point = db.get.return_value
    result = MagicMock()
    result.mappings.return_value.all.side_effect = lambda: [
        {
            **vars(point),
            "id": "P01",
            "name": "Simulado",
            "zone": "Centro",
            "lat": 20.97,
            "lon": -89.62,
            "status": "NoData",
            "simulated": True,
            "water_depth_cm": None,
            "updated_at": None,
            "last_update_age_seconds": None,
        }
    ]
    db.execute.return_value = result
    response = await client.get("/public/points", headers={"X-Forwarded-For": "untrusted"})
    assert response.status_code == 200
    assert response.json() == [{
        "id": "P01", "name": "Simulado", "zone": "Centro", "lat": 20.97, "lon": -89.62,
        "status": "NoData", "simulated": True, "waterDepthCm": None, "updatedAt": None,
        "lastUpdateAgeSeconds": None, "watchThresholdCm": 15.0, "alertThresholdCm": 25.0,
    }]
    thresholds = {"watchThresholdCm": 20.25, "alertThresholdCm": 30.75}
    patched = await client.patch(
        "/points/P01/thresholds",
        json=thresholds,
        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": f"Bearer {token(role='Supervisor')}"},
    )
    assert patched.status_code == 200
    db.commit.assert_awaited_once()
    refreshed = await client.get("/public/points")
    assert refreshed.status_code == 200
    assert refreshed.json() == [{**response.json()[0], **thresholds}]
    assert db.execute.await_count == 2
    await redis.set("rl:telemetry:public:127.0.0.1", 60, ex=60)
    assert (await client.get("/public/points")).status_code == 429


@pytest.mark.parametrize(
    "query",
    [
        "bucket=bad",
        "from=2026-01-01T00:00:00Z&to=2026-01-09T00:00:00Z",
        "from=2026-01-01T00:00:00",
        "from=2026-01-02T00:00:00Z&to=2026-01-01T00:00:00Z",
    ],
)
async def test_readings_bounds(setup, query):
    response = await setup[0].get("/points/P01/readings?" + query, headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 422


async def test_readings_parameters_and_forecast(setup):
    client, db, _, _ = setup
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    db.execute.return_value = result
    response = await client.get("/points/P01/readings?bucket=1h", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 200 and response.json() == []
    assert db.execute.call_args.args[1]["bucket"] == timedelta(hours=1)
    db.scalars.return_value = MagicMock()
    db.scalars.return_value.all.return_value = []
    assert (await client.get("/points/P01/forecast", headers={"Authorization": f"Bearer {token()}"})).json() == []
    db.get.return_value = None
    assert (await client.get("/points/P99/forecast", headers={"Authorization": f"Bearer {token()}"})).status_code == 404


async def test_prod_docs_disabled():
    app = create_app(Settings(environment="prod"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/openapi.json")).status_code == 404
        assert (await client.get("/docs")).status_code == 404


async def test_kpi_uncached_path(setup):
    client, db, redis, _ = setup
    counts = MagicMock()
    counts.all.return_value = [("Normal", 4), ("Alert", 1)]
    metrics = MagicMock()
    metrics.mappings.return_value.one.return_value = {
        "max_depth_cm": 30.0,
        "data_freshness_seconds": 5.0,
    }
    rain = MagicMock()
    rain.mappings.return_value.all.return_value = []
    db.execute.side_effect = [counts, metrics, rain]
    response = await client.get("/kpis", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 200
    assert response.json()["pointsByStatus"] == {"Normal": 4, "Watch": 0, "Alert": 1, "NoData": 0}
    assert 0 < await redis.ttl("cache:kpis:telemetry") <= 10


async def test_successful_reading_exact_camelcase(setup):
    client, db, _, _ = setup
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        {"captured_at": datetime.now(UTC), "water_depth_cm": None, "rain_mm5min": 2.0}
    ]
    db.execute.return_value = result
    response = await client.get("/points/P01/readings", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 200
    assert response.json()[0]["waterDepthCm"] is None
    assert response.json()[0]["rainMm5min"] == 2.0


@pytest.mark.parametrize("depth,rain", [(Decimal("12.75"), Decimal("2.25")), (None, None)])
async def test_readings_asyncpg_row_shape_and_interval_binding(setup, depth, rain):
    client, db, _, _ = setup
    at = datetime(2026, 11, 12, 7, tzinfo=UTC)
    keys = ["captured_at", "water_depth_cm", "rain_mm5min"]
    row = Row(SimpleResultMetaData(keys), None, dict(zip(keys, range(3))), (at, depth, rain))
    result = MagicMock()
    result.mappings.return_value.all.return_value = [row._mapping]
    db.execute.return_value = result
    response = await client.get("/points/P01/readings?bucket=5m", headers={"Authorization": f"Bearer {token()}"})
    assert response.status_code == 200
    assert response.json() == [{
        "capturedAt": "2026-11-12T07:00:00Z",
        "waterDepthCm": float(depth) if depth is not None else None,
        "rainMm5min": float(rain) if rain is not None else None,
    }]
    # asyncpg's interval codec requires timedelta, not a human-readable string.
    assert db.execute.call_args.args[1]["bucket"] == timedelta(minutes=5)


@pytest.mark.parametrize("samples,expected,maximum", [
    ([("P01", 2, "ok", 30)] * 12 + [
        ("P02", 1, "ok", 20), ("P02", 3, "ok", 10), ("P02", None, "ok", 5),
        ("P03", 4, "ok", 20), ("P03", 6, "ok", 10), ("P04", None, "ok", 10),
        ("P01", 100, "suspect", 10), ("P01", 100, "ok", 90), ("P01", 100, "ok", -10),
    ], {"P01": 24.0, "P02": 24.0, "P03": 60.0, "P04": None}, 60.0),
    ([], {}, None),
    ([("P01", None, "ok", 10)], {"P01": None}, None),
])
async def test_hourly_rain_per_point_computation(setup, samples, expected, maximum):
    client, db, redis, _ = setup
    # Execute the production rain aggregation with a local SQL engine, not mocked averages.
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("ATTACH DATABASE ':memory:' AS telemetry"))
        connection.execute(text("CREATE TABLE telemetry.clean_reading "
                                "(point_id TEXT, rain_mm5min NUMERIC, quality_flag TEXT, captured_at TIMESTAMP)"))
        now = datetime.now(UTC)
        for point, rain, quality, age in samples:
            connection.execute(text("INSERT INTO telemetry.clean_reading VALUES (:point, :rain, :quality, :at)"),
                               {"point": point, "rain": rain, "quality": quality, "at": (now - timedelta(minutes=age)).isoformat(" ")})
        counts, metrics = MagicMock(), MagicMock()
        counts.all.return_value = [("Normal", 5)]
        metrics.mappings.return_value.one.return_value = {"max_depth_cm": None, "data_freshness_seconds": None}
        results = iter([counts, metrics])

        async def execute(statement, params=None):
            result = next(results, None)
            return result if result is not None else connection.execute(
                statement, {key: value.isoformat(" ") for key, value in params.items()}
            )

        db.execute.side_effect = execute
        response = await client.get("/kpis", headers={"Authorization": f"Bearer {token()}"})
        assert response.status_code == 200
        assert response.json()["rainLast60minByPoint"] == expected
        assert response.json()["rainLast60minMm"] == maximum
        cached = await client.get("/kpis", headers={"Authorization": f"Bearer {token()}"})
        assert cached.json() == response.json()
        assert db.execute.await_count == 3
    engine.dispose()
