# ADR-0043 — Асинхронная наблюдаемая публикация с single-flight

- Status: Proposed
- Date: 2026-09-29
- Owners: backend, frontend, geospatial, operations
- Related phase: Phase 3, iteration 6
- Supersedes: синхронный HTTP-вызов `POST /publish`
- Superseded by: —

## Context

Multi-root публикация собирает отдельный DXF для каждого выбранного корня, разрешает XREF, импортирует геометрию в PostGIS и пересчитывает render assemblies. Для проекта «Старый Гай» выбрано десять корней; отдельные assembled DXF имеют размер порядка 120–150 МБ. Операция занимает минуты и не должна удерживать один HTTP-запрос.

Текущий прототип имеет три дефекта:

- кнопка снова становится доступной после завершения или обрыва браузерного `fetch`, хотя сервер ещё может работать;
- повторное нажатие способно запустить конкурентную публикацию той же revision;
- пользователь видит только общий HTTP 500, но не фазу, корень, прогресс и сохранённые артефакты.

Локальный `busy` state компонента недостаточен: источником истины должен быть серверный job.

## Decision

### 1. Publication job становится отдельной сущностью

Вводится `intake.publication_jobs`:

```text
id
revision_id
selection_fingerprint
state = queued | assembling | importing | finalizing | completed | failed
phase
root_total / root_completed
entity_total / entity_completed
progress
current_root_asset_id
model_id
attempt
heartbeat_at
started_at / finished_at
error_code / error_summary
metrics jsonb
```

Снимок `publication_roots`, их ролей, closure fingerprints и source hashes фиксируется в `input_snapshot`. Job всегда воспроизводит этот снимок и не читает меняющийся UI selection в середине выполнения.

### 2. Single-flight и идемпотентный запуск

`POST /v1/intake/projects/{id}/publication-jobs` атомарно:

1. блокирует текущую workflow revision;
2. вычисляет selection fingerprint;
3. возвращает существующий active job с тем же fingerprint либо создаёт один новый;
4. ставит Celery-задачу после commit;
5. отвечает `202 Accepted` с job representation.

Частичный unique index запрещает более одного job в состояниях `queued|assembling|importing|finalizing` для одной revision. Повторный клик не создаёт дубль.

### 3. Кнопка определяется серверным состоянием

Кнопка публикации disabled, если:

- существует active publication job;
- выбранный состав не сохранён;
- текущий selection fingerprint отличается от job/revision snapshot;
- публикация уже завершена для этого fingerprint.

После reload состояние восстанавливается из API. Закрытие вкладки не отменяет job.

### 4. Прогресс имеет фазы и монотонные единицы

Сначала известны корни, поэтому assembly progress считается точно по `root_completed/root_total`. Перед импортом каждый assembled DXF инвентаризуется, после чего появляется `entity_total`. Общий progress использует фиксированные веса:

```text
validation 5%
assembly 45%
geometry import 40%
finalization 10%
```

Progress не уменьшается. Внутри текущего root дополнительно показываются bytes/entities, но они не подменяют общий denominator.

### 5. Журнал действий получает persisted events

Каждый переход пишет событие с `job_id`, phase, root path, counters, artifact locator и длительностью:

- публикация поставлена в очередь;
- начата/завершена сборка конкретного корня;
- XREF разрешён вручную либо пропущен по waiver;
- начат/завершён импорт корня;
- пересчитаны spatial focus/render assemblies;
- canonical model опубликована;
- job завершён ошибкой с безопасным diagnostic summary.

UI показывает эти события в существующем activity dock и один общий progress bar. Технический traceback остаётся в server log, пользователю возвращается typed error.

### 6. Транзакционность и повторный запуск

Тяжёлые DXF artifacts записываются вне длинной DB-транзакции в каталог job с временным именем и атомарным rename. Их manifest содержит fingerprint. Завершённые совпадающие assemblies можно повторно использовать.

Canonical model, spatial objects, revision/workflow state и audit event фиксируются одной финальной транзакцией. До неё частичная модель не становится текущей. Failed job сохраняет диагностические artifacts, но не меняет опубликованную model pointer.

Worker обновляет heartbeat. Stale job не перезапускается молча: оператор или пользователь запускает explicit retry, который создаёт новый attempt и может переиспользовать валидные assemblies.

### 7. API

```text
POST /v1/intake/projects/{project_id}/publication-jobs -> 202 PublicationJob
GET  /v1/intake/projects/{project_id}/publication-jobs/current
GET  /v1/intake/projects/{project_id}/publication-jobs/{job_id}
POST /v1/intake/projects/{project_id}/publication-jobs/{job_id}/retry
```

Старый `POST /publish` временно возвращает `202` и делегирует создание job; синхронная реализация удаляется после миграции UI.

## Alternatives considered

### Увеличить HTTP timeout

Отклонено: не решает reload, повторные клики, single-flight, наблюдаемость и восстановление.

### Держать disabled только в React state

Отклонено: состояние теряется при reload и не знает о другом клиенте либо продолжающем работу сервере.

### Публиковать каждый root отдельной моделью

Отклонено: пользователь утвердил единый publication set; отдельные root assemblies остаются внутренними атомами одного canonical manifest.

## Consequences

Положительные:

- кнопка отражает реальную серверную работу;
- повторное нажатие безопасно;
- длительная публикация переживает reload;
- прогресс и причина ошибки видны по корню и фазе;
- валидные тяжёлые assemblies можно переиспользовать.

Цена:

- новая таблица, Celery queue/worker и polling/SSE projection;
- импорт надо разбить на наблюдаемые порции;
- требуется lifecycle для временных и failed artifacts;
- необходимо мигрировать синхронный endpoint.

## Verification

- двойной POST создаёт ровно один active job;
- reload сохраняет disabled кнопку и текущий прогресс;
- journal показывает начало/конец каждого root assembly;
- waived/manual XREF отражаются в manifest и событиях;
- падение на корне N показывает root path и typed error, workflow не становится published;
- retry переиспользует assemblies с совпадающим fingerprint;
- завершение атомарно устанавливает model id и state `published`;
- stalled heartbeat помечается отдельно и не запускает конкурентный worker;
- frontend больше не держит многоминутный HTTP request.

## Implementation prerequisites

- migration `publication_jobs` и partial unique index active revision;
- Celery queue `publication` и отдельный worker с concurrency 1;
- extraction `publish_revision` в идемпотентные assembly/import/finalize steps;
- progress callback и persisted activity events;
- API job contracts и polling;
- frontend hook current job, disabled-state и progress bar;
- cleanup policy для job artifacts;
- integration test на двойной запуск, crash/retry и reload.

## References

- [ADR-0019](0019-resolved-xref-assembly.md)
- [ADR-0028](0028-cad-workbench-graph-navigation-bulk-review-and-activity-dock.md)
- [ADR-0042](0042-multi-root-publication-set.md)
- [Phase 3, iteration 6](../dev-plan/phase-03-iteration-06-preview-publication-and-layer-viewer.md)
