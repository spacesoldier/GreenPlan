import { describe, expect, it } from "vitest";

import { applyAffine, viewportMatrix } from "./raster-frame-cache";
import {
  extentContains,
  expandViewport,
  fitExtent,
  panViewport,
  panViewportOnCanvas,
  rotateBearing,
  screenToCadPoint,
  viewportToCadBBox,
  zoomViewport,
  zoomViewportAtScreenPoint,
} from "./viewport";


describe("CAD viewport", () => {
  it("fits a CAD extent and flips its vertical axis", () => {
    expect(fitExtent([10, 20, 110, 70], 0.1)).toEqual({ x: 0, y: -80, width: 120, height: 70 });
  });

  it("expands a tall project to the actual wide canvas aspect", () => {
    const result = fitExtent([700, 14000, 850, 14600], 0, 1.5);
    expect(result.width / result.height).toBeCloseTo(1.5, 10);
    expect(result.x).toBeCloseTo(325, 10);
    expect(result.y).toBe(-14600);
  });

  it("zooms around the pointer anchor", () => {
    const result = zoomViewport({ x: 0, y: 0, width: 100, height: 50 }, 2, 0.25, 0.8);
    expect(result).toEqual({ x: 12.5, y: 20, width: 50, height: 25 });
  });

  it("creates a centered 1.8-frame raster overscan viewport", () => {
    expect(expandViewport({ x: 10, y: 20, width: 100, height: 50 }, 0.4))
      .toEqual({ x: -30, y: 0, width: 180, height: 90 });
  });

  it("converts a screen drag into viewBox movement", () => {
    const result = panViewport({ x: 100, y: 200, width: 1000, height: 500 }, 80, -40, 800, 400);
    expect(result).toEqual({ x: 0, y: 250, width: 1000, height: 500 });
  });

  it("keeps the CAD point under the cursor fixed in a letterboxed canvas", () => {
    const viewport = { x: 694, y: -14984, width: 182, height: 607 };
    const screen: [number, number] = [239, 131];
    const canvas: [number, number] = [544, 373];
    const cadBefore = screenToCadPoint(viewport, 0, screen[0], screen[1], canvas[0], canvas[1]);
    const result = zoomViewportAtScreenPoint(viewport, 0, 2.1, screen[0], screen[1], canvas[0], canvas[1]);
    const worldAfter = applyAffine(viewportMatrix(result, 0, ...canvas), [cadBefore[0], -cadBefore[1]]);

    expect(worldAfter[0]).toBeCloseTo(screen[0], 8);
    expect(worldAfter[1]).toBeCloseTo(screen[1], 8);
  });

  it("preserves the pointer anchor and pan delta with bearing", () => {
    const viewport = { x: 10, y: -80, width: 100, height: 50 };
    const canvas: [number, number] = [900, 500];
    const screen: [number, number] = [240, 170];
    const cadBefore = screenToCadPoint(viewport, 31, screen[0], screen[1], ...canvas);
    const zoomed = zoomViewportAtScreenPoint(viewport, 31, 2, screen[0], screen[1], ...canvas);
    const anchored = applyAffine(viewportMatrix(zoomed, 31, ...canvas), [cadBefore[0], -cadBefore[1]]);
    expect(anchored[0]).toBeCloseTo(screen[0], 8);
    expect(anchored[1]).toBeCloseTo(screen[1], 8);

    const panned = panViewportOnCanvas(viewport, 31, 75, -20, ...canvas);
    const centerWorld = screenToCadPoint(viewport, 31, canvas[0] / 2, canvas[1] / 2, ...canvas);
    const shifted = applyAffine(viewportMatrix(panned, 31, ...canvas), [centerWorld[0], -centerWorld[1]]);
    expect(shifted[0]).toBeCloseTo(canvas[0] / 2 + 75, 8);
    expect(shifted[1]).toBeCloseTo(canvas[1] / 2 - 20, 8);
  });

  it("normalizes bearing to a stable signed range", () => {
    expect(rotateBearing(170, 30)).toBe(-160);
    expect(rotateBearing(-170, -30)).toBe(160);
  });

  it("turns the visible flipped viewport back into a CAD bbox", () => {
    expect(viewportToCadBBox({ x: 10, y: -80, width: 100, height: 50 }, 0)).toEqual([10, 30, 110, 80]);
    const rotated = viewportToCadBBox({ x: 10, y: -80, width: 100, height: 50 }, 45);
    expect(rotated[0]).toBeLessThan(10);
    expect(rotated[1]).toBeLessThan(30);
    expect(rotated[2]).toBeGreaterThan(110);
    expect(rotated[3]).toBeGreaterThan(80);
  });

  it("keeps the active prefetch window while the visible bbox remains inside it", () => {
    expect(extentContains([0, 0, 100, 100], [20, 10, 80, 90])).toBe(true);
    expect(extentContains([0, 0, 100, 100], [-1, 10, 80, 90])).toBe(false);
  });
});
