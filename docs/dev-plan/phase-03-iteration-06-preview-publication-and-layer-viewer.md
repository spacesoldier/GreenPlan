# Phase 3, iteration 6 — Preview publication и layer-aware spatial review

- Status: In progress
- Date: 2026-09-29
- Owners: backend, frontend, geospatial, CAD ingestion

## Outcome

Пользователь выбирает несколько верхнеуровневых корней CAD-графа, принимает их объединённый XREF forest без ручной классификации каждого слоя,
публикует её как честно маркированную preview-модель и исследует графику в 2D viewer через фасетный
навигатор исходных и смысловых слоёв. Unknown-геометрия остаётся видимой, а система отдельно сообщает,
почему модель ещё не готова к нормативному расчёту и автоматической расстановке растений.

## Accepted ADR prerequisites

Перед реализацией принять:

- [ADR-0040](../adr/0040-independent-geometry-and-semantic-publication-readiness.md);
- [ADR-0041](../adr/0041-faceted-layer-navigator-for-spatial-viewer.md);
- [ADR-0042](../adr/0042-multi-root-publication-set.md).

Продолжают действовать ADR-0007–0010, ADR-0015, ADR-0017–0020, ADR-0028 и ADR-0039.

## Scope

- независимые geometry/dependency/fidelity/semantic/constraint/render readiness;
- preview publication при неполной семантике;
- multi-root publication set, выбираемый только из верхнеуровневых узлов CAD-графа;
- XREF closure, readiness и findings, ограниченные выбранными корнями;
- classification snapshot и перенос подтверждённых решений в canonical objects;
- semantic debt и предупреждение перед публикацией;
- versioned scene-layer catalog с source identity, status, counts и extent;
- фасеты «Источники», «По смыслу», «Готовность»;
- group/leaf visibility, solo, restore, search, фильтры и zoom-to-layer;
- атомарная согласованность feature query, Canvas и picking;
- возврат из viewer в CAD Explorer к source layer;
- URL/view-state для воспроизводимого слоя и вида;
- основа того же visibility contract для будущего 3D renderer.

## Out of scope

- требование вручную разобрать все слои;
- полноценный 3D renderer;
- автоматическая расстановка растений;
- исполнение нормативных правил на preview/unknown данных;
- редактирование исходного DWG;
- произвольное изменение domain taxonomy из viewer;
- финальные shared presets и многопользовательские права доступа.

## Data and API contracts

### Readiness snapshot

API публикации и detail проекта возвращают:

```text
geometry_readiness
dependency_readiness
fidelity_readiness
semantic_readiness { layer_coverage, object_coverage, confirmed, unknown, not_applicable }
constraint_readiness { status, blockers[] }
render_readiness
publication_mode = preview | effective
```

Snapshot хранится на revision/model и имеет fingerprint.

### Classification projection

Review/publish request передаёт массив root selection objects с ролями; каждый root автоматически включает транзитивный XREF closure. Publish transaction фиксирует root-set manifest и classification snapshot. Canonical object получает source layer identity,
resolved class, resolution source/version и evidence id. Unknown не удаляется.

### Layer catalog

`GET /v1/models/{model_id}/scene-manifest` возвращает catalog version и facet roots. Leaf содержит
source identity, class/status, counts, extent и view metadata. Feature query принимает leaf ids либо
короткий server-side visibility token.

### View state

View state версионирован и содержит model version, facet, expanded nodes, visibility preset/diff,
viewport, bearing, 2D/3D mode и selection.

## Tests to write before implementation

### T3.6.1 — Publication gate separation

- неполная semantic coverage не блокирует preview при готовой геометрии;
- critical fidelity issue по-прежнему блокирует публикацию;
- unresolved XREF без waiver блокирует dependency readiness;
- UI явно называет публикацию preview;
- effective/planning run запрещён при blocked constraint readiness.

### T3.6.2 — Multi-root selection and closure

- в выборе видны только корни, сгруппированные по проектному решению, исходным данным и архиву;
- dependency нельзя передать как root;
- несколько корней публикуются вместе со своими closures;
- findings вне выбранных closures не блокируют публикацию;
- archive root не становится effective design без явной смены роли;
- shared dependency дедуплицируется по occurrence identity.

### T3.6.3 — Classification snapshot projection

- human correction имеет приоритет над assistant/rule;
- assistant assignment имеет provenance;
- unknown сохраняется в canonical model;
- одинаковое имя из разных source assets не разделяет решение;
- повторная публикация той же revision воспроизводит fingerprint.

### T3.6.4 — Coverage calculation

- layer и object coverage считаются независимо;
- пустые слои не улучшают coverage;
- подтверждённый `not_applicable` учитывается корректно;
- counts UI совпадают с API и SQL fixture.

### T3.6.5 — Layer catalog identity

- одноимённые слои разных DWG получают разные scene layer ids;
- XREF ancestry восстанавливается;
- extent/count агрегируются детерминированно;
- facet nodes ссылаются на один leaf identity.

### T3.6.6 — Navigator interaction

- group checkbox имеет tri-state;
- solo/restore не теряет предыдущий visibility set;
- search работает по source name/path и category label;
- zoom-to-layer использует extent;
- unknown filter не скрывает их по умолчанию;
- переход в CAD Explorer содержит project/revision/source/layer deep link.

### T3.6.7 — Render/picking consistency

- скрытая геометрия не рисуется и не выбирается;
- group toggle публикуется одним atomic frame;
- stale request со старым visibility fingerprint отбрасывается;
- pan/zoom и overscan не возвращают скрытые объекты;
- cached tile повторно используется после возврата слоя.

### T3.6.8 — Browser workflow

- открыть review → принять с предупреждением → опубликовать preview;
- открыть viewer → найти unknown → solo → zoom → выбрать объект;
- перейти к source layer в CAD Explorer;
- deep link после reload восстанавливает вид.

## Ordered work packages

1. Принять ADR-0040/0041/0042 и зафиксировать prototype wording «preview publication».
2. Написать T3.6.1–T3.6.2; добавить publication root set, closure snapshot и scoped readiness.
3. Заменить radio master picker на grouped root checkboxes с ролями и dependency preview.
4. Написать T3.6.3–T3.6.4 classification projection/coverage tests; добавить readiness schema и SQL projection.
5. Исправить publish transaction: immutable classification snapshot и unknown-preserving import.
6. Добавить карточку readiness/semantic debt на шаге «Проверка/Публикация».
7. Написать T3.6.5; ввести scene-layer identity, catalog и facet projection.
8. Написать T3.6.6; реализовать resizable/virtualized layer navigator.
9. Написать T3.6.7; связать visibility fingerprint с query, Canvas, picking и tile cache.
10. Добавить source-layer deep links и persisted view state.
11. Написать и пройти T3.6.8 на опубликованном проекте «Старый Гай».
12. Снять browser/API/SQL evidence и дополнить документ отчётом.

## Progress

Завершены work packages 1-3 и multi-root часть package 5: схема выбора корней, XREF closure, scoped gate, grouped UI и раздельная сборка root manifests. Добавлены unit tests вычисления корней; полный API suite и frontend suite проходят. Readiness schema, classification snapshot projection и layer-aware viewer остаются в работе.

## Acceptance matrix

| Требование | Доказательство |
|---|---|
| Можно продолжить без полного ручного разбора | T3.6.1 + preview model id |
| Публикуется выбранный forest, а не произвольные файлы | multi-root API/UI tests + root manifest |
| Не создаётся ложная planning readiness | blocked constraint run fixture |
| Решения CAD Inspector доходят до viewer | T3.6.3 + object detail evidence |
| Unknown не теряется | T3.6.3 + unknown feature count до/после publish |
| Слои различаются по источникам | T3.6.5 |
| Навигатор управляет сценой | T3.6.6 |
| Скрытое нельзя выбрать | T3.6.7 |
| Состояние воспроизводимо | T3.6.8 deep-link reload |

## Risks and fallback

- Если classification projection не готов, preview допускается только с явной маркировкой, что классы
  получены legacy rule classifier; результат не используется для planning.
- Если facet catalog слишком дорог, первая версия отдаёт плоские leaves и строит группы на клиенте,
  сохраняя канонические ids.
- Если visibility token усложняет API, ограниченный список ids остаётся query contract до измеренного
  порога; большие наборы используют preset позже.
- Если source-layer extent отсутствует, zoom-to-layer временно выполняет bounded aggregate query.
- Старый viewer остаётся rollback path для чтения уже опубликованных model version.

## Exit gate

Один реальный проект с неполной классификацией выбирает несколько верхнеуровневых root-файлов, автоматически получает их XREF closures, проходит scoped fidelity review и публикуется как preview,
сохраняет все unknown objects и открывается в viewer. Пользователь может в фасетном навигаторе найти
слой по источнику или смыслу, скрыть/изолировать его, приблизиться к нему, выбрать объект и вернуться
по deep link в CAD Explorer. При этом planning endpoint доказуемо отказывает, если неизвестный
потенциально значимый слой пересекает область расчёта.

## Completion report

Заполняется после реализации: команды тестов, model/revision ids, coverage SQL, API fixtures,
скриншоты navigator и измерения render/picking consistency.
