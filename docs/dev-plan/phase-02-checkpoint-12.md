# Phase 2 — checkpoint 12: canvas-aspect viewport и атомарная смена tile frame

- Status: Complete
- Date: 2026-09-27
- Decisions: [ADR-0009](../adr/0009-viewport-virtualization-and-canvas-rendering.md), [ADR-0010](../adr/0010-coherent-spatial-tile-cache.md), [ADR-0011](../adr/0011-interaction-raster-frame-cache.md)

## Symptom

При pan старые растения исчезали, одновременно появлялись новые. При zoom растения пропадали прежде всего у левого и правого краёв Canvas. Увеличение spatial/raster overscan уменьшило частоту эффекта, но не устранило его.

## Root causes

### Logical viewport did not match Canvas aspect

`fitExtent` сохранял узкие пропорции вертикальной улицы, а Canvas был широким. Renderer использовал centered aspect-fit и фактически показывал дополнительную world area по бокам. При этом API bbox и renderer culling продолжали считать видимой только узкую логическую область.

Следствие: geometry могла находиться на экране, но быть исключена culling как якобы невидимая. При движении и zoom граница этой ложной центральной полосы пересекала растения.

### Partial replacement of an established frame

После изменения tile window frontend публиковал `readyFeatures` после каждого отдельного tile, если LOD не менялся. Новый неполный набор заменял прежний полный кадр:

```text
old complete frame -> first new tile only -> more new tiles -> complete frame
```

Именно поэтому часть старых объектов исчезала одновременно с появлением новых.

## Fix

1. `ResizeObserver` сообщает фактический размер CAD Canvas в workspace.
2. `fitExtent(..., canvasAspect)` расширяет короткую ось и создаёт viewport с тем же aspect ratio, что и Canvas.
3. API bbox, culling, pan, zoom, raster reprojection и screen/CAD coordinates теперь описывают одну видимую world area.
4. Partial tile commit разрешён только до первого полного кадра.
5. После появления установленного frame любой следующий window/LOD публикуется только при `allReady(tiles)`.
6. Пока новый frame собирается, пользователь продолжает видеть coherent предыдущий raster frame.

## Browser acceptance

Песчаный, production build, wheel anchor на группе растений:

| Zoom | Composed features | Result |
|---:|---:|---|
| 100% | 4 839 | полный overview |
| 212% | 4 551 | растения остаются у краёв |
| 448% | 2 279 | positions/crowns сохраняются |
| 949% | 2 279 | detail LOD опубликован целиком |
| 2 009% | 600 | отдельные растения и кроны видны по всей ширине |

Pan на 160 CSS pixels:

```text
new feature requests:       0
raster blits:               19
double-rAF after release:   19 ms
composed features:          4 839
```

## Automated verification

```text
Web: 6 files, 34 tests passed
TypeScript typecheck: passed
Next.js production Docker build: passed
Web container running on port 38101
```

Новые tests фиксируют:

- расширение tall extent до фактического canvas aspect;
- запрет partial commit после первого complete frame;
- разрешение progressive partial commit только при первоначальной загрузке.

## Exit gate

| Requirement | Evidence | Status |
|---|---|---|
| Canvas и logical viewport имеют один aspect | unit test + ResizeObserver | Passed |
| Edge geometry входит в bbox/culling | zoom sequence 100–2009% | Passed |
| Установленный frame не заменяется partial tiles | tile commit contract test | Passed |
| Pan не меняет растения партиями | 160 px browser acceptance | Passed |
| Production regression | 34 tests, typecheck, Docker build | Passed |
