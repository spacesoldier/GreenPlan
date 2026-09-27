# ADR-0024 — Обратимое удаление проектов в прототипе

- Status: Accepted
- Date: 2026-09-27
- Owners: backend, frontend, data platform
- Related phase: Phase 3, iteration 2
- Supersedes: —
- Superseded by: —

## Context

Во время настройки ingestion одни и те же поставки будут загружаться многократно. Тестовые
проекты нужно быстро убирать с первой страницы, но физическое удаление каскада delivery,
source assets, CAD inventories, assistant runs и review evidence уничтожило бы полезные
результаты экспериментов.

Одновременно soft-deleted проект не должен блокировать повторное создание проекта с тем же
человеческим кодом улицы.

## Decision

В `catalog.projects` добавляются `deleted_at` и `deletion_reason`. Обычные list/detail/model
queries всегда включают `deleted_at IS NULL`. `DELETE /v1/intake/projects/{id}` выставляет
tombstone, создаёт audit event и просит активные assistant runs остановиться на безопасной
границе. Связанные строки и файлы не удаляются.

Уникальность `(workspace_id, code)` действует только для строк без tombstone посредством
partial unique index. Поэтому новая загрузка может использовать прежний code, не меняя и не
восстанавливая старую поставку.

Кнопка удаления находится на плитке intake-проекта и требует browser confirmation. После
успешного ответа плитка сразу исключается из локального состояния.

## Consequences

- результаты прошлых прогонов остаются доступны для диагностики непосредственно в БД;
- случайное удаление не уничтожает данные;
- повторная загрузка той же улицы получает новый project/revision/delivery identity;
- объём БД и content store продолжает расти;
- UI восстановления, retention policy, права доступа и garbage collection пока отсутствуют.

Это осознанный компромисс прототипа. Перед промышленной эксплуатацией нужны отдельные права
на удаление/восстановление, корзина, сроки хранения, очистка orphaned blobs и журнал actor ID.

## Verification

- удалённый проект отсутствует в `/v1/projects` и `/v1/intake/projects`;
- detail и mutating endpoints возвращают `404` для tombstone;
- повторный DELETE безопасен и возвращает `204`;
- связанные delivery, assets, findings, runs и reviews остаются в таблицах;
- новый проект может получить тот же code;
- `audit.events` содержит `soft_delete` с `recoverable=true`.
