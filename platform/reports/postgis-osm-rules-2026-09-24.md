# Проверка OSM-review и нормативного ingestion

Дата: 2026-09-24.

## Применённая миграция

`005_osm_review_and_rule_ingestion.sql` успешно применена к локальному контейнеру `postgis` базы `greenplan_domain` на порту, заданном compose-конфигурацией. В `ops.schema_migrations` присутствуют версии `0001`–`005`.

Проверено существование:

- `provenance.object_candidates`;
- `rules.document_ingestion_runs`;
- `rules.document_segments`;
- `rules.rule_candidates`;
- новых полей редакции документа и global scope source asset.

Транзакционный smoke-test успешно создал `scope_kind=global` document без фиктивной project revision и затем откатил тестовые данные. После миграции база содержит 82 прикладные таблицы в десяти схемах; `rules.document_segments.search_vector` создан как stored `tsvector` с GIN-индексом.

## Проверенный официальный файл

Источник: `https://www.mos.ru/upload/documents/files/7389/Postanovlenie743-PP.pdf`.

```text
local file: normatives/local/moscow-743-pp__checked-2026-09-24.pdf
media: PDF 1.4, A4, not encrypted
pages: 199
bytes: 8715708
sha256: f5af99982255e6de363543bb2789d395f81a86928c3bebc6ef7ba4a404db2276
```

Текстовый слой извлечён `pdftotext -layout` без OCR:

```text
local file: normatives/extracted/moscow-743-pp__checked-2026-09-24.txt
lines: 15316
bytes: 1804260
sha256: c460ce0cc896415c1622d1d0b07c650a26f3ecca892cb35565055aaa883d3182
```

Найден адресуемый источник первых кандидатов: PDF page 13, пункт 3.6.3, таблица 3.6.1. Транскрипция находится в `normatives/candidates/moscow-743-pp__table-3.6.1.yml` и имеет статус `needs_expert_review`.

## Не завершено намеренно

Точные официальные карточки Минстроя установлены: СП 42 — `https://minstroyrf.gov.ru/docs/14465/`, СП 82 — `https://minstroyrf.gov.ru/docs/14131/`. Сервер Минстроя при прямом запросе не отдал HTML в разумный срок, поэтому прямые PDF и изменения пока не скачаны. Документы не заменялись файлами с неофициальных зеркал и в manifest остаются `link_only` до сборки актуальной редакции со всеми изменениями. Для 623-ПП требуется отдельно подтвердить официальный консолидированный источник.

Пользователь сообщил о легальном бесплатном вечернем окне чтения в одной из справочных систем. Для него добавлен ручной acquisition workflow: сохранить доступный документ без обхода ограничений, зафиксировать URL/условия/timezone/редакцию/hash и только затем запускать локальное извлечение.

Отдельная диагностика `docs.cntd.ru` сохранена в `platform/reports/cntd-access-2026-09-24.md`: пользовательская ссылка `5200163` оказалась legacy СНиП, текущий СП 42 имеет id `456054209`, а HTTPS с agent environment недоступен до уровня HTTP-ответа.
