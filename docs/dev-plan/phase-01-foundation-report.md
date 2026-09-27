# Phase 1 — Foundation and dataset reconnaissance

- Status: Complete
- Period: 2026-09-21 — 2026-09-25
- Owners: architecture, CAD ingestion, data platform
- Nature: retrospective report for work completed before formal phase governance

## Outcome

Создан воспроизводимый фундамент: весь доступный DWG-корпус конвертирован в зеркальное DXF-дерево, второй reader дал независимую диагностику, развернута отдельная предметная PostGIS-БД, а архитектура OSM-кандидатов и нормативного ingestion закреплена схемой и документацией.

Phase 1 не является готовым пользовательским приложением и не содержит planning engine end-to-end.

## Delivered

### CAD ingestion and conversion

- Docker Compose: operational PostgreSQL, Redis, ODA worker, LibreDWG worker и control CLI.
- ODA публикует DXF; LibreDWG работает как независимый диагностический reader.
- Идемпотентность submit по source path + SHA-256.
- Безопасная рекурсивная обработка DWG во вложенных архивах; верхнеуровневый backup ZIP исключён.
- Зеркальная выдача `dataset/<project>/dxf/...` и переносимое `platform/exports/dxf-only`.

Результат основного набора:

| Метрика | Значение |
|---|---:|
| `.dwg`-путей в dataset | 1009 |
| настоящих DWG | 819 |
| PaxHeader/non-DWG | 190 |
| ODA DXF обычных файлов | 819/819 |
| LibreDWG JSON обычных файлов | 792/819 |
| ODA failures | 0 |
| DXF version | AC1032 |
| объём опубликованных обычных DXF | 14.18 GiB |

Архивный контур:

| Метрика | Значение |
|---|---:|
| проектных архивов первого уровня | 39 |
| вложенных архивов | 10 |
| найденных DWG paths | 432 |
| ODA DXF | 432/432 |
| LibreDWG 0.14 JSON | 432/432 |
| опубликованный объём | 5,294,812,295 bytes |

### Domain data foundation

- Поднят отдельный PostGIS 16/3.5 с bind-mounted PGDATA.
- Созданы schemas `core`, `catalog`, `geo`, `biology`, `rules`, `planning`, `provenance`, `intake`, `ops`, `audit`, `api`.
- Применены migrations `001`–`005`; после 005 — 82 application tables.
- Реализованы SRID/integrity checks и immutability approved canonical models.
- Добавлены OSM object candidates и document/rule ingestion tables с Russian FTS.

### Architecture and source corpus

- Описаны anatomy analysis 20 проектов, canonical domain model, OSM offline/conflation, web brief и rulebook.
- Загружен официальный PDF 743-ПП: 199 pages, SHA-256 `f5af99982255e6de363543bb2789d395f81a86928c3bebc6ef7ba4a404db2276`.
- Извлечён текстовый слой и подготовлены 13 `needs_expert_review` candidates по п. 3.6.3/таблице 3.6.1.
- Зарегистрированы официальные карточки СП 42 и СП 82 и стратегия вечернего acquisition.

## Retrospectively accepted ADR

- [ADR-0002](../adr/0002-cad-conversion-chain.md)
- [ADR-0003](../adr/0003-separate-operational-and-domain-databases.md)
- [ADR-0004](../adr/0004-canonical-model-provenance-and-immutability.md)
- [ADR-0005](../adr/0005-osm-buildings-as-reviewed-candidates.md)
- [ADR-0006](../adr/0006-regulatory-documents-and-executable-rules.md)

## Verification evidence

- [Two-pilot conversion report](../../platform/reports/pilot-run-2026-09-22.md)
- [Full conversion report](../../platform/reports/full-run-2026-09-23.md)
- [Archive inventory and conversion](../../platform/reports/archive-dwg-inventory-2026-09-23.md)
- [PostGIS deployment and smoke tests](../../platform/reports/postgis-domain-db-2026-09-24.md)
- [OSM/rule ingestion migration check](../../platform/reports/postgis-osm-rules-2026-09-24.md)
- [CNTD access investigation](../../platform/reports/cntd-access-2026-09-24.md)

## Known gaps carried into Phase 2/3

- DXF ещё не импортирован в canonical spatial objects на двух пилотах.
- Не реализованы FastAPI, Next.js и scene transport.
- Нет локального OSM PBF/importer/tile pipeline.
- Rule candidates не прошли экспертный approval.
- Нет исполняемого constraint engine и generated planting plan.
- LibreDWG failures требуют risk-based entity/layer diff, но не блокируют ODA artifacts.

## Completion statement

Phase 1 завершена как инфраструктурная и исследовательская фаза. Её baseline нельзя называть готовым MVP сервиса озеленения; он является проверенным основанием для test-first Phase 2.
