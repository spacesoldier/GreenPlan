# ADR-0029 — Мастер подготовки, selection-driven inspector и изменяемая нижняя панель

- Status: Accepted
- Date: 2026-09-28
- Owners: frontend, product design, CAD domain
- Related phase: Phase 3, iteration 4
- Supersedes: presentation layout of ADR-0028
- Superseded by: —

## Context

Рабочая область уже разделена на материалы, CAD Explorer, проблемы и публикацию, но боковая
навигация воспринимается как набор независимых экранов. Реальный процесс имеет конечную цель:
собрать поставку, разобрать CAD, устранить ограничения и опубликовать проверенную модель.

CAD-инженеры ожидают дерево документов слева и свойства выбранного объекта справа от дерева.
Постоянный inspector, не связанный с selection, заставляет повторно выбирать документ в select.
Проблемы и журнал нужны во всех шагах и должны раскрываться для подробного чтения.

## Decision

1. Этапы `Материалы → CAD-разбор → Проверка → Публикация` показываются сверху как мастер с
   видимой конечной целью и состоянием каждого этапа. Переход не обязан быть линейно заблокирован:
   инженер может вернуться к исходным материалам, не теряя selection.
2. В CAD-разборе dependency tree находится слева. Узлы имеют стабильный selection kind:
   `document`, `space`, `layer`, `xref`.
3. Центральная область является inspector выбранного узла:
   - document: метаданные и его Model/Paper spaces;
   - space: вкладка активного листа и список относящихся к документу слоёв;
   - layer: семантические признаки, provider evidence и review action;
   - XREF: source/target/status/path и переход к canonical target.
4. Model и Paper spaces отображаются вкладками. Выбор вкладки сохраняется отдельно для документа.
   Пока DXF-инвентаризация не содержит per-space membership слоя, UI честно показывает слои
   документа и маркирует это ограничение, а не выдумывает принадлежность.
5. `Проблемы` и `Журнал` становятся вкладками единого bottom tray. Панель имеет collapsed state и
   изменяемую мышью высоту через верхнюю drag-handle с min/max bounds. Высота хранится в
   `localStorage`; основной контент резервирует столько же места и не перекрывается.

## Consequences

- направление процесса и publish goal постоянно видимы;
- дерево и inspector следуют привычной CAD-компоновке;
- один selection contract позволит позже добавить URL deep links;
- потребуется нормализовать связь layer-space/viewport, чтобы фильтр листа стал точным;
- resize должен работать с pointer capture и клавиатурной альтернативой.

## Verification

- этапы мастера доступны сверху и переключают рабочую область;
- выбор document/space/layer/XREF меняет inspector без отдельного document select;
- вкладка листа меняет active space и переживает обновление данных;
- drag верхней кромки меняет высоту tray в допустимых пределах;
- вкладки «Проблемы» и «Журнал» сохраняют независимый selection;
- tray не перекрывает последнюю строку inspector.

## References

- [ADR-0028](0028-cad-workbench-graph-navigation-bulk-review-and-activity-dock.md)
- [Phase 3, iteration 4](../dev-plan/phase-03-iteration-04-guided-cad-review.md)
