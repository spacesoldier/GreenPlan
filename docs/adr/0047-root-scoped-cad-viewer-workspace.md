# ADR-0047 — Root-scoped CAD viewer вместо объединённой сцены поставки

- Status: Accepted
- Date: 2026-09-29
- Owners: frontend, backend, CAD ingestion, geospatial
- Related phase: Phase 3, iteration 8
- Supersedes: отображение всех publication roots одной сценой по умолчанию
- Superseded by: —

## Context

Multi-root публикация сохраняет проектные решения, исходные данные и архивы, но их одновременная
отрисовка создаёт визуальное месиво и загружает в браузер геометрию, которую сейчас не исследуют.
Workbench уже использует понятную структуру «головной файл → XREF → слой»; viewer должен её сохранять.

## Decision

1. В один момент viewer открывает один publication root и его транзитивное XREF-замыкание. Другие
   корни остаются в модели, но не входят в текущие extent, counts, feature query и Canvas frame.
2. Без `root_id` выбирается первый `effective_design`, затем первый root по publication manifest.
   Legacy-модель без manifest продолжает работать в aggregate mode.
3. Верхний selector группирует корни как «Проектное решение», «Исходные данные», «Архив» и «Прочее».
   Выбор хранится в `?project=...&root=...`.
4. Левая панель показывает `root file → XREF source → layers`. Leaf хранит scene layer id, исходное
   имя, source path/asset, опубликованный class snapshot, review identity, count и visibility.
   Эвристически восстановленный источник явно помечается как inference.
5. Root id входит в ключ manifest, spatial tile и frame generation. Старый запрос не может заменить
   кадр после переключения. Текущий кадр остаётся под loading overlay до атомарного перехода.
6. Категория слоя меняется существующим classification review API. Решение сразу видно в дереве, но
   immutable canonical model не переписывается: UI показывает, что нужна повторная публикация.

## Alternatives considered

- Все roots и visibility checkbox: отклонено из-за тяжёлой начальной загрузки и неоднозначного вида.
- Отдельная canonical model на файл: отклонено как дублирование publication transaction.
- Мутация class опубликованных объектов: отклонено, потому что ломает воспроизводимость provenance.

## Consequences

Положительные: ограниченная нагрузка, понятная сцена, единая навигация подготовки и просмотра,
исправление семантики по видимой геометрии, воспроизводимый deep link.

Компромиссы: compare mode будет отдельной функцией; старые публикации дают частично эвристический XREF
provenance; исправление класса требует republish; persisted root-specific focus появится позднее.

## Verification

- manifest/features фильтруются по root, неизвестный root даёт typed 404;
- selector группируется и восстанавливается из URL;
- stale tile другого root не фиксируется на Canvas;
- дерево показывает root/XREF/layers и управляет visibility;
- review меняет source decision и показывает republish marker, не мутируя текущую модель;
- legacy fixture открывается без root.

## References

- [ADR-0004](0004-canonical-model-provenance-and-immutability.md)
- [ADR-0041](0041-faceted-layer-navigator-for-spatial-viewer.md)
- [ADR-0042](0042-multi-root-publication-set.md)
- [Phase 3, iteration 8](../dev-plan/phase-03-iteration-08-root-scoped-viewer.md)
