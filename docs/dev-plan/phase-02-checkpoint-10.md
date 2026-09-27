# Phase 2 — checkpoint 10: корректный zoom anchor при letterboxing

- Status: Complete
- Date: 2026-09-26
- Decision: [ADR-0011](../adr/0011-interaction-raster-frame-cache.md)

## Symptom

При увеличении узкого вертикального проекта растения исчезали, а после zoom out возвращались. API и LOD-геометрия оставались целыми, но визуально это выглядело как потеря объектов.

## Root cause

Canvas сохраняет пропорции CAD viewport и для Песчаного имеет большие горизонтальные поля. Wheel anchor вычислялся как простая доля всей ширины DOM Canvas:

```text
(pointerX - canvas.left) / canvas.width
```

Renderer при этом использовал uniform scale и centered aspect-fit offset. Поэтому экранная точка под курсором и вычисленная CAD-точка не совпадали. Каждый zoom сдвигал viewport в сторону; растения уходили за видимую область, хотя продолжали существовать в API и tile cache.

Та же ошибка влияла на:

- отображаемые координаты курсора;
- скорость горизонтального pan;
- zoom при ненулевом bearing.

## Fix

Все screen/CAD conversions теперь используют одну affine-матрицу с renderer и её inverse:

- `screenToCadPoint` переводит pixel coordinate в CAD XY с учётом aspect-fit и bearing;
- `zoomViewportAtScreenPoint` решает новое положение viewport так, чтобы исходная world point осталась под тем же экранным pixel;
- `panViewportOnCanvas` сохраняет world point и сдвигает её ровно на pointer delta;
- wheel, coordinate readout и drag используют эти функции вместо независимых приближённых формул.

## Verification

Automated tests проверяют:

- zoom anchor на letterboxed viewport;
- zoom anchor при bearing 31°;
- pan delta при bearing 31°;
- существующие viewport, raster cache и rendering contracts.

Browser acceptance на Песчаном выполнен с wheel anchor непосредственно над группой растений:

| Zoom | Composed cache features | Visual result |
|---:|---:|---|
| 100% | 4 838 | группа видна |
| 212% | 4 364 | та же группа остаётся под курсором |
| 448% | 1 891 | видны отдельные растения |
| 949% | 1 891 | видны позиционные круги и кроны |
| 2 009% | 170 | детальные круги и контуры остаются в кадре |

Уменьшение composed feature count при zoom является ожидаемым spatial culling: меньший bbox содержит меньше объектов. Проверяемые объекты внутри bbox больше не исчезают из-за ложного сдвига камеры.

## Regression gates

```text
Web: 6 files, 31 tests passed
TypeScript typecheck: passed
Next.js production build: passed
Web container rebuilt and running on port 38101
```

## Exit gate

| Requirement | Evidence | Status |
|---|---|---|
| World point остаётся под wheel pointer | affine unit tests и browser zoom sequence | Passed |
| Letterboxing учитывается | tall Peschany viewport at 100–2009% | Passed |
| Bearing учитывается | zoom/pan tests at 31° | Passed |
| Position circles/crowns не пропадают | visual acceptance at 949% and 2009% | Passed |
| Production build | Next.js build and deployed container | Passed |
