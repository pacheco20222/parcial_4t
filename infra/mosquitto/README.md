# MQTT broker

Compose starts Mosquitto non-root with this config and ACL, TLS listener 8883
only. `/run/secrets/{ca.crt,mqtt_server.crt,mqtt_server.key,mosquitto_passwd}`
are required; bootstrap generates these. `TZ=UTC` makes log timestamps UTC.
Devices publish only their own `merida/flood/P0n/DEV-P0n-A/telemetry` topic;
`svc-telemetry` subscribes to `merida/flood/+/+/telemetry`. QoS 1 clients.
Connection/auth/ACL logs go to stdout for T5 parsing. No host ports.

Run: `docker compose up -d mosquitto` after bootstrap. Offline ACL/config tests:
`services/telemetry-service/.venv/bin/python -m unittest discover -s scripts/tests -p test_compose.py -v`.
Authenticated TLS/ACL checks require Docker; socket health is liveness only.
