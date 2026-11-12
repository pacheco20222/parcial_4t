# PostgreSQL init

Compose mounts `10-init.sh` as `/docker-entrypoint-initdb.d/10-flood-init.sh`; runs once on an
empty volume. Creates TimescaleDB, isolated schema owners and search paths for
DB `flood`; revokes PUBLIC database/schema privileges. No cross-schema grants.
Reads `/run/secrets/telemetry_db_password` and `ops_db_password` using psql
literal variables; `POSTGRES_USER`/`POSTGRES_DB` select the init connection.
Port 5432 is internal. No application events.

Check: `bash -n infra/postgres/10-init.sh`. Real role, extension and migration
checks need Docker; see `../README.md`, including Timescale public API access.
