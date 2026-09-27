# Развёртывание предметной PostGIS-БД

Дата: 2026-09-24.

## Разделение баз

- `postgres:16-alpine`, host port `35483`, bind-mount `platform/data/postgres` — существующая операционная БД конвертера;
- `postgis/postgis:16-3.5-alpine`, host port `36483`, bind-mount `platform/data/postgis` — новая предметная БД `greenplan_domain`.

Старый контейнер и его данные не изменялись.

## Применённая схема

Init-каталог: `platform/db/postgis-init`.

1. `001_domain_schema.sql` — расширения и доменные таблицы;
2. `002_seed_catalogs.sql` — стартовые классы объектов, воздействий и биологических требований;
3. `003_integrity_and_views.sql` — integrity triggers и API views;
4. `004_model_immutability.sql` — полная защита утверждённых canonical models.

Созданы PostgreSQL schemas: `core`, `catalog`, `geo`, `biology`, `rules`, `planning`, `provenance`, `intake`, `ops`, `audit`, `api`.

После запуска подтверждены:

- PostgreSQL `16.15`;
- PostGIS `3.5.7`;
- `ltree` `1.2`;
- `pgcrypto` `1.3`;
- 78 таблиц в десяти хранимых схемах;
- 33 стартовых класса пространственных объектов;
- 8 стартовых классов воздействий;
- четыре записи в `ops.schema_migrations`.

## Проверки

Транзакционный smoke test создал workspace → project → revision → territory → coordinate space → canonical model → building → footprint и затем выполнил `ROLLBACK`.

Проверено:

- geometry с SRID модели принимается;
- geometry с другим SRID отклоняется trigger-функцией;
- после перевода canonical model в `approved` изменение её geometry блокируется;
- контейнер имеет состояние `healthy`.
