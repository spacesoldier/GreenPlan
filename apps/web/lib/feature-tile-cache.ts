import type { Feature } from "./contracts";
import type { Extent } from "./viewport";

export type FeatureTile = {
  key: string;
  lod: number;
  bbox: Extent;
};

export function canCommitTileFrame(displayedLod: number | null, complete: boolean): boolean {
  return complete || displayedLod === null;
}

type ReadyEntry = {
  state: "ready";
  features: Feature[];
  lastUsed: number;
};

type PendingEntry = {
  state: "pending";
  promise: Promise<Feature[]>;
  controller: AbortController;
  lastUsed: number;
};

type TileEntry = ReadyEntry | PendingEntry;

// Overview still needs small enough cells to publish a useful central frame
// before a dense linear project has finished loading end-to-end.
// At overview LOD, one focus-sized grid cell avoids transferring the same
// long CAD assembly through dozens of neighbouring spatial tiles.
// Keep a two-viewport fetch window in the low tens of requests. Extremely
// fine cells duplicate large CAD assemblies and leave a stale raster visible
// while hundreds of requests settle.
const GRID_DIVISIONS_BY_LOD = [32, 8, 4, 1] as const;

export function tileCoverage(tiles: FeatureTile[]): Extent | null {
  if (!tiles.length) return null;
  return tiles.reduce<Extent>((extent, tile) => [
    Math.min(extent[0], tile.bbox[0]),
    Math.min(extent[1], tile.bbox[1]),
    Math.max(extent[2], tile.bbox[2]),
    Math.max(extent[3], tile.bbox[3]),
  ], [...tiles[0].bbox]);
}

export function tilesForBBox(
  modelId: string,
  modelVersion: number,
  bbox: Extent,
  modelExtent: Extent,
  lod: number,
  gridExtent: Extent = modelExtent,
): FeatureTile[] {
  const safeLod = Math.max(0, Math.min(3, Math.trunc(lod)));
  const divisions = GRID_DIVISIONS_BY_LOD[safeLod];
  const span = Math.max(gridExtent[2] - gridExtent[0], gridExtent[3] - gridExtent[1], 1);
  const tileSize = span / divisions;
  const epsilon = tileSize * 1e-9;
  const minColumn = Math.floor((bbox[0] - gridExtent[0]) / tileSize);
  const maxRequestedColumn = Math.floor((bbox[2] - gridExtent[0] - epsilon) / tileSize);
  const minRow = Math.floor((bbox[1] - gridExtent[1]) / tileSize);
  const maxRequestedRow = Math.floor((bbox[3] - gridExtent[1] - epsilon) / tileSize);
  const tiles: FeatureTile[] = [];
  for (let row = minRow; row <= maxRequestedRow; row += 1) {
    for (let column = minColumn; column <= maxRequestedColumn; column += 1) {
      const tileBBox: Extent = [
        Math.max(modelExtent[0], gridExtent[0] + column * tileSize),
        Math.max(modelExtent[1], gridExtent[1] + row * tileSize),
        Math.min(modelExtent[2], gridExtent[0] + (column + 1) * tileSize),
        Math.min(modelExtent[3], gridExtent[1] + (row + 1) * tileSize),
      ];
      if (tileBBox[0] >= tileBBox[2] || tileBBox[1] >= tileBBox[3]) continue;
      tiles.push({
        key: `${modelId}/${modelVersion}/${safeLod}/${column}/${row}`,
        lod: safeLod,
        bbox: tileBBox,
      });
    }
  }
  const centerX = (bbox[0] + bbox[2]) / 2;
  const centerY = (bbox[1] + bbox[3]) / 2;
  return tiles.sort((left, right) => {
    const leftDistance = Math.hypot((left.bbox[0] + left.bbox[2]) / 2 - centerX, (left.bbox[1] + left.bbox[3]) / 2 - centerY);
    const rightDistance = Math.hypot((right.bbox[0] + right.bbox[2]) / 2 - centerX, (right.bbox[1] + right.bbox[3]) / 2 - centerY);
    return leftDistance - rightDistance || left.key.localeCompare(right.key);
  });
}

function renderRank(feature: Feature): number {
  if (!feature.class_code.startsWith("vegetation.")) return 0;
  if (feature.geometry_role === "position" || feature.geometry.type === "Point") return 10;
  if (feature.geometry_role === "crown") return 20;
  return 15;
}

export function sortFeaturesForRender(features: Feature[]): Feature[] {
  return [...features].sort((left, right) => {
    const rankDifference = renderRank(left) - renderRank(right);
    return rankDifference || left.stable_key.localeCompare(right.stable_key);
  });
}

export class FeatureTileCache {
  private entries = new Map<string, TileEntry>();
  private clock = 0;

  constructor(private readonly maxFeatureReferences = 350_000) {}

  load(tile: FeatureTile, loader: (signal: AbortSignal) => Promise<Feature[]>): Promise<Feature[]> {
    const existing = this.entries.get(tile.key);
    if (existing?.state === "ready") {
      existing.lastUsed = ++this.clock;
      return Promise.resolve(existing.features);
    }
    if (existing?.state === "pending") {
      existing.lastUsed = ++this.clock;
      return existing.promise;
    }
    const controller = new AbortController();
    const promise = loader(controller.signal)
      .then((features) => {
        const current = this.entries.get(tile.key);
        if (current?.state === "pending" && current.promise === promise) {
          this.entries.set(tile.key, { state: "ready", features, lastUsed: ++this.clock });
        }
        return features;
      })
      .catch((error) => {
        const current = this.entries.get(tile.key);
        if (current?.state === "pending" && current.promise === promise) this.entries.delete(tile.key);
        throw error;
      });
    this.entries.set(tile.key, { state: "pending", promise, controller, lastUsed: ++this.clock });
    return promise;
  }

  hasReady(key: string): boolean {
    return this.entries.get(key)?.state === "ready";
  }

  allReady(tiles: FeatureTile[]): boolean {
    return tiles.every((tile) => this.hasReady(tile.key));
  }

  readyFeatures(tiles: FeatureTile[]): Feature[] {
    const unique = new Map<string, Feature>();
    for (const tile of tiles) {
      const entry = this.entries.get(tile.key);
      if (entry?.state !== "ready") continue;
      entry.lastUsed = ++this.clock;
      for (const item of entry.features) unique.set(item.id, item);
    }
    return [...unique.values()];
  }

  prune(protectedKeys: Set<string>): void {
    let references = 0;
    const candidates: Array<[string, ReadyEntry]> = [];
    for (const [key, entry] of this.entries) {
      if (entry.state !== "ready") continue;
      references += entry.features.length;
      if (!protectedKeys.has(key)) candidates.push([key, entry]);
    }
    candidates.sort((left, right) => left[1].lastUsed - right[1].lastUsed);
    for (const [key, entry] of candidates) {
      if (references <= this.maxFeatureReferences) break;
      this.entries.delete(key);
      references -= entry.features.length;
    }
  }

  clear(): void {
    for (const entry of this.entries.values()) {
      if (entry.state === "pending") entry.controller.abort();
    }
    this.entries.clear();
  }
}
