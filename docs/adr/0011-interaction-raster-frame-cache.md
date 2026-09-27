# ADR-0011: Raster frame cache для интерактивной навигации CAD viewport

- Status: Accepted
- Date: 2026-09-25
- Owners: frontend
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

ADR-0010 устранил повторную загрузку spatial data и page tearing, но Canvas остаётся immediate-mode renderer. При каждом pointer move текущая реализация заново обходит и трассирует все видимые векторы, даже если набор features не изменился. В плотных дендропланах это создаёт задержки и может визуально разрывать позиционные круги и контуры крон во время gesture.

Нужен быстрый interaction path, который не меняет canonical data cache, picking contract и итоговую точность vector frame.

## Decision

### Stale raster during gesture

После точного vector render основной и picking Canvas копируются в raster frame. Пока меняется только viewport transform, сохранённый frame репроецируется через affine matrix:

```text
screen_old -> inverse(view transform old) -> CAD screen space -> view transform new
```

Матрица учитывает pan, zoom, bearing, aspect-fit offsets и device pixel ratio. Во время drag выполняется только bitmap composition. Для wheel/rotate последовательность событий объединяется debounce-окном; после покоя выполняется один точный vector redraw.

### Exact refresh

- При отсутствии подходящего frame выполняется vector render в ближайшем `requestAnimationFrame`.
- После окончания drag точный redraw выполняется немедленно.
- После wheel/rotate точный redraw выполняется через 140 ms без нового события.
- Raster frame никогда не становится источником domain geometry: это только временная presentation cache.
- При сильном увеличении bitmap может кратко выглядеть мягче, но заменяется точным frame после debounce.

### Cache key and invalidation

Ключ содержит:

```text
canonical frame key + visible layer signature + selected object id
```

Viewport и bearing хранятся внутри frame и используются для reprojection, но не создают новый ключ на каждый event.

Frame инвалидируется или заменяется при:

- изменении набора ready spatial tiles;
- изменении layer visibility;
- изменении selection/style revision;
- resize или device pixel ratio;
- исчерпании memory budget.

### Bounded LRU

Кеш хранит несколько последних raster frames в `OffscreenCanvas`; fallback использует detached HTML Canvas. Бюджет считается по фактическим RGBA bytes обоих passes. Начальный лимит — 64 MiB. Least-recently-used frames удаляются первыми.

Picking bitmap репроецируется без smoothing той же матрицей, поэтому canonical color ids остаются согласованы с видимым stale frame. Click блокируется во время активного drag; после gesture точный picking pass обновляется.

## Alternatives considered

### Перетрассировать vectors на каждом animation frame

Отклонено для плотных проектов: `requestAnimationFrame` ограничивает частоту, но не стоимость одного кадра.

### CSS transform самого Canvas

Подходит только для краткого pan/scale, усложняет clipping, bearing, координаты pointer и синхронизацию picking. Canvas composition с явной матрицей оставляет DOM layout неизменным.

### Сразу перейти на WebGL/MVT

Остаётся вероятным production renderer, но меняет больше компонентов. Raster frame cache локально устраняет interaction bottleneck и сохраняет текущий scene/picking contract.

### Постоянные raster tiles вместо frame cache

Отложено: потребует tile seams, overscan, style invalidation и нескольких pixel densities. Frame cache проще проверяет выигрыш; результаты профилирования определят необходимость постоянных raster tiles.

## Consequences

### Positive

- pan/zoom/rotate не трассируют vectors на каждом событии;
- круги и crown contours перемещаются как единый bitmap;
- stale frame остаётся видимым во время смены LOD/data tiles;
- picking соответствует показанному raster frame;
- точный vector result сохраняется после gesture;
- память ограничена измеряемым LRU budget.

### Negative / trade-offs

- края старого frame могут временно оголиться при большом pan;
- сильный zoom кратко масштабирует raster pixels;
- selection/layer change требует нового точного frame;
- два RGBA passes расходуют память;
- bitmap cache не заменяет будущий WebGL renderer.

## Verification

- affine round-trip сохраняет точки для identity transform;
- pan/zoom/bearing reprojection совпадает с прямым target transform;
- LRU не превышает 64 MiB и удаляет старейшие frames;
- серия pointer moves выполняет один vector redraw после gesture;
- wheel burst показывает raster immediately и один exact redraw после debounce;
- picking после reprojection возвращает тот же canonical id;
- смена layers/selection не использует frame с устаревшим style key;
- оба пилота сохраняют полный feature count и не дают application errors.

## References

- [ADR-0009](0009-viewport-virtualization-and-canvas-rendering.md)
- [ADR-0010](0010-coherent-spatial-tile-cache.md)
- [Checkpoint 06](../dev-plan/phase-02-checkpoint-06.md)
- [Work package](../dev-plan/phase-02-raster-frame-cache.md)
- [Checkpoint 07](../dev-plan/phase-02-checkpoint-07.md)
