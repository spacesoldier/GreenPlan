# ADR-0018: DWG читается напрямую либо конвертируется только с доказательным fidelity gate

- Status: Accepted
- Date: 2026-09-27
- Owners: CAD ingestion, backend, geospatial
- Related phase: Phase 3
- Supersedes: —
- Superseded by: —

## Context

ADR-0002 выбрал ODA как основной конвертер и LibreDWG как независимый диагностический reader. Массовый прогон доказал техническую конвертируемость корпуса, но не сделал проверку сохранности обязательной частью каждой пользовательской загрузки.

На Песчаном переулке текущая веб-сцена не содержит часть дорожек, покрытий и заливок. XREF обнаружены в источниках, но не собраны в полную сцену. Пока неизвестно, где именно возникла потеря: в исходной комплектности, разрешении XREF, DWG→DXF, parser, canonical import или renderer.

Успешный exit code и непустой DXF не являются доказательством содержательной сохранности.

## Decision

### Reader-first capability routing

Каждый файл определяется по сигнатуре, а не расширению. Для DWG orchestrator сначала проверяет доступные direct readers и их capability profile.

Reader считается пригодным не потому, что открыл файл, а если он способен для данной версии и классов выдать требуемый инвентарь профиля GreenPlan:

- header/version/units/extents;
- model space и layouts/viewports;
- layers, blocks, inserts и attributes;
- XREF/underlay paths и transforms;
- entity counts по типам, включая `HATCH`;
- proxy/custom class inventory;
- диагностическую геометрию и текст для нужного профиля.

Если direct reader покрывает требуемый профиль, canonical parser может работать из его нормализованного результата без обязательного DXF. Если покрытие частичное, оно сохраняется как независимая pre-conversion диагностика, после чего запускается DWG→DXF.

### Controlled conversion fallback

Стандартная конвертация использует ODA и сохраняет исходную версию (`AC1032 → DXF AC1032` для соответствующего входа). Down-save запрещён без отдельной политики. LibreDWG не публикует итоговый DXF, но его диагностика участвует в отчёте расхождений согласно ADR-0002.

Каждый запуск фиксирует:

- source SHA-256 и detected format/version;
- converter/reader name, exact version и capability profile;
- image/binary digest и конфигурацию;
- команду без секретов, exit code, stdout/stderr и длительность;
- SHA-256 всех производных артефактов;
- причину выбора direct-read либо conversion path.

### Pre/post inventories

До конвертации строится DWG inventory доступным независимым reader. После конвертации строится DXF inventory другим parser. Сравнение выполняется по категориям, а не только по общему числу entities:

- spaces/layouts/viewports;
- layers и их visibility/style;
- blocks/inserts/attributes;
- entity types, особенно `HATCH`, paths/curves, text и dimensions;
- extents и spatial clusters;
- XREF, images и underlays;
- proxy/custom classes;
- контрольные тексты и handles там, где они стабильны.

Разница в total count сама по себе не означает потерю: конвертер может менять внутреннее представление. Однако исчезновение критического класса, слоя, зависимости или пространственного кластера требует объяснения.

### XREF is part of the input, not decoration

После инвентаризации всей delivery строится dependency graph. XREF разрешается по следующему порядку:

1. точный нормализованный относительный путь внутри delivery;
2. исходный basename при единственном совпадении;
3. content hash/известная копия того же asset;
4. ручной выбор при неоднозначности.

Case mismatch и Windows separators нормализуются, но исходный путь сохраняется. Каждая вставка хранит transform. Рекурсивные ссылки и cycles выявляются явно.

Критическая missing/ambiguous XREF не исчезает из отчёта и блокирует `accepted`, если содержит территорию, покрытия, сети, здания, ограничения или проектную растительность.

### Layout and visual evidence

Model space и каждый layout анализируются отдельно. Штамп, легенда и viewport не смешиваются с геометрией территории.

Для master-кандидатов создаются сопоставимые preview:

- raw direct-read model space;
- converted DXF model space;
- paper-space layouts;
- resolved XREF assembly;
- canonical scene/render.

Visual diff является evidence, но не заменяет структурный diff. И наоборот, совпадение счётчиков не доказывает визуальную сохранность заливок.

### Fidelity verdict

Результат получает один статус:

- `accepted` — критические зависимости разрешены, профиль сохранён, различия объяснены;
- `accepted_with_review` — сцена пригодна для ограниченного preview, но содержит явно обозначенные некритичные неизвестные;
- `rejected` — потеряна либо не прочитана информация, способная изменить планирование;
- `not_comparable` — pre-inventory недостаточен для доказательного сравнения.

Только `accepted` может автоматически стать effective canonical revision. `accepted_with_review` требует решения специалиста и остаётся preview до подтверждения. `rejected` и `not_comparable` не допускаются к расчёту посадок.

### No silent repair

Audit/repair, explode proxy, bind XREF и иные изменяющие операции выполняются только как отдельная производная ветка. Исходный результат конвертера сохраняется. UI показывает, какая операция добавила, удалила или преобразовала entities.

## Alternatives considered

### Всегда сначала конвертировать

Отклонено: теряется независимая точка сравнения, а ошибки конвертации невозможно отличить от состава исходного DWG.

### Считать ODA exit code достаточным

Отклонено: конвертер может успешно завершить операцию с proxy, отсутствующими XREF или визуально значимыми различиями.

### Требовать точного равенства entity count

Отклонено: валидное преобразование может менять внутреннее разбиение entities, не меняя содержательного результата.

### Автоматически bind/explode всё

Отклонено: это разрушает структуру происхождения, может менять семантику и затрудняет поиск этапа потери.

### Использовать только визуальное сравнение

Отклонено: похожие картинки могут скрывать потерю невидимого слоя, атрибутов, Z, XREF или объектов ограничений.

## Consequences

### Positive

- место потери локализуется по стадиям;
- дорожки, заливки и зоны нельзя молча потерять при публикации;
- direct reader и converter сравниваются независимо;
- XREF становятся частью completeness gate;
- каждый verdict воспроизводим по версиям инструментов и хешам.

### Negative / trade-offs

- загрузка проекта становится дольше и создаёт несколько артефактов;
- некоторые DWG останутся `not_comparable`, если нет достаточно полного независимого reader;
- visual diff требует CAD-render backend и контрольных настроек шрифтов/plot styles;
- критерии критичности требуют предметного review.

## Verification

- fixture с `HATCH` проходит round-trip без необъяснимого исчезновения;
- fixture с дорожкой, снеговой зоной и внешней заливкой выявляет удаление каждого класса;
- missing XREF даёт `rejected` либо обоснованный `accepted_with_review`, но не `accepted`;
- layout inventory и model inventory сохраняются раздельно;
- повторный запуск теми же inputs/tool digests даёт тот же normalized report fingerprint;
- UI показывает pre/post delta, логи и источник каждого preview;
- для Песчаного судьба выбранных дорожек и заливок прослеживается по стадиям до handle/asset.

## References

- [ADR-0002](0002-cad-conversion-chain.md)
- [DWG→DXF: сохранность и gate](../07-dwg-dxf-fidelity.md)
- [Песчаный: ручной разбор](../project-research/01-peschanaya-architect-review.md)
- [Phase 3](../dev-plan/phase-03-controlled-project-intake.md)
