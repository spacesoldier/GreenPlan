# Phase 3, iteration 2 — Project Intake Assistant

- Status: In progress — vertical slice 1 implemented 2026-09-27
- Target: превратить несистематизированную проектную папку в проверяемый project graph, assembled CAD preview и очередь semantic review
- Owners: backend, CAD ingestion, ML, frontend, landscape architecture
- Decisions: [ADR-0018](../adr/0018-evidence-gated-cad-reading-and-conversion.md), [ADR-0019](../adr/0019-resolved-xref-assembly.md), [ADR-0020](../adr/0020-human-reviewed-cad-classification.md), [ADR-0021](../adr/0021-bounded-project-intake-assistant.md), [ADR-0022](../adr/0022-versioned-cad-semantic-taxonomy-and-learning-loop.md), [ADR-0023](../adr/0023-typed-decision-provider-jev-and-laya.md)

## Outcome

Пользователь загружает целую папку подрядчика и запускает ассистента. Ассистент завершает
конечный run и показывает:

1. что относится к исходным данным, проектному решению, обследованию, архиву и XREF;
2. какой файл является вероятной «головой» проекта;
3. какие XREF разрешены, неоднозначны или отсутствуют;
4. assembled preview с точным manifest;
5. слои каждого CAD-документа, разложенные по многомерной taxonomy;
6. компактную очередь вопросов, без ответа на которые публикация небезопасна.

Инженер исправляет предложения пакетно или по одному. После исправлений зависимые стадии
пересчитываются, а raw delivery остаётся неизменной.

## Baseline

Уже работают:

- создание проекта и загрузка папки;
- content-addressed storage и format detection;
- ODA/LibreDWG pipeline;
- DXF inventory, master candidates и fidelity findings;
- XREF placements и базовое разрешение по пути/basename;
- assembled DXF при публикации;
- плоские rule-first suggestions и ручное accept/reject;
- миграция PostGIS `010`.

Итерация не начинает pipeline заново, а оборачивает существующие функции в наблюдаемый
assistant run и расширяет семантический контракт.

## Implementation checkpoint — 2026-09-27

Реализован первый сквозной срез:

- migration `011`: taxonomy registry, feature snapshots, immutable classification review
  events, assistant runs и typed task DAG;
- стабильный fingerprint поставки с версиями orchestration, taxonomy и provider;
- идемпотентный `POST /v1/intake/projects/{project_id}/assistant-runs` и persisted status;
- четыре этапа `inventory -> (xref_graph, semantic_taxonomy) -> summary` с dependency gate,
  attempts, heartbeat, progress, terminal state и безопасным повторным запуском;
- taxonomy `cad-v1` с независимыми осями `domain`, `lifecycle`, `representation`,
  `object_class`, `document_role`;
- provider-neutral typed choice validation и общий Jev-compatible adapter; Laya использует
  тот же контракт, а ошибка provider сохраняет rule-only fallback;
- allowlisted feature snapshot: внешнему provider не передаются полная геометрия и
  произвольные поля;
- UI cockpit с run fingerprint, версиями, progress и состояниями задач;
- обратимое удаление тестовых проектов с первой страницы без потери поставок и evidence
  ([ADR-0024](../adr/0024-prototype-project-soft-delete.md));
- старые неподтверждённые плоские layer suggestions переводятся в `superseded`, тогда как
  принятые review events не переписываются повторным анализом.

Live smoke test на проекте «Старый Гай»: run завершён как `review_required`, четыре задачи
выполнены, критические XREF findings сохранились. Это подтверждает механизм, но не закрывает
exit gate всей фазы.

Остаются следующие work packages: candidate scoring для ambiguous XREF, preview manifest
diff, contractor profiles, batch multi-axis correction UI, optional Laya container,
frozen/gold manifests и сравнительный прогон всех 20 проектов. До их завершения статус фазы
остаётся `In progress`.

## In scope

### Assistant orchestration

- `assistant_runs`, typed tasks, dependencies, retries, heartbeat и cancellation;
- fingerprint inputs/config/tool versions;
- incremental invalidation при добавлении файла или review decision;
- terminal summary `ready`, `review_required`, `blocked`, `failed`;
- WebSocket/SSE progress вместо polling-only UI;
- безопасный resume после рестарта контейнера.

### Delivery understanding

- file-role classifier v2 с directory context;
- document families и probable revisions без физического перемещения;
- связь archive/member и исключение служебных PaxHeader/`__MACOSX`;
- обнаружение перечётных ведомостей и PDF-листов;
- master ranking по структуре CAD, а не только имени файла.

### XREF graph and assembly

- resolver candidates с объяснимым score;
- поиск в раскрытых вложенных архивах;
- cycle, overlay, units и multiple-placement validation;
- ручное разрешение ambiguous edge;
- assembly preview до publication;
- manifest diff между повторными runs;
- отчёт по неподдержанным proxy/ACAD_TABLE/OBJECTS.

### Semantic layer assistant

- taxonomy registry и migration существующих suggestions;
- multi-axis result: domain/lifecycle/representation/object class/document role;
- feature snapshots: CAD statistics, styles, blocks, sample text и context;
- deterministic rules v2;
- Laya multilingual provider behind Jev-compatible HTTP contract;
- hosted Jev adapter как opt-in challenger на том же normalized state;
- provider timeout/circuit breaker и rule-only fallback;
- contractor/project profile;
- batch review, correction scope и immutable review events.

### Evaluation on 20 projects

- frozen inventory manifest всех проектов;
- reviewed gold subset файлов, XREF edges и слоёв;
- раздельные train/dev/test по project/contractor;
- per-category metrics, calibration и dangerous-error report;
- regression comparison каждой новой rules/model/taxonomy version.

## Out of scope

- автоматическое удаление или переименование файлов пользователя;
- автоматическое утверждение ambiguous XREF;
- распознавание всей геометрии proprietary vertical products;
- утверждение semantic mapping без review;
- свободный агент с shell/SQL/write tools;
- нормативный reasoning и генерация посадок — остаются в Phase 4;
- photorealistic 3D rendering.

## Proposed data additions

| Entity | Purpose |
|---|---|
| `intake.assistant_runs` | fingerprint, taxonomy/model/tool versions и итог run |
| `intake.assistant_tasks` | typed DAG nodes, state, attempts, progress и dependencies |
| `intake.document_relations` | contains/derived_from/revision_of/supports |
| `intake.xref_candidates` | возможные targets, score и cues до выбора edge |
| `intake.assembly_artifacts` | assembled DXF, manifest, completeness и diagnostics |
| `intake.classification_taxonomies` | immutable taxonomy versions |
| `intake.classification_labels` | оси, labels и migration mapping |
| `intake.feature_snapshots` | воспроизводимый вход rule/model classifier |
| `intake.classification_reviews` | неизменяемые исправления и область применимости |
| `intake.contractor_profiles` | локальные сокращения и priors без загрязнения global rules |
| `intake.evaluation_sets/runs` | frozen gold data и метрики версии движка |

Имена финализируются отдельной migration review. Не следует дублировать уже существующие
`cad_documents`, `cad_xrefs`, `cad_layers`, `classification_suggestions` и stage attempts.

## Tests written before implementation

### T3A.1 — Assistant run contract

- один fingerprint создаёт один logical run;
- task не стартует до завершения обязательных dependencies;
- retry не создаёт второй effective output;
- restart продолжает run с последнего committed stage;
- cancel останавливает новые задачи, не удаляя полученные evidence.

### T3A.2 — Delivery safety

- raw asset нельзя изменить через assistant API;
- nested archive limits, traversal и symlink fixtures блокируются;
- top-level transport ZIP остаётся исключённым;
- роли `archive/service_noise` не удаляют и не скрывают файл от review.

### T3A.3 — XREF resolution

- relative path имеет приоритет над basename;
- unique basename разрешается с evidence;
- одинаковые basename дают ambiguous, а не случайный bind;
- archive member может стать target с сохранённым parent provenance;
- cycle и incompatible units блокируют assembly;
- attach/overlay и несколько placements соблюдаются.

### T3A.4 — Incremental assembly

- добавление missing XREF закрывает finding без повторной конвертации независимых файлов;
- изменение review edge инвалидирует только downstream assembly/import;
- manifest diff перечисляет добавленные/удалённые assets и transforms;
- assembled preview fingerprint воспроизводим.

### T3A.5 — Multi-axis taxonomy

- domain, lifecycle и representation независимы;
- utility annotation не становится pipeline geometry;
- proposed vegetation отличается от existing vegetation;
- mixed layer остаётся review_required;
- unknown/not_applicable не подменяются нулём или самым частым классом.

### T3A.6 — Model-provider containment

- provider получает только разрешённый feature snapshot;
- timeout/HTTP error включает rule-only fallback;
- неизвестный model label отклоняется schema validation;
- model suggestion не меняет effective mapping без review;
- model/taxonomy/prompt versions входят в fingerprint.

### T3A.7 — Review learning loop

- correction создаёт event и не переписывает прошлый event;
- project-only correction не влияет на другой проект;
- contractor mapping применяется только после отдельного подтверждения scope;
- training snapshot включает только опубликованные review events;
- новая model version не становится default без regression gate.

### T3A.8 — UI workflow

- live run timeline переживает reload;
- file tree фильтруется по роли и uncertainty;
- XREF graph показывает candidates, transforms и blockers;
- layer table поддерживает batch accept и выбор осей;
- из suggestion открываются исходный файл, слой, sample и reasoning;
- пользователь видит, что пересчитается после изменения.

## Ordered work packages

1. Обсудить и принять ADR-0021/0022/0023; зафиксировать taxonomy v1 и provider contract.
2. Сформировать frozen manifests и gold subset из 20 проектов.
3. Написать T3A.1–T3A.2; добавить assistant run/task schema и orchestration.
4. Написать T3A.3–T3A.4; реализовать candidate resolver, graph review и preview assembly.
5. Написать T3A.5; мигрировать flat suggestions в multi-axis representation.
6. Реализовать feature extraction v1 и deterministic rule baseline.
7. Написать T3A.6; поднять opt-in Laya container, Laya adapter и hosted Jev adapter.
8. Разметить gold subset; измерить rule-only, Laya и Jev, настроить per-axis abstention thresholds.
9. Написать T3A.7; реализовать review events, scopes и training snapshots.
10. Написать T3A.8; собрать assistant cockpit в Next.js.
11. Прогнать все 20 проектов, классифицировать неожиданные failure modes и выпустить report.
12. Только после exit gate сделать assistant default entry point для новых проектов.

## Initial acceptance targets

Цели подтверждаются или корректируются после разметки baseline, но не задним числом после
финального прогона.

| Requirement | Target/evidence |
|---|---|
| Ни один проект не зависает без terminal result | 20/20 terminal assistant runs |
| Ошибочный автоматический XREF bind | 0 на reviewed set |
| Найденные разрешимые XREF | не менее 95% recall на reviewed set |
| Роли файлов | macro-F1 не менее 0.85 на held-out projects |
| Семантика слоёв | macro-F1 не менее 0.75 на answered subset + опубликованный coverage |
| Опасные semantic errors | 0 high-confidence effective mappings без review |
| Экономия ручной работы | не менее 50% решений принимаются batch/rule confirmation |
| Воспроизводимость | одинаковые manifest/fingerprint при повторном запуске |
| Auditability | 100% effective mappings и edges имеют evidence/reviewer |

## Risks and fallback

- Если Laya плохо понимает русские сокращения, default остаётся rule-only; corrections идут в
  размеченный corpus до fine-tuning.
- Если contractor неизвестен, его profile не угадывается, применяется global taxonomy с
  большим abstention.
- Если assembly не переносит proxy objects, ассистент показывает diagnostic preview и
  блокирует заявление о полной сохранности.
- Если 20 проектов слишком велики для одного run, планировщик шардирует по document, сохраняя
  project-level dependency graph.
- Если taxonomy спорна, слой остаётся multi-label/unknown; импорт не должен насильно выбирать
  физический объект.

## Exit gate

Итерация завершена, когда все 20 проектов получили воспроизводимые terminal runs, reviewed
XREF graph и versioned layer suggestions; хотя бы два проекта с XREF опубликованы из assembled
preview; acceptance report содержит baseline, итоговые метрики, dangerous errors, время review
и список оставшихся неподдержанных сущностей.
