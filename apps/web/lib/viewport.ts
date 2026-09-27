import { applyAffine, invertAffine, viewportMatrix } from "./raster-frame-cache";

export type Extent = [number, number, number, number];

export type Viewport = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export function extentContains(outer: Extent, inner: Extent): boolean {
  return outer[0] <= inner[0] && outer[1] <= inner[1]
    && outer[2] >= inner[2] && outer[3] >= inner[3];
}

export function fitExtent(extent: Extent, paddingRatio = 0.025, canvasAspect?: number): Viewport {
  const [minX, minY, maxX, maxY] = extent;
  const sourceWidth = Math.max(maxX - minX, 1);
  const sourceHeight = Math.max(maxY - minY, 1);
  const padding = Math.max(sourceWidth, sourceHeight) * paddingRatio;
  const viewport = {
    x: minX - padding,
    y: -(maxY + padding),
    width: sourceWidth + padding * 2,
    height: sourceHeight + padding * 2,
  };
  if (!canvasAspect || !Number.isFinite(canvasAspect) || canvasAspect <= 0) return viewport;
  const currentAspect = viewport.width / viewport.height;
  if (currentAspect < canvasAspect) {
    const nextWidth = viewport.height * canvasAspect;
    return { ...viewport, x: viewport.x - (nextWidth - viewport.width) / 2, width: nextWidth };
  }
  const nextHeight = viewport.width / canvasAspect;
  return { ...viewport, y: viewport.y - (nextHeight - viewport.height) / 2, height: nextHeight };
}

export function zoomViewport(
  viewport: Viewport,
  factor: number,
  anchorX = 0.5,
  anchorY = 0.5,
): Viewport {
  const nextWidth = viewport.width / factor;
  const nextHeight = viewport.height / factor;
  return {
    x: viewport.x + (viewport.width - nextWidth) * anchorX,
    y: viewport.y + (viewport.height - nextHeight) * anchorY,
    width: nextWidth,
    height: nextHeight,
  };
}

export function expandViewport(viewport: Viewport, bufferRatio: number): Viewport {
  const marginX = viewport.width * Math.max(bufferRatio, 0);
  const marginY = viewport.height * Math.max(bufferRatio, 0);
  return {
    x: viewport.x - marginX,
    y: viewport.y - marginY,
    width: viewport.width + marginX * 2,
    height: viewport.height + marginY * 2,
  };
}

export function panViewport(
  viewport: Viewport,
  deltaPixelsX: number,
  deltaPixelsY: number,
  canvasWidth: number,
  canvasHeight: number,
): Viewport {
  return {
    ...viewport,
    x: viewport.x - deltaPixelsX * viewport.width / Math.max(canvasWidth, 1),
    y: viewport.y - deltaPixelsY * viewport.height / Math.max(canvasHeight, 1),
  };
}

function viewportWithWorldAtScreen(
  width: number,
  height: number,
  bearing: number,
  world: [number, number],
  screen: [number, number],
  canvasWidth: number,
  canvasHeight: number,
): Viewport {
  const project = (x: number, y: number) => applyAffine(
    viewportMatrix({ x, y, width, height }, bearing, canvasWidth, canvasHeight),
    world,
  );
  const origin = project(0, 0);
  const unitX = project(1, 0);
  const unitY = project(0, 1);
  const a = unitX[0] - origin[0];
  const b = unitY[0] - origin[0];
  const c = unitX[1] - origin[1];
  const d = unitY[1] - origin[1];
  const targetX = screen[0] - origin[0];
  const targetY = screen[1] - origin[1];
  const determinant = a * d - b * c;
  if (Math.abs(determinant) < 1e-12) return { x: 0, y: 0, width, height };
  return {
    x: (targetX * d - b * targetY) / determinant,
    y: (a * targetY - targetX * c) / determinant,
    width,
    height,
  };
}

export function screenToCadPoint(
  viewport: Viewport,
  bearing: number,
  screenX: number,
  screenY: number,
  canvasWidth: number,
  canvasHeight: number,
): [number, number] {
  const [worldX, worldY] = applyAffine(
    invertAffine(viewportMatrix(viewport, bearing, canvasWidth, canvasHeight)),
    [screenX, screenY],
  );
  return [worldX, -worldY];
}

export function zoomViewportAtScreenPoint(
  viewport: Viewport,
  bearing: number,
  factor: number,
  screenX: number,
  screenY: number,
  canvasWidth: number,
  canvasHeight: number,
): Viewport {
  const world = applyAffine(
    invertAffine(viewportMatrix(viewport, bearing, canvasWidth, canvasHeight)),
    [screenX, screenY],
  );
  return viewportWithWorldAtScreen(
    viewport.width / factor,
    viewport.height / factor,
    bearing,
    world,
    [screenX, screenY],
    canvasWidth,
    canvasHeight,
  );
}

export function panViewportOnCanvas(
  viewport: Viewport,
  bearing: number,
  deltaPixelsX: number,
  deltaPixelsY: number,
  canvasWidth: number,
  canvasHeight: number,
): Viewport {
  const center: [number, number] = [canvasWidth / 2, canvasHeight / 2];
  const world = applyAffine(
    invertAffine(viewportMatrix(viewport, bearing, canvasWidth, canvasHeight)),
    center,
  );
  return viewportWithWorldAtScreen(
    viewport.width,
    viewport.height,
    bearing,
    world,
    [center[0] + deltaPixelsX, center[1] + deltaPixelsY],
    canvasWidth,
    canvasHeight,
  );
}

export function rotateBearing(current: number, delta: number): number {
  return ((current + delta + 180) % 360 + 360) % 360 - 180;
}

export function viewportToCadBBox(viewport: Viewport, bearing = 0): Extent {
  if (bearing === 0) {
    return [
      viewport.x,
      -(viewport.y + viewport.height),
      viewport.x + viewport.width,
      -viewport.y,
    ];
  }
  const centerX = viewport.x + viewport.width / 2;
  const centerY = viewport.y + viewport.height / 2;
  const radius = Math.hypot(viewport.width, viewport.height) / 2;
  return [centerX - radius, -(centerY + radius), centerX + radius, -(centerY - radius)];
}
