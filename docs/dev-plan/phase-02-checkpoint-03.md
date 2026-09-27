# Phase 2 — checkpoint 03: interactive CAD viewport

- Status: Verified checkpoint; Phase 2 remains In progress
- Date: 2026-09-25

## Delivered

- wheel zoom anchored at the pointer position;
- left-button drag pan;
- `Shift + drag` or right-button drag bearing rotation;
- `+`, `−`, rotate and fit-to-extent controls;
- current zoom percentage and bearing indicator;
- live CAD-local cursor coordinates;
- zoom limits from 25% to 4,000% of the fitted extent;
- drag suppression so releasing over a feature does not accidentally select it;
- reset of viewport and bearing when the project changes.

True camera pitch is intentionally not emulated in the SVG renderer. In 2D the supported orientation operation is bearing rotation. Pitch/tilt belongs to a future 3D renderer and must share project/object selection with this viewport.

## Test-first evidence

`lib/viewport.test.ts` was added before `lib/viewport.ts`; its first run failed because the implementation module did not exist. The completed suite verifies:

1. CAD extent fitting and Y-axis inversion;
2. zoom around an arbitrary pointer anchor;
3. conversion of screen drag into viewBox displacement;
4. stable bearing normalization.

```text
apps/web: 7 tests passed
TypeScript --noEmit: passed
Next.js production Docker build: passed
```

## Browser interaction evidence

Chrome DevTools Protocol dispatched actual wheel and pointer events against the running Compose application:

```text
initial: 100%, bearing 0 degrees
wheel zoom: 182%, viewBox width 3349.07 -> 1838.01
drag pan: viewBox origin changed, width remained 1838.01
Shift-drag rotate: bearing 0 -> 21 degrees
```

This checkpoint does not yet implement viewport-driven bbox paging. The initial bounded feature collection remains in memory while the user navigates it.
