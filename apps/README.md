# GreenPlan applications

Phase 2 starts with two independently testable services:

- `api` — FastAPI domain API and OpenAPI contract;
- `web` — Next.js workspace and server-side BFF.

## Local checks

```bash
cd apps/api
UV_CACHE_DIR=.uv-cache uv sync --all-groups
UV_CACHE_DIR=.uv-cache uv run pytest

cd ../web
npm ci
npm test
npm run typecheck
npm run build
```

The Next.js production build explicitly uses webpack because Turbopack's CSS worker opens an internal IPC port which is unavailable in restricted build environments.

## Current data mode

The first executable slice uses deterministic in-process fixtures for the two pilots. They exist to freeze T2.2–T2.6 contracts and are visibly synthetic. PostGIS repository integration and isolated database tests remain T2.1/T2.4 work; production data is not read or modified by these fixtures.
