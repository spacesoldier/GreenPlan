# ADR-0004: Каноническая модель версионируется, а approved revision неизменяема

- Status: Accepted
- Date: 2026-09-25
- Owners: domain architecture
- Related phase: Phase 1
- Supersedes: —
- Superseded by: —

## Context

Одну территорию описывают DWG/XREF, PDF, ведомости, OSM и ручные решения. Геометрии могут конфликтовать, иметь разные системы координат и относиться к разным моментам времени. Хранение только «последнего состояния» уничтожило бы объяснимость расчёта.

## Decision

- Каждый расчёт ссылается на явный UUID canonical model, а не на неявную `current` запись.
- Source assets/fragments, transforms и object evidence сохраняются отдельно от предметного объекта.
- Исходная и нормализованная геометрия не подменяют друг друга.
- После `assembly_status=approved` объекты, геометрии и зависимости модели нельзя изменять; исправление создаёт дочернюю draft model.
- Неопределённость представляется статусами `unknown`, `candidate`, `conflict`, `needs_review`, а не нулём или guessed value.

## Alternatives considered

### Единый редактируемый слой объектов

Отклонён: невозможно воспроизвести старый расчёт и определить, какой источник изменил решение.

### Хранить provenance только в JSON-логах

Отклонён: связи нельзя надёжно валидировать и запрашивать как предметные данные.

## Consequences

### Positive

- расчёты и отчёты воспроизводимы;
- конфликт источников остаётся видимым;
- approved model пригодна как audit boundary.

### Negative / trade-offs

- модели занимают больше места;
- публикация требует явного workflow;
- UI должен показывать версию и статус модели.

## Verification

- DB trigger блокирует изменение approved model и её геометрии;
- geometry SRID совпадает с coordinate space модели;
- object evidence указывает ровно на один source fragment или external feature;
- API engineering operations требуют явный `model_id`.

## References

- [Предметная модель](../10-domain-data-model.md)
- [Схема БД](../12-database-schema-v1.md)
- [PostGIS smoke-test](../../platform/reports/postgis-domain-db-2026-09-24.md)
