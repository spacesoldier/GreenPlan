# GreenPlan CAD conversion platform

Асинхронная цепочка для каждого DWG:

```text
control submit → Redis/Celery queue `oda` → ODA worker → DXF + audit log
                                      └→ Redis/Celery queue `libredwg` → LibreDWG worker → JSON + warnings
                                                                                └→ PostgreSQL stages/artifacts/status
```

`postgres` хранит только операционные метаданные конвертера, логи и SHA-256. Производные файлы лежат на host bind-mount `platform/work/jobs/<job UUID>/`; исходный `dataset` монтируется только для чтения. Данные PostgreSQL лежат именно в `platform/data/postgres`, не в named Docker volume.

Отдельный `postgis` хранит новую предметную модель территории. Его данные находятся в независимом bind-mount `platform/data/postgis`; контейнер не заменяет и не изменяет старый `postgres`.

## Phase 2 application slice

FastAPI и Next.js добавлены в тот же Compose как независимые сервисы:

```bash
docker compose --env-file .env up -d --build api web
```

- web workspace: `http://127.0.0.1:${WEB_PORT:-38101}`;
- FastAPI/OpenAPI: `http://127.0.0.1:${API_PORT:-38100}/docs`;
- readiness: `http://127.0.0.1:${API_PORT:-38100}/health/ready`.

Текущий первый slice явно работает в `GREENPLAN_DATA_MODE=fixture` и показывает два детерминированных пилота. Это тестовый контракт T2.2–T2.6, а не утверждение, что реальные пилотные DXF уже импортированы в доменную модель. PostGIS repository и изолированные DB integration tests составляют следующий пакет T2.1/T2.4.

## Предметная PostGIS-БД

Сервис `postgis` опубликован на `127.0.0.1/0.0.0.0:${POSTGIS_PORT:-36483}` и по умолчанию создаёт БД `greenplan_domain`. Первый запуск пустого `platform/data/postgis` автоматически выполняет SQL из `platform/db/postgis-init`:

```bash
docker compose --env-file .env up -d postgis
docker compose --env-file .env ps postgis
docker compose --env-file .env exec postgis \
  psql -U greenplan_domain -d greenplan_domain -c '\dn'
```

Создаются расширения PostGIS, `ltree`, `pgcrypto` и схемы `core`, `catalog`, `geo`, `biology`, `rules`, `planning`, `provenance`, `intake`, `ops`, `audit`, `api`. Текущая версия применения записана в `ops.schema_migrations`.

Init-скрипты Docker исполняются только при создании пустого PGDATA. После первого запуска новые изменения оформляются отдельной последовательной SQL-миграцией и применяются явно; очистка `platform/data/postgis` не является способом обновления схемы.

Строка подключения с host-машины:

```text
postgresql://greenplan_domain:<POSTGIS_PASSWORD>@127.0.0.1:36483/greenplan_domain
```

Логический backup новой БД:

```bash
docker compose --env-file .env exec -T postgis \
  pg_dump -U greenplan_domain -d greenplan_domain -Fc \
  > greenplan-domain.dump
```

## Первый запуск

1. Получить ODA File Converter самостоятельно, принять его условия и распаковать DEB:

   ```bash
   mkdir -p /tmp/oda-app
   dpkg-deb -x /path/to/ODAFileConverter.deb /tmp/oda-app
   ```

2. Создать локальную конфигурацию:

   ```bash
   cp .env.example .env
   # В .env указать ODA_RUNTIME_HOST_DIR=/tmp/oda-app/usr/bin/ODAFileConverter_27.1.0.0
   # LOCAL_UID/LOCAL_GID должны совпадать с владельцем рабочей папки (обычно 1000/1000).
   ```

3. Собрать и запустить платформу. `35483` — порт операционного PostgreSQL, `36483` — предметного PostGIS; Redis наружу не опубликован.

   ```bash
   docker compose --env-file .env up --build -d postgres postgis redis oda-worker libredwg-worker
   docker compose --env-file .env --profile tools run --rm control init-db
   ```

## Пилоты

Сначала зарегистрировать структуру всех 20 верхнеуровневых проектов (это не запускает конвертацию):

```bash
docker compose --env-file .env --profile tools run --rm control ingest-projects
```

Поставить в очередь два проверенных пилота, по одному за раз:

```bash
docker compose --env-file .env --profile tools run --rm control submit \
  'Пилотный проект 20 улиц/14. Куликовская улица/Проектные решения/DWG/Генеральный план.dwg'

docker compose --env-file .env --profile tools run --rm control submit \
  'Пилотный проект 20 улиц/2. Песчаный переулок/Проектное решение /DWG/ГР_Песчаный переулок.dwg'
```

Команда печатает UUID. Наблюдение:

```bash
docker compose --env-file .env --profile tools run --rm control status <job UUID>
docker compose --env-file .env logs -f oda-worker libredwg-worker
```

`completed_with_warnings` ожидаем для части R2018-файлов: LibreDWG может создать JSON с parser warnings. Успех ODA и LibreDWG хранится по стадиям раздельно, поэтому warning LibreDWG не маскирует отсутствие DXF.

Закреплённый исходник LibreDWG 0.14 лежит в `vendor/libredwg/packages/libredwg-0.14.tar.gz` и проверяется при сборке по SHA-256. Помимо reader-проверки можно поставить все исходники на диагностический DXF-экспорт LibreDWG:

```bash
docker compose --env-file .env --profile tools run --rm control retry-libredwg-dxf-all
```

Эта стадия записывается как `libredwg_dxf`, создаёт временный R2018 DXF и удаляет его после фиксации размера и лога. Она не публикует файл и не заменяет ODA: `return code = 0` совместим с тысячами сообщений о нестабильных, неполных и необработанных классах.

## Массовый прогон

Проверить объём очереди без записи в БД:

```bash
docker compose --env-file .env --profile tools run --rm control submit-all --dry-run
```

Поставить все настоящие DWG в очередь; известные `PaxHeader` отбрасываются по сигнатуре до ODA:

```bash
docker compose --env-file .env --profile tools run --rm control submit-all
docker compose --env-file .env --profile tools run --rm control batch-status
```

Опубликовать готовые ODA-результаты только в `dataset`:

```bash
docker compose --env-file .env --profile tools run --rm control publish-completed --destination dataset
```

Повторный `submit-all` идемпотентен для неизменившегося файла по паре `input_path + SHA-256`. Одинаковые DWG в разных исходных путях не склеиваются: каждый получает свой зеркальный DXF.

Для массового режима `WORK_ROOT_HOST_DIR=/tmp/greenplan-cad-work` переносит рабочие артефакты с тесного `/home` на корневой раздел. `LIBREDWG_KEEP_JSON=false` сохраняет метрики и stderr в PostgreSQL, но удаляет объёмный JSON; `WORK_KEEP_INPUT=false` удаляет staging-копию DWG после диагностики.

## DWG внутри проектных архивов

Архивы обрабатываются только внутри каталогов с точным (без учёта регистра) именем `Архив` или `Архивы` в нумерованных проектах. Верхнеуровневый `dataset/Пилотный проект 20 улиц.zip` намеренно исключён: это резервная копия всего набора, её распаковка продублировала бы датасет. Также исключаются служебные `PaxHeader`.

Сначала выполнить безопасную распаковку только DWG и вложенных ZIP/RAR/7z во временный staging на просторном разделе:

```bash
python3 scripts/archive_members.py --extract
```

Скрипт проверяет пути членов архивов, рекурсивно раскрывает вложенные архивы, удаляет символические ссылки и создаёт `/tmp/greenplan-archive-extracted-sol/archive-manifest.json` с SHA-256 и сигнатурами DWG. Остальные файлы из архивов не извлекаются. Исходные архивы в `dataset` не меняются.

Проверить и отправить извлечённые DWG в обычную ODA/LibreDWG-цепочку:

```bash
docker compose --env-file .env --profile tools run --rm control submit-archives --dry-run
docker compose --env-file .env --profile tools run --rm control submit-archives
```

Виртуальный путь сохраняет provenance и не смешивается с исходным деревом. Например член `files/a.dwg` архива `Архив/old.zip` будет опубликован как:

```text
dataset/<коллекция>/<улица>/dxf/_archives/Архив/old.zip/files/a.dxf
```

Одинаковые DWG по разным архивным путям остаются отдельными представлениями: это важно для восстановления состава каждой поставки. Staging можно удалить только после завершения и публикации всех архивных задач; для повторной диагностики без него потребуется заново выполнить распаковку.

## Выкладка DXF: рабочая папка не является выдачей

`work/jobs/<UUID>/` — внутренняя, воспроизводимая рабочая область одной задачи: там есть staging-копия исходного DWG, DXF от ODA и JSON/`stderr` LibreDWG. Её нельзя передавать как результат: в ней технические копии, диагностика и UUID вместо понятных путей.

Выдачу создаёт только команда `publish` из сохранённого ODA-артефакта. Для исходника:

```text
dataset/Пилотный проект 20 улиц/14. Куликовская улица/
  Проектные решения/DWG/Генеральный план.dwg
```

она создаёт два идентичных по содержанию DXF, сохраняя путь **после папки улицы**:

```text
dataset/Пилотный проект 20 улиц/14. Куликовская улица/
  dxf/Проектные решения/DWG/Генеральный план.dxf

platform/exports/dxf-only/
  14. Куликовская улица/Проектные решения/DWG/Генеральный план.dxf
```

В `dataset` исходники не перемещаются и не изменяются: добавляется только изолированная папка `dxf/` в корне улицы. В переносимом дереве лежат **только `.dxf`**, без JSON, логов и манифестов; полная provenance остаётся в PostgreSQL. Копирование атомарно, проверяет SHA-256, не перезаписывает отличающийся файл без `--overwrite`, а повторный запуск с тем же байтовым результатом отвечает `already_present`.

Выложить один готовый job в оба назначения:

```bash
docker compose --env-file .env --profile tools run --rm control publish <job UUID>
```

Выложить по одному результату на каждый уникальный исходный DWG, уже завершённый ODA:

```bash
docker compose --env-file .env --profile tools run --rm control publish-completed
```

Перед массовой записью доступен безопасный просмотр путей: `publish-completed --dry-run`. При будущем прогоне 20 проектов сначала запускаем `--dry-run`, сверяем структуру, потом убираем этот флаг.

## Как устроена первичная структура проектов

`ingest-projects` проходит папки с префиксом `N.` под `dataset/Пилотный проект 20 улиц` и записывает все файлы (кроме `PaxHeader`) в `source_assets`. Роли — это только объяснимая эвристика путей:

| Роль | Сигналы |
|---|---|
| `project_head_candidate` | «Проектное решение» и имя «генплан», «генеральный план», `ГР_`, «дендроплан», «разбивочно-посадочный» |
| `project_delivery` | «Проектное решение» без сильного сигнала листа |
| `material_basis` | «Исходные данные», АПОТ, ИРД |
| `archive` | «Архив» |
| `plan_candidate` / `unclassified` | остальные планы и материалы |

Для новых intake-проектов используется более точный словарь ролей: `project_solution`,
`source_data`, `survey_existing`, `xref_dependency`, `register`, `normative`, `archive`,
`service_noise`, `unknown`. Роль — проверяемая классификационная подсказка, а не команда на
перемещение или удаление файла. Детали: `docs/adr/0020-human-reviewed-cad-classification.md`.

Это старт для статистики разных подрядчиков: сохраняются confidence и cues, а не выдуманная окончательная связь «голова → основание». Следующим шагом будет отчёт по каждому проекту, где человек или LLM подтверждает связи между `project_head_candidate` и `material_basis`.
