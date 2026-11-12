import asyncio
import json
import ssl
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aiomqtt
import httpx
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings, read_secret
from .domain import Payload, StatusMachine, quality
from .logging import event
from .models import CleanReading, Device, Forecast, MonitoringPoint, RawReading


async def rate_count(redis: Redis, key: str, seconds: int = 60) -> int:
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, seconds, nx=True)
        result = await pipe.execute()
    return int(result[0])


class Runtime:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], redis: Redis, settings: Settings) -> None:
        self.sessions, self.redis, self.settings = sessions, redis, settings
        self.states: dict[str, StatusMachine] = {}
        self.pending_status: dict[str, dict[str, Any]] = {}
        self.started_at = datetime.now(UTC)
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self.sessions() as db:
            points = (await db.scalars(select(MonitoringPoint))).all()
            rows = (
                await db.execute(
                    text("""
                SELECT p.id AS point_id, r.captured_at
                FROM telemetry.monitoring_point p LEFT JOIN LATERAL (
                    SELECT captured_at FROM telemetry.clean_reading
                    WHERE point_id=p.id AND quality_flag='ok' AND water_depth_cm IS NOT NULL
                    ORDER BY captured_at DESC LIMIT 1
                ) r ON true
            """)
                )
            ).all()
            latest = {row.point_id: row.captured_at for row in rows}
            self.states = {p.id: StatusMachine(p.status, latest.get(p.id)) for p in points}

    async def status_changed(
        self, db: AsyncSession, point: MonitoringPoint, previous: str, depth: float | None, now: datetime
    ) -> None:
        current = self.states[point.id].status.value
        if current == previous:
            return
        data = self.pending_status.get(point.id)
        if data is None or data["current"] != current:
            data = {
                "eventId": str(uuid4()),
                "type": "point.status_changed",
                "pointId": point.id,
                "pointName": point.name,
                "zone": point.zone,
                "previous": previous,
                "current": current,
                "waterDepthCm": depth,
                "occurredAt": now.isoformat(),
                "watchThresholdCm": point.watch_threshold_cm,
                "alertThresholdCm": point.alert_threshold_cm,
            }
            self.pending_status[point.id] = data
        await self.redis.xadd("stream:point-status", {"data": json.dumps(data)}, maxlen=10000, approximate=True)
        point.status = current
        await db.commit()
        await self.redis.hset(f"latest:{point.id}", mapping={"status": current})
        self.pending_status.pop(point.id, None)
        event("point.status_changed", point_id=point.id, previous=previous, status=current)

    async def ingest(self, topic: str, body: bytes) -> None:
        try:
            payload = Payload.model_validate_json(body)
        except ValidationError:
            event("telemetry.validation_failed")
            return
        async with self.lock, self.sessions() as db:
            device = await db.get(Device, payload.device_id)
            if (
                topic != f"merida/flood/{payload.point_id}/{payload.device_id}/telemetry"
                or device is None
                or device.point_id != payload.point_id
            ):
                event("telemetry.topic_mismatch", device_id=payload.device_id, point_id=payload.point_id)
                return
            point = await db.get(MonitoringPoint, payload.point_id)
            assert point is not None
            count = await rate_count(self.redis, f"rl:telemetry:device:{payload.device_id}")
            if count > self.settings.max_msgs_per_device_per_min:
                event("telemetry.rate_exceeded", device_id=payload.device_id)
                return
            key = f"dedup:{payload.message_id}"
            if not await self.redis.set(key, "1", nx=True, ex=86400):
                event("telemetry.duplicate", device_id=payload.device_id)
                return
            # DB uniqueness also protects redelivery after the Redis TTL expires.
            if await db.get(RawReading, payload.message_id) is not None:
                event("telemetry.duplicate", device_id=payload.device_id)
                return
            now = datetime.now(UTC)
            previous = await db.scalar(
                select(CleanReading)
                .where(
                    CleanReading.device_id == payload.device_id,
                    CleanReading.quality_flag == "ok",
                    CleanReading.water_depth_cm.is_not(None),
                )
                .order_by(CleanReading.captured_at.desc())
                .limit(1)
            )
            prior = (
                (previous.captured_at, previous.water_depth_cm)
                if previous and previous.water_depth_cm is not None
                else None
            )
            flag = quality(payload, prior, False, now)
            db.add(
                RawReading(
                    message_id=payload.message_id,
                    device_id=payload.device_id,
                    captured_at=payload.captured_at,
                    received_at=now,
                    payload=payload.model_dump(mode="json", by_alias=True),
                )
            )
            db.add(
                CleanReading(
                    message_id=payload.message_id,
                    device_id=payload.device_id,
                    point_id=payload.point_id,
                    captured_at=payload.captured_at,
                    received_at=now,
                    water_depth_cm=payload.water_depth_cm,
                    rain_mm5min=payload.rain_mm5min,
                    quality_flag=flag,
                )
            )
            try:
                await db.commit()
            except Exception:
                await self.redis.delete(key)
                raise
            state = self.states.setdefault(point.id, StatusMachine(point.status))
            reading = {
                "type": "telemetry.reading",
                "pointId": point.id,
                "deviceId": device.id,
                "capturedAt": payload.captured_at.isoformat(),
                "waterDepthCm": payload.water_depth_cm,
                "rainMm5min": payload.rain_mm5min,
                "qualityFlag": flag,
                "status": state.status.value,
            }
            await self.redis.hset(
                f"latest:{point.id}",
                mapping={
                    k: json.dumps(v) if v is None or isinstance(v, (int, float)) else v
                    for k, v in {**reading, "updatedAt": now.isoformat()}.items()
                },
            )
            await self.redis.publish("events:telemetry", json.dumps(reading))
            old = point.status
            state.observe(
                payload.water_depth_cm,
                payload.captured_at,
                point.watch_threshold_cm,
                point.alert_threshold_cm,
                flag == "suspect",
            )
            await self.status_changed(db, point, old, payload.water_depth_cm, now)
            event("telemetry.ingested", device_id=device.id, point_id=point.id)
            if flag == "suspect":
                event("telemetry.suspect_reading", device_id=device.id, point_id=point.id)

    async def mqtt_loop(self) -> None:
        tls = ssl.create_default_context(cafile=str(self.settings.mqtt_ca_file))
        password = read_secret(self.settings.mqtt_password_file).get_secret_value()
        delay = 1
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.settings.mqtt_host,
                    port=self.settings.mqtt_port,
                    username=self.settings.mqtt_username,
                    password=password,
                    tls_context=tls,
                    max_queued_incoming_messages=1000,
                ) as client:
                    await client.subscribe("merida/flood/+/+/telemetry", qos=1)
                    delay = 1
                    async for message in client.messages:
                        if not isinstance(message.payload, (bytes, bytearray)) or len(message.payload) > 16384:
                            event("telemetry.validation_failed")
                            continue
                        try:
                            await self.ingest(str(message.topic), bytes(message.payload))
                        except Exception:
                            event("telemetry.ingest_failed")
            except aiomqtt.MqttError:
                event("telemetry.mqtt_disconnected")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def watchdog_loop(self) -> None:
        while True:
            try:
                async with self.lock, self.sessions() as db:
                    for point in (await db.scalars(select(MonitoringPoint))).all():
                        state = self.states.setdefault(point.id, StatusMachine(point.status))
                        previous = point.status
                        now = datetime.now(UTC)
                        state.watchdog(now, self.started_at)
                        await self.status_changed(db, point, previous, None, now)
            except Exception:
                event("telemetry.watchdog_failed")
            await asyncio.sleep(30)

    async def forecast_point(self, client: httpx.AsyncClient, point: MonitoringPoint) -> None:
        for attempt in range(3):
            try:
                response = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": point.lat,
                        "longitude": point.lon,
                        "hourly": "precipitation",
                        "forecast_hours": 24,
                        "timezone": "UTC",
                    },
                )
                response.raise_for_status()
                hourly = response.json()["hourly"]
                times, values = hourly["time"], hourly["precipitation"]
                if len(times) != len(values) or not 1 <= len(times) <= 24:
                    raise ValueError("Invalid hourly forecast")
                rows: list[dict[str, Any]] = []
                issued = datetime.now(UTC)
                for at, value in zip(times, values, strict=True):
                    if value is not None and (
                        isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1000
                    ):
                        raise ValueError("Invalid precipitation")
                    rows.append(
                        {
                            "point_id": point.id,
                            "forecast_for": datetime.fromisoformat(at).replace(tzinfo=UTC),
                            "issued_at": issued,
                            "precip_mm": value,
                        }
                    )
                async with self.sessions() as db:
                    statement = insert(Forecast).values(rows)
                    await db.execute(
                        statement.on_conflict_do_update(
                            index_elements=[Forecast.point_id, Forecast.forecast_for],
                            set_={"issued_at": statement.excluded.issued_at, "precip_mm": statement.excluded.precip_mm},
                        )
                    )
                    await db.commit()
                await self.redis.hset(
                    f"forecast:{point.id}",
                    mapping={
                        "issuedAt": issued.isoformat(),
                        "data": json.dumps(
                            [{"forecastFor": r["forecast_for"].isoformat(), "precipMm": r["precip_mm"]} for r in rows]
                        ),
                    },
                )
                await self.redis.expire(f"forecast:{point.id}", 3600)
                return
            except (httpx.HTTPError, ValueError, KeyError, TypeError, OverflowError):
                event("telemetry.forecast_failed", point_id=point.id, attempt=attempt + 1)
                if attempt < 2:
                    await asyncio.sleep(2**attempt)

    async def forecast_loop(self) -> None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            while True:
                try:
                    async with self.sessions() as db:
                        points = (await db.scalars(select(MonitoringPoint))).all()
                    for point in points:
                        try:
                            await self.forecast_point(client, point)
                        except Exception:
                            event("telemetry.forecast_failed", point_id=point.id)
                except Exception:
                    event("telemetry.forecast_failed")
                await asyncio.sleep(3600)
