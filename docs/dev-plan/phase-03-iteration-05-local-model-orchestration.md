# Phase 3, iteration 5 — Локальный CPU-контур Qwen/Gemma

- Status: Complete
- Date: 2026-09-29
- Owners: backend, ML, platform

## Outcome

Инженер может запустить опциональный Compose-профиль, отправить feature snapshot CAD-слоя в typed
оркестратор и получить проверяемую подсказку Qwen с условным вторым мнением Gemma. На машине с 16 ГБ
RAM модели не находятся в памяти одновременно.

## ADR prerequisites

- ADR-0023 — provider-neutral typed decisions и human review;
- ADR-0030 — фоновая semantic queue;
- ADR-0032 — evidence-assisted CAD semantics;
- ADR-0034 — accepted topology Ax + sequential llama.cpp runtime.

## Scope

- read-only mount уже скачанных GGUF;
- allowlisted aliases Qwen, Gemma и benchmark YandexGPT;
- lazy start и последовательная смена `llama-server`;
- Ax typed classification endpoint и Laya-compatible transition endpoint;
- low-confidence/unknown cascade Qwen → Gemma;
- health/status, provenance модели и bounded request bodies;
- Compose-профиль `ai-next` и операторская документация.

## Out of scope

- одновременная резидентность нескольких моделей;
- автоматическая публикация категории без review;
- retrieval/Qdrant и optimizer training;
- image input через Gemma projector;
- GPU runtime и production authentication.

## Tests written before implementation

1. runtime принимает только известные aliases и существующий GGUF с правильной сигнатурой;
2. неизвестный alias не может подставить произвольный путь;
3. повторный запрос того же профиля не перезапускает процесс;
4. смена профиля сначала останавливает предыдущий процесс;
5. output validator отклоняет категорию вне taxonomy и невалидную confidence;
6. high-confidence Qwen не вызывает Gemma;
7. low-confidence, `unknown` и explicit second opinion вызывают Gemma;
8. disagreement помечается `abstained/reviewRequired`, а не подтверждается автоматически;
9. Compose config показывает internal-only services и read-only model mount.

## Work packages

1. Зафиксировать topology в ADR-0034.
2. Написать unit tests runtime registry/lifecycle и orchestration policy.
3. Реализовать runtime supervisor поверх официального `llama.cpp:server`.
4. Реализовать Ax service с OpenAI-compatible provider profiles.
5. Добавить `ai-next` services, healthchecks и resource-safe defaults.
6. Проверить unit tests, Compose rendering, container health и один реальный Qwen smoke request.
7. Записать измерения cold start, peak RSS и latency; только затем включать в основной semantic workflow.

## Acceptance matrix

| Требование | Evidence |
|---|---|
| модели не попадают в image/Git | `.dockerignore`, read-only bind mount, `git check-ignore` |
| не более одной модели в runtime | lifecycle unit test и runtime status |
| typed output ограничен taxonomy | orchestrator validation tests |
| каскад не подтверждает конфликт | cascade policy tests |
| обычный запуск остаётся лёгким | Compose profile inspection |
| реальный CPU inference работает | Qwen smoke response и runtime logs |

## Risks and fallback

- Cold switch может занимать минуты; UI должен показывать загрузку профиля.
- Если Ax несовместим с конкретным chat template, сохраняется прямой llama.cpp diagnostic endpoint.
- Если памяти недостаточно, профиль останавливается, а rules/Laya baseline остаются доступны.
- YandexGPT не участвует в автоматическом каскаде до отдельного benchmark.

## Completion report

Реализованы два internal-only сервиса профиля `ai-next`: Ax-оркестратор и supervisor над официальным
CPU `llama.cpp:server`. GGUF подключены read-only, загрузка ленивая, произвольные aliases и пути
отклоняются. Перед сменой профиля предыдущий дочерний процесс завершается; Docker socket и БД сервисам
не передаются.

Проверки 2026-09-29:

- runtime unit tests: `3 passed`;
- orchestration policy: `5 passed`;
- TypeScript strict build и `docker compose --profile ai-next config --quiet` прошли;
- оба контейнера получили status `healthy` без предварительной загрузки модели;
- реальный Ax → Qwen → Gemma smoke request завершился HTTP 200 за 49,049 с;
- Qwen загрузился примерно за 2,2 с, prompt eval составил 33,84 tokens/s, generation — 8,14 tokens/s;
- наблюдавшийся Qwen runtime footprint — около 4,19 GiB, orchestrator — около 38 MiB;
- после переключения в контейнере обнаружен один `llama-server`, активный профиль `cad-gemma`;
- alias `../../etc/passwd` отклонён с HTTP 400 до обращения к модели.

На smoke-примере Qwen вернул `unknown`, а Gemma ошибочно предположила `vegetation.existing`. Итог был
безопасно помечен `disagreement=true`, `abstained=true`, `reviewRequired=true`. Это подтверждает работу
review gate, но также показывает, что качество нулевого prompt-а недостаточно: следующий этап — retrieval
подтверждённых примеров и evaluation corpus, а не автоматическое применение model suggestions.

Сервисы оставлены запущенными для локальной проверки. Основной semantic Celery workflow пока остаётся на
Laya; переходный `/v1/systemone` реализован, но переключение очереди должно быть отдельным контролируемым
изменением с корректной provider/model provenance в БД.
