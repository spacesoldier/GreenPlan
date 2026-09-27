# ADR-0015: Overscan-поля для непрерывного CAD pan

- Status: Accepted
- Date: 2026-09-26
- Owners: frontend
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

ADR-0011 сохраняет последний exact Canvas frame и репроецирует его во время drag. Однако frame имел размер ровно с видимый Canvas. Даже при наличии spatial features в tile cache сдвиг камеры немедленно открывал край bitmap, на котором ещё не было нарисованных растений. До завершения следующего exact pass это выглядело как исчезновение объектов.

Spatial prefetch сам по себе проблему не решает: загруженная в память geometry и уже растеризованные pixels — разные уровни кеша.

## Decision

### Data overscan

Prefetch bbox расширяется на `0.5 × viewport` с каждой стороны, то есть покрывает до `2 × viewport` по каждой оси до directional lead и clipping по document extent.

### Raster overscan

Exact visible и picking passes строятся для viewport с полем `0.4 × viewport` с каждой стороны:

```text
render width  = 1.8 × visible viewport width
render height = 1.8 × visible viewport height
```

Размер detached Canvas увеличивается тем же коэффициентом, поэтому pixel density совпадает с экранной. Готовый overscan frame хранит собственные viewport/size и при публикации обрезается `rasterReprojectionMatrix` до текущего видимого Canvas.

Visible и color-picking surfaces имеют одинаковые поля и публикуются атомарно. При последующем pan до края overscan выполняется только bitmap reprojection; exact frame перестраивается после окончания gesture.

### Memory budget

Один overscan frame требует примерно `1.8² = 3.24` объёма прежнего frame. Общий LRU budget остаётся 64 MiB: увеличение одного frame автоматически уменьшает число удерживаемых исторических кадров, не создавая неограниченного роста памяти.

## Alternatives considered

### Увеличить только spatial prefetch

Отклонено: geometry загружена, но отсутствующие pixels всё равно нельзя показать во время drag без vector redraw.

### Exact redraw на каждом pointer move

Отклонено ADR-0011: возвращает main-thread stalls на плотных дендропланах.

### Overscan больше 2×

Отложено: квадратично увеличивает Canvas memory и стоимость exact pass. Текущие 1.8× raster / 2× data покрывают обычный gesture примерно на треть экрана в любую сторону.

## Consequences

### Positive

- растения не обрываются на границе Canvas при обычном pan;
- gesture не ждёт сеть или vector renderer;
- picking соответствует overscanned visible frame;
- память остаётся ограниченной существующим LRU.

### Negative / trade-offs

- exact pass рисует область в 3.24 раза больше по пикселям;
- LRU хранит меньше исторических frame keys;
- drag дальше примерно 40% viewport без остановки всё ещё может достигнуть края bitmap;
- очень большие Canvas/devicePixelRatio могут потребовать адаптивного уменьшения overscan в будущем.

## Verification

- centered expansion 1.8× зафиксирован unit test;
- pan на 160 CSS pixels сохраняет растения в кадре до `pointerup`;
- во время gesture выполняются raster blits, не vector redraws;
- после settled state pan не создаёт feature HTTP requests;
- cold load и input latency не регрессируют относительно checkpoint 10.

## References

- [ADR-0011](0011-interaction-raster-frame-cache.md)
- [ADR-0014](0014-frame-budgeted-cad-rendering.md)
- [Checkpoint 11](../dev-plan/phase-02-checkpoint-11.md)
