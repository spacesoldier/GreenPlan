"use client";

import { useEffect, useRef } from "react";

import type { Feature } from "@/lib/contracts";
import { decodePickingColor, renderCadSceneProgressively } from "@/lib/canvas-renderer";
import { RasterFrameCache, rasterReprojectionMatrix, rasterStyleKey } from "@/lib/raster-frame-cache";
import { expandViewport, type Viewport } from "@/lib/viewport";

const RASTER_OVERSCAN_BUFFER = 0.4;

type Props = {
  features: Feature[];
  sceneKey: string;
  viewport: Viewport;
  bearing: number;
  visibleLayers: Set<string>;
  selectedId: string;
  dragging: boolean;
  onCanvasSize: (width: number, height: number) => void;
  onSelect: (id: string) => void;
  onWheel: (event: WheelEvent, canvas: HTMLCanvasElement) => void;
  onPointerDown: React.PointerEventHandler<HTMLCanvasElement>;
  onPointerMove: React.PointerEventHandler<HTMLCanvasElement>;
  onPointerUp: React.PointerEventHandler<HTMLCanvasElement>;
  onPointerLeave: React.PointerEventHandler<HTMLCanvasElement>;
};

type RasterSurface = OffscreenCanvas | HTMLCanvasElement;

type RasterFrame = {
  byteSize: number;
  visible: RasterSurface;
  picking: RasterSurface;
  viewport: Viewport;
  bearing: number;
  width: number;
  height: number;
  ids: string[];
};

function copyCanvas(source: HTMLCanvasElement): RasterSurface {
  const target: RasterSurface = typeof OffscreenCanvas === "undefined"
    ? document.createElement("canvas")
    : new OffscreenCanvas(source.width, source.height);
  target.width = source.width;
  target.height = source.height;
  const context = target.getContext("2d");
  context?.drawImage(source, 0, 0);
  return target;
}

function blitFrame(
  target: HTMLCanvasElement,
  source: RasterSurface,
  frame: RasterFrame,
  viewport: Viewport,
  bearing: number,
  smoothing: boolean,
) {
  const bounds = target.getBoundingClientRect();
  const width = Math.max(bounds.width, 1);
  const height = Math.max(bounds.height, 1);
  const pixelRatio = window.devicePixelRatio || 1;
  const pixelWidth = Math.round(width * pixelRatio);
  const pixelHeight = Math.round(height * pixelRatio);
  if (target.width !== pixelWidth || target.height !== pixelHeight) {
    target.width = pixelWidth;
    target.height = pixelHeight;
  }
  const context = target.getContext("2d", smoothing ? undefined : { willReadFrequently: true });
  if (!context) return;
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.clearRect(0, 0, target.width, target.height);
  const matrix = rasterReprojectionMatrix(
    frame.viewport,
    frame.bearing,
    frame.width,
    frame.height,
    viewport,
    bearing,
    width,
    height,
  );
  context.imageSmoothingEnabled = smoothing;
  context.setTransform(
    matrix[0] * pixelRatio,
    matrix[1] * pixelRatio,
    matrix[2] * pixelRatio,
    matrix[3] * pixelRatio,
    matrix[4] * pixelRatio,
    matrix[5] * pixelRatio,
  );
  context.drawImage(source, 0, 0, frame.width, frame.height);
}

export function CadCanvas(props: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const pickingCanvas = useRef<HTMLCanvasElement>(null);
  const pickingIds = useRef<string[]>([""]);
  const rasterFrames = useRef(new RasterFrameCache<RasterFrame>());
  const wasDragging = useRef(false);
  const vectorRenderCount = useRef(0);
  const rasterBlitCount = useRef(0);

  useEffect(() => {
    const target = canvas.current;
    if (!target) return;
    const report = () => {
      const bounds = target.getBoundingClientRect();
      props.onCanvasSize(bounds.width, bounds.height);
    };
    report();
    const observer = new ResizeObserver(report);
    observer.observe(target);
    return () => observer.disconnect();
  }, [props.onCanvasSize]);

  useEffect(() => {
    if (!canvas.current || !pickingCanvas.current) return;
    const visibleCanvas = canvas.current;
    const hitCanvas = pickingCanvas.current;
    const cacheKey = rasterStyleKey(props.sceneKey, props.visibleLayers, props.selectedId);
    const cached = rasterFrames.current.get(cacheKey);
    if (cached) {
      blitFrame(visibleCanvas, cached.visible, cached, props.viewport, props.bearing, true);
      blitFrame(hitCanvas, cached.picking, cached, props.viewport, props.bearing, false);
      pickingIds.current = cached.ids;
      rasterBlitCount.current += 1;
      visibleCanvas.dataset.rasterBlits = String(rasterBlitCount.current);
    }

    const justEndedDrag = wasDragging.current && !props.dragging;
    wasDragging.current = props.dragging;
    if (props.dragging) return;

    let animationFrame = 0;
    let cancelled = false;
    const renderExact = () => {
      animationFrame = window.requestAnimationFrame(async () => {
        const bounds = visibleCanvas.getBoundingClientRect();
        const displaySize = { width: Math.max(bounds.width, 1), height: Math.max(bounds.height, 1) };
        const renderViewport = expandViewport(props.viewport, RASTER_OVERSCAN_BUFFER);
        const renderSize = {
          width: displaySize.width * (1 + RASTER_OVERSCAN_BUFFER * 2),
          height: displaySize.height * (1 + RASTER_OVERSCAN_BUFFER * 2),
        };
        const draftVisible = document.createElement("canvas");
        const draftPicking = document.createElement("canvas");
        const ids = await renderCadSceneProgressively(
          draftVisible,
          draftPicking,
          props.features,
          renderViewport,
          props.bearing,
          props.visibleLayers,
          props.selectedId,
          renderSize,
          () => cancelled,
        );
        if (!ids || cancelled) return;
        pickingIds.current = ids;
        const frame: RasterFrame = {
          byteSize: (draftVisible.width * draftVisible.height + draftPicking.width * draftPicking.height) * 4,
          visible: copyCanvas(draftVisible),
          picking: copyCanvas(draftPicking),
          viewport: renderViewport,
          bearing: props.bearing,
          width: renderSize.width,
          height: renderSize.height,
          ids,
        };
        blitFrame(visibleCanvas, frame.visible, frame, props.viewport, props.bearing, true);
        blitFrame(hitCanvas, frame.picking, frame, props.viewport, props.bearing, false);
        rasterFrames.current.set(cacheKey, frame);
        vectorRenderCount.current += 1;
        visibleCanvas.dataset.vectorRenders = String(vectorRenderCount.current);
        visibleCanvas.dataset.featureCount = String(props.features.length);
      });
    };

    if (!cached) renderExact();
    // Let pointer-up and the next interaction frame commit before starting the
    // budgeted exact pass. A new gesture cancels this timer and keeps using the
    // already reprojected raster instead of queuing obsolete vector work.
    const timer = !cached ? 0 : window.setTimeout(renderExact, justEndedDrag ? 100 : 140);
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
      window.cancelAnimationFrame(animationFrame);
    };
  }, [props.bearing, props.dragging, props.features, props.sceneKey, props.selectedId, props.viewport, props.visibleLayers]);

  useEffect(() => () => rasterFrames.current.clear(), []);

  useEffect(() => {
    const target = canvas.current;
    if (!target) return;
    const handleWheel = (event: WheelEvent) => props.onWheel(event, target);
    target.addEventListener("wheel", handleWheel, { passive: false });
    return () => target.removeEventListener("wheel", handleWheel);
  }, [props.onWheel]);

  function pick(event: React.MouseEvent<HTMLCanvasElement>) {
    if (props.dragging || !pickingCanvas.current) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const scaleX = pickingCanvas.current.width / Math.max(bounds.width, 1);
    const scaleY = pickingCanvas.current.height / Math.max(bounds.height, 1);
    const context = pickingCanvas.current.getContext("2d", { willReadFrequently: true });
    if (!context) return;
    const pixel = context.getImageData(
      Math.floor((event.clientX - bounds.left) * scaleX),
      Math.floor((event.clientY - bounds.top) * scaleY),
      1,
      1,
    ).data;
    const id = pickingIds.current[decodePickingColor([pixel[0], pixel[1], pixel[2]])];
    if (id) props.onSelect(id);
  }

  return <>
    <canvas
      ref={canvas}
      className="drawing cad-canvas"
      aria-label="Чертёж проекта"
      onClick={pick}
      onPointerDown={props.onPointerDown}
      onPointerMove={props.onPointerMove}
      onPointerUp={props.onPointerUp}
      onPointerCancel={props.onPointerUp}
      onPointerLeave={props.onPointerLeave}
      onContextMenu={(event) => event.preventDefault()}
    />
    <canvas ref={pickingCanvas} className="picking-canvas" aria-hidden="true" />
  </>;
}
