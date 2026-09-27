# Phase 2 — checkpoint 07: interaction raster frame cache

- Status: Complete
- Date: 2026-09-25
- Decision: [ADR-0011](../adr/0011-interaction-raster-frame-cache.md)
- Work package: [interaction raster frame cache](phase-02-raster-frame-cache.md)

## Result

CAD viewport больше не трассирует десятки тысяч векторных объектов на каждом событии pan/zoom/rotate. Последний точный visible frame и синхронный picking frame сохраняются в ограниченном LRU-кеше и во время gesture репроецируются одной affine matrix. После окончания drag или 140 ms покоя wheel/rotate выполняется один точный vector redraw.

Кеш является только presentation-слоем. Canonical geometry, spatial tile cache и итоговый точный кадр остаются источником истины.

## Implementation

- добавлены affine transforms `old screen -> CAD -> new screen`, включая pan, zoom, bearing и aspect-fit;
- visible и picking passes копируются в `OffscreenCanvas`; для браузеров без него используется detached HTML Canvas;
- picking frame переносится той же матрицей без image smoothing;
- ключ кадра включает canonical scene key, отсортированную видимость слоёв и selected object id;
- scene key меняется при изменении полного набора ready spatial tiles;
- LRU учитывает RGBA-память обоих passes и ограничен 64 MiB;
- drag использует только bitmap composition, exact redraw выполняется сразу после pointer up;
- wheel/rotate burst объединяется окном 140 ms;
- добавлены диагностические счётчики `data-vector-renders` и `data-raster-blits` для browser acceptance.

## Automated verification

В `apps/web`:

```text
npm test          5 files, 22 tests passed
npm run typecheck passed
npm run build     passed (Next.js production build)
```

Новые unit tests проверяют:

- identity и обратимость affine transform;
- совпадение raster reprojection с прямым target transform для pan/zoom;
- смену bearing;
- LRU eviction по byte budget;
- разделение cache keys при смене selection и layer set.

## Browser acceptance

Проверка выполнена на production-сборке в Chromium с доступным `OffscreenCanvas`.

### Песчаный переулок

- загружено 87 728 объектов;
- 20 промежуточных pointer moves: vector renders `2 -> 2`, raster blits `0 -> 21`;
- после pointer up: vector renders `2 -> 3`, то есть один exact redraw;
- burst из пяти wheel events: во время burst vector renders не изменился, raster blits `23 -> 33`;
- после 300 ms: vector renders `4 -> 5`, то есть один delayed exact redraw;
- picking точного кадра вернул canonical object id `13c46d8b-6a35-5a2f-8252-d8515212ebad`;
- через 35 ms после wheel, до exact debounce, raster blits изменились `0 -> 2`, а vector renders остались `2 -> 2`; click по репроецированному picking frame вернул тот же canonical id;
- после selection exact/style refresh счётчик стал `2 -> 3`; новых browser console errors нет.

### Куликовская улица

- загружено 135 765 объектов без урезания;
- production viewport создал точные raster frames с поддержкой `OffscreenCanvas`;
- переключение проекта сбросило старый scene/style key и построило кадр второго проекта.

## Operational notes

- большой pan может кратко показать пустой край старого bitmap — следующий spatial/exact frame его заменяет;
- при сильном zoom до exact refresh возможна краткая мягкость линий;
- selection и layer visibility не переиспользуют кадр с другим style key;
- постоянные raster tiles или WebGL остаются следующим уровнем оптимизации, если профилирование покажет необходимость.

## Exit gate

| Requirement | Evidence | Status |
|---|---|---|
| Нет vector tracing на каждом pointer move | `2 -> 2` vector, 21 raster blit | Passed |
| Один exact frame после drag | `2 -> 3` после pointer up | Passed |
| Wheel burst coalesced | пять events, один delayed vector redraw | Passed |
| Ограниченная память | unit-tested 64 MiB LRU | Passed |
| Picking/style invalidation | stale-frame click вернул тот же id; после selection один exact redraw; style-key unit test | Passed |
| Оба пилота целиком | 87 728 и 135 765 объектов | Passed |
| Regression/build | 22 tests, typecheck, production build | Passed |
