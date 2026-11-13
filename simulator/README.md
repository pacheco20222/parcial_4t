# Flood simulator (T4)

Five fictitious Mérida stations, P01–P05 / DEV-P01-A–DEV-P05-A.
Simulated data demonstrates the pipeline; it does not predict flooding.
One TLS MQTT client and credential per device; QoS 1, no retained messages.

From `simulator/`, using the prepared environment:

```sh
.venv/bin/python -m flood_simulator
.venv/bin/pytest -q
.venv/bin/ruff check .
```

| Variable | Default / meaning |
|---|---|
| `MQTT_HOST` | `mosquitto`; only this TLS hostname is accepted |
| `MQTT_PORT` | `8883` |
| `MQTT_CA_FILE` | `/run/secrets/ca.crt`, trusted broker CA |
| `MQTT_DEVICES_FILE` | `/run/secrets/mqtt_devices.json`, JSON device/password map for all five devices |
| `SCENARIO` | `cycle`; also `dry`, `light_rain`, `storm`, `sensor_fault` |
| `INTERVAL_SECONDS` | `60`, finite and ≥ 1; real seconds, not a simulation speed multiplier |
| `SEED` | Optional integer; reproduces per-point rain variation and batteries |

Mount secrets read-only under `/run/secrets`; never put passwords in env vars.
The broker certificate must cover `mosquitto`, which must resolve on the lab network.
TLS CA and hostname verification remain enabled. Clients reconnect with backoff
bounded at 1–30 seconds, bounded queues and five-second connection timeouts.
SIGINT/SIGTERM stops publishing and closes every client. Offline readings are skipped.

`cycle` repeats every 30 minutes: 2 dry, 5 light rain, 7 storm, 16 drain-down.
Runoff concentration and point-specific drainage/elevation factors produce distinct,
nonnegative depths with changes capped at 30 cm/min. Cycle reaches Watch (15 cm),
Alert (25 cm), then drains early enough for five-minute downward hysteresis.
The telemetry service owns status transitions. `rainMm5min` integrates the preceding
five minutes, including partial windows at startup. `sensor_fault` silences P01
from minute 1 through minute 6 and sends null P02 depth for one minute every seven
minutes. Other stations keep sending; missing readings are never replaced with zero.

Publishes `merida/flood/{pointId}/{deviceId}/telemetry`, using contracts §5:
`messageId` UUID, `deviceId`, `pointId`, UTC `capturedAt`, `waterDepthCm`,
`rainMm5min`, integer `batteryPct`, `fwVersion`. No HTTP endpoints or inbound ports.
JSON stdout logs include `ts`, `level`, `service`, `event`; credentials never logged.
Transport events use `mqtt.*`; simulator events use `simulator.*`.

## Simulated citizen reports

`docker compose up -d citizen-bot` runs the same image with
`python -m flood_simulator.citizen_bot`. No secrets or inbound ports; `app_net` only.
Uses stdlib HTTP: GET `http://telemetry-service:8000/public/points`, then POST
`http://ops-service:8080/public/reports` with the required CSRF header.

- `CITIZEN_BOT_ENABLED=true` (default); `false` keeps the process idle.
- `CITIZEN_BOT_MIN_INTERVAL_SECONDS=150` (default and minimum), plus 0–30 s jitter.
- Alert/Watch selections are weighted 8:3; approximately 10% of selections use
  Normal points when both groups exist. NoData points are skipped. Reports use
  varied Mexican Spanish, generic street references and occasional duplicates.
- GET retries at most three times, HTTP timeout 10 s; POST is never retried
  immediately. HTTP 429 waits at least 600 s (numeric Retry-After respected up
  to 3600 s). SIGTERM interrupts waits; in-flight HTTP finishes within its timeout.
- JSON log events: `citizen_bot.report_sent`, `citizen_bot.skipped`,
  `citizen_bot.error`; report descriptions and HTTP error bodies are never logged.

Run `.venv/bin/pytest -q tests/test_citizen_bot.py` for focused offline tests.
Orchestrator must verify report creation and rate limits in Compose.

## Lab attack demo

Own lab only. Refuses before reading secrets or connecting unless confirmed:

```sh
ATTACK_SIM_CONFIRM=lab ATTACK_SCENARIO=all \
  .venv/bin/python -m flood_simulator.attack_sim
```

Same TLS settings and mounted secrets. `ATTACK_SCENARIO`:

- `bruteforce`: eight wrong DEV-P01-A logins, 0.5 seconds apart (SR-02).
- `acl_violation`: DEV-P02-A publishes to P01's telemetry and fake command topic (SR-03).
- `flood`: DEV-P01-A sends 30 distinct messages across ten seconds (SR-04).
- `spoof`: P01's topic carries DEV-P02-A / P02 identity (`telemetry.topic_mismatch`).
- `foreign_network`: valid DEV-P03-A sends one P03 reading via IDMZ (SR-01).
- `all`: runs those five sequentially, then exits.

`foreign_network` connects TCP to `ATTACK_IDMZ_BROKER_HOST` (default `172.30.20.10`),
restricted to usable IPv4 hosts in lab `172.30.20.0/24`. Keep `MQTT_HOST=mosquitto`:
a local Paho socket override routes TCP to the IP while TLS SNI/hostname verification
remain `mosquitto`, with CA verification required and `tls_insecure_set(False)`.
No global DNS/socket patches. Both `ot_net` and `idmz_net` attachments are required;
confirm IDMZ source in broker logs. Tests exercise installed Paho's socket/TLS path
with network I/O mocked; live source routing and alerts require Compose verification.

Attack clients disable reconnects; connection responses wait at most eight seconds.
Publish waits are bounded (0.2 seconds for flood, three seconds otherwise).
`attack.*` logs describe attempts; MQTT v5 PUBACK rejection logs
`mqtt.publish_denied`. Broker and telemetry logs establish actual detections;
client completion alone does not prove an ACL denial or a SIEM alert. Broker outages
may prevent delivery; no unbounded retry or flood loop. SIGTERM stops remaining attempts.

## Container handoff

Build context: `simulator/`. Dockerfile pins Python 3.13.9 slim-bookworm and uv 0.13.1,
runs `uv sync --frozen --no-dev`, then uses UID/GID 10001 with no exposed ports.
Default command runs telemetry; reuse image for attack-sim with Compose command
`["python", "-m", "flood_simulator.attack_sim"]`, confirmation env and lab-only profile.
Attach OT and IDMZ networks for attack-sim; mount CA and device secrets readable by UID 10001. No new deps.
Orchestrator must build/run the image and verify broker auth, ACL denials, reconnect,
NoData/status transitions and SR-01/02/03/04 in the complete Compose stack.
