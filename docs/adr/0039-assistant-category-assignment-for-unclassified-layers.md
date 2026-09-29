# ADR-0039 — Назначение классов ассистентом только неразобранным слоям

- Status: Accepted
- Date: 2026-09-29
- Owners: CAD domain, backend, frontend, ML
- Related phase: Phase 4, iteration 3
- Supersedes in part: ADR-0020 и ADR-0038 для file-scoped semantic assistant
- Superseded by: —

## Context

Semantic worker сохранял результат модели как pending suggestion. Пользователь затем повторял уже
сделанную классификацию вручную, чтобы получить confirmed mapping и зелёную плашку. Повторный запуск
снова обходил все слои файла, включая уже назначенные человеком.

## Decision

File-scoped semantic job выбирает только `cad_layers.mapping_status <> confirmed`. Прогресс и input
fingerprint также считаются только по этой области.

Любой содержательный класс ассистента сразу записывается как `review_status=accepted` и
`mapping_status=confirmed`, обновляет canonical candidate class, создаёт classification review и
audit event. `unknown` не подтверждается и остаётся в очереди «Не разобраны».

Автоматическое назначение не выдаётся за ручное: `axis_results.assistant_assigned=true`, resolver,
model invocation и confidence сохраняются. UI показывает «назначено ассистентом». Пользователь
может выбрать подтверждённый слой и переназначить его тем же batch-review механизмом.

Если неразобранных слоёв нет, кнопка отключена, а API возвращает conflict `all_layers_classified`,
а не создаёт пустую задачу.

## Consequences

### Positive

- один вызов модели даёт тот же рабочий результат, что ручное назначение;
- повторный запуск обрабатывает только оставшийся хвост;
- человеческие решения не перезаписываются;
- `unknown` не маскируется зелёным подтверждением.

### Negative / trade-offs

- ошибочный содержательный ответ модели временно становится confirmed;
- инженер должен исправить ошибку вручную;
- provenance обязателен для различения модели, canonical-name matcher и человека.

## Verification

- scope SQL содержит `mapping_status<>confirmed`;
- assignable policy принимает конечные классы и `not_applicable`, но отвергает `unknown`;
- фильтр «Не разобраны» основан на mapping status, а не на тексте suggestion;
- повторный job тестового файла взял 2 из 4 слоёв: модельный `not_applicable` стал confirmed,
  `unknown` остался candidate, два ручных confirmed не изменились;
- API tests, web tests, typecheck и production builds проходят.

## References

- [ADR-0038](0038-grouped-cad-categories-and-canonical-name-auto-confirmation.md)
- [Phase 4 iteration 3](../dev-plan/phase-04-iteration-03-assistant-category-assignment.md)
