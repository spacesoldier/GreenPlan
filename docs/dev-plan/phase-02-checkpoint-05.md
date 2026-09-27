# Phase 2 — checkpoint 05: Canvas viewport virtualization

- Status: Verified
- Date: 2026-09-25
- Decision: [ADR-0009](../adr/0009-viewport-virtualization-and-canvas-rendering.md)
- Work package: [viewport virtualization](phase-02-viewport-virtualization.md)

## Result

2D viewport больше не создаёт SVG/React-узел на каждый CAD-объект. Геометрия загружается полными страницами для расширенного bbox, отсекается по фактическому полю зрения и рисуется двумя Canvas passes: видимым и color-picking.

Клиент отменяет устаревшую цепочку запросов при zoom/pan. Следующий bbox имеет запас 35% и смещение до 25% в сторону движения. В пределах уже загруженного окна повторный запрос не выполняется.

## Implemented contracts

- `GET /v1/models/{model_id}/features` принимает `limit` и `offset`, возвращает `next_offset`;
- серверный порядок страниц детерминирован по `stable_key`;
- клиент запрашивает страницы по 5,000 объектов до `next_offset = null`;
- первый пакет и затем каждые 20,000 объектов появляются прогрессивно;
- новый viewport отменяет предыдущий `AbortController` и не принимает его поздние ответы;
- renderer не рисует объекты prefetch-поля за пределами видимого bbox;
- bounds одной и той же feature кешируются в `WeakMap`;
- выбор объекта выполняется чтением RGB id со скрытого Canvas;
- wheel зарегистрирован как native non-passive listener, поэтому zoom не прокручивает страницу.

## Verification evidence

### Automated

```text
apps/api/.venv/bin/pytest -q
19 passed

cd apps/web && npm test -- --run
3 test files, 11 tests passed

cd apps/web && npm run typecheck
passed

cd apps/web && npm run build
production build passed
```

Новый API contract test проверяет непересекающиеся страницы и `next_offset`. Canvas unit tests проверяют predictive bbox, culling bounds и round-trip picking color.

### Live PostGIS and browser

| Проверка | Результат |
|---|---|
| Песчаный переулок, overview | отрисована завершённая выборка `87,728` объектов |
| Куликовская улица, overview | отрисована завершённая выборка `135,765` объектов |
| DOM при полной выборке | 2 Canvas, 0 `.drawing-feature` SVG nodes |
| API pages 0 и 5,000 | по 5,000 features, 0 совпадающих ids, следующие offsets 5,000 и 10,000 |
| Zoom до 386% на Песчаном | overview request отменён на offset 25,000; новый bbox завершён с 25,326 объектами |
| Zoom + pan на Куликовской | первый zoom bbox получил `ERR_ABORTED`, следующий запрос ушёл со смещённым bbox |
| Wheel | `scrollY = 0`, passive-listener error отсутствует |
| Picking | клик по Canvas выбрал canonical id `6fccadad-dc16-555f-8b91-82f6959cd15c`, загрузил object detail/evidence и записал deep link |

Снимок полной сцены Песчаного: [viewport-canvas-peschanaya-overview.png](../../reports/viewport-canvas-peschanaya-overview.png).

## Known limitation and next step

Полный overview локального CAD-проекта неизбежно содержит все объекты extent. Для Куликовской это 28 последовательных GeoJSON-страниц; ручная проверка завершилась в пределах 30-секундного окна, но transport остаётся тяжёлым. Это не DOM/render bottleneck, а следующий кандидат на оптимизацию.

Следующий spike должен сравнить:

1. keyset pagination вместо повторного `OFFSET`;
2. MVT/binary tiles с HTTP cache;
3. WebGL/deck.gl renderer для сложных стилей и ещё больших сцен.

Scene adapter и canonical object ids при этом сохраняются.
