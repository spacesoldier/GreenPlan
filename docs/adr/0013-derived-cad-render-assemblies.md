# ADR-0013: Derived CAD render assemblies вместо передачи каждого block primitive

- Status: Accepted
- Date: 2026-09-26
- Owners: domain, frontend
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

Viewport уже использует spatial/raster cache и persisted focus, но canonical import разворачивает каждый `INSERT` в отдельные примитивы. На Песчаном растительный слой содержит 63 252 `LINE`, происходящие примерно из 1 120 source handles. Один символ дерева может состоять из 118–426 линий, а отдельные составные элементы — из тысяч примитивов.

Передача и отрисовка каждого примитива как самостоятельного feature создаёт повторяющиеся metadata, десятки тысяч Canvas draw calls и визуально разносит позиционный круг и крону. Удалять canonical primitives или склеивать их необратимо нельзя: provenance должен оставаться до конкретного DXF entity.

## Decision

### Separate canonical and presentation identity

Canonical `geo.spatial_objects`, geometries и evidence остаются без изменений. PostGIS хранит отдельный derived projection:

- `geo.render_assemblies` — один render feature на `(model, layer, class, source handle)`;
- `geo.render_assembly_members` — упорядоченная связь assembly с каждым canonical object;
- assembly id совпадает с id детерминированно выбранного representative canonical object, поэтому существующие picking/deep-link/object endpoints продолжают работать;
- properties ответа содержат `render_assembly`, `member_count`, `source_handle` и algorithm version.

Первый scope — vegetation objects с доступным source handle. Canonical objects, которые не вошли в assembly, возвращаются прежним путём.

### Geometry

Assembly хранит `ST_Collect` primary geometries в порядке:

1. `position`;
2. прочая vegetation geometry;
3. `crown`.

Mixed geometry становится `GeometryCollection`; однородная — соответствующим multi-type. Renderer обязан рекурсивно поддерживать `MultiPoint`, `MultiLineString`, `MultiPolygon` и `GeometryCollection` для bounds, visible pass и color picking.

Каждый member упрощается до LOD **до** `ST_Collect`. Таблица хранит exact geometry и три precomputed LOD-проекции. Упрощение уже собранного `GeometryCollection` запрещено: оно плохо сокращает вложенные spline/line components и создаёт многомегабайтные ответы.

Assembly публикуется и выбирается атомарно. Picking возвращает representative canonical object; полный состав восстанавливается через membership table.

### Refresh and API

`geo.refresh_model_render_assemblies(model_id)` идемпотентно пересобирает derived projection после импорта. `features` endpoint объединяет:

- assemblies, пересекающие bbox;
- canonical features, отсутствующие в membership table.

Pagination и сортировка выполняются после `UNION ALL`, чтобы page boundaries больше не зависели от количества дочерних примитивов блока. LOD simplification для vegetation assembly использует crown-safe tolerance.

## Alternatives considered

### Группировать только в браузере

Отклонено: не сокращает JSON, SQL pagination и parsing; каждый downstream viewer повторял бы CAD-specific логику.

### Заменить canonical objects одним объектом блока

Отклонено: теряются entity-level provenance, диагностика конвертации и возможность последующей семантической пересборки.

### Dynamic `ST_Collect` на каждый bbox

Отклонено: переносит стоимость группировки в интерактивный запрос. Projection должен считаться после импорта и иметь GiST index.

### Сразу MVT

MVT остаётся следующим transport-слоем, но сам по себе не определяет, какие CAD primitives образуют один объект отображения. Assembly contract нужен и GeoJSON, и MVT.

## Consequences

### Positive

- десятки тысяч draw calls превращаются в тысячи assemblies;
- metadata и picking colors передаются один раз на исходный block handle;
- круг и крона одного handle приходят атомарно;
- canonical provenance не меняется;
- будущий MVT exporter получает готовую единицу генерализации.

### Negative / trade-offs

- выбор assembly открывает representative object, а не отдельный дочерний segment;
- некорректно организованный подрядчиком handle может объединить крупную группу; member count и bbox остаются диагностируемыми;
- `GeometryCollection` требует поддержки во всех viewers;
- координаты дочерних линий пока всё ещё передаются; последующая line merging/MVT может дополнительно уменьшить payload.

## Verification

- refresh повторяем и создаёт уникальное membership;
- ни один canonical object/provenance row не удаляется;
- каждый assembly id разрешается существующим object endpoint;
- bounds и renderer поддерживают nested geometry collections;
- position/crown одного handle находятся в одном API feature;
- Песчаный vegetation feature count уменьшается минимум в 20 раз;
- cold first-useful frame и settled time улучшаются относительно checkpoint 08;
- picking и deep link работают после агрегации.

## References

- [ADR-0010](0010-coherent-spatial-tile-cache.md)
- [ADR-0012](0012-persisted-primary-spatial-cluster.md)
- [Work package](../dev-plan/phase-02-render-assemblies.md)
