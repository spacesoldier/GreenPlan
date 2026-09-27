# Phase 2 — checkpoint 09: render assemblies и отзывчивый exact frame

- Status: Complete
- Date: 2026-09-26
- Decisions: [ADR-0013](../adr/0013-derived-cad-render-assemblies.md), [ADR-0014](../adr/0014-frame-budgeted-cad-rendering.md)
- Work package: [derived CAD render assemblies](phase-02-render-assemblies.md)

## Result

Canonical DXF primitives и provenance сохранены, но viewport больше не обязан передавать и рисовать каждый дочерний сегмент растительного CAD-блока как отдельный feature. PostGIS публикует derived assembly с exact geometry и тремя заранее рассчитанными LOD. API объединяет assemblies с canonical objects, не вошедшими в assembly.

На frontend добавлены recursive `GeometryCollection`/multi-geometry rendering, крупные overview cells, повторное использование полного покрытия cell, ограниченный `Path2D` cache и покадровая сборка exact visible+picking passes на detached Canvas. Во время сборки остаётся виден репроецированный raster frame; готовые passes публикуются атомарно.

## Stored projection

| Project | Canonical objects | Assemblies | Assembly members | Render features, all extent |
|---|---:|---:|---:|---:|
| Песчаный переулок | 87 728 | 2 147 | 84 951 | 4 924 |
| Куликовская улица | 135 765 | 1 787 | 2 927 | 134 625 |

Membership содержит 87 878 уникальных object ids; отсутствующих representative canonical objects — 0. Повторный refresh идемпотентно удаляет и пересобирает derived projection, не изменяя canonical rows.

На Песчаном transport count уменьшен в 17.8 раза по всем классам и примерно в 39.6 раза для 84 951 объединённого vegetation scope. Assembly с position и crown разрешается через прежний object endpoint и возвращает исходные asset, layer и handle.

## LOD diagnostics

LOD строится для каждого member до `ST_Collect`. Для крупнейших assemblies:

| Members | Exact points | LOD3 points | Exact memory | LOD3 memory |
|---:|---:|---:|---:|---:|
| 965 | 688 045 | 7 913 | 11 MiB | 131 KiB |
| 845 | 602 485 | 6 929 | 9.2 MiB | 115 KiB |
| 975 | 268 575 | 3 075 | 4.1 MiB | 56 KiB |
| 2 160 | 110 448 | 7 776 | 1.7 MiB | 150 KiB |

Полный focus Песчаного на LOD3 отдаёт около 11.5 MB JSON за 1.1 s через прямой API-вызов. Browser transport дробит его на шесть крупных cache cells, сохраняя progressive/cancellable contract.

## Browser measurements

Production containers, cold-cache headless Chrome, settled state; после загрузки выполнен pan на 80 CSS pixels.

| Metric | Песчаный | Куликовская |
|---|---:|---:|
| Objects in composed focus frame | 4 838 | 128 473 |
| Cold settled | 1.54 s | 23.61 s |
| Feature HTTP requests | 6 | 31 |
| New requests after pan | 0 | 0 |
| Double `requestAnimationFrame` after pointer-up | 28 ms | 26 ms |

Для Песчаного checkpoint 08 фиксировал 16.71 s до settled main cluster при 86 578 отдельных features. Таким образом, текущий путь быстрее примерно в 10.8 раза и сокращает browser feature count примерно в 17.9 раза.

`Path2D` и frame-budgeted renderer снизили синхронную задержку ближайшего кадра после pointer-up с измеренных 405–552 ms до 28 ms. Exact pass продолжает собираться после этого покадрово, не заменяя экран частичным visible/picking результатом.

## Provenance and identity check

Проверочный mixed assembly:

```text
representative id: 8cea19a8-f340-5caa-91e8-c40b8f7231c3
members: 975
roles: crown, position
source: dxf/Проектное решение /DWG/ГР_Песчаный переулок.dxf
layer: 04 Дендроплан (растения)
handle: 7831
```

Representative id существует в `geo.spatial_objects`; `/v1/objects/{id}` возвращает прежний stable key и source reference. Следовательно, color picking/deep link сохраняют canonical identity, хотя сцена рисует assembly.

## Automated verification

```text
API: 22 passed
Web: 6 files, 29 tests passed
TypeScript typecheck: passed
Next.js production build: passed
API, PostGIS, PostgreSQL and Web containers: running; healthchecked services healthy
```

Тесты дополнительно фиксируют nested GeometryCollection bounds, overview cell coverage, tile dedupe, frame-budget yield и отмену устаревшего exact frame.

## Remaining boundary

Куликовская остаётся тяжёлой не из-за pan/render scheduling, а из-за структуры источника: только 2 927 из 135 765 canonical objects имеют общий пригодный ключ assembly. Интерфейс во время pan отзывчив и не перезапрашивает данные, но cold load 23.61 s не соответствует будущему production gate.

Следующий performance work package для такого класса проектов должен исследовать:

1. parent `INSERT`/block instance identity при импорте вместо одного leaf handle;
2. MVT или бинарный geometry transport;
3. WebGL renderer с GPU buffers;
4. server-side line merge только как derived projection с проверяемым provenance membership.

## Exit gate

| Requirement | Evidence | Status |
|---|---|---|
| Canonical/provenance не потеряны | counts неизменны; membership и representative проверены | Passed |
| Песчаный vegetation transport сокращён минимум в 20 раз | 84 951 members → 2 147 assemblies, 39.6× | Passed |
| Position и crown атомарны | mixed assembly из 975 members | Passed |
| Песчаный cold load улучшен | 16.71 s → 1.54 s | Passed |
| Small pan без reload/main-frame stall | 0 requests; 28 ms double-rAF | Passed |
| Оба пилота отображаются | 4 838 и 128 473 focus features | Passed |
| Regression/build | API 22, Web 29, typecheck, production build | Passed |
| Production cold gate для Куликовской | 23.61 s; требуется следующий work package | Not passed |
