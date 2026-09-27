"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import type { IntakeProjectDetail } from "@/lib/contracts";
import { domainJson, formatBytes } from "@/lib/domain-client";

const stateLabels: Record<string, string> = {
  draft: "Черновик", receiving: "Приём файлов", analyzing: "Анализ",
  review_required: "Инженерная проверка", ready_to_publish: "Готов к публикации",
  published: "Опубликован", blocked: "Заблокирован", failed: "Ошибка",
};

function relativeName(file: File): string {
  return (file.webkitRelativePath || file.name).replace(/^\/+/, "");
}

export function ProjectIntake({ projectId }: { projectId: string }) {
  const folderInput = useRef<HTMLInputElement>(null);
  const [project, setProject] = useState<IntakeProjectDetail | null>(null);
  const [selectedMaster, setSelectedMaster] = useState("");
  const [comment, setComment] = useState("Проверено инженером; ограничения преобразования приняты.");
  const [busy, setBusy] = useState("");
  const [uploadProgress, setUploadProgress] = useState<[number, number] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const next = await domainJson<IntakeProjectDetail>(`/v1/intake/projects/${projectId}`);
    setProject(next);
    setSelectedMaster((current) => current || next.master_candidates.find((item) => item.selected)?.source_asset_id || next.master_candidates[0]?.source_asset_id || "");
    return next;
  }, [projectId]);

  useEffect(() => {
    folderInput.current?.setAttribute("webkitdirectory", "");
    folderInput.current?.setAttribute("directory", "");
  }, []);

  useEffect(() => {
    load().catch((reason: Error) => setError(reason.message));
  }, [load]);

  useEffect(() => {
    if (project?.intake_state !== "analyzing") return;
    const timer = window.setInterval(() => load().catch(() => undefined), 1800);
    return () => window.clearInterval(timer);
  }, [load, project?.intake_state]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy("upload"); setError(""); setUploadProgress([0, files.length]);
    try {
      for (let index = 0; index < files.length; index += 1) {
        const form = new FormData();
        form.set("relative_path", relativeName(files[index]));
        form.set("file", files[index]);
        await domainJson(`/v1/intake/projects/${projectId}/files`, { method: "POST", body: form });
        setUploadProgress([index + 1, files.length]);
      }
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ошибка загрузки");
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

  if (!project) return <main className="intake-loading"><span className="loader" /><strong>{error || "Открываем проект…"}</strong></main>;
  const mayAnalyze = project.file_count > 0 && !["analyzing", "published"].includes(project.intake_state);
  const mayReview = project.intake_state === "review_required"
    && !!selectedMaster
    && project.critical_count === 0
    && project.fidelity_verdict !== "rejected";

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

      <section className="intake-layout">
        <div className="intake-main">
          <article className="intake-card upload-card">
            <div className="card-heading"><div><span>01</span><h2>Исходные материалы</h2></div><p>Структура папок и контрольные суммы сохраняются как доказательство поставки.</p></div>
            <div className="upload-actions">
              <label className="upload-drop"><input ref={folderInput} type="file" multiple onChange={(event) => upload(event.target.files)} /><b>＋</b><strong>Загрузить папку проекта</strong><span>DWG, DXF, PDF, XLSX, ZIP и связанные файлы</span></label>
              <label className="upload-file"><input type="file" multiple onChange={(event) => upload(event.target.files)} />Добавить отдельные файлы</label>
            </div>
            {uploadProgress && <div className="upload-progress"><i style={{ width: `${uploadProgress[0] / uploadProgress[1] * 100}%` }} /><span>{uploadProgress[0]} / {uploadProgress[1]}</span></div>}
            <div className="file-list">
              {project.files.length === 0 ? <p className="empty-line">Файлы ещё не загружены</p> : project.files.map((file) => (
                <div className="file-row" key={file.id}><span className={`file-kind kind-${file.detected_format}`}>{(file.detected_format || file.relative_path.split(".").pop() || "file").toUpperCase()}</span><div><strong>{file.relative_path}</strong><small>{formatBytes(file.size_bytes)} · {file.sha256.slice(0, 12)} · {file.role?.replaceAll("_", " ") || "не разобран"}</small></div><em>{file.format_version || "—"}</em></div>
              ))}
            </div>
          </article>

          <article className="intake-card">
            <div className="card-heading"><div><span>02</span><h2>Контролируемый анализ</h2></div><p>Прямое чтение DWG, fallback через ODA, инвентаризация DXF и проверка внешних ссылок.</p></div>
            <button className="action-primary analyze-button" disabled={!mayAnalyze || !!busy} onClick={() => action("analyze", `/v1/intake/projects/${projectId}/analyze`)}>{project.intake_state === "analyzing" ? "Анализ выполняется…" : "Запустить анализ поставки"}</button>
            <div className="stage-list">
              {project.stages.length === 0 ? <p className="empty-line">После запуска здесь появится журнал этапов.</p> : project.stages.map((stage) => (
                <details className="stage-row" key={stage.id}><summary><i className={`stage-dot stage-${stage.state}`} /><div><strong>{stage.stage.replaceAll("_", " ")}</strong><small>{stage.error_summary || `${Math.round(stage.progress * 100)}% · попытка ${stage.attempt_no}`}</small></div><span>{stage.state.replaceAll("_", " ")}</span></summary>{(stage.stderr || stage.stdout) && <pre>{stage.stderr || stage.stdout}</pre>}</details>
              ))}
            </div>
          </article>

          <article className="intake-card">
            <div className="card-heading"><div><span>03</span><h2>Разбор состава и слоёв</h2></div><p>Правила предлагают категорию; инженер подтверждает её. Неясные случаи позже сможет разбирать локальная Laya.</p></div>
            <div className="classification-list">
              {project.classification_suggestions
                .filter((item) => item.review_status === "pending")
                .sort((a, b) => a.confidence - b.confidence)
                .slice(0, 30)
                .map((item) => <div className="classification-row" key={item.id}>
                  <span>{item.target_kind === "file" ? "Файл" : "Слой"}</span>
                  <div><strong title={item.target_label}>{item.target_label}</strong><small>{item.suggested_category.replaceAll("_", " ")} · {Math.round(item.confidence * 100)}% · {item.method}</small></div>
                  <button disabled={!!busy} onClick={() => reviewClassification(item.id, "reject")}>×</button>
                  <button className="classification-accept" disabled={!!busy} onClick={() => reviewClassification(item.id, "accept")}>✓</button>
                </div>)}
              {!project.classification_suggestions.some((item) => item.review_status === "pending") && <p className="empty-line">Подсказки появятся после анализа поставки.</p>}
            </div>
            {project.classification_suggestions.filter((item) => item.review_status === "pending").length > 30 && <p className="empty-line">Показаны 30 самых неуверенных подсказок.</p>}
          </article>

          <article className="intake-card">
            <div className="card-heading"><div><span>04</span><h2>Вердикт и публикация</h2></div><p>Мастер выбирает человек. Неоднозначности и потери остаются видимыми в журнале.</p></div>
            <div className="candidate-list">
              {project.master_candidates.map((candidate) => <label className={`candidate-row ${selectedMaster === candidate.source_asset_id ? "selected" : ""}`} key={candidate.source_asset_id}><input type="radio" name="master" checked={selectedMaster === candidate.source_asset_id} onChange={() => setSelectedMaster(candidate.source_asset_id)} /><div><strong>{candidate.relative_path}</strong><small>{candidate.role.replaceAll("_", " ")} · признаки: {candidate.cues.join(", ") || "нет"}</small></div><b>{candidate.score.toFixed(0)}</b></label>)}
              {!project.master_candidates.length && <p className="empty-line">Кандидаты появятся после анализа CAD-файлов.</p>}
            </div>
            {project.intake_state === "review_required" && <div className="review-box">{project.critical_count > 0 && <p className="review-blocked-note">Сначала устраните {project.critical_count} критических замечаний и запустите анализ повторно.</p>}<label>Комментарий инженерной проверки<textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} /></label><div><button className="reject-button" disabled={!!busy} onClick={() => action("reject", `/v1/intake/projects/${projectId}/review`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "reject", comment, selected_master_asset_id: selectedMaster || null }) })}>Отклонить</button><button className="action-primary" disabled={!mayReview || comment.length < 3 || !!busy} onClick={() => action("review", `/v1/intake/projects/${projectId}/review`, { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "accept", comment, selected_master_asset_id: selectedMaster }) })}>Принять с фиксацией</button></div></div>}
            {project.intake_state === "ready_to_publish" && <button className="action-primary publish-button" disabled={!!busy} onClick={() => action("publish", `/v1/intake/projects/${projectId}/publish`)}>Опубликовать каноническую модель</button>}
          </article>
        </div>

        <aside className="intake-aside">
          <article className="intake-card"><h3>Контроль качества</h3><div className="quality-metrics"><div><strong>{project.cad_count}</strong><span>CAD-файлов</span></div><div><strong>{project.finding_count}</strong><span>наблюдений</span></div><div className={project.critical_count ? "danger" : ""}><strong>{project.critical_count}</strong><span>критических</span></div></div><p className="verdict">Вердикт <b>{project.fidelity_verdict?.replaceAll("_", " ") || "ещё не сформирован"}</b></p></article>
          <article className="intake-card"><h3>Наблюдения</h3><div className="finding-list">{project.findings.map((finding) => <div className={`finding finding-${finding.severity}`} key={finding.id}><span>{finding.severity}</span><strong>{finding.title}</strong><p>{finding.detail}</p></div>)}{!project.findings.length && <p className="empty-line">Пока замечаний нет.</p>}</div></article>
          <article className="intake-card"><h3>Инвентаризация CAD</h3><div className="inventory-list">{project.inventories.map((inventory) => <div key={inventory.id}><strong>{inventory.relative_path}</strong><span>{inventory.stage} · {inventory.parse_status}</span><small>{String(inventory.metrics.entity_count ?? "—")} объектов · {String(inventory.metrics.layer_count ?? "—")} слоёв · {String(inventory.metrics.layout_count ?? "—")} листов</small></div>)}{!project.inventories.length && <p className="empty-line">Нет результатов.</p>}</div></article>
        </aside>
      </section>
      {error && <div className="toast-error" role="alert">{error}<button onClick={() => setError("")}>×</button></div>}
    </main>
  );
}
