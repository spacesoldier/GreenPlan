"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type CSSProperties, type InputHTMLAttributes, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";

import type { CadXrefDependency, FidelityFinding, IntakeFile, IntakeProjectDetail } from "@/lib/contracts";
import { domainJson, formatBytes } from "@/lib/domain-client";
import { inspectFolderSelection, isSupportedProjectFile, partitionProjectFiles, relativeUploadPath } from "@/lib/folder-selection";
import { areAllCadLayersClassified, buildCadWorkspaceRoots, buildDeliveryTree, cadCategoryGroups, cadCategoryLabel, clampDockSplit, clampTrayHeight, clampTreeWidth, effectiveFindingSelection, groupLayerFamilies, hostPathParts, layerMatchesReviewMode, projectRelativePath, reviewableLayerSuggestionIds, nextFindingSelection, newlyAssistantClassifiedSuggestionIds, toggleScopedSelection, wizardStepStates, xrefCandidateOptions, type CadDocumentTreeNode, type DeliveryTreeNode } from "@/lib/cad-workbench";

const stateLabels: Record<string, string> = {
  draft: "Черновик", receiving: "Приём файлов", analyzing: "Анализ",
  review_required: "Инженерная проверка", ready_to_publish: "Готов к публикации",
  published: "Опубликован", blocked: "Заблокирован", failed: "Ошибка",
};

const directoryPickerAttributes = {
  webkitdirectory: "",
  directory: "",
} as InputHTMLAttributes<HTMLInputElement>;
const projectFileAccept = ".dwg,.dxf,.xls,.xlsx,.xlsm,.xlsb,.xlt,.xltx,.xltm,.csv,.ods";
const minValuableFileBytes = 10 * 1024;
type PublicationRootRole = "effective_design" | "reference_context" | "historical";
const publicationGroupLabels = { project_solution: "Проектные решения", source_data: "Исходные данные", archive: "Архив" } as const;
const publicationRoleLabels: Record<PublicationRootRole, string> = { effective_design: "Действующее решение", reference_context: "Контекст", historical: "Исторический материал" };

const stageLabels: Record<string, string> = {
  direct_read: "Прямое чтение DWG", conversion: "Конвертация ODA → DXF",
  direct_dwg_read: "Прямое чтение DWG", oda_conversion: "Конвертация ODA → DXF",
  converted_dxf_inventory: "Инвентаризация полученного DXF", uploaded_dxf_inventory: "Инвентаризация загруженного DXF",
  dxf_inventory: "Инвентаризация DXF", xref_resolution: "Разрешение XREF",
  fidelity_check: "Проверка полноты", fidelity_recheck: "Повторное сравнение DWG/DXF", classification: "Классификация",
};

function DeliveryNodes({ nodes, onContextMenu }: { nodes: DeliveryTreeNode[]; onContextMenu: (event: ReactMouseEvent, node: DeliveryTreeNode) => void }) {
  return <>{nodes.map((node) => node.kind === "folder"
    ? <details className="wb-tree-folder" key={node.id} open><summary onContextMenu={(event) => onContextMenu(event, node)}><span>⌄</span>{node.label}<small>{node.children.length}</small></summary><div><DeliveryNodes nodes={node.children} onContextMenu={onContextMenu} /></div></details>
    : <button className="wb-tree-file" key={node.id} onContextMenu={(event) => onContextMenu(event, node)}><span>{node.label.toLocaleLowerCase().endsWith(".dwg") ? "DWG" : node.label.split(".").pop()?.toUpperCase()}</span><b>{node.label}</b></button>)}</>;
}

type FindingGroup = { sourceAssetId: string; label: string; findings: FidelityFinding[] };
function FindingQueue({ groups, selectedId, checkedIds, departingId, revalidatingSourceId, onSelect, onToggle }: { groups: FindingGroup[]; selectedId: string; checkedIds: string[]; departingId: string; revalidatingSourceId: string; onSelect: (id: string) => void; onToggle: (id: string) => void }) {
  return <div className="issue-queue">{groups.map((group) => { const path = hostPathParts(group.label); return <section className={`issue-file-group ${group.sourceAssetId === revalidatingSourceId ? "revalidating" : ""}`} key={group.sourceAssetId}>
    <header><span>{path.file || group.label}</span><small>{path.folder || "Проект"} · {group.findings.length}</small></header>
    {group.findings.map((finding) => <div className={`issue-queue-row ${finding.id === selectedId ? "active" : ""} ${finding.id === departingId ? "departing" : ""}`} key={finding.id}>
      <label title="Добавить проблему в массовое действие"><input type="checkbox" checked={checkedIds.includes(finding.id)} onChange={() => onToggle(finding.id)} /><span>Выбрать</span></label>
      <button className={`issue-${finding.severity}`} onClick={() => onSelect(finding.id)}><i /><span><strong>{finding.title}</strong><small>{finding.code} · {finding.status}</small></span></button>
    </div>)}
  </section>; })}</div>;
}
function ReadableDrawingPath({ path, label = "Для чертежа:" }: { path: string; label?: string }) {
  const host = hostPathParts(path);
  return <div className="xref-host-path finding-source-path"><b>{label}</b><span>{host.leading.map((part, index) => <i key={part + "-" + index}>{part}<em>/</em></i>)}{host.folder && <strong>{host.folder}<em>/</em></strong>}<mark>{host.file}</mark></span></div>;
}

type SelectedCadNode = { kind: "document" | "space" | "layer" | "xref"; id: string };
function XrefResolutionChoices({ xref, files, value, busy, onChange, onResolve }: {
  xref: CadXrefDependency; files: IntakeFile[]; value: string; busy: boolean;
  onChange: (assetId: string) => void; onResolve: () => void;
}) {
  const candidates = xrefCandidateOptions(xref, files);
  const kindLabels = {
    project_solution: "Проектное решение", source_data: "Исходные данные", archive: "Архив",
    survey: "Обследования", other: "Прочее",
  };
  return <section className="xref-resolution-control">
    <header><span>Неоднозначная внешняя ссылка</span><strong>{xref.reference_name}</strong><ReadableDrawingPath path={xref.source_relative_path} /></header>
    <p>Выберите, какую найденную копию подключить к этой конкретной XREF. Система не выбирает файл автоматически.</p>
    <div>{candidates.map(({ path, file, kind, compatible, recommended, recommendationReason }) => {
      const sourceDate = file?.source_modified_at ? new Date(file.source_modified_at).toLocaleString("ru-RU") : null;
      const uploadDate = file?.uploaded_at ? new Date(file.uploaded_at).toLocaleString("ru-RU") : null;
      const className = [file?.id === value ? "selected" : "", recommended ? "recommended" : "", compatible ? "" : "incompatible"].filter(Boolean).join(" ");
      return <label key={path} className={className}>
        <input type="radio" name={`xref-${xref.id}`} value={file?.id || ""} disabled={!file || !compatible} checked={file?.id === value} onChange={() => file && compatible && onChange(file.id)} />
        <span><strong>{path}</strong><small>{kindLabels[kind]} · {file ? `${formatBytes(file.size_bytes)} · SHA ${file.sha256.slice(0, 12)}` : "кандидат отсутствует в текущей поставке"}</small><small>{sourceDate ? `Изменён в источнике: ${sourceDate}` : uploadDate ? `Дата исходника неизвестна · загружен: ${uploadDate}` : "Дата неизвестна"}</small>{!compatible && <em>Недопустим: архивный чертёж может ссылаться только на архивную ветку</em>}{recommended && <em>Рекомендация: {recommendationReason}</em>}</span>
      </label>;
    })}</div>
    <button className="action-primary" disabled={!value || busy} onClick={onResolve}>{busy ? "Проверяем и перезапускаем…" : "Использовать выбранный файл"}</button>
  </section>;
}


function CadDependencyNodes({ nodes, project, layerDocument, selectedCadNode, onDocument, onSpace, onLayer, onXref }: {
  nodes: CadDocumentTreeNode[];
  project: IntakeProjectDetail;
  layerDocument: string;
  selectedCadNode: SelectedCadNode;
  onDocument: (assetId: string) => void;
  onSpace: (assetId: string, spaceId: string) => void;
  onLayer: (assetId: string, layerId: string) => void;
  onXref: (assetId: string, xrefId: string) => void;
}) {
  return <>{nodes.map((node) => {
    const spaces = project.cad_spaces.filter((item) => item.source_asset_id === node.assetId);
    const layers = project.cad_layers.filter((item) => item.source_asset_id === node.assetId);
    const fileName = node.path.split("/").at(-1) || node.path;
    const documentSelected = node.assetId === layerDocument;
    const allLayersClassified = areAllCadLayersClassified(layers);
    return <div className={`cad-dependency-node ${node.via ? "is-xref" : "is-root"}`} key={`${node.via?.id || "root"}-${node.assetId}`}>
      {node.via && <button className="cad-xref-edge ref-resolved" title={node.via.original_path || node.via.reference_name} onClick={() => onXref(node.via!.source_asset_id, node.via!.id)}><span>↳</span><b>{node.via.reference_name}</b><small>XREF</small></button>}
      <details>
        <summary className={`${documentSelected ? "active-document" : ""} ${selectedCadNode.kind === "document" && selectedCadNode.id === node.assetId ? "selected" : ""}`} aria-current={documentSelected ? "true" : undefined} onClick={() => onDocument(node.assetId)} title={node.path}><span>{documentSelected ? "✓" : "DWG"}</span><b>{fileName}</b>{allLayersClassified && <i className="cad-file-ready" title="Все слои файла разобраны" aria-label="Все слои файла разобраны">✓</i>}<small>{node.cycle ? "цикл" : `${spaces.length} лист. · ${layers.length} сл.`}</small></summary>
        {!node.cycle && (node.assetId === layerDocument || !node.via) && <>
          <div className="cad-tree-group"><em>Листы</em>{spaces.map((space) => <button className={selectedCadNode.kind === "space" && selectedCadNode.id === space.id ? "selected" : ""} key={space.id} onClick={() => onSpace(node.assetId, space.id)}><span>{space.space_kind === "model" ? "M" : "Л"}</span><b>{space.name}</b><small>{space.entity_count}</small></button>)}</div>
          <details className="cad-tree-subtree"><summary><b>Слои</b><small>{layers.length}</small></summary><div className="cad-tree-layers">{layers.map((layer) => <button className={selectedCadNode.kind === "layer" && selectedCadNode.id === layer.id ? "selected" : ""} key={layer.id} onClick={() => onLayer(node.assetId, layer.id)}><span>≡</span><b>{layer.name}</b><small title={layer.suggested_category}>{cadCategoryLabel(layer.suggested_category)}</small></button>)}</div></details>
          {node.unresolved.length > 0 && <div className="cad-tree-group cad-missing-refs"><em>Неразрешённые XREF</em>{node.unresolved.map((xref) => <button className={`ref-${xref.status} ${selectedCadNode.kind === "xref" && selectedCadNode.id === xref.id ? "selected" : ""}`} key={xref.id} title={xref.original_path || ""} onClick={() => onXref(node.assetId, xref.id)}><span>?</span><b>{xref.reference_name}</b><small>{xref.status === "ambiguous" ? <>неоднозначно · {xref.matches.length} вариантов</> : xref.status === "missing" ? "файл не найден" : xref.status}</small></button>)}</div>}
          {node.children.length > 0 && <div className="cad-xref-children"><em>Подключённые DWG</em><CadDependencyNodes nodes={node.children} project={project} layerDocument={layerDocument} selectedCadNode={selectedCadNode} onDocument={onDocument} onSpace={onSpace} onLayer={onLayer} onXref={onXref} /></div>}
        </>}
      </details>
    </div>;
  })}</>;
}

export function ProjectIntake({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<IntakeProjectDetail | null>(null);
  const projectRef = useRef<IntakeProjectDetail | null>(null);
  const commandbarRef = useRef<HTMLElement | null>(null);
  const [commandbarHeight, setCommandbarHeight] = useState(116);
  const [selectedPublicationRoots, setSelectedPublicationRoots] = useState<Record<string, PublicationRootRole>>({});
  const [layerDocument, setLayerDocument] = useState("");
  const [layerQuery, setLayerQuery] = useState("");
  const [layerMode, setLayerMode] = useState<"all" | "unknown" | "reviewed">("all");
  const layerModeRef = useRef(layerMode);
  const [workbenchView, setWorkbenchView] = useState<"materials" | "explorer" | "publish">("materials");
  const [activeStep, setActiveStep] = useState(0);
  const [treeWidth, setTreeWidth] = useState(360);
  const [selectedCadNode, setSelectedCadNode] = useState<SelectedCadNode>({ kind: "document", id: "" });
  const [selectedLayerIds, setSelectedLayerIds] = useState<string[]>([]);
  const [departingLayerIds, setDepartingLayerIds] = useState<string[]>([]);
  const [bulkCategory, setBulkCategory] = useState("unknown");
  const [selectedFindingId, setSelectedFindingId] = useState("");
  const [checkedFindingIds, setCheckedFindingIds] = useState<string[]>([]);
  const [bulkFindingAction, setBulkFindingAction] = useState<"waive" | "block">("waive");
  const [findingReason, setFindingReason] = useState("Ограничение принято для текущей редакции.");
  const [dockExpanded, setDockExpanded] = useState(true);
  const [dockTab, setDockTab] = useState<"issues" | "activity">("activity");
  const [dockHeight, setDockHeight] = useState(320);
  const [dockSplit, setDockSplit] = useState(560);
  const [selectedActivityId, setSelectedActivityId] = useState("");
  const [comment, setComment] = useState("Проверено инженером; ограничения преобразования приняты.");
  const [busy, setBusy] = useState("");
  const [uploadProgress, setUploadProgress] = useState<[number, number] | null>(null);
  const [uploadNote, setUploadNote] = useState("");
  const [liveUpload, setLiveUpload] = useState<{ state: string; title: string; detail: string; at: string } | null>(null);
  const [error, setError] = useState("");
  const [xrefTargetId, setXrefTargetId] = useState("");
  const [departingFindingId, setDepartingFindingId] = useState("");
  const [revalidatingSourceId, setRevalidatingSourceId] = useState("");
  const [resolutionNotice, setResolutionNotice] = useState("");
  const [deliveryMenu, setDeliveryMenu] = useState<{ x: number; y: number; node: DeliveryTreeNode } | null>(null);

  useEffect(() => { layerModeRef.current = layerMode; }, [layerMode]);

  useEffect(() => {
    const node = commandbarRef.current;
    if (!node) return;
    const measure = () => setCommandbarHeight(Math.ceil(node.getBoundingClientRect().height));
    measure();
    window.addEventListener("resize", measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    return () => { window.removeEventListener("resize", measure); observer?.disconnect(); };
  }, []);

  const load = useCallback(async () => {
    const next = await domainJson<IntakeProjectDetail>(`/v1/intake/projects/${projectId}`);
    const previous = projectRef.current;
    projectRef.current = next;
    const assistantDepartingIds = previous && layerModeRef.current === "unknown"
      ? newlyAssistantClassifiedSuggestionIds(previous.cad_layers, next.cad_layers)
      : [];
    if (assistantDepartingIds.length) {
      setDepartingLayerIds((current) => Array.from(new Set([...current, ...assistantDepartingIds])));
      await new Promise((resolve) => window.setTimeout(resolve, 460));
    }
    setProject(next);
    const cadFiles = next.files.filter((file) => file.size_bytes > minValuableFileBytes && ["dwg", "dxf"].includes(file.detected_format || file.relative_path.split(".").at(-1)?.toLocaleLowerCase() || ""));
    const cadAssetIds = new Set(cadFiles.map((item) => item.id));
    next.cad_layers.forEach((item) => cadAssetIds.add(item.source_asset_id));
    const fallbackDocument = next.publication_roots[0]?.source_asset_id || next.master_candidates[0]?.source_asset_id || next.cad_layers[0]?.source_asset_id || cadFiles[0]?.id || "";
    setSelectedPublicationRoots((current) => {
      const validIds = new Set(next.publication_roots.map((item) => item.source_asset_id));
      const validCurrent = Object.fromEntries(Object.entries(current).filter(([id]) => validIds.has(id))) as Record<string, PublicationRootRole>;
      if (Object.keys(validCurrent).length) return validCurrent;
      const persisted = Object.fromEntries(next.publication_roots.filter((item) => item.selected).map((item) => [item.source_asset_id, item.selected_role || item.default_role])) as Record<string, PublicationRootRole>;
      if (Object.keys(persisted).length) return persisted;
      const preferred = next.publication_roots.find((item) => item.workspace_kind === "project_solution") || next.publication_roots[0];
      return preferred ? { [preferred.source_asset_id]: preferred.default_role } : {};
    });
    setLayerDocument((current) => cadAssetIds.has(current) ? current : fallbackDocument);
    setSelectedCadNode((current) => current.kind === "document" && !cadAssetIds.has(current.id) ? { kind: "document", id: fallbackDocument } : current.id ? current : { kind: "document", id: fallbackDocument });
    if (assistantDepartingIds.length) {
      setDepartingLayerIds((current) => current.filter((id) => !assistantDepartingIds.includes(id)));
    }
    return next;
  }, [projectId]);

  const assistantPollingActive = project?.assistant_runs?.some((run) => ["queued", "running"].includes(run.state)) ?? false;
  const semanticPollingActive = project?.semantic_suggestion_jobs?.some((job) => ["queued", "running"].includes(job.state)) ?? false;

  useEffect(() => {
    load().catch((reason: Error) => setError(reason.message));
  }, [load]);

  useEffect(() => {
    if (project?.intake_state !== "analyzing" && !assistantPollingActive && !semanticPollingActive) return;
    let cancelled = false;
    let timer = 0;
    const poll = async () => {
      try { await load(); }
      catch { /* A later poll can recover from a transient refresh failure. */ }
      finally { if (!cancelled) timer = window.setTimeout(poll, 1000); }
    };
    timer = window.setTimeout(poll, 350);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [load, project?.intake_state, assistantPollingActive, semanticPollingActive]);

  useEffect(() => {
    const close = () => setDeliveryMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("blur", close);
    return () => { window.removeEventListener("click", close); window.removeEventListener("blur", close); };
  }, []);

  useEffect(() => {
    const saved = Number(window.localStorage.getItem("greenplan.intake.tray-height"));
    if (Number.isFinite(saved) && saved > 0) setDockHeight(clampTrayHeight(saved, window.innerHeight));
    const savedDockSplit = Number(window.localStorage.getItem("greenplan.intake.dock-split"));
    if (Number.isFinite(savedDockSplit) && savedDockSplit > 0) setDockSplit(clampDockSplit(savedDockSplit, window.innerWidth));
    const savedTreeWidth = Number(window.localStorage.getItem("greenplan.intake.tree-width"));
    if (Number.isFinite(savedTreeWidth) && savedTreeWidth > 0) setTreeWidth(clampTreeWidth(savedTreeWidth, window.innerWidth));
  }, []);

  function beginDockResize(event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDockExpanded(true);
    const startY = event.clientY;
    const startHeight = dockHeight;
    const move = (pointer: PointerEvent) => setDockHeight(clampTrayHeight(startHeight + startY - pointer.clientY, window.innerHeight));
    const finish = (pointer: PointerEvent) => {
      const value = clampTrayHeight(startHeight + startY - pointer.clientY, window.innerHeight);
      setDockHeight(value);
      window.localStorage.setItem("greenplan.intake.tray-height", String(value));
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
  }

  function beginTreeResize(event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = treeWidth;
    const move = (pointer: PointerEvent) => setTreeWidth(clampTreeWidth(startWidth + pointer.clientX - startX, window.innerWidth));
    const finish = (pointer: PointerEvent) => {
      const value = clampTreeWidth(startWidth + pointer.clientX - startX, window.innerWidth);
      setTreeWidth(value);
      window.localStorage.setItem("greenplan.intake.tree-width", String(value));
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
  }

  function beginDockSplitResize(event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = dockSplit;
    const move = (pointer: PointerEvent) => setDockSplit(clampDockSplit(startWidth + pointer.clientX - startX, window.innerWidth));
    const finish = (pointer: PointerEvent) => {
      const value = clampDockSplit(startWidth + pointer.clientX - startX, window.innerWidth);
      setDockSplit(value);
      window.localStorage.setItem("greenplan.intake.dock-split", String(value));
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", finish);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", finish);
  }

  async function upload(files: FileList | null, mode: "folder" | "files") {
    if (!files?.length) return;
    const selected = Array.from(files);
    if (mode === "folder") {
      const selection = inspectFolderSelection(selected);
      if (!selection.valid) {
        setError("Браузер открыл обычный выбор файлов и не передал структуру каталога. Используйте Chromium/Chrome/Edge или кнопку «Добавить отдельные файлы».");
        return;
      }
    }
    const { supported, skipped } = partitionProjectFiles(selected);
    if (!supported.length) {
      setError("В выбранном наборе нет поддерживаемых DWG, DXF или табличных файлов Excel.");
      return;
    }
    const skippedNote = skipped.length ? ` Пропущено неподдерживаемых файлов: ${skipped.length}.` : "";
    if (mode === "folder") {
      const selection = inspectFolderSelection(selected);
      setUploadNote(`Каталог «${selection.root}»: к загрузке ${supported.length} из ${selection.fileCount} файлов. Относительные пути сохраняются.${skippedNote}`);
    } else {
      setUploadNote(`${supported.length} отдельных файлов будут помещены в корень поставки. XREF ищутся только внутри уже загруженного набора.${skippedNote}`);
    }
    setBusy("upload"); setError(""); setUploadProgress([0, supported.length]);
    setLiveUpload({ state: "running", title: "Загрузка поставки", detail: `Подготовлено файлов: ${supported.length}`, at: new Date().toISOString() });
    try {
      for (let index = 0; index < supported.length; index += 1) {
        const current = supported[index];
        setLiveUpload({ state: "running", title: `Загрузка ${index + 1} из ${supported.length}`, detail: relativeUploadPath(current), at: new Date().toISOString() });
        const form = new FormData();
        form.set("relative_path", relativeUploadPath(current));
        form.set("last_modified_ms", String(current.lastModified));
        form.set("file", current);
        await domainJson(`/v1/intake/projects/${projectId}/files`, { method: "POST", body: form });
        setUploadProgress([index + 1, supported.length]);
      }
      await load();
      setLiveUpload({ state: "completed", title: "Загрузка завершена", detail: `${supported.length} файлов принято${skipped.length ? `, ${skipped.length} пропущено` : ""}`, at: new Date().toISOString() });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ошибка загрузки");
      setLiveUpload({ state: "failed", title: "Ошибка загрузки", detail: reason instanceof Error ? reason.message : "Операция прервана", at: new Date().toISOString() });
    } finally {
      setBusy(""); setUploadProgress(null);
    }
  }

  function openDeliveryMenu(event: ReactMouseEvent, node: DeliveryTreeNode) {
    event.preventDefault();
    event.stopPropagation();
    setDeliveryMenu({
      node,
      x: Math.min(event.clientX, window.innerWidth - 250),
      y: Math.min(event.clientY, window.innerHeight - 110),
    });
  }

  async function removeDeliveryNode(node: DeliveryTreeNode) {
    setDeliveryMenu(null);
    const subject = node.kind === "folder" ? `папку «${node.label}» и все вложенные файлы` : `файл «${node.label}»`;
    if (!window.confirm(`Удалить ${subject} из проекта? Исходные файлы на вашем диске останутся без изменений.`)) return;
    setBusy("delete-delivery-path"); setError("");
    try {
      await domainJson(`/v1/intake/projects/${projectId}/files?relative_path=${encodeURIComponent(node.relativePath)}`, { method: "DELETE" });
      await load();
      setLiveUpload({ state: "completed", title: "Материал исключён из проекта", detail: node.relativePath, at: new Date().toISOString() });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось удалить материал из проекта");
    } finally {
      setBusy("");
    }
  }

  async function action(name: string, path: string, init?: RequestInit) {
    setBusy(name); setError("");
    try { await domainJson(path, { method: "POST", ...init }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Операция не выполнена"); }
    finally { setBusy(""); }
  }

  async function reviewSelectedLayers(decision: "accept" | "reject") {
    if (!selectedLayerIds.length) return;
    const reviewedIds = [...selectedLayerIds];
    const shouldDepart = decision === "accept" && layerMode === "unknown" && bulkCategory !== "unknown";
    setBusy("batch-classification"); setError("");
    if (shouldDepart) setDepartingLayerIds(reviewedIds);
    try {
      await Promise.all([
        domainJson(`/v1/intake/projects/${projectId}/classifications/batch-review`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ suggestion_ids: reviewedIds, decision, category: decision === "accept" ? bulkCategory : null, comment: "Массовая проверка в CAD workbench" }),
        }),
        shouldDepart ? new Promise((resolve) => window.setTimeout(resolve, 460)) : Promise.resolve(),
      ]);
      await load();
      setSelectedLayerIds((current) => current.filter((id) => !reviewedIds.includes(id)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось назначить категорию");
    } finally {
      setDepartingLayerIds([]);
      setBusy("");
    }
  }

  async function resolveSelectedFinding(actionName: "waive" | "reopen" | "block") {
    const findingId = effectiveFindingSelection(project?.findings || [], selectedFindingId);
    if (!findingId) return;
    if (actionName !== "waive") {
      await action("finding-resolution", `/v1/intake/projects/${projectId}/findings/${findingId}/resolve`, {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: actionName, reason: findingReason }),
      });
      return;
    }
    const finding = project?.findings.find((item) => item.id === findingId);
    const findingsBefore = project?.findings || [];
    setBusy("finding-resolution"); setError(""); setResolutionNotice("Фиксируем решение…");
    try {
      const result = await domainJson<{ source_complete: boolean; remaining_issues: number; revalidation_state: string | null }>(`/v1/intake/projects/${projectId}/findings/${findingId}/resolve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: actionName, reason: findingReason }),
      });
      setDepartingFindingId(findingId);
      if (result.source_complete && finding?.source_asset_id) setRevalidatingSourceId(finding.source_asset_id);
      setResolutionNotice(result.source_complete ? "Все проблемы файла закрыты · повторная проверка завершена" : `Решение принято · осталось проблем: ${result.remaining_issues}`);
      await new Promise((resolve) => window.setTimeout(resolve, 520));
      const updated = await load();
      setSelectedFindingId(finding ? nextFindingSelection(findingsBefore, updated.findings, finding.id) : "");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось сохранить решение"); }
    finally { setBusy(""); setDepartingFindingId(""); setRevalidatingSourceId(""); }
  }
  async function resolveCheckedFindings() {
    if (!checkedFindingIds.length) return;
    const ids = [...checkedFindingIds];
    setBusy("bulk-finding-resolution"); setError(""); setResolutionNotice(`Применяем решение к ${ids.length} проблемам…`);
    const failed: string[] = [];
    for (const findingId of ids) {
      try {
        await domainJson(`/v1/intake/projects/${projectId}/findings/${findingId}/resolve`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: bulkFindingAction, reason: findingReason }),
        });
      } catch { failed.push(findingId); }
    }
    try {
      const updated = await load();
      const remaining = updated.findings.filter((item) => ["open", "rejected"].includes(item.status));
      setCheckedFindingIds(failed);
      if (!remaining.some((item) => item.id === selectedFindingId)) setSelectedFindingId(remaining[0]?.id || "");
      if (failed.length) {
        setError(`Не удалось обработать ${failed.length} из ${ids.length} проблем. Они остались выбранными.`);
        setResolutionNotice(`Применено: ${ids.length - failed.length} · ошибок: ${failed.length}`);
      } else setResolutionNotice(`Решение применено к ${ids.length} проблемам`);
    } finally { setBusy(""); }
  }


  async function resolveSelectedXref(xref: CadXrefDependency) {
    if (!xrefTargetId) return;
    const finding = project?.findings.find((item) => item.status === "open" && item.source_asset_id === xref.source_asset_id && item.code === "xref_ambiguous" && (((item.evidence.xref as { path?: string; name?: string } | undefined)?.path === xref.original_path) || ((item.evidence.xref as { path?: string; name?: string } | undefined)?.name === xref.reference_name)));
    const findingsBefore = project?.findings || [];
    setBusy("resolve-xref"); setError(""); setResolutionNotice("Проверяем выбранную связь…");
    try {
      const result = await domainJson<{ source_complete: boolean; remaining_issues: number; revalidation_state: string | null }>(`/v1/intake/projects/${projectId}/xrefs/${xref.id}/resolve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_asset_id: xrefTargetId }),
      });
      if (finding) setDepartingFindingId(finding.id);
      if (result.source_complete) setRevalidatingSourceId(xref.source_asset_id);
      setResolutionNotice(result.source_complete ? "Связи и сравнение DWG/DXF проверены заново · XREF-проблем не осталось" : `Связь сохранена · осталось XREF-проблем: ${result.remaining_issues}`);
      await new Promise((resolve) => window.setTimeout(resolve, 520));
      const updated = await load();
      setSelectedFindingId(finding ? nextFindingSelection(findingsBefore, updated.findings, finding.id) : "");
      setXrefTargetId("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось разрешить XREF"); }
    finally { setBusy(""); setDepartingFindingId(""); setRevalidatingSourceId(""); }
  }

  if (!project) return <main className="intake-loading"><span className="loader" /><strong>{error || "Открываем проект…"}</strong></main>;
  const assistantRun = project.assistant_runs[0];
  const assistantActive = assistantRun && ["queued", "running"].includes(assistantRun.state);
  const assistantTaskCount = assistantRun?.tasks.length || 0;
  const assistantCompletedCount = assistantRun?.tasks.filter((task) => ["completed", "completed_with_warnings"].includes(task.state)).length || 0;
  const assistantCurrentTask = assistantRun?.tasks.find((task) => task.state === "running")
    || assistantRun?.tasks.find((task) => task.state === "pending");
  const assistantWaitingForConversions = assistantRun?.summary?.waiting_for === "conversion_workers";
  const assistantProgressPercent = Math.max(0, Math.min(100, Math.round((assistantRun?.progress || 0) * 100)));
  const assistantProgressTitle = assistantWaitingForConversions ? "Ожидаем конвертеры и сверку файлов"
    : assistantCurrentTask?.title || "Формируем итоговую очередь проверки";
  const publicationRootSelections = Object.entries(selectedPublicationRoots).map(([source_asset_id, role]) => ({ source_asset_id, role }));
  const selectedRootCandidates = project.publication_roots.filter((item) => selectedPublicationRoots[item.source_asset_id]);
  const persistedRootSelections = project.publication_roots.filter((item) => item.selected).map((item) => ({ source_asset_id: item.source_asset_id, role: item.selected_role || item.default_role })).sort((a, b) => a.source_asset_id.localeCompare(b.source_asset_id));
  const normalizedRootSelections = [...publicationRootSelections].sort((a, b) => a.source_asset_id.localeCompare(b.source_asset_id));
  const publicationSelectionDirty = JSON.stringify(persistedRootSelections) !== JSON.stringify(normalizedRootSelections);
  const publicationGroups = (["project_solution", "source_data", "archive"] as const).map((kind) => ({
    kind, label: publicationGroupLabels[kind], roots: project.publication_roots.filter((item) => item.workspace_kind === kind),
  })).filter((group) => group.roots.length);
  const mayReview = ["review_required", "ready_to_publish"].includes(project.intake_state)
    && publicationRootSelections.length > 0
    && publicationRootSelections.some((item) => item.role === "effective_design")
    && selectedRootCandidates.every((item) => item.unresolved_count === 0 && item.critical_count === 0);
  const xrefsBySource = project.xref_dependencies.reduce((result, xref) => {
    const values = result.get(xref.source_asset_id) || [];
    values.push(xref); result.set(xref.source_asset_id, values); return result;
  }, new Map<string, typeof project.xref_dependencies>());
  const filePathById = new Map(project.files.map((file) => [file.id, file.relative_path]));
  const visibleFiles = project.files.filter((file) => file.size_bytes > minValuableFileBytes && isSupportedProjectFile({ name: file.relative_path }));
  const visibleBytes = visibleFiles.reduce((total, file) => total + file.size_bytes, 0);
  const mayAnalyze = visibleFiles.length > 0 && !["analyzing", "published"].includes(project.intake_state);
  const convertedByAsset = new Map(project.inventories
    .filter((item) => item.stage === "converted_dxf" && item.artifact_locator)
    .map((item) => [item.source_asset_id, item.artifact_locator]));
  const activityEvents = [
    ...(liveUpload ? [{ id: "live-upload", state: liveUpload.state, title: liveUpload.title, detail: liveUpload.detail, at: liveUpload.at, metrics: {}, stdout: "", stderr: "" }] : []),
    ...project.stages.map((stage) => ({
      id: stage.id,
      state: stage.state,
      title: stageLabels[stage.stage] || stage.stage.replaceAll("_", " "),
      detail: `${filePathById.get(stage.source_asset_id || "") || "Весь проект"} · попытка ${stage.attempt_no}${convertedByAsset.get(stage.source_asset_id || "") ? ` · ${convertedByAsset.get(stage.source_asset_id || "")}` : ""}`,
      at: stage.finished_at || stage.started_at || stage.created_at,
      metrics: stage.metrics, stdout: stage.stdout, stderr: stage.stderr,
    })),
    ...(assistantRun?.tasks || []).map((task) => ({
      id: `task-${task.id}`, state: task.state, title: task.title,
      detail: task.error_summary || `Попыток: ${task.attempts} · ${Math.round(task.progress * 100)}%`,
      at: task.finished_at || task.started_at || assistantRun.created_at,
      metrics: { progress: task.progress, attempts: task.attempts, dependencies: task.dependencies }, stdout: "", stderr: task.error_summary || "",
    })),
    ...(project.semantic_suggestion_jobs || []).map((job) => ({
      id: `semantic-${job.id}`, state: job.state, title: "Нейросетевая классификация слоёв",
      detail: `${filePathById.get(job.source_asset_id) || "CAD-документ"} · ${job.completed_count}/${job.total_count}${job.failed_count ? ` · ошибок ${job.failed_count}` : ""}`,
      at: job.finished_at || job.heartbeat_at || job.started_at || job.created_at,
      metrics: { provider: job.provider, model: job.model, total: job.total_count, completed: job.completed_count, failed: job.failed_count },
      stdout: "", stderr: job.error_summary || "",
    })),
  ].sort((left, right) => Date.parse(right.at) - Date.parse(left.at)).slice(0, 40);
  const cadDocumentsById = new Map(project.files
    .filter((file) => file.size_bytes > minValuableFileBytes && ["dwg", "dxf"].includes(file.detected_format || file.relative_path.split(".").at(-1)?.toLocaleLowerCase() || ""))
    .map((file) => [file.id, file.relative_path]));
  project.cad_layers.forEach((layer) => cadDocumentsById.set(layer.source_asset_id, layer.source_relative_path));
  const layerDocuments = Array.from(cadDocumentsById.entries());
  const cadWorkspaceRoots = buildCadWorkspaceRoots(layerDocuments, project.xref_dependencies);
  const selectedSpaces = project.cad_spaces.filter((space) => space.source_asset_id === layerDocument);
  const unclassifiedLayerCount = project.cad_layers.filter((layer) =>
    layer.source_asset_id === layerDocument && layer.mapping_status !== "confirmed"
  ).length;
  const selectedLayers = project.cad_layers.filter((layer) => {
    if (layer.source_asset_id !== layerDocument) return false;
    if (!layerMatchesReviewMode(layer, layerMode)) return false;
    return !layerQuery || layer.name.toLocaleLowerCase().includes(layerQuery.toLocaleLowerCase());
  });
  const deliveryTree = buildDeliveryTree(visibleFiles);
  const layerFamilies = [...groupLayerFamilies(selectedLayers).entries()];
  const visibleLayerSuggestionIds = Array.from(new Set(reviewableLayerSuggestionIds(selectedLayers)));
  const allVisibleLayersSelected = visibleLayerSuggestionIds.length > 0
    && visibleLayerSuggestionIds.every((id) => selectedLayerIds.includes(id));
  const someVisibleLayersSelected = visibleLayerSuggestionIds.some((id) => selectedLayerIds.includes(id));
  const actionableFindings = project.findings.filter((finding) => ["open", "rejected"].includes(finding.status));
  const findingGroups = [...actionableFindings.reduce((groups, finding) => {
    const key = finding.source_asset_id || "project";
    const values = groups.get(key) || [];
    values.push(finding); groups.set(key, values); return groups;
  }, new Map<string, typeof actionableFindings>()).entries()].map(([sourceAssetId, findings]) => ({
    sourceAssetId, label: filePathById.get(sourceAssetId) || "Проблемы проекта", findings,
  }));
  const effectiveSelectedFindingId = effectiveFindingSelection(actionableFindings, selectedFindingId);
  const selectedFinding = actionableFindings.find((finding) => finding.id === effectiveSelectedFindingId);
  const sameKindFindings = selectedFinding ? actionableFindings.filter((finding) => finding.code === selectedFinding.code) : [];
  const allSameKindChecked = sameKindFindings.length > 0 && sameKindFindings.every((finding) => checkedFindingIds.includes(finding.id));
  const selectedFindingInventories = project.inventories.filter((item) => item.source_asset_id === selectedFinding?.source_asset_id);
  const selectedActivity = activityEvents.find((event) => event.id === selectedActivityId) || activityEvents[0];
  const selectedLayer = project.cad_layers.find((layer) => selectedCadNode.kind === "layer" && layer.id === selectedCadNode.id);
  const selectedXref = project.xref_dependencies.find((xref) => selectedCadNode.kind === "xref" && xref.id === selectedCadNode.id);
  const findingXrefEvidence = selectedFinding?.evidence?.xref as { name?: string; path?: string } | undefined;
  const selectedFindingXref = selectedFinding?.code === "xref_ambiguous"
    ? project.xref_dependencies.find((xref) => xref.source_asset_id === selectedFinding.source_asset_id
      && (xref.original_path === findingXrefEvidence?.path || xref.reference_name === findingXrefEvidence?.name))
    : undefined;
  const selectedSpace = project.cad_spaces.find((space) => selectedCadNode.kind === "space" && space.id === selectedCadNode.id)
    || selectedSpaces[0];
  const semanticJob = project.semantic_suggestion_jobs?.find((job) => job.source_asset_id === layerDocument);
  const activeSemanticJob = project.semantic_suggestion_jobs?.find((job) => ["queued", "running"].includes(job.state));
  const semanticActive = semanticJob && ["queued", "running"].includes(semanticJob.state);
  const semanticBusyElsewhere = !!activeSemanticJob && activeSemanticJob.source_asset_id !== layerDocument;
  const openFindingCount = project.findings.filter((item) => item.status === "open").length;
  const stepStates = wizardStepStates({
    fileCount: visibleFiles.length, cadCount: project.cad_count,
    cadAnalyzed: ["review_required", "ready_to_publish", "published"].includes(project.intake_state),
    openFindings: openFindingCount,
    reviewAccepted: ["ready_to_publish", "published"].includes(project.intake_state),
    published: project.intake_state === "published",
  });

  function selectDocument(assetId: string) {
    setLayerDocument(assetId);
    setSelectedCadNode({ kind: "document", id: assetId });
  }

  function openWizardStep(step: number) {
    setActiveStep(step);
    if (step === 0) setWorkbenchView("materials");
    if (step === 1) setWorkbenchView("explorer");
    if (step === 2) { setWorkbenchView("explorer"); setDockTab("issues"); setDockExpanded(true); }
    if (step === 3) setWorkbenchView("publish");
  }

  return (
    <main className="intake-page" style={{ "--tray-height": `${dockHeight}px`, "--tree-width": `${treeWidth}px`, "--dock-list-width": `${dockSplit}px`, "--commandbar-height": `${commandbarHeight}px` } as CSSProperties}>
      <header className="intake-topbar">
        <Link className="brand-lockup compact" href="/"><span className="brand-mark">G</span><span><strong>GreenPlan</strong><small>Проекты</small></span></Link>
        <nav><Link href="/">Все проекты</Link><span>/</span><strong>{project.title}</strong></nav>
        {project.current_model_id && <Link className="open-model-link" href={`/workspace?project=${project.id}`}>Открыть модель ↗</Link>}
      </header>

      <section className="intake-commandbar" ref={commandbarRef}>
        <div className="intake-project-heading"><span className="eyebrow">{project.code} · редакция {project.revision_no}</span><h1>{project.title}</h1><p>{project.description || "Описание проекта пока не заполнено."}</p></div>
        <nav className="preparation-wizard" aria-label="Этапы подготовки проекта">
          {[
            ["Материалы", `${visibleFiles.length} файлов`],
            ["CAD-разбор", `${project.cad_layers.length} слоёв`],
            ["Проверка", openFindingCount ? `${openFindingCount} проблем` : "нет открытых проблем"],
            ["Публикация", project.intake_state === "published" ? "модель опубликована" : "конечная цель"],
          ].map(([title, detail], index) => <button key={title} className={`${stepStates[index]} ${activeStep === index ? "active" : ""}`} onClick={() => openWizardStep(index)}><i>{stepStates[index] === "complete" ? "✓" : index + 1}</i><span><b>{title}</b><small>{detail}</small></span></button>)}
        </nav>
        <div className="intake-hero-status"><span className={`intake-state state-${project.intake_state}`}>{stateLabels[project.intake_state] ?? project.intake_state}</span><strong>{visibleFiles.length}</strong><small>файлов · {formatBytes(visibleBytes)}</small></div>
      </section>

      <section className="intake-layout workbench-layout">
        <div className="intake-main">
          {workbenchView === "materials" && <>
          <article className="intake-card upload-card">
            <div className="card-heading"><div><span>01</span><h2>Исходные материалы</h2></div><p>Структура папок и контрольные суммы сохраняются как доказательство поставки.</p></div>
            <div className="upload-actions">
              <label className="upload-drop"><input {...directoryPickerAttributes} accept={projectFileAccept} type="file" multiple onChange={(event) => upload(event.target.files, "folder")} /><b>＋</b><strong>Загрузить папку проекта</strong><span>DWG, DXF и таблицы; вложенные пути сохраняются</span></label>
              <label className="upload-file"><input accept={projectFileAccept} type="file" multiple onChange={(event) => upload(event.target.files, "files")} />Добавить отдельные файлы</label>
            </div>
            <p className="upload-explainer"><strong>Папка:</strong> сохраняем дерево и ищем XREF по относительному пути, затем по имени. <strong>Отдельные файлы:</strong> кладём в корень; зависимости из соседних папок сами не загружаются.</p>
            {uploadNote && <p className="upload-note">{uploadNote}</p>}
            {uploadProgress && <div className="upload-progress"><i style={{ width: `${uploadProgress[0] / uploadProgress[1] * 100}%` }} /><span>{uploadProgress[0]} / {uploadProgress[1]}</span></div>}
            <div className="file-list">
              {visibleFiles.length === 0 ? <p className="empty-line">Поддерживаемые файлы ещё не загружены</p> : visibleFiles.map((file) => (
                <div className="file-row" key={file.id}><span className={`file-kind kind-${file.detected_format}`}>{(file.detected_format && file.detected_format !== "unknown" ? file.detected_format : file.relative_path.split(".").pop() || "file").toUpperCase()}</span><div><strong>{file.relative_path}</strong><small>{formatBytes(file.size_bytes)} · {file.sha256.slice(0, 12)} · {file.role?.replaceAll("_", " ") || "не разобран"}</small></div><em>{file.format_version || "—"}</em></div>
              ))}
            </div>
          </article>

          <article className="intake-card">
            <div className="card-heading"><div><span>02</span><h2>Контролируемый анализ</h2></div><p>Прямое чтение DWG, fallback через ODA, инвентаризация DXF и проверка внешних ссылок.</p></div>
            <div className="analysis-scope"><b>Область поиска</b><span>Текущая поставка: {visibleFiles.length} рабочих файлов. Файлы не более 10 КиБ скрыты как служебный шум; серверный dataset и чужие проекты не просматриваются автоматически.</span></div>
            <button className="action-primary analyze-button" disabled={!mayAnalyze || !!busy || !!assistantActive} onClick={() => action("assistant", `/v1/intake/projects/${projectId}/assistant-runs`)}>{assistantActive ? "Ассистент выполняет разбор…" : "Запустить ассистента поставки"}</button>
            {assistantRun && <section className="assistant-run" aria-label="Ход работы ассистента">
              <header><div><strong>{assistantRun.state.replaceAll("_", " ")}</strong><small>{assistantRun.taxonomy_version} · {assistantRun.provider_version} · {assistantRun.input_fingerprint.slice(0, 10)}</small></div><b>{Math.round(assistantRun.progress * 100)}%</b></header>
              <div className="assistant-progress"><i style={{ width: `${assistantRun.progress * 100}%` }} /></div>
              <ol>{assistantRun.tasks.map((task) => <li key={task.id} className={`assistant-task task-${task.state}`}><i /><div><strong>{task.title}</strong><small>{task.error_summary || `${task.state.replaceAll("_", " ")} · попыток ${task.attempts}`}</small></div></li>)}</ol>
            </section>}
            <div className="stage-list">
              {project.stages.length === 0 ? <p className="empty-line">После запуска здесь появится журнал этапов.</p> : project.stages.map((stage) => (
                <details className="stage-row" key={stage.id}><summary><i className={`stage-dot stage-${stage.state}`} /><div><strong>{stageLabels[stage.stage] || stage.stage.replaceAll("_", " ")}</strong><small>{filePathById.get(stage.source_asset_id || "") || "Весь проект"} · {stage.error_summary || `${Math.round(stage.progress * 100)}% · попытка ${stage.attempt_no} · ${Object.entries(stage.metrics || {}).slice(0, 3).map(([key, value]) => `${key}: ${String(value)}`).join(" · ")}`}</small></div><span>{stage.state.replaceAll("_", " ")}</span></summary>{(stage.stderr || stage.stdout) && <pre>{stage.stderr || stage.stdout}</pre>}</details>
              ))}
            </div>
          </article>
          </>}

          {workbenchView === "explorer" && <article className="intake-card cad-inspector">
            <div className="card-heading"><div><span>02</span><h2>Инспектор CAD</h2></div><p>Выберите документ, лист, слой или XREF в дереве слева. Ассистент назначает класс неразобранным слоям; любое решение можно исправить вручную.</p></div>
            <div className="document-context"><div><span>Документ</span><strong title={layerDocuments.find(([id]) => id === layerDocument)?.[1]}>{projectRelativePath(layerDocuments.find(([id]) => id === layerDocument)?.[1] || "Документ не выбран")}</strong></div><div className="xref-summary"><span><b>{(xrefsBySource.get(layerDocument) || []).length}</b> XREF</span><span><b>{selectedSpaces.length}</b> листов</span><span><b>{project.cad_layers.filter((item) => item.source_asset_id === layerDocument).length}</b> слоёв</span></div><button className="ai-suggest-button" disabled={!layerDocument || unclassifiedLayerCount === 0 || !!semanticPollingActive || !!busy} title={unclassifiedLayerCount === 0 ? "Все слои этого файла уже имеют выбранный класс" : semanticBusyElsewhere ? `Сейчас обрабатывается: ${filePathById.get(activeSemanticJob!.source_asset_id) || "другой CAD-файл"}` : `Ассистент назначит класс ${unclassifiedLayerCount} неразобранным слоям открытого файла`} onClick={() => action("semantic-suggest", `/v1/intake/projects/${projectId}/semantic-suggestion-jobs`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_asset_id: layerDocument }) })}>{semanticActive ? `Этот файл · ${semanticJob?.completed_count || 0}/${semanticJob?.total_count || 0}` : semanticBusyElsewhere ? "Модель занята другим файлом" : unclassifiedLayerCount === 0 ? "Все слои разобраны" : `✦ Назначить классы · ${unclassifiedLayerCount}`}</button></div>
            {semanticJob && <div className={`semantic-job semantic-${semanticJob.state}`}><b>Только выбранный файл · {projectRelativePath(filePathById.get(semanticJob.source_asset_id) || "CAD-документ")}</b><span>{semanticJob.state.replaceAll("_", " ")} · {semanticJob.completed_count}/{semanticJob.total_count}{semanticJob.failed_count ? ` · ошибок ${semanticJob.failed_count}` : ""}</span>{semanticJob.error_summary && <small>{semanticJob.error_summary}</small>}</div>}
            <div className="space-tabs" role="tablist" aria-label="Листы документа">{selectedSpaces.map((space) => <button role="tab" aria-selected={selectedSpace?.id === space.id} className={selectedSpace?.id === space.id ? "active" : ""} key={space.id} onClick={() => setSelectedCadNode({ kind: "space", id: space.id })}><i>{space.space_kind === "model" ? "M" : "Л"}</i><span>{space.name}</span><small>{space.entity_count.toLocaleString("ru-RU")}</small></button>)}{!selectedSpaces.length && <p className="empty-line">Пространства документа не найдены.</p>}</div>
            {selectedSpace && <p className="space-scope-note">Выбран лист «{selectedSpace.name}». Ниже пока показаны слои всего документа: точная привязка видимости слоёв к листам и viewport ещё не извлечена.</p>}
            {selectedXref && <section className="selected-object-card"><span>XREF · {selectedXref.status}</span><h3>{selectedXref.reference_name}</h3><code>{selectedXref.original_path || "Путь не записан"}</code><p>{selectedXref.target_relative_path ? `Цель: ${selectedXref.target_relative_path}` : selectedXref.matches.length ? `Кандидаты: ${selectedXref.matches.join(", ")}` : "Файл не найден в текущей поставке."}</p>{selectedXref.referenced_asset_id && <button onClick={() => selectDocument(selectedXref.referenced_asset_id!)}>Перейти к целевому документу</button>}</section>}
            {selectedXref?.status === "ambiguous" && <XrefResolutionChoices xref={selectedXref} files={project.files} value={xrefTargetId} busy={!!busy} onChange={setXrefTargetId} onResolve={() => resolveSelectedXref(selectedXref)} />}
            {selectedLayer && <section className="selected-object-card"><span>Слой · {selectedLayer.method}</span><h3>{selectedLayer.name}</h3><p>{selectedLayer.entity_count.toLocaleString("ru-RU")} объектов · категория <b title={selectedLayer.suggested_category}>{cadCategoryLabel(selectedLayer.suggested_category)}</b>{selectedLayer.review_status === "accepted" ? (selectedLayer.axis_results.auto_confirmed ? " · подтверждено по названию слоя" : selectedLayer.axis_results.assistant_assigned ? " · назначено ассистентом" : " · проверена инженером") : ` · подсказка ${Math.round((selectedLayer.confidence || 0) * 100)}%`}</p><div className="entity-tags">{Object.entries(selectedLayer.entity_types).map(([kind, count]) => <span key={kind}>{kind} <b>{count}</b></span>)}</div></section>}
            <div className="layer-toolbar"><label><span>Поиск слоя</span><input value={layerQuery} onChange={(event) => setLayerQuery(event.target.value)} placeholder="деревья, кабель…" /></label><div className="layer-modes"><button className={layerMode === "unknown" ? "active" : ""} onClick={() => setLayerMode("unknown")}>Не разобраны</button><button className={layerMode === "all" ? "active" : ""} onClick={() => setLayerMode("all")}>Все</button><button className={layerMode === "reviewed" ? "active" : ""} onClick={() => setLayerMode("reviewed")}>Проверены</button></div><small className="layer-filter-summary">Показано {selectedLayers.length} из {project.cad_layers.filter((item) => item.source_asset_id === layerDocument).length}</small></div>
            <div className="bulk-review-bar"><label className="select-all-layers"><input type="checkbox" aria-label="Выбрать все видимые слои" disabled={!visibleLayerSuggestionIds.length} checked={allVisibleLayersSelected} ref={(node) => { if (node) node.indeterminate = someVisibleLayersSelected && !allVisibleLayersSelected; }} onChange={(event) => setSelectedLayerIds((current) => toggleScopedSelection(current, visibleLayerSuggestionIds, event.target.checked))} /><span>Выбрать все</span><small>{visibleLayerSuggestionIds.length}</small></label><span>Выбрано: <b>{selectedLayerIds.length}</b></span><select value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)}>{cadCategoryGroups.map((group) => <optgroup key={group.label} label={group.label}>{group.options.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</optgroup>)}</select><button disabled={!selectedLayerIds.length || !!busy} onClick={() => reviewSelectedLayers("reject")}>Отклонить</button><button className="action-primary" disabled={!selectedLayerIds.length || !!busy} onClick={() => reviewSelectedLayers("accept")}>Назначить категорию</button></div>
            <div className="layer-table"><header><span>Слой / семейство</span><span>Состав</span><span>Классификация</span><span>Выбор</span></header>{layerFamilies.map(([familyKey, members]) => {
              const layer = members[0];
              const axes = layer.axis_results.axes;
              const suggestionIds = reviewableLayerSuggestionIds(members);
              const selected = suggestionIds.length > 0 && suggestionIds.every((id) => selectedLayerIds.includes(id));
              const departing = suggestionIds.some((id) => departingLayerIds.includes(id));
              return <div className={`layer-row ${selectedCadNode.kind === "layer" && selectedCadNode.id === layer.id ? "selected" : ""} ${departing ? "departing" : ""}`} key={familyKey} onClick={() => setSelectedCadNode({ kind: "layer", id: layer.id })}><div><strong>{layer.name}</strong><small>{members.reduce((sum, item) => sum + item.entity_count, 0).toLocaleString("ru-RU")} объектов · {members.length} в семействе · {layer.method} · {Math.round((layer.confidence || 0) * 100)}%</small></div><div className="entity-tags">{Object.entries(layer.entity_types).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([kind, count]) => <span key={kind}>{kind} <b>{count}</b></span>)}</div><div className="axis-grid">{layer.review_status === "accepted" ? <span className="confirmed-category" title={layer.suggested_category}>{cadCategoryLabel(layer.suggested_category)}</span> : axes ? Object.entries(axes).slice(0, 4).map(([axis, value]) => <span key={axis}><em>{axis === "object_class" ? "класс объекта" : axis}</em>{axis === "object_class" ? cadCategoryLabel(value.label) : value.label}</span>) : <span title={layer.suggested_category}>{cadCategoryLabel(layer.suggested_category)}</span>}</div><div className="layer-family-select"><input type="checkbox" aria-label={`Выбрать семейство ${layer.name}`} disabled={!suggestionIds.length} checked={selected} onChange={() => setSelectedLayerIds((current) => selected ? current.filter((id) => !suggestionIds.includes(id)) : Array.from(new Set([...current, ...suggestionIds])))} /></div></div>;
            })}{!selectedLayers.length && <p className="empty-line">В выбранном режиме слоёв нет.</p>}</div>
          </article>}

          {workbenchView === "publish" && <article className="intake-card">
            <div className="card-heading"><div><span>05</span><h2>Вердикт и публикация</h2></div><p>Состав модели выбирает инженер. Верхнеуровневые чертежи публикуются вместе с их разрешёнными XREF-ветками.</p></div>
            <div className="publication-root-picker">
              <header><div><strong>Состав публикации</strong><p>Выберите несколько верхнеуровневых чертежей. Разрешённые XREF включатся автоматически.</p></div><span>{publicationRootSelections.length} выбрано</span></header>
              {publicationGroups.map((group) => <section className={`publication-root-group root-${group.kind}`} key={group.kind}><h3>{group.label}<small>{group.roots.length}</small></h3>{group.roots.map((candidate) => {
                const selected = !!selectedPublicationRoots[candidate.source_asset_id];
                const blocked = candidate.unresolved_count > 0 || candidate.critical_count > 0;
                return <article className={`publication-root-row ${selected ? "selected" : ""} ${blocked ? "blocked" : ""}`} key={candidate.source_asset_id}>
                  <label><input type="checkbox" checked={selected} onChange={(event) => setSelectedPublicationRoots((current) => { const next = { ...current }; if (event.target.checked) next[candidate.source_asset_id] = candidate.selected_role || candidate.default_role; else delete next[candidate.source_asset_id]; return next; })} /><span><strong>{projectRelativePath(candidate.relative_path)}</strong><small>{candidate.dependency_count ? `Подключено XREF: ${candidate.dependency_count}` : "Самостоятельный чертёж"} · рейтинг {candidate.score.toFixed(0)}</small></span></label>
                  <select aria-label={`Роль ${candidate.relative_path}`} value={selectedPublicationRoots[candidate.source_asset_id] || candidate.default_role} onChange={(event) => setSelectedPublicationRoots((current) => ({ ...current, [candidate.source_asset_id]: event.target.value as PublicationRootRole }))}>{Object.entries(publicationRoleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                  <div className="publication-root-status">{candidate.unresolved_count > 0 && <b>{candidate.unresolved_count} XREF требуют решения</b>}{candidate.critical_count > 0 && <b>{candidate.critical_count} критических замечаний</b>}{!blocked && <i>Готов к включению</i>}</div>
                  {candidate.dependency_paths.length > 0 && <details><summary>Состав ветки ({candidate.dependency_count})</summary>{candidate.dependency_paths.map((path) => <code key={path}>{projectRelativePath(path)}</code>)}</details>}
                </article>;
              })}</section>)}
              {!project.publication_roots.length && <p className="empty-line">Корневые чертежи появятся после построения CAD-графа.</p>}
            </div>
            {["review_required", "ready_to_publish"].includes(project.intake_state) && <div className="review-box">{selectedRootCandidates.some((item) => item.unresolved_count > 0 || item.critical_count > 0) && <p className="review-blocked-note">В выбранных ветках остаются критические замечания или неразрешённые XREF.</p>}{publicationRootSelections.length > 0 && !publicationRootSelections.some((item) => item.role === "effective_design") && <p className="review-blocked-note">Назначьте хотя бы один корень действующим проектным решением.</p>}<label>Комментарий инженерной проверки<textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} /></label><div>{project.intake_state === "review_required" && <button className="reject-button" disabled={!!busy} onClick={() => action("reject", `/v1/intake/projects/${projectId}/review`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "reject", comment, roots: publicationRootSelections }) })}>Отклонить</button>}<button className="action-primary" disabled={!mayReview || comment.length < 3 || !!busy} onClick={() => action("review", `/v1/intake/projects/${projectId}/review`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "accept", comment, roots: publicationRootSelections }) })}>Зафиксировать состав</button></div></div>}
            {project.intake_state === "ready_to_publish" && <button className="action-primary publish-button" disabled={!!busy || publicationSelectionDirty || !persistedRootSelections.length} title={publicationSelectionDirty || !persistedRootSelections.length ? "Сначала сохраните состав публикации" : undefined} onClick={() => action("publish", `/v1/intake/projects/${projectId}/publish`)}>{publicationSelectionDirty || !persistedRootSelections.length ? "Сначала сохраните состав публикации" : "Опубликовать каноническую модель"}</button>}
          </article>}
        </div>

        <aside className="intake-aside wb-tree-pane">
          {workbenchView === "materials" && <article className="intake-card"><h3>Дерево поставки</h3><div className="delivery-tree"><DeliveryNodes nodes={deliveryTree} onContextMenu={openDeliveryMenu} /></div></article>}
          {workbenchView === "explorer" && <article className="intake-card cad-tree-card"><header><div><span>Структура проекта</span><h3>CAD-граф</h3></div><small>Смысловые корни и подключённые XREF</small></header><div className="cad-nav-tree">{cadWorkspaceRoots.map((root) => <section className={`cad-workspace-root root-${root.kind}`} key={root.kind}><header><strong>{root.label}</strong><small>{root.nodes.length} корневых</small></header><CadDependencyNodes nodes={root.nodes} project={project} layerDocument={layerDocument} selectedCadNode={selectedCadNode} onDocument={selectDocument} onSpace={(assetId, id) => { setLayerDocument(assetId); setSelectedCadNode({ kind: "space", id }); }} onLayer={(assetId, id) => { setLayerDocument(assetId); setSelectedCadNode({ kind: "layer", id }); }} onXref={(assetId, id) => { setXrefTargetId(""); setLayerDocument(assetId); setSelectedCadNode({ kind: "xref", id }); }} /></section>)}</div></article>}
          {workbenchView === "publish" && <article className="intake-card"><h3>Контроль качества</h3><div className="quality-metrics"><div><strong>{project.cad_count}</strong><span>CAD-файлов</span></div><div><strong>{project.finding_count}</strong><span>наблюдений</span></div><div className={project.critical_count ? "danger" : ""}><strong>{project.critical_count}</strong><span>критических</span></div></div><p className="verdict">Вердикт <b>{project.fidelity_verdict?.replaceAll("_", " ") || "ещё не сформирован"}</b></p></article>}
        </aside>
        <button className="workbench-column-resizer" aria-label="Изменить ширину дерева проекта" title="Потяните, чтобы изменить ширину дерева" onPointerDown={beginTreeResize} />
      </section>
      <section className={`activity-dock ${dockExpanded ? "expanded" : "collapsed"}`} style={{ "--tray-height": `${dockHeight}px` } as CSSProperties}>
        {dockExpanded && <button className="activity-dock-resizer" aria-label="Изменить высоту нижней панели" onPointerDown={beginDockResize} />}
        <header className="activity-dock-tabs"><i className={assistantActive || semanticActive || busy === "upload" ? "is-live" : ""} /><button className={dockTab === "issues" ? "active" : ""} onClick={() => { setDockTab("issues"); setDockExpanded(true); }}>Проблемы <em>{openFindingCount}</em></button><button className={dockTab === "activity" ? "active" : ""} onClick={() => { setDockTab("activity"); setDockExpanded(true); }}>Журнал действий <em>{activityEvents.length}</em></button>{assistantActive ? <div className="dock-assistant-progress" aria-live="polite"><div><b>Ассистент поставки</b><span>{assistantProgressTitle} · {assistantCompletedCount}/{assistantTaskCount} задач</span></div><div className="dock-progress-track"><i style={{ width: `${assistantProgressPercent}%` }} /></div><strong>{assistantProgressPercent}%</strong></div> : <span>{dockTab === "activity" ? selectedActivity?.title || "Событий пока нет" : resolutionNotice || selectedFinding?.title || "Проблем нет"}</span>}<button className="dock-collapse" onClick={() => setDockExpanded((value) => !value)}>{dockExpanded ? "⌄" : "⌃"}</button></header>
        {dockExpanded && dockTab === "activity" && <div className="activity-dock-body"><div className="activity-stream">{activityEvents.map((event) => <button className={`activity-event activity-${event.state} ${event.id === selectedActivity?.id ? "selected" : ""}`} key={event.id} onClick={() => setSelectedActivityId(event.id)}><i /><time>{new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(event.at))}</time><div><strong>{event.title}</strong><small>{event.detail}</small></div></button>)}</div><button className="dock-column-resizer" aria-label="Изменить ширину списка журнала" onPointerDown={beginDockSplitResize} /><aside>{selectedActivity ? <><span>{selectedActivity.state}</span><h3>{selectedActivity.title}</h3><p>{selectedActivity.detail}</p><dl><div><dt>Время</dt><dd>{new Date(selectedActivity.at).toLocaleString("ru-RU")}</dd></div><div><dt>ID события</dt><dd>{selectedActivity.id}</dd></div></dl><details open><summary>Метрики</summary><pre>{JSON.stringify(selectedActivity.metrics, null, 2)}</pre></details>{(selectedActivity.stderr || selectedActivity.stdout) && <details><summary>Технический вывод</summary><pre>{selectedActivity.stderr || selectedActivity.stdout}</pre></details>}<p className="activity-hint">Artifact locator показан в описании завершённой конвертации.</p></> : <p>Выберите событие.</p>}</aside></div>}
        {dockExpanded && dockTab === "issues" && <div className="tray-issues issue-split"><div className="issue-list-pane"><div className="issue-bulk-bar"><button disabled={!selectedFinding} onClick={() => setCheckedFindingIds(allSameKindChecked ? checkedFindingIds.filter((id) => !sameKindFindings.some((finding) => finding.id === id)) : [...new Set([...checkedFindingIds, ...sameKindFindings.map((finding) => finding.id)])])}>{allSameKindChecked ? "Снять однотипные" : "Выбрать все однотипные (" + sameKindFindings.length + ")"}</button><span>{checkedFindingIds.length ? "Выбрано: " + checkedFindingIds.length : "Отметьте проблемы для общего решения"}</span><select aria-label="Действие для выбранных проблем" value={bulkFindingAction} onChange={(event) => setBulkFindingAction(event.target.value as "waive" | "block")}><option value="waive">Игнорировать в редакции</option><option value="block">Блокировать</option></select><button className="action-primary" disabled={!checkedFindingIds.length || !!busy} onClick={resolveCheckedFindings}>{busy === "bulk-finding-resolution" ? "Применяем…" : "Применить ко всем"}</button></div><FindingQueue groups={findingGroups} selectedId={selectedFinding?.id || ""} checkedIds={checkedFindingIds} departingId={departingFindingId} revalidatingSourceId={revalidatingSourceId} onToggle={(id) => setCheckedFindingIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])} onSelect={(id) => { setXrefTargetId(""); setResolutionNotice(""); setSelectedFindingId(id); }} /></div><button className="dock-column-resizer" aria-label="Изменить ширину списка проблем" onPointerDown={beginDockSplitResize} />{selectedFinding ? <section className="issue-detail"><header><span>{selectedFinding.severity}</span><h3>{selectedFinding.title}</h3><p>{selectedFinding.detail}</p></header>{selectedFinding.source_asset_id && !selectedFindingXref && filePathById.get(selectedFinding.source_asset_id) && <ReadableDrawingPath path={filePathById.get(selectedFinding.source_asset_id)!} />}{selectedFinding.code === "xref_missing" && findingXrefEvidence?.path && <div className="missing-xref-target"><b>Искомая внешняя ссылка</b><code>{findingXrefEvidence.path}</code></div>}<dl><div><dt>Этап</dt><dd>{selectedFinding.stage}</dd></div><div><dt>Код</dt><dd>{selectedFinding.code}</dd></div><div><dt>Статус</dt><dd>{selectedFinding.status}</dd></div></dl>{selectedFindingXref && <XrefResolutionChoices xref={selectedFindingXref} files={project.files} value={xrefTargetId} busy={!!busy} onChange={setXrefTargetId} onResolve={() => resolveSelectedXref(selectedFindingXref)} />}{selectedFindingInventories.length > 0 && <div className="fidelity-comparison">{selectedFindingInventories.map((inventory) => <div key={inventory.id}><header><b>{inventory.stage}</b><span>{inventory.tool_name || inventory.format}</span></header><dl><div><dt>Объекты</dt><dd>{String(inventory.metrics.entity_count ?? "—")}</dd></div><div><dt>Слои</dt><dd>{String(inventory.metrics.layer_count ?? "—")}</dd></div><div><dt>Листы</dt><dd>{String(inventory.metrics.layout_count ?? "—")}</dd></div></dl>{inventory.artifact_locator && <code>{inventory.artifact_locator}</code>}</div>)}</div>}<details><summary>Evidence</summary><pre>{JSON.stringify(selectedFinding.evidence, null, 2)}</pre></details>{selectedFinding.resolution?.reason && <div className="issue-resolution"><b>{selectedFinding.resolution.action}</b><p>{selectedFinding.resolution.reason}</p></div>}<label className="issue-reason">Обоснование решения<textarea rows={2} value={findingReason} onChange={(event) => setFindingReason(event.target.value)} /></label><div className="issue-actions"><button disabled={!!busy} onClick={() => action("retry-search", `/v1/intake/projects/${projectId}/assistant-runs`)}>Повторить анализ</button><button onClick={() => resolveSelectedFinding("reopen")}>Вернуть</button><button className="reject-button" onClick={() => resolveSelectedFinding("block")}>Блокировать</button><button className="action-primary" onClick={() => resolveSelectedFinding("waive")}>Игнорировать в редакции</button></div></section> : <p className="empty-line">Проблем нет.</p>}</div>}
      </section>
      {deliveryMenu && <div className="delivery-context-menu" role="menu" style={{ left: deliveryMenu.x, top: deliveryMenu.y }} onClick={(event) => event.stopPropagation()}><div><strong>{deliveryMenu.node.label}</strong><small>{deliveryMenu.node.kind === "folder" ? "Папка поставки" : "Файл поставки"}</small></div><button role="menuitem" disabled={!!busy} onClick={() => removeDeliveryNode(deliveryMenu.node)}><span>×</span>Удалить из проекта</button></div>}
      {error && <div className="toast-error" role="alert">{error}<button onClick={() => setError("")}>×</button></div>}
    </main>
  );
}
