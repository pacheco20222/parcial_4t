#!/bin/sh
set -eu
alembic upgrade head
exec telemetry-service
