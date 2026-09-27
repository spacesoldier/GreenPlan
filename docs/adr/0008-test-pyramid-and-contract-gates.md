# ADR-0008: Фазы принимаются контрактными тестами на границах системы

- Status: Accepted
- Date: 2026-09-25
- Owners: development team
- Related phase: Phase 2, Phase 3, Phase 4
- Supersedes: —
- Superseded by: —

## Context

Большинство рисков проекта возникает на границах: версия БД и API, CRS, candidate/approved state, bbox geometry transport, сохранение provenance и различие preview/effective. Большое число isolated unit tests не докажет эти контракты.

## Decision

Пирамида тестов строится так:

1. быстрые unit tests для pure parsing, mapping и state transitions;
2. schema/contract tests для SQL migrations, OpenAPI и DTO;
3. PostGIS integration tests в отдельной test database;
4. API tests через FastAPI ASGI без сети;
5. минимальные browser E2E для критических пользовательских путей;
6. fixture-based regression tests на двух пилотах и нормативных фрагментах.

Каждая phase capability сначала получает failing acceptance/contract test. Snapshot tests не заменяют semantic assertions. Тесты не читают mutable production dataset напрямую: используются маленькие лицензируемые fixtures с известными hashes.

## Alternatives considered

### Только E2E

Слишком медленно и плохо локализует ошибки пространственной/предметной логики.

### Только unit tests

Не проверяет migrations, SQL constraints, serialization, BFF proxy и renderer picking.

### Тестировать на полном dataset

Полезно как nightly/regression run, но непригодно для быстрой и переносимой проверки каждой функции.

## Consequences

### Positive

- критические границы проверяются до UI polish;
- тесты формализуют ADR;
- ошибки найденных проектов превращаются в постоянные fixtures.

### Negative / trade-offs

- нужна управляемая test PostGIS;
- fixtures необходимо анонимизировать/проверять по лицензии;
- browser E2E требует стабильных selectors и deterministic scene.

## Verification

- CI/local command поднимает test dependencies и завершается одним exit code;
- тесты не требуют production PGDATA и не изменяют dataset;
- Phase 2/3 acceptance matrix связывает requirement с test id;
- regression fixture добавляется до исправления каждого нового дефекта.

## References

- [Development lifecycle](0001-development-lifecycle.md)
- [Phase 2 plan](../dev-plan/phase-02-readonly-vertical-slice.md)
- [Phase 3 intake plan](../dev-plan/phase-03-controlled-project-intake.md)
- [Phase 4 planning plan](../dev-plan/phase-04-review-and-planning.md)
