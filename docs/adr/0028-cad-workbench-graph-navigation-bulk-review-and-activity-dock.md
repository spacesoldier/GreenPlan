# ADR-0028 — CAD workbench: графовая навигация, массовый review и нижний журнал

- Status: Proposed
- Date: 2026-09-28
- Owners: frontend, CAD ingestion, domain model
- Related phase: Phase 3, iteration 3
- Supersedes: presentation parts of ADR-0025, ADR-0026 and ADR-0027
- Superseded by: —

## Context

Текущий intake screen последовательно показывает загрузку, анализ, XREF, слои, findings,
инвентаризации и публикацию. Функции стали рабочими, но одна длинная страница больше не передаёт
их отношения:

- document picker отрывает слой и layout от физического дерева поставки и XREF-графа;
- один target DWG может использоваться несколькими host documents, а XREF-граф может иметь цикл;
- подтверждать сотни слоёв отдельными галками нецелесообразно;
- `cad inventory` и generic findings не объясняют пользователю, что сравнивалось и что делать;
- activity log занимает правую колонку, но одновременно нужен context inspector выбранного узла;
- missing XREF и расхождение DWG/DXF требуют разных evidence и разных действий.

Важна корректная CAD-семантика. XREF является block reference в конкретном host space, находится
на host layer и указывает на target document. Он не является дочерним содержимым слоя. Target
document имеет собственные Model/Paper spaces и layers. Один target может иметь несколько parents,
а recursive attachment может образовать цикл; следовательно, предметная структура является графом,
даже если UI раскрывает её как дерево.

## Decision

### 1. Workspace shell вместо длинной формы

После создания проекта открывается CAD workbench из четырёх зон:

1. верхняя command bar — upload, run/re-run analysis, общий status и publish gate;
2. левая navigation rail — переключение `Материалы`, `CAD Explorer`, `Проблемы`, `Публикация`;
3. центральная рабочая область выбранного view;
4. правая context panel выбранного node/issue, а не постоянная свалка предупреждений.

Activity log переносится в закреплённый нижний dock. В collapsed состоянии видны текущая операция,
progress и число warnings. В expanded состоянии dock имеет ограниченную высоту, собственный scroll,
фильтр и список событий. Выбор события открывает persisted details: субъект, attempt/run/job ID,
вход, команда, метрики, stdout/stderr, созданные artifacts и их locators. Dock резервирует место в
layout и не перекрывает последнюю строку основной области.

### 2. Два дерева и одна identity

`Материалы` показывает физическое immutable delivery tree: folders и files ровно по загруженным
relative paths.

`CAD Explorer` показывает проекцию dependency graph:

```text
CAD document
├── Пространства
│   ├── Model
│   └── Листы
│       └── layout / viewports / stamp and legend candidates
├── Слои
│   └── layer / usage / semantic axes
└── Внешние ссылки
    └── XREF instance [host space, host layer, transform, attach|overlay]
        └── target CAD document (canonical link or missing/ambiguous target)
```

Target document существует в UI один раз по stable document identity. Повторное появление под
другим parent рисуется alias node; click переводит к canonical node. Cycle заканчивается backlink,
а не рекурсивным дублированием. Можно переключать представление `Иерархия` / `Граф`, сохраняя одну
selection/deep-link identity.

### 3. Массовая семантическая классификация

Primary review unit — не отдельная строка, а `layer family`: группа по нормализованному имени и
feature signature с видимым списком затронутых documents. Пользователь может выбрать несколько
слоёв/families и назначить category/axes одной операцией.

Минимальная domain taxonomy для первой итерации:

- vegetation;
- transport and surfaces;
- utilities с subtype water/sewer/drainage/gas/heat/power/telecom/unknown;
- buildings and structures;
- terrain;
- boundaries and protection zones;
- annotation;
- sheet service content: frame/stamp/legend/viewport;
- unknown/mixed/not-applicable.

Lifecycle и representation остаются независимыми осями. Batch accept сохраняет один review event
с exact member list и previous/next values; он не превращается в неаудируемый массовый UPDATE.
Rule/model suggestion служит фильтром и подсказкой. Low-confidence rows можно сгруппировать,
отложить или оставить unknown; подтверждать каждую строку не требуется для продолжения review.

### 4. Problems как типизированная очередь действий

Generic findings заменяются typed issues с общими полями `state`, `severity`, `evidence`,
`available_actions`, `resolution`, `actor`, `reason`, `timestamp`.

Для missing/ambiguous XREF доступны:

- повторить автоматический поиск в current delivery;
- загрузить/найти файл и привязать target вручную;
- выбрать одного из неоднозначных candidates;
- `Игнорировать для этой редакции` с обязательным обоснованием и явно рассчитанным влиянием на
  completeness/publish gate.

Разговорное «забить болт» в модели называется `waive`. Waiver не удаляет finding и не утверждает,
что ссылка разрешена; он фиксирует принятое человеком ограничение конкретной revision.

Для DWG/DXF fidelity mismatch context panel показывает side-by-side evidence:

- reader/converter/version;
- entity/layer/layout/XREF counts и delta;
- unsupported/proxy/object warnings;
- stdout/stderr с поиском;
- source and derived artifact locators, size и SHA-256;
- действия re-run, mark converter limitation, block или waive with reason.

`CAD inventory` перестаёт быть отдельной пользовательской карточкой. Его факты становятся
properties document node и evidence соответствующих events/issues.

### 5. Persisted graph and review contracts

Следующая миграция нормализует сведения, которые сейчас частично лежат в JSON:

- XREF placements: host document/space/layer, transform, attach/overlay, target edge;
- layouts, viewports и per-viewport layer states;
- layer families и members;
- batch classification review events;
- issue resolutions/waivers;
- activity event details и artifact references.

Файловая и CAD identities не смешиваются: source asset отвечает на вопрос «откуда байты», CAD
document — «что прочитано», graph edge/placement — «как подключено», review event — «кто и почему
принял решение».

## Alternatives considered

### Оставить длинную страницу с accordion sections

Просто реализуется, но не даёт устойчивой selection между деревом, issue, слоем и evidence и
вынуждает пользователя постоянно прокручивать страницу.

### Использовать только force-directed граф как в Obsidian

Хорошо показывает shared dependencies и cycles, но плохо работает с длинными русскими путями,
сотнями слоёв и последовательным review. Граф остаётся дополнительной проекцией; основная —
виртуализированное дерево плюс context panel.

### Считать XREF дочерним узлом слоя

Отклонено как неверная доменная модель: host layer относится к INSERT instance, target document
не принадлежит этому слою и может иметь несколько родителей.

### Требовать review каждой layer suggestion

Отклонено как непригодное для 20 проектов. Используются families, batch actions, abstention и
review by exception.

## Consequences

### Positive

- физическая поставка, CAD-граф и review workflow становятся различимыми, но связанными;
- shared XREF и cycles показываются без дублирования/бесконечного раскрытия;
- сотни слоёв классифицируются группами;
- каждое предупреждение получает evidence и допустимые действия;
- нижний журнал не конкурирует с context panel и остаётся доступным из любого view;
- `cad inventory` превращается из непонятного раздела во внутренний источник доказательств.

### Negative / trade-offs

- нужны миграции для viewport/XREF placement/review/waiver, а не только изменение вёрстки;
- tree virtualization и сохранение selection/deep link добавляют frontend state;
- автоматическое объединение layer families может ошибаться и требует preview members;
- waiver policy должна явно влиять на publication gate и не может быть декоративной кнопкой;
- graph view потребует отдельной оптимизации после tree-first реализации.

## Verification

- один shared target DWG имеет одну canonical identity и два alias nodes;
- XREF cycle заканчивается backlink и не зависает;
- XREF instance показывает host space/layer и transform;
- batch category operation создаёт audit event с полным member set и воспроизводится после reload;
- unknown layers можно оставить без сотен индивидуальных clicks;
- missing XREF нельзя пометить resolved через waiver;
- waiver требует reason и меняет publish gate согласно policy;
- fidelity issue открывает counts delta, logs и artifact locators;
- activity dock scrollable, keyboard accessible и открывает persisted event details;
- collapsed/expanded dock не перекрывает workspace content;
- selection document/layer/XREF/issue воспроизводится из URL.

## References

- [ADR-0019](0019-resolved-xref-assembly.md)
- [ADR-0025](0025-folder-ingest-and-visible-xref-dependency-tree.md)
- [ADR-0026](0026-intake-activity-stream-and-supported-file-boundary.md)
- [ADR-0027](0027-context-first-cad-layer-inspection.md)
- [Phase 3, iteration 3](../dev-plan/phase-03-iteration-03-cad-workbench.md)
