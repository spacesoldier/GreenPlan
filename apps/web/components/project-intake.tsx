"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type InputHTMLAttributes } from "react";

import type { IntakeProjectDetail } from "@/lib/contracts";
import { domainJson, formatBytes } from "@/lib/domain-client";
import { inspectFolderSelection, isSupportedProjectFile, partitionProjectFiles, relativeUploadPath } from "@/lib/folder-selection";
import { buildDeliveryTree, groupLayerFamilies, type DeliveryTreeNode } from "@/lib/cad-workbench";

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

function xrefIdentity(path: string | null, name: string): string {
  return (path || name).replaceAll("\\", "/").replace(/^\.\.\//, "").toLocaleLowerCase();
}

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
  const [workbenchView, setWorkbenchView] = useState<"materials" | "explorer" | "issues" | "publish">("explorer");
  const [selectedLayerIds, setSelectedLayerIds] = useState<string[]>([]);
  const [bulkCategory, setBulkCategory] = useState("utility.unknown");
  const [selectedFindingId, setSelectedFindingId] = useState("");
  const [findingReason, setFindingReason] = useState("Ограничение принято для текущей редакции.");
  const [dockExpanded, setDockExpanded] = useState(true);
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
    return next;
  }, [projectId]);

  useEffect(() => {
    load().catch((reason: Error) => setError(reason.message));
  }, [load]);

  useEffect(() => {
    const runActive = project?.assistant_runs?.some((run) => ["queued", "running"].includes(run.state));
    if (project?.intake_state !== "analyzing" && !runActive) return;
    const timer = window.setInterval(() => load().catch(() => undefined), 1800);
    return () => window.clearInterval(timer);
  }, [load, project?.intake_state, project?.assistant_runs]);

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

  async function reviewClassification(id: string, decision: "accept" | "reject", category?: string) {
    await action(`classification-${id}`, `/v1/intake/projects/${projectId}/classifications/${id}/review`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, category: category || null, comment: "Проверено в intake UI" }),
    });
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
  const dependencyUse = project.xref_dependencies.reduce((result, xref) => {
    const key = xrefIdentity(xref.original_path, xref.reference_name);
    const sources = result.get(key) || new Set<string>();
    sources.add(xref.source_asset_id); result.set(key, sources);
    return result;
  }, new Map<string, Set<string>>());
  const xrefCounts = project.xref_dependencies.reduce<Record<string, number>>((result, xref) => {
    result[xref.status] = (result[xref.status] || 0) + 1; return result;
  }, {});
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

  return (
    <main className="intake-page">
      <header className="intake-topbar">
        <Link className="brand-lockup compact" href="/"><span className="brand-mark">G</span><span><strong>GreenPlan</strong><small>Проекты</small></span></Link>
        <nav><Link href="/">Все проекты</Link><span>/</span><strong>{project.title}</strong></nav>
        {project.current_model_id && <Link className="open-model-link" href={`/workspace?project=${project.id}`}>Открыть модель ↗</Link>}
      </header>

      <section className="intake-hero">
        <div><span className="eyebrow">{project.code} · редакция {project.revision_no}</span><h1>{project.title}</h1><p>{project.description || "Описание проекта пока не заполнено."}</p></div>
        <div className="intake-hero-status"><span className={`intake-state state-${project.intake_state}`}>{stateLabels[project.intake_state] ?? project.intake_state}</span><strong>{project.file_count}</strong><small>файлов · {formatBytes(project.total_bytes)}</small></div>
      </section>

      <section className="intake-layout workbench-layout">
        <nav className="wb-nav" aria-label="Разделы проекта">
          <span>Рабочая область</span>
          <button className={workbenchView === "materials" ? "active" : ""} onClick={() => setWorkbenchView("materials")}><i>01</i><b>Материалы</b><small>{project.file_count} файлов</small></button>
          <button className={workbenchView === "explorer" ? "active" : ""} onClick={() => setWorkbenchView("explorer")}><i>02</i><b>CAD Explorer</b><small>{project.cad_layers.length} слоёв</small></button>
          <button className={workbenchView === "issues" ? "active" : ""} onClick={() => setWorkbenchView("issues")}><i>03</i><b>Проблемы</b><small>{project.findings.filter((item) => item.status === "open").length} открыто</small></button>
          <button className={workbenchView === "publish" ? "active" : ""} onClick={() => setWorkbenchView("publish")}><i>04</i><b>Публикация</b><small>{project.fidelity_verdict || "нет вердикта"}</small></button>
        </nav>
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

          {workbenchView === "explorer" && <>
          <article className="intake-card xref-card">
            <div className="card-heading"><div><span>03</span><h2>Связи файлов · XREF</h2></div><p>Дерево показывает, какой DWG подключает зависимость, где она ожидалась и нашёлся ли файл в поставке.</p></div>
            <div className="xref-summary"><span><b>{project.xref_dependencies.length}</b> ссылок</span><span className="resolved"><b>{xrefCounts.resolved || 0}</b> найдены</span><span className="missing"><b>{xrefCounts.missing || 0}</b> отсутствуют</span><span className="ambiguous"><b>{xrefCounts.ambiguous || 0}</b> неоднозначны</span></div>
            <div className="xref-tree">
              {Array.from(xrefsBySource.entries()).map(([sourceId, xrefs]) => <details key={sourceId} open>
                <summary><i>DWG</i><strong>{xrefs[0].source_relative_path}</strong><span>{xrefs.length} ссылок</span></summary>
                <div className="xref-children">{xrefs.map((xref) => {
                  const shared = dependencyUse.get(xrefIdentity(xref.original_path, xref.reference_name))?.size || 1;
                  return <div className={`xref-edge xref-${xref.status}`} key={xref.id}><i /><div><strong>{xref.reference_name}</strong><code>{xref.original_path || "Путь не записан в DWG"}</code><small>{xref.target_relative_path
                    ? `Найден: ${xref.target_relative_path}`
                    : xref.matches.length ? `Кандидаты: ${xref.matches.join(", ")}` : "Совпадений в загруженной поставке нет"}{shared > 1 ? ` · эту зависимость используют ${shared} DWG` : ""}{xref.placement_count ? ` · вставок: ${xref.placement_count}` : ""}</small></div><b>{xref.status}</b></div>;
                })}</div>
              </details>)}
              {!project.xref_dependencies.length && <p className="empty-line">XREF появятся после анализа CAD-файлов.</p>}
            </div>
          </article>

          <article className="intake-card">
            <div className="card-heading"><div><span>04</span><h2>Инспектор слоёв и листов</h2></div><p>Сначала фиксируем факты из DXF, затем подтверждаем семантику. Сейчас работает rules-v2; Laya не подключена.</p></div>
            <div className="layer-toolbar">
              <label><span>Документ</span><select value={layerDocument} onChange={(event) => setLayerDocument(event.target.value)}>{layerDocuments.map(([id, path]) => <option key={id} value={id}>{path}</option>)}</select></label>
              <label><span>Поиск слоя</span><input value={layerQuery} onChange={(event) => setLayerQuery(event.target.value)} placeholder="деревья, кабель…" /></label>
              <div className="layer-modes"><button className={layerMode === "unknown" ? "active" : ""} onClick={() => setLayerMode("unknown")}>Не разобраны</button><button className={layerMode === "all" ? "active" : ""} onClick={() => setLayerMode("all")}>Все</button><button className={layerMode === "reviewed" ? "active" : ""} onClick={() => setLayerMode("reviewed")}>Проверены</button></div>
            </div>
            <div className="bulk-review-bar"><span>Выбрано: <b>{selectedLayerIds.length}</b></span><select value={bulkCategory} onChange={(event) => setBulkCategory(event.target.value)}><option value="utility.unknown">Инженерные сети</option><option value="transport.road">Дороги и проезды</option><option value="surface.lawn">Покрытия и газоны</option><option value="vegetation.existing">Существующая растительность</option><option value="vegetation.proposed">Проектируемая растительность</option><option value="structure.building">Здания и сооружения</option><option value="terrain">Рельеф</option><option value="territory.work_boundary">Границы и зоны</option><option value="not_applicable">Служебное / неприменимо</option><option value="unknown">Не определено</option></select><button disabled={!selectedLayerIds.length || !!busy} onClick={() => reviewSelectedLayers("reject")}>Отклонить</button><button className="action-primary" disabled={!selectedLayerIds.length || !!busy} onClick={() => reviewSelectedLayers("accept")}>Назначить категорию</button></div>
            <div className="space-strip">{selectedSpaces.map((space) => <div className={`space-chip space-${space.space_kind}`} key={space.id}><b>{space.space_kind === "model" ? "MODEL" : "ЛИСТ"}</b><span>{space.name}</span><small>{space.entity_count.toLocaleString("ru-RU")} объектов</small></div>)}{!selectedSpaces.length && <p className="empty-line">Пространства документа не найдены.</p>}</div>
            <div className="layer-table"><header><span>Слой / семейство</span><span>Состав</span><span>Классификация</span><span>Выбор</span></header>{layerFamilies.map(([familyKey, members]) => {
              const layer = members[0];
              const axes = layer.axis_results.axes;
              const suggestionIds = members.filter((item) => item.review_status === "pending").map((item) => item.suggestion_id);
              const selected = suggestionIds.length > 0 && suggestionIds.every((id) => selectedLayerIds.includes(id));
              return <div className="layer-row" key={familyKey}><div><strong>{layer.name}</strong><small>{members.reduce((sum, item) => sum + item.entity_count, 0).toLocaleString("ru-RU")} объектов · {members.length} в семействе · {Math.round((layer.confidence || 0) * 100)}%</small></div><div className="entity-tags">{Object.entries(layer.entity_types).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([kind, count]) => <span key={kind}>{kind} <b>{count}</b></span>)}</div><div className="axis-grid">{axes ? Object.entries(axes).slice(0, 4).map(([axis, value]) => <span key={axis}><em>{axis}</em>{value.label}</span>) : <span>{layer.suggested_category}</span>}</div><div className="layer-family-select"><input type="checkbox" aria-label={`Выбрать семейство ${layer.name}`} disabled={!suggestionIds.length} checked={selected} onChange={() => setSelectedLayerIds((current) => selected ? current.filter((id) => !suggestionIds.includes(id)) : Array.from(new Set([...current, ...suggestionIds])))} /><small>{suggestionIds.length || "✓"}</small></div></div>;
            })}{!selectedLayers.length && <p className="empty-line">В выбранном режиме слоёв нет.</p>}</div>
          </article>
          </>}

          {workbenchView === "issues" && <article className="intake-card issues-workbench"><div className="card-heading"><div><span>03</span><h2>Проблемы и ограничения</h2></div><p>Выберите проблему слева: справа появятся evidence, действия и последствия решения.</p></div><div className="issue-split"><div className="issue-queue">{project.findings.map((finding) => <button className={`${finding.id === selectedFinding?.id ? "active" : ""} issue-${finding.severity}`} key={finding.id} onClick={() => setSelectedFindingId(finding.id)}><i /><span><strong>{finding.title}</strong><small>{finding.code} · {finding.status}</small></span></button>)}</div>{selectedFinding ? <section className="issue-detail"><header><span>{selectedFinding.severity}</span><h3>{selectedFinding.title}</h3><p>{selectedFinding.detail}</p></header><dl><div><dt>Этап</dt><dd>{selectedFinding.stage}</dd></div><div><dt>Код</dt><dd>{selectedFinding.code}</dd></div><div><dt>Статус</dt><dd>{selectedFinding.status}</dd></div></dl>{selectedFindingInventories.length > 0 && <div className="fidelity-comparison">{selectedFindingInventories.map((inventory) => <div key={inventory.id}><header><b>{inventory.stage}</b><span>{inventory.tool_name || inventory.format}</span></header><dl><div><dt>Объекты</dt><dd>{String(inventory.metrics.entity_count ?? "—")}</dd></div><div><dt>Слои</dt><dd>{String(inventory.metrics.layer_count ?? "—")}</dd></div><div><dt>Листы</dt><dd>{String(inventory.metrics.layout_count ?? "—")}</dd></div></dl>{inventory.artifact_locator && <code>{inventory.artifact_locator}</code>}</div>)}</div>}<details open><summary>Evidence</summary><pre>{JSON.stringify(selectedFinding.evidence, null, 2)}</pre></details>{selectedFinding.resolution?.reason && <div className="issue-resolution"><b>{selectedFinding.resolution.action}</b><p>{selectedFinding.resolution.reason}</p></div>}<label className="issue-reason">Обоснование решения<textarea rows={3} value={findingReason} onChange={(event) => setFindingReason(event.target.value)} /></label><div className="issue-actions"><button disabled={!!busy} onClick={() => action("retry-search", `/v1/intake/projects/${projectId}/assistant-runs`)}>Повторить поиск/анализ</button><button onClick={() => resolveSelectedFinding("reopen")}>Вернуть в работу</button><button className="reject-button" onClick={() => resolveSelectedFinding("block")}>Блокировать</button><button className="action-primary" onClick={() => resolveSelectedFinding("waive")}>Игнорировать в редакции</button></div></section> : <p className="empty-line">Проблем нет.</p>}</div></article>}

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

        <aside className="intake-aside">
          {workbenchView === "materials" && <article className="intake-card"><h3>Дерево поставки</h3><div className="delivery-tree"><DeliveryNodes nodes={deliveryTree} /></div></article>}
          {workbenchView === "explorer" && <article className="intake-card"><h3>CAD-граф</h3><div className="cad-nav-tree">{layerDocuments.map(([assetId, path]) => { const refs = xrefsBySource.get(assetId) || []; return <details key={assetId} open={assetId === layerDocument}><summary onClick={() => setLayerDocument(assetId)}><span>DWG</span><b>{path}</b></summary><button onClick={() => setLayerDocument(assetId)}>▦ Пространства <small>{project.cad_spaces.filter((item) => item.source_asset_id === assetId).length}</small></button><button onClick={() => setLayerDocument(assetId)}>≡ Слои <small>{project.cad_layers.filter((item) => item.source_asset_id === assetId).length}</small></button><div className="cad-ref-branch"><em>Внешние ссылки</em>{refs.map((xref) => <button className={`ref-${xref.status}`} key={xref.id} title={xref.original_path || ""} disabled={!xref.referenced_asset_id} onClick={() => xref.referenced_asset_id && setLayerDocument(xref.referenced_asset_id)}><span>↗</span><b>{xref.reference_name}</b><small>{xref.target_relative_path ? "alias → " + xref.target_relative_path : xref.status}</small></button>)}</div></details>; })}</div></article>}
          <article className="intake-card"><h3>Контроль качества</h3><div className="quality-metrics"><div><strong>{project.cad_count}</strong><span>CAD-файлов</span></div><div><strong>{project.finding_count}</strong><span>наблюдений</span></div><div className={project.critical_count ? "danger" : ""}><strong>{project.critical_count}</strong><span>критических</span></div></div><p className="verdict">Вердикт <b>{project.fidelity_verdict?.replaceAll("_", " ") || "ещё не сформирован"}</b></p></article>
        </aside>
      </section>
      <section className={`activity-dock ${dockExpanded ? "expanded" : "collapsed"}`}><button className="activity-dock-toggle" onClick={() => setDockExpanded((value) => !value)}><i className={assistantActive || busy === "upload" ? "is-live" : ""} /><b>Журнал действий</b><span>{selectedActivity?.title || "Событий пока нет"}</span><em>{activityEvents.length}</em><strong>{dockExpanded ? "⌄" : "⌃"}</strong></button>{dockExpanded && <div className="activity-dock-body"><div className="activity-stream">{activityEvents.map((event) => <button className={`activity-event activity-${event.state} ${event.id === selectedActivity?.id ? "selected" : ""}`} key={event.id} onClick={() => setSelectedActivityId(event.id)}><i /><time>{new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(event.at))}</time><div><strong>{event.title}</strong><small>{event.detail}</small></div></button>)}</div><aside>{selectedActivity ? <><span>{selectedActivity.state}</span><h3>{selectedActivity.title}</h3><p>{selectedActivity.detail}</p><dl><div><dt>Время</dt><dd>{new Date(selectedActivity.at).toLocaleString("ru-RU")}</dd></div><div><dt>ID события</dt><dd>{selectedActivity.id}</dd></div></dl><details open><summary>Метрики</summary><pre>{JSON.stringify(selectedActivity.metrics, null, 2)}</pre></details>{(selectedActivity.stderr || selectedActivity.stdout) && <details><summary>Технический вывод</summary><pre>{selectedActivity.stderr || selectedActivity.stdout}</pre></details>}<p className="activity-hint">Artifact locator показан в описании завершённой конвертации.</p></> : <p>Выберите событие.</p>}</aside></div>}</section>
      {error && <div className="toast-error" role="alert">{error}<button onClick={() => setError("")}>×</button></div>}
    </main>
  );
}
