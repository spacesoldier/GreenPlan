# ADR-0006: Нормативный текст и исполняемое правило — разные сущности

- Status: Accepted
- Date: 2026-09-25
- Owners: rulebook and domain experts
- Related phase: Phase 1, Phase 4
- Supersedes: —
- Superseded by: —

## Context

Нормативы распространяются как PDF/HTML разных редакций, содержат таблицы, примечания и исключения. LLM полезна для поиска и структурирования, но её свободный ответ не может быть основанием инженерного решения.

## Decision

- Raw document, edition, source fragment, provision, rule candidate, approved rule и published rule set хранятся отдельно.
- Сегментация следует юридической структуре и сохраняет page/bbox locator.
- LLM создаёт только `rules.rule_candidates` со своей версией, prompt hash, confidence и raw output.
- Deterministic validation проверяет число, единицу, классификаторы, условия, даты и источник.
- Только reviewer создаёт/утверждает `rules.rules`; constraint engine читает только approved rules опубликованного rule set.
- Новая редакция не переписывает старую, а отправляет зависимые правила на revalidation.

## Alternatives considered

### RAG-ответ непосредственно в planning engine

Отклонён: недетерминирован, не гарантирует точную цитату и не фиксирует применённую редакцию.

### Ручной hardcode расстояний

Отклонён как непроверяемый и плохо версионируемый, хотя ручной review чисел остаётся обязательным.

## Consequences

### Positive

- каждое ограничение имеет точную трассу до источника;
- LLM можно менять без изменения опубликованных правил;
- старый расчёт воспроизводится по rule set fingerprint.

### Negative / trade-offs

- нужен экспертный review;
- ingestion сложнее простого embeddings index;
- доступность и лицензия документов становятся частью данных.

## Verification

- candidate не доступен в `api.effective_rules`;
- approved rule требует reviewer и provision;
- provision связан с verified edition/source fragment;
- regression case подтверждает геометрию и объяснение каждого правила;
- report содержит document, edition, locator и rule version.

## References

- [Rulebook](../04-rulebook-explainability.md)
- [Нормативный ingestion](../15-regulatory-corpus-and-rule-ingestion.md)
- [Первые кандидаты 743-ПП](../../normatives/candidates/moscow-743-pp__table-3.6.1.yml)
