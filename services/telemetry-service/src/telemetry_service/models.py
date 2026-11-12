from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, MetaData, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(schema="telemetry")


class MonitoringPoint(Base):
    __tablename__ = "monitoring_point"
    __table_args__ = (
        CheckConstraint(
            "0 < watch_threshold_cm AND watch_threshold_cm < alert_threshold_cm AND alert_threshold_cm <= 150"
        ),
    )
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    zone: Mapped[str] = mapped_column(String(32))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    watch_threshold_cm: Mapped[float] = mapped_column(default=15)
    alert_threshold_cm: Mapped[float] = mapped_column(default=25)
    status: Mapped[str] = mapped_column(String(16), default="Normal")
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)


class Device(Base):
    __tablename__ = "device"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    point_id: Mapped[str] = mapped_column(ForeignKey("telemetry.monitoring_point.id"), index=True)
    fw_version: Mapped[str] = mapped_column(String(64), default="1.0.0")
    calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="Active")


class RawReading(Base):
    __tablename__ = "raw_reading"
    message_id: Mapped[UUID] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("telemetry.device.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class CleanReading(Base):
    __tablename__ = "clean_reading"
    __table_args__ = (
        Index("ix_clean_point_time", "point_id", "captured_at"),
        Index("ix_clean_device_time", "device_id", "captured_at"),
    )
    message_id: Mapped[UUID] = mapped_column(primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    point_id: Mapped[str] = mapped_column(ForeignKey("telemetry.monitoring_point.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("telemetry.device.id"))
    water_depth_cm: Mapped[float | None] = mapped_column(Float)
    rain_mm5min: Mapped[float | None] = mapped_column(Float)
    quality_flag: Mapped[str] = mapped_column(String(16))


class Forecast(Base):
    __tablename__ = "forecast"
    point_id: Mapped[str] = mapped_column(ForeignKey("telemetry.monitoring_point.id"), primary_key=True)
    forecast_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    precip_mm: Mapped[float | None] = mapped_column(Float)
