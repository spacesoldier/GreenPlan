# Phase 4, iteration 5: Surface-region inspector and prototype clearance

- Status: In progress
- Date: 2026-09-30
- Owners: domain / geospatial / API / web
- Prerequisites: ADR-0049, ADR-0050

## Outcome

После указания газона инженер видит в правой панели все классы объектов, пересекающие найденный контур, может сохранить контур как candidate и получить проверочный остаток площади после отступа от наземных препятствий.

## Scope

- intersection inventory с total counts и bounded object sample;
- surface-region inspector вместо обычного object inspector;
- persistent `planning.surface_regions` candidate с fingerprint;
- prototype clearance 0,5 CAD units;
- отдельный overlay исходного контура и зоны после вычитания;
- существующие деревья и кустарники как наземные препятствия;
- utility inventory без автоматического вычитания.

## Out of scope

- утверждение CRS и юридически значимый метрический расчёт;
- разные нормативные зоны tree/shrub/grass;
- автоматический выбор растений и генерация посадочных точек;
- редактирование DWG/DXF.

## Tests before implementation

1. API detection returns intersection summary and excludes source polygon from its own inventory.
2. Save is idempotent by fingerprint and root-scoped.
3. Prototype preview subtracts eligible surface objects by 0.5 units.
4. Utility objects are reported but do not reduce prototype geometry.
5. UI helpers choose region inspector and create distinct preview overlays.
6. Old Guy live check returns internal transport/vegetation inventory and valid polygon result.

## Work packages

1. Add migration 020 for persistent surface-region candidates.
2. Extend API models/repository with inventory, save and preview contracts.
3. Add PostGIS intersection and prototype difference queries.
4. Build right-side contour inspector and actions.
5. Verify tests, build, local containers and Old Guy E2E.

## Acceptance

- contour selection does not disappear when the right inspector opens;
- intersection count and class groups are visible;
- save action returns a stable candidate id;
- prototype zone is visually distinct and smaller when obstacles exist;
- UI explicitly labels CAD-unit assumption;
- frozen submission tag remains at `1974385`.

## Completion report

To be filled after implementation and pilot verification.
