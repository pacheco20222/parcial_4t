#!/usr/bin/env bash
set -euo pipefail
# psql quotes :'variables' as SQL literals; values never enter SQL source/argv.
# Environment is confined to this init-only psql process; never enable tracing.
TELEMETRY_DB_PASSWORD="$(cat /run/secrets/telemetry_db_password)" \
OPS_DB_PASSWORD="$(cat /run/secrets/ops_db_password)" \
psql -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<'SQL'
\getenv telemetry_password TELEMETRY_DB_PASSWORD
\getenv ops_password OPS_DB_PASSWORD
BEGIN;
CREATE EXTENSION IF NOT EXISTS timescaledb;
REVOKE ALL ON DATABASE flood FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE ROLE telemetry_svc LOGIN PASSWORD :'telemetry_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE ops_svc LOGIN PASSWORD :'ops_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT CONNECT ON DATABASE flood TO telemetry_svc, ops_svc;
CREATE SCHEMA telemetry AUTHORIZATION telemetry_svc;
CREATE SCHEMA ops AUTHORIZATION ops_svc;
REVOKE ALL ON SCHEMA telemetry, ops FROM PUBLIC;
-- TimescaleDB API (create_hypertable, time_bucket) lives in public: usage only, telemetry role only.
GRANT USAGE ON SCHEMA public TO telemetry_svc;
ALTER ROLE telemetry_svc IN DATABASE flood SET search_path = telemetry, public;
ALTER ROLE ops_svc IN DATABASE flood SET search_path = ops;
COMMIT;
SQL
