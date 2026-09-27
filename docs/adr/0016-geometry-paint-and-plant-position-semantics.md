# ADR-0016: Семантика отрисовки CAD-геометрии и посадочных позиций

- Status: Accepted
- Date: 2026-09-27
- Owners: frontend, domain
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

Derived vegetation assembly может быть `GeometryCollection`: окружность посадочного места, контур кроны и открытые декоративные линии блока объединены для атомарной загрузки и отрисовки. Canvas `fill()` не различает назначение вложенных примитивов. Если передать ему общий `Path2D`, он неявно замыкает открытые линии и превращает фрагменты сложной кроны в треугольники и ломаные заливки.

Дополнительно CAD-слой `position` не доказывает наличие полной графики растения. В исходнике окружность посадочного места и крона могут:

- входить в один block handle;
- быть отдельными CAD entities рядом друг с другом;
- существовать только как окружность без найденной кроны.

Поэтому визуальная окружность не должна автоматически интерпретироваться как растение с известной кроной.

## Decision

### Paint contract

Renderer рекурсивно раскладывает любую GeoJSON geometry на примитивы и строит два независимых пути:

- `stroke path`: points, lines и polygon rings;
- `fill path`: только points и polygons.

Открытые `LineString` и `MultiLineString` никогда не попадают в `fill path`. Правило одинаково для visible и color-picking surface. `GeometryCollection` не имеет собственной paint-семантики: она наследуется от каждого вложенного примитива.

### Position contract

`geometry_role = position` означает «в исходном CAD найден графический маркер посадочного места». Это не синоним подтверждённого растения и не доказательство отсутствия растения.

Связь position → crown имеет три состояния:

1. `same_assembly` — доказана общим CAD block handle;
2. `spatial_candidate` — отдельная крона найдена рядом, связь требует детерминированного matching/review;
3. `unmatched` — подходящая крона не найдена в установленном радиусе.

Frontend обязан сохранять различие состояний. До появления предметного matching нельзя молча объединять соседние entities только по близости: на плотных посадках это может связать позицию с чужой кроной.

### Transport and cache contract

Крупные CAD assemblies могут пересекать несколько spatial tiles. Размер grid выбирается так, чтобы двухэкранное prefetch-поле не порождало сотни дублирующих запросов. Feature dedupe по `id` и атомарная публикация полного tile window остаются обязательными.

## Alternatives considered

### Не вызывать fill для всей GeometryCollection

Недостаточно: points и реальные polygons внутри одной collection должны сохранять заливку и корректный picking.

### Принудительно замыкать линии кроны

Отклонено: меняет исходную CAD-геометрию и создаёт вымышленные поверхности.

### Связывать position с ближайшей crown без ограничений

Отклонено: геометрическая близость является кандидатом, но не provenance. Нужны радиус, one-to-one matching, оценка неоднозначности и review.

## Consequences

### Positive

- сложные кроны не превращаются в треугольные заливки;
- picking совпадает с видимой геометрией;
- посадочное место не маскируется под подтверждённое растение;
- сохраняется путь к безопасному пространственному matching отдельных entities.

### Negative / trade-offs

- для feature кешируются два `Path2D` вместо одного;
- отдельные position/crown пока могут визуально сосуществовать без предметной связи;
- полноценная классификация `spatial_candidate`/`unmatched` требует отдельной derived-модели в PostGIS.

## Verification

- unit test проверяет, что открытые линии mixed assembly не входят в fill path;
- browser zoom sequence подтверждает отсутствие неявных треугольных заливок;
- visible и picking render используют один primitive partition;
- число feature requests в последовательности 100–2009% ограничено двузначным значением;
- диагностический запрос отдельно считает `same_assembly`, nearby other entity и позиции без найденной кроны.

## References

- [ADR-0010](0010-coherent-spatial-tile-cache.md)
- [ADR-0013](0013-derived-cad-render-assemblies.md)
- [ADR-0014](0014-frame-budgeted-cad-rendering.md)
- [Checkpoint 13](../dev-plan/phase-02-checkpoint-13.md)
