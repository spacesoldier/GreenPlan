"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type CSSProperties, type InputHTMLAttributes, type PointerEvent as ReactPointerEvent } from "react";

import type { IntakeProjectDetail } from "@/lib/contracts";
import { domainJson, formatBytes } from "@/lib/domain-client";
import { inspectFolderSelection, isSupportedProjectFile, partitionProjectFiles, relativeUploadPath } from "@/lib/folder-selection";
import { buildDeliveryTree, clampTrayHeight, groupLayerFamilies, wizardStepStates, type DeliveryTreeNode } from "@/lib/cad-workbench";

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

const stageLabels: Record<string, string> = {
  direct_read: "Прямое чтение DWG", conversion: "Конвертация ODA → DXF",
  direct_dwg_read: "Прямое чтение DWG", oda_conversion: "Конвертация ODA → DXF",
  converted_dxf_inventory: "Инвентаризация полученного DXF", uploaded_dxf_inventory: "Инвентаризация загруженного DXF",
  dxf_inventory: "Инвентаризация DXF", xref_resolution: "Разрешение XREF",
  fidelity_check: "Проверка полноты", classification: "Классификация",
};

function DeliveryNodes({ nodes }: { nodes: DeliveryTreeNode[] }) {
  return <>{nodes.map((node) => node.kind === "folder"
    ? <details className="wb-tree-folder" key={node.id} open><summary><span>⌄</span>{node.label}<small>{node.children.length}</small></summary><div><DeliveryNodes nodes={node.children} /></div></details>
    : <button className="wb-tree-file" key={node.id}><span>{node.label.toLocaleLowerCase().endsWith(".dwg") ? "DWG" : node.label.split(".").pop()?.toUpperCase()}</span><b>{node.label}</b></button>)}</>;
}

export function ProjectIntake({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<IntakeProjectDetail | null>(null);
  const [selectedMaster, setSelectedMaster] = useState("");
  const [layerDocument, setLayerDocument] = useState("");
  const [layerQuery, setLayerQuery] = useState("");
  const [layerMode, setLayerMode] = useState<"all" | "unknown" | "reviewed">("unknown");
  const [workbenchView, setWorkbenchView] = useState<"materials" | "explorer" | "publish">("explorer");
  const [selectedCadNode, setSelectedCadNode] = useState<{ kind: "document" | "space" | "layer" | "xref"; id: string }>({ kind: "document", id: "" });
  const [selectedLayerIds, setSelectedLayerIds] = useState<string[]>([]);
  const [bulkCategory, setBulkCategory] = useState("utility.unknown");
  const [selectedFindingId, setSelectedFindingId] = useState("");
  const [findingReason, setFindingReason] = useState("Ограничение принято для текущей редакции.");
  const [dockExpanded, setDockExpanded] = useState(true);
  const [dockTab, setDockTab] = useState<"issues" | "activity">("activity");
  const [dockHeight, setDockHeight] = useState(320);
  const [selectedActivityId, setSelectedActivityId] = useState("");
  const [comment, setComment] = useState("Проверено инженером; ограничения преобразования приняты.");
  const [busy, setBusy] = useState("");
  const [uploadProgress, setUploadProgress] = useState<[number, number] | null>(null);
  const [uploadNote, setUploadNote] = useState("");
  const [liveUpload, setLiveUpload] = useState<{ state: string; title: string; detail: string; at: string } | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const next = await domainJson<IntakeProjectDetail>(`/v1/intake/projects/${projectId}`);
    setProject(next);
    setSelectedMaster((current) => current || next.master_candidates.find((item) => item.selected)?.source_asset_id || next.master_candidates[0]?.source_asset_id || "");
    setLayerDocument((current) => current || next.master_candidates[0]?.source_asset_id || next.cad_layers[0]?.source_asset_id || "");
    setSelectedCadNode((current) => current.id ? current : { kind: "document", id: next.master_candidates[0]?.source_asset_id || next.cad_layers[0]?.source_asset_id || "" });
    return next;
  }, [projectId]);

  useEffect(() => {
    load().catch((reason: Error) => setError(reason.message));
  }, [load]);

  useEffect(() => {
    const runActive = project?.assistant_runs?.some((run) => ["queued", "running"].includes(run.state));
    const semanticActive = project?.semantic_suggestion_jobs?.some((job) => ["queued", "running"].includes(job.state));
    if (project?.intake_state !== "analyzing" && !runActive && !semanticActive) return;
    const timer = window.setInterval(() => load().catch(() => undefined), 1800);
    return () => window.clearInterval(timer);
  }, [load, project?.intake_state, project?.assistant_runs, project?.semantic_suggestion_jobs]);

  useEffect(() => {
    const saved = Number(window.localStorage.getItem("greenplan.intake.tray-height"));
    if (Number.isFinite(saved) && saved > 0) setDockHeight(clampTrayHeight(saved, window.innerHeight));
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

  async function action(name: string, path: string, init?: RequestInit) {
    setBusy(name); setError("");
    try { await domainJson(path, { method: "POST", ...init }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Операция не выполнена"); }
    finally { setBusy(""); }
  }

  async function reviewSelectedLayers(decision: "accept" | "reject") {
    if (!selectedLayerIds.length) return;
    await action("batch-classification", `/v1/intake/projects/${projectId}/classifications/batch-review`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ suggestion_ids: selectedLayerIds, decision, category: decision === "accept" ? bulkCategory : null, comment: "Массовая проверка в CAD workbench" }),
    });
    setSelectedLayerIds([]);
  }

  async function resolveSelectedFinding(actionName: "waive" | "reopen" | "block") {
    if (!selectedFindingId) return;
    await action("finding-resolution", `/v1/intake/projects/${projectId}/findings/${selectedFindingId}/resolve`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: actionName, reason: findingReason }),
    });
  }

  if (!project) return <main className="intake-loading"><span className="loader" /><strong>{error || "Открываем проект…"}</strong></main>;
  const mayAnalyze = project.file_count > 0 && !["analyzing", "published"].includes(project.intake_state);
  const assistantRun = project.assistant_runs[0];
  const assistantActive = assistantRun && ["queued", "running"].includes(assistantRun.state);
  const mayReview = project.intake_state === "review_required"
    && !!selectedMaster
    && project.critical_count === 0
    && project.fidelity_verdict !== "rejected";
  const xrefsBySource = project.xref_dependencies.reduce((result, xref) => {
    const values = result.get(xref.source_asset_id) || [];
    values.push(xref); result.set(xref.source_asset_id, values); return result;
  }, new Map<string, typeof project.xref_dependencies>());
  const filePathById = new Map(project.files.map((file) => [file.id, file.relative_path]));
  const visibleFiles = project.files.filter((file) => isSupportedProjectFile({ name: file.relative_path }));
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
  const layerDocuments = Array.from(new Map(project.cad_layers.map((layer) => [layer.source_asset_id, layer.source_relative_path])).entries());
  const selectedSpaces = project.cad_spaces.filter((space) => space.source_asset_id === layerDocument);
  const selectedLayers = project.cad_layers.filter((layer) => {
    if (layer.source_asset_id !== layerDocument) return false;
    if (layerMode === "unknown" && layer.suggested_category !== "unknown") return false;
    if (layerMode === "reviewed" && layer.review_status === "pending") return false;
    return !layerQuery || layer.name.toLocaleLowerCase().includes(layerQuery.toLocaleLowerCase());
  });
  const deliveryTree = buildDeliveryTree(visibleFiles);
  const layerFamilies = [...groupLayerFamilies(selectedLayers).entries()];
  const selectedFinding = project.findings.find((finding) => finding.id === selectedFindingId) || project.findings[0];
  const selectedFindingInventories = project.inventories.filter((item) => item.source_asset_id === selectedFinding?.source_asset_id);
  const selectedActivity = activityEvents.find((event) => event.id === selectedActivityId) || activityEvents[0];
  const selectedLayer = project.cad_layers.find((layer) => selectedCadNode.kind === "layer" && layer.id === selectedCadNode.id);
  const selectedXref = project.xref_dependencies.find((xref) => selectedCadNode.kind === "xref" && xref.id === selectedCadNode.id);
  const selectedSpace = project.cad_spaces.find((space) => selectedCadNode.kind === "space" && space.id === selectedCadNode.id)
    || selectedSpaces[0];
  const semanticJob = project.semantic_suggestion_jobs?.find((job) => job.source_asset_id === layerDocument);
  const semanticActive = semanticJob && ["queued", "running"].includes(semanticJob.state);
  const openFindingCount = project.findings.filter((item) => item.status === "open").length;
  const stepStates = wizardStepStates({
    fileCount: project.file_count, cadCount: project.cad_count,
    openFindings: openFindingCount, published: project.intake_state === "published",
  });

  function selectDocument(assetId: string) {
    setLayerDocument(assetId);
    setSelectedCadNode({ kind: "document", id: assetId });
  }

  function openWizardStep(step: number) {
    if (step === 0) setWorkbenchView("materials");
    if (step === 1) setWorkbenchView("explorer");
    if (step === 2) { setWorkbenchView("explorer"); setDockTab("issues"); setDockExpanded(true); }
    if (step === 3) setWorkbenchView("publish");
  }

  return (
    <main className="intake-page" style={{ "--tray-height": `${dockHeight}px` } as CSSProperties}>
      <header className="intake-topbar">
        <Link className="brand-lockup compact" href="/"><span className="brand-mark">G</span><span><strong>GreenPlan</strong><small>Проекты</small></span></Link>
        <nav><Link href="/">Все проекты</Link><span>/</span><strong>{project.title}</strong></nav>
        {project.current_model_id && <Link className="open-model-link" href={`/workspace?project=${project.id}`}>Открыть модель ↗</Link>}
      </header>

      <section className="intake-hero">
        <div><span className="eyebrow">{project.code} · редакция {project.revision_no}</span><h1>{project.title}</h1><p>{project.description || "Описание проекта пока не заполнено."}</p></div>
        <div className="intake-hero-status"><span className={`intake-state state-${project.intake_state}`}>{stateLabels[project.intake_state] ?? project.intake_state}</span><strong>{project.file_count}</strong><small>файлов · {formatBytes(project.total_bytes)}</small></div>
      </section>

      <nav className="preparation-wizard" aria-label="Этапы подготовки проекта">
        {[
          ["Материалы", `${project.file_count} файлов`],
          ["CAD-разбор", `${project.cad_layers.length} слоёв`],
          ["Проверка", openFindingCount ? `${openFindingCount} проблем` : "готово"],
          ["Публикация", project.intake_state === "published" ? "модель опубликована" : "конечная цель"],
        ].map(([title, detail], index) => <button key={title} className={`${stepStates[index]} ${(workbenchView === "materials" && index === 0) || (workbenchView === "explorer" && index === 1) || (dockTab === "issues" && dockExpanded && index === 2) || (workbenchView === "publish" && index === 3) ? "active" : ""}`} onClick={() => openWizardStep(index)}><i>{stepStates[index] === "complete" ? "✓" : index + 1}</i><span><b>{title}</b><small>{detail}</small></span></button>)}
        <div><span>Цель</span><b>Проверенная модель проекта</b></div>
      </nav>

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
            <div className="analysis-scope"><b>Область поиска</b><span>Текущая поставка: {project.file_count} файлов. Серверный dataset и чужие проекты не просматриваются автоматически.</span></div>
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
            <div className="card-heading"><div><span>02</span><h2>Инспектор CAD</h2></div><p>Выберите документ, лист, слой или XREF в дереве слева. Подсказки модели остаются кандидатами до инженерной проверки.</p></div>
            <div className="document-context"><div><span>Документ</span><strong>{layerDocuments.find(([id]) => id === layerDocument)?.[1] || "Документ не выбран"}</strong></div><div className="xref-summary"><span><b>{(xrefsBySource.get(layerDocument) || []).length}</b> XREF</span><span><b>{selectedSpaces.length}</b> листов</span><span><b>{project.cad_layers.filter((item) => item.source_asset_id === layerDocument).length}</b> слоёв</span></div><button className="ai-suggest-button" disabled={!layerDocument || !!semanticActive || !!busy} onClick={() => action("semantic-suggest", `/v1/intake/projects/${projectId}/semantic-suggestion-jobs`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source_asset_id: layerDocument }) })}>{semanticActive ? `Модель работает · ${semanticJob?.completed_count || 0}/${semanticJob?.total_count || 0}` : "✦ Подсказать категории"}</button></div>
            {semanticJob && <div className={`semantic-job semantic-${semanticJob.state}`}><b>{semanticJob.provider} · multilingual · experimental</b><span>{semanticJob.state.replaceAll("_", " ")} · {semanticJob.completed_count}/{semanticJob.total_count}{semanticJob.failed_count ? ` · ошибок ${semanticJob.failed_count}` : ""}</span>{semanticJob.error_summary && <small>{semanticJob.error_summary}</small>}</div>}
            <div className="space-tabs" role="tablist" aria-label="Листы документа">{selectedSpaces.map((space) => <button role="tab" aria-selected={selectedSpace?.id === space.id} className={selectedSpace?.id === space.id ? "active" : ""} key={space.id} onClick={() => setSelectedCadNode({ kind: "space", id: space.id })}><i>{space.space_kind === "model" ? "M" : "Л"}</i><span>{space.name}</span><small>{space.entity_count.toLocaleString("ru-RU")}</small></button>)}{!selectedSpaces.length && <p className="empty-line">Пространства документа не найдены.</p>}</div>
            {selectedSpace && <p className="space-scope-note">Показаны слои документа для вкладки «{selectedSpace.name}». Точная видимость по viewport появится после нормализации per-space layer states.</p>}
            {selectedXref && <section className="selected-object-card"><span>XREF · {selectedXref.status}</span><h3>{selectedXref.reference_name}</h3><code>{selectedXref.original_path || "Путь не записан"}</code><p>{selectedXref.target_relative_path ? `Цель: ${selectedXref.target_relative_path}` : selectedXref.matches.length ? `Кандидаты: ${selectedXref.matches.join(", ")}` : "Файл не найден в текущей поставке."}</p>{selectedXref.referenced_asset_id && <button onClick={() => selectDocument(selectedXref.referenced_asset_id!)}>Перейти к целевому документу</button>}</section>}
            {selectedLayer && <section className="selected-object-card"><span>Слой · {selectedLayer.method}</span><h3>{selectedLayer.name}</h3><p>{selectedLayer.entity_count.toLocaleString("ru-RU")} объектов · подсказка <b>{selectedLayer.suggested_category}</b> · {Math.round((selectedLayer.confidence || 0) * 100)}%</p><div className="entity-tags">{Object.entries(selectedLayer.entity_types).map(([kind, count]) => <span key={kind}>{kind} <b>{count}</b></span>)}</div></section>}
            <div className="layer-toolbar"><label><span>Поиск слоя</span><input value={layerQuery} onChange={(event) => setLayerQuery(event.target.value)} placeholder="деревья, кабель…" /></label><div className="layer-modes"><button className={layerMode === "unknown" ? "active" : ""} onClick={() => setLayerMode("unknown")}>Не разобраны</button><button className={layerMode === "all" ? "active" : ""} onClick={() => setLayerMode("all")}>Все</button><button className={layerMode === "reviewed" ? "active" : ""} onClick={() => setLayerMode("reviewed")}>Проверены</button></div></div>
            <div className="bulk-review-bar"><span>Выбрано: <b>{selectedLayerIds.length}</b></span><select value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)}><option value="utility.unknown">Инженерные сети</option><option value="transport.road">Дороги и проезды</option><option value="surface.lawn">Покрытия и газоны</option><option value="vegetation.existing">Существующая растительность</option><option value="vegetation.proposed">Проектируемая растительность</option><option value="structure.building">Здания и сооружения</option><option value="terrain">Рельеф</option><option value="territory.work_boundary">Границы и зоны</option><option value="not_applicable">Служебное / неприменимо</option><option value="unknown">Не определено</option></select><button disabled={!selectedLayerIds.length || !!busy} onClick={() => reviewSelectedLayers("reject")}>Отклонить</button><button className="action-primary" disabled={!selectedLayerIds.length || !!busy} onClick={() => reviewSelectedLayers("accept")}>Назначить категорию</button></div>
            <div className="layer-table"><header><span>Слой / семейство</span><span>Состав</span><span>Классификация</span><span>Выбор</span></header>{layerFamilies.map(([familyKey, members]) => {
              const layer = members[0];
              const axes = layer.axis_results.axes;
              const suggestionIds = members.filter((item) => item.review_status === "pending").map((item) => item.suggestion_id);
              const selected = suggestionIds.length > 0 && suggestionIds.every((id) => selectedLayerIds.includes(id));
              return <div className={`layer-row ${selectedCadNode.kind === "layer" && selectedCadNode.id === layer.id ? "selected" : ""}`} key={familyKey} onClick={() => setSelectedCadNode({ kind: "layer", id: layer.id })}><div><strong>{layer.name}</strong><small>{members.reduce((sum, item) => sum + item.entity_count, 0).toLocaleString("ru-RU")} объектов · {members.length} в семействе · {layer.method} · {Math.round((layer.confidence || 0) * 100)}%</small></div><div className="entity-tags">{Object.entries(layer.entity_types).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([kind, count]) => <span key={kind}>{kind} <b>{count}</b></span>)}</div><div className="axis-grid">{axes ? Object.entries(axes).slice(0, 4).map(([axis, value]) => <span key={axis}><em>{axis}</em>{value.label}</span>) : <span>{layer.suggested_category}</span>}</div><div className="layer-family-select"><input type="checkbox" aria-label={`Выбрать семейство ${layer.name}`} disabled={!suggestionIds.length} checked={selected} onChange={() => setSelectedLayerIds((current) => selected ? current.filter((id) => !suggestionIds.includes(id)) : Array.from(new Set([...current, ...suggestionIds])))} /><small>{suggestionIds.length || "✓"}</small></div></div>;
            })}{!selectedLayers.length && <p className="empty-line">В выбранном режиме слоёв нет.</p>}</div>
          </article>}

          {workbenchView === "publish" && <article className="intake-card">
            <div className="card-heading"><div><span>05</span><h2>Вердикт и публикация</h2></div><p>Мастер выбирает человек. Неоднозначности и потери остаются видимыми в журнале.</p></div>
            <div className="candidate-list">
              {project.master_candidates.map((candidate) => <label className={`candidate-row ${selectedMaster === candidate.source_asset_id ? "selected" : ""}`} key={candidate.source_asset_id}><input type="radio" name="master" checked={selectedMaster === candidate.source_asset_id} onChange={() => setSelectedMaster(candidate.source_asset_id)} /><div><strong>{candidate.relative_path}</strong><small>{candidate.role.replaceAll("_", " ")} · признаки: {candidate.cues.join(", ") || "нет"}</small></div><b>{candidate.score.toFixed(0)}</b></label>)}
              {!project.master_candidates.length && <p className="empty-line">Кандидаты появятся после анализа CAD-файлов.</p>}
            </div>
            {project.intake_state === "review_required" && <div className="review-box">{project.critical_count > 0 && <p className="review-blocked-note">Сначала устраните {project.critical_count} критических замечаний и запустите анализ повторно.</p>}<label>Комментарий инженерной проверки<textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} /></label><div><button className="reject-button" disabled={!!busy} onClick={() => action("reject", `/v1/intake/projects/${projectId}/review`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "reject", comment, selected_master_asset_id: selectedMaster || null }) })}>Отклонить</button><button className="action-primary" disabled={!mayReview || comment.length < 3 || !!busy} onClick={() => action("review", `/v1/intake/projects/${projectId}/review`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "accept", comment, selected_master_asset_id: selectedMaster }) })}>Принять с фиксацией</button></div></div>}
            {project.intake_state === "ready_to_publish" && <button className="action-primary publish-button" disabled={!!busy} onClick={() => action("publish", `/v1/intake/projects/${projectId}/publish`)}>Опубликовать каноническую модель</button>}
          </article>}
        </div>

        <aside className="intake-aside wb-tree-pane">
          {workbenchView === "materials" && <article className="intake-card"><h3>Дерево поставки</h3><div className="delivery-tree"><DeliveryNodes nodes={deliveryTree} /></div></article>}
          {workbenchView === "explorer" && <article className="intake-card cad-tree-card"><header><div><span>Структура проекта</span><h3>CAD-граф</h3></div><small>Документы, листы, слои и зависимости</small></header><div className="cad-nav-tree">{layerDocuments.map(([assetId, path]) => { const refs = xrefsBySource.get(assetId) || []; const spaces = project.cad_spaces.filter((item) => item.source_asset_id === assetId); const layers = project.cad_layers.filter((item) => item.source_asset_id === assetId); return <details key={assetId} open={assetId === layerDocument}><summary className={selectedCadNode.kind === "document" && selectedCadNode.id === assetId ? "selected" : ""} onClick={() => selectDocument(assetId)}><span>DWG</span><b>{path}</b></summary><div className="cad-tree-group"><em>Листы</em>{spaces.map((space) => <button className={selectedCadNode.kind === "space" && selectedCadNode.id === space.id ? "selected" : ""} key={space.id} onClick={() => { setLayerDocument(assetId); setSelectedCadNode({ kind: "space", id: space.id }); }}><span>{space.space_kind === "model" ? "M" : "Л"}</span><b>{space.name}</b><small>{space.entity_count}</small></button>)}</div><details className="cad-tree-subtree"><summary><b>Слои</b><small>{layers.length}</small></summary><div className="cad-tree-layers">{layers.map((layer) => <button className={selectedCadNode.kind === "layer" && selectedCadNode.id === layer.id ? "selected" : ""} key={layer.id} onClick={() => { setLayerDocument(assetId); setSelectedCadNode({ kind: "layer", id: layer.id }); }}><span>≡</span><b>{layer.name}</b><small>{layer.suggested_category}</small></button>)}</div></details><div className="cad-tree-group"><em>Внешние ссылки</em>{refs.map((xref) => <button className={`ref-${xref.status} ${selectedCadNode.kind === "xref" && selectedCadNode.id === xref.id ? "selected" : ""}`} key={xref.id} title={xref.original_path || ""} onClick={() => { setLayerDocument(assetId); setSelectedCadNode({ kind: "xref", id: xref.id }); }}><span>↗</span><b>{xref.reference_name}</b><small>{xref.target_relative_path ? "alias" : xref.status}</small></button>)}</div></details>; })}</div></article>}
          {workbenchView === "publish" && <article className="intake-card"><h3>Контроль качества</h3><div className="quality-metrics"><div><strong>{project.cad_count}</strong><span>CAD-файлов</span></div><div><strong>{project.finding_count}</strong><span>наблюдений</span></div><div className={project.critical_count ? "danger" : ""}><strong>{project.critical_count}</strong><span>критических</span></div></div><p className="verdict">Вердикт <b>{project.fidelity_verdict?.replaceAll("_", " ") || "ещё не сформирован"}</b></p></article>}
        </aside>
      </section>
      <section className={`activity-dock ${dockExpanded ? "expanded" : "collapsed"}`} style={{ "--tray-height": `${dockHeight}px` } as CSSProperties}>
        {dockExpanded && <button className="activity-dock-resizer" aria-label="Изменить высоту нижней панели" onPointerDown={beginDockResize} />}
        <header className="activity-dock-tabs"><i className={assistantActive || semanticActive || busy === "upload" ? "is-live" : ""} /><button className={dockTab === "issues" ? "active" : ""} onClick={() => { setDockTab("issues"); setDockExpanded(true); }}>Проблемы <em>{openFindingCount}</em></button><button className={dockTab === "activity" ? "active" : ""} onClick={() => { setDockTab("activity"); setDockExpanded(true); }}>Журнал действий <em>{activityEvents.length}</em></button><span>{dockTab === "activity" ? selectedActivity?.title || "Событий пока нет" : selectedFinding?.title || "Проблем нет"}</span><button className="dock-collapse" onClick={() => setDockExpanded((value) => !value)}>{dockExpanded ? "⌄" : "⌃"}</button></header>
        {dockExpanded && dockTab === "activity" && <div className="activity-dock-body"><div className="activity-stream">{activityEvents.map((event) => <button className={`activity-event activity-${event.state} ${event.id === selectedActivity?.id ? "selected" : ""}`} key={event.id} onClick={() => setSelectedActivityId(event.id)}><i /><time>{new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(event.at))}</time><div><strong>{event.title}</strong><small>{event.detail}</small></div></button>)}</div><aside>{selectedActivity ? <><span>{selectedActivity.state}</span><h3>{selectedActivity.title}</h3><p>{selectedActivity.detail}</p><dl><div><dt>Время</dt><dd>{new Date(selectedActivity.at).toLocaleString("ru-RU")}</dd></div><div><dt>ID события</dt><dd>{selectedActivity.id}</dd></div></dl><details open><summary>Метрики</summary><pre>{JSON.stringify(selectedActivity.metrics, null, 2)}</pre></details>{(selectedActivity.stderr || selectedActivity.stdout) && <details><summary>Технический вывод</summary><pre>{selectedActivity.stderr || selectedActivity.stdout}</pre></details>}<p className="activity-hint">Artifact locator показан в описании завершённой конвертации.</p></> : <p>Выберите событие.</p>}</aside></div>}
        {dockExpanded && dockTab === "issues" && <div className="tray-issues issue-split"><div className="issue-queue">{project.findings.map((finding) => <button className={`${finding.id === selectedFinding?.id ? "active" : ""} issue-${finding.severity}`} key={finding.id} onClick={() => setSelectedFindingId(finding.id)}><i /><span><strong>{finding.title}</strong><small>{finding.code} · {finding.status}</small></span></button>)}</div>{selectedFinding ? <section className="issue-detail"><header><span>{selectedFinding.severity}</span><h3>{selectedFinding.title}</h3><p>{selectedFinding.detail}</p></header><dl><div><dt>Этап</dt><dd>{selectedFinding.stage}</dd></div><div><dt>Код</dt><dd>{selectedFinding.code}</dd></div><div><dt>Статус</dt><dd>{selectedFinding.status}</dd></div></dl>{selectedFindingInventories.length > 0 && <div className="fidelity-comparison">{selectedFindingInventories.map((inventory) => <div key={inventory.id}><header><b>{inventory.stage}</b><span>{inventory.tool_name || inventory.format}</span></header><dl><div><dt>Объекты</dt><dd>{String(inventory.metrics.entity_count ?? "—")}</dd></div><div><dt>Слои</dt><dd>{String(inventory.metrics.layer_count ?? "—")}</dd></div><div><dt>Листы</dt><dd>{String(inventory.metrics.layout_count ?? "—")}</dd></div></dl>{inventory.artifact_locator && <code>{inventory.artifact_locator}</code>}</div>)}</div>}<details><summary>Evidence</summary><pre>{JSON.stringify(selectedFinding.evidence, null, 2)}</pre></details>{selectedFinding.resolution?.reason && <div className="issue-resolution"><b>{selectedFinding.resolution.action}</b><p>{selectedFinding.resolution.reason}</p></div>}<label className="issue-reason">Обоснование решения<textarea rows={2} value={findingReason} onChange={(event) => setFindingReason(event.target.value)} /></label><div className="issue-actions"><button disabled={!!busy} onClick={() => action("retry-search", `/v1/intake/projects/${projectId}/assistant-runs`)}>Повторить анализ</button><button onClick={() => resolveSelectedFinding("reopen")}>Вернуть</button><button className="reject-button" onClick={() => resolveSelectedFinding("block")}>Блокировать</button><button className="action-primary" onClick={() => resolveSelectedFinding("waive")}>Игнорировать в редакции</button></div></section> : <p className="empty-line">Проблем нет.</p>}</div>}
      </section>
      {error && <div className="toast-error" role="alert">{error}<button onClick={() => setError("")}>×</button></div>}
    </main>
  );
}
