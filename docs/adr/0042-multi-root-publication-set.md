# ADR-0042 — Multi-root publication set вместо единственного master-файла

- Status: Accepted
- Date: 2026-09-29
- Owners: CAD ingestion, backend, frontend, geospatial
- Related phase: Phase 3, iteration 6
- Supersedes: предположение об одном `selected_master_asset_id` в ADR-0017 и текущем prototype API
- Superseded by: —

## Context

Реальная поставка не всегда имеет один DWG, который исчерпывающе представляет проект. На верхнем
уровне могут независимо находиться генеральный план, посадочный чертёж, исходная геоподоснова и
исторические редакции. Каждый такой файл может иметь собственное рекурсивное XREF-поддерево, а одни и
те же зависимости могут использоваться несколькими головными файлами.

Текущий экран публикации показывает плоский список всех `master_candidates` с radio button. В него
попадают и настоящие головы, и файлы, уже подключённые как XREF, и копии из архивов. Один
`selected_master_asset_id` заставляет пользователя выбрать только один файл и не использует уже
построенный CAD dependency graph.

Нужна публикационная единица, совпадающая со структурой проекта: пользователь выбирает несколько
верхнеуровневых файлов, а система включает их разрешённые зависимости автоматически.

## Decision

### 1. Публиковать набор корней

Единицей выбора становится `publication root set`, а не один master. Для каждой revision хранится
упорядоченный набор:

```text
revision_id
source_asset_id
root_role = effective_design | reference_context | historical
workspace_kind = project_solution | source_data | archive
selected_by
selected_at
```

Как минимум один корень должен иметь роль `effective_design` или явно разрешённую эквивалентную роль
для preview. Старое поле `selected_master_asset_id` остаётся только как временная совместимость и не
является источником истины после миграции.

### 2. В UI выбираются только настоящие корни CAD-графа

Selectable candidate — CAD-документ, который:

- относится к поддерживаемой ветке поставки;
- имеет разобранное или конвертированное представление;
- не является достижимым дочерним узлом другого документа через разрешённый XREF в том же graph
  snapshot;
- не является мусорным/исключённым asset;
- не скрыт внутри выбранного корня как dependency.

Корни группируются по смысловой ветке каталога:

1. **Проектное решение**;
2. **Исходные данные**;
3. **Архив**.

В первой версии файлы из неопределённой ветки не предлагаются к публикации, пока не назначен
`workspace_kind`. Название группы не является выбранным root: внутри неё может быть несколько
независимых верхнеуровневых DWG/DXF.

Если файл становится дочерним после разрешения XREF, он исчезает из selectable root list, но остаётся
видимым в раскрываемом dependency preview выбранного родителя.

### 3. Выбор корня включает транзитивное XREF-поддерево

Для каждого выбранного root сервер вычисляет immutable closure с учётом:

- resolved XREF edges;
- attach/overlay semantics;
- INSERT transform;
- порядка и циклов;
- выбранной revision и resolution snapshot.

Пользователь не отмечает каждый XREF вручную. UI показывает количество включённых файлов, missing и
ambiguous edges и позволяет раскрыть состав перед публикацией.

### 4. Роли корней влияют на последующее использование

- `effective_design` — рабочее проектное решение, кандидат для planning и нормативной проверки;
- `reference_context` — исходная подоснова и контекст; видима, но не считается проектным результатом;
- `historical` — архивная редакция; по умолчанию выключена в viewer и не участвует в effective
  constraint/planning run.

Рекомендуемые роли выводятся из workspace kind, но пользователь подтверждает их. Выбор архивного
корня не должен молча смешивать старую и актуальную геометрию как один effective result.

### 5. Readiness и findings считаются по выбранному closure

Publication gate проверяет union всех dependency closures выбранных корней. Critical finding файла,
который не входит ни в один выбранный closure, остаётся в проекте, но не блокирует эту публикацию.

Для каждого root UI показывает собственные:

- geometry/dependency/fidelity readiness;
- unresolved XREF count;
- semantic coverage;
- число объектов и предполагаемый extent;
- причину блокировки.

Смена root selection пересчитывает aggregate readiness и новый publication fingerprint.

### 6. Собирать корни раздельно, публиковать единым manifest

Каждый root сначала получает собственный assembled artifact и assembly manifest по ADR-0019. Затем
canonical model публикует scene-root manifest, связывающий эти сборки в одну сцену. Это сохраняет
границу provenance и не требует безымянно склеивать несколько DXF до импорта.

```text
canonical model
  -> scene root A -> assembly A -> XREF closure A
  -> scene root B -> assembly B -> XREF closure B
  -> scene root C -> assembly C -> XREF closure C
```

Canonical object хранит `scene_root_id` и source occurrence. Viewer может включать корни независимо.

### 7. Дедупликация не уничтожает трансформации

Общий source asset может быть достижим из нескольких корней. Исходные bytes и parsed source geometry
дедуплицируются по content/source identity. Render/canonical occurrence различается по:

```text
source entity identity + transform fingerprint + coordinate space
```

Если одна и та же occurrence встречается через несколько корней с одинаковым transform fingerprint,
геометрия хранится один раз, а provenance содержит несколько root paths. Разные INSERT transforms
остаются разными occurrences.

### 8. API использует root selection objects

Review/publication request принимает не массив произвольных файлов, а список:

```json
{
  "roots": [
    {"source_asset_id": "...", "role": "effective_design"},
    {"source_asset_id": "...", "role": "reference_context"}
  ]
}
```

Сервер проверяет, что каждый asset является root в текущем dependency snapshot. Переданный дочерний
XREF отклоняется с кодом `publication_root_is_dependency` и ссылкой на родительский root.

## Implementation status

Реализован первый сквозной срез `multi_root_v1`:

- `intake.publication_roots` хранит выбранные корни, роли, порядок и fingerprint XREF closure;
- detail API вычисляет только настоящие корни графа и группирует их по веткам поставки;
- review API принимает `roots[]`, проверяет роли, unresolved XREF и critical findings в union выбранных closures;
- UI использует checkbox multi-select, role selector и раскрываемый dependency preview;
- publish transaction собирает каждый root отдельно и сохраняет единый root manifest в canonical model;
- canonical objects и scene layers имеют root-scoped identity и provenance properties.

Остаётся отдельная оптимизация occurrence-aware дедупликации общей зависимости между несколькими root assemblies. Сейчас одинаковая shared dependency сохраняется в контексте каждого корня: это не теряет геометрию и provenance, но может дублировать render occurrence. Остальные пункты Phase 3 iteration 6 про readiness snapshot и viewer navigator выполняются следующими work packages.

## Alternatives considered

### Оставить один master и подключать всё через него

Отклонено: несколько независимых головных чертежей могут не ссылаться друг на друга, хотя вместе
образуют полезную сцену.

### Показать checkbox у каждого DWG

Отклонено: пользователь повторно вручную собирал бы уже известный XREF-граф и мог бы включить
зависимость без родительской трансформации.

### Автоматически включить все top-level roots

Отклонено: архивы и исходные материалы могут дублировать проектное решение или представлять другую
редакцию. Система рекомендует, но не угадывает состав публикации.

### Склеить выбранные DXF до сохранения provenance

Отклонено: теряются границы root, роли, причины дублирования и возможность независимо управлять
видимостью.

## Consequences

### Positive

- UI показывает только содержательные головы графа;
- пользователь публикует несколько независимых частей проекта;
- XREF включаются автоматически и воспроизводимо;
- архив не смешивается с актуальным решением без явной роли;
- findings и readiness относятся к реально публикуемому набору;
- viewer получает естественный верхний уровень навигации.

### Negative / trade-offs

- текущий `selected_master_asset_id` и radio UI требуют миграции;
- publish transaction становится набором root assemblies;
- нужна occurrence-aware дедупликация;
- смена XREF resolution инвалидирует root closure и readiness fingerprint.

## Verification

- дочерний XREF отсутствует среди selectable roots;
- три независимых головы можно выбрать одновременно;
- выбор root автоматически включает nested attach и корректно ограничивает overlay;
- shared dependency не дублирует одинаковую occurrence, но разные transforms сохраняются;
- critical finding невыбранного root не блокирует публикацию;
- critical finding внутри выбранного closure блокирует соответствующий root;
- archive root получает historical role и выключен по умолчанию;
- сервер отклоняет попытку передать dependency как root;
- reload восстанавливает root set, роли и порядок;
- publication fingerprint меняется при selection, role или XREF resolution change.

## References

- [ADR-0017](0017-project-intake-workspace-and-state-machine.md)
- [ADR-0019](0019-resolved-xref-assembly.md)
- [ADR-0040](0040-independent-geometry-and-semantic-publication-readiness.md)
- [ADR-0041](0041-faceted-layer-navigator-for-spatial-viewer.md)
- [Phase 3, iteration 6](../dev-plan/phase-03-iteration-06-preview-publication-and-layer-viewer.md)
