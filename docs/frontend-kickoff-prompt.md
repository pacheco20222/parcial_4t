# Frontend kickoff prompt

Paste into a new Claude Code session at the repo root (branch off `main` first: `git switch -c frontend`).

```text
We're starting the frontend phase of this project. Read CLAUDE.md, project.md (rubric criterion 2),
architecture.md §8, docs/frontend-handoff.md and docs/contracts.md before anything else.

Goal: build the Angular SPA in frontend/ against the existing, working backend (do not change backend
contracts; if something is missing, list it and ask). Act as the senior Angular engineer persona from CLAUDE.md.

Process:
1. Start the backend (bootstrap.sh, docker compose up, smoke.py) and explore the live API/SignalR.
2. Design first: use the impeccable, ui-ux-pro-max, frontend-design and design-motion-principles skills
   to propose a visual direction for a municipal flood early-warning dashboard (calm, trustworthy,
   high-contrast status colors Normal/Watch/Alert/NoData, mobile-first, Spanish UI). Show me 2 directions
   and let me pick before building.
3. Plan the app (routes, state with signals, services, HTTP interceptor for X-Requested-With + 401 refresh,
   SignalR service with reconnect + refetch) and the views in the handoff: citizen, operator, supervisor/admin.
4. Delegate substantial implementation to Codex subagents (their sandbox has no network/Docker: you run
   npm install and docker; Codex writes code and runs tests offline). Review every diff.
5. Integrate with Caddy + CI + Dependabot per the "Definition of done" in docs/frontend-handoff.md.
6. Verify in a real browser at 375 px and desktop: login, live map/KPIs updating without reload during
   SCENARIO=storm, work order actions, citizen report. Then commit on the branch and open a PR to main.
```
