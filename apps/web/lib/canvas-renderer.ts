import type { Feature } from "./contracts";
import { runFrameBudgeted } from "./frame-scheduler";
import { viewportToCadBBox, type Extent, type Viewport } from "./viewport";

const boundsCache = new WeakMap<Feature, Extent>();
type GeometryPaths = { stroke: Path2D; fill: Path2D | null };
const pathCache = new WeakMap<Feature, Map<number, GeometryPaths>>();

export function expandViewportForPrefetch(
  viewport: Viewport,
  directionX: number,
  directionY: number,
  bearing = 0,
  bufferRatio = 0.5,
  leadRatio = 0.25,
): Extent {
  const marginX = viewport.width * bufferRatio;
  const marginY = viewport.height * bufferRatio;
  const leadX = Math.max(-1, Math.min(1, directionX)) * viewport.width * leadRatio;
  const leadY = Math.max(-1, Math.min(1, directionY)) * viewport.height * leadRatio;
  return viewportToCadBBox({
    x: viewport.x - marginX + leadX,
    y: viewport.y - marginY + leadY,
    width: viewport.width + marginX * 2,
    height: viewport.height + marginY * 2,
  }, bearing);
}

function visitCoordinates(value: unknown, visit: (x: number, y: number) => void): void {
  if (!Array.isArray(value)) return;
  if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
    visit(value[0], value[1]);
    return;
  }
  for (const child of value) visitCoordinates(child, visit);
}

export function featureBounds(feature: Feature): Extent {
  const cached = boundsCache.get(feature);
  if (cached) return cached;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const visitGeometry = (geometry: Feature["geometry"]) => {
    visitCoordinates(geometry.coordinates, (x, y) => {
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    });
    for (const child of geometry.geometries ?? []) visitGeometry(child);
  };
  visitGeometry(feature.geometry);
  const bounds: Extent = [minX, minY, maxX, maxY];
  boundsCache.set(feature, bounds);
  return bounds;
}

export function intersectsViewport(left: Extent, right: Extent): boolean {
  return !(left[2] < right[0] || left[0] > right[2] || left[3] < right[1] || left[1] > right[3]);
}

export function encodePickingColor(index: number): [number, number, number] {
  return [(index >> 16) & 255, (index >> 8) & 255, index & 255];
}

export function decodePickingColor(color: [number, number, number]): number {
  return (color[0] << 16) | (color[1] << 8) | color[2];
}

export type GeometryPrimitive =
  | { kind: "point"; coordinates: number[] }
  | { kind: "line"; coordinates: number[][] }
  | { kind: "polygon"; coordinates: number[][][] };

export function visitGeometryPrimitives(
  geometry: Feature["geometry"],
  visit: (primitive: GeometryPrimitive) => void,
): void {
  if (geometry.type === "Point") {
    visit({ kind: "point", coordinates: geometry.coordinates as number[] });
    return;
  }
  if (geometry.type === "LineString") {
    visit({ kind: "line", coordinates: geometry.coordinates as number[][] });
    return;
  }
  if (geometry.type === "Polygon") {
    visit({ kind: "polygon", coordinates: geometry.coordinates as number[][][] });
    return;
  }
  if (geometry.type === "MultiPoint") {
    for (const point of geometry.coordinates as number[][]) {
      visit({ kind: "point", coordinates: point });
    }
    return;
  }
  if (geometry.type === "MultiLineString") {
    for (const line of geometry.coordinates as number[][][]) {
      visit({ kind: "line", coordinates: line });
    }
    return;
  }
  if (geometry.type === "MultiPolygon") {
    for (const polygon of geometry.coordinates as number[][][][]) {
      visit({ kind: "polygon", coordinates: polygon });
    }
    return;
  }
  if (geometry.type === "GeometryCollection") {
    for (const child of geometry.geometries ?? []) {
      visitGeometryPrimitives(child, visit);
    }
  }
}

function appendPoint(path: Path2D, coordinates: number[], pointRadius: number): void {
  const [x, y] = coordinates;
  path.moveTo(x + pointRadius, -y);
  path.arc(x, -y, pointRadius, 0, Math.PI * 2);
}

function appendLine(path: Path2D, coordinates: number[][]): void {
  coordinates.forEach(([x, y], index) => index ? path.lineTo(x, -y) : path.moveTo(x, -y));
}

function appendPolygon(path: Path2D, coordinates: number[][][]): void {
  for (const ring of coordinates) {
    appendLine(path, ring);
    path.closePath();
  }
}

function geometryPaths(feature: Feature, pointRadius: number): GeometryPaths | null {
  let variants = pathCache.get(feature);
  const key = Math.round(pointRadius * 1_000_000) / 1_000_000;
  const cached = variants?.get(key);
  if (cached) return cached;
  const stroke = new Path2D();
  const fill = new Path2D();
  let hasStroke = false;
  let hasFill = false;
  visitGeometryPrimitives(feature.geometry, (primitive) => {
    if (primitive.kind === "point") {
      appendPoint(stroke, primitive.coordinates, pointRadius);
      appendPoint(fill, primitive.coordinates, pointRadius);
      hasStroke = true;
      hasFill = true;
    } else if (primitive.kind === "line") {
      appendLine(stroke, primitive.coordinates);
      hasStroke ||= primitive.coordinates.length > 0;
    } else {
      appendPolygon(stroke, primitive.coordinates);
      appendPolygon(fill, primitive.coordinates);
      hasStroke = true;
      hasFill = true;
    }
  });
  if (!hasStroke) return null;
  const paths = { stroke, fill: hasFill ? fill : null };
  if (!variants) {
    variants = new Map();
    pathCache.set(feature, variants);
  }
  // A feature only needs visible/picking radii at the last few zoom levels.
  // Bound retained native Path2D memory during long editing sessions.
  if (variants.size >= 6) variants.delete(variants.keys().next().value!);
  variants.set(key, paths);
  return paths;
}

function prepareContext(
  canvas: HTMLCanvasElement,
  context: CanvasRenderingContext2D,
  viewport: Viewport,
  bearing: number,
  displaySize?: { width: number; height: number },
): { scale: number; width: number; height: number } {
  const bounds = canvas.getBoundingClientRect();
  const width = Math.max(displaySize?.width ?? bounds.width, 1);
  const height = Math.max(displaySize?.height ?? bounds.height, 1);
  const pixelRatio = window.devicePixelRatio || 1;
  const pixelWidth = Math.round(width * pixelRatio);
  const pixelHeight = Math.round(height * pixelRatio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, width, height);
  const scale = Math.min(width / viewport.width, height / viewport.height);
  const offsetX = (width - viewport.width * scale) / 2;
  const offsetY = (height - viewport.height * scale) / 2;
  const centerX = viewport.x + viewport.width / 2;
  const centerY = viewport.y + viewport.height / 2;
  context.translate(offsetX, offsetY);
  context.scale(scale, scale);
  context.translate(-viewport.x, -viewport.y);
  context.translate(centerX, centerY);
  context.rotate(bearing * Math.PI / 180);
  context.translate(-centerX, -centerY);
  context.lineCap = "round";
  context.lineJoin = "round";
  return { scale, width, height };
}

export async function renderCadSceneProgressively(
  canvas: HTMLCanvasElement,
  pickingCanvas: HTMLCanvasElement,
  features: Feature[],
  viewport: Viewport,
  bearing: number,
  visibleLayers: Set<string>,
  selectedId: string,
  displaySize: { width: number; height: number },
  cancelled: () => boolean,
): Promise<string[] | null> {
  const context = canvas.getContext("2d");
  const picking = pickingCanvas.getContext("2d", { willReadFrequently: true });
  if (!context || !picking) return [""];
  const main = prepareContext(canvas, context, viewport, bearing, displaySize);
  prepareContext(pickingCanvas, picking, viewport, bearing, displaySize);
  const visibleBBox = viewportToCadBBox(viewport, bearing);
  const pointRadius = 3.2 / main.scale;
  const pickRadius = 7 / main.scale;
  const ids = [""];

  const completed = await runFrameBudgeted(features, (feature) => {
    if (!visibleLayers.has(feature.layer_id) || !intersectsViewport(featureBounds(feature), visibleBBox)) return;
    const index = ids.length;
    if (index >= 0xffffff) return;
    ids.push(feature.id);
    const selected = feature.id === selectedId;
    const surfacePreview = feature.class_code === "derived.surface_candidate";
    const review = feature.semantic_status === "needs_review";
    context.strokeStyle = surfacePreview ? "#1f8f4f" : selected ? "#2e8d59" : review ? "#c18428" : "#526d86";
    context.fillStyle = surfacePreview ? "rgba(83,196,109,.34)" : selected ? "rgba(71,176,113,.28)" : review ? "rgba(211,152,54,.10)" : "rgba(74,102,126,.08)";
    context.lineWidth = (surfacePreview ? 3.2 : selected ? 2.6 : 1.1) / main.scale;
    const visiblePaths = geometryPaths(feature, pointRadius);
    if (visiblePaths) {
      if (visiblePaths.fill) context.fill(visiblePaths.fill, "evenodd");
      context.stroke(visiblePaths.stroke);
    }

    const [red, green, blue] = encodePickingColor(index);
    picking.strokeStyle = `rgb(${red},${green},${blue})`;
    picking.fillStyle = `rgb(${red},${green},${blue})`;
    picking.lineWidth = 7 / main.scale;
    const hitPaths = geometryPaths(feature, pickRadius);
    if (hitPaths) {
      if (hitPaths.fill) picking.fill(hitPaths.fill, "evenodd");
      picking.stroke(hitPaths.stroke);
    }
  }, { budgetMs: 10, cancelled });
  return completed ? ids : null;
}
