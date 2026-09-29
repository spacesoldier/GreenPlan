# Установка, Docker-образы и работа оператора GreenPlan

## 1. Назначение и состояние инструкции

Инструкция предназначена для локального развёртывания прототипа на Linux и для
первичного прохождения проекта через мастер подготовки материалов. Она описывает
текущий UI до публикации канонической модели. Раздел конструктора озеленения
будет дополнен после реализации spatial constraint и planting engine.

Команды выполняются из корня клонированного репозитория, если явно не указан
другой каталог.

## 2. Требования к машине

Минимум для базового CAD-контура без локальных LLM:

- Linux x86_64; основной проверяемый вариант — современная Ubuntu;
- 4 CPU cores;
- 16 ГБ RAM;
- 25 ГБ свободного места плюс объём исходных проектов и производных DXF;
- Docker Engine и Docker Compose plugin;
- Git, `curl`, `sha256sum`, `dpkg-deb`;
- доступ в интернет для первичной сборки образов.

Для AI-профилей рекомендуется:

- не менее 16 ГБ RAM при строго последовательной загрузке моделей;
- 50–80 ГБ свободного места без учёта dataset;
- дополнительно около 10 ГБ для Laya image/cache;
- около 11 ГиБ для подготовленного набора Qwen, Gemma, vision projector и
  YandexGPT benchmark;
- `aria2c` для возобновляемой загрузки GGUF.

Не запускайте Qwen, Gemma и YandexGPT одновременно на машине с 16 ГБ RAM.
`llm-runtime` специально выгружает предыдущий профиль перед загрузкой следующего.

## 3. Что нужно скачать

### 3.1 Репозиторий

```bash
git clone https://github.com/spacesoldier/GreenPlan.git
cd GreenPlan
```

### 3.2 Docker

Установите Docker Engine и Compose plugin по инструкции для своей системы:

- <https://docs.docker.com/engine/install/ubuntu/>
- <https://docs.docker.com/compose/install/linux/>

Проверка:

```bash
docker version
docker compose version
docker run --rm hello-world
```

Пользователь должен иметь доступ к Docker daemon. В производственной среде
учтите, что членство в группе `docker` фактически даёт привилегированный доступ к
машине.

### 3.3 ODA File Converter

Официальная страница загрузки:

<https://www.opendesign.com/guestfiles/oda_file_converter>

Нужно самостоятельно принять условия ODA и получить Linux x64 DEB. Пакет и
извлечённый runtime нельзя помещать в публичный Git или публичный Docker image без
отдельной лицензионной проверки.

Пример локальной подготовки:

```bash
mkdir -p vendor/oda/packages vendor/oda/runtime
cp /path/to/ODAFileConverter_QT6_lnxX64_8.3dll_27.1.deb \
  vendor/oda/packages/

dpkg-deb -x \
  vendor/oda/packages/ODAFileConverter_QT6_lnxX64_8.3dll_27.1.deb \
  vendor/oda/runtime

find vendor/oda/runtime/usr/bin -maxdepth 1 -type d \
  -name 'ODAFileConverter_*' -print
```

Для проверенной локальной сборки каталог имеет вид:

```text
vendor/oda/runtime/usr/bin/ODAFileConverter_27.1.0.0/
```

Если версия изменилась, используйте фактическое имя каталога. В `.env` указывается
именно каталог runtime, а не путь к DEB и не путь к одному executable.

### 3.4 LibreDWG 0.14

Dockerfile использует закреплённый архив GNU LibreDWG 0.14. Он не хранится в Git.

```bash
mkdir -p vendor/libredwg/packages
curl -fL --retry 3 \
  -o vendor/libredwg/packages/libredwg-0.14.tar.gz \
  https://ftp.gnu.org/gnu/libredwg/libredwg-0.14.tar.gz

echo 'cb6ee0b078c6d9e0f09d66f1feac33ba6342df88ae544e9f9335fab475218351  vendor/libredwg/packages/libredwg-0.14.tar.gz' \
  | sha256sum -c -
```

Сборка намеренно остановится, если checksum не совпадёт. Не заменяйте архив под
тем же именем другой версией: обновление версии требует отдельного изменения
Dockerfile и повторного диагностического benchmark.

Официальный каталог релизов: <https://ftp.gnu.org/gnu/libredwg/>.

### 3.5 Локальные публикации и dataset

Эти каталоги не входят в Git:

```text
dataset/                  исходные проектные поставки
normatives/local/         локальные книги и публикации
platform/data/            базы и модели
platform/work/            рабочие артефакты
platform/exports/         переносимая DXF-выдача
```

Создавайте их вручную и не снимайте соответствующие правила `.gitignore`.

## 4. Конфигурация

```bash
cd platform
cp .env.example .env
id -u
id -g
```

Минимально отредактируйте `.env`:

```dotenv
ODA_RUNTIME_HOST_DIR=/absolute/path/to/GreenPlan/vendor/oda/runtime/usr/bin/ODAFileConverter_27.1.0.0
LOCAL_UID=1000
LOCAL_GID=1000

POSTGRES_PASSWORD=replace-with-random-local-password
POSTGIS_PASSWORD=replace-with-another-random-local-password
LLM_RUNTIME_API_KEY=replace-before-shared-use
ORCHESTRATOR_API_KEY=replace-before-shared-use
```

Путь `ODA_RUNTIME_HOST_DIR` должен быть абсолютным. `.env` исключён из Git.

Порты по умолчанию:

| Компонент | Host port | Назначение |
|---|---:|---|
| Операционный PostgreSQL | 35483 | metadata конвертера |
| PostGIS | 36483 | предметная модель |
| FastAPI | 38100 | API и OpenAPI |
| Next.js | 38101 | пользовательский интерфейс |

Если порт занят, измените только левую host-часть через `.env`. Внутренние порты
Compose менять не нужно.

Проверка конфигурации без запуска:

```bash
docker compose --env-file .env config --services
docker compose --env-file .env config >/dev/null
```

## 5. Сборка образов локально

### 5.1 Базовый профиль

```bash
cd platform

docker compose --env-file .env pull postgres postgis redis
docker compose --env-file .env build \
  api web control oda-worker libredwg-worker
```

Сборка `libredwg-worker` проверит архив по SHA-256. Сборка `oda-worker` не копирует
ODA runtime: он монтируется только при запуске.

Запуск инфраструктуры:

```bash
docker compose --env-file .env up -d postgres postgis redis
docker compose --env-file .env --profile tools run --rm control init-db
```

PostGIS init scripts выполняются автоматически только на пустом
`platform/data/postgis`. Последующие SQL-файлы применяются как миграции, а не
путём удаления PGDATA.

Запуск приложения и CAD workers:

```bash
docker compose --env-file .env up -d \
  api web oda-worker libredwg-worker

docker compose --env-file .env ps
```

### 5.2 Laya profile

Laya — действующий экспериментальный baseline для подсказок слоёв.

```bash
mkdir -p data/laya-cache
docker compose --env-file .env --profile ai up -d --build \
  laya semantic-worker
```

Первая загрузка долгая: зависимости и checkpoint сохраняются в
`platform/data/laya-cache`.

### 5.3 Qwen/Gemma/Ax profile

Установите `aria2c`, затем загрузите закреплённые GGUF:

```bash
cd ..
./platform/scripts/download_llm_models.sh

cd platform/data/llm-models
sha256sum --check SHA256SUMS
cd ../..
```

Скрипт загружает модели из Hugging Face, фиксирует ревизии и не добавляет веса в
Git. Состав и лицензии перечислены в [LLM_MODELS.md](../../platform/LLM_MODELS.md).

Запуск:

```bash
docker compose --env-file .env --profile ai-next up -d --build \
  llm-runtime decision-orchestrator
```

Эти сервисы пока являются отдельным экспериментальным профилем и не заменяют
рабочий Laya semantic worker автоматически.

## 6. Проверка развёртывания

```bash
curl -fsS http://127.0.0.1:38100/health/live
curl -fsS http://127.0.0.1:38100/health/ready
curl -I http://127.0.0.1:38101

docker compose --env-file .env ps
docker compose --env-file .env logs --tail=100 \
  api web oda-worker libredwg-worker
```

Откройте:

- приложение: <http://127.0.0.1:38101>;
- OpenAPI: <http://127.0.0.1:38100/docs>.

Если readiness API не проходит, сначала проверяйте health PostGIS и Redis, затем
права пользователя на `platform/data/intake`.

## 7. Публикация образов в Docker Hub

### 7.1 Сколько репозиториев создать

Рекомендуется **восемь Docker Hub repositories**, по одному на собственный образ:

| Repository | Dockerfile | Кто использует |
|---|---|---|
| `spacesoldier/greenplan-api` | `apps/api/Dockerfile` | `api`, `domain-import`, `semantic-worker` |
| `spacesoldier/greenplan-web` | `apps/web/Dockerfile` | `web` |
| `spacesoldier/greenplan-control` | `platform/control.Dockerfile` | CLI tools |
| `spacesoldier/greenplan-oda-worker` | `platform/oda-worker.Dockerfile` | ODA queue; без proprietary runtime |
| `spacesoldier/greenplan-libredwg-worker` | `platform/libredwg-worker.Dockerfile` | LibreDWG queue |
| `spacesoldier/greenplan-laya` | `platform/laya.Dockerfile` | Laya inference; без checkpoint внутри |
| `spacesoldier/greenplan-llm-runtime` | `platform/llm-runtime.Dockerfile` | llama.cpp supervisor; без GGUF внутри |
| `spacesoldier/greenplan-decision-orchestrator` | `apps/decision-orchestrator/Dockerfile` | Ax policy/orchestration |

PostgreSQL, PostGIS и Redis не дублируются: используются официальные upstream
images. Веса моделей не следует помещать ни в Git, ни в application images.
Они загружаются отдельно, хранятся на host и подключаются read-only.

### 7.2 Политика тегов

Для первого прототипа:

- `0.1.0` — читаемый release tag;
- `<git-sha>` — неизменяемая привязка к исходникам;
- `latest` — только для последней проверенной демонстрационной сборки.

Не публикуйте только `latest`: невозможно будет воспроизвести конкретный запуск.

### 7.3 Сборка и push

Войти:

```bash
docker login
```

Из корня репозитория:

```bash
export GREENPLAN_VERSION=0.1.0
export GREENPLAN_SHA="$(git rev-parse --short=12 HEAD)"
export DOCKERHUB_NAMESPACE=spacesoldier

docker build -f apps/api/Dockerfile \
  -t "$DOCKERHUB_NAMESPACE/greenplan-api:$GREENPLAN_VERSION" .
docker build -f apps/web/Dockerfile \
  -t "$DOCKERHUB_NAMESPACE/greenplan-web:$GREENPLAN_VERSION" .
docker build -f platform/control.Dockerfile \
  -t "$DOCKERHUB_NAMESPACE/greenplan-control:$GREENPLAN_VERSION" .
docker build -f platform/oda-worker.Dockerfile \
  -t "$DOCKERHUB_NAMESPACE/greenplan-oda-worker:$GREENPLAN_VERSION" .
docker build -f platform/libredwg-worker.Dockerfile \
  -t "$DOCKERHUB_NAMESPACE/greenplan-libredwg-worker:$GREENPLAN_VERSION" .
docker build -f platform/laya.Dockerfile \
  -t "$DOCKERHUB_NAMESPACE/greenplan-laya:$GREENPLAN_VERSION" .
docker build -f platform/llm-runtime.Dockerfile \
  -t "$DOCKERHUB_NAMESPACE/greenplan-llm-runtime:$GREENPLAN_VERSION" .
docker build -f apps/decision-orchestrator/Dockerfile \
  -t "$DOCKERHUB_NAMESPACE/greenplan-decision-orchestrator:$GREENPLAN_VERSION" .
```

Перед push прогоните тесты и smoke start. Затем добавьте SHA-теги и отправьте:

```bash
for image in \
  greenplan-api \
  greenplan-web \
  greenplan-control \
  greenplan-oda-worker \
  greenplan-libredwg-worker \
  greenplan-laya \
  greenplan-llm-runtime \
  greenplan-decision-orchestrator; do
  docker tag \
    "$DOCKERHUB_NAMESPACE/$image:$GREENPLAN_VERSION" \
    "$DOCKERHUB_NAMESPACE/$image:$GREENPLAN_SHA"
  docker push "$DOCKERHUB_NAMESPACE/$image:$GREENPLAN_VERSION"
  docker push "$DOCKERHUB_NAMESPACE/$image:$GREENPLAN_SHA"
done
```

После отдельной приёмки можно добавить и отправить `latest`. Перед первой
публикацией желательно настроить Docker Hub repositories как public и добавить
к каждому краткое описание и ссылку на GitHub.

### 7.4 Что нельзя встраивать в images

- ODA DEB и извлечённый runtime;
- GGUF, Laya/Hugging Face cache;
- dataset и загруженные проекты;
- `.env`, пароли и API keys;
- PostgreSQL/PostGIS PGDATA;
- локальные нормативные публикации.

Для установки из registry потребуется compose override с `image:` для восьми
сервисов. Его следует добавить в отдельной итерации вместе с CI, multi-arch
решением и smoke-проверкой опубликованных digest. До этого эталонный путь —
локальная сборка текущего Compose.

## 8. Как загрузить проект

### 8.1 Создание

1. Откройте `http://127.0.0.1:38101`.
2. На стартовом экране нажмите плитку с большим плюсом.
3. Введите понятное название территории и создайте проект.
4. Откройте шаг **Материалы**.

### 8.2 Выбор способа загрузки

Для реальной поставки используйте **Добавить папку проекта**, а не повторную
загрузку файлов по одному. Браузер передаёт относительные пути, поэтому дерево
каталогов сохраняется.

Поддерживаемая рабочая граница:

- `.dwg`;
- `.dxf`;
- Excel: `.xls`, `.xlsx` и поддерживаемые табличные варианты.

Остальные файлы пока не показываются в основном списке разбора. Оригинальная
папка на диске не изменяется.

Если браузер спрашивает разрешение на чтение каталога, подтвердите выбор всей
поставки. Не выбирайте верхнеуровневый резервный ZIP всего dataset как обычный
проект: он создаст дубликаты. Вложенные архивы требуют отдельного контролируемого
контура распаковки.

### 8.3 Дерево поставки

Дерево поставки отвечает на вопрос «что фактически загрузили» и повторяет
структуру папок. Это не XREF-граф.

Проверьте:

- видны ли корневые группы `Проектное решение`, `Исходные данные`, `Архив`;
- сохранились ли относительные пути;
- нет ли очевидного сервисного мусора;
- совпадает ли количество CAD-файлов с ожиданием.

Элемент можно исключить из проекта через контекстное меню. Это удаляет asset и
его производные данные из текущего проекта, но не удаляет исходный файл на диске.

## 9. Как провести контролируемый CAD-разбор

### 9.1 Запуск анализа

Перейдите к шагу **CAD-разбор** и запустите контролируемый анализ. Наблюдайте:

- общий progress bar ассистента;
- вкладку **Журнал действий** в нижней панели;
- вкладку **Проблемы**;
- состояние конкретного файла в CAD-графе.

Не начинайте массово разрешать проблемы, пока ассистент продолжает добавлять
новые задачи. В целевом варианте progress является серверным и учитывает все
стадии; текущие длинные операции могут обновлять UI с задержкой.

### 9.2 Что происходит с DWG

Для каждого чертежа система:

1. регистрирует файл и SHA-256;
2. пытается получить reader evidence;
3. при необходимости запускает ODA DWG→DXF;
4. параллельно получает независимую диагностику LibreDWG;
5. извлекает layouts, layers, blocks и entity types;
6. находит XREF;
7. сравнивает состав до и после конвертации;
8. создаёт findings, если доказательств недостаточно.

Сообщение LibreDWG не означает автоматически, что ODA-результат плох. Это
независимый диагностический сигнал, который рассматривается вместе с entity
counts, слоями, XREF и визуальной проверкой.

## 10. Как разрешить XREF

### 10.1 CAD-граф

CAD-граф отвечает на вопрос «какой чертёж подключает какой». По умолчанию корни
свёрнуты. Раскрывайте нужный корневой файл и следуйте по веткам. Один target может
повторяться под несколькими родителями — это нормальное представление графа в
виде дерева.

Корни группируются по смысловым директориям поставки. Архивные редакции не должны
автоматически подменять актуальный файл из проектного решения.

### 10.2 Неразрешённая ссылка

Проблема означает, что target с указанным XREF-именем не найден среди допустимых
assets. Проверьте:

1. путь ссылающегося чертежа;
2. исходное XREF-имя;
3. наличие похожего basename во всей загруженной папке;
4. не исключён ли нужный файл из поставки;
5. не лежит ли он только во вложенном архиве;
6. не был ли файл переименован подрядчиком.

Если файл удалось найти, добавьте его в проект и повторите анализ. Если ссылка
действительно не нужна для текущей редакции, выберите **Игнорировать в редакции**.
Это решение сохраняется как waiver и позволяет продолжить, но остаётся в аудите.

### 10.3 Неоднозначная ссылка

Проблема означает, что найдено несколько правдоподобных файлов. Система не должна
выбирать молча.

Сравните:

- полный относительный путь;
- принадлежность к `Проектному решению`, `Исходным данным` или `Архиву`;
- близость к папке parent-чертежа;
- размер;
- дату и редакцию, если они надёжно доступны;
- содержимое и слой/лист назначения.

Выберите конкретный target и подтвердите. Когда все блокирующие XREF конкретного
файла разрешены, зависимые операции и сравнение DWG/DXF запускаются повторно.

### 10.4 Что снять на скриншоты

Для будущего иллюстрированного руководства нужны:

1. выбранная папка проекта и её дерево;
2. раскрытый корень CAD-графа с XREF;
3. карточка неразрешённой ссылки;
4. выбор одного target из неоднозначных;
5. состояние проблемы после подтверждения;
6. журнал повторного fidelity check.

Скриншоты рекомендуется хранить в `docs/operator-guide/` с обезличенными путями.

## 11. Как разобрать слои

1. В CAD-графе выберите конкретный DWG/DXF.
2. Убедитесь, что выбранный узел визуально выделен.
3. В инспекторе переключите нужный layout как вкладку.
4. Выберите фильтр **Не разобраны**.
5. При необходимости нажмите **Подсказать категории этого файла**.
6. Проверьте предлагаемые конечные классы.
7. Назначьте класс одному слою или выбранной группе.
8. При ошибке откройте фильтр **Все** или **Проверено** и переназначьте класс.

Кнопка подсказок обрабатывает только текущий файл и только слои без выбранного
класса. Модельная подсказка должна иметь тот же видимый результат, что ручное
назначение, но её provenance отличается.

Примеры нормализации:

- `теплосеть`, `тепловая сеть` → инженерная тепловая сеть;
- `возд линии`, `возд линии телеграф` → воздушная линия связи;
- `трубопроводы`, `подземные коммуникации` без уточнения → инженерная сеть,
  тип не определён;
- `подошва откоса` → рельеф/откос;
- мосты, павильоны, навесы, памятники, фонтаны и ограды → здания и сооружения с
  дальнейшим уточнением класса.

Зелёная галка у файла означает, что все его слои получили конечный класс. Это не
равно полной инженерной проверке геометрии или XREF.

## 12. Проверка и публикация

На шаге **Проверка** разберите блокирующие findings. Неизвестные семантические
слои могут оставаться как debt для графического preview, но должны быть явно
видны и могут блокировать будущий planning.

На шаге **Публикация**:

1. выберите один или несколько верхнеуровневых корневых файлов;
2. проверьте автоматически включённые XREF closures;
3. зафиксируйте состав;
4. запустите публикацию один раз;
5. следите за журналом и progress bar;
6. не перезагружайте исходные материалы во время сборки.

Для больших проектов сборка может занять десятки минут. Целевой ADR-0043 требует
disable кнопки на время job, persisted progress и возможность восстановить
состояние после перезагрузки страницы. Пока эта итерация не завершена, при
browser timeout сначала проверяйте журнал и статус проекта: backend мог
продолжить работу и успешно зафиксировать модель.

## 13. Где искать результаты

### Intake upload

```text
platform/data/intake/<project-or-revision>/...
```

Точный физический путь является внутренней деталью; UI и API должны оперировать
asset id и относительным путём поставки.

### Конверсионные jobs

```text
platform/work/jobs/<job-uuid>/
```

Это техническая рабочая область, а не выдача заказчику.

### Переносимая DXF-выдача

```text
platform/exports/dxf-only/
```

Выдача создаётся отдельной publish-командой конверсионной платформы и повторяет
понятную структуру проекта.

### Базы

```text
platform/data/postgres/
platform/data/postgis/
```

Не копируйте живой PGDATA как логический backup. Используйте `pg_dump`.

## 14. Резервное копирование

PostGIS:

```bash
cd platform
docker compose --env-file .env exec -T postgis \
  pg_dump -U greenplan_domain -d greenplan_domain -Fc \
  > greenplan-domain.dump
```

Операционный PostgreSQL:

```bash
docker compose --env-file .env exec -T postgres \
  pg_dump -U greenplan -d greenplan -Fc \
  > greenplan-operations.dump
```

Отдельно сохраняйте intake и, если они нужны для аудита, `work/jobs`. Модели можно
скачать повторно по закреплённым ревизиям, поэтому их backup необязателен при
ограниченном месте.

## 15. Остановка и обновление

Остановить контейнеры без удаления данных:

```bash
cd platform
docker compose --env-file .env --profile ai --profile ai-next down
```

Не используйте `down -v` как обычную команду обслуживания. Bind-mounted PGDATA
не является named volume и требует отдельного осознанного удаления.

Обновление кода:

```bash
git pull --ff-only
docker compose --env-file .env build
docker compose --env-file .env up -d
docker compose --env-file .env ps
```

Перед обновлением схемы сделайте `pg_dump` и прочитайте новые migration/phase
notes.

## 16. Диагностика типовых проблем

### ODA worker не запускается

- проверьте абсолютный `ODA_RUNTIME_HOST_DIR`;
- убедитесь, что путь указывает на извлечённый runtime;
- проверьте архитектуру x86_64 и наличие executable;
- смотрите `docker compose logs oda-worker`.

### LibreDWG build не находит архив

Проверьте наличие:

```text
vendor/libredwg/packages/libredwg-0.14.tar.gz
```

и повторите `sha256sum -c` из раздела загрузки.

### Permission denied в `platform/data`

Сверьте `LOCAL_UID`/`LOCAL_GID` с `id -u` и `id -g`, затем владельца конкретной
bind-mounted директории. Не применяйте рекурсивный `chmod 777` ко всему проекту.

### UI показывает HTTP 500

Соберите correlation context:

```bash
docker compose --env-file .env logs --since=10m api web
```

Запишите project id, действие, время и выбранный файл. Не нажимайте операцию много
раз подряд: сначала проверьте, не продолжает ли backend уже созданную задачу.

### Публикация кажется зависшей

Проверьте CPU, память, свободное место, журнал API и состояние PostGIS. Импорт
миллионов геометрий может продолжаться после timeout браузера. Не удаляйте job и
не перезапускайте БД до проверки серверного статуса.

## 17. Проверки разработчика

```bash
cd apps/api
UV_CACHE_DIR=.uv-cache uv sync --all-groups
UV_CACHE_DIR=.uv-cache uv run pytest

cd ../web
npm ci
npm test
npm run typecheck
npm run build

cd ../decision-orchestrator
npm ci
npm test

cd ../llm-runtime
PYTHONPATH=. ../api/.venv/bin/pytest -q
```

Перед релизом также обязательны `docker compose config`, сборка восьми images,
healthchecks и smoke-прохождение одного небольшого проекта.

## 18. Что будет добавлено после конструктора

Будущие разделы этой инструкции:

- подтверждение зелёных поверхностей и цветных заливок;
- просмотр пересечений с сетями и охранными зонами;
- создание и редактирование site condition profile;
- подбор палитры растений;
- настройка рядовой посадки кустарников;
- генерация деревьев внутри допустимых полигонов;
- сравнение planting alternatives;
- инженерное подтверждение и экспорт отчёта;
- 2D/3D-просмотр и подготовка реалистичных кадров.

До реализации этих функций UI не должен имитировать нормативно подтверждённый
автоматический дендроплан.
\nТребования к будущим planning/export workers и правила freeze описаны в [отдельном документе](compose-evolution-and-submission-freeze.md).
