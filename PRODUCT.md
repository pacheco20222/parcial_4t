# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primary: municipal operator / supervisor** (roles `Operator` < `Supervisor` < `Admin`) supervising flood-prone points in Mérida during storms. Primary scene: **desktop in a control room** (long sessions, often at night). Phone use (remote supervision) must work at 375 px, but desktop gets the design priority.
- **Secondary: citizen** (anonymous) checking whether a nearby street is flooded and submitting a report from a phone.
- **Admin**: user management, audit log, link to SOC console (Grafana `/soc/`).

## Product Purpose

**Alerta Pluvial Mérida** is an early-warning and response dashboard: simulated IoT water-depth sensors → live point status (Normal / Watch / Alert / NoData) → automatic alerts and work orders with SLA → crews dispatched and tracked. Success = operators see a status change within seconds without reloading, and can act on it (assign crew, move a work order) from desktop or phone.

University Alpha prototype (SIS4415, Segundo Parcial). Evaluated live in a 6-minute demo; rubric criterion 2 rewards real-time KPIs, responsive/mobile, and demonstrable remote supervision.

## Positioning

Closes the loop from sensor to crew: a status change automatically opens an alert and a work order with an SLA, and the KPI "alert → crew on site" measures response time. Not just a map of sensors.

## Operating Context

- Backend exists and is fixed (see docs/frontend-handoff.md, docs/contracts.md): REST via `/api/telemetry` and `/api/ops`, SignalR `/hubs/live`, cookie auth with CSRF header.
- Demo uses `SCENARIO=storm` so points escalate Normal → Watch → Alert in minutes.
- 5 fictitious monitoring points (P01–P05) in Mérida zones (Centro, Norte, Oriente, …).

## Capabilities and Constraints

- UI copy in Spanish (México); code in English.
- All data is simulated: a visible "datos simulados" disclaimer is required.
- `NoData` means a stale sensor: show "sin datos", never 0.
- Strict CSP (self only; OSM tiles for maps); no external CDNs, fonts must be bundled.
- Work order flow: Open → Assigned → InProgress → Resolved → Closed, or Open → Cancelled; optimistic concurrency (`version`, 409).
- Citizen reports: no personal data collected; rate-limited.

## Brand Commitments

- Name: **Alerta Pluvial Mérida**. Fictitious; must not imitate the real Ayuntamiento de Mérida identity (no official seal, logos, or colors presented as official).

## Evidence on Hand

- Live backend data only (simulated). No real users, testimonials, or official endorsements exist; do not fabricate them.

## Product Principles

1. Status first: the state of each point and what needs action must be readable at a glance.
2. Live, not refreshed: every number updates from the event stream; stale data is labeled as stale.
3. Act where you look: the alert, its work order, and the crew action are one step apart.
4. Honest prototype: simulated data is always labeled as such.

## Accessibility & Inclusion

- Status must never rely on color alone (label + icon/shape); WCAG AA contrast; keyboard operable; respect `prefers-reduced-motion`.
