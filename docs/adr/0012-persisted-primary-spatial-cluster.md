# ADR-0012: Персистентный основной spatial cluster модели

- Status: Accepted
- Date: 2026-09-26
- Owners: domain, frontend
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

Полный extent CAD-файла не равен рабочей территории. Подрядчики оставляют в model space вынесенные блоки, легенды, заготовки и фрагменты для копирования. Fit-to-document делает рабочую улицу мелкой, а stable tile grid, рассчитанный от загрязнённого extent, создаёт слишком крупные tiles. На пилотах первый полный кадр передаёт десятки тысяч примитивов и реагирует на pan с заметной задержкой.

Определять фокус заново в браузере нельзя: результат должен быть одинаковым для web, nanoCAD/FreeCAD и фоновых анализаторов, воспроизводимым по версии модели и доступным без загрузки всей геометрии.

## Decision

### Derived domain record

PostGIS хранит для каждой canonical model одну вычисленную запись `geo.model_spatial_focus`:

- bbox и центр главного кластера в coordinate space модели;
- метод и версия алгоритма;
- параметры кластеризации;
- число объектов в кластере, общее число объектов и coverage ratio;
- время расчёта.

Это derived candidate, а не утверждённая граница проектирования. Он управляет начальным viewport и spatial grid, но не ограничивает доступ к объектам вне него.

### Computation

После импорта один раз выполняется DBSCAN по `ST_PointOnSurface(primary geometry)`:

```text
eps = 25 CAD units
min points = 8
winner = largest non-noise cluster
```

Для текущих `cad_local` моделей единица объявлена как метр, но CRS остаётся candidate. Параметры сохраняются вместе с результатом и могут быть пересчитаны новой версией алгоритма. Если DBSCAN не создаёт кластер, fallback использует extent всех anchor points.

Extent строится по anchor points участников, а не по полным геометриям: одиночная длинная служебная линия не должна снова растянуть initial view. UI добавляет presentation padding самостоятельно.

### API and client

`scene-manifest` возвращает одновременно:

- `extent` — полный документный extent;
- `spatial_focus` — вычисленный основной кластер либо `null`.

Начальный viewport и команда Home используют `spatial_focus.extent`. Полный extent остаётся границей запросов и доступен для ручного перехода. Tile grid получает origin/span от spatial focus, но может иметь отрицательные и выходящие за focus индексы, поэтому pan к удалённым объектам продолжает работать.

Tiles запрашиваются от ближайшего к центру viewport к дальним. Debounce после gesture уменьшается до 60 ms; уже готовый raster frame остаётся на экране.

### Vegetation composition

DXF `CIRCLE` на vegetation layer считается позиционным контуром (`position`), прочая line/polygon geometry — `crown`. Это обеспечивает детерминированный z-order: сначала круг позиции, затем фактический контур кроны. Tile продолжает публиковаться только после получения всех страниц.

## Alternatives considered

### Вычислять bbox на клиенте

Отклонено: требует сначала скачать именно тот объём, который мешает первому кадру, и даёт разные результаты downstream clients.

### Хранить focus в JSON properties canonical model

Отклонено: spatial columns, ограничения целостности и воспроизводимые метрики важнее удобства одного JSON update.

### Считать largest envelope только по количеству объектов в grid cells

Быстрее, но чувствительно к выбору сетки и разрывает длинную улицу на соседние клетки. DBSCAN лучше выражает связную плотную область.

### Удалить удалённые фрагменты

Отклонено: они остаются частью исходного CAD и могут быть нужны для provenance или ручного анализа.

## Consequences

### Positive

- рабочая территория сразу занимает экран;
- одинаковый focus доступен всем клиентам;
- выбросы не раздувают базовый размер spatial tile;
- центр-first loading быстрее даёт полезный кадр;
- удалённые материалы не теряются;
- позиционный круг не перекрывает позднее нарисованную крону.

### Negative / trade-offs

- DBSCAN добавляет несколько секунд к завершению импорта;
- фиксированные 25 units предполагают метрическую CAD-модель и пока требуют review для иных единиц;
- самый плотный кластер не всегда является рабочей территорией, поэтому позже нужен ручной override/acceptance;
- focus не решает сам по себе стоимость передачи всех overview-примитивов; следующим уровнем остаются precomputed LOD/MVT assemblies.

## Verification

- миграция хранит ровно одну focus record на model;
- повторный расчёт идемпотентно заменяет запись;
- manifest возвращает document extent и persisted spatial focus;
- initial/Home viewport использует focus extent;
- grid остается стабильным внутри focus и создаёт tiles за его пределами;
- tile order начинается от центра запрошенного bbox;
- vegetation `CIRCLE` импортируется с role `position`;
- оба пилота открываются на основном кластере, удалённые фрагменты доступны через pan;
- pan начинает запрос не позднее 60 ms после gesture.

## References

- [ADR-0009](0009-viewport-virtualization-and-canvas-rendering.md)
- [ADR-0010](0010-coherent-spatial-tile-cache.md)
- [ADR-0011](0011-interaction-raster-frame-cache.md)
- [Work package](../dev-plan/phase-02-primary-spatial-focus.md)
- [Checkpoint 08](../dev-plan/phase-02-checkpoint-08.md)
