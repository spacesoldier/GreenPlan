import type { Viewport } from "./viewport";

export type Affine = [number, number, number, number, number, number];

const IDENTITY: Affine = [1, 0, 0, 1, 0, 0];

export function multiplyAffine(left: Affine, right: Affine): Affine {
  return [
    left[0] * right[0] + left[2] * right[1],
    left[1] * right[0] + left[3] * right[1],
    left[0] * right[2] + left[2] * right[3],
    left[1] * right[2] + left[3] * right[3],
    left[0] * right[4] + left[2] * right[5] + left[4],
    left[1] * right[4] + left[3] * right[5] + left[5],
  ];
}

export function invertAffine(matrix: Affine): Affine {
  const determinant = matrix[0] * matrix[3] - matrix[1] * matrix[2];
  if (Math.abs(determinant) < 1e-12) throw new Error("viewport transform is not invertible");
  return [
    matrix[3] / determinant,
    -matrix[1] / determinant,
    -matrix[2] / determinant,
    matrix[0] / determinant,
    (matrix[2] * matrix[5] - matrix[3] * matrix[4]) / determinant,
    (matrix[1] * matrix[4] - matrix[0] * matrix[5]) / determinant,
  ];
}

export function applyAffine(matrix: Affine, point: [number, number]): [number, number] {
  return [
    matrix[0] * point[0] + matrix[2] * point[1] + matrix[4],
    matrix[1] * point[0] + matrix[3] * point[1] + matrix[5],
  ];
}

function translation(x: number, y: number): Affine {
  return [1, 0, 0, 1, x, y];
}

function scaling(value: number): Affine {
  return [value, 0, 0, value, 0, 0];
}

function rotation(degrees: number): Affine {
  const radians = degrees * Math.PI / 180;
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  return [cosine, sine, -sine, cosine, 0, 0];
}

export function viewportMatrix(
  viewport: Viewport,
  bearing: number,
  canvasWidth: number,
  canvasHeight: number,
): Affine {
  const scale = Math.min(canvasWidth / viewport.width, canvasHeight / viewport.height);
  const offsetX = (canvasWidth - viewport.width * scale) / 2;
  const offsetY = (canvasHeight - viewport.height * scale) / 2;
  const centerX = viewport.x + viewport.width / 2;
  const centerY = viewport.y + viewport.height / 2;
  return [
    translation(offsetX, offsetY),
    scaling(scale),
    translation(-viewport.x, -viewport.y),
    translation(centerX, centerY),
    rotation(bearing),
    translation(-centerX, -centerY),
  ].reduce(multiplyAffine, IDENTITY);
}

export function rasterReprojectionMatrix(
  sourceViewport: Viewport,
  sourceBearing: number,
  sourceWidth: number,
  sourceHeight: number,
  targetViewport: Viewport,
  targetBearing: number,
  targetWidth: number,
  targetHeight: number,
): Affine {
  const source = viewportMatrix(sourceViewport, sourceBearing, sourceWidth, sourceHeight);
  const target = viewportMatrix(targetViewport, targetBearing, targetWidth, targetHeight);
  return multiplyAffine(target, invertAffine(source));
}

export function rasterStyleKey(frameKey: string, visibleLayers: Set<string>, selectedId: string): string {
  return `${frameKey}|${[...visibleLayers].sort().join(",")}|${selectedId}`;
}

type SizedValue = { byteSize: number };

export class RasterFrameCache<T extends SizedValue> {
  private entries = new Map<string, { value: T; lastUsed: number }>();
  private clock = 0;
  private usedBytes = 0;

  constructor(private readonly maxBytes = 64 * 1024 * 1024) {}

  get byteSize(): number {
    return this.usedBytes;
  }

  get(key: string): T | undefined {
    const entry = this.entries.get(key);
    if (!entry) return undefined;
    entry.lastUsed = ++this.clock;
    return entry.value;
  }

  set(key: string, value: T): void {
    const existing = this.entries.get(key);
    if (existing) {
      this.usedBytes -= existing.value.byteSize;
      this.entries.delete(key);
    }
    if (value.byteSize > this.maxBytes) return;
    this.entries.set(key, { value, lastUsed: ++this.clock });
    this.usedBytes += value.byteSize;
    const oldest = () => [...this.entries.entries()]
      .sort((left, right) => left[1].lastUsed - right[1].lastUsed)[0];
    while (this.usedBytes > this.maxBytes && this.entries.size) {
      const candidate = oldest();
      if (!candidate) break;
      this.entries.delete(candidate[0]);
      this.usedBytes -= candidate[1].value.byteSize;
    }
  }

  clear(): void {
    this.entries.clear();
    this.usedBytes = 0;
  }
}
