# Phase 2 — Read-only application vertical slice

- Status: In progress
- Target: first runnable web/API application on two pilots
- Owners: backend, frontend, data ingestion

## Outcome

Пользователь открывает список проектов, выбирает Песчаный переулок или Куликовскую улицу и получает read-only 2D workspace: дерево источников, канонические слои/объекты, свойства, provenance и статус качества. Приложение запускается одной документированной Compose-командой.

## ADR prerequisites

Приняты и обязательны ADR-0003, ADR-0004, [ADR-0007 — web boundaries и downstream viewers](../adr/0007-web-application-boundaries.md) и [ADR-0008 — test pyramid](../adr/0008-test-pyramid-and-contract-gates.md).

## Pinned runtimes for the first vertical slice

- Python 3.12;
- FastAPI 0.141.1;
- psycopg 3.3.6;
- Node.js 24 LTS in containers; local Node.js 25 is acceptable only for development checks;
- Next.js 16.3.5;
- React 19.3.0;
- PostgreSQL 16 + PostGIS 3.5.

## Scope

- monorepo/application layout для `apps/api` и `apps/web`;
- FastAPI health/readiness, settings, SQLAlchemy/psycopg boundary и OpenAPI;
- Next.js application shell и BFF;
- workspace/project/model navigation;
- pilot fixture ingestion в PostGIS с явным model/version/CRS status;
- endpoints project summary, source tree, scene manifest, bbox features, object/evidence;
- read-only 2D renderer с pan/zoom/picking и layer visibility;
- deep link выбранного project/model/object;
- loading/empty/error/needs-review states;
- local developer commands и CI-equivalent test command.

## Out of scope

- OSM acceptance/rejection mutations;
- rule approval и rule-set publication;
- генерация посадок и DXF export;
- полноценный 3D;
- arbitrary CAD editing;
- production authentication provider — используется replaceable development identity boundary.

## Contracts to freeze before code

### Repository/runtime

```text
apps/api/       FastAPI domain service
apps/web/       Next.js application and BFF
packages/       generated/shared contracts only where justified
tests/fixtures/ small deterministic pilot fixtures
```

### Minimal API

```text
GET /health/live
GET /health/ready
GET /v1/projects
GET /v1/projects/{project_id}
GET /v1/projects/{project_id}/models
GET /v1/project-revisions/{revision_id}/source-tree
GET /v1/models/{model_id}/scene-manifest
GET /v1/models/{model_id}/features?bbox=&layers=&lod=
GET /v1/objects/{object_id}
GET /v1/objects/{object_id}/evidence
```

Responses always carry explicit resource/model version. Feature endpoint rejects an absent bbox unless the requested model is below a documented small-size threshold.

## Tests written before implementation

### T2.1 — Migration and repository contract

- empty test PostGIS applies migrations 001–005;
- application DB role can read API views but cannot mutate approved model;
- test never mounts production `platform/data/postgis`.

### T2.2 — API schema and health

- OpenAPI contains all Phase 2 routes and stable error envelope;
- liveness does not depend on DB; readiness fails when DB is unavailable;
- invalid UUID/bbox/LOD produces typed 4xx, not internal SQL error.

### T2.3 — Project/model versioning

- project list returns both pilots from fixtures;
- project detail exposes revision, model UUID, assembly status and CRS status;
- no endpoint silently substitutes a newer model when explicit model id was requested.

### T2.4 — Spatial query

- bbox returns only intersecting feature ids;
- geometry outside bbox is absent;
- coordinates and unit metadata match model coordinate space;
- unknown/candidate semantic state is preserved in DTO.

### T2.5 — Provenance

- selected object links to source asset/fragment and transform;
- conflicting evidence remains two assertions, not one overwritten value;
- source paths are display metadata, not entity identity.

### T2.6 — BFF boundary

- browser-facing route forwards correlation id and typed errors;
- internal FastAPI URL and DB credentials never appear in client JS;
- aborted browser request cancels or abandons upstream stream safely.

### T2.7 — Browser acceptance

- open pilot deep link;
- wait for scene, toggle layer, select feature;
- object card shows class/status/source;
- reload restores project/model/object from URL;
- empty and API-error states remain navigable.

## Ordered work packages

1. Choose and record pinned runtime versions under accepted ADR-0007/0008.
2. Create test-only PostGIS lifecycle and pilot fixtures.
3. Write T2.1–T2.5 failing backend tests.
4. Implement FastAPI repository/API until backend tests pass.
5. Generate/freeze TypeScript DTO client from OpenAPI or prove an equivalent contract method.
6. Write T2.6 and component tests for application states.
7. Implement Next.js shell/BFF.
8. Write T2.7 browser test against deterministic scene fixture.
9. Implement scene adapter and read-only viewport.
10. Run two-pilot acceptance, measure payload/render performance and publish Phase 2 report.

## Acceptance matrix

| Requirement | Evidence |
|---|---|
| one-command local start | documented Compose command + healthy services |
| both pilots visible | T2.3 + screenshot/report |
| explicit model version | T2.3 contract assertions |
| bbox spatial filtering | T2.4 PostGIS integration |
| object provenance | T2.5 API integration |
| BFF has no domain/DB ownership | T2.6 boundary test |
| usable 2D read-only flow | T2.7 browser acceptance |
| production data untouched | isolated test PGDATA and fixture hashes |

## Risks and fallback

- If deck.gl fails CAD precision/volume spike, keep API/scene adapter and replace only renderer.
- If full pilot DXF import is not stable, ship a documented bounded subset fixture; do not disguise it as full semantic coverage.
- If global CRS is unresolved, render CAD local XY without OSM overlay and show `needs_review`.

## Exit gate

All T2 tests pass; both pilot deep links work after clean startup; report records versions, timings, known missing layers and exact fixture/source hashes.
