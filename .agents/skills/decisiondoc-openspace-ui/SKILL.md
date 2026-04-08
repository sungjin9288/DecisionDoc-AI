---
name: decisiondoc-openspace-ui
description: Improve the static and PWA shell in DecisionDoc-AI. Use for work under app/static, offline/empty/export-adjacent views, and visual polish guided by DESIGN.md without changing core API, approval, tenant, or security semantics.
---

# DecisionDoc OpenSpace UI

## Required Context

1. `AGENTS.md`
2. `README.md`
3. `docs/architecture.md`
4. `docs/security_policy.md`
5. `DESIGN.md` when it exists
6. the touched static files and their directly related tests

## Working Rules

- Limit changes to static shell, PWA assets, and presentation-oriented flows.
- Treat `DESIGN.md` as visual guidance only, not as architecture or policy authority.
- Do not change API contracts, auth flows, tenant boundaries, or approval semantics from static UI work.
- Preserve accessibility and PWA basics such as manifest, icons, offline fallback, and clear status communication.

## Typical Touch Points

- `app/static/index.html`
- `app/static/offline.html`
- `app/static/manifest.json`
- `app/static/sw.js`
- `app/static/icons/`
- related UI or PWA tests

## Verification

- Run the narrowest relevant UI/PWA tests first.
- If no dedicated UI tests exist for the touched area, report that clearly instead of guessing.

## Close-Out

Report touched static files, any `DESIGN.md` influence, tests run, and any remaining browser-only checks not executed.
