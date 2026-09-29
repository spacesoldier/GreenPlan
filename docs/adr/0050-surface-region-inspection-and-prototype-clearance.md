# ADR-0050: Инспектор найденного контура и прототипная зона посадок

- Status: Accepted
- Date: 2026-09-30
- Owners: domain / geospatial / API / web
- Related phase: Phase 4, iteration 5
- Extends: ADR-0049

## Context

Seed-инструмент ADR-0049 уже находит готовый либо восстановленный контур газона. Сам полигон недостаточен: внутри него проходят дорожки, бордюры, существующие деревья, сооружения и инженерные сети. В частности, класс или слой с названием «границы улицы» может содержать внутреннюю тропиночную сеть. До генерации посадок инженер должен увидеть состав пересечений и подтвердить найденную область.

Координатная система пилота остаётся `cad_local/candidate`. Поэтому нормативные метры нельзя незаметно выдавать за доказанный расчёт.

## Decision

После обнаружения контура система автоматически строит root-scoped spatial inventory всех пересекающих его canonical objects. Ответ содержит общее количество, группировку по классам, ограниченную выборку объектов, признак подземной сети и признак участия в прототипном вычитании. Ограничение размера ответа не меняет полный count.

При выбранном контуре правая панель переключается из object inspector в surface-region inspector. Она показывает площадь, способ получения, confidence, пересечения и три действия: сбросить preview, сохранить кандидат, вычислить прототипную зону посадок.

Сохранение создаёт отдельную запись `planning.surface_regions` со статусом `candidate`, геометрией, publication root, source object, fingerprint и assumptions. Исходные CAD-объекты не изменяются. Повторное сохранение того же fingerprint идемпотентно.

Прототипная зона строится как:

`prototype_feasible = detected_region - union(buffer(eligible_surface_obstacles, 0.5 CAD units))`.

В препятствия входят наземные `transport.*`, `structure.*`, подходящие `surface.*`, `terrain.*`, а также существующие деревья/кустарники. `utility.*` показываются в inventory, но пока не вычитаются: позднее для дерева, кустарника и газона применяются разные правила СП. `annotation.*`, исходный полигон газона и прочая непредметная графика не становятся препятствием.

Число 0,5 является только прототипным параметром. Пока unit/CRS не подтверждены, UI обязан писать «0,5 CAD-единицы; предполагается метр» и возвращать `needs_review`. Результат не называется нормативно допустимым.

## API contracts

- `POST /v1/models/{model_id}/surface-regions:detect` возвращает contour, source object и intersection inventory.
- `POST /v1/models/{model_id}/surface-regions` идемпотентно сохраняет candidate.
- `POST /v1/models/{model_id}/planting-zones:preview` возвращает prototype feasible polygon, площади до/после, obstacle count и assumptions.

## Consequences

- Тропинки и внутренние контуры становятся видимыми до генерации посадок.
- Подземные сети не теряются, но и не применяются преждевременно одинаково ко всем растениям.
- Candidate сохраняется независимо от неизменяемой CAD-модели.
- Следующий нормативный виток заменит единый prototype buffer на отдельные tree/shrub/grass overlays по approved rules.

## Verification

- inventory учитывает только выбранный model/root и исключает source object контура;
- utility присутствует в inventory с `underground=true`, но не участвует в prototype buffer;
- пешеходная дорожка и существующее дерево уменьшают prototype feasible area;
- повторное сохранение возвращает ту же candidate запись;
- UI показывает contour inspector и отдельный feasible overlay;
- unknown CAD unit всегда сопровождается assumption и `needs_review`.
