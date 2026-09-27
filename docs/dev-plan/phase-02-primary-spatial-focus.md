# Phase 2 work package — primary spatial focus and responsive tile loading

- Status: Complete
- Date: 2026-09-26
- Prerequisite: [ADR-0012](../adr/0012-persisted-primary-spatial-cluster.md)

## Outcome

При открытии CAD-проекта основной кластер объектов крупно занимает viewport. Его центр и bbox вычислены один раз и хранятся в PostGIS. Pan загружает ближайшие tiles первым, а круг позиции растения стабильно рисуется под контуром кроны.

## Tests before implementation

1. API manifest exposes persisted focus contract.
2. Focus-relative tile grid сохраняет stable keys.
3. Grid строит допустимые отрицательные/внешние индексы для удалённых материалов.
4. Tiles сортируются по расстоянию до центра request bbox.
5. DXF vegetation `CIRCLE` получает role `position`.
6. Existing crown z-order test остаётся зелёным.

## Work order

1. Добавить PostGIS migration и идемпотентную функцию расчёта.
2. Включить расчёт в конец import pipeline.
3. Расширить manifest contract.
4. Перевести initial/Home viewport и tile grid на persisted focus.
5. Включить center-first loading и 60 ms settle delay.
6. Переклассифицировать vegetation circles и проверить оба пилота.

## Exit gate

- focus записан для обеих моделей с сохранёнными metrics;
- browser стартует на focus, а не document extent;
- центральная часть появляется до окончания фоновой подгрузки всего окна;
- удалённые фрагменты остаются достижимы;
- круг/крона имеют детерминированный порядок;
- API/web tests, typecheck и production build проходят.

## Completion

Реализация, DB metrics и browser timings зафиксированы в [checkpoint 08](phase-02-checkpoint-08.md). Exit gate пройден 2026-09-26.
