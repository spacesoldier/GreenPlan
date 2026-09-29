# Phase 3, iteration 8 — Root-scoped viewer и исправление категорий по геометрии

- Status: Verification
- Date: 2026-09-29
- Owners: backend, frontend, CAD ingestion

## Outcome

Инженер открывает один верхнеуровневый чертёж из структурированного списка, видит только его
геометрию и XREF closure, управляет слоями слева и исправляет категорию слоя во время визуальной
проверки. Большие корни переключаются без смешивания старого и нового кадра.

## Accepted ADR prerequisites

- [ADR-0047](../adr/0047-root-scoped-cad-viewer-workspace.md);
- ADR-0004, ADR-0009, ADR-0010, ADR-0019, ADR-0020, ADR-0041 и ADR-0042.

## Scope

- root catalog и root-scoped extent/counts/issues/features;
- grouped selector с URL state;
- дерево root/XREF/layers и visibility;
- повторное назначение класса через review API и republish marker;
- root-aware tile/frame identity и stale-request protection;
- legacy fallback без publication root manifest.

Вне scope: compare двух roots, мутация canonical snapshot, полный occurrence provenance старых моделей,
3D renderer и виртуализация десятков тысяч строк.

## Data and API contracts

`GET /v1/models/{model_id}/scene-manifest?root_id={asset_uuid}` возвращает roots, `active_root_id`,
closure sources и слои активного корня. `GET /features?...&root_id=...` применяет тот же scope.
Leaf содержит source classification identity только при доказуемом сопоставлении.

## Tests written before implementation

1. default предпочитает `effective_design`;
2. manifest/features фильтруются по root;
3. неизвестный root даёт typed 404;
4. selector стабильно группируется;
5. XREF-prefixed слой получает source group;
6. root входит в tile key;
7. review показывает republish state;
8. legacy manifest совместим.

## Ordered work packages

1. Зафиксировать ADR и phase plan.
2. Добавить backend contracts и root-scoped queries.
3. Добавить API tests default/filter/invalid root.
4. Добавить frontend projection helpers и tests.
5. Перестроить topbar и левое дерево.
6. Подключить visibility, category correction и republish marker.
7. Сделать request/frame generation root-aware.
8. Прогнать API/web tests, typecheck и production build.
9. Проверить реальный multi-root проект и заполнить completion report.

## Acceptance matrix

| Требование | Доказательство |
|---|---|
| Нет смеси поставки | root-filter API test + screenshot |
| Понятно, какой файл открыт | grouped selector + URL reload |
| Видны XREF-источники | source tree fixture + UI inspection |
| Категорию можно исправить | review API + republish marker |
| Старый ответ не мелькает | generation/cache unit test |
| Не грузится вся поставка | network evidence одного root/bbox |

## Risks and fallback

Если source слоя не восстановлен, visibility остаётся, а editor отключается с объяснением. Модель без
root manifest работает в legacy mode. Root manifest кэшируется по `(model_id, root_id)`.

## Completion report

Реализован root-scoped vertical slice. Проверка 2026-09-29:

- `apps/api/.venv/bin/pytest -q`: 79 passed;
- `npm test`: 65 passed;
- `npm run typecheck`: passed;
- `npm run build`: Next.js production build passed;
- live model `11f9176d-24df-4798-92b8-2a4b9f4870e0`: 10 roots; default root
  `212fa834-e421-4046-bb40-2047fb4d04f3` содержит 227720 объектов и 161 scene layer вместо
  aggregate 1744053 объектов;
- live feature query на focus bbox вернул только выбранный `publication_root_id`.

До перевода в Complete остаётся визуальная приёмка пользователем и smoke-test записи новой категории
на выбранном слое с последующей повторной публикацией.
