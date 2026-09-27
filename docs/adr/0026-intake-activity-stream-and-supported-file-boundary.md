# ADR-0026 — Живой журнал intake и граница поддерживаемых файлов

- Status: Accepted
- Date: 2026-09-27
- Owners: frontend, CAD ingestion
- Related phase: Phase 3, iteration 2
- Supersedes: —
- Superseded by: —

## Context

Основной журнал processing attempts находился в центральной длинной колонке и был ориентирован
на технический stderr. Во время загрузки и асинхронной обработки пользователь не видел короткого
ответа на вопросы «что выполняется сейчас», «над каким файлом» и «куда записан DXF».

Folder picker одновременно принимал всю поставку: PDF, изображения, архивы и служебные файлы
занимали место в content store и засоряли список, хотя текущий prototype умеет содержательно
работать только с DWG, DXF и перечётными ведомостями.

## Decision

В правой колонке intake workspace размещается компактный activity stream. Он объединяет
клиентский прогресс upload, persisted assistant tasks и persisted processing attempts, сортирует
события по времени и обновляется тем же polling cycle. Каждое событие содержит время, состояние,
название этапа и delivery-relative path. После ODA conversion показывается `artifact_locator`.
Подробный stdout/stderr остаётся в раскрываемом центральном журнале.

Перед upload UI формирует allowlist. В текущую поставку принимаются:

- CAD: `.dwg`, `.dxf`;
- Excel binary/OpenXML и templates: `.xls`, `.xlsx`, `.xlsm`, `.xlsb`, `.xlt`, `.xltx`, `.xltm`;
- распространённые табличные обменные форматы: `.csv`, `.ods`.

Остальные файлы не отправляются в API и не показываются в списке материалов. UI сообщает только
их количество. `accept` у file input является подсказкой браузеру, а фактическая фильтрация
повторяется в коде, поскольку браузеры не обязаны строго соблюдать `accept`.

## Consequences

- ход длинной загрузки и обработки виден без прокрутки центральной колонки;
- журнал после reload восстанавливается из persisted server attempts, кроме transient upload event;
- перечётные ведомости разных поколений Excel получают корректный media type и роль register;
- неподдерживаемые PDF и изображения пока не сохраняются как provenance поставки;
- когда появится PDF ingestion, его расширения должны быть добавлены отдельным решением вместе
  с parser/preview/review contract, а не только в allowlist.

## Verification

- выбор папки с DWG, XLSM, PDF и JPG загружает только DWG и XLSM;
- UI показывает количество пропущенных файлов;
- activity stream обновляет имя загружаемого файла;
- processing attempt показывает имя исходного asset и номер попытки;
- завершённая конвертация показывает locator производного DXF;
- reload сохраняет server-side события;
- XLSM/XLSB/ODS классифицируются как tabular register candidates.
