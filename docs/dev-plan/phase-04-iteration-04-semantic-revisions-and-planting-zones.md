# Phase 4, iteration 4: Semantic revisions and planting feasibility zones

- Status: Planned
- Date: 2026-09-30
- Owners: domain / geospatial / API / web
- Prerequisites: ADR-0035, ADR-0036, ADR-0048, ADR-0049

## Outcome

Инженер накапливает исправления классов слоёв и сохраняет их одной semantic revision без копирования геометрии. Для выбранного publication root система строит проверяемые кандидатные зоны озеленения и доступные области для деревьев, кустарников и травы с объяснением каждого ограничения.

## Scope

- два явных viewer tool mode: навигация и обозначение газона;
- seed-point API для surface polygon detection с utility exclusion;
- draft/confirm lifecycle найденного контура газона;

- persistent semantic draft и versioned diff;
- кнопка сохранения версии, optimistic lock и deep link;
- аудит polygon/seed/hatch evidence;
- polygonize candidate reconstruction внутри границы работ;
- построение constraint zones из approved rules;
- раздельные feasible overlays для tree/shrub/grass;
- viewer controls и инспектор provenance;
- пилотный расчёт Старого Гая.

## Out of scope

- окончательная расстановка растений и оптимизация их количества;
- автоматическое закрытие крупных разрывов в linework;
- использование review/draft rules как обязательных запретов;
- изменение исходных DWG/DXF.

## Tests before implementation

1. Semantic diff: dedupe операций, atomic save, immutable history, 409 conflict.
2. Geometry: metric CRS gate, valid polygonization, gap tolerance, minimum component filter.
3. Rules: tree/shrub distances, class descendants, approved-only membership.
4. Provenance: every exclusion references source object and rule.
5. API: async job, progress, cancellation/idempotency and bbox overlay query.
6. Web: dirty counter, save button, version selector, four overlay kinds and explanation inspector.
7. Старый Гай: explicit `ДВ_ГП_П_Газон` polygons are separated from `Леса и газоны` marker hypotheses.

## Work packages

1. Add semantic revision/draft migrations and API.
2. Replace immediate republish notice with accumulated changes and save-version UX.
3. Add candidate/feasible zone schema with fingerprints and provenance edges.
4. Implement deterministic PostGIS reconstruction and constraint derivation worker.
5. Add viewer overlays and diagnostics.
6. Run the Old Guy pilot, inspect false closures and tune only explicit tolerances.

## Acceptance

- category edits survive reload and save without new geometry rows;
- only one selected root/XREF closure participates in a run;
- no effective zone is produced without candidate-domain and metric-CRS evidence;
- tree, shrub and grass results are independently queryable;
- every excluded area is explainable from UI;
- repeated identical run reuses its fingerprinted result.

## Completion report

To be filled after implementation and pilot verification.
