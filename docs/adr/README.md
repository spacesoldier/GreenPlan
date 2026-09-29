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
| [0021](0021-bounded-project-intake-assistant.md) | Accepted | Ограниченный ассистент превращает delivery в project/XREF/semantic graph и review queue |
| [0022](0022-versioned-cad-semantic-taxonomy-and-learning-loop.md) | Accepted | Многомерная taxonomy, feature snapshots и контролируемое обучение на review events |
| [0023](0023-typed-decision-provider-jev-and-laya.md) | Accepted | Provider-neutral typed decisions, benchmark Jev/Laya и rule-only fallback |
| [0024](0024-prototype-project-soft-delete.md) | Accepted | Обратимое скрытие intake-проектов без потери результатов экспериментов |
| [0025](0025-folder-ingest-and-visible-xref-dependency-tree.md) | Accepted | Настоящая загрузка каталога и диагностическое дерево XREF текущей поставки |
| [0026](0026-intake-activity-stream-and-supported-file-boundary.md) | Accepted | Живой журнал обработки и allowlist CAD/табличных файлов intake |
| [0027](0027-context-first-cad-layer-inspection.md) | Accepted | Контекстный инспектор слоёв и review-корпус до fine-tuning |
| [0028](0028-cad-workbench-graph-navigation-bulk-review-and-activity-dock.md) | Accepted | CAD workbench, graph/tree navigation, batch review, typed issues и нижний activity dock |
| [0029](0029-preparation-wizard-selection-inspector-and-resizable-tray.md) | Accepted | Верхний мастер, selection-driven CAD inspector и resizable bottom tray |
| [0030](0030-local-cad-semantic-suggestion-worker.md) | Accepted | Локальный Laya service и фоновая очередь model suggestions для CAD-слоёв |
| [0031](0031-xref-triggered-fidelity-recheck.md) | Accepted | Разрешение XREF повторно запускает сравнение DWG/DXF и обновляет очередь проблем |
| [0032](0032-evidence-assisted-cad-layer-semantics.md) | Proposed | Контекстная классификация слоёв, retrieval инженерных примеров и benchmark CPU-моделей |
| [0033](0033-deduplicated-evidence-and-vector-retrieval.md) | Proposed | Дедуплицированные CAD/нормативные корпуса, pgvector-first retrieval и rebuildable vector projection |
| [0034](0034-dual-cpu-model-orchestration-with-ax.md) | Accepted | Каскад Qwen/Gemma на CPU, последовательный llama.cpp runtime и typed orchestration через ax-llm/ax |
| [0035](0035-cad-surface-reconstruction-and-spatial-context.md) | Proposed | Entity-level HATCH/road reconstruction, semantic surfaces и вычислимые пространственные отношения |
| [0036](0036-sp42-provenance-gated-constraint-rules.md) | Accepted | СП 42 кодируется как provenance-gated review rules с сохранением примечаний и способа измерения |
| [0037](0037-standard-aligned-cad-object-taxonomy-v2.md) | Accepted | Закрытая object taxonomy v2 отделяет нормативный класс от lifecycle и representation |
| [0038](0038-grouped-cad-categories-and-canonical-name-auto-confirmation.md) | Accepted | Конечные CAD-классы сгруппированы, а уникальные совпадения имени слоя подтверждаются автоматически |
| [0039](0039-assistant-category-assignment-for-unclassified-layers.md) | Accepted | Ассистент сразу назначает содержательные классы только неразобранным слоям |
| [0040](0040-independent-geometry-and-semantic-publication-readiness.md) | Proposed | Геометрический preview публикуется при видимом semantic debt, planning имеет отдельный task gate |
| [0041](0041-faceted-layer-navigator-for-spatial-viewer.md) | Proposed | Viewer использует фасетный source/semantic layer navigator и единый visibility state |
| [0042](0042-multi-root-publication-set.md) | Accepted | Публикация выбирает несколько корней CAD-графа и автоматически включает их XREF closures |
| [0043](0043-asynchronous-observable-publication-job.md) | Proposed | Фоновая single-flight публикация, серверный прогресс и события activity dock |
| [0044](0044-qwen-runtime-image-and-regulatory-bootstrap.md) | Accepted | Публичный Qwen-only runtime и идемпотентный provenance-aware bootstrap СП |
| [0045](0045-library-workspace-and-versioned-knowledge-catalogs.md) | Accepted | Общесистемная библиотека нормативов, принципов генерации и растений |
| [0046](0046-cad-plant-symbol-library-ingestion.md) | Accepted | Импорт CAD-блоков растений с review, provenance и сохранением геометрии |

## Именование

```text
NNNN-kebab-case-title.md
```

Номер монотонный и не переиспользуется. Шаблон: [template.md](template.md).
