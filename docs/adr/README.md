# Architecture Decision Records

ADR фиксируют архитектурное решение, его контекст, альтернативы и последствия. Они отвечают на вопрос «почему система устроена так», а не дублируют справочник API или исходный код.

## Порядок работы

1. До планирования новой фазы создать или обновить необходимые ADR.
2. Обсудить решение и перевести ADR из `Proposed` в `Accepted`.
3. Сослаться на принятые ADR из phase plan.
4. Написать тесты, выражающие контракты фазы.
5. Реализовать функции до прохождения тестов.
6. В отчёте фазы привести команды и артефакты проверки.

Принятый ADR не переписывается так, будто первоначальное решение было другим. Новое решение создаётся отдельным ADR со статусом `Accepted` и полем `Supersedes`; старый получает `Superseded by`.

## Статусы

- `Proposed` — решение подготовлено, но ещё не принято;
- `Accepted` — решение обязательно для новых изменений;
- `Rejected` — рассмотрено и отклонено;
- `Superseded` — заменено более новым ADR;
- `Deprecated` — больше не применяется, но прямой замены нет.

## Реестр

| ADR | Статус | Решение |
|---|---|---|
| [0001](0001-development-lifecycle.md) | Accepted | Порядок ADR → plan → tests → implementation → report |
| [0002](0002-cad-conversion-chain.md) | Accepted | ODA как издатель DXF, LibreDWG как независимый диагностический reader |
| [0003](0003-separate-operational-and-domain-databases.md) | Accepted | Раздельные PostgreSQL конвертера и предметный PostGIS |
| [0004](0004-canonical-model-provenance-and-immutability.md) | Accepted | Каноническая модель, provenance и неизменяемость approved revisions |
| [0005](0005-osm-buildings-as-reviewed-candidates.md) | Accepted | OSM-здания входят через review candidates, а не напрямую |
| [0006](0006-regulatory-documents-and-executable-rules.md) | Accepted | LLM извлекает кандидаты, исполняются только утверждённые правила |
| [0007](0007-web-application-boundaries.md) | Accepted | Next.js UI/BFF, FastAPI domain API и независимые downstream viewers |
| [0008](0008-test-pyramid-and-contract-gates.md) | Accepted | Контрактные тесты и quality gates для web/domain vertical slices |
| [0009](0009-viewport-virtualization-and-canvas-rendering.md) | Accepted | Canvas renderer, bbox pagination, culling, predictive prefetch и color picking |
| [0010](0010-coherent-spatial-tile-cache.md) | Accepted | Stable spatial tiles, atomic frame commit, dedupe, vegetation z-order и bounded cache |
| [0011](0011-interaction-raster-frame-cache.md) | Accepted | Affine raster reprojection во время gesture и deferred exact Canvas render |
| [0012](0012-persisted-primary-spatial-cluster.md) | Accepted | Persisted основной spatial cluster, focus-relative tile grid и vegetation composition order |
| [0013](0013-derived-cad-render-assemblies.md) | Accepted | Derived vegetation assemblies по CAD block handle без потери canonical provenance |
| [0014](0014-frame-budgeted-cad-rendering.md) | Accepted | LOD-aware transport cells, Path2D cache и покадровая атомарная сборка exact Canvas frame |
| [0015](0015-overscanned-raster-frames.md) | Accepted | Raster 1.8× и data 2× overscan для непрерывного pan без исчезновения растений |
| [0016](0016-geometry-paint-and-plant-position-semantics.md) | Accepted | Раздельные stroke/fill paths и явная семантика связи посадочного места с кроной |
| [0017](0017-project-intake-workspace-and-state-machine.md) | Accepted | Начальный экран, создание проекта, неизменяемая загрузка и управляемый intake lifecycle |
| [0018](0018-evidence-gated-cad-reading-and-conversion.md) | Accepted | Reader-first DWG обработка, контролируемая конвертация и обязательный fidelity/XREF gate |
| [0019](0019-resolved-xref-assembly.md) | Accepted | Рекурсивная сборка разрешённого XREF-графа с сохранением INSERT transforms |
| [0020](0020-human-reviewed-cad-classification.md) | Accepted | Rule-first подсказки для файлов и CAD-слоёв, модель только за human review gate |
| [0021](0021-bounded-project-intake-assistant.md) | Proposed | Ограниченный ассистент превращает delivery в project/XREF/semantic graph и review queue |
| [0022](0022-versioned-cad-semantic-taxonomy-and-learning-loop.md) | Proposed | Многомерная taxonomy, feature snapshots и контролируемое обучение на review events |
| [0023](0023-typed-decision-provider-jev-and-laya.md) | Proposed | Provider-neutral typed decisions, benchmark Jev/Laya и rule-only fallback |

## Именование

```text
NNNN-kebab-case-title.md
```

Номер монотонный и не переиспользуется. Шаблон: [template.md](template.md).
