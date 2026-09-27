# Phase 2 — checkpoint 02: real DXF → PostGIS → browser

- Status: Verified checkpoint; Phase 2 remains In progress
- Date: 2026-09-25
- Data mode: PostGIS populated from converted pilot DXF

## Delivered

- `ezdxf 1.4.4` parser with recursive `INSERT` expansion and inherited block-layer handling;
- conversion of CAD primitives to GeoJSON/PostGIS geometry;
- deterministic per-layer sampling with a hard model cap, preserving rare semantic layers;
- layer-name classification with explicit confidence and `needs_review` fallback;
- idempotent importer for Песчаный переулок and Куликовская улица;
- source assets, CAD layer/entity fragments and classification evidence for every imported object;
- `PostgisRepository` behind the existing FastAPI repository contract;
- production Compose mode switched from synthetic fixtures to PostGIS;
- real CAD extents, layers, features, sources and provenance exposed through the Next.js BFF;
- SVG viewport fitted to the model extent, including CAD Y-axis correction and point rendering;
- fixed-height application shell so long layer trees scroll without moving the drawing off screen;
- working URL restoration of project, object and view state.

The importer is available as an explicit tools-profile job:

```bash
cd platform
docker compose --env-file .env --profile tools run --rm domain-import
```

The job reads the dataset mount read-only. It runs under `LOCAL_UID:LOCAL_GID` because converted DXF files may be mode `0600`.

## Loaded pilot evidence

| Project | Source primitives traversed | Stored geometries | CAD layers traversed | Source layers represented | Semantically mapped geometries |
|---|---:|---:|---:|---:|---:|
| Песчаный переулок | 99,418 | 5,122 | 35 | 31 | 4,232 |
| Куликовская улица | 143,742 | 9,154 | 202 | 96 | 6,184 |

`source layers represented` is lower than `CAD layers traversed` when a layer contains no supported geometric primitive after block expansion. The database retains source-layer counts even when no geometry is emitted.

The current scene endpoint returns at most 6,000 features per bbox request. Куликовская therefore stores all 9,154 sampled geometries but the initial full-extent browser request receives 6,000. This is a transport/render guard, not data loss.

## Verification evidence

```text
apps/api: 17 passed
apps/web: 3 passed
TypeScript --noEmit: passed
Next.js production Docker build: passed
FastAPI readiness: 200
FastAPI project list: two real projects
Next.js BFF project list: two real projects
PostGIS object counts: 5,122 + 9,154
Celery ODA worker: ready
Celery LibreDWG worker: ready
```

Read-only end-to-end probes covered:

1. project list through FastAPI and BFF;
2. scene manifest and real CAD extent;
3. bbox feature retrieval;
4. object detail and classification evidence;
5. revision source tree;
6. browser rendering in headless Chrome;
7. direct URL restoration of project and selected object;
8. inspector display of source DXF path, layer and handle.

## Findings from real drawings

- recursive block expansion is mandatory: top-level entity counts materially understate the drawing;
- a single file contains both project geometry and sheet/service fragments;
- full file extent is therefore not a reliable territory extent;
- CAD layer names are numerous, contractor-specific and sometimes encoding-like; unknown layers remain visible and marked `needs_review`;
- the application must separate `document extent`, `sheet/annotation extent` and `working territory extent` before map overlay and automatic planting;
- both current coordinate spaces remain `cad_local/candidate`; OSM overlay must wait for an accepted transform or control-point fit.

## Known limitations and next gate

- sampling is deterministic but is not a lossless canonical CAD import;
- unsupported entity types remain visible only in traversal statistics;
- no automatic model-space versus paper/legend clustering exists yet;
- the renderer has fit-to-extent and picking, but pan/zoom and tiled bbox fetching are not implemented;
- browser verification is currently a repeatable headless smoke check, not yet a committed Playwright test;
- PostGIS repository needs an isolated integration-test database before Phase 2 completion.

Next work is to identify the actual working-territory cluster, add viewport pan/zoom with bbox paging, and commit T2.1/T2.4/T2.7 automated integration tests.
