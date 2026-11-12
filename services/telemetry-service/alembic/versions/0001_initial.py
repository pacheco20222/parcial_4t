"""Telemetry tables, Timescale hypertable and fictitious monitoring points."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitoring_point",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("zone", sa.String(32), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("watch_threshold_cm", sa.Float(), nullable=False),
        sa.Column("alert_threshold_cm", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "0 < watch_threshold_cm AND watch_threshold_cm < alert_threshold_cm AND alert_threshold_cm <= 150"
        ),
        schema="telemetry",
    )
    op.create_table(
        "device",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("point_id", sa.String(16), sa.ForeignKey("telemetry.monitoring_point.id"), nullable=False),
        sa.Column("fw_version", sa.String(64), nullable=False),
        sa.Column("calibrated_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False),
        schema="telemetry",
    )
    op.create_table(
        "raw_reading",
        sa.Column("message_id", pg.UUID(), primary_key=True),
        sa.Column("device_id", sa.String(32), sa.ForeignKey("telemetry.device.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        schema="telemetry",
    )
    op.create_table(
        "clean_reading",
        sa.Column("message_id", pg.UUID(), primary_key=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("point_id", sa.String(16), sa.ForeignKey("telemetry.monitoring_point.id"), nullable=False),
        sa.Column("device_id", sa.String(32), sa.ForeignKey("telemetry.device.id"), nullable=False),
        sa.Column("water_depth_cm", sa.Float()),
        sa.Column("rain_mm5min", sa.Float()),
        sa.Column("quality_flag", sa.String(16), nullable=False),
        schema="telemetry",
    )
    op.create_table(
        "forecast",
        sa.Column("point_id", sa.String(16), sa.ForeignKey("telemetry.monitoring_point.id"), primary_key=True),
        sa.Column("forecast_for", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("precip_mm", sa.Float()),
        schema="telemetry",
    )
    op.execute("SELECT public.create_hypertable('telemetry.clean_reading', 'captured_at', if_not_exists => TRUE)")
    for table, name, columns in [
        ("device", "ix_telemetry_device_point_id", ["point_id"]),
        ("raw_reading", "ix_telemetry_raw_reading_device_id", ["device_id"]),
        ("raw_reading", "ix_telemetry_raw_reading_captured_at", ["captured_at"]),
        ("clean_reading", "ix_clean_point_time", ["point_id", "captured_at"]),
        ("clean_reading", "ix_clean_device_time", ["device_id", "captured_at"]),
    ]:
        op.create_index(name, table, columns, schema="telemetry")
    points = sa.table(
        "monitoring_point",
        sa.column("id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("zone", sa.String()),
        sa.column("lat", sa.Float()),
        sa.column("lon", sa.Float()),
        sa.column("watch_threshold_cm", sa.Float()),
        sa.column("alert_threshold_cm", sa.Float()),
        sa.column("status", sa.String()),
        sa.column("simulated", sa.Boolean()),
        schema="telemetry",
    )
    devices = sa.table(
        "device", *(sa.column(c, sa.String()) for c in ["id", "point_id", "fw_version", "status"]), schema="telemetry"
    )
    coords = [(20.967, -89.623), (21.025, -89.620), (20.971, -89.570), (20.976, -89.680), (20.920, -89.620)]
    for n, (zone, (lat, lon)) in enumerate(
        zip(["Centro", "Norte", "Oriente", "Poniente", "Sur"], coords, strict=True), 1
    ):
        point_id = f"P{n:02}"
        op.bulk_insert(
            points,
            [
                {
                    "id": point_id,
                    "name": f"Punto simulado {point_id} — {zone}",
                    "zone": zone,
                    "lat": lat,
                    "lon": lon,
                    "watch_threshold_cm": 15,
                    "alert_threshold_cm": 25,
                    "status": "Normal",
                    "simulated": True,
                }
            ],
        )
        op.bulk_insert(
            devices, [{"id": f"DEV-{point_id}-A", "point_id": point_id, "fw_version": "1.0.0", "status": "Active"}]
        )


def downgrade() -> None:
    for table in ["forecast", "clean_reading", "raw_reading", "device", "monitoring_point"]:
        op.drop_table(table, schema="telemetry")
