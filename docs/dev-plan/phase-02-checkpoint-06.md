# Phase 2 — checkpoint 06: coherent spatial tile cache

- Status: Verified
- Date: 2026-09-25
- Decision: [ADR-0010](../adr/0010-coherent-spatial-tile-cache.md)
- Work package: [coherent spatial tile cache](phase-02-coherent-tile-cache.md)

## Result

Произвольные перекрывающиеся bbox заменены стабильной project-relative tile grid. Tile накапливает все HTTP pages в staging и только после завершения становится доступен renderer. Поэтому arrival order страниц больше не определяет визуальный порядок и не показывает позиционные круги отдельно от поздно пришедших контуров крон.

Cache переиспользует ready и pending tile requests, дедуплицирует features по canonical id и ограничен LRU-бюджетом `350,000` feature references. При смене проекта pending requests отменяются. При смене LOD предыдущий кадр остаётся на Canvas до атомарного commit нового набора tiles.

## Implementation details

- стабильный key: `model_id/model_version/lod/column/row`;
- grid divisions по LOD: `128 / 32 / 8 / 2`;
- до двух tile loaders выполняются параллельно;
- страницы внутри tile загружаются последовательно по 5,000 features;
- соседние tile results дедуплицируются по `Feature.id`;
- deterministic order: base geometry → vegetation position → other vegetation → crown;
- Canvas renders coalesced через `requestAnimationFrame`;
- immutable model pages: `private, max-age=300, stale-while-revalidate=3600`;
- BFF передаёт `Cache-Control` браузеру;
- PostGIS manifest кешируется по immutable `model_id` и не пересчитывается для каждой страницы.

## Verification evidence

### Automated

```text
apps/api/.venv/bin/pytest -q
20 passed

cd apps/web && npm test -- --run
4 test files, 17 tests passed

cd apps/web && npm run typecheck
passed

cd apps/web && npm run build
production build passed
```

Unit contracts проверяют stable grid, pending request coalescing, staging visibility, canonical-id dedupe, vegetation z-order, protected LRU eviction и BFF cache header.

### Live PostGIS and browser

| Проверка | Результат |
|---|---|
| Песчаный overview | полный кадр `87,728` объектов |
| Куликовская overview | полный кадр `135,765` объектов |
| Zoom на Песчаном, 350 ms после начала | новый LOD ещё грузится, старый Canvas остаётся видимым (`39,736` непрозрачных pixels в dense anchor) |
| Малый pan в готовом cache window | `0` новых feature requests; count остался `86,660` |
| Pan через tile boundary | `3` новых запроса вместо повторной загрузки всего bbox |
| Возврат zoom к готовому overview | `0` новых запросов, немедленно восстановлено `87,728` объектов |
| HTTP cache через Next.js BFF | заголовок `private, max-age=300, stale-while-revalidate=3600` сохранён |
| Browser console | application errors отсутствуют; остаётся только отдельный `favicon.ico` 404 |

## PostGIS concurrency finding

Первый прогон с тремя параллельными tile loaders выявил стандартный лимит `/dev/shm` контейнера: PostgreSQL получил `could not resize shared memory segment ... No space left on device`.

Исправлено тремя мерами:

1. manifest агрегаты кешируются и не запускаются на каждой feature page;
2. client concurrency ограничен двумя tile loaders;
3. PostGIS контейнеру задан `shm_size: 256mb`.

После повторного развёртывания оба полных проекта и zoom/pan сценарии прошли без `500`, `DiskFull` и traceback.

## Remaining limitation

Data cache устраняет повторную передачу и page tearing, но обычный Canvas остаётся immediate-mode renderer: при изменении viewport видимые векторы необходимо трассировать снова. `requestAnimationFrame` объединяет лишние React updates, однако не заменяет raster reuse.

Если профилирование 20 проектов покажет render-bound задержки, следующий отдельный spike:

1. raster tile cache на `OffscreenCanvas`/`ImageBitmap`;
2. мгновенная композиция старых bitmap tiles во время gesture;
3. vector redraw после окончания gesture;
4. отдельный picking tile или spatial hit-test;
5. сравнение с deck.gl/MVT WebGL pipeline.

Raster cache нельзя включать вслепую: требуется определить pixel ratio, bearing/style invalidation и memory budget.
