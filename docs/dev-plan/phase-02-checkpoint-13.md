# Phase 2 — checkpoint 13: корректная paint-семантика крон и ограничение tile fan-out

- Status: Complete
- Date: 2026-09-27
- Decisions: [ADR-0010](../adr/0010-coherent-spatial-tile-cache.md), [ADR-0013](../adr/0013-derived-cad-render-assemblies.md), [ADR-0014](../adr/0014-frame-budgeted-cad-rendering.md), [ADR-0016](../adr/0016-geometry-paint-and-plant-position-semantics.md)

## Symptoms

1. После zoom/pan сложные условные обозначения крон иногда выглядели как россыпь треугольников и замкнутых ломаных.
2. Правильная детальная графика появлялась с большой задержкой или после переключения окон.
3. Часть посадочных мест оставалась окружностями, из-за чего было неясно, отсутствует ли растение или только его графическая связь.

## Root causes

### Mixed geometry was filled as one path

Derived assembly объединяет position, crown и вспомогательные линии в `GeometryCollection`. Старый renderer строил один `Path2D` и вызывал `fill()` по типу верхнеуровневой geometry. Canvas неявно замыкал открытые линии сложной кроны, создавая треугольники.

### Excessively fine transport grid

После исправления viewport aspect двухэкранный prefetch мог пересечь сотни слишком мелких tiles. Одна и та же крупная assembly дублировалась по запросам, а до complete atomic commit пользователь продолжал видеть репроецированный старый raster. Переключение окна лишь давало очереди время завершиться и не являлось исправлением.

### Position and crown are not always one CAD entity

Окружность `position` может иметь crown в том же block handle, рядом в другом entity либо не иметь найденной crown. Эти случаи нельзя различить только по внешнему виду окружности.

## Fix

1. GeoJSON geometry рекурсивно разбирается на point/line/polygon primitives.
2. Renderer хранит независимые stroke и fill paths; открытые линии никогда не заполняются.
3. Тот же partition применяется в color-picking pass.
4. Детальность transport grid изменена с `[128, 32, 16, 1]` на `[32, 8, 4, 1]` divisions по LOD.
5. Сохранены feature dedupe, полный atomic tile commit и bounded `Path2D` cache.
6. Object detail дополняется метаданными render assembly; инспектор отличает «составная графика найдена» от «только маркер положения».
7. Зафиксирована предметная семантика position/crown; автоматический nearest-neighbour merge в этот checkpoint не входит.

## Browser acceptance

Песчаный переулок, production build, последовательный zoom одного участка:

| Zoom | Composed features | Cumulative feature requests | Result |
|---:|---:|---:|---|
| 100% | 4 839 | 12 | overview готов |
| 212% | 4 774 | 47 | mixed assemblies без ложной заливки |
| 448% | 2 279 | 75 | detail geometry опубликована целиком |
| 949% | 2 279 | 75 | повторно использован cache |
| 2 009% | 621 | 99 | ветвистые кроны остаются линиями |

До укрупнения grid та же последовательность создавала 1 103 feature requests. После изменения — 99.

## Position/crown diagnostic

Диагностическая классификация vegetation positions по общему assembly и наличию crown в радиусе 5 CAD units:

| Проект | Positions | Same assembly | Nearby other entity | No crown within 5 |
|---|---:|---:|---:|---:|
| Куликовская улица | 1 195 | 456 | 431 | 308 |
| Песчаный переулок | 7 584 | 7 356 | 226 | 2 |

Вывод: на Песчаном почти каждая окружность имеет графику кроны, но 226 связей проходят между отдельными CAD entities и ещё не являются canonical relationship. На Куликовской доля реально unmatched positions существенно выше. Следующий предметный шаг — one-to-one spatial matching с ambiguity score и review, а не безусловное склеивание ближайших объектов.

## Automated verification

```text
Web: 6 files, 36 tests passed
TypeScript typecheck: passed
Next.js standalone production build: passed
Next.js production Docker build: passed
Web container running on port 38101
```

Новые tests фиксируют:

- primitive partition mixed `GeometryCollection`;
- отсутствие open crown lines в fill path;
- ограниченный tile fan-out для двух соседних detail windows.

## Exit gate

| Requirement | Evidence | Status |
|---|---|---|
| Open lines не превращаются в polygons | primitive partition test + browser image | Passed |
| Picking следует той же paint-семантике | общий `geometryPaths` | Passed |
| Exact detail не ждёт сотни tiles | 1 103 → 99 requests | Passed |
| UI не объявляет position подтверждённым растением | ADR-0016 semantic contract | Passed |
| Production regression | 36 tests, typecheck, build, running container | Passed |
