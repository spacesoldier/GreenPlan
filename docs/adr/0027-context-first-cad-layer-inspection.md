# ADR-0027 — Контекстный разбор CAD-слоёв до обучения модели

- Status: Accepted
- Date: 2026-09-28
- Owners: CAD ingestion, ML, frontend
- Related phase: Phase 3, iteration 2
- Supersedes: —
- Superseded by: —

## Context

Имя слоя само по себе недостаточно для предметной классификации. `Деревья` может обозначать
существующие насаждения, проектную посадку, условные обозначения или текст легенды. Слои
`0`, `Defpoints`, `point02` и подрядческие сокращения не несут понятного смысла без состава
примитивов, документа, Model/Paper Space, блоков и подписей.

В пилоте «Старый Гай» rules-v2 создал 414 layer suggestions; 259 остались `unknown` со средней
уверенностью 0,25. Laya не была запущена: assistant run зафиксирован с provider `rules-v2`, а
`LAYA_URL` не настроен. Поэтому существующие подсказки нельзя считать результатом нейросети.

## Decision

До fine-tuning строится проверяемый context-first dataset и рабочий layer inspector. Для каждого
слоя UI показывает исходный документ, entity count, histogram entity types и независимые оси:

- domain;
- lifecycle;
- representation;
- object class;
- document role.

Model Space и Paper Space показываются отдельным списком с количеством собственных entities.
Это не означает, что layout содержит копию модели: viewport и его layer visibility должны стать
отдельными сущностями следующего шага.

Rule results остаются baseline. Инженерские accept/reject записываются как review evidence.
Laya подключается сначала как challenger только для `unknown/mixed`, без автоматического изменения
effective mapping. Для русского текста рассматривается multilingual checkpoint, но его качество
измеряется на нашей gold-разметке.

Fine-tuning запрещён до накопления versioned набора с разделением по проектам/подрядчикам и
отложенного test set. Иначе модель запомнит имена слоёв одного подрядчика и метрика окажется
ложно высокой.

## Consequences

- текущая эвристика становится видимой и проверяемой, а не мелкой строкой без контекста;
- Model и печатные листы больше не смешиваются концептуально;
- появляется корпус инженерских решений для benchmark и будущего обучения;
- пока не извлекаются viewport layer states, stamp blocks, legend samples и per-layout usage;
- Laya не объявляется источником классификации, пока provider run этого не подтверждает.

## Verification

- API возвращает layers, spaces, source paths, entity histograms и axes;
- UI фильтрует слои по документу, имени и review state;
- Model и layouts видны раздельно;
- accept/reject обращается к конкретному suggestion ID;
- provider/version отображаются в run и сохраняются с suggestion;
- benchmark делит train/test по проектам, а не случайным строкам слоёв.
