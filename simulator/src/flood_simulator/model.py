"""Deterministic simulated runoff, not a predictive flood model."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

SCENARIOS = {"dry", "light_rain", "storm", "sensor_fault", "cycle"}


@dataclass(frozen=True)
class Station:
    point_id: str
    catchment: float
    drainage_cm_min: float

    @property
    def device_id(self) -> str:
        return f"DEV-{self.point_id}-A"


STATIONS = tuple(
    Station(f"P{i:02}", catchment, drainage)
    for i, (catchment, drainage) in enumerate(
        [(1.2, 6.9), (1.1, 6.4), (1.0, 5.9), (0.9, 5.3), (0.8, 4.8)], 1
    )
)


def rain_intensity(scenario: str, elapsed: float) -> float:
    """Rain in mm/hour; cycle: 2m dry, 5m light, 7m storm, 16m drain."""
    if scenario not in SCENARIOS or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("invalid scenario or elapsed time")
    if scenario == "cycle":
        minute = (elapsed % 1800) / 60
        return 0.0 if minute < 2 or minute >= 14 else (30.0 if minute < 7 else 120.0)
    return {"dry": 0.0, "light_rain": 30.0, "storm": 120.0, "sensor_fault": 30.0}[
        scenario
    ]


def advance_depth(depth: float, rain_mm_hour: float, seconds: float, station: Station) -> float:
    """Runoff concentration minus per-point drainage/elevation effect, cm."""
    if any(not math.isfinite(x) or x < 0 for x in (depth, rain_mm_hour, seconds)):
        raise ValueError("model inputs must be finite and nonnegative")
    rate = rain_mm_hour * 0.09 * station.catchment - station.drainage_cm_min
    return max(0.0, depth + max(-30.0, min(30.0, rate)) * seconds / 60)


def silent(scenario: str, station: Station, elapsed: float) -> bool:
    return scenario == "sensor_fault" and station.point_id == "P01" and 60 <= elapsed < 360


def null_depth(scenario: str, station: Station, elapsed: float) -> bool:
    return scenario == "sensor_fault" and station.point_id == "P02" and int(elapsed) % 420 < 60


def topic(station: Station) -> str:
    if station not in STATIONS:
        raise ValueError("unknown station")
    return f"merida/flood/{station.point_id}/{station.device_id}/telemetry"


def build_payload(
    station: Station, depth: float | None, rain_mm5min: float | None,
    captured_at: datetime, message_id: UUID, battery: int = 98,
) -> dict:
    if station not in STATIONS:
        raise ValueError("unknown station")
    for value in (depth, rain_mm5min):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("reading must be finite and nonnegative")
    if type(battery) is not int or not 0 <= battery <= 100:
        raise ValueError("invalid battery")
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("capturedAt must be timezone aware")
    return {
        "messageId": str(UUID(str(message_id))),
        "deviceId": station.device_id,
        "pointId": station.point_id,
        "capturedAt": captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "waterDepthCm": round(depth, 3) if depth is not None else None,
        "rainMm5min": round(rain_mm5min, 3) if rain_mm5min is not None else None,
        "batteryPct": battery,
        "fwVersion": "sim-1.0.0",
    }


def rain_last_five_minutes(scenario: str, elapsed: float) -> float:
    """Accumulated mm over the preceding five minutes since simulation start."""
    rain_intensity(scenario, elapsed)  # Validate before entering the integration loop.
    start = max(0.0, elapsed - 300)
    total = 0.0
    while start < elapsed:
        end = min(start + 1, elapsed)
        total += rain_intensity(scenario, (start + end) / 2) * (end - start) / 3600
        start = end
    return total
