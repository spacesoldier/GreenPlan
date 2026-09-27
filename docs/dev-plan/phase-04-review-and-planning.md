# Phase 4 — Reviewed context, rulebook and first planning result

- Status: Planned
- Target: controlled mutations and first explainable constraint/planting flow
- Owners: backend, geospatial, rulebook, frontend

## Outcome

Reviewer выбирает OSM-здание, добавляет его в рассмотрение и принимает/отклоняет без изменения approved baseline. Нормоконтролёр проверяет извлечённое правило. Система публикует тестовый rule set, строит constraint zones и выдаёт первый детерминированный planting proposal с объяснением до конкретного provision.

## ADR prerequisites

- ADR-0005 and ADR-0006 remain Accepted;
- ADR-0007 and ADR-0008 remain Accepted;
- before implementation, add ADR for constraint geometry semantics and conflict/priority resolution;
- before mutations, add ADR for authorization and audit identity.

## Scope

- local OSM snapshot registration/import for two pilot extents;
- clickable building candidate API and review UI;
- verified/candidate transform visibility and constraints;
- document segment/rule candidate review UI;
- manual approval of bounded 743-ПП fixture rules;
- immutable published test rule set;
- deterministic building/utility buffers for tree/shrub intervention classes;
- first planting candidate generation for one declared plant profile;
- decision checks and source-linked explanation;
- preview/effective distinction throughout API and UI.

## Out of scope

- automatic approval of all normative documents;
- optimization of a complete planting assortment;
- legal assurance beyond expert-reviewed corpus;
- photorealistic rendering;
- unattended OSM conflation for all 20 projects;
- final production RBAC/SSO implementation beyond agreed roles.

## Tests written before implementation

### T4.1 — OSM candidate state machine

- shortlist is idempotent;
- click does not mutate approved model;
- accept requires reviewer, verified policy and canonical object in a draft child model;
- reject preserves history; new snapshot marks open candidate stale.

### T4.2 — Transform and preview safety

- unverified transform cannot produce effective constraint;
- preview response carries uncertainty and `not_for_final_decision`;
- accepted object in approved child model can participate in effective evaluation.

### T4.3 — Rule candidate safety

- LLM candidate is absent from effective rules;
- accept fails without edition, fragment, locator, reviewer or valid units;
- accepted rule remains draft until explicit approval/publication;
- published rule set fingerprint is deterministic.

### T4.4 — Table 3.6.1 regression fixtures

- building/tree and building/shrub distances match reviewed fixture;
- utilities distinguish tree/shrub and null/non-applicable cells;
- crown-diameter and insolation notes produce conditions/needs-review, not silently discarded text.

### T4.5 — Geometry engine

- buffer uses correct geometry role and metric CRS;
- boundary cases at required distance are deterministic;
- invalid/unknown geometry never produces `allowed`;
- union/difference preserves provenance of contributing constraints.

### T4.6 — Explanation integrity

- every pass/fail/unknown links rule version, edition, locator and object evidence;
- changing rule set or model changes run fingerprint;
- same inputs/config/seed reproduce byte-equivalent normalized decisions.

### T4.7 — Browser review flow

- select OSM building → shortlist → preview → accept/reject;
- open rule candidate beside source page and approve with validation;
- select planting proposal and navigate to both object and normative evidence.

## Ordered work packages

1. Write/accept constraint semantics and authorization ADRs.
2. Build OSM fixture/import and T4.1–T4.2 tests.
3. Implement candidate/review domain operations and UI.
4. Build bounded regulatory fixture and T4.3–T4.4 tests.
5. Implement rule review/publication transaction.
6. Write T4.5–T4.6 before geometry/planning implementation.
7. Implement deterministic constraint engine and one-profile proposal generator.
8. Write and pass T4.7 browser flow.
9. Produce DXF/JSON only if the canonical input fidelity gate is satisfied; otherwise report a blocked export honestly.
10. Publish Phase 4 report with screenshots, SQL/API evidence and reproducibility hashes.

## Acceptance matrix

| Requirement | Evidence |
|---|---|
| OSM click is safe and reviewable | T4.1/T4.2 |
| only approved published rules execute | T4.3 |
| first normative distances are traceable | T4.4 |
| spatial result is deterministic | T4.5/T4.6 |
| reviewer can complete flow | T4.7 |
| proposal explains every decision | decision JSON + source navigation |

## Risks and fallback

- If project CRS is unverified, OSM remains diagnostic and planning uses only verified local geometry.
- If normative edition is incomplete, rule publication is blocked; demo shows candidate review, not a false legal result.
- If plant optimization is unstable, Phase 4 ships deterministic feasible candidates without claiming optimality.

## Exit gate

At least one pilot completes `model + published test rule set → constraints → proposal → explanation` with all T4 tests passing and no unreviewed source participating in an effective `allowed` decision.
