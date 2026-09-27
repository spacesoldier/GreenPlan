# Phase 2 work package — derived CAD render assemblies

- Status: Complete
- Date: 2026-09-26
- Prerequisite: [ADR-0013](../adr/0013-derived-cad-render-assemblies.md)

## Outcome

Viewport получает один атомарный render feature на vegetation block handle вместо десятков или сотен дочерних DXF primitives, сохраняя canonical objects и provenance в PostGIS.

## Tests before implementation

1. Bounds рекурсивно охватывают `GeometryCollection` и multi-geometries.
2. Renderer принимает nested geometry без потери picking id.
3. Assembly refresh не создаёт повторного membership.
4. Representative id существует в canonical objects.
5. API не возвращает одновременно assembly и его member primitives.
6. Features вне assembly продолжают возвращаться.

## Work order

1. Добавить derived tables, indexes и refresh function.
2. Пересчитать assemblies двух пилотов.
3. Перевести bbox API на union assemblies + unassembled canonical features.
4. Добавить recursive multi-geometry renderer.
5. Включить refresh в import pipeline.
6. Измерить counts, payload, cold load, pan и picking.

Отчёт и фактические измерения: [checkpoint 09](phase-02-checkpoint-09.md).

## Exit gate

- canonical counts остаются 87 728 и 135 765;
- vegetation transport count Песчаного уменьшается минимум в 20 раз;
- circle/crown одного handle публикуются одним feature;
- оба пилота отображаются и выбираются;
- tests, typecheck и production build проходят;
- checkpoint содержит измерения до/после.
