# План публикации GreenPlan в Docker Hub

## Короткий ответ

Docker Hub account: <https://hub.docker.com/repositories/simplizio>.

В namespace `simplizio` нужно создать **восемь public repositories**:

1. `greenplan-api`
2. `greenplan-web`
3. `greenplan-control`
4. `greenplan-oda-worker`
5. `greenplan-libredwg-worker`
6. `greenplan-laya`
7. `greenplan-llm-runtime`
8. `greenplan-decision-orchestrator`

PostgreSQL, PostGIS и Redis берутся из официальных upstream repositories. Для
`semantic-worker`, `domain-import`, `plant-library-import`, будущих
`regulatory-bootstrap`, `planning-worker` и `export-worker` отдельные Docker Hub
repositories не нужны: эти роли переиспользуют `greenplan-api` с другой командой.

## Реестр собственных образов

| Repository | Что находится внутри | Compose-роли | Публикация сейчас |
|---|---|---|---|
| `simplizio/greenplan-api` | FastAPI, Celery-модули, `ezdxf`, предметные CLI | `api`, `semantic-worker`, tools/import jobs, будущие planning/export/bootstrap jobs | public |
| `simplizio/greenplan-web` | production standalone Next.js | `web` | public |
| `simplizio/greenplan-control` | CLI управления операционной очередью и конверсионной БД | `control` | public |
| `simplizio/greenplan-oda-worker` | Celery wrapper, Xvfb и зависимости, но не ODA runtime | `oda-worker` | public |
| `simplizio/greenplan-libredwg-worker` | GNU LibreDWG diagnostic reader и worker | `libredwg-worker` | public с сохранением обязательных GPL notices/source offer |
| `simplizio/greenplan-laya` | Laya server и CPU runtime | `laya` | public без checkpoint до отдельной проверки redistribution license |
| `simplizio/greenplan-llm-runtime` | закреплённый llama.cpp supervisor и публичный Qwen3-4B Q4_K_M | `llm-runtime` | public, Qwen-only variant |
| `simplizio/greenplan-decision-orchestrator` | Ax/TypeScript typed decision orchestration | `decision-orchestrator` | public |

## Почему repositories именно восемь

Repository соответствует самостоятельно собираемому image, а не каждому
контейнеру или процессу. Один image может безопасно выполнять несколько ролей,
если у них один dependency set и release lifecycle.

Поэтому не создаются:

- `greenplan-semantic-worker` — это `greenplan-api` с Celery command;
- `greenplan-domain-import` — это `greenplan-api` с import CLI;
- `greenplan-plant-library-import` — это `greenplan-api` с
  `python -m greenplan_api.import_plant_symbols`;
- `greenplan-regulatory-bootstrap` — будет `greenplan-api` с отдельной one-shot
  командой;
- `greenplan-planning-worker` и `greenplan-export-worker` — будут
  `greenplan-api` с разными Celery queues;
- `greenplan-postgres`, `greenplan-postgis`, `greenplan-redis` — используются
  официальные закреплённые upstream images.

Если dependency set planning или нормативного pipeline заметно разойдётся с API,
новый image и repository вводится отдельным ADR, а не заранее.

## Содержимое образов с моделями

### Qwen

Целевой public image `greenplan-llm-runtime` содержит одну модель:

```text
Qwen3-4B-Q4_K_M.gguf
```

В image также включаются:

- исходная лицензия и model card;
- `SHA256SUMS`;
- точная Hugging Face revision;
- OCI labels с названием модели, source URL, лицензией и git revision GreenPlan.

Слой весов копируется до supervisor-кода. Поэтому очередная версия приложения
переиспользует тот же content-addressed model layer и не хранит вторую копию.
Compose всё равно запускает только один `llm-runtime` на машине с 16 ГБ RAM.

Gemma и YandexGPT не входят в public image. Они остаются локальными benchmark
profiles до отдельной проверки условий распространения.

### Laya

Первый public `greenplan-laya` содержит runtime, но не checkpoint. Checkpoint
подключается из bind-mounted Hugging Face cache. Включать его в image можно только
после фиксации точной ревизии, checksum и подтверждения лицензии на
redistribution. Это ограничение важнее удобства установки.

## Запрещённое содержимое

Ни в один public image не попадают:

- ODA File Converter DEB или распакованный proprietary runtime;
- Gemma/YandexGPT weights;
- Laya checkpoint без проверенного права на redistribution;
- dataset, проекты пользователей, DWG/DXF поставок и результаты конвертации;
- PostgreSQL/PostGIS data directories;
- `.env`, пароли, API keys и cookies;
- локальные книги и публикации с неясными условиями распространения.

ODA worker публикуется только как свободная оболочка. Пользователь получает ODA
самостоятельно и монтирует runtime read-only.

## Настройки repositories в Docker Hub

Для каждого repository:

- Visibility: `Public`;
- Build type: manual/CI push, без Docker Hub autobuild на первом этапе;
- Overview: одна строка назначения, ссылка на GitHub и ссылка на операторскую
  инструкцию;
- не включать mutable tags в deployment без digest pinning;
- vulnerability scanning включить, если он доступен для тарифа.

Рекомендуемые краткие описания:

| Repository | Description |
|---|---|
| `greenplan-api` | GreenPlan FastAPI domain API, CAD ingestion and background jobs |
| `greenplan-web` | GreenPlan Next.js operator workspace |
| `greenplan-control` | GreenPlan conversion control CLI |
| `greenplan-oda-worker` | GreenPlan ODA adapter without proprietary ODA runtime |
| `greenplan-libredwg-worker` | GreenPlan LibreDWG diagnostic worker |
| `greenplan-laya` | GreenPlan Laya CPU inference runtime without model checkpoint |
| `greenplan-llm-runtime` | GreenPlan llama.cpp runtime with Qwen3-4B Q4_K_M |
| `greenplan-decision-orchestrator` | GreenPlan typed AI decision orchestration using Ax |

## Политика тегов

Каждый проверенный image получает одновременно:

- release tag: `0.1.0`;
- source tag: `git-<12-char-sha>`;
- architecture tag при необходимости: `0.1.0-amd64`;
- OCI digest, который записывается в release manifest.

`latest` указывает только на последнюю проверенную демонстрационную сборку и не
используется как единственная ссылка в Compose.

Для Qwen runtime дополнительно публикуется immutable model tag:

```text
qwen3-4b-q4km-bc640142
```

Release tag может указывать на тот же manifest, но model tag не переносится на
другие веса или quantization.

Пока сдача не объявлена замороженной, git tag `submission-2026-09-29` является
движущимся candidate pointer. Docker images в это время получают source tags.
После команды владельца о freeze tag фиксируется; затем публикуется одноимённый
image tag или отдельный release manifest. После freeze существующие git/image
tags не переносятся: hotfix получает новый суффикс.

## Рекомендуемый порядок публикации

1. Создать восемь пустых public repositories.
2. Собрать и проверить шесть базовых application/worker images без моделей.
3. Собрать `greenplan-laya` без checkpoint.
4. Собрать Qwen-bearing `greenplan-llm-runtime`, проверить checksum и OCI labels.
5. Выполнить smoke start всего Compose из registry images.
6. Присвоить release и source tags, сохранить digest каждого image.
7. Отправить `latest` только после успешного smoke start.

Не следует начинать с параллельного push всех образов: Qwen image большой, а
ошибка в базовом API/Web иначе обнаружится только после долгой передачи.

## Release manifest

Для сдачи создаётся текстовый manifest следующего вида:

```text
source_commit=<full git sha>
greenplan-api=simplizio/greenplan-api@sha256:...
greenplan-web=simplizio/greenplan-web@sha256:...
greenplan-control=simplizio/greenplan-control@sha256:...
greenplan-oda-worker=simplizio/greenplan-oda-worker@sha256:...
greenplan-libredwg-worker=simplizio/greenplan-libredwg-worker@sha256:...
greenplan-laya=simplizio/greenplan-laya@sha256:...
greenplan-llm-runtime=simplizio/greenplan-llm-runtime@sha256:...
greenplan-decision-orchestrator=simplizio/greenplan-decision-orchestrator@sha256:...
```

Именно digest, а не отображаемое имя тега, является окончательной ссылкой на
содержимое образа.

## Связанные решения

- [ADR-0044: образ Qwen и нормативный bootstrap](../adr/0044-qwen-runtime-image-and-regulatory-bootstrap.md)
- [Развитие Compose](compose-evolution-and-submission-freeze.md)
- [Установка и работа оператора](deployment-and-operator-guide.md)
