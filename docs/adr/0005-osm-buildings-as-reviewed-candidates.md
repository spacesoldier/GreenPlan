# ADR-0005: OSM-здания входят в проект только через review candidates

- Status: Accepted
- Date: 2026-09-25
- Owners: geodata and review workflow
- Related phase: Phase 1, Phase 4
- Supersedes: —
- Superseded by: —

## Context

В CAD часто отсутствуют контуры зданий, а OSM даёт удобный офлайн-контекст. Однако его полнота, дата и точность различаются; outline и building parts могут дублировать друг друга, а локальная CAD CRS может не иметь доказанного преобразования к WGS 84.

## Decision

- OSM импортируется как versioned external dataset из PBF, не как публичные raster tiles.
- Клик `Добавить в рассмотрение` создаёт `provenance.object_candidates`, а не canonical building.
- Candidate хранит snapshot feature, target class, transform, proposed geometry и match metrics.
- До review разрешён только явно маркированный constraint preview.
- Acceptance создаёт/связывает объект в новой draft model; effective constraint появляется после approval модели.
- При неизвестном назначении, состоянии или transform результат — `needs_review`, не `allowed`.

## Alternatives considered

### Автоматически копировать все OSM buildings

Отклонено из-за ложной точности, временных конфликтов и дубликатов с CAD.

### Использовать OSM только как картинку

Отклонено: нельзя адресовать feature, хранить evidence и рассчитывать проверяемые ограничения.

## Consequences

### Positive

- пользователь может дополнять контекст кликом;
- provenance и ODbL attribution сохраняются;
- safety-critical расчёт не зависит от неподтверждённого фона.

### Negative / trade-offs

- требуется review UI и conflation;
- OSM snapshot/tiles/feature API нужно обслуживать локально;
- candidate и canonical object имеют разные lifecycle.

## Verification

- уникальность candidate на `(model, external feature, target class)`;
- acceptance требует reviewer и canonical object;
- approved model не меняется при клике;
- preview/effective constraints возвращаются разными статусами;
- snapshot replacement помечает необработанные candidates stale.

## References

- [OSM offline buildings](../11-osm-offline-buildings.md)
- [OSM review UX/API](../14-osm-building-review.md)
- [Migration 005](../../platform/db/postgis-init/005_osm_review_and_rule_ingestion.sql)
