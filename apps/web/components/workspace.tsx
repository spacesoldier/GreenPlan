"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

import { CadCanvas } from "@/components/cad-canvas";
import { expandViewportForPrefetch } from "@/lib/canvas-renderer";
import {
  FeatureTileCache,
  canCommitTileFrame,
  sortFeaturesForRender,
  tileCoverage,
  tilesForBBox,
  type FeatureTile,
} from "@/lib/feature-tile-cache";

import type {
  Evidence,
  Feature,
  FeatureCollection,
  ObjectDetail,
  Project,
  SceneManifest,
  SourceNode,
} from "@/lib/contracts";
import {
  extentContains,
  fitExtent,
  panViewportOnCanvas,
  rotateBearing,
  screenToCadPoint,
  viewportToCadBBox,
  zoomViewport,
  zoomViewportAtScreenPoint,
  type Extent,
  type Viewport,
} from "@/lib/viewport";

type LoadState = "loading" | "ready" | "empty" | "error";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/domain${path}`, { signal });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.error?.message ?? `HTTP ${response.status}`);
  return body as T;
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}>{status.replaceAll("_", " ")}</span>;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function clampExtent(extent: Extent, boundary: Extent): Extent | null {
  const intersection: Extent = [
    Math.max(extent[0], boundary[0]),
    Math.max(extent[1], boundary[1]),
    Math.min(extent[2], boundary[2]),
    Math.min(extent[3], boundary[3]),
  ];
  return intersection[0] <= intersection[2] && intersection[1] <= intersection[3] ? intersection : null;
}

export function Workspace() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [manifest, setManifest] = useState<SceneManifest | null>(null);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [featureFrameKey, setFeatureFrameKey] = useState("empty");
  const [sources, setSources] = useState<SourceNode[]>([]);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set());
  const [selectedId, setSelectedId] = useState("");
  const [selectedObject, setSelectedObject] = useState<ObjectDetail | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState("");
  const [view, setView] = useState<"2d" | "3d">("2d");
  const [viewport, setViewport] = useState<Viewport>(() => fitExtent([0, 0, 500, 300]));
  const [bearing, setBearing] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [cursorPosition, setCursorPosition] = useState<[number, number] | null>(null);
  const drag = useRef<{ pointerId: number; x: number; y: number; mode: "pan" | "rotate"; moved: boolean } | null>(null);
  const ignoreFeatureClick = useRef(false);
  const frameRequestId = useRef(0);
  const previousViewportCenter = useRef<[number, number] | null>(null);
  const featureTileCache = useRef(new FeatureTileCache());
  const activeTileWindow = useRef<{
    modelId: string;
    modelVersion: number;
    lod: number;
    bbox: Extent;
    tiles: FeatureTile[];
  } | null>(null);
  const displayedLod = useRef<number | null>(null);
  const [featureLoading, setFeatureLoading] = useState(false);
  const [canvasAspect, setCanvasAspect] = useState<number | null>(null);

  const project = projects.find((item) => item.id === projectId);

  useEffect(() => () => featureTileCache.current.clear(), []);

  useEffect(() => {
    const controller = new AbortController();
    getJson<{ items: Project[] }>("/v1/projects", controller.signal)
      .then(({ items }) => {
        setProjects(items);
        const requested = new URLSearchParams(window.location.search).get("project");
        setProjectId(items.find((item) => item.id === requested)?.id ?? items[0]?.id ?? "");
        if (!items.length) setState("empty");
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") {
          setError(reason.message);
          setState("error");
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!project) return;
    const controller = new AbortController();
    setState("loading");
    Promise.all([
      getJson<SceneManifest>(`/v1/models/${project.current_model_id}/scene-manifest`, controller.signal),
      getJson<{ nodes: SourceNode[] }>(`/v1/project-revisions/${project.current_revision_id}/source-tree`, controller.signal),
    ])
      .then(([nextManifest, sourceTree]) => {
        setManifest(nextManifest);
        setSources(sourceTree.nodes);
        setFeatures([]);
        setFeatureFrameKey(`${project.current_model_id}/${nextManifest.model_version}/empty`);
        featureTileCache.current.clear();
        activeTileWindow.current = null;
        displayedLod.current = null;
        frameRequestId.current += 1;
        previousViewportCenter.current = null;
        setVisibleLayers(new Set(nextManifest.layers.map((layer) => layer.id)));
        const requestedObject = new URLSearchParams(window.location.search).get("object") ?? "";
        setSelectedId(requestedObject);
        setState(nextManifest.feature_count ? "ready" : "empty");
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") {
          setError(reason.message);
          setState("error");
        }
      });
    return () => controller.abort();
  }, [project]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedObject(null);
      setEvidence([]);
      return;
    }
    const controller = new AbortController();
    Promise.all([
      getJson<ObjectDetail>(`/v1/objects/${selectedId}`, controller.signal),
      getJson<{ items: Evidence[] }>(`/v1/objects/${selectedId}/evidence`, controller.signal),
    ]).then(([object, objectEvidence]) => {
      setSelectedObject(object);
      setEvidence(objectEvidence.items);
    }).catch(() => undefined);
    return () => controller.abort();
  }, [selectedId]);

  useEffect(() => {
    if (!projectId || state === "loading") return;
    const params = new URLSearchParams(window.location.search);
    params.set("project", projectId);
    if (selectedId) params.set("object", selectedId);
    else params.delete("object");
    params.set("view", view);
    window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
  }, [projectId, selectedId, state, view]);

  const focusExtent = useMemo<Extent>(
    () => manifest?.spatial_focus?.extent ?? manifest?.extent ?? [0, 0, 500, 300],
    [manifest],
  );
  const fitViewport = useMemo(
    () => fitExtent(focusExtent, 0.025, canvasAspect ?? undefined),
    [canvasAspect, focusExtent],
  );

  useEffect(() => {
    setViewport(fitViewport);
    setBearing(0);
  }, [fitViewport]);

  const handleCanvasSize = useCallback((width: number, height: number) => {
    if (width <= 0 || height <= 0) return;
    const next = width / height;
    setCanvasAspect((current) => current !== null && Math.abs(current - next) < 0.002 ? current : next);
  }, []);

  useEffect(() => {
    if (!project || !manifest || manifest.model_id !== project.current_model_id || state !== "ready" || dragging) return;
    const modelId = project.current_model_id;
    const center: [number, number] = [viewport.x + viewport.width / 2, viewport.y + viewport.height / 2];
    const previous = previousViewportCenter.current;
    const directionX = previous ? (center[0] - previous[0]) / Math.max(viewport.width, 1) : 0;
    const directionY = previous ? (center[1] - previous[1]) / Math.max(viewport.height, 1) : 0;
    previousViewportCenter.current = center;
    const zoom = fitViewport.width / viewport.width;
    const lod = zoom < 1.5 ? 3 : zoom < 4 ? 2 : zoom < 12 ? 1 : 0;
    const visibleBBox = clampExtent(viewportToCadBBox(viewport, bearing), manifest.extent);
    const nextPrefetchBBox = clampExtent(
      expandViewportForPrefetch(viewport, directionX, directionY, bearing),
      manifest.extent,
    );
    if (!visibleBBox || !nextPrefetchBBox) {
      setFeatures([]);
      setFeatureFrameKey(`${modelId}/${manifest.model_version}/${lod}/outside`);
      displayedLod.current = lod;
      return;
    }
    const active = activeTileWindow.current;
    const canReuseWindow = active
      && active.modelId === modelId
      && active.modelVersion === manifest.model_version
      && active.lod === lod
      && extentContains(active.bbox, visibleBBox);
    const tiles = canReuseWindow ? active.tiles : tilesForBBox(
        modelId,
        manifest.model_version,
        nextPrefetchBBox,
        manifest.extent,
        lod,
        manifest.spatial_focus?.extent ?? manifest.extent,
      );
    if (!canReuseWindow) {
      activeTileWindow.current = {
        modelId,
        modelVersion: manifest.model_version,
        lod,
        bbox: tileCoverage(tiles) ?? nextPrefetchBBox,
        tiles,
      };
    }
    const requestId = ++frameRequestId.current;
    const cache = featureTileCache.current;

    const commitReadyFrame = () => {
      if (requestId !== frameRequestId.current) return;
      const complete = cache.allReady(tiles);
      if (!canCommitTileFrame(displayedLod.current, complete)) return;
      const ready = cache.readyFeatures(tiles);
      if (ready.length || complete) {
        const readyKeys = tiles.filter((tile) => cache.hasReady(tile.key)).map((tile) => tile.key).join(",");
        setFeatures(sortFeaturesForRender(ready));
        setFeatureFrameKey(`${modelId}/${manifest.model_version}/${lod}:${readyKeys}`);
      }
      if (complete) displayedLod.current = lod;
    };

    commitReadyFrame();
    if (cache.allReady(tiles)) {
      cache.prune(new Set(tiles.map((tile) => tile.key)));
      setFeatureLoading(false);
      return;
    }

    async function loadTile(tile: FeatureTile, signal: AbortSignal): Promise<Feature[]> {
      const accumulated: Feature[] = [];
      let offset = 0;
      do {
        const page = await getJson<FeatureCollection>(
          `/v1/models/${modelId}/features?bbox=${tile.bbox.join(",")}&lod=${tile.lod}&limit=5000&offset=${offset}`,
          signal,
        );
        accumulated.push(...page.features);
        if (page.next_offset === null) return accumulated;
        offset = page.next_offset;
      } while (!signal.aborted);
      return accumulated;
    }

    setFeatureLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        let nextIndex = 0;
        const worker = async () => {
          while (nextIndex < tiles.length) {
            const tile = tiles[nextIndex];
            nextIndex += 1;
            await cache.load(tile, (signal) => loadTile(tile, signal));
            commitReadyFrame();
          }
        };
        await Promise.all(Array.from({ length: Math.min(2, tiles.length) }, () => worker()));
        commitReadyFrame();
        cache.prune(new Set(tiles.map((tile) => tile.key)));
      } catch (reason) {
        if (reason instanceof Error && reason.name !== "AbortError") setError(reason.message);
      } finally {
        if (requestId === frameRequestId.current) setFeatureLoading(false);
      }
    }, 60);
    return () => {
      window.clearTimeout(timer);
    };
  }, [bearing, dragging, fitViewport.width, manifest, project, state, viewport]);

  function changeZoom(
    factor: number,
    anchor?: { x: number; y: number; width: number; height: number },
  ) {
    setViewport((current) => {
      const minimumWidth = fitViewport.width / 100_000;
      const maximumWidth = fitViewport.width * 4;
      const desiredWidth = Math.min(maximumWidth, Math.max(minimumWidth, current.width / factor));
      const actualFactor = current.width / desiredWidth;
      return anchor
        ? zoomViewportAtScreenPoint(
            current, bearing, actualFactor, anchor.x, anchor.y, anchor.width, anchor.height,
          )
        : zoomViewport(current, actualFactor, 0.5, 0.5);
    });
  }

  function resetViewport() {
    setViewport(fitViewport);
    setBearing(0);
  }

  function pointerPosition(event: React.MouseEvent<HTMLCanvasElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      bounds,
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    };
  }

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    if (event.button !== 0 && event.button !== 2) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      mode: event.button === 2 || event.shiftKey ? "rotate" : "pan",
      moved: false,
    };
    setDragging(true);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    const position = pointerPosition(event);
    setCursorPosition(screenToCadPoint(
      viewport,
      bearing,
      position.x,
      position.y,
      position.bounds.width,
      position.bounds.height,
    ));
    const active = drag.current;
    if (!active || active.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - active.x;
    const deltaY = event.clientY - active.y;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 2) active.moved = true;
    if (active.mode === "rotate") {
      setBearing((current) => rotateBearing(current, deltaX * 0.35));
    } else {
      setViewport((current) => panViewportOnCanvas(
        current,
        bearing,
        deltaX,
        deltaY,
        position.bounds.width,
        position.bounds.height,
      ));
    }
    active.x = event.clientX;
    active.y = event.clientY;
  }

  function handlePointerUp(event: React.PointerEvent<HTMLCanvasElement>) {
    if (drag.current?.moved) {
      ignoreFeatureClick.current = true;
      window.setTimeout(() => { ignoreFeatureClick.current = false; }, 0);
    }
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function toggleLayer(layerId: string) {
    setVisibleLayers((current) => {
      const next = new Set(current);
      if (next.has(layerId)) next.delete(layerId);
      else next.add(layerId);
      return next;
    });
  }

  const selectedAssemblyMemberCount = typeof selectedObject?.properties.member_count === "number"
    ? selectedObject.properties.member_count
    : null;

  return (
    <main className="app-frame">
      <header className="topbar">
        <Link className="workspace-brand" href="/" aria-label="Вернуться ко всем проектам">
          <div className="brand-mark">G</div>
          <div className="brand-copy"><strong>GreenPlan</strong><span>spatial intelligence</span></div>
        </Link>
        <div className="project-switcher">
          <span className="eyebrow">Проект</span>
          <select value={projectId} onChange={(event) => { setSelectedId(""); setProjectId(event.target.value); }}>
            {projects.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
        </div>
        <div className="topbar-meta">
          <span className="live-dot" /> API connected
          <button className="avatar" aria-label="Профиль">СЛ</button>
        </div>
      </header>

      <section className="workspace">
        <aside className="left-panel panel">
          <div className="panel-heading"><span>Навигация</span><button aria-label="Свернуть">‹</button></div>
          <nav className="nav-tabs"><button className="active">Модель</button><button>Источники</button></nav>
          <div className="tree-section">
            <p className="tree-label">Каноническая модель</p>
            <div className="tree-root"><span className="tree-icon">◇</span><div><strong>{project?.title ?? "Загрузка…"}</strong><small>model v{project?.model_version ?? "—"}</small></div></div>
            {manifest?.layers.map((layer) => (
              <label className="layer-row" key={layer.id}>
                <input type="checkbox" checked={visibleLayers.has(layer.id)} onChange={() => toggleLayer(layer.id)} />
                <span className={`layer-swatch swatch-${layer.id}`} />
                <span>{layer.title}</span><small>{layer.feature_count.toLocaleString("ru-RU")}</small>
              </label>
            ))}
          </div>
          <div className="tree-section sources">
            <p className="tree-label">Исходные данные</p>
            {sources.map((source) => <div className="source-row" key={source.id}><span>{source.title.split(".").pop()?.toUpperCase() ?? "FILE"}</span><div><strong>{source.title}</strong><small>{source.display_path}</small></div></div>)}
          </div>
          <div className="quality-card"><span className="quality-score">{Math.round((1 - ((manifest?.issues.needs_review ?? 0) / Math.max(manifest?.feature_count ?? 1, 1))) * 100)}%</span><div><strong>Качество модели</strong><small>{manifest?.issues.needs_review ?? 0} требуют проверки</small></div></div>
        </aside>

        <section className="canvas-panel">
          <div className="canvas-toolbar">
            <div className="segmented"><button className={view === "2d" ? "active" : ""} onClick={() => setView("2d")}>2D</button><button className={view === "3d" ? "active" : ""} onClick={() => setView("3d")}>3D</button></div>
            <div className="mode-chip"><span /> CAD local XY</div>
            <div className="toolbar-spacer" />
            <button className="tool-button">Слои</button><button className="tool-button">Измерить</button><button className="primary-button">Запустить анализ</button>
          </div>

          <div className={`drawing-surface view-${view} ${dragging ? "is-dragging" : ""}`}>
            {state === "loading" && <div className="state-card"><i className="loader" /><strong>Собираем сцену</strong><span>Загружаем слои и provenance</span></div>}
            {state === "error" && <div className="state-card error"><strong>Сцена недоступна</strong><span>{error}</span><button onClick={() => location.reload()}>Повторить</button></div>}
            {state === "empty" && <div className="state-card"><strong>В модели пока нет объектов</strong><span>Проверьте импорт и выбранную revision</span></div>}
            {state === "ready" && view === "2d" && (
              <CadCanvas
                features={features}
                sceneKey={featureFrameKey}
                viewport={viewport}
                bearing={bearing}
                visibleLayers={visibleLayers}
                selectedId={selectedId}
                dragging={dragging}
                onCanvasSize={handleCanvasSize}
                onSelect={(id) => { if (!ignoreFeatureClick.current) setSelectedId(id); }}
                onWheel={(event, canvas) => {
                  event.preventDefault();
                  const bounds = canvas.getBoundingClientRect();
                  changeZoom(
                    Math.exp(-event.deltaY * 0.003),
                    {
                      x: event.clientX - bounds.left,
                      y: event.clientY - bounds.top,
                      width: Math.max(bounds.width, 1),
                      height: Math.max(bounds.height, 1),
                    },
                  );
                }}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerLeave={() => setCursorPosition(null)}
              />
            )}
            {state === "ready" && view === "3d" && <div className="three-placeholder"><div className="wire-cube"><i /><i /><i /></div><strong>3D scene contract готов</strong><span>Полный renderer подключается после Phase 2 spike</span></div>}
            {state === "ready" && view === "2d" && <div className="map-controls" aria-label="Управление видом">
              <button onClick={() => changeZoom(2)} aria-label="Приблизить">+</button>
              <button onClick={() => changeZoom(1 / 2)} aria-label="Отдалить">−</button>
              <button onClick={() => setBearing((current) => rotateBearing(current, -15))} aria-label="Повернуть против часовой стрелки">↺</button>
              <button onClick={resetViewport} aria-label="Показать весь план">⌂</button>
              <span>{Math.round(fitViewport.width / viewport.width * 100).toLocaleString("ru-RU")}% · {Math.round(bearing)}° · {features.length.toLocaleString("ru-RU")} объектов{featureLoading ? " · загрузка…" : ""}</span>
            </div>}
            <div className="coordinates">{cursorPosition ? `X ${cursorPosition[0].toFixed(2)}  Y ${cursorPosition[1].toFixed(2)}` : "Перетащите — сдвиг · колесо — масштаб · Shift/ПКМ — поворот"}</div>
          </div>
        </section>

        <aside className="right-panel panel">
          <div className="panel-heading"><span>Инспектор</span><button aria-label="Закрыть выбор" onClick={() => setSelectedId("")}>×</button></div>
          {!selectedObject ? (
            <div className="nothing-selected"><div>⌁</div><strong>Выберите объект</strong><span>Нажмите на геометрию, чтобы увидеть свойства и происхождение.</span></div>
          ) : (
            <div className="inspector-content">
              <div className="object-title"><span className="object-glyph">▰</span><div><p>{selectedObject.class_code}</p><h2>{selectedObject.name ?? selectedObject.stable_key}</h2></div></div>
              <div className="badge-line"><StatusPill status={selectedObject.semantic_status} /><span>{Math.round(selectedObject.confidence * 100)}% confidence</span></div>
              <section className="property-section"><h3>Идентификация</h3><dl><dt>Stable key</dt><dd>{selectedObject.stable_key}</dd><dt>Lifecycle</dt><dd>{selectedObject.lifecycle}</dd><dt>Geometry</dt><dd>{selectedObject.geometry_role}</dd></dl></section>
              {selectedObject.geometry_role === "position" && (
                <section className="property-section"><h3>Посадочное место</h3><div className={`geometry-callout ${selectedAssemblyMemberCount && selectedAssemblyMemberCount > 1 ? "geometry-linked" : "geometry-unmatched"}`}>
                  <strong>{selectedAssemblyMemberCount && selectedAssemblyMemberCount > 1 ? "Составная графика найдена" : "Только маркер положения"}</strong>
                  <span>{selectedAssemblyMemberCount && selectedAssemblyMemberCount > 1
                    ? `В исходном CAD-блоке связано элементов: ${selectedAssemblyMemberCount}. Контур растения отрисовывается вместе с этим маркером.`
                    : "Связанная крона в том же CAD-блоке не найдена. Растение может быть отдельным соседним объектом; связь требует проверки."}</span>
                </div></section>
              )}
              <section className="property-section"><h3>Источник</h3><div className="evidence-card"><strong>{selectedObject.source.path}</strong><span>Слой {selectedObject.source.layer ?? "—"} · handle {selectedObject.source.handle ?? "—"}</span></div></section>
              <section className="property-section"><h3>Evidence <em>{evidence.length}</em></h3>{evidence.length === 0 ? <p className="muted">Нет дополнительных утверждений</p> : evidence.map((item) => <div className={`evidence-row evidence-${item.decision}`} key={item.id}><div><strong>{item.attribute_name ?? item.role}</strong><span>{displayValue(item.asserted_value)}</span></div><StatusPill status={item.decision} /></div>)}</section>
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}
