# Phase 4, iteration 2 — быстрый разбор конечных CAD-классов

Статус: реализовано 2026-09-29.

Связанный ADR: [ADR-0038](../adr/0038-grouped-cad-categories-and-canonical-name-auto-confirmation.md).

## Цель

Сохранить точные классы ADR-0037, сократить ручной путь назначения и автоматически закрывать
только доказуемые совпадения названия слоя с каноническим словарём.

## Контракты

1. Выбор класса сгруппирован по инженерному смыслу, но сохраняет leaf object class.
2. `utility.unknown` доступен как неполный класс без применения subtype-specific rules.
3. Уникальное каноническое совпадение сразу получает confirmed mapping и audit provenance.
4. Неоднозначность не автоподтверждается и уходит к модели/инженеру.
5. Модель запускается только после deterministic matcher.
6. UI различает автоматическое подтверждение и проверку инженером.

## Реализация

- canonical name matcher с нормализацией, threshold 0.94 и защитой от равных кандидатов;
- русский CAD-словарь эквивалентов и root rules: `теплосеть/тепловая сеть/теплотрасса` → `utility.heat.pipeline`, `трубопроводы/подземные коммуникации` → `utility.unknown`;
- grouped category options в CAD Inspector;
- semantic worker с bypass Laya для канонических совпадений;
- запись classification review, mapping, provider metadata и audit event;
- migration 018 для `utility.unknown` в active taxonomy;
- regression tests для точных, близких и неоднозначных имён.

## Проверка

- API: 66 tests passed;
- web: 59 tests passed, TypeScript clean;
- production API/web images собраны;
- API и web возвращают HTTP 200, semantic worker подключён к очереди;
- на загруженном проекте «Старый Гай» найдено 63 потенциальных канонических совпадения без изменения данных.
