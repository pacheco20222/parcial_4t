# Alerta Pluvial Mérida — frontend

Angular 22 standalone SPA for the academic flood-monitoring prototype. Spanish UI; simulated readings are always labeled. Runtime dependencies are already installed and pinned in `package.json` / `package-lock.json`; this implementation adds or upgrades none.

From `frontend/`:

```sh
npx ng serve
npx ng lint
npx ng test --watch=false
npx ng build
```

Development serves at `http://localhost:4200`. `proxy.conf.json` forwards `/api`, `/hubs`, and `/soc` to `https://localhost:8443`; the backend must be running separately. Production output is `dist/alerta-pluvial/browser`. No e2e runner is configured.

`angular.json` disables Angular's persistent cache (`cli.cache.enabled: false`) because the installed native LMDB cache crashed in this environment. Re-enable it after the upstream environment issue is fixed. Production disables inline critical CSS and font fetching to preserve the gateway CSP; fonts are bundled locally. Caddy must render the nonce placeholder in `src/index.html` for production component styles.

## Structure

- `src/app/core/api`: response and live-event interfaces.
- `src/app/core/auth`, `http`: cookie-backed session, role guards, CSRF header, single-flight refresh and retry. Tokens never enter JavaScript storage.
- `src/app/core/live`: one SignalR connection, reconnect state and bounded initial retries.
- `src/app/core/state`: signal stores, live merges, reconnect reloads, KPI debounce, formatting helpers.
- `src/app/shared`: SVG icons, status band, Leaflet map with OpenStreetMap attribution.
- `src/app/features`: public map/report form, login/MFA, operator shell/panel, point history and forecast, alerts, work-order board, citizen-report moderation, crews, users, audit and account/MFA enrollment.
- `src/styles/_tokens.scss`, `DESIGN.md`, `.impeccable/design.json`: visual tokens and documented design system.

REST and hub contracts: `../docs/frontend-handoff.md` and `../docs/contracts.md`. Route guards provide navigation UX; backend authorization remains authoritative.

Unit tests use Vitest and Angular HTTP testing to verify session behavior, concurrent refresh, store merges, Spanish labels, chart scales, threshold validation, work-order transitions/concurrency, report moderation, MFA/QR enrollment and UI contracts. Local lint/test/build evidence does not establish backend integration, deployed CSP behavior, OSM tile availability, SignalR delivery, or browser layout/accessibility. Desktop and 375 px browser captures remain pending; no connected browser was available during this implementation. The design review is source-only, with recapture required before a visual ship verdict.

Known backend limits: `GET /crews` currently requires Supervisor, despite the handoff listing Operator access. Operators cannot resolve crew names or browse crews until backend authorization is aligned. MFA enrollment refreshes `/auth/me`; backend activation revokes refresh families without replacing cookies, so a later refresh may require signing in again. Alert-level filtering applies to the current server page because the API only filters status and point; the UI states that scope.
