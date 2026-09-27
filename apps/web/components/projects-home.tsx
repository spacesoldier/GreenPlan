"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { IntakeProjectSummary, Project } from "@/lib/contracts";
import { domainJson, formatBytes } from "@/lib/domain-client";

type State = "loading" | "ready" | "error";

const stateLabels: Record<string, string> = {
  draft: "Черновик",
  receiving: "Загрузка файлов",
  analyzing: "Анализируется",
  review_required: "Нужна проверка",
  ready_to_publish: "Готов к публикации",
  published: "Опубликован",
  blocked: "Заблокирован",
};

export function ProjectsHome() {
  const [published, setPublished] = useState<Project[]>([]);
  const [intake, setIntake] = useState<IntakeProjectSummary[]>([]);
  const [state, setState] = useState<State>("loading");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      domainJson<{ items: Project[] }>("/v1/projects", { signal: controller.signal }),
      domainJson<{ items: IntakeProjectSummary[] }>("/v1/intake/projects", { signal: controller.signal }),
    ]).then(([publishedResult, intakeResult]) => {
      setPublished(publishedResult.items);
      setIntake(intakeResult.items);
      setState("ready");
    }).catch((reason: Error) => {
      if (reason.name !== "AbortError") {
        setError(reason.message);
        setState("error");
      }
    });
    return () => controller.abort();
  }, []);

  const standalonePublished = useMemo(() => {
    const intakeIds = new Set(intake.map((project) => project.id));
    return published.filter((project) => !intakeIds.has(project.id));
  }, [intake, published]);

  return (
    <main className="projects-page">
      <header className="projects-header">
        <Link className="brand-lockup" href="/" aria-label="GreenPlan — проекты">
          <span className="brand-mark">G</span>
          <span><strong>GreenPlan</strong><small>Инженерная платформа</small></span>
        </Link>
        <div className="projects-heading">
          <span className="eyebrow">Рабочее пространство</span>
          <h1>Проекты озеленения</h1>
          <p>Исходные материалы, контроль преобразований и канонические модели в одном месте.</p>
        </div>
        <div className="projects-header-meta"><i /> локальный контур</div>
      </header>

      {state === "error" ? (
        <section className="projects-message"><strong>Не удалось загрузить проекты</strong><span>{error}</span></section>
      ) : (
        <section className="project-grid" aria-busy={state === "loading"}>
          <Link className="project-tile create-project-tile" href="/projects/new">
            <span className="create-plus" aria-hidden="true">+</span>
            <div><strong>Новый проект</strong><span>Создать и загрузить исходные материалы</span></div>
          </Link>

          {intake.map((project, index) => (
            <Link className="project-tile" href={`/projects/${project.id}`} key={project.id}>
              <div className={`project-cover cover-${index % 4}`}>
                <span>{project.code.slice(0, 2).toUpperCase()}</span>
                <i /><i /><i />
              </div>
              <div className="project-tile-body">
                <div className="project-state-line">
                  <span className={`intake-state state-${project.intake_state}`}>{stateLabels[project.intake_state] ?? project.intake_state}</span>
                  {project.critical_count > 0 && <span className="critical-count">{project.critical_count} крит.</span>}
                </div>
                <h2>{project.title}</h2>
                <p>{project.file_count} файлов · {formatBytes(project.total_bytes)} · {project.cad_count} CAD</p>
                <footer><span>{project.code}</span><time>{new Date(project.updated_at).toLocaleDateString("ru-RU")}</time></footer>
              </div>
            </Link>
          ))}

          {standalonePublished.map((project, index) => (
            <Link className="project-tile" href={`/workspace?project=${project.id}`} key={project.id}>
              <div className={`project-cover cover-${(index + intake.length) % 4}`}>
                <span>{project.code.slice(0, 2).toUpperCase()}</span><i /><i /><i />
              </div>
              <div className="project-tile-body">
                <div className="project-state-line"><span className="intake-state state-published">Опубликован</span></div>
                <h2>{project.title}</h2>
                <p>Модель v{project.model_version} · {project.assembly_status.replaceAll("_", " ")}</p>
                <footer><span>{project.code}</span><span>Открыть чертёж →</span></footer>
              </div>
            </Link>
          ))}

          {state === "loading" && [0, 1, 2].map((value) => <div className="project-tile project-skeleton" key={value} />)}
        </section>
      )}
    </main>
  );
}
