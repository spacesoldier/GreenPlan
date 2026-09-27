# Phase 2 — checkpoint 01: API/BFF/UI contracts

- Status: Verified checkpoint; Phase 2 remains In progress
- Date: 2026-09-25
- Data mode: deterministic fixtures, not production PostGIS

## Delivered

- `apps/api`: FastAPI application, typed DTO, stable error envelope and repository protocol;
- all read-only routes listed in the Phase 2 minimal API;
- two deterministic pilot fixtures with explicit project/revision/model identities;
- bbox and layer filtering, preservation of `needs_review`, object provenance and conflicting evidence;
- `apps/web`: Next.js App Router workspace with server-side BFF;
- three-panel project workspace, source/layer navigation, SVG 2D scene, picking, inspector, evidence and 2D/3D state;
- URL state for project, object and view;
- Docker images and Compose services on ports `38100` and `38101`;
- pinned runtimes and lock files.

## Test-first evidence

The API tests were created before `greenplan_api` existed. The initial expected failure was `ModuleNotFoundError: greenplan_api`. After implementation:

```text
apps/api: 13 passed
apps/web: 3 passed
TypeScript: passed
Next.js production build: passed (webpack)
npm audit: 0 vulnerabilities
```

The BFF tests prove correlation-id forwarding, typed upstream errors, path traversal rejection and removal of browser cookies/authorization before calling the domain API. Static client bundles were searched for the internal FastAPI hostname and database secret markers; none were found.

## Runtime evidence

```text
greenplan-platform-api-1  healthy  0.0.0.0:38100->8000
greenplan-platform-web-1 running  0.0.0.0:38101->3000
GET http://127.0.0.1:38100/health/ready              200
GET http://127.0.0.1:38100/v1/projects               200, two pilots
GET http://127.0.0.1:38101/api/domain/v1/projects    200, two pilots
GET http://127.0.0.1:38101/                           200
```

Turbopack was not used for the production build: its CSS worker tries to bind an internal IPC port and fails in the restricted build environment. `next build --webpack` succeeds and is the pinned build command for this checkpoint.

## Honest limitations

- `GREENPLAN_DATA_MODE=fixture` is the only implemented repository mode and is validated at startup;
- the fixtures express API semantics but are not claimed to be imported geometry from the pilot DWG files;
- SVG is a deterministic scene adapter proof, not the final deck.gl renderer;
- 3D currently proves shared application state only and does not render glTF/Three.js geometry;
- browser E2E has not been added yet.

## Next work package

1. Write isolated PostGIS migration/repository tests using a separate PGDATA.
2. Add idempotent pilot fixture ingestion into PostGIS.
3. Implement `PostgisRepository` for the same repository protocol.
4. Run the existing 13 API tests against PostGIS and add spatial SQL assertions.
5. Add browser E2E for deep-link reload, layer toggle, picking and error state.
6. Replace the bounded SVG proof with the renderer selected by the two-pilot spike.
