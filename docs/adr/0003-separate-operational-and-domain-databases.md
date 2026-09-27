# ADR-0003: Операционная БД конвертера отделена от предметного PostGIS

- Status: Accepted
- Date: 2026-09-25
- Owners: platform and data architecture
- Related phase: Phase 1
- Supersedes: —
- Superseded by: —

## Context

Существующая PostgreSQL хранит jobs, stages, logs и conversion artifacts. Предметная модель требует PostGIS, версий проектов, геометрии, нормативов, растений, provenance и строгой целостности. Миграция операционной базы на месте создала бы ненужный риск для уже завершённой конвертации.

## Decision

- `postgres` остаётся операционной БД CAD-конвертера.
- `postgis` хранит предметную модель GreenPlan в отдельном PGDATA и на отдельном host port.
- Связь выполняется через устойчивые идентификаторы, hashes и intake-процесс, а не межбазовые foreign keys.
- Обе БД используют bind-mounted каталоги `platform/data/*`, не anonymous Docker volumes.
- Новая схема изменяется последовательными SQL migrations и журналируется в `ops.schema_migrations`.

## Alternatives considered

### Одна общая PostGIS-БД сразу

Технически проще для join, но опасно смешивает lifecycle jobs и утверждённых предметных моделей и требует рискованного преобразования существующей БД.

### Файлы вместо предметной БД

Не позволяют надёжно отвечать на запросы provenance, versioning, rule applicability и spatial relationships.

## Consequences

### Positive

- сбой доменной разработки не повреждает историю конвертации;
- backup/retention и доступы можно разделить;
- предметная схема не зависит от внутренней структуры Celery jobs.

### Negative / trade-offs

- нет атомарной транзакции между двумя БД;
- ingestion должен быть идемпотентным и сверять hashes;
- compose и мониторинг содержат две СУБД.

## Verification

- разные bind mounts и host ports;
- healthcheck обеих БД;
- schema migration smoke tests;
- повторный intake не создаёт дубликаты одного source asset;
- восстановление каждой БД проверяется независимо.

## References

- [Отчёт PostGIS](../../platform/reports/postgis-domain-db-2026-09-24.md)
- [Физическая схема](../12-database-schema-v1.md)
