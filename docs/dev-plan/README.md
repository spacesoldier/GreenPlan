# Планы фаз разработки

Этот каталог хранит исполнимые планы и отчёты фаз. Архитектурные причины находятся в [ADR](../adr/README.md), предметные спецификации — в остальных документах `docs/`.

## Lifecycle фазы

```text
draft ADR -> accepted ADR -> planned phase -> tests written/failing
  -> implementation -> tests passing -> verified report -> complete
```

Статусы phase document:

- `Planned` — scope и acceptance определены, реализация не начата;
- `In progress` — тесты/реализация начаты;
- `Verification` — функции готовы, выполняются acceptance/regression checks;
- `Complete` — отчёт содержит доказательства прохождения gate;
- `Blocked` — указан внешний blocker и сохранён работоспособный предыдущий baseline.

## Реестр

| Фаза | Статус | Результат |
|---|---|---|
| [Phase 1](phase-01-foundation-report.md) | Complete | CAD-конвертация, PostGIS foundation, OSM/rule ingestion design и проверенные исходные артефакты |
| [Phase 2](phase-02-readonly-vertical-slice.md) | In progress | FastAPI + Next.js, полный поддерживаемый DXF-импорт, Canvas viewport, coherent spatial/raster caches, persisted primary focus и derived render assemblies; [checkpoint 1](phase-02-checkpoint-01.md), [checkpoint 2](phase-02-checkpoint-02.md), [checkpoint 3](phase-02-checkpoint-03.md), [checkpoint 4](phase-02-checkpoint-04.md), [checkpoint 5](phase-02-checkpoint-05.md), [checkpoint 6](phase-02-checkpoint-06.md), [checkpoint 7](phase-02-checkpoint-07.md), [checkpoint 8](phase-02-checkpoint-08.md), [checkpoint 9](phase-02-checkpoint-09.md), [checkpoint 10](phase-02-checkpoint-10.md), [checkpoint 11](phase-02-checkpoint-11.md), [checkpoint 12](phase-02-checkpoint-12.md), [checkpoint 13](phase-02-checkpoint-13.md) |
| [Phase 3](phase-03-controlled-project-intake.md) | In progress | Создание проекта, загрузка поставки, reader-first DWG pipeline, XREF graph и доказательный fidelity gate; [XREF/classification checkpoint](phase-03-checkpoint-xref-classification.md) |
| [Phase 3, iteration 2](phase-03-iteration-02-intake-assistant.md) | Planned | Ассистент разбора смешанной поставки, XREF assembly, versioned taxonomy и прогон 20 проектов |
| [Phase 3, iteration 3](phase-03-iteration-03-cad-workbench.md) | In progress | Workbench vertical slice: delivery/CAD trees, layer-family batch review, typed issues и нижний журнал |
| [Phase 3, iteration 4](phase-03-iteration-04-guided-cad-review.md) | In progress | Верхний мастер, selection inspector, resizable tray и локальные AI-подсказки слоёв; [checkpoint 1](phase-03-iteration-04-checkpoint-01.md) |
| [Phase 3, iteration 5](phase-03-iteration-05-local-model-orchestration.md) | Complete | Ax orchestration и последовательный CPU llama.cpp runtime для Qwen/Gemma |
| [Phase 3, iteration 6](phase-03-iteration-06-preview-publication-and-layer-viewer.md) | Planned | Preview publication при неполной семантике и фасетный навигатор слоёв в spatial viewer |
| [Phase 3, iteration 7](phase-03-iteration-07-observable-publication.md) | Planned | Single-flight Celery publication job, persisted progress, activity events и server-driven disabled button |
| [Phase 3, iteration 8](phase-03-iteration-08-root-scoped-viewer.md) | In progress | Один активный publication root, XREF/layer tree, root-aware streaming и исправление категорий из viewer |
| [Phase 4](phase-04-review-and-planning.md) | Planned | OSM review, нормативный review и первый детерминированный constraint/planting workflow |
| [Phase 4, iteration 1](phase-04-iteration-01-sp42-rulebook-taxonomy.md) | In progress | СП 42 rulebook и нормативно согласованная CAD taxonomy v2 |
| [Phase 4, iteration 2](phase-04-iteration-02-knowledge-library-bootstrap.md) | Planned | Qwen runtime, идемпотентный разбор СП и библиотека нормативов, принципов генерации и CAD-символов растений |
| [Phase 4, iteration 4](phase-04-iteration-04-semantic-revisions-and-planting-zones.md) | Planned | Semantic diff revisions, инструменты навигации и обозначения газона, вычисление planting feasibility zones |
| [Phase 4, iteration 5](phase-04-iteration-05-surface-region-inspector.md) | In progress | Инспектор контура, spatial inventory, сохранение candidate и prototype clearance |

## Обязательная структура будущей фазы

1. Status, dates, owners.
2. Outcome — один проверяемый пользовательский результат.
3. Accepted ADR prerequisites.
4. Scope / out of scope.
5. Data/API contracts.
6. Tests to write before implementation.
7. Ordered work packages.
8. Acceptance matrix requirement → test/evidence.
9. Risks and rollback/fallback.
10. Completion report, добавляемый после фактической проверки.

Нельзя переводить фазу в `Complete` по наличию файлов или UI-макета. Требуются работающий запуск, passing tests и сохранённые доказательства.
