"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import type { IntakeProjectDetail } from "@/lib/contracts";
import { domainJson } from "@/lib/domain-client";

function slugify(value: string): string {
  return value.toLowerCase().trim().replace(/[^a-z0-9а-яё]+/gi, "-")
    .replace(/[а-яё]/gi, (letter) => ({ а:"a",б:"b",в:"v",г:"g",д:"d",е:"e",ё:"e",ж:"zh",з:"z",и:"i",й:"y",к:"k",л:"l",м:"m",н:"n",о:"o",п:"p",р:"r",с:"s",т:"t",у:"u",ф:"f",х:"h",ц:"c",ч:"ch",ш:"sh",щ:"sch",ъ:"",ы:"y",ь:"",э:"e",ю:"yu",я:"ya" }[letter.toLowerCase()] ?? ""))
    .replace(/^-+|-+$/g, "").slice(0, 80);
}

export function CreateProjectForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [codeEdited, setCodeEdited] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const project = await domainJson<IntakeProjectDetail>("/v1/intake/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, code, description: description || null }),
      });
      router.push(`/projects/${project.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось создать проект");
      setBusy(false);
    }
  }

  return (
    <main className="form-page">
      <Link className="back-link" href="/">← Все проекты</Link>
      <section className="project-form-card">
        <div className="form-intro"><span className="eyebrow">Новый проект</span><h1>Начнём с основы</h1><p>Создайте контейнер проекта. На следующем шаге загрузим исходную структуру папок без её разрушения.</p></div>
        <form onSubmit={submit}>
          <label>Название проекта<input autoFocus required minLength={2} value={title} onChange={(event) => { const value=event.target.value; setTitle(value); if (!codeEdited) setCode(slugify(value)); }} placeholder="Песчаный переулок" /></label>
          <label>Код проекта<input required pattern="[a-z0-9][a-z0-9-]*" value={code} onChange={(event) => { setCodeEdited(true); setCode(event.target.value.toLowerCase()); }} placeholder="peschany-pereulok" /><small>Латиница, цифры и дефис. Код используется в ссылках и журнале.</small></label>
          <label>Описание<textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} placeholder="Что входит в поставку, подрядчик, стадия проекта…" /></label>
          {error && <div className="form-error">{error}</div>}
          <div className="form-actions"><Link href="/">Отмена</Link><button className="action-primary" disabled={busy}>{busy ? "Создаём…" : "Создать проект"}</button></div>
        </form>
      </section>
    </main>
  );
}
