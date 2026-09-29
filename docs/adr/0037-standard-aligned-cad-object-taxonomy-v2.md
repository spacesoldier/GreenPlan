# ADR-0037 — Нормативно согласованная CAD object taxonomy v2

- Status: Accepted
- Date: 2026-09-29
- Owners: CAD domain, architecture domain, backend, frontend, ML
- Supersedes in part: ADR-0022 taxonomy `cad-v1`
- Related: ADR-0020, ADR-0022, ADR-0027, ADR-0032, ADR-0036

## Context

Текущий выбор категорий смешивает назначение слоя, жизненный цикл, изображение и физический объект:
`vegetation.existing`, `vegetation.proposed`, `surface.lawn`, `transport.road`, `utility.unknown`.
Такие метки удобны для первого просмотра, но недостаточны для таблицы 9.1: правило различает край
тротуара, край проезжей части, трамвайное полотно, подпорную стенку, тип сети и вид посадки.

## Decision

### Независимые оси

- `object_class` — физический/нормативный класс объекта;
- `lifecycle` — existing, proposed, demolition, replacement, reference, unknown;
- `representation` — point, centerline, footprint, edge, crown, hatch, text и т. п.;
- `document_role` — обследование, генплан, дендроплан, подоснова, XREF, лист;
- `domain` — навигационная группа, не исполняемая категория.

`vegetation.tree` остаётся деревом независимо от того, существующее оно или проектируемое. Крона и
ствол — representations одного объекта, а не разные растения.

### Закрытый object class vocabulary

Taxonomy `cad-v2-sp42` содержит только зарегистрированные коды. Основные листья:

- `vegetation.tree`, `vegetation.shrub`, `vegetation.grass`, `vegetation.mixed`;
- `structure.building`, `structure.wall.external`, `structure.support`,
  `structure.retaining_wall`;
- `transport.road.carriageway`, `transport.road.edge`, `transport.road.curb`,
  `transport.pedestrian.path_edge`, `transport.tram.track_edge`, `transport.cycleway.edge`,
  `transport.ditch.edge`;
- `utility.gas.pipeline`, `utility.sewer.pipeline`, `utility.heat.pipeline`,
  `utility.water.pipeline`, `utility.drainage.pipeline`, `utility.power.cable`,
  `utility.power.overhead`, `utility.telecom.cable`;
- `terrain.slope_toe`, `terrain.groundwater_level`, `terrain`;
- `territory.work_boundary`, `territory.visibility_zone`,
  `territory.metro_technical_zone`, `territory.sanitary_protection_zone`,
  `territory.utility_protection_zone`;
- `not_applicable`, `unknown` только для intake classification, не для канонической геометрии.

Широкие parent-классы и исторический `utility.unknown` не предлагаются для нового назначения: если
точный leaf class неизвестен, слой остаётся `unknown` до review. UI получает список из активной taxonomy, а не поддерживает собственный
произвольный набор.

### Migration

- `cad-v1` переводится в `retired`, `cad-v2-sp42` становится единственной active taxonomy;
- `surface.lawn` больше не назначается новым слоям; его замена — `vegetation.grass` + lifecycle;
- существующие подтверждённые значения не переписываются молча, а помечаются для remap/review;
- deterministic rules и LLM получают один и тот же allowlist v2;
- неизвестная инженерная сеть остаётся `utility.unknown` и не наследует минимальное расстояние
  конкретного типа без review.

## Consequences

- правила СП однозначно связываются со слоями и объектами;
- существующее/проектируемое больше не дублирует class tree;
- список длиннее, зато broad category не притворяется достаточной для расчёта;
- frontend и model signatures должны получать taxonomy из API в следующей итерации; до этого их
  статические списки покрываются contract tests.

## Verification

- в БД ровно одна active taxonomy и это `cad-v2-sp42`;
- каждый v2 object class, кроме `unknown/not_applicable`, разрешается в `geo.object_classes`;
- drainage не классифицируется как sewer, sidewalk — как generic road, lawn — как surface;
- lifecycle не зашит в новый vegetation object class;
- UI не предлагает retired `surface.lawn` и `vegetation.existing/proposed`.
