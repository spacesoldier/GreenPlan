# ADR-0041 — Фасетный навигатор слоёв для пространственного viewer

- Status: Proposed
- Date: 2026-09-29
- Owners: frontend, geospatial backend, CAD ingestion
- Related phase: Phase 3, iteration 6
- Supersedes: расширяет ADR-0009, ADR-0010 и ADR-0017
- Superseded by: —

## Context

Текущий viewer уже показывает плоский список `SceneLayer` и умеет включать и выключать слой. Контракт
содержит `id`, `title`, `class_codes`, `geometry_roles` и `feature_count`; feature API принимает список
layer id. Этого достаточно для пилотного Canvas renderer, но недостаточно для разбора реального
комплекта:

- одинаково названные слои приходят из нескольких DWG/XREF;
- пользователю важно видеть как физическую структуру источников, так и смысловые категории;
- unknown-слои нельзя скрывать только потому, что классификация не закончена;
- слоёв может быть много, поэтому плоский список плохо читается;
- изменение видимости должно одинаково влиять на графику, picking, счётчики и 3D;
- нужно быстро найти слой на плане, изолировать его и перейти к классификации.

CAD Explorer решает задачу подготовки поставки, а spatial viewer — задачу исследования опубликованной
сцены. Они используют один classification snapshot, но не обязаны иметь одинаковую компоновку UI.

## Decision

### 1. Ввести канонический scene-layer identity

`scene_layer_id` идентифицирует слой в пределах опубликованной model revision и строится из:

- source asset identity;
- CAD document identity;
- исходной layer identity/name;
- версии publish/classification snapshot.

Одинаковое имя в разных DWG не сливает слои. Отдельная таблица/проекция связывает scene layer с
canonical objects, source path, XREF ancestry и подтверждённым object class.

### 2. Один набор слоёв, несколько фасетных представлений

Навигатор имеет переключаемые представления, которые ссылаются на одни `scene_layer_id`:

1. **По источникам** — publication root set, сгруппированный как проектное решение/исходные данные/архив → подключённый DWG/XREF → CAD-слой;
2. **По смыслу** — крупная группа → конечный object class → исходные слои;
3. **По готовности** — неизвестные, подсказанные, подтверждённые, неприменимые;
4. позднее **Оверлеи** — OSM, нормативные зоны, результаты анализа и planting proposals.

Узел может встречаться в нескольких фасетах, но видимость хранится один раз. Tree projection не
копирует геометрию и не создаёт новые domain objects.

### 3. Контракт manifest

`SceneManifest` получает версионированный layer catalog. Для leaf минимум:

```text
id, source_asset_id, source_document_id, source_path, source_layer_name,
class_code, semantic_status, confidence, feature_count, geometry_roles,
extent, default_visible, color_token
```

Группы возвращают `id`, `kind`, `title`, `children`, агрегированные counts и tri-state readiness.
Manifest не содержит полную геометрию. Extent и counts вычисляются при публикации и позволяют
рисовать navigator без запроса всех features.

### 4. Поведение навигатора

Для leaf и group доступны:

- включить/выключить с tri-state checkbox;
- «показать только этот» и «вернуть предыдущий набор»;
- приблизить к extent слоя;
- поиск по имени, пути, классу и русским сокращениям;
- фильтры unknown/confirmed и «есть объекты в текущем viewport»;
- счётчики объектов и индикатор semantic status;
- переход в CAD Explorer на соответствующий source layer;
- выбор цвета только как view preference, без изменения domain class.

Навигатор располагается рядом с графикой в левой панели. Панель сворачивается и изменяет ширину, но
Canvas сохраняет текущий центр/масштаб. На узком экране она становится drawer.

### 5. Единая модель видимости для render и picking

Visibility state задаётся множеством leaf `scene_layer_id` и имеет стабильный fingerprint. Один и тот
же snapshot используется для:

- bbox/tile feature query;
- Canvas render;
- color picking;
- inspector selection;
- 3D renderer;
- screenshot/render export.

Скрытый объект не может оставаться кликабельным. Переключение группы применяется атомарно к visible и
picking frame. Активная загрузка со старым visibility fingerprint не публикуется в кадр.

### 6. Сохранение состояния и deep links

В URL или компактном persisted view state сохраняются:

- project/model revision;
- активная фасета;
- раскрытые группы;
- visibility preset или отклонения от default;
- viewport/bearing/view 2D/3D;
- selected object/layer.

Большие множества layer ids не записываются непосредственно в URL: сохраняется preset id плюс diff или
короткий server-side view-state id.

### 7. Производительность

- catalog загружается один раз на model version;
- поиск и раскрытие дерева не инициируют feature query;
- bbox query получает только видимые leaf ids либо server-side visibility token;
- layer extent индексируется;
- изменение visibility инвалидирует frame, но не уничтожает независимые cached tiles;
- кэш feature tiles учитывает model version, LOD и слой/visibility partition;
- группы виртуализируются при больших списках.

## Alternatives considered

### Оставить плоский список смысловых слоёв

Отклонено: теряется источник, XREF-контекст и различие одинаково названных слоёв.

### Показывать только структуру DWG/XREF

Отклонено: архитектору также нужен быстрый ответ «покажи все сети» или «покажи unknown».

### Формировать отдельную копию сцены для каждой комбинации видимости

Отклонено: комбинаторный рост кэша и рассинхронизация render/picking. Видимость является view state,
а не новой canonical model.

### Скрывать unknown по умолчанию

Отклонено: именно среди unknown могут находиться ещё не распознанные ограничения.

## Consequences

### Positive

- можно продолжать проверку модели до полного семантического разбора;
- источник и смысл слоя доступны в одном viewer;
- навигация масштабируется на XREF-комплекты;
- 2D, 3D, picking и screenshot используют одну видимость;
- из viewer можно адресно вернуться к неразобранному CAD-слою.

### Negative / trade-offs

- SceneManifest меняет версию;
- нужен устойчивый scene-layer identity и миграция старых моделей;
- фасеты требуют серверной агрегации;
- visibility-aware cache сложнее плоского списка.

## Verification

- два одноимённых слоя из разных DWG имеют разные ids и видны в правильных ветках;
- один leaf, показанный в двух фасетах, имеет единое состояние видимости;
- group checkbox корректно показывает checked/unchecked/indeterminate;
- hidden layer отсутствует и в visible Canvas, и в picking;
- поздний ответ старого visibility request не заменяет новый frame;
- zoom-to-layer использует persisted extent без загрузки всех features;
- unknown-слои видны и фильтруются;
- deep link восстанавливает facet, visibility, viewport и selection;
- 10 000 layer nodes остаются управляемыми за счёт виртуализации.

## References

- [ADR-0009](0009-viewport-virtualization-and-canvas-rendering.md)
- [ADR-0010](0010-coherent-spatial-tile-cache.md)
- [ADR-0015](0015-overscanned-raster-frames.md)
- [ADR-0028](0028-cad-workbench-graph-navigation-bulk-review-and-activity-dock.md)
- [ADR-0040](0040-independent-geometry-and-semantic-publication-readiness.md)
- [ADR-0042](0042-multi-root-publication-set.md)
- [Phase 3, iteration 6](../dev-plan/phase-03-iteration-06-preview-publication-and-layer-viewer.md)
