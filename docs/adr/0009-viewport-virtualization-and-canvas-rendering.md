# ADR-0009: Виртуализировать CAD viewport и рисовать через Canvas

- Status: Accepted
- Date: 2026-09-25
- Owners: frontend and spatial API
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

Полный поддерживаемый импорт двух пилотов содержит 223,493 геометрии. SVG proof создавал отдельный DOM-узел на объект и поэтому был ограничен серверной выборкой. Увеличение SVG приводило бы к дорогим layout, hit testing и обновлениям React. Однократная выборка полного extent также не позволяет догружать детали при pan/zoom.

Пользователь должен видеть все объекты текущего поля зрения, а не случайную выборку. Навигация не должна блокировать UI, и небольшое продолжение движения желательно подготавливать заранее.

## Decision

- Основной 2D CAD renderer переходит с SVG feature nodes на HTML Canvas 2D.
- React владеет viewport и данными сцены, но не создаёт React/DOM-элемент на каждую геометрию.
- Spatial API возвращает bbox-выборку страницами с детерминированным порядком.
- Клиент продолжает запрос страниц до исчерпания bbox и постепенно перерисовывает результат.
- При изменении viewport незавершённая цепочка запросов отменяется через `AbortController`.
- Запрашиваемый bbox шире видимого; его центр смещается в сторону последнего pan. Это создаёт упреждающий cache window.
- Renderer проверяет пересечение feature bbox с видимым viewport и не рисует объекты только из prefetch-поля.
- Picking выполняется отдельным offscreen color pass: цвет пикселя однозначно отображается в canonical object id.
- Overview использует LOD-упрощение геометрии, но не семплирование объектов. Все объекты видимого bbox проходят через страницы.
- GeoJSON pagination является промежуточным Phase 2 transport. При подтверждённом bottleneck она заменяется MVT/binary tiles без смены scene adapter и UI contract.

## Alternatives considered

### Оставить SVG и скрывать элементы CSS

Отклонено: скрытый DOM-узел продолжает расходовать память и участвовать в reconciliation; десятки тысяч объектов остаются неприемлемыми.

### Загружать весь проект и фильтровать только в браузере

Отклонено: переносит сотни тысяч геометрий и provenance независимо от viewport, ухудшает первый кадр и память.

### Немедленно перейти на deck.gl/MapLibre MVT

Это целевая GIS-архитектура ADR-0007, но сейчас CRS пилотов остаётся `cad_local/candidate`. Canvas сохраняет scene contract и быстрее доказывает корректные culling, paging и picking. MVT остаётся следующим transport/render spike.

### WebGL renderer собственной разработки

Не выбран: потребует triangulation, buffer lifecycle и GPU picking до проверки семантики данных. Canvas достаточен для текущих линейных CAD-примитивов.

## Consequences

### Positive

- число объектов не равно числу DOM-узлов;
- видимый bbox может быть отрисован целиком;
- pan/zoom отменяет устаревшую работу;
- prefetch уменьшает пустые кадры на продолжении движения;
- object picking сохраняется;
- renderer можно позднее заменить на deck.gl/MVT за scene adapter.

### Negative / trade-offs

- Canvas не предоставляет accessibility node на каждый объект;
- picking buffer и основной pass должны использовать одинаковую трансформацию;
- пагинация GeoJSON создаёт несколько HTTP-запросов и временно дублирует геометрию в памяти;
- сложные CAD styles, текст и hatch пока отображаются упрощённо;
- overview всего проекта всё ещё может быть тяжёлым и требует метрик до выбора MVT.

## Verification

- API contract test доказывает отсутствие пропусков и повторов между страницами;
- viewport unit test доказывает видимый и упреждающий bbox по направлению pan;
- browser test двигает viewport до завершения загрузки и доказывает отмену старой цепочки;
- число Canvas DOM-элементов постоянно при росте feature count;
- проверка на Песчаном отрисовывает все объекты тестового bbox, включая объекты после первой серверной страницы;
- color picking возвращает canonical object id;
- pan/zoom остаётся отзывчивым на целевом объёме; измерения фиксируются в checkpoint report.

## References

- [ADR-0007](0007-web-application-boundaries.md)
- [Phase 2 plan](../dev-plan/phase-02-readonly-vertical-slice.md)
- [Checkpoint 04](../dev-plan/phase-02-checkpoint-04.md)
- [Viewport virtualization work package](../dev-plan/phase-02-viewport-virtualization.md)
