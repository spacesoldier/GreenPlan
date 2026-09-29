# Phase 4, iteration 2: Knowledge library bootstrap

- Status: Planned
- Date: 2026-09-29
- Owners: platform / domain / web / CAD ingestion
- Prerequisites: ADR-0044, ADR-0045, ADR-0046

## Outcome

После запуска GreenPlan пользователь открывает на главной странице раздел «Библиотека», видит зарегистрированный СП 42 с прогрессом машинного разбора, каталог принципов генерации и карточки растений с CAD-символами из `Шаблоны значков.dwg`. Все автоматически полученные знания остаются проверяемыми кандидатами, а повторный bootstrap не создаёт дублей.

## Scope

- собрать и опубликовать Qwen-only CPU image;
- сделать profile-aware health-check runtime;
- добавить one-shot/resumable `regulatory-bootstrap` в compose;
- извлечь page-aware текст СП, сегменты и Qwen rule candidates;
- создать API и UI раздела `/library` с тремя каталогами;
- расширить PostGIS сущностями generation principles и CAD symbols;
- импортировать plant symbol library из DWG/DXF;
- показать provenance, версии, статусы и review actions.

## Out of scope

- автоматическое утверждение нормативных правил;
- публичная поставка Gemma/YandexGPT;
- полная ботаническая энциклопедия и автоматическое заполнение всех условий произрастания;
- production RBAC и электронная подпись reviewer;
- собственно генерация посадок и финальный DXF export — здесь создаются данные и контракты для следующей итерации.

## Data and API contracts

- bootstrap fingerprint: document SHA + extractor + segmenter + schema/prompt + model digest;
- `GET /library/regulations`, `/library/generation-principles`, `/library/plants` — фильтры, cursor pagination, status facets;
- detail endpoints возвращают provenance и immutable version identifiers;
- long-running ingestion/import endpoints возвращают job id; прогресс доступен через общий activity/job contract;
- model output проходит JSON Schema и domain validation до записи candidate;
- symbol identity: source asset SHA + block identity; preview является производным артефактом.

## Tests to write before implementation

1. Runtime contract: Qwen-only profile healthy, missing disabled models ignored, checksum mismatch fails build/start.
2. Regulatory unit tests: page locators, deterministic segmentation, schema rejection, fingerprint calculation.
3. Regulatory integration: empty PostGIS bootstrap, second-run no-op, resume after interruption, no candidate auto-approved.
4. Symbol parser unit tests: nested blocks, attributes, Cyrillic normalization, service-name rejection, geometry limits.
5. Symbol integration audit: known source yields 96 layers, 105 INSERT and 99 unique inserted block names; second import has no duplicates.
6. API contract tests: filters, pagination, provenance and status separation.
7. Web tests: library navigation from home, three screens, card/detail deep links, loading/error/empty states.
8. Round-trip test: reviewed symbol writes to DXF as block + INSERT and is readable by independent reader.

## Ordered work packages

### WP1 — Reproducible Qwen runtime

- add build args/named model context and SHA verification;
- copy weights before runtime code to maximize layer reuse;
- implement `LLM_ENABLED_PROFILES` and health semantics;
- generate SBOM/provenance and publish immutable tag.

### WP2 — Database migrations

- add generation principle/version tables and catalog snapshots;
- add CAD symbol library, symbol, alias and profile-link tables;
- add uniqueness constraints for bootstrap and symbol import;
- preserve existing manually seeded SP rules.

### WP3 — Regulatory bootstrap

- register PDF edition and source asset;
- implement deterministic page text extraction and segmentation;
- enqueue bounded Qwen extraction with resumable checkpoints;
- validate/store candidates and activity progress.

### WP4 — Plant symbol importer

- read block definitions, INSERT, attributes and layers;
- retain canonical local geometry and derive bounded previews;
- normalize name candidates and create review queue;
- link reviewed symbols to taxa/plant profiles.

### WP5 — Library API and UI

- add main-page Library entry;
- build three catalog routes and card/detail views;
- expose progress, provenance, review status, search and filters;
- add review actions without bypassing approval gates.

### WP6 — Release evidence

- run bootstrap/import on a clean PostGIS directory;
- capture counts, timings, model/image digests and screenshots;
- document image pull/build and offline startup;
- freeze release commit without moving `submission-2026-09-29`.

## Acceptance matrix

| Requirement | Evidence |
|---|---|
| Public stack starts without host model mount | Compose smoke test using immutable Qwen image |
| SP appears once and is searchable by page/locator | DB integration test and Library screenshot |
| Qwen result is not executable before review | API/DB constraint test |
| Repeated bootstrap is idempotent | Stable row counts and reused fingerprint |
| DWG symbols retain CAD identity | Import audit and round-trip DXF test |
| Dirty block names do not create approved taxa | Parser/review test |
| Three catalogs are reachable from home | Web navigation test |
| Published knowledge is reproducible | Snapshot/version API contract test |

## Risks and fallback

- If Qwen image cannot be pushed in time, compose supports the existing read-only host model mount and records its SHA.
- If Qwen extraction is slow on CPU, deterministic corpus registration completes first and inference resumes asynchronously.
- If a complex symbol exceeds rendering limits, raw block geometry is retained and the preview is marked `needs_review`.
- If DWG reader loses proprietary entities, ODA DXF and LibreDWG diagnostics are retained side by side; the symbol is not silently approved.

## Completion report

To be filled only after tests and clean-install verification. Presence of screens or images alone does not complete the phase.

