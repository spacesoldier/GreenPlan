# ADR-0021 — Ограниченный ассистент разбора проектной поставки

- Status: Accepted
- Date: 2026-09-27
- Owners: backend, CAD ingestion, ML, frontend
- Related phase: Phase 3, iteration 2
- Supersedes: —
- Superseded by: —

## Context

Поставка подрядчика — не набор независимых файлов. Это неформальный проектный пакет, где
рядом могут лежать:

- исходные данные заказчика и геоподоснова;
- несколько редакций проектного решения;
- головные DWG, листы для печати и вспомогательные CAD-файлы;
- XREF с абсолютными, относительными и устаревшими путями;
- обследования, перечётные ведомости, PDF и пояснительные записки;
- архивы предыдущих вариантов и служебные файлы.

Один универсальный вызов LLM не способен безопасно определить структуру такого проекта.
Нужны повторяемые технические стадии, граф зависимостей, ограниченные модельные решения и
очередь вопросов человеку. Уже принятые ADR-0018–0020 определяют fidelity gate, XREF assembly
и reviewable classification suggestions, но не связывают их в цельного ассистента.

## Decision

Вводится **Project Intake Assistant** — доменный оркестратор с конечным автоматом, а не
свободный автономный агент. Он выполняет только заранее зарегистрированные операции и не
получает права изменять либо удалять исходную поставку.

### 1. Единица работы

Ассистент работает с immutable `delivery` и создаёт `assistant_run`, привязанный к точным:

- revision и delivery fingerprint;
- версиям taxonomy, rules и model provider;
- версиям readers/converters;
- конфигурации лимитов архивов и XREF resolution;
- случайному seed, если он используется модельным компонентом.

Повторный запуск с теми же входами идемпотентен. Новый файл, новая версия taxonomy или
ручное решение создают новый run либо явно инвалидируют зависимые задачи.

### 2. Граф стадий

```text
delivery inventory
  -> safe nested archive expansion
  -> file-role suggestions
  -> CAD capability routing
  -> DWG diagnostics / controlled DXF conversion
  -> document, layout, layer, block and text inventory
  -> XREF candidate search
  -> dependency graph validation
  -> resolved XREF assembly preview
  -> layer feature extraction
  -> semantic suggestions
  -> human review queue
  -> publication readiness report
```

Задачи исполняются через существующую очередь Celery. Стадия получает typed input/output,
heartbeat, retry policy и terminal state. Ошибка одного необязательного документа не должна
скрывать результаты остальных файлов.

### 3. Иерархия материалов вместо «корзин»

Ассистент не перемещает оригиналы. Он строит поверх них роли и отношения:

- `contains`, `derived_from`, `revision_of`;
- `candidate_master`, `project_sheet`, `xref_dependency`;
- `source_data`, `survey_existing`, `register`, `normative`;
- `archive_candidate`, `service_noise`, `unknown`.

`archive` и `service_noise` означают лишь предлагаемую роль. Такой файл остаётся доступен для
поиска XREF и ручной проверки. Автоматического удаления не существует.

### 4. XREF — отдельный доказательный граф

Ассистент использует ADR-0019 и для каждой ссылки формирует candidates с причиной score:

1. путь относительно родительского документа;
2. точный нормализованный путь delivery;
3. уникальный basename;
4. hash/размер и структурное сходство CAD inventory;
5. поиск среди безопасно раскрытых archive members;
6. ручной выбор при неоднозначности.

Автоматический bind допустим только для единственного кандидата, прошедшего порог и проверки
на цикл, версию DXF, единицы и совместимость. Ассистент обязан показать XREF graph до
публикации и никогда не выбирать между двумя равными basename молча.

### 5. Модель помогает, но не утверждает факты

Небольшая decision model может отвечать на закрытые вопросы: роль файла, домен слоя,
lifecycle и функция слоя. Она не получает SQL, shell, filesystem write или publish tools.
Её результат сохраняется как suggestion с вероятностями, alternatives, input snapshot и
model version. Принятие master, ambiguous XREF и semantic mapping остаётся человеческим
решением.

### 6. Выход ассистента

Ассистент выпускает не один ответ в чате, а набор проверяемых артефактов:

- дерево поставки с предложенными ролями;
- выбранный человеком master и список альтернатив;
- XREF graph и assembly manifest;
- таблицу документов/layouts/layers и semantic suggestions;
- очередь конфликтов и неизвестных случаев;
- fidelity/readiness report;
- полный audit trail решений человека.

## Alternatives considered

### Один большой prompt со списком файлов и слоёв

Не выбран: теряются размеры, XREF transforms, provenance и воспроизводимость; ответ невозможно
надёжно перепроверить после изменения одного файла.

### Полностью автономный агент с доступом к файловой системе

Не выбран: слишком широкие полномочия для недоверенной поставки и недетерминированные
переименования/удаления. Для CAD fidelity требуется строгий pipeline.

### Только детерминированные правила

Остаются первым уровнем, но не покрывают сокращения и двадцать различных подрядных практик.
Неизвестные случаи требуют decision model и накопления review evidence.

## Consequences

### Positive

- один наблюдаемый процесс от папки до assembled model;
- источник каждого решения и каждой ошибки сохраняется;
- можно повторно прогонять все 20 проектов и сравнивать версии движка;
- модель можно менять без изменения доменной схемы и без перепубликации исходников;
- человек разбирает только отсортированную очередь неопределённостей.

### Negative / trade-offs

- потребуется планировщик зависимостей и invalidation;
- объём метаданных и производных артефактов заметно вырастет;
- архивы и вложенные XREF требуют жёстких resource limits;
- успешный assembled DXF всё равно не доказывает сохранность proprietary proxy objects.

## Verification

- повтор одинакового run даёт тот же manifest и fingerprints;
- добавление одного XREF пересчитывает только зависимую часть графа;
- ambiguous и cyclic XREF никогда не bind автоматически;
- удаление/перезапись raw asset невозможно через операции ассистента;
- падение model provider оставляет rule results и review queue работоспособными;
- все 20 проектов завершаются отчётом `ready / review_required / blocked`, а не зависшей задачей;
- UI воспроизводит состояние ассистента после reload по project/revision/run URL.

## References

- [ADR-0018](0018-evidence-gated-cad-reading-and-conversion.md)
- [ADR-0019](0019-resolved-xref-assembly.md)
- [ADR-0020](0020-human-reviewed-cad-classification.md)
- [Phase 3 iteration 2](../dev-plan/phase-03-iteration-02-intake-assistant.md)
