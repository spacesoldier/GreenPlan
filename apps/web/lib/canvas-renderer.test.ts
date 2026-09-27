import { describe, expect, it } from "vitest";

import type { Feature } from "./contracts";
import {
  decodePickingColor,
  encodePickingColor,
  expandViewportForPrefetch,
  featureBounds,
  intersectsViewport,
  visitGeometryPrimitives,
} from "./canvas-renderer";

const feature = (geometry: Feature["geometry"]): Feature => ({
  id: "object-1",
  stable_key: "object-1",
  class_code: "unknown.constraint",
  layer_id: "unknown",
  name: null,
  lifecycle: "existing",
  semantic_status: "needs_review",
  confidence: 0.4,
  geometry_role: "other",
  geometry,
  properties: {},
});

describe("Canvas CAD renderer", () => {
  it("expands and leads the fetch window in pan direction", () => {
    const bbox = expandViewportForPrefetch({ x: 0, y: -100, width: 200, height: 100 }, 1, -0.5);
    expect(bbox[0]).toBeLessThan(0);
    expect(bbox[1]).toBeLessThan(0);
    expect(bbox[2]).toBeGreaterThan(200);
    expect(bbox[3]).toBeGreaterThan(100);
    expect((bbox[0] + bbox[2]) / 2).toBeGreaterThan(100);
  });

  it("computes bounds and culls geometry outside the visible CAD bbox", () => {
    const line = feature({ type: "LineString", coordinates: [[10, 20], [30, 40]] });
    expect(featureBounds(line)).toEqual([10, 20, 30, 40]);
    expect(intersectsViewport(featureBounds(line), [0, 0, 20, 30])).toBe(true);
    expect(intersectsViewport(featureBounds(line), [100, 100, 200, 200])).toBe(false);
  });

  it("computes bounds for nested CAD render assemblies", () => {
    const assembly = feature({
      type: "GeometryCollection",
      geometries: [
        { type: "Polygon", coordinates: [[[10, 20], [20, 20], [20, 30], [10, 20]]] },
        { type: "MultiLineString", coordinates: [[[5, 25], [15, 40]], [[30, 10], [35, 45]]] },
      ],
    } as Feature["geometry"]);

    expect(featureBounds(assembly)).toEqual([5, 10, 35, 45]);
  });

  it("keeps open crown lines out of the fill path in mixed assemblies", () => {
    const geometry: Feature["geometry"] = {
      type: "GeometryCollection",
      geometries: [
        { type: "MultiLineString", coordinates: [[[0, 0], [5, 8], [10, 0]]] },
        { type: "Point", coordinates: [5, 4] },
        { type: "Polygon", coordinates: [[[20, 20], [25, 20], [25, 25], [20, 20]]] },
      ],
    };
    const primitives: string[] = [];
    visitGeometryPrimitives(geometry, (primitive) => primitives.push(primitive.kind));

    expect(primitives).toEqual(["line", "point", "polygon"]);
    expect(primitives.filter((kind) => kind !== "line")).toEqual(["point", "polygon"]);
  });

  it("round-trips a picking index through an RGB color", () => {
    for (const index of [1, 255, 256, 65_535, 1_000_000]) {
      expect(decodePickingColor(encodePickingColor(index))).toBe(index);
    }
  });
});
