# ADR-0035: Восстановление CAD-поверхностей и пространственного контекста

- Status: Proposed
- Date: 2026-09-29
- Owners: CAD ingestion / geospatial platform
- Related phase: Phase 4
- Supersedes: —
- Superseded by: —

## Context

Задаче размещения растений нужны не только символы растений, но и площади озеленения, дорожные поверхности, борта, сети, охранные зоны и соседние объекты. В поставках эта семантика распределена между HATCH, замкнутыми полилиниями, слоями, цветами, легендами и XREF.

Аудит Старого Гая показал, что ODA сохранил сотни HATCH и их boundary paths, однако текущий intake сохраняет только агрегаты по слоям. `cad_entities` пуст, поэтому система не может выполнить пространственный анализ. «Зелёный цвет» полезен как evidence, но недостаточен: оттенок может наследоваться от слоя, быть true-color/ACI, а одинаковый слой содержит несколько цветов и паттернов.

## Decision

Вводится entity-level pipeline `DXF entity -> diagnostic CAD feature -> reviewed semantic surface -> canonical spatial object`.

### Диагностический CAD feature

Для каждого поддержанного entity сохраняются:

- document, model/layout space, layer, handle и block/XREF path;
- исходная геометрия или воспроизводимая аппроксимация;
- raw color mode и effective RGB с указанием источника `entity/layer/byblock`;
- transparency, linetype, lineweight, hatch pattern и visibility;
- provenance до исходного asset и производного DXF.

HATCH boundaries преобразуются в Polygon/MultiPolygon. Дуги и spline flattening используют tolerance, связанный с единицами и масштабом проекта; исходное описание edges сохраняется. Внутренние loops становятся holes. Невалидная геометрия не исправляется молча: raw geometry и repair result хранятся раздельно.

### Семантические кандидаты

Кандидат поверхности получает независимые оси:

- object class: green area, lawn, flower bed, shrub mass, road, carriageway, sidewalk, curb, utility, protection zone, unknown;
- lifecycle: existing, proposed, demolition, replacement, unknown;
- representation: hatch, footprint, centerline, boundary;
- confidence и evidence.

Классификация использует совокупность file role, layer name, entity type, effective style, hatch pattern, legend match, соседний текст и review examples. Цвет не является разрешающим правилом.

### Дорожная геометрия

Приоритет источников:

1. подтверждённый HATCH/closed polyline поверхности;
2. поверхность, восстановленная polygonize из бортов и границ;
3. OSM road corridor как reviewed reference/candidate;
4. эвристический buffer осевой линии только для preview с низкой confidence.

CAD и OSM не сливаются автоматически. Сопоставление хранит distance/overlap evidence и требует review при заметном расхождении.

### Пространственные отношения

После подтверждения поверхности PostGIS вычисляет версионированные отношения:

- `ST_Intersects(green_area, utility/protection_zone)`;
- площадь и долю пересечения;
- `ST_DWithin` до здания, борта, проезжей части и тротуара;
- положение вдоль road corridor и сторона улицы;
- доступная посадочная площадь после вычитания запретов и буферов.

Производное отношение всегда ссылается на версии обоих объектов и rule/evidence, чтобы оно пересчитывалось после смены master, XREF или классификации.

## Alternatives considered

### Классифицировать только по зелёному цвету

Отклонено: пропускает малонасыщенные зелёные заливки и смешивает оформление, растительность и служебную графику.

### Искать дороги только в OSM

Отклонено: OSM полезен как внешняя опора, но не описывает проектируемые покрытия и локальные границы работ с CAD-точностью.

### Восстанавливать всё из линий без HATCH

Отклонено: HATCH уже содержит явные loops и holes; повторная polygonize теряет более сильное исходное доказательство.

## Consequences

### Positive

- зелёные площади и дорожные покрытия становятся запросопригодными объектами PostGIS;
- можно вычислять пересечения с сетями и нормативными зонами;
- сохраняется объяснимость: цвет, слой, legend и source handle доступны инженеру;
- одна схема работает для CAD и reviewed OSM candidates.

### Negative / trade-offs

- entity-level import заметно увеличит объём БД;
- curve flattening и geometry repair требуют tolerance policy и метрик качества;
- master/XREF assembly должен быть выбран до канонизации координат;
- легенды и стили разных подрядчиков потребуют human review и корпуса примеров.

## Verification

- для `улица Старый Гай_ГП.dwg` импорт сохраняет 596 HATCH без необъяснимого исчезновения;
- 596 HATCH дают 614 boundary paths, а holes не превращаются в отдельные залитые полигоны;
- слои газонов дают reviewable green-area candidates с исходным effective RGB и pattern;
- дорожные HATCH и бортовые LWPOLYLINE доступны раздельно и участвуют в построении road surface;
- `ST_Intersects` возвращает воспроизводимые пересечения green-area с тестовой utility/protection-zone;
- смена master/XREF revision инвалидирует производные spatial relations, но не raw CAD evidence.

## References

- [ADR-0018](0018-evidence-gated-cad-reading-and-conversion.md)
- [ADR-0019](0019-resolved-xref-assembly.md)
- [ADR-0022](0022-versioned-cad-semantic-taxonomy-and-learning-loop.md)
- [Аудит Старого Гая](../project-research/02-stary-gay-hatch-road-audit.md)
