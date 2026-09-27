# Phase 2 — checkpoint 08: persisted spatial focus and viewport hysteresis

- Status: Complete
- Date: 2026-09-26
- Decision: [ADR-0012](../adr/0012-persisted-primary-spatial-cluster.md)
- Work package: [primary spatial focus](phase-02-primary-spatial-focus.md)

## Result

Initial/Home viewport больше не использует загрязнённый полный extent DXF. Основной DBSCAN-кластер вычисляется после импорта, хранится в PostGIS и входит в scene manifest. Удалённые заготовки не удаляются и остаются достижимы через pan.

Tile grid привязан к bbox focus, но поддерживает отрицательные и внешние индексы. Tiles загружаются от центра наружу. Активное prefetch-окно имеет hysteresis: пока видимый bbox остаётся внутри уже загруженного окна, небольшой pan не создаёт новую полосу запросов.

Vegetation `CIRCLE` теперь имеет role `position`, а line/polygon detail — `crown`. Crown geometry получает в четыре раза более осторожный LOD tolerance и рисуется после позиционного круга.

## Persisted focus records

Параметры расчёта: `ST_ClusterDBSCAN`, `eps=25`, `minpoints=8`, anchor `ST_PointOnSurface`, algorithm version `1`.

| Project | Main cluster | Total | Coverage | Focus bbox |
|---|---:|---:|---:|---|
| Песчаный переулок | 86 576 | 87 728 | 98.68685% | `708.562,14391.667 — 862.019,14969.677` |
| Куликовская улица | 129 271 | 135 765 | 95.21673% | `3715.530,-11467.265 — 4831.129,-9602.622` |

В PostGIS обновлено 8 779 vegetation circles: 7 584 на Песчаном и 1 195 на Куликовской.

## Browser measurements

Cold-cache Chromium, production containers, Песчаный:

| Milestone | Time from navigation | Composed features |
|---|---:|---:|
| First tiny frame | 0.24 s | 3 |
| First useful central frame | 1.62 s | 6 961 |
| Expanded central frame | 2.18 s | 18 414 |
| Majority of visible detail | 4.44 s | 40 709 |
| Main cluster present | 12.76 s | 86 576 |
| Prefetch window settled | 16.71 s | 86 578 |

До focus-relative center-first tiles первый кадр появлялся только после полного ожидания, примерно через 15.5 s.

После полной загрузки drag на 80 CSS pixels:

- новый raster frame появляется во время gesture;
- feature count остаётся 86 578;
- новых feature HTTP requests: `0`;
- до viewport hysteresis тот же сценарий создавал 21 запрос и ждал около 8.2 s.

Screenshot: [Песчаный, initial primary focus](../../reports/peschanaya-primary-focus.png).

## Crown diagnostics

Проверка source geometry после role migration:

| Project | Position circles | Crown geometry within 5 CAD units |
|---|---:|---:|
| Песчаный переулок | 7 584 | 7 581 |
| Куликовская улица | 1 195 | 858 |

Следовательно, на Песчаном почти каждый круг имеет фактическую crown geometry и теперь получает правильный z-order/LOD. На Куликовской 337 кругов не имеют crown geometry в радиусе 5 units; это уже вопрос состава исходного CAD или семантической сборки, а не потеря страницы transport.

## Automated verification

```text
API: 22 passed
Web: 5 files, 25 tests passed
TypeScript typecheck: passed
Next.js production/Docker build: passed
API, PostGIS, Web containers: healthy
```

Tests фиксируют manifest focus contract, vegetation circle role, focus-relative external tile indices, center-first order и prefetch containment.

## Remaining performance boundary

Полное overview-окно всё ещё содержит десятки тысяч низкоуровневых DXF primitives. На Песчаном 63 252 vegetation `LINE` происходят всего из примерно 1 120 source handles; отдельные символы состоят из десятков и сотен сегментов. Следующий существенный шаг — derived render assemblies/MVT, группирующие дочерние primitives одного CAD block без утраты provenance. Увеличение debounce или очередной Canvas cache не устранит этот объём данных.

## Exit gate

| Requirement | Evidence | Status |
|---|---|---|
| Focus persisted for both models | two PostGIS records with metrics | Passed |
| Initial/Home use focus | browser screenshot and manifest contract | Passed |
| Useful progressive frame | 6 961 features at 1.62 s cold | Passed |
| Small pan avoids network reload | zero new requests versus previous 21 | Passed |
| Circle below crown | role migration, render order and LOD policy | Passed |
| Remote data remains reachable | unbounded focus-relative grid clipped only by document extent | Passed |
| Regression/build | API 22, Web 25, typecheck and Docker build | Passed |
