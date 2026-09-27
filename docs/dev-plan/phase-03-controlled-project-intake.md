# Phase 3 — Управляемая загрузка проекта и доказательный CAD-импорт

- Status: In progress
- Target: создать проект из UI, загрузить поставку и получить наблюдаемый verdict сохранности до публикации сцены
- Owners: frontend, backend, CAD ingestion, geospatial
- Decisions: [ADR-0017](../adr/0017-project-intake-workspace-and-state-machine.md), [ADR-0018](../adr/0018-evidence-gated-cad-reading-and-conversion.md), [ADR-0019](../adr/0019-resolved-xref-assembly.md), [ADR-0020](../adr/0020-human-reviewed-cad-classification.md)

## Почему эта фаза стала следующей

Phase 2 доказала работу viewer на двух заранее импортированных проектах, но обошла пользовательскую приёмку. В результате текущая сцена Песчаного переулка была построена из одного конвертированного файла без обязательного доказательства полноты XREF, layouts, дорожек и заливок.

До OSM, нормативных ограничений и автоматической расстановки растений система обязана доказуемо ответить:

1. что именно загрузил пользователь;
2. какие файлы являются master-кандидатами и зависимостями;
3. смогли ли мы прочитать исходный DWG напрямую;
4. зачем понадобилась конвертация и каким инструментом она сделана;
5. что изменилось или исчезло после каждой стадии;
6. можно ли использовать полученную сцену для расчётов.

Ранее запланированный контур OSM/rulebook/planning переносится в Phase 4.

## Outcome

Пользователь открывает начальный экран, создаёт проект, загружает папку Песчаного переулка или новую поставку и наблюдает весь pipeline. Система сохраняет исходники, определяет реальные форматы, выбирает direct-read либо conversion path, строит XREF graph и показывает fidelity report.

Начальный экран принят как портфель проектов: адаптивный grid карточек, где первый тайл в левом верхнем углу — заметная кнопка с крупным `+`. Она открывает создание проекта; следующие тайлы показывают уже опубликованные и находящиеся на приёмке проекты, их состояние, объём поставки и количество CAD-файлов.

В существующий 2D workspace можно перейти только после явной публикации прошедшей проверку ревизии либо в маркированном preview-режиме. Пользователь может указать, что результат неполон, и увидеть конкретные блокирующие причины.

## ADR prerequisites

До начала реализации:

- ADR-0017 и ADR-0018 обсуждены и переведены из `Proposed` в `Accepted`;
- ADR-0002 остаётся действующим для роли ODA/LibreDWG;
- ADR-0007 сохраняет границу Next.js BFF → FastAPI;
- ADR-0008 определяет порядок tests-before-implementation.

## Scope

### Ретроспективная ревизия существующей конвертации

- восстановить source/output SHA-256, ODA/LibreDWG versions, команды и логи пилотного прогона;
- сравнить `ГР_Песчаный переулок.dwg` с полученным DXF;
- отдельно исследовать DWG генерального плана и каталог `Xrefs`;
- локализовать судьбу выбранных дорожек, заливки снеговой зоны и зелёных заливок;
- разделить потери converter, unresolved XREF, parser, importer и renderer;
- выпустить отчёт, не приписывающий потерю этапу без evidence.

### Web application

- начальный экран списка проектов;
- создание проекта и draft revision;
- загрузка отдельных файлов, папки и поддерживаемого архива;
- дерево поставки и инвентаризация;
- экран стадий обработки и логов;
- fidelity/XREF/layout review;
- выбор master-кандидата;
- публикация либо блокировка ревизии;
- переход в существующий workspace.

### Backend and workers

- streaming upload и immutable content-addressed storage;
- MIME/magic detection и безопасное извлечение архивов;
- capability registry readers/converters;
- direct DWG diagnostic read;
- controlled ODA conversion fallback;
- independent DXF inventory;
- pre/post diff и verdict engine;
- XREF resolver по всей delivery;
- асинхронные jobs, progress events, retry и cancellation;
- audit trail публикации.

### Data model

Переиспользовать существующие:

- `catalog.projects`, `catalog.project_revisions`;
- `intake.deliveries`, `intake.delivery_entries`;
- `intake.conversion_jobs`, `conversion_stages`, `conversion_artifacts`, `publications`;
- `intake.cad_documents`, `cad_xrefs`, `cad_layers`, `cad_entities`;
- `provenance.source_assets`, `source_fragments`, `transforms`;
- `ops.processing_runs`, `run_components`;
- `audit.events`.

Добавить миграцией только недостающие понятия:

- upload session/chunks и квоты;
- tool capability snapshot;
- CAD spaces/layouts/viewports;
- normalized inventory snapshot;
- inventory comparison и individual findings;
- fidelity verdict и review decision;
- master candidate/assembly selection;
- связь preview с точной стадией и source fingerprint.

## Out of scope

- полный универсальный DWG renderer в браузере;
- автоматическое понимание всех штампов и легенд;
- гарантированный импорт proprietary proxy objects; поддерживаемые XREF теперь собираются по ADR-0019;
- гарантированное чтение proprietary vertical-product объектов;
- редактирование исходных DWG;
- OSM, нормативный rule review и генерация посадок — перенесены в Phase 4;
- production object storage и resumable multipart cloud upload, если локальный streaming upload покрывает пилоты.

## User flow and routes

| Route | Экран | Главный результат |
|---|---|---|
| `/` | Projects home | grid проектов; первый тайл создаёт новый проект |
| `/projects/new` | Create project | новый project + draft revision |
| `/projects/:id` | Intake cockpit | загрузка, inventory, live-стадии, findings, master review и publish |
| `/workspace?project=:id` | Existing workspace | опубликованная каноническая модель |

Навигация сохраняет project/revision/run в URL. Refresh не сбрасывает прогресс и выбор.

## Pipeline contract

```text
receive bytes
  → detect real format
  → inventory delivery
  → register CAD candidates
  → direct reader capability check
      ├── sufficient → normalized direct-read document
      └── insufficient → pre-inventory + ODA conversion → DXF inventory
  → resolve XREF graph across delivery
  → compare inventories and previews
  → fidelity verdict
  → human assembly/review decision
  → canonical import
  → publish revision
```

Каждая стрелка создаёт stage record. Нельзя подменять failed stage ручным файлом без регистрации нового artifact и provenance.

## Fidelity report contract

Отчёт содержит:

- идентификаторы source и output artifacts;
- версии readers/converters и image digests;
- detected DWG/DXF versions;
- model/layout/viewports до и после;
- слои, блоки, entity types и spatial extents;
- отдельные строки для `HATCH`, paths, text, dimensions и proxy;
- XREF graph с resolved/missing/ambiguous status;
- структурные findings с severity и evidence;
- ссылки на сопоставимые preview;
- итог `accepted / accepted_with_review / rejected / not_comparable`;
- reviewer, время, комментарий и audit event при ручном решении.

## Tests written before implementation

### T3.1 — Project and revision lifecycle

- создание проекта создаёт только draft revision;
- duplicate project code возвращает типизированную ошибку;
- новая delivery не изменяет published revision;
- недопустимый state transition отклоняется;
- publish атомарно фиксирует model, delivery и verdict fingerprints.

### T3.2 — Upload and storage safety

- большие файлы стримятся без полной буферизации;
- SHA-256 вычисляется во время записи;
- одинаковые байты дедуплицируются, пути остаются отдельными entries;
- `../`, absolute paths, symlink escape и архивная бомба отклоняются;
- interrupted upload не становится delivery entry;
- удаление временного job не удаляет raw blob.

### T3.3 — Format detection and routing

- DWG определяется по `ACxxxx`, несмотря на неверное расширение;
- файл `.dwg` без сигнатуры не попадает в converter;
- достаточный direct reader не вызывает обязательную конвертацию;
- partial reader сохраняет диагностику и запускает fallback;
- отсутствие reader и converter даёт actionable `blocked`, а не пустую сцену.

### T3.4 — Conversion provenance

- ODA получает input/output version policy без silent down-save;
- command, tool version/digest, stdout/stderr и exit code сохранены;
- retry создаёт новую stage attempt;
- output artifact проходит size/hash/version checks;
- LibreDWG warning не подменяет ODA artifact, но попадает в findings.

### T3.5 — Fidelity regression fixtures

Фикстура содержит line/path, polygon, `HATCH`, text, block/attribute, layout/viewport, XREF и snow-storage zone.

- исчезновение дорожки выявляется;
- исчезновение hatch/заливки выявляется;
- исчезновение layout выявляется;
- изменение extents/spatial cluster выявляется;
- допустимое изменение внутреннего entity decomposition не создаёт ложный critical finding;
- unexplained critical finding запрещает `accepted`.

### T3.6 — XREF graph

- exact relative path разрешается первым;
- Windows separators и case mismatch нормализуются с сохранением original path;
- неоднозначный basename остаётся `ambiguous`;
- recursive XREF transform композируется детерминированно;
- cycle не зацикливает worker;
- critical missing XREF блокирует effective publication.

### T3.7 — UI journey

- projects home → new project → folder upload → inventory;
- processing screen обновляет стадии без перезагрузки;
- пользователь открывает stdout/stderr и finding evidence;
- fidelity review сравнивает raw/converted/assembled/canonical preview;
- blocked revision не открывается как effective workspace;
- accepted preview публикуется и появляется в project switcher;
- deep link восстанавливает project/revision/run.

### T3.8 — Песчаный forensic acceptance

- в delivery зарегистрированы оба master-кандидата и XLSX;
- XREF генерального плана представлены графом, а не плоским списком;
- минимум одна дорожка прослежена source → reader → DXF → importer → renderer;
- минимум одна зелёная заливка и снеговая зона имеют такой же trace;
- для каждой пропажи указан первый stage, где evidence перестаёт существовать;
- итоговый verdict объясняет, можно ли использовать сцену для планирования.

## Ordered work packages

1. Обсудить и принять ADR-0017/0018.
2. Провести forensic-аудит старой конвертации Песчаного без изменения pipeline.
3. Зафиксировать failing fixtures T3.3–T3.6 на реальных классах потерь.
4. Добавить миграцию intake/fidelity сущностей и repository contract tests.
5. Реализовать content-addressed storage и T3.1–T3.2.
6. Реализовать project/create/upload/inventory API и первые три экрана.
7. Ввести capability registry и direct-read/conversion routing.
8. Реализовать normalized inventories, XREF graph и diff engine.
9. Реализовать processing/fidelity/assembly screens.
10. Подключить canonical import только после verdict/review.
11. Мигрировать Песчаный и Куликовскую как исторические deliveries, не меняя raw files.
12. Выполнить T3.7–T3.8 и опубликовать отчёт Phase 3.

## Implementation checkpoint — 2026-09-27

Реализован первый сквозной вертикальный срез:

- migration `009_controlled_project_intake.sql`: workflow, CAD inventories/spaces, stage attempts, findings и master candidates;
- content-addressed raw storage с SHA-256 и дедупликацией;
- API создания проекта, загрузки файлов с сохранением относительного пути, запуска анализа, review и publish;
- проверка формата по содержимому, а не расширению;
- LibreDWG diagnostic stage → ODA fallback → независимая `ezdxf` inventory;
- фиксация команд, stdout/stderr, метрик и артефакта conversion job;
- разрешение XREF по delivery с `missing/ambiguous` critical findings;
- portfolio UI с первым plus-tile, форма проекта и единый intake cockpit;
- Next.js BFF принимает streaming request body и не передаёт browser credentials во внутренний API;
- опубликованный master импортируется существующим canonical importer и открывается в `/workspace`.

Проверки checkpoint: 37 frontend tests, 5 intake unit tests, TypeScript typecheck, production Next.js build, Compose config, PostGIS migration и live HTTP health/BFF smoke.

Ещё не закрывают Exit gate фазы: безопасное извлечение ZIP, полноценный normalized pre/post diff, recursive XREF transforms/cycles, visual side-by-side preview, retry/cancel API, forensic trace Песчаного и migration исторических deliveries. Поэтому статус фазы остаётся `In progress`.

## Acceptance matrix

| Requirement | Evidence |
|---|---|
| Проект создаётся пользователем | T3.1 + browser journey |
| Файлы загружаются безопасно и неизменяемо | T3.2 + storage hashes |
| DWG сначала читается доступным reader | T3.3 + routing record |
| Конвертация полностью трассируется | T3.4 + stage/artifact records |
| Потеря дорожки или заливки видна | T3.5 + preview/diff finding |
| XREF участвует в completeness gate | T3.6 + dependency graph |
| Неполная сцена не маскируется под effective | T3.7 |
| Причина потерь Песчаного локализована | T3.8 + forensic report |

## Risks and fallback

- Если LibreDWG не даёт достаточного pre-inventory, verdict становится `not_comparable`; ODA preview можно показать, но автоматическую публикацию не разрешать.
- Если ODA runtime недоступен, проект остаётся `blocked` с инструкцией по установке/подключению converter, а исходники сохраняются.
- Если browser folder upload нестабилен, поддержать ZIP как переносимый delivery, сохраняя исходные относительные пути.
- Если visual renderer не воспроизводит DWG напрямую, использовать независимый CAD-export preview и явно маркировать его backend.
- Если универсальное распознавание штампа не готово, Phase 3 допускает ручное назначение роли layout с сохранением reviewer evidence.
- Если полный XREF assembly слишком велик, preview строится по master-кандидатам и критическим зависимостям, но missing graph остаётся видимым.

## Rollback

Новые intake routes и таблицы добавляются без изменения опубликованных Phase 2 моделей. Existing workspace продолжает читать текущие revisions. Отключение нового feature flag возвращает прежний project switcher, но не удаляет загруженные deliveries и audit trail.

## Exit gate

Phase 3 завершается только когда:

1. пользователь создаёт новый проект и загружает поставку без ручного доступа разработчика к БД;
2. direct-read/conversion choice объяснён capability evidence;
3. fidelity report и XREF graph доступны в UI;
4. critical loss блокирует effective publication;
5. для Песчаного установлено, на каком этапе исчезают выбранные дорожки и заливки;
6. принятая ревизия открывается в существующем viewer с полным provenance;
7. все T3.1–T3.8 проходят на production-like Compose стенде.
