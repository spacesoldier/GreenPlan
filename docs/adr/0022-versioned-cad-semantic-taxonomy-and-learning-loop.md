# ADR-0022 — Версионируемая CAD-таксономия и обучение на инженерной проверке

- Status: Accepted
- Date: 2026-09-27
- Owners: domain modelling, CAD ingestion, ML, landscape architecture
- Related phase: Phase 3, iteration 2
- Supersedes: уточняет классификационный контракт ADR-0020
- Superseded by: —

## Context

Плоская категория для слоя недостаточна. Например, слой одновременно может означать
«проектируемые», «кустарники», «контур кроны» и «графика генерального плана». Другой слой
может содержать подписи газопровода, но не его геометрию. Имя `ДВ_ГП_П_ДО_Тип5б` понятно
конкретному подрядчику, но не универсальному классификатору.

Если записать один ответ модели прямо в `geo.object_classes`, система смешает наблюдение,
гипотезу и утверждённую семантику. Если обучаться на всех подтверждениях без версий и
разделения по проектам, оценка будет завышена из-за утечки одинаковых шаблонов подрядчика.

## Decision

### 1. Многомерная классификация

Каждый CAD layer получает независимые оси:

| Ось | Примеры |
|---|---|
| `domain` | vegetation, transport, utility, building, terrain, boundary, protection_zone, annotation, unknown |
| `lifecycle` | existing, proposed, demolition, replacement, reference, unknown |
| `representation` | point, centerline, footprint, crown, hatch, symbol, text, dimension, legend, sheet_frame, construction |
| `object_class` | код из версионируемого `geo.object_classes`, если данных достаточно |
| `document_role` | survey, general_plan, dendroplan, source_base, xref, printable_sheet |

Оси допускают `unknown`, `not_applicable` и несколько кандидатов. `object_class` не выводится
только из `domain`: например, подпись водопровода остаётся annotation с тематикой utility,
но не становится геометрией трубы.

### 2. Taxonomy registry

Добавляются версии taxonomy и immutable label definitions. Suggestion ссылается на точную
версию. Переименование или разделение категории создаёт новую версию и migration map, но не
переписывает исторические решения.

Project/contractor profile хранит локальные сокращения отдельно от глобальной taxonomy.
Подтверждение `ДО = дорожная одежда` может повышать prior для документов этого профиля, но
не становится глобальным правилом без отдельной проверки на других подрядчиках.

### 3. Feature snapshot

Классификатор получает версионированный снимок признаков:

- нормализованное и исходное имя слоя;
- путь, роль документа, layout/model context и XREF ancestry;
- entity type histogram, число объектов и долю block inserts;
- color, linetype, lineweight, visibility/frozen flags;
- block names и ограниченную выборку TEXT/MTEXT;
- geometry type, bbox, плотность, повторяемость символов;
- соседние слои и co-occurrence внутри документа;
- rule-based matches и contractor profile cues.

Полная геометрия и содержимое документов не отправляются внешнему provider. Для локальной
Laya формируется компактный state; для любого внешнего provider действует отдельная policy.

### 4. Ensemble и abstention

Итоговая подсказка собирается из независимых источников:

- deterministic rules;
- project/contractor profile;
- typed decision model;
- структурные признаки CAD;
- ранее подтверждённые решения только из разрешённой training version.

Каждый источник сохраняет собственный score. Resolver не усредняет несовместимые ответы
молча: конфликт отправляется человеку. Confidence используется только после calibration на
reviewed evaluation set. Система обязана уметь воздержаться от ответа.

### 5. Human learning loop

Инженер может:

- принять подсказку целиком;
- изменить одну или несколько осей;
- отметить слой как смешанный;
- связать его с другим слоем или block family;
- указать применимость решения к файлу, подрядчику или всем проектам;
- пометить недостаток контекста и запросить просмотр легенды/штампа.

Review event неизменяем и отделён от текущего effective mapping. Новый набор правил или
модель обучается только на опубликованной training snapshot. Автоматическое online learning
не допускается.

### 6. Оценка без утечки

Метрики считаются по каждой оси и категории. Train/test разделяются минимум по project и,
когда метаданные позволяют, по contractor. Отдельно измеряются:

- coverage при confidence threshold;
- precision/recall/F1;
- calibration error;
- доля abstain и конфликтов;
- время инженерной проверки;
- число опасных ошибок: сеть как дорожка, существующее как проектируемое, annotation как
  физический объект.

## Alternatives considered

### Одна категория на слой

Не выбрана: смешивает предметную сущность, стадию и способ изображения и приводит к ложным
геометрическим объектам.

### Свободный текст от генеративной LLM

Допускается только как пояснение. Не выбран как контракт данных: ответы нестабильны и не
обеспечивают закрытый словарь, вероятности и миграцию taxonomy.

### Немедленное дообучение после каждого клика

Не выбрано из-за дрейфа, ошибочных подтверждений и невозможности воспроизвести прошлый run.

## Consequences

### Positive

- слой описывается точнее и не превращает подписи в реальные сети;
- решения подрядчика переиспользуются контролируемо;
- качество модели можно измерять и сравнивать между версиями;
- накопленная ручная работа превращается в пригодный для обучения датасет.

### Negative / trade-offs

- review UI становится многомерным;
- потребуется миграция существующих плоских suggestions;
- первые проекты всё равно потребуют существенной ручной разметки;
- benchmark и calibration становятся обязательной частью релиза модели.

## Verification

- taxonomy version и feature snapshot присутствуют у каждого model suggestion;
- одинаковые inputs/model/taxonomy дают одинаковый normalized result;
- annotation layer не создаёт utility geometry без отдельного geometry evidence;
- `existing` и `proposed` проверяются независимо от domain;
- test split не содержит слои того же project revision, что и train;
- принятие локального contractor mapping не изменяет глобальные правила;
- новая модель не становится default, пока regression suite не пройден.

## References

- [ADR-0020](0020-human-reviewed-cad-classification.md)
- [ADR-0021](0021-bounded-project-intake-assistant.md)
- [Domain data model](../10-domain-data-model.md)
- [Phase 3 iteration 2](../dev-plan/phase-03-iteration-02-intake-assistant.md)
