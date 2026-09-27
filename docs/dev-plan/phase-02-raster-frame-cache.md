# Phase 2 work package — interaction raster frame cache

- Status: Complete
- Date: 2026-09-25
- Prerequisite: [ADR-0011](../adr/0011-interaction-raster-frame-cache.md)

## Outcome

Непрерывные pan/zoom/rotate используют bitmap reprojection. Векторная сцена и picking перерисовываются один раз после gesture либо debounce, без исчезновения составных обозначений растений.

## Tests before implementation

1. Affine matrix identity и inverse round-trip.
2. Reprojection даёт те же screen coordinates, что прямой target transform.
3. Bearing участвует в reprojection.
4. Raster LRU соблюдает byte budget.
5. Style/frame key разделяет selection и layer visibility.
6. Browser test измеряет vector render count во время gesture.
7. Picking сохраняет canonical id после raster reprojection и exact refresh.

## Work order

1. Реализовать и протестировать affine viewport transforms.
2. Добавить bounded raster frame LRU.
3. Ввести stable canonical frame key из ready spatial tiles.
4. Разделить immediate bitmap composition и deferred exact render.
5. Синхронно репроецировать visible и picking passes.
6. Проверить оба пилота и зафиксировать метрики.

## Exit gate

- pointer move не вызывает vector tracing;
- exact redraw выполняется после окончания gesture;
- wheel burst coalesced одним delayed redraw;
- raster cache ограничен 64 MiB;
- picking, layers и selection корректны;
- automated tests и production build проходят.

## Completion

Реализация и проверяемые метрики зафиксированы в [checkpoint 07](phase-02-checkpoint-07.md). Exit gate пройден 2026-09-25.
