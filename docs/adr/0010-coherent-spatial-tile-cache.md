# ADR-0010: Когерентный spatial tile cache для CAD viewport

- Status: Accepted
- Date: 2026-09-25
- Owners: frontend and spatial API
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

ADR-0009 убрал feature DOM nodes и научил viewport запрашивать расширенный bbox. Однако каждый новый bbox всё ещё передаёт перекрывающуюся геометрию заново и заменяет текущий массив результатами последовательных страниц.

Для растений это особенно заметно: позиционный круг и контур кроны могут быть разными CAD-объектами. Если они попали в разные страницы, промежуточный кадр показывает только часть условного обозначения. При zoom/pan уже готовая сцена исчезает, повторно собирается и несколько раз целиком перерисовывается. Широкий prefetch bbox уменьшает число запросов, но увеличивает дублирование и стоимость каждого ответа.

## Decision

### Stable project grid

Каждый immutable `model_id` получает стабильную квадратную сетку в CAD coordinates. Размер tile зависит от LOD, но не от текущего viewport. Клиент запрашивает только отсутствующие tile keys, а не очередной произвольный пересекающийся bbox.

Tile key содержит:

```text
model_id / model_version / lod / column / row
```

Граница tile передаётся существующему bbox endpoint. Переход на MVT позднее меняет transport, но не ключи и cache policy.

### Two-phase frame commit

- Страницы одного tile собираются во staging entry.
- Tile становится `ready` только после `next_offset = null`.
- Незавершённый tile никогда не участвует в кадре: позиционные круги и crown contours не разделяются границей HTTP page.
- При pan готовые tiles того же LOD остаются на экране, пока догружается новая полоса.
- При смене LOD предыдущий полный кадр используется как stale fallback и заменяется только после готовности всех tiles нового viewport.
- Первый кадр может дополняться по мере готовности целых tiles, но не отдельных страниц.

### Deduplication and deterministic draw order

- Features из пересекающихся tiles объединяются по canonical object id.
- Порядок рисования не зависит от tile/page arrival: базовая геометрия, затем vegetation position markers, затем crown geometry, выбранный объект последним.
- Renderer получает только features готовых tiles текущего cache window и по-прежнему выполняет точный viewport culling.

### Cache lifecycle

- Готовые и выполняющиеся tile requests переиспользуются.
- Pan не отменяет полезный запрос tile: результат остаётся кандидатом для ближайшего движения назад.
- Смена `model_id` отменяет pending requests и очищает cache.
- LRU ограничивает cache по числу feature references; tiles текущего кадра защищены от eviction.
- Versioned feature responses получают browser-private cache headers. BFF передаёт их клиенту.

## Alternatives considered

### Кэшировать произвольные bbox

Отклонено: проверка покрытия и вычисление разности перекрывающихся прямоугольников быстро усложняются; одинаковый участок получает разные URL и плохо использует HTTP cache.

### Только увеличить prefetch bbox

Отклонено: уменьшает частоту запросов, но передаёт ещё больше повторяющейся геометрии и не решает page tearing.

### Сразу кэшировать raster ImageBitmap

Отложено. Raster tiles ускорят повторную композицию, но требуют отдельной стратегии resolution, bearing, styles и picking. Сначала фиксируется корректный vector tile cache; raster/OffscreenCanvas становится следующим измеряемым уровнем.

### Отображать каждую полученную страницу

Отклонено: arrival order превращается в z-order и даёт визуально неполные растения.

## Consequences

### Positive

- повторное посещение участка не вызывает повторный API request;
- соседний pan загружает только отсутствующую полосу tiles;
- одинаковые features на границе tiles не дублируются в кадре;
- plant marker/crown обновляются когерентно на границе tile commit;
- zoom сохраняет предыдущий кадр до готовности нового LOD;
- стабильные tile URLs готовы к HTTP cache и MVT migration.

### Negative / trade-offs

- bbox объекта, пересекающий несколько tiles, пока может повториться в transport;
- сетка добавляет несколько небольших запросов вместо одного широкого;
- memory budget и eviction требуют телеметрии на всех 20 проектах;
- vector Canvas всё ещё повторно трассирует видимые features при каждом кадре;
- идеальная атомарность «одно растение» потребует явного plant aggregate id в canonical model.

## Verification

- повторный запрос одного tile вызывает loader один раз;
- пересекающиеся tiles возвращают один canonical object в composed frame;
- незавершённые страницы tile не попадают в ready frame;
- position marker сортируется раньше crown geometry независимо от arrival order;
- pan запрашивает только новые tile keys;
- zoom сохраняет старый Canvas до полного commit нового LOD;
- browser test не показывает падение feature count к размеру первой страницы;
- API/BFF сохраняют private cache header для versioned geometry.

## References

- [ADR-0004](0004-canonical-model-provenance-and-immutability.md)
- [ADR-0009](0009-viewport-virtualization-and-canvas-rendering.md)
- [Checkpoint 05](../dev-plan/phase-02-checkpoint-05.md)
- [Work package](../dev-plan/phase-02-coherent-tile-cache.md)
