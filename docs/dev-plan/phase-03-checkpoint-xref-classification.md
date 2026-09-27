# Phase 3 checkpoint — XREF assembly и разбор смешанной поставки

- Date: 2026-09-27
- Status: implemented, model-provider benchmark pending
- Decisions: [ADR-0019](../adr/0019-resolved-xref-assembly.md), [ADR-0020](../adr/0020-human-reviewed-cad-classification.md)

## Что теперь делает система с целой папкой

Папка остаётся неизменяемой delivery. Система не переносит оригиналы и не удаляет то, что
похоже на мусор. Поверх дерева строятся независимые представления:

1. inventory фактических форматов и контрольных сумм;
2. role suggestions для файлов;
3. master candidates;
4. CAD documents/layers/XREF graph;
5. canonical model только после fidelity gate и инженерного решения.

Файлы классифицируются как `project_solution`, `source_data`, `survey_existing`,
`xref_dependency`, `register`, `normative`, `archive`, `service_noise` или `unknown`.
Это представление, а не физическая «корзина».

ZIP внутри проектного дерева раскрывается в content-addressed storage как производные
`archive_member`; parent asset сохраняется. Верхнеуровневый ZIP-бандл не раскрывается и не
участвует в анализе. Действуют лимиты 10 000 members, 2 GiB unpacked, 512 MiB/member и
compression ratio 200; path traversal, encrypted members, PaxHeader и `__MACOSX` пропускаются.

## XREF

Инвентаризация сохраняет для каждой ссылки:

- исходный путь и имя блока;
- attach/overlay;
- resolved/missing/ambiguous;
- asset назначения;
- все placements: layout, handle, 4x4 matrix, insert, rotation и scale.

Публикация собирает производный `assemblies/<revision>/assembled.dxf`, рекурсивно встраивая
разрешённые ссылки. SHA-256 и manifest входят в properties canonical model. Геометрия затем
импортируется именно из assembled DXF.

## Подсказки классификатора

Миграция `010` добавляет `intake.classification_suggestions`. Экран intake показывает сначала
30 самых неуверенных файлов/слоёв и позволяет принять либо отклонить решение. Подтверждение
слоя обновляет `cad_layers.mapping_status`; исходный слой остаётся доступен как evidence.

Rule provider работает сейчас. Laya зафиксирована как следующий provider через её
Jev-compatible HTTP API после локального benchmark на размеченной выборке слоёв. Вес модели
и сам runtime намеренно не включены в обязательный API image.

## Проверка

- API unit tests: 15 passed;
- web unit tests: 37 passed;
- TypeScript: `tsc --noEmit` passed;
- production Next.js build passed;
- migration `010` применена к локальному PostGIS;
- на «Старом Гае» записаны 9 XREF с одной placement каждый и 70 suggestions: 1 file + 69
  реально используемых modelspace layers;
- файл `улица Старый Гай_ГП.dwg` предложен как `project_solution` по признаку `_ГП`;
- 9 ссылок остаются `missing`, пока соответствующие файлы не загружены в эту delivery.

## Следующий контрольный прогон

Загрузить найденную папку из девяти зависимостей «Старого Гая», повторить анализ, проверить
нулевое число missing XREF, принять master и опубликовать. Затем сравнить assembled scene с
листами ГП и отдельно измерить судьбу HATCH, IMAGE, ACAD_TABLE и proxy entities.

