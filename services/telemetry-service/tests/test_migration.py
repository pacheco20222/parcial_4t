import os
import subprocess
import sys
from pathlib import Path


def test_migration_offline_sql(tmp_path):
    secret = tmp_path / "password"
    secret.write_text("offline-render-only")
    service = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=service,
        env={**os.environ, "DATABASE_PASSWORD_FILE": str(secret)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    for table in ["alembic_version", "monitoring_point", "device", "raw_reading", "clean_reading", "forecast"]:
        assert f"CREATE TABLE telemetry.{table}" in result.stdout
    assert "public.create_hypertable" in result.stdout
    assert "PRIMARY KEY (message_id, captured_at)" in result.stdout
    for number in range(1, 6):
        assert f"DEV-P{number:02}-A" in result.stdout
        assert f"Punto simulado P{number:02}" in result.stdout
    assert "offline-render-only" not in result.stdout
