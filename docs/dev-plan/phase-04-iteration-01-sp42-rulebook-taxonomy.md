# Phase 4, iteration 1 — СП 42 rulebook и object taxonomy v2

- Status: Complete
- Date: 2026-09-29
- Owners: architecture domain, CAD domain, rulebook, backend, frontend

## Outcome

Слои классифицируются закрытым нормативно пригодным vocabulary, а локальная редакция СП 42
представлена в PostGIS как источник, provisions и структурированные review rules. Таблица 9.1 полностью
проверяется SQL-тестами и готова к экспертной публикации без повторного ручного ввода.

## Prerequisites

- ADR-0006;
- ADR-0036;
- ADR-0037.

## Tests before implementation

1. Новая taxonomy имеет ровно один active version и не содержит lifecycle в object class.
2. Все категории классификатора существуют в taxonomy/geo catalog.
3. Таблица 9.1 даёт 19 ненулевых subject/object clearances.
4. Прочерки не превращаются в нули или `allow`.
5. Газ/канализация, вода/дренаж, тепло, power/telecom остаются раздельно классифицируемыми.
6. Правила примечаний crown/overhead/insolation требуют review.
7. Draft rule set не считается published.
8. Frontend предлагает v2 labels и не предлагает retired broad vegetation/lawn values.

## Work packages

1. Инвентаризировать все озеленительные положения локального PDF с page/locator/hash.
2. Добавить taxonomy v2 и canonical object classes.
3. Исправить deterministic layer classifier и typed model allowlist.
4. Обновить UI category picker/labels.
5. Загрузить document edition, provisions, review rules и draft rule set.
6. Применить миграцию к локальному PostGIS и выполнить SQL assertions.
7. Зафиксировать ограничения применимости и очередь экспертной проверки.

## Exit gate

Миграция идемпотентна; API/web tests проходят; SQL возвращает полный набор таблицы 9.1 без approved или
published записей до назначения реального reviewer.


## Completion evidence

- миграция `016` применена к локальному PostGIS без ошибок;
- SQL: 19 правил таблицы 9.1, 31 правило СП 42 всего, 0 approved; edition `unverified`, rule set `draft`;
- API: 63 теста прошли;
- Web: 17 целевых тестов прошли, `tsc --noEmit` прошёл;
- Decision orchestrator: 5 тестов прошли, TypeScript build прошёл;
- инвентаризация: `docs/normative-research/sp42-13330-2016-landscaping-rules.md`.
