# ADR-0023 — Provider-neutral typed decisions: Jev и Laya

- Status: Accepted
- Date: 2026-09-27
- Owners: ML, backend, security, domain modelling
- Related phase: Phase 3, iteration 2
- Supersedes: —
- Superseded by: —

## Context

Ассистенту нужно многократно отвечать на небольшие вопросы с заранее известным пространством
ответов:

- какую роль играет файл в поставке;
- к какому domain относится CAD layer;
- показывает слой existing, proposed, demolition или reference;
- содержит ли слой geometry, annotation, hatch, legend либо construction graphics;
- достаточно ли контекста или требуется инженерная проверка.

Генеративная LLM может вернуть JSON, но остаётся генератором текста: формат и набор labels
нужно дополнительно валидировать. Jev позиционируется как decision layer с типами `Choice`,
`Score` и `Noul`, явными probabilities/confidence и несколькими вопросами над одним state.
Laya предоставляет локальную open-weight реализацию typed decisions и Jev-compatible HTTP
endpoint. Требуется решить, как использовать оба варианта без привязки доменной модели к
одному поставщику.

## Decision

### 1. Доменный контракт не зависит от provider

Backend вводит интерфейс `TypedDecisionProvider`:

```text
decide(
  state: VersionedFeatureSnapshot,
  questions: map<QuestionId, Choice | Score | Noul>,
  provider_config_version
) -> TypedDecisionResult
```

Сохраняются request schema version, provider/model version, question definitions, ответ,
probabilities, confidence, latency, usage/cost, error и fingerprint. Provider response сначала
проходит schema validation и только затем становится `classification_suggestion`.

### 2. Роли providers

| Provider | Роль в Phase 3 iteration 2 |
|---|---|
| deterministic rules | обязательный baseline и fallback без сетевой/модельной зависимости |
| Laya multilingual | основной кандидат для локального bulk inference над русскими именами и метаданными |
| hosted Jev | challenger для сравнительного benchmark и возможный provider для ограниченных несекретных states |
| generative LLM | только для открытых задач: разбор легенды, пояснение evidence, предложение новых неизвестных labels |

Default выбирается только по результатам benchmark на frozen reviewed set. Наличие общего
`/v1/systemone`-подобного wire contract не означает равное качество или полную семантическую
эквивалентность моделей.

### 3. Вопросы остаются атомарными

Для одного layer feature snapshot отправляются независимые `Choice`:

- `domain`;
- `lifecycle`;
- `representation`;
- `document_role`, если вопрос относится к документу.

`Score` применяется для упорядочиваемых величин, например степени похожести на master или
приоритета review. `Noul` применяется только к отдельному проверяемому утверждению. Решение
`можно автоматически публиковать` не задаётся модели: его вычисляет код из fidelity state,
риска, thresholds и наличия обязательных review events.

Каждый `Choice` включает `unknown/other`, чтобы provider мог не выбирать ложную предметную
категорию. Число вариантов ограничивается релевантной веткой taxonomy, а не всеми классами
БД одновременно.

### 4. Confidence управляет маршрутом, но не является доказательством

Probability/confidence используются только для:

- ранжирования human review queue;
- выбора дополнительного анализа;
- batch confirmation низкорисковых suggestions после calibration;
- сравнения providers.

Они не заменяют accuracy, fidelity checks и human review. Порог задаётся по каждой оси и
категории на reviewed data. Конфликт rules/provider или значение около порога приводит к
`review_required`, а не к случайному выбору.

### 5. Privacy и deployment

- API keys существуют только в backend/worker secrets и не попадают в Next.js bundle.
- Hosted Jev выключен по умолчанию для project content.
- Перед внешним вызовом policy проверяет разрешённые поля feature snapshot, проект и consent.
- Полные DWG/DXF, геометрия, персональные данные и содержимое документов внешнему provider не
  отправляются.
- Local Laya работает отдельным optional container/process с resource limits и healthcheck;
  model weights не включаются в основной API image.
- При timeout, quota, invalid response или недоступности provider pipeline продолжает работу
  в rule-only режиме и регистрирует diagnostic event.

### 6. Benchmark

Rules, Laya и Jev получают байтово эквивалентный normalized feature state и одинаковые
question definitions. Сравниваются:

- macro/per-class precision, recall и F1 по каждой оси;
- calibration error и risk/coverage curve;
- dangerous errors;
- abstention и human review rate;
- p50/p95 latency, retry/error rate;
- стоимость на document/project;
- устойчивость к сокращениям, транслитерации и отсутствующему контексту.

Provider не становится default на основании marketing benchmark или нескольких удачных
примеров.

## Alternatives considered

### Использовать только hosted Jev

Не выбрано до проверки политики данных, русского домена, стоимости и доступности. Остаётся
ценным challenger благодаря typed API.

### Использовать только локальную Laya

Не фиксируется заранее: локальность и открытые веса удобны, но качество на сокращениях CAD
должно быть измерено. Provider abstraction позволяет сравнить её без переписывания pipeline.

### Использовать `ax-llm/ax` как обязательную прослойку

Не выбрано для первой реализации. Ax может оркестрировать providers и оптимизацию prompts,
но текущему Python backend достаточно небольшого typed adapter. Ax можно добавить позже,
если появятся сложные flows и обучаемые question programs.

### Генеративная LLM с JSON Schema для всех решений

Не выбрана как основной классификатор: она полезна для open-ended разбора, но typed decision
provider лучше соответствует конечному answer space и вероятностному routing.

## Consequences

### Positive

- Jev и Laya сравниваются на одинаковом контракте;
- можно переключить provider без изменения taxonomy и review UI;
- стоимость, latency и качество становятся измеримыми;
- pipeline остаётся работоспособным без модели;
- правила безопасности и публикации остаются детерминированными.

### Negative / trade-offs

- нужно поддерживать adapter/conformance tests для каждого provider;
- probability distributions разных моделей нельзя считать взаимозаменяемыми без calibration;
- local Laya требует RAM/VRAM, model cache и операционного мониторинга;
- hosted Jev добавляет стоимость, внешний SLA и требования к data policy.

## Verification

- contract fixtures проходят для rules, Laya adapter и Jev adapter;
- неизвестный label, отсутствующая probability или неверный question id отклоняются;
- API key отсутствует в browser assets и logs;
- внешний provider не получает запрещённые поля feature snapshot;
- timeout и 429 переводят задачу в rule-only/review, но не обрывают assistant run;
- replay хранит точные model/question/schema versions;
- default provider выбирается опубликованным evaluation result;
- high confidence без reviewed calibration не создаёт effective mapping.

## References

- [Jev developer documentation](https://thejevai.com/docs)
- [Jev vs LLM community overview](https://huggingface.co/blog/sora-2/jev-ai-vs-llms-when-should-you-use-a-decision-mode)
- [Laya model card and Jev-compatible server](https://huggingface.co/convaiinnovations/laya)
- [ADR-0021](0021-bounded-project-intake-assistant.md)
- [ADR-0022](0022-versioned-cad-semantic-taxonomy-and-learning-loop.md)
- [Phase 3 iteration 2](../dev-plan/phase-03-iteration-02-intake-assistant.md)
