# ADR-0014: LOD-aware transport cells и покадровый exact render

- Status: Accepted
- Date: 2026-09-26
- Owners: frontend, domain API
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

ADR-0013 уменьшил Песчаный с 87 728 canonical primitives до примерно 4 900 render features. Профилирование после внедрения обнаружило два оставшихся независимых узких места:

1. мелкая overview-сетка запрашивала одни и те же протяжённые assemblies во множестве соседних bbox: 61 HTTP request на холодной загрузке и новые полосы запросов после малого pan;
2. точный visible+picking Canvas pass синхронно занимал главный поток примерно на 0.4–0.6 s после `pointerup`, хотя во время gesture уже использовался быстрый raster frame.

Увеличивать debounce недостаточно: оно переносит блокировку, но не ограничивает длительность одной browser task.

## Decision

### LOD-aware request granularity

- overview LOD использует крупные focus-relative cells; detailed LOD сохраняют мелкую сетку;
- active prefetch window хранит полный union bbox фактически запрошенных cells, а не исходный непривязанный bbox запроса;
- пока visible bbox входит в это покрытие, pan не создаёт новую полосу HTTP requests;
- feature id остаётся canonical/representative id, поэтому dedupe между cells не меняется.

### Reusable vector paths

GeoJSON geometry компилируется в `Path2D` один раз на feature и screen-space point radius. Кеш привязан к объекту feature через `WeakMap`; на feature остаётся не больше шести вариантов радиуса. Bounds по-прежнему кешируются независимо.

### Frame-budgeted exact pass

Точная visible и color-picking сцены строятся на detached Canvas с бюджетом 10 ms на один slice. Между slices renderer отдаёт управление следующему `requestAnimationFrame`.

- текущий raster frame остаётся видимым и репроецируется без ожидания;
- после завершения оба точных passes атомарно копируются в экранные Canvas;
- изменение viewport/data/style отменяет устаревшую сборку;
- после `pointerup` exact pass стартует через 100 ms, чтобы pointer event и ближайшие кадры интерфейса завершились первыми;
- первая сцена без cached frame начинает покадровую сборку немедленно.

## Alternatives considered

### Один синхронный exact render после debounce

Отклонено: main-thread pause сохраняется, только начинается позже.

### Не обновлять exact frame после pan

Отклонено: raster теряет резкость, а picking начинает расходиться с окончательным viewport.

### Немедленно перейти на WebGL/MVT

Остаётся следующим уровнем для проектов без полезных assemblies, но требует отдельного transport и renderer contract. Покадровая сборка устраняет блокирующую task, сохраняя текущий Canvas API.

### Рисовать progressive chunks прямо на visible Canvas

Отклонено: пользователь видел бы неполные кроны и рассогласование visible/picking. Detached surfaces обеспечивают atomic publish.

## Consequences

### Positive

- overview не дублирует крупные assemblies по десяткам мелких cells;
- малый pan использует уже загруженное tile coverage;
- главный поток регулярно возвращается обработке input и animation frames;
- visible и picking публикуются согласованно;
- отменённый data frame не заменяет более новую сцену.

### Negative / trade-offs

- точный кадр появляется не мгновенно, а после фоновой покадровой сборки;
- до публикации виден репроецированный raster, который может быть мягче;
- отдельный очень сложный `Path2D.stroke()` всё ещё может превысить бюджет одного slice;
- Куликовская, где большая часть primitives не образует assemblies, остаётся кандидатом на MVT/WebGL и дополнительную семантическую агрегацию.

## Verification

- scheduler отдаёт управление при исчерпании бюджета и отменяет stale frame;
- overview Песчаного делает не более 6 feature requests;
- pan на 80 CSS pixels после settled state делает 0 новых feature requests;
- cold settled Песчаного укладывается в 3 s на локальном production стенде;
- visible и picking feature id сохраняются после atomic publish;
- API/web tests, typecheck и production Docker build проходят.

## References

- [ADR-0010](0010-coherent-spatial-tile-cache.md)
- [ADR-0011](0011-interaction-raster-frame-cache.md)
- [ADR-0013](0013-derived-cad-render-assemblies.md)
- [Checkpoint 09](../dev-plan/phase-02-checkpoint-09.md)
