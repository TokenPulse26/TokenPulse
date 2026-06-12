# TokenPulse Dashboard (TypeScript)

The new web dashboard — replaces `web-dashboard.py`, talks directly to the
Rust proxy's JSON API, and shares design tokens with tokenpulse.to.

## Status

Milestone 1: Overview page — proxy status, stat cards, model/project
breakdowns, recent requests, with today/7d/30d/all range switching.
Data polls every 10–15s.

Not yet ported from the Python dashboard: budgets (CRUD), spend chart,
activity heatmap, forecast, optimizer, context audit, reliability panel,
insights, CSV export. The proxy still needs API endpoints for several of
those (budget CRUD, forecast, optimizer, CSV) — they currently only exist
in `web-dashboard.py`.

## Dev

```sh
npm install
npm run dev      # http://localhost:5173 (note: may bind IPv6 ::1 only)
```

The dev server proxies `/api` and `/health` to the Rust proxy at
`127.0.0.1:4100` (override with `TOKENPULSE_PROXY_URL`), so the TokenPulse
proxy must be running. No CORS setup needed — the browser only talks to
the dev server.

## Build

```sh
npm run build    # type-checks, then emits frontend/dist/
```

End state (not wired up yet): the Rust proxy serves this build directly,
and the Tauri shell points at it — replacing both the Python dashboard on
port 4200 and the static fallback page in the repo-root `dist/`.

## Design tokens

`src/index.css` `@theme` block mirrors `tokenpulse-site/style.css`
(`--bg #0a0a0a`, accent `#00d4aa`, Inter). Keep them in sync when the site
changes.
