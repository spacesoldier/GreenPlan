import { describe, expect, it, vi } from "vitest";

import type { Feature } from "./contracts";
import {
  FeatureTileCache,
  canCommitTileFrame,
  sortFeaturesForRender,
  tileCoverage,
  tilesForBBox,
  type FeatureTile,
} from "./feature-tile-cache";

function feature(id: string, role = "other", geometryType = "LineString"): Feature {
  return {
    id,
    stable_key: id,
    class_code: role === "other" ? "unknown.constraint" : "vegetation.existing",
    layer_id: "cad-layer",
    name: null,
    lifecycle: "existing",
    semantic_status: "inferred",
    confidence: 0.7,
    geometry_role: role,
    geometry: geometryType === "Point"
      ? { type: "Point", coordinates: [5, 5] }
      : { type: "LineString", coordinates: [[0, 0], [10, 10]] },
    properties: {},
  };
}

const tile = (key: string): FeatureTile => ({ key, lod: 2, bbox: [0, 0, 10, 10] });

describe("coherent feature tile cache", () => {
  it("publishes partial tiles only before the first complete frame", () => {
    expect(canCommitTileFrame(null, false)).toBe(true);
    expect(canCommitTileFrame(2, false)).toBe(false);
    expect(canCommitTileFrame(2, true)).toBe(true);
  });

  it("uses stable project-relative tile keys for the same area", () => {
    const first = tilesForBBox("model-1", 7, [21, 21, 24, 24], [0, 0, 100, 100], 2);
    const second = tilesForBBox("model-1", 7, [22, 22, 23, 23], [0, 0, 100, 100], 2);
    expect(first.map((item) => item.key)).toEqual(second.map((item) => item.key));
    expect(first.every((item) => item.key.startsWith("model-1/7/2/"))).toBe(true);
  });

  it("keeps a two-frame detailed window to a bounded tile count", () => {
    const focus: [number, number, number, number] = [700, 14_400, 860, 15_000];
    const tiles = tilesForBBox(
      "model-1", 7, [690, 14_700, 880, 14_850], [-1000, 13_000, 2200, 16_000], 0, focus,
    );
    expect(tiles.length).toBeLessThanOrEqual(100);
  });

  it("uses the persisted focus as grid origin and scale without clipping remote material", () => {
    const documentExtent: [number, number, number, number] = [-1000, -1000, 3000, 3000];
    const focusExtent: [number, number, number, number] = [100, 100, 300, 500];
    const focus = tilesForBBox("model-1", 7, [110, 120, 140, 140], documentExtent, 3, focusExtent);
    const remote = tilesForBBox("model-1", 7, [-900, -900, -800, -800], documentExtent, 3, focusExtent);

    expect(focus.map((item) => item.key)).toEqual(["model-1/7/3/0/0"]);
    expect(remote.length).toBeGreaterThan(0);
    expect(remote.some((item) => item.key.includes("/-"))).toBe(true);
  });

  it("orders requested tiles from the viewport center outwards", () => {
    const tiles = tilesForBBox("model-1", 7, [0, 0, 100, 100], [0, 0, 100, 100], 3);
    const first = tiles[0].bbox;
    const centerX = (first[0] + first[2]) / 2;
    const centerY = (first[1] + first[3]) / 2;
    expect(Math.hypot(centerX - 50, centerY - 50)).toBeLessThan(40);
  });

  it("uses coarse overview cells and exposes their full reusable coverage", () => {
    const tiles = tilesForBBox(
      "model-1", 7, [80, 80, 320, 480], [-1000, -1000, 3000, 3000], 3, [100, 100, 300, 500],
    );
    const coverage = tileCoverage(tiles);

    expect(tiles.length).toBeLessThanOrEqual(4);
    expect(coverage).not.toBeNull();
    expect(coverage![0]).toBeLessThanOrEqual(80);
    expect(coverage![1]).toBeLessThanOrEqual(80);
    expect(coverage![2]).toBeGreaterThanOrEqual(320);
    expect(coverage![3]).toBeGreaterThanOrEqual(480);
  });

  it("coalesces concurrent loads and hides staging features until ready", async () => {
    const cache = new FeatureTileCache();
    let release: ((items: Feature[]) => void) | undefined;
    const loader = vi.fn(() => new Promise<Feature[]>((resolve) => { release = resolve; }));
    const first = cache.load(tile("same"), loader);
    const second = cache.load(tile("same"), loader);

    expect(loader).toHaveBeenCalledTimes(1);
    expect(cache.readyFeatures([tile("same")])).toEqual([]);
    expect(cache.allReady([tile("same")])).toBe(false);

    release?.([feature("plant-1")]);
    await Promise.all([first, second]);
    expect(cache.allReady([tile("same")])).toBe(true);
    expect(cache.readyFeatures([tile("same")]).map((item) => item.id)).toEqual(["plant-1"]);
  });

  it("deduplicates canonical objects repeated on tile boundaries", async () => {
    const cache = new FeatureTileCache();
    await cache.load(tile("left"), async () => [feature("shared"), feature("left")]);
    await cache.load(tile("right"), async () => [feature("shared"), feature("right")]);
    expect(cache.readyFeatures([tile("left"), tile("right")]).map((item) => item.id).sort())
      .toEqual(["left", "right", "shared"]);
  });

  it("draws plant position markers before crown geometry regardless of arrival order", () => {
    const crown = feature("crown", "crown");
    const marker = feature("marker", "position", "Point");
    const base = feature("base");
    expect(sortFeaturesForRender([crown, marker, base]).map((item) => item.id))
      .toEqual(["base", "marker", "crown"]);
  });

  it("evicts least-recently-used tiles but preserves protected frame tiles", async () => {
    const cache = new FeatureTileCache(2);
    await cache.load(tile("old"), async () => [feature("old-1"), feature("old-2")]);
    await cache.load(tile("active"), async () => [feature("active")]);
    cache.prune(new Set(["active"]));
    expect(cache.hasReady("old")).toBe(false);
    expect(cache.hasReady("active")).toBe(true);
  });
});
