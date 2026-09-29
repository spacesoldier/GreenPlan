# Развитие Docker Compose и фиксация версии для сдачи

## Вывод

Текущий Docker Compose подходит как основание следующего витка. Для поиска
пересечений, генерации точек посадки и DXF-экспорта не требуется менять БД,
брокер или границу API. Развитие может быть аддитивным:

- PostGIS остаётся источником пространственной истины;
- Redis остаётся брокером короткоживущих сообщений;
- FastAPI создаёт jobs и отдаёт их состояние;
- длительные вычисления уходят в отдельные Celery workers;
- результаты и прогресс сохраняются в PostGIS;
- экспортные файлы пишутся в bind-mounted `platform/exports`.

Текущий Compose можно фиксировать для сдачи. Новые сервисы добавляются уже после
freeze отдельными коммитами и не меняют зафиксированный submission tag.

## Что уже готово в основании

| Возможность | Существующий компонент |
|---|---|
| Пространственные операции | PostGIS 16/3.5 |
| Геометрические и предметные сущности | схемы `geo`, `planning`, `biology`, `rules` |
| Фоновые задачи | Redis и Celery |
| DXF reader/writer | `ezdxf` в API image |
| Управление процессом | FastAPI и intake job patterns |
| Артефакты на одном host | bind mounts `work`, `exports`, `data` |
| Наблюдаемость в UI | activity dock и подготовленный контракт progress jobs |

В схеме уже предусмотрены plans, revisions, constraint zones, candidate sites,
proposals, proposal geometries, capacity assessments, checks и rejections. Их
нужно наполнить исполняемым поведением, а не проектировать параллельную БД.

## Какие процессы добавить

### `planning-worker`

Назначение:

1. реконструировать подтверждённые зелёные поверхности;
2. построить нормативные buffers и constraint zones;
3. вычислить допустимую площадь через пространственную разность;
4. сгенерировать кандидаты кустарников вдоль контуров;
5. сгенерировать кандидаты деревьев внутри полигонов;
6. подобрать совместимые plant profiles;
7. сохранить proposals, checks, rejections и progress events.

Worker переиспользует образ `simplizio/greenplan-api` и слушает отдельную
очередь `planning`. Начальная concurrency — `1`: тяжёлые `ST_Buffer`,
`ST_UnaryUnion`, `ST_Difference` и массовая проверка кандидатов конкурируют за RAM
и временное пространство PostGIS.

### `export-worker`

Назначение:

1. получить утверждённую plan revision;
2. проверить coordinate space и единицы;
3. создать DXF с раздельными слоями существующих объектов, ограничений,
   деревьев, кустарников, крон, подписей и легенды;
4. записать временный файл;
5. проверить чтение результата и состав сущностей;
6. выполнить atomic rename в `/exports`;
7. сохранить checksum, размер, generator version и provenance.

Worker также переиспользует `simplizio/greenplan-api`, слушает очередь
`export` и получает mount `./exports:/exports`.

Для выпуска DXF ODA не нужен: файл создаётся через `ezdxf`. Если позже понадобится
обратный выпуск DWG, он должен быть отдельным явно лицензированным контуром через
ODA, а не скрытой частью DXF-export.

## Принципиальное расширение Compose

Это целевой эскиз, а не готовая конфигурация для вставки до появления кода:

```yaml
planning-worker:
  image: simplizio/greenplan-api:${GREENPLAN_VERSION}
  environment:
    GREENPLAN_DATABASE_URL: ${GREENPLAN_DATABASE_URL}
    CELERY_BROKER_URL: redis://redis:6379/0
  command:
    - celery
    - -A
    - greenplan_api.planning_worker:celery
    - worker
    - --queues=planning
    - --concurrency=1
    - --prefetch-multiplier=1

export-worker:
  image: simplizio/greenplan-api:${GREENPLAN_VERSION}
  environment:
    GREENPLAN_DATABASE_URL: ${GREENPLAN_DATABASE_URL}
    CELERY_BROKER_URL: redis://redis:6379/0
    GREENPLAN_EXPORT_ROOT: /exports
  volumes:
    - ./exports:/exports
  command:
    - celery
    - -A
    - greenplan_api.export_worker:celery
    - worker
    - --queues=export
    - --concurrency=1
    - --prefetch-multiplier=1
```

Перед добавлением этого блока необходимы worker modules, migrations, API jobs,
health/heartbeat и тест восстановления после падения между записью БД и файла.

## Нужны ли новые Docker Hub repositories

Нет. Оба worker используют существующий `greenplan-api` image. Рекомендованный
набор остаётся равен восьми repositories:

1. `simplizio/greenplan-api`;
2. `simplizio/greenplan-web`;
3. `simplizio/greenplan-control`;
4. `simplizio/greenplan-oda-worker`;
5. `simplizio/greenplan-libredwg-worker`;
6. `simplizio/greenplan-laya`;
7. `simplizio/greenplan-llm-runtime`;
8. `simplizio/greenplan-decision-orchestrator`.

Разные роли одного image различаются Compose command и очередью, а не отдельным
repository.

## Что усилить в существующих сервисах

### PostGIS

- проверить GiST/SP-GiST индексы реальными `EXPLAIN (ANALYZE, BUFFERS)`;
- вынести `shm_size`, `work_mem` и statement timeout в профиль машины;
- ограничить сложность геометрии до overlay либо применять контролируемое
  subdivision;
- хранить промежуточные зоны по job/revision и удалять их retention-задачей;
- запрещать публикацию результата с невалидной геометрией.

### Jobs

- персистентные состояния `queued/running/finalizing/completed/failed`;
- heartbeat и обнаружение stale worker;
- идемпотентность по digest
  `canonical_model + rule_set + plant_catalog + plan_spec`;
- partial unique index или advisory lock против двойного запуска;
- отдельные счётчики surfaces, constraints, candidates, checks и exports;
- retry только с понятной границы, а не повтор всей операции вслепую.

### Артефакты

Для односерверного прототипа MinIO/S3 не требуется. Bind-mounted `/exports`
проще, прозрачно копируется и не вводит ещё один сервис. Объектное хранилище нужно
при переходе к нескольким host, большим командам или подписанным download URL.

Qdrant также не нужен для геометрического planning. Векторный retrieval примеров
и нормативов развивается независимо и не включается в критический путь проверки
посадок.

## Ресурсные ограничения

На машине с 16 ГБ RAM нельзя одновременно отдавать большую LLM, выполнять
массовый PostGIS overlay и импортировать миллионы CAD-сущностей без управления
нагрузкой. Для прототипа:

- planning concurrency `1`;
- export concurrency `1`;
- LLM-профили загружаются последовательно;
- количество candidate sites ограничивается quota;
- крупные зоны обрабатываются порциями;
- перед job проверяется свободное место;
- progress и cancellation являются частью контракта.

## Фиксация версии для сдачи

Сдача должна ссылаться не на подвижный `main`, а на аннотированный tag:

```text
submission-2026-09-29
```

До явной команды владельца о freeze этот tag является candidate pointer и может
передвигаться на каждый проверенный коммит. После команды о заморозке действуют
правила недельного freeze:

- tag больше не перемещается и не переиспользуется;
- зафиксированный commit не amend и не force-push;
- дальнейшая разработка продолжается новыми коммитами без изменения tag;
- критический hotfix получает новый tag с суффиксом, а не заменяет старый;
- Docker images сдачи получают version tag и полный Git SHA;
- submission manifest фиксирует Git tag, image digests, дату, конфигурацию и
  известные ограничения.

Воспроизведение:

```bash
git fetch --tags origin
git checkout submission-2026-09-29
git rev-parse HEAD
```

После сдачи Docker images и `main` можно обновлять. Проверяющая сторона при этом
всегда может вернуться к неизменному submission tag.
