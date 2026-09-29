# Phase 3, iteration 7 — Наблюдаемая фоновая публикация

- Status: Planned
- Date: 2026-09-29
- Owners: backend, frontend, geospatial, operations

## Outcome

Нажатие «Опубликовать» быстро создаёт одну фоновую задачу, блокирует повторный запуск на сервере и показывает в activity dock устойчивый после reload прогресс по корням, импорту и финализации до появления canonical model либо понятной typed error.

## Accepted ADR prerequisites

- [ADR-0019](../adr/0019-resolved-xref-assembly.md);
- [ADR-0028](../adr/0028-cad-workbench-graph-navigation-bulk-review-and-activity-dock.md);
- [ADR-0042](../adr/0042-multi-root-publication-set.md);
- после принятия: [ADR-0043](../adr/0043-asynchronous-observable-publication-job.md).

## Scope

- таблицы publication job, immutable input snapshot и events;
- partial unique index для single-flight revision;
- отдельная Celery queue/worker `publication` с concurrency 1;
- идемпотентные assembly/import/finalize steps;
- fingerprint и повторное использование root assemblies;
- heartbeat, stale detection, typed failure и explicit retry;
- API create/current/detail/retry;
- project detail projection активного job;
- disabled publish button из server state;
- общий progress bar и события в activity dock;
- короткая финальная транзакция переключения canonical model;
- cleanup policy для временных/failed artifacts.

## Out of scope

- параллельная публикация нескольких revision одного проекта;
- автоматическая отмена долгого job;
- распределённый импорт одного DXF несколькими worker;
- скрытое изменение выбранного publication root set;
- удаление диагностических artifacts сразу после failure.

## Data and API contracts

`PublicationJob` содержит state, phase, selection fingerprint, root/entity counters, monotonic progress, current root, timestamps, heartbeat, model id, error и metrics. `POST` возвращает `202`, а повторный запрос с тем же активным fingerprint возвращает тот же job.

Activity event содержит stable id, job id, phase, root asset/path, message, counters, artifact locator, state и timestamp. UI объединяет их с существующим журналом без временных synthetic events.

## Tests to write before implementation

### T3.7.1 — Single-flight

- два одновременных POST создают одну строку и одну Celery task;
- reload и второй клиент получают тот же active job;
- другой fingerprint не стартует до завершения активного job;
- completed fingerprint не публикуется повторно без explicit retry/new revision.

### T3.7.2 — Progress contract

- progress монотонен и ограничен 0..1;
- root counters обновляются после атомарного rename assembly;
- entity denominator фиксируется до import progress;
- current root и phase согласованы с последним persisted event;
- heartbeat обновляется во время CPU-bound этапов.

### T3.7.3 — Failure and retry

- XREF error возвращает typed failure с root path;
- DB/model pointer не меняется при failure;
- retry использует только artifacts с совпадающим fingerprint;
- stale job помечается, но конкурентный worker не запускается автоматически;
- ручной retry создаёт новый attempt с parent job id.

### T3.7.4 — UI workflow

- кнопка disabled сразу после `202` и после reload;
- повторный click не отправляет новый запуск;
- dock показывает phase, percent и root N/M;
- persisted events открываются с подробностями и artifact locator;
- completed job переводит проект в published без ручного refresh;
- failed job показывает действие retry и не маскируется HTTP 500.

### T3.7.5 — Atomic publication

- частичные spatial objects недоступны как current model;
- финальная транзакция одновременно фиксирует model, revision, workflow и audit;
- падение финализации откатывает pointer/state;
- scene manifest содержит все root assembly manifests и waived/manual XREF evidence.

## Ordered work packages

1. Принять ADR-0043 и написать T3.7.1.
2. Добавить migration publication_jobs/events и single-flight repository.
3. Вынести синхронный publish в job orchestration и отдельную Celery queue.
4. Разделить assembly/import/finalize, добавить callbacks, heartbeat и fingerprinted artifacts.
5. Написать T3.7.2–T3.7.3 и fault-injection fixtures.
6. Добавить API create/current/detail/retry и compatibility redirect старого endpoint.
7. Подключить job projection к project detail.
8. Реализовать server-driven disabled button, polling и progress bar activity dock.
9. Написать T3.7.4 и пройти reload/double-click/failure browser scenarios.
10. Сократить финальную транзакцию и пройти T3.7.5.
11. Прогнать «Старый Гай» с десятью корнями, записать timings, bytes, entities и SQL evidence.
12. Настроить retention/cleanup и обновить runbook.

## Acceptance matrix

| Требование | Доказательство |
|---|---|
| Нельзя запустить дубль | concurrent API test + partial unique index |
| Кнопка корректна после reload | browser test + current-job API |
| Видно фактический прогресс | persisted counters/events + dock screenshot |
| Ошибка объясняет root и фазу | fault-injection XREF/import tests |
| Retry не пересобирает валидное | artifact reuse metrics |
| Частичная модель не публикуется | transaction rollback integration test |
| Большой проект завершается без HTTP timeout | «Старый Гай» job report |

## Risks and fallback

- CPU-bound ezdxf может редко обновлять heartbeat: callback должен вызываться между документами и порциями entity scan.
- Celery redelivery требует идемпотентности step keys и DB claims.
- Длинный bulk import надо дробить без открытия частичной модели читателям.
- До переключения UI старый endpoint остаётся совместимым, но создаёт тот же job вместо синхронного выполнения.
