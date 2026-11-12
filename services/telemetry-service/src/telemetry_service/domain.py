from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class DTO(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


class Payload(DTO):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False)
    message_id: UUID
    device_id: str = Field(pattern=r"^DEV-P\d{2}-[A-Z]$", max_length=32)
    point_id: str = Field(pattern=r"^P\d{2}$")
    captured_at: datetime
    water_depth_cm: float | None = Field(strict=True)
    rain_mm5min: float | None = Field(alias="rainMm5min", strict=True)
    battery_pct: int = Field(strict=True, ge=0, le=100)
    fw_version: str = Field(min_length=1, max_length=64)

    @field_validator("captured_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("capturedAt must be UTC")
        if value > datetime.now(UTC) + timedelta(seconds=60):
            raise ValueError("capturedAt is in the future")
        return value.astimezone(UTC)


class Thresholds(DTO):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", allow_inf_nan=False)
    watch_threshold_cm: float = Field(gt=0, le=150, strict=True)
    alert_threshold_cm: float = Field(gt=0, le=150, strict=True)

    @model_validator(mode="after")
    def ordered(self) -> "Thresholds":
        if self.watch_threshold_cm >= self.alert_threshold_cm:
            raise ValueError("watchThresholdCm must be below alertThresholdCm")
        return self


class Status(StrEnum):
    NORMAL = "Normal"
    WATCH = "Watch"
    ALERT = "Alert"
    NO_DATA = "NoData"


class StatusMachine:
    def __init__(self, status: str = "Normal", last_valid: datetime | None = None) -> None:
        self.status = Status(status)
        self.last_valid = last_valid
        self.below_since: datetime | None = None

    def observe(self, depth: float | None, at: datetime, watch: float, alert: float, suspect: bool = False) -> Status:
        if suspect or depth is None or (self.last_valid is not None and at <= self.last_valid):
            return self.status
        if self.last_valid is not None and at - self.last_valid >= timedelta(minutes=3):
            self.below_since = None
        self.last_valid = at
        if self.status == Status.NO_DATA:
            self.status = Status.NORMAL
            self.below_since = None
            return self.status
        target = Status.ALERT if depth >= alert else Status.WATCH if depth >= watch else Status.NORMAL
        ranks = {Status.NORMAL: 0, Status.WATCH: 1, Status.ALERT: 2}
        if ranks[target] >= ranks[self.status]:
            self.below_since = None
            self.status = target
        else:
            self.below_since = self.below_since or at
            if at - self.below_since >= timedelta(minutes=5):
                self.status = Status.WATCH if self.status == Status.ALERT else Status.NORMAL
                self.below_since = None
        return self.status

    def watchdog(self, now: datetime, started_at: datetime) -> Status:
        if now - (self.last_valid or started_at) >= timedelta(minutes=3):
            self.status = Status.NO_DATA
            self.below_since = None
        return self.status


def quality(
    payload: Payload,
    previous: tuple[datetime, float] | None = None,
    rate_exceeded: bool = False,
    now: datetime | None = None,
) -> str:
    depth, rain = payload.water_depth_cm, payload.rain_mm5min
    suspect = rate_exceeded or (depth is not None and not 0 <= depth <= 150)
    suspect |= rain is not None and not 0 <= rain <= 100
    suspect |= (now or datetime.now(UTC)) - payload.captured_at >= timedelta(minutes=3)
    if previous and depth is not None:
        elapsed = (payload.captured_at - previous[0]).total_seconds()
        suspect |= elapsed <= 0 or (elapsed <= 90 and abs(depth - previous[1]) > 30)
    return "suspect" if suspect else "ok"
