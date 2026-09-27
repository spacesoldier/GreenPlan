import { describe, expect, it } from "vitest";

import {
  RasterFrameCache,
  applyAffine,
  rasterReprojectionMatrix,
  rasterStyleKey,
  viewportMatrix,
} from "./raster-frame-cache";

function expectPointClose(actual: [number, number], expected: [number, number]) {
  expect(actual[0]).toBeCloseTo(expected[0], 8);
  expect(actual[1]).toBeCloseTo(expected[1], 8);
}

describe("raster frame transforms", () => {
  it("produces identity reprojection for the same viewport", () => {
    const viewport = { x: 10, y: -80, width: 100, height: 50 };
    const matrix = rasterReprojectionMatrix(viewport, 12, 800, 500, viewport, 12, 800, 500);
    expectPointClose(applyAffine(matrix, [123, 234]), [123, 234]);
  });

  it("matches a direct target transform for pan and zoom", () => {
    const source = { x: 0, y: -100, width: 200, height: 100 };
    const target = { x: 40, y: -80, width: 80, height: 40 };
    const world: [number, number] = [75, -55];
    const sourcePoint = applyAffine(viewportMatrix(source, 0, 900, 500), world);
    const expected = applyAffine(viewportMatrix(target, 0, 900, 500), world);
    const reprojection = rasterReprojectionMatrix(source, 0, 900, 500, target, 0, 900, 500);
    expectPointClose(applyAffine(reprojection, sourcePoint), expected);
  });

  it("matches a direct target transform when bearing changes", () => {
    const source = { x: 0, y: -100, width: 200, height: 100 };
    const target = { x: 10, y: -90, width: 150, height: 75 };
    const world: [number, number] = [125, -30];
    const sourcePoint = applyAffine(viewportMatrix(source, -20, 700, 500), world);
    const expected = applyAffine(viewportMatrix(target, 35, 700, 500), world);
    const reprojection = rasterReprojectionMatrix(source, -20, 700, 500, target, 35, 700, 500);
    expectPointClose(applyAffine(reprojection, sourcePoint), expected);
  });
});

describe("raster frame LRU", () => {
  it("evicts least-recently-used frames to stay inside its byte budget", () => {
    const cache = new RasterFrameCache<{ byteSize: number; value: string }>(100);
    cache.set("first", { byteSize: 40, value: "first" });
    cache.set("second", { byteSize: 40, value: "second" });
    cache.get("first");
    cache.set("third", { byteSize: 40, value: "third" });
    expect(cache.get("first")?.value).toBe("first");
    expect(cache.get("second")).toBeUndefined();
    expect(cache.get("third")?.value).toBe("third");
    expect(cache.byteSize).toBeLessThanOrEqual(100);
  });

  it("separates layer and selection style revisions", () => {
    const layers = new Set(["trees", "buildings"]);
    expect(rasterStyleKey("frame-1", layers, "tree-1"))
      .toBe("frame-1|buildings,trees|tree-1");
    expect(rasterStyleKey("frame-1", layers, "tree-2"))
      .not.toBe(rasterStyleKey("frame-1", layers, "tree-1"));
  });
});
