# Phase 2 work package — viewport virtualization

- Status: Complete
- Date: 2026-09-25
- Prerequisite: [ADR-0009](../adr/0009-viewport-virtualization-and-canvas-rendering.md)

## Outcome

Все объекты видимого bbox постепенно появляются на Canvas без создания feature DOM nodes. Pan/zoom отменяет старую загрузку и предзагружает полосу в направлении движения. Picking объекта остаётся доступным.

## Tests before implementation

1. API pagination возвращает непересекающиеся страницы и завершение.
2. Расширенный bbox содержит viewport и смещается по направлению pan.
3. Feature bounds и culling корректны для Point, LineString и Polygon.
4. Picking color стабильно кодирует/декодирует индекс объекта.
5. Browser smoke получает больше одной страницы, меняет viewport и выбирает объект Canvas.

## Work order

1. Расширить feature endpoint параметрами `offset` и `limit`.
2. Добавить клиентский abortable page loader.
3. Добавить predictive buffered bbox.
4. Заменить SVG feature tree двумя Canvas passes.
5. Проверить полный bbox и navigation latency на обоих пилотах.
6. Зафиксировать измерения и ограничения в checkpoint report.

## Exit gate

- видимый bbox не ограничен первой страницей;
- старые ответы не заменяют данные нового viewport;
- Canvas сохраняет pan/zoom/bearing и picking;
- тесты и production Docker build проходят;
- оба пилота остаются доступны через существующие deep links.

Gate пройден. Результаты и ограничения зафиксированы в [checkpoint 05](phase-02-checkpoint-05.md).
