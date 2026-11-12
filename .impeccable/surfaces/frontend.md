---
version: 1
slug: "frontend"
primary_target: "frontend"
related_targets: []
---

Scope: Angular SPA in frontend/ — operator console (Operate mode, desktop-first, must work at 375 px), citizen public view, supervisor/admin views. Spanish UI.

Audience/job: municipal operator/supervisor sees which points need action and acts (alerts, work orders, crews); citizen checks status and reports.

## Direction contract

THESIS: The city's worst current status owns the screen as a full-width signal band; points live on an alert ladder people already know from hurricane season. Refuses the grey SaaS card grid with a status pill lost in a corner.

OWN-WORLD: Bulletin white ground #f7f7f4, ink #101820 header, solid signal fields green #2e7d32, amber #f2b705, red #d6402a, slate hatched grey #6b7280 for Sin datos. Barlow Condensed uppercase headings and huge tabular KPI numerals, Barlow body. Square corners, 1px hairlines, 4px top rule on KPI tiles, glyph per status (▲ Alerta, ◆ Vigilancia, ● Normal, ■ Sin datos). No official seals.

STORY: Operator reads the band (is anything wrong?), the ladder (which points), KPIs (how bad, how fast are we responding), then acts on alerts and work orders one click away. Updates live without reload.

FIRST VIEWPORT: Ink top bar with wordmark, nav, user chip; 56px status band in worst-status colour with plain sentence and "En vivo"; 3 columns: alert ladder 280px | KPI row of 5 + Leaflet map | alerts feed + work orders 360px. "Datos simulados" label visible. On phone: band, ladder, KPIs stack; nav collapses.

FORM: Semáforo de Protección Civil (civil-protection alert ladder), my top-ranked grounded candidate (#1), chosen as IMPECCABLE'S PICK. seed:fe1d00f78d704329

Signature interaction: band and ladder re-sort live when a point changes status (rung transition, band colour change), respecting prefers-reduced-motion.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
