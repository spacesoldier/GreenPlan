# ADR-0034 — Двухмодельный CPU-контур Qwen/Gemma под управлением Ax

- Status: Accepted
- Date: 2026-09-28
- Owners: ML, backend, CAD domain, regulatory domain
- Related: ADR-0023, ADR-0030, ADR-0032, ADR-0033

## Context

Laya иногда правильно классифицирует CAD-слои, но качество нестабильно. На целевой машине из ТЗ
доступно от 16 ГБ RAM, поэтому большие модели нельзя сделать обязательной частью runtime. Два доступных
4B-кандидата дают разные преимущества:

- Qwen3-4B хорошо подходит для русскоязычного structured reasoning и текстовых сокращений;
- Gemma 3 4B даёт независимое второе мнение и потенциально может анализировать изображения страниц,
  штампов и легенд после отдельной проверки multimodal runtime.

Пользователь ранее предложил фреймворк `ax-llm/ax`. Это не `google/ax`: одноимённый Google AX является
кластерным runtime для автономных agent workloads и к данной задаче не относится.

`ax-llm/ax` — TypeScript-first DSPy-подобный framework с typed signatures, provider profiles, flows,
few-shot/GEPA optimizers и callback для внешней памяти. Он может обращаться к OpenAI-compatible
llama.cpp endpoints, но не является inference engine, vector database или источником истины.

## Decision

### 1. Используем обе модели, но не держим обязательными одновременно

Вводятся два локальных provider profile:

- `cad-qwen`: `Qwen3-4B-GGUF`, quantization `Q4_K_M`;
- `cad-gemma`: `Gemma 3 4B IT GGUF`, quantization `Q4_K_M`.

Обе модели проходят один evaluation corpus. На 16 ГБ основной режим — каскад:

1. rules/retrieval формируют кандидатов;
2. Qwen выполняет первый typed decision;
3. Gemma запускается только при низкой уверенности, неизвестном сокращении, конфликте с retrieval или
   по команде инженера «второе мнение»;
4. согласие моделей повышает приоритет подсказки, но не превращает её в автоматически подтверждённую;
5. расхождение всегда попадает в review queue.

Для benchmark допускаются последовательные полные прогоны обеих моделей. Два постоянно резидентных
llama.cpp server на минимальном профиле 16 ГБ не являются обязательной конфигурацией.

### 2. Ax живёт в отдельном orchestration worker

Ax не импортируется в Next.js и не получает доступ к БД. Добавляется отдельный внутренний
`decision-orchestrator`/worker, который:

- принимает allowlisted feature snapshot и retrieved evidence;
- выполняет версионированную typed signature;
- выбирает provider profile и каскадную ветку;
- валидирует category по taxonomy;
- возвращает candidates, confidence, abstain, disagreement и evidence ids.

FastAPI остаётся владельцем jobs, прав доступа, Postgres-транзакций и review workflow. Model servers
экспонируют только внутренний OpenAI-compatible API. Ax flow не может самостоятельно принять категорию,
изменить проект или записать нормативное правило.

### 3. Сигнатуры и optimizer artifacts версионируются

Пример логического контракта:

```text
layerObservation:json,
retrievedCadExamples:json[],
allowedCategories:string[] ->
category:class allowedCategories,
confidence:number,
alternatives:json[],
abstained:boolean,
rationale:string,
evidenceIds:string[]
```

Фактический allowed enum строится из taxonomy, а не доверяется свободному тексту модели. В БД хранятся
`signature_version`, Ax version, provider/model/weights revision, retrieval snapshot и optimizer artifact.

Few-shot optimizer обучается только на опубликованном dataset release из подтверждённых review events.
Оптимизация prompt-а не изменяет taxonomy и не заменяет evaluation gate.

### 4. Retrieval остаётся внешним и контролируемым

Ax callback памяти обращается к нашему `RetrievalIndex` из ADR-0033. Worker получает только top-k
CAD exemplars либо нормативных chunks с provenance. Ax не хранит каноническую память внутри процесса.
Это позволяет менять pgvector на Qdrant без изменения signature и не смешивать CAD и нормативный корпус.

### 5. У моделей разные дополнительные роли

- Qwen — основной текстовый классификатор имён, сокращений и контекстных признаков CAD;
- Gemma — adjudicator/second opinion; после отдельного benchmark может анализировать raster crop легенды,
  штампа или таблицы условных обозначений;
- обе модели могут извлекать кандидаты норм из retrieved chunks, но исполняемое правило возникает только
  после инженерно-юридической проверки согласно ADR-0006;
- Laya сохраняется как baseline до получения сравнительных метрик.

### 6. Ресурсные ограничения обязательны

- context по умолчанию 4–8k, а не заявленный максимум модели;
- concurrency inference на 16 ГБ равен 1;
- модельный worker не запускает тяжёлую CAD-конвертацию одновременно без resource scheduler;
- измеряются вес файла, peak RSS, cold start, tokens/s и полный RSS Compose-профиля;
- при нехватке памяти система остаётся в rules/retrieval-only режиме.

### 7. Контейнерная топология и смена моделей

Compose-профиль `ai-next` добавляет два сервиса:

- `decision-orchestrator` — TypeScript-сервис с `ax-llm/ax`, typed validation и каскадом;
- `llm-runtime` — CPU `llama.cpp` за внутренним supervisor API.

Runtime монтирует `platform/data/llm-models` только для чтения и знает allowlist профилей
`cad-qwen`, `cad-gemma`, `cad-yandex`. Supervisor лениво запускает дочерний `llama-server`,
сериализует обращения и перед новым профилем завершает предыдущий процесс. Docker socket ему не
передаётся. Это позволяет реализовать каскад на 16 ГБ RAM ценой cold start при втором мнении.

Healthcheck runtime проверяет наличие и GGUF-сигнатуру весов, но не загружает модель. Обычный
`docker compose up` новые сервисы не запускает. `decision-orchestrator` имеет собственный typed endpoint
и временный совместимый `/v1/systemone`, чтобы существующая очередь могла мигрировать без изменения UI.

Qwen является профилем по умолчанию, Gemma запускается при низкой уверенности, `unknown`, явном запросе
второго мнения или конфликте. YandexGPT доступна только как явно выбранный benchmark-профиль и не входит
в автоматический каскад.

## Consequences

- получаем два независимых 4B-сигнала без зависимости от одной модели;
- Ax даёт typed flow, provider switching и оптимизацию few-shot примеров;
- появляется дополнительный TypeScript service и контракт между FastAPI и orchestrator;
- Gemma имеет отдельные Terms of Use, Qwen3-4B опубликована под Apache-2.0;
- disagreement увеличивает объём ручной проверки, но предоставляет полезные обучающие случаи;
- модели и Ax остаются заменяемыми, так как решения и evidence принадлежат доменной БД.

## Verification

- один feature snapshot воспроизводимо прогоняется через оба provider profile;
- invalid category или malformed Ax output отклоняется до записи suggestion;
- Qwen low-confidence запускает Gemma, high-confidence не тратит второй inference без настройки;
- disagreement сохраняет оба ответа и создаёт review item;
- подтверждённая человеком категория никогда не перезаписывается повторным model run;
- выключенный Ax/model profile оставляет rules и retrieval работоспособными;
- benchmark на 16 ГБ фиксирует полный peak RSS, а не только размер GGUF;
- Google AX отсутствует в dependency graph.
- обычный Compose-профиль не запускает и не загружает GGUF;
- при переходе Qwen → Gemma старый `llama-server` завершён до загрузки новых весов;
- runtime отклоняет неизвестный model alias и путь, не входящий в allowlist;
- контейнеры не получают Docker socket, database credentials и опубликованные наружу model ports.

## References

- [ax-llm/ax](https://github.com/ax-llm/ax)
- [google/ax — другое ПО](https://github.com/google/ax)
- [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF)
- [Gemma 3 4B IT GGUF](https://huggingface.co/ggml-org/gemma-3-4b-it-GGUF)
- [ADR-0032](0032-evidence-assisted-cad-layer-semantics.md)
- [ADR-0033](0033-deduplicated-evidence-and-vector-retrieval.md)
