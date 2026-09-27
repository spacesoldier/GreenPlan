# Phase 3, iteration 3 — CAD workbench and review operations

- Status: Planned
- Date: 2026-09-28
- Owners: frontend, backend, CAD ingestion, data platform

## Outcome

Инженер ориентируется в большой CAD-поставке через связанное delivery/dependency tree, массово
классифицирует семейства слоёв, разрешает XREF/fidelity issues по evidence и наблюдает выполнение
в scrollable bottom activity dock без перехода по одной длинной странице.

## ADR prerequisites

- принять ADR-0028;
- ADR-0018, ADR-0019, ADR-0020 и ADR-0027 остаются действующими;
- перед автоматическим effective mapping принять taxonomy/learning ADR-0022;
- Laya/Jev остаются advisory до принятия ADR-0023 и benchmark gate.

## Scope

- workspace shell: command bar, view rail, main view, context inspector, activity dock;
- physical delivery tree и dependency-oriented CAD tree с общей selection identity;
- document spaces, layers, XREF instances и target aliases/backlinks;
- tree-first implementation с virtualization; graph projection можно включить после tree gate;
- layer families, multi-select и batch category/axis review;
- typed issue queue для missing/ambiguous XREF и DWG/DXF fidelity mismatch;
- manual XREF mapping, retry search и revision-scoped waiver with reason;
- fidelity evidence diff и раскрываемые technical logs/artifacts;
- persisted activity event detail;
- URL-deep links на document/space/layer/XREF/issue/event.

## Out of scope

- автоматическое извлечение содержания штампа и легенды — в этой итерации создаются candidates и
  anchors, semantic decoding идёт следующим пакетом;
- окончательный force-directed graph для тысяч узлов;
- автоматическое принятие model suggestions;
- удаление source files или artifacts;
- production RBAC; actor/audit contract обязателен, но prototype использует системного reviewer;
- полная реконструкция proxy objects, которые не поддерживает converter/reader.

## Data contracts and migrations

### Graph projection

- `CadExplorerNode`: stable ID, kind, label, canonical ID, parent projection ID, counts/status;
- `CadExplorerEdge`: containment/reference/alias/backlink, source/target, status;
- `XrefPlacement`: host document, space, layer, block name, matrix, attach/overlay;
- endpoint поддерживает lazy children и ancestor path для deep link;
- graph fingerprint зависит от revision, inventory и manual mappings.

### Layers and layouts

- нормализовать layouts/viewports/per-viewport layer states;
- `LayerFamily`: normalization version, signature, suggested axes, member count;
- family members всегда доступны до batch action;
- batch review хранит immutable exact member snapshot и taxonomy/provider versions.

### Issues and evidence

- issue kinds имеют typed evidence schema и allowlisted actions;
- resolution state: `open`, `investigating`, `resolved`, `waived`, `blocked`;
- waiver хранит reason, actor, policy version и calculated impact;
- fidelity evidence содержит source/derived inventory diff и artifact references.

### Activity

- event detail связывает assistant run, task, processing attempt, job, asset и artifacts;
- stdout/stderr возвращаются отдельным bounded endpoint с pagination/truncation metadata;
- live update v1 остаётся polling; SSE рассматривается только после измерения нагрузки.

## Tests written before implementation

### T3W.1 — Graph/tree correctness

- physical paths не меняются при построении projection;
- shared XREF target получает alias nodes с одним canonical document ID;
- cycle заканчивается backlink;
- missing/ambiguous target не создаёт ложный document;
- host space/layer/transform присутствуют у XREF placement;
- lazy child pages не дают duplicate/missing nodes.

### T3W.2 — Selection and navigation

- выбор alias фокусирует canonical target и сохраняет backlink trail;
- URL восстанавливает view, selected node и opened ancestors;
- смена view не теряет project/revision context;
- keyboard navigation работает для tree и bottom dock.

### T3W.3 — Layer family and bulk review

- normalization deterministic и versioned;
- похожее имя без совпадения signature не объединяется молча;
- preview перечисляет все members до commit;
- batch accept/reject создаёт один event и обновляет ровно выбранный snapshot;
- повтор запроса с idempotency key не создаёт второй review;
- смена taxonomy не переписывает старый review.

### T3W.4 — XREF issue actions

- retry ограничен current delivery;
- manual target требует совместимого CAD asset и сохраняет reviewer evidence;
- ambiguous candidate выбирается явно;
- waive требует reason и не меняет edge status на resolved;
- добавление файла может перевести missing в resolved при повторном resolver run;
- policy корректно блокирует/разрешает publication с waiver.

### T3W.5 — Fidelity evidence

- source/derived counters сравниваются одинаковой schema/version;
- отсутствующая source inventory обозначается `comparison_unavailable`, а не mismatch=0;
- logs имеют truncation marker и cursor;
- artifact locator/size/hash соответствуют DB и диску;
- rerun создаёт новую attempt history, не затирая старую.

### T3W.6 — Activity dock

- dock имеет независимый scroll и bounded DOM rows;
- live event обновляет существующую операцию, а не плодит duplicates;
- click открывает subject, metrics, logs и artifacts;
- reload восстанавливает persisted events;
- collapse/expand не перекрывает последнюю строку main view;
- error и warning доступны по фильтру и screen reader status.

### T3W.7 — End-to-end reviewer journey

- открыть проект → найти головной DWG → пройти XREF alias → выбрать family неизвестных слоёв →
  назначить `utilities` → открыть missing XREF → найти/waive → открыть fidelity delta → посмотреть
  log/artifact → reload → получить тот же state/deep link.

## Ordered work packages

1. Обсудить и принять ADR-0028; заморозить wire-level contracts и route state.
2. Написать T3W.1; мигрировать XREF placements/layouts/viewports и реализовать lazy explorer API.
3. Написать T3W.2; собрать workspace shell, physical/CAD trees и context inspector.
4. Написать T3W.3; добавить layer family preview, multi-select и audited batch review.
5. Написать T3W.4; реализовать typed XREF issues, retry/manual mapping/waiver и policy impact.
6. Написать T3W.5; реализовать normalized fidelity diff, bounded logs и artifact evidence.
7. Написать T3W.6; перенести activity в fixed bottom dock с details panel.
8. Удалить старые дублирующие cards только после parity checklist нового workbench.
9. Написать и пройти T3W.7 на Старом Гае и Песчаном переулке.
10. Прогнать tree/family/issues по 20 проектам и выпустить iteration report.

## Acceptance matrix

| Requirement | Evidence |
|---|---|
| Ориентация без flat document picker | Старый Гай открывается от head DWG до shared XREF и target layers |
| Нет бесконечного XREF tree | cycle/backlink contract tests |
| Массовый review | family batch на ≥20 members с одним audit event |
| Осмысленные категории | domain/subtype/axes видны и фильтруются, unknown допустим |
| Missing XREF управляем | retry/manual/waive с evidence и policy impact |
| Fidelity понятна | side-by-side counters, logs и source/derived artifacts |
| Журнал не мешает inspector | scrollable bottom dock, collapse и clickable details |
| Состояние воспроизводимо | reload/deep-link E2E |
| Нет регрессии intake | upload, assistant, conversion и publication gates продолжают работать |

## Risks and fallback

- Если graph projection слишком тяжёл, default tree загружается lazy, graph view выключается feature
  flag без потери review функций.
- Если family clustering даёт false merges, автоматическое объединение ограничивается exact
  normalized name + signature; fuzzy groups показываются только как suggestions.
- Если source DWG inventory недостаточна, fidelity panel честно показывает unavailable и ODA/log
  evidence, не утверждая равенство.
- Если bottom dock мешает малому экрану, он превращается в modal sheet, сохраняя тот же event model.

## Exit gate

Итерация переходит в Verification после passing T3W.1–T3W.7. Complete требует screenshots и
API/SQL evidence для двух пилотов, regression test intake pipeline и отчёт по масштабу всех 20
проектов: documents, XREF edges/cycles/missing, layouts/viewports, layer families, bulk decisions,
waivers и unresolved fidelity issues.
