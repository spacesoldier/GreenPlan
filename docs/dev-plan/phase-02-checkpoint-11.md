# Phase 2 — checkpoint 11: overscan-поля для pan

- Status: Complete
- Date: 2026-09-26
- Decision: [ADR-0015](../adr/0015-overscanned-raster-frames.md)

## Result

Spatial prefetch увеличен до двух viewport, а exact visible/picking raster frame строится для области 1.8 viewport. Во время pan renderer показывает соседние уже нарисованные pixels вместо пустого края и не запускает синхронную векторную перерисовку.

## Browser acceptance

Production build, Песчаный переулок, cold cache. После settled frame выполнен непрерывный горизонтальный pan на 160 CSS pixels с захваченной мышью.

```text
cold settled:             1.50 s
feature requests:         6
new requests during pan:  0
raster blits:             19
vector redraws in drag:   0
double-rAF after release: 20 ms
main task during check:   49 ms
composed features:        4 838
```

Кадр снят до `pointerup`: растительные круги, кроны и границы продолжаются в открывшуюся область; обрыва по старой границе viewport нет.

## Automated verification

```text
Web: 6 files, 32 tests passed
TypeScript typecheck: passed
Next.js production Docker build: passed
Web container running on port 38101
```

## Exit gate

| Requirement | Evidence | Status |
|---|---|---|
| Минимум 1.5 viewport raster coverage | configured and tested 1.8× | Passed |
| Data шире raster coverage | 2× spatial prefetch versus 1.8× raster | Passed |
| Plants remain during active pan | 160 px pre-pointerup browser capture | Passed |
| No network reload for ordinary pan | 0 new feature requests | Passed |
| Input remains responsive | 20 ms double-rAF | Passed |
