# Phase 3, iteration 4 — Guided CAD review and local semantic assist

- Status: In progress
- Date: 2026-09-28
- Owners: frontend, backend, ML, data platform
- Decisions: ADR-0029, ADR-0030

## Outcome

Инженер проходит понятный мастер подготовки, выбирает документ/лист/слой из левого CAD-дерева,
получает контекстный inspector и по запросу запускает локальные нейросетевые подсказки, не
превращая их в неподтверждённые изменения модели.

## Scope

- верхний stepper с конечной целью публикации;
- selection-driven CAD inspector и tabs пространств/листов;
- CAD tree слева от inspector;
- resizable bottom tray с tabs «Проблемы» / «Журнал»;
- persisted semantic suggestion jobs и Celery queue;
- опциональный local Laya container с disk cache;
- кнопка запуска и polling статуса model assist;
- отображение provider method/confidence и обязательный review.

## Tests before implementation

- T3G.1: step state вычисляется из project state без ложного completed;
- T3G.2: document/space/layer/XREF selection однозначно разрешается в inspector;
- T3G.3: tray height clamp и drag delta детерминированы;
- T3G.4: provider payload содержит только allowlisted layer features;
- T3G.5: unknown label/invalid probability не сохраняются;
- T3G.6: job idempotency и terminal states;
- T3G.7: model suggestion сосуществует с rule suggestion и требует review.

## Work packages

1. Принять ADR-0029/0030 и зафиксировать contracts.
2. Написать pure frontend tests для selection, wizard state и tray resize.
3. Перестроить workbench layout и bottom tray.
4. Добавить migration jobs, API start/status и repository projection.
5. Добавить semantic Celery worker и typed layer provider adapter.
6. Добавить Compose profile `ai`, local cache и эксплуатационную инструкцию.
7. Подключить кнопку и polling, показать method/confidence/error.
8. Пройти regression tests/build и smoke test без AI profile.
9. Запустить Laya profile, измерить cold start/RAM/latency и проверить выборку размеченных слоёв.
10. Решить по benchmark: fine-tune, calibration или замена provider.

## Acceptance

| Требование | Evidence |
|---|---|
| Процесс читается как мастер | верхний stepper и доступная publish goal |
| CAD navigation привычна | tree слева, inspector selection справа |
| Листы переключаются | Model/Paper tabs без второго document selector |
| Категории предлагаются в фоне | persisted job + semantic queue + status polling |
| AI безопасен | allowlist, validation, human review gate |
| Нижняя панель пригодна для расследования | tabs, collapse и pointer resize |
| Базовый стек не зависит от weights | compose без `--profile ai` остаётся healthy |

## Exit gate

UI/backend vertical slice и regression tests переводят итерацию в `Verification`. `Complete`
требует реального прогона local Laya по двум пилотам, размеченной выборки не менее 100 слоёв и
отчёта accuracy/calibration/latency/RAM. До этого кнопка и suggestions помечены experimental.
