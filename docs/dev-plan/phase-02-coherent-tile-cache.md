# Phase 2 work package — coherent spatial tile cache

- Status: Complete
- Date: 2026-09-25
- Prerequisite: [ADR-0010](../adr/0010-coherent-spatial-tile-cache.md)

## Outcome

Повторный zoom/pan не загружает перекрывающуюся геометрию заново. Кадр меняется только целыми spatial tiles, имеет детерминированный vegetation z-order и сохраняет предыдущий LOD до готовности нового.

## Tests before implementation

1. Stable grid возвращает одинаковые tile keys для одинаковой области.
2. Cache объединяет параллельные обращения к одному tile в один loader call.
3. Feature на границе двух tiles дедуплицируется по canonical id.
4. Staging tile не доступен для frame composition до завершения всех страниц.
5. Position markers сортируются раньше crown geometry.
6. LRU не удаляет tiles активного кадра.
7. BFF сохраняет cache policy versioned geometry response.
8. Browser smoke подтверждает stale-frame zoom и загрузку только новой полосы при pan.

## Work order

1. Реализовать stable CAD tile grid и cache contracts.
2. Перенести page accumulation из React effect в tile loader.
3. Добавить ready/staging state, dedupe и bounded LRU.
4. Ввести atomic LOD frame commit и deterministic render order.
5. Передавать browser-private cache headers через FastAPI/BFF.
6. Проверить оба пилота и зафиксировать network/render evidence.

## Exit gate

- page tearing отсутствует;
- возврат к уже просмотренной области не создаёт новых feature requests;
- pan догружает только отсутствующие tile keys;
- feature count не падает к размеру одной страницы при zoom;
- оба пилота сохраняют picking и layer visibility;
- tests, typecheck и production build проходят.

Gate пройден. Результаты и эксплуатационные ограничения зафиксированы в [checkpoint 06](phase-02-checkpoint-06.md).
