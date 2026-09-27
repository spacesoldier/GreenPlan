# ADR-0007: Next.js отвечает за UI/BFF, FastAPI — за предметный API

- Status: Accepted
- Date: 2026-09-25
- Owners: web and backend
- Related phase: Phase 2
- Supersedes: —
- Superseded by: —

## Context

Web-приложению нужны project navigation, большие пространственные выборки, 2D/3D viewport, background jobs и позднее review mutations. Нельзя давать браузеру прямой доступ к PostGIS или превращать Next.js BFF во второй предметный backend.

При этом web-приложение не является единственным способом просмотра результата. Исходное ТЗ требует экспортировать итоговый DXF так, чтобы его можно было открыть в CAD: прямо назван `nanoCAD` либо иной просмотрщик под МосТех.ОС/Linux. Критерий проверки — исходные слои не повреждены, отдельный слой результата читается. `FreeCAD` в ТЗ не назван; его можно проверять как дополнительного downstream consumer, не выдавая такую совместимость за исходное требование.

## Decision

- Next.js App Router владеет application shell, SSR лёгких страниц, сессией и BFF Route Handlers.
- FastAPI является единственным владельцем domain queries/mutations, PostGIS и OpenAPI.
- Server Components обращаются к FastAPI server-to-server; интерактивный client workspace — к BFF.
- Тяжёлая геометрия передаётся bbox/LOD chunks; BFF stream-проксирует и не агрегирует весь проект.
- 2D renderer скрыт за scene adapter; исходный выбор для spike — deck.gl + MapLibre для geospatial basemap.
- 3D появится за тем же scene contract, но не входит в Phase 2 critical path.
- Browser workspace — основной интерактивный клиент, но не единственный клиент платформы.
- FastAPI/OpenAPI, версионированные scene-артефакты и опубликованные экспорты являются явными downstream contracts:
  - `DXF` — для CAD-просмотрщиков и редакторов;
  - bbox-scoped `GeoJSON`, позднее MVT/binary transport — для 2D/GIS-клиентов;
  - `glTF` с mapping стабильных object ids — для внешних 3D-клиентов.
- Обязательная DXF-совместимость проверяется в `nanoCAD` или в выбранном совместимом просмотрщике под МосТех.ОС/Linux. FreeCAD, LibreCAD и QCAD входят только в матрицу кандидатов до появления воспроизводимых результатов проверки.
- Unreal Engine может быть отдельным 3D/downstream-клиентом тех же опубликованных моделей; он не владеет доменной моделью и не становится обязательной частью серверного контура.
- Downstream viewer не получает прямой доступ к PostGIS и не изменяет approved model. Изменённый во внешнем CAD файл возвращается через intake как новый source artifact/revision, а не перезаписывает опубликованный результат.

## Alternatives considered

### Только Next.js с прямым SQL

Отклонено: смешивает UI, auth proxy и domain transactions, усложняет Python geometry/ingestion stack.

### Browser → FastAPI напрямую

Возможно позднее для signed tile endpoints, но усложняет session/cookie boundary первой версии.

### Один встроенный viewer как единственный поддерживаемый клиент

Отклонено: ТЗ требует переносимый DXF, а инженерные, GIS- и презентационные сценарии используют разные инструменты. Доменное ядро не должно зависеть от конкретного renderer.

### Unreal Engine как основной клиент

Не выбран для инженерного MVP: тяжелее доставка, review/workspace UI и deployment. Unreal остаётся возможным downstream viewer.

## Consequences

### Positive

- чёткие границы auth/domain/render;
- OpenAPI и версионированные артефакты допускают разные web, CAD, GIS и 3D-клиенты;
- scene transport можно оптимизировать независимо.

### Negative / trade-offs

- два web runtime и дополнительный hop через BFF;
- нужно следить за DTO drift;
- streaming и отмена запросов требуют явного тестирования;
- совместимость нельзя объявлять по названию формата: нужна versioned viewer matrix с приложением, версией, ОС, тестовым артефактом и результатом;
- внешний CAD round trip потенциально меняет handles, типы сущностей и metadata, поэтому считается новым импортом.

## Verification

- browser bundle не содержит DB credentials/internal FastAPI URL;
- Next.js не импортирует database driver domain layer;
- FastAPI OpenAPI проходит schema test;
- запрос feature без bbox/малого scope отклоняется;
- selection/deep link воспроизводится из URL;
- golden DXF открывается хотя бы в одном предусмотренном ТЗ CAD-viewer; исходные слои доступны, а отдельный `GREEN_AI_*` слой результата читается и независимо переключается;
- для каждого заявленного viewer фиксируются точная версия, ОС, hash DXF, предупреждения и найденные расхождения;
- glTF/GeoJSON consumer сохраняет связь с canonical object ids;
- изменения из внешнего CAD не могут обойти intake, provenance и создание новой revision.

## References

- [Web application brief](../13-web-application-design-brief.md)
- [Optional nanoCAD .NET client concept](../16-nanocad-client-concept.md)
- [Phase 2 plan](../dev-plan/phase-02-readonly-vertical-slice.md)
- Исходное ТЗ, разделы 2.2, 4 и 6: `3. Департамент природопользования и охраны окружающей среды.pdf`

## Follow-up note — 2026-09-25

Возможен отдельный тонкий клиент GreenPlan внутри nanoCAD на C#/.NET API. Он использует тот же FastAPI/OpenAPI, создаёт и обновляет `GREEN_AI_*`, показывает объекты и объяснения в CAD, но не получает прямой доступ к PostGIS и не переносит предметную логику в плагин. Решение о разработке принимается отдельным ADR после SDK/license/МосТех.ОС spike.
