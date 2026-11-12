import asyncio
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .auth import client_ip, identity, supervisor
from .config import Settings, read_secret
from .domain import DTO, Thresholds
from .logging import configure, event
from .models import Forecast, MonitoringPoint
from .runtime import Runtime, rate_count


class Health(DTO):
    status: str


class PublicPoint(DTO):
    id: str
    name: str
    zone: str
    lat: float
    lon: float
    status: str
    simulated: bool
    water_depth_cm: float | None
    updated_at: datetime | None
    last_update_age_seconds: float | None


class Reading(DTO):
    captured_at: datetime
    water_depth_cm: float | None
    rain_mm5min: float | None = Field(alias="rainMm5min")


class ForecastResponse(DTO):
    forecast_for: datetime
    issued_at: datetime
    precip_mm: float | None


class KPIs(DTO):
    points_by_status: dict[str, int]
    max_depth_cm: float | None
    rain_last60min_mm: float | None = Field(alias="rainLast60minMm")
    rain_last60min_by_point: dict[str, float | None] = Field(default_factory=dict, alias="rainLast60minByPoint")
    data_freshness_seconds: float | None


async def database(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as db:
        yield db


def redis_client(request: Request) -> Redis:
    return cast(Redis, request.app.state.redis)


DB = Annotated[AsyncSession, Depends(database)]
Cache = Annotated[Redis, Depends(redis_client)]
User = Annotated[dict[str, Any], Depends(identity)]
Supervisor = Annotated[dict[str, Any], Depends(supervisor)]


async def point_or_404(db: AsyncSession, point_id: str) -> MonitoringPoint:
    point = await db.get(MonitoringPoint, point_id)
    if point is None:
        raise HTTPException(404, "Point not found")
    return point


def create_app(settings: Settings | None = None, *, background: bool = True) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure(settings.log_level)
        app.state.public_key = settings.jwt_public_key_file.read_text()
        # Validate every mounted credential at startup, never expose their values.
        read_secret(settings.mqtt_password_file)
        ssl.create_default_context(cafile=str(settings.mqtt_ca_file))
        if not isinstance(load_pem_public_key(app.state.public_key.encode()), RSAPublicKey):
            raise ValueError("JWT verification key must be RSA")
        engine = create_async_engine(
            settings.database_url(),
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"server_settings": {"search_path": "telemetry,public", "statement_timeout": "10000"}},
        )
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
        redis = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=read_secret(settings.redis_password_file).get_secret_value(),
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )
        app.state.redis = redis
        runtime = Runtime(app.state.sessions, redis, settings)
        app.state.runtime = runtime
        tasks: list[asyncio.Task[None]] = []
        try:
            await runtime.initialize()
            if background:
                tasks = [asyncio.create_task(runtime.mqtt_loop()), asyncio.create_task(runtime.watchdog_loop())]
                if settings.open_meteo_enabled:
                    tasks.append(asyncio.create_task(runtime.forecast_loop()))
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await redis.aclose()
            await engine.dispose()

    app = FastAPI(
        lifespan=lifespan,
        docs_url="/docs" if settings.environment == "dev" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment == "dev" else None,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def security(request: Request, call_next: Any) -> Any:
        if (
            request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.headers.get("x-requested-with") != "XMLHttpRequest"
        ):
            event("csrf.rejected", client_ip=client_ip(request), path=request.url.path, status=403)
            return JSONResponse({"detail": "CSRF header required"}, status_code=403)
        return await call_next(request)

    @app.get("/healthz", response_model=Health)
    async def healthz() -> Health:
        return Health(status="ok")

    @app.get("/readyz", response_model=Health)
    async def readyz(db: DB, redis: Cache) -> Health:
        try:
            await db.execute(text("SELECT 1"))
            await redis.ping()
        except Exception:
            raise HTTPException(503, "Dependencies unavailable") from None
        return Health(status="ready")

    @app.get("/public/points", response_model=list[PublicPoint])
    async def points(request: Request, db: DB, redis: Cache) -> list[PublicPoint]:
        if await rate_count(redis, f"rl:telemetry:public:{client_ip(request)}") > 60:
            raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": "60"})
        rows = (
            (
                await db.execute(
                    text("""
            SELECT p.*, r.water_depth_cm, r.captured_at AS updated_at,
                   EXTRACT(EPOCH FROM (now() - r.captured_at)) AS last_update_age_seconds
            FROM telemetry.monitoring_point p LEFT JOIN LATERAL (
                SELECT water_depth_cm, captured_at FROM telemetry.clean_reading
                WHERE point_id=p.id AND quality_flag='ok' AND water_depth_cm IS NOT NULL
                ORDER BY captured_at DESC LIMIT 1
            ) r ON true ORDER BY p.id
        """)
                )
            )
            .mappings()
            .all()
        )
        return [PublicPoint.model_validate(row) for row in rows]

    @app.get("/points/{point_id}/readings", response_model=list[Reading])
    async def readings(
        point_id: str,
        db: DB,
        user: User,
        start: Annotated[datetime | None, Query(alias="from")] = None,
        end: Annotated[datetime | None, Query(alias="to")] = None,
        bucket: Literal["1m", "5m", "15m", "1h"] = "5m",
    ) -> list[Reading]:
        end = end or datetime.now(UTC)
        start = start or end - timedelta(hours=6)
        if start.utcoffset() is None or end.utcoffset() is None or not timedelta(0) < end - start <= timedelta(days=7):
            raise HTTPException(422, "Use aware timestamps and a positive range of at most 7 days")
        await point_or_404(db, point_id)
        interval = timedelta(minutes={"1m": 1, "5m": 5, "15m": 15, "1h": 60}[bucket])
        rows = (
            (
                await db.execute(
                    text("""
            SELECT public.time_bucket(CAST(:bucket AS interval), captured_at) AS captured_at,
                   avg(water_depth_cm) AS water_depth_cm, avg(rain_mm5min) AS rain_mm5min
            FROM telemetry.clean_reading WHERE point_id=:point AND captured_at >= :start
            AND captured_at < :end AND quality_flag='ok'
            GROUP BY 1 ORDER BY 1
        """),
                    {"bucket": interval, "point": point_id, "start": start, "end": end},
                )
            )
            .mappings()
            .all()
        )
        return [Reading.model_validate(row) for row in rows]

    @app.get("/kpis", response_model=KPIs)
    async def kpis(db: DB, redis: Cache, user: User) -> KPIs:
        key = "cache:kpis:telemetry"
        cached = await redis.get(key)
        if cached:
            return KPIs.model_validate_json(cached)
        counts = (
            await db.execute(text("SELECT status, count(*) FROM telemetry.monitoring_point GROUP BY status"))
        ).all()
        row = (
            (
                await db.execute(
                    text("""
            SELECT max(water_depth_cm) AS max_depth_cm,
            EXTRACT(EPOCH FROM (now() - max(captured_at))) AS data_freshness_seconds
            FROM telemetry.clean_reading WHERE quality_flag='ok' AND captured_at >= now() - interval '60 minutes'
        """)
                )
            )
            .mappings()
            .one()
        )
        now = datetime.now(UTC)
        rain_rows = (
            await db.execute(
                text("""
            SELECT point_id, avg(rain_mm5min) * 12 AS rain_mm
            FROM telemetry.clean_reading WHERE quality_flag='ok'
            AND captured_at >= :start AND captured_at < :end
            GROUP BY point_id
        """),
                {"start": now - timedelta(minutes=60), "end": now},
            )
        ).mappings().all()
        rain_by_point = {r["point_id"]: float(r["rain_mm"]) if r["rain_mm"] is not None else None for r in rain_rows}
        max_rain = max((value for value in rain_by_point.values() if value is not None), default=None)
        status_counts = {str(row[0]): int(row[1]) for row in counts}
        result = KPIs(
            points_by_status={s: status_counts.get(s, 0) for s in ["Normal", "Watch", "Alert", "NoData"]},
            rainLast60minMm=max_rain,
            rainLast60minByPoint=rain_by_point,
            **row,
        )
        await redis.set(key, result.model_dump_json(by_alias=True), ex=10)
        return result

    @app.get("/points/{point_id}/forecast", response_model=list[ForecastResponse])
    async def forecast(point_id: str, db: DB, user: User) -> list[ForecastResponse]:
        await point_or_404(db, point_id)
        now = datetime.now(UTC)
        rows = (
            await db.scalars(
                select(Forecast)
                .where(
                    Forecast.point_id == point_id,
                    Forecast.forecast_for >= now,
                    Forecast.forecast_for < now + timedelta(hours=24),
                )
                .order_by(Forecast.forecast_for)
                .limit(24)
            )
        ).all()
        return [ForecastResponse.model_validate(row) for row in rows]

    @app.patch("/points/{point_id}/thresholds", response_model=Thresholds)
    async def thresholds(point_id: str, body: Thresholds, request: Request, db: DB, user: Supervisor) -> Thresholds:
        runtime: Runtime = request.app.state.runtime
        async with runtime.lock:
            point = await point_or_404(db, point_id)
            before = {"watchThresholdCm": point.watch_threshold_cm, "alertThresholdCm": point.alert_threshold_cm}
            point.watch_threshold_cm, point.alert_threshold_cm = body.watch_threshold_cm, body.alert_threshold_cm
            await db.commit()
            if point_id in runtime.states:
                runtime.states[point_id].below_since = None
            event(
                "audit.threshold_change",
                user=user["sub"],
                client_ip=client_ip(request),
                point_id=point_id,
                previous=before,
                current=body.model_dump(by_alias=True),
            )
        return body

    return app
