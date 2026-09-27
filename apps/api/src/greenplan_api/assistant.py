from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable, Mapping
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


ASSISTANT_SCHEMA_VERSION = "intake-assistant-v1"
TAXONOMY_VERSION = "cad-v1"
RULES_VERSION = "rules-v2"


@dataclass(frozen=True)
class AssistantTaskSpec:
    key: str
    title: str
    dependencies: tuple[str, ...] = ()


ASSISTANT_TASKS = (
    AssistantTaskSpec("inventory", "Инвентаризация и конвертация"),
    AssistantTaskSpec("xref_graph", "Разрешение внешних ссылок", ("inventory",)),
    AssistantTaskSpec("semantic_taxonomy", "Классификация файлов и слоёв", ("inventory",)),
    AssistantTaskSpec("summary", "Сводка и очередь проверки", ("xref_graph", "semantic_taxonomy")),
)


def assistant_fingerprint(
    entries: Iterable[Mapping[str, object]],
    *,
    taxonomy_version: str = TAXONOMY_VERSION,
    provider_version: str = RULES_VERSION,
) -> str:
    normalized = sorted(
        ({"relative_path": str(item["relative_path"]), "sha256": str(item["sha256"])} for item in entries),
        key=lambda item: (item["relative_path"], item["sha256"]),
    )
    payload = {
        "schema_version": ASSISTANT_SCHEMA_VERSION,
        "taxonomy_version": taxonomy_version,
        "provider_version": provider_version,
        "entries": normalized,
    }
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def runnable_tasks(states: Mapping[str, str]) -> list[str]:
    completed = {key for key, state in states.items() if state in {"completed", "completed_with_warnings"}}
    return [
        task.key for task in ASSISTANT_TASKS
        if states.get(task.key) == "pending" and all(dependency in completed for dependency in task.dependencies)
    ]


def _connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def create_or_resume_run(database_url: str, project_id: UUID) -> tuple[UUID, bool]:
    """Return the logical run for the current immutable input fingerprint."""
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT pr.id AS revision_id,pw.delivery_id
               FROM catalog.project_revisions pr
               JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               WHERE pr.project_id=%s ORDER BY pr.revision_no DESC LIMIT 1""",
            (project_id,),
        )
        revision = cursor.fetchone()
        if revision is None:
            raise KeyError(project_id)
        cursor.execute(
            """SELECT de.relative_path,sa.sha256
               FROM intake.delivery_entries de
               JOIN provenance.source_assets sa ON sa.id=de.source_asset_id
               WHERE de.delivery_id=%s ORDER BY de.relative_path""",
            (revision["delivery_id"],),
        )
        entries = cursor.fetchall()
        if not entries:
            raise ValueError("upload at least one file before starting the assistant")
        fingerprint = assistant_fingerprint(entries)
        cursor.execute(
            """INSERT INTO intake.assistant_runs(
                   revision_id,input_fingerprint,schema_version,taxonomy_version,provider_version,
                   state,summary,started_at,heartbeat_at)
               VALUES (%s,%s,%s,%s,%s,'queued','{}'::jsonb,now(),now())
               ON CONFLICT (revision_id,input_fingerprint) DO NOTHING
               RETURNING id""",
            (revision["revision_id"], fingerprint, ASSISTANT_SCHEMA_VERSION, TAXONOMY_VERSION, RULES_VERSION),
        )
        inserted = cursor.fetchone()
        created = inserted is not None
        if created:
            run_id = inserted["id"]
        else:
            cursor.execute(
                "SELECT id,state FROM intake.assistant_runs WHERE revision_id=%s AND input_fingerprint=%s",
                (revision["revision_id"], fingerprint),
            )
            existing = cursor.fetchone()
            run_id = existing["id"]
            if existing["state"] == "failed":
                cursor.execute(
                    """UPDATE intake.assistant_runs SET state='queued',progress=0,error_summary=NULL,
                              finished_at=NULL,heartbeat_at=now() WHERE id=%s""",
                    (run_id,),
                )
                cursor.execute(
                    """UPDATE intake.assistant_tasks SET state='pending',progress=0,error_summary=NULL,
                              finished_at=NULL WHERE run_id=%s AND state='failed'""",
                    (run_id,),
                )
        for position, task in enumerate(ASSISTANT_TASKS):
            cursor.execute(
                """INSERT INTO intake.assistant_tasks(
                       run_id,task_key,title,position,state,dependencies,input_fingerprint)
                   VALUES (%s,%s,%s,%s,'pending',%s,%s)
                   ON CONFLICT (run_id,task_key) DO NOTHING""",
                (run_id, task.key, task.title, position, list(task.dependencies), fingerprint),
            )
        return run_id, created


def execute_run(
    database_url: str,
    intake_root: Path,
    project_id: UUID,
    run_id: UUID,
    broker_url: str | None,
) -> None:
    """Execute the bounded v1 DAG and persist every committed boundary.

    Existing intake functions remain the implementation of the inventory step. The other
    v1 tasks verify/materialize results already produced by that step; this makes resume and
    future task extraction possible without creating a second ingestion pipeline.
    """
    from .intake_service import analyze_revision

    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE intake.assistant_runs SET state='running',heartbeat_at=now()
               WHERE id=%s AND state NOT IN ('completed','review_required','blocked','cancelled')""",
            (run_id,),
        )

    while True:
        with _connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT state,cancel_requested FROM intake.assistant_runs WHERE id=%s", (run_id,))
            run = cursor.fetchone()
            if run is None or run["state"] in {"completed", "review_required", "blocked", "failed", "cancelled"}:
                return
            if run["cancel_requested"]:
                cursor.execute("UPDATE intake.assistant_runs SET state='cancelled',finished_at=now() WHERE id=%s", (run_id,))
                cursor.execute(
                    "UPDATE intake.assistant_tasks SET state='cancelled',finished_at=now() WHERE run_id=%s AND state='pending'",
                    (run_id,),
                )
                return
            cursor.execute("SELECT task_key,state FROM intake.assistant_tasks WHERE run_id=%s", (run_id,))
            states = {row["task_key"]: row["state"] for row in cursor.fetchall()}
            available = runnable_tasks(states)
            if not available:
                if all(state in {"completed", "completed_with_warnings"} for state in states.values()):
                    cursor.execute(
                        """SELECT pw.state,pw.fidelity_verdict,
                                  (SELECT count(*) FROM intake.classification_suggestions cs
                                   JOIN intake.assistant_runs ar ON ar.revision_id=cs.revision_id
                                   WHERE ar.id=%s AND cs.review_status='pending') AS pending_reviews
                           FROM intake.assistant_runs ar
                           JOIN intake.project_workflows pw ON pw.revision_id=ar.revision_id
                           WHERE ar.id=%s""",
                        (run_id, run_id),
                    )
                    result = cursor.fetchone()
                    if result["state"] == "analyzing":
                        cursor.execute(
                            """UPDATE intake.assistant_runs SET state='running',progress=.95,
                                      summary=%s,heartbeat_at=now() WHERE id=%s""",
                            (Jsonb({"workflow_state": "analyzing", "waiting_for": "conversion_workers"}), run_id),
                        )
                        return
                    terminal = "review_required" if result["pending_reviews"] or result["state"] != "published" else "completed"
                    cursor.execute(
                        """UPDATE intake.assistant_runs SET state=%s,progress=1,summary=%s,
                                  heartbeat_at=now(),finished_at=now() WHERE id=%s""",
                        (terminal, Jsonb({"workflow_state": result["state"], "fidelity_verdict": result["fidelity_verdict"],
                                         "pending_reviews": result["pending_reviews"]}), run_id),
                    )
                return
            task_key = available[0]
            cursor.execute(
                """UPDATE intake.assistant_tasks SET state='running',attempts=attempts+1,
                          started_at=COALESCE(started_at,now()),heartbeat_at=now(),error_summary=NULL
                   WHERE run_id=%s AND task_key=%s AND state='pending'""",
                (run_id, task_key),
            )
        try:
            if task_key == "inventory":
                analyze_revision(database_url, intake_root, project_id, broker_url)
            with _connect(database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE intake.assistant_tasks SET state='completed',progress=1,
                              heartbeat_at=now(),finished_at=now() WHERE run_id=%s AND task_key=%s""",
                    (run_id, task_key),
                )
                cursor.execute(
                    """UPDATE intake.assistant_runs SET heartbeat_at=now(),progress=(
                           SELECT count(*) FILTER (WHERE state IN ('completed','completed_with_warnings'))::numeric /
                                  GREATEST(count(*),1) FROM intake.assistant_tasks WHERE run_id=%s)
                       WHERE id=%s""",
                    (run_id, run_id),
                )
        except Exception as exc:
            with _connect(database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE intake.assistant_tasks SET state='failed',error_summary=%s,
                              heartbeat_at=now(),finished_at=now() WHERE run_id=%s AND task_key=%s""",
                    (str(exc), run_id, task_key),
                )
                cursor.execute(
                    """UPDATE intake.assistant_runs SET state='failed',error_summary=%s,
                              heartbeat_at=now(),finished_at=now() WHERE id=%s""",
                    (str(exc), run_id),
                )
            return


def reconcile_project_runs(database_url: str, project_id: UUID) -> None:
    """Close runs whose asynchronous conversion jobs were synchronized by refresh_workflow."""
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT ar.id,pw.state,pw.fidelity_verdict
               FROM intake.assistant_runs ar
               JOIN catalog.project_revisions pr ON pr.id=ar.revision_id
               JOIN intake.project_workflows pw ON pw.revision_id=ar.revision_id
               WHERE pr.project_id=%s AND ar.state='running'
                 AND NOT EXISTS (
                   SELECT 1 FROM intake.assistant_tasks task
                   WHERE task.run_id=ar.id AND task.state NOT IN ('completed','completed_with_warnings')
                 )""",
            (project_id,),
        )
        for run in cursor.fetchall():
            if run["state"] == "analyzing":
                continue
            cursor.execute(
                """SELECT count(*) AS pending FROM intake.classification_suggestions cs
                   JOIN intake.assistant_runs ar ON ar.revision_id=cs.revision_id
                   WHERE ar.id=%s AND cs.review_status='pending'""",
                (run["id"],),
            )
            pending = cursor.fetchone()["pending"]
            terminal = "review_required" if pending or run["state"] != "published" else "completed"
            cursor.execute(
                """UPDATE intake.assistant_runs SET state=%s,progress=1,summary=%s,
                          heartbeat_at=now(),finished_at=now() WHERE id=%s""",
                (terminal, Jsonb({"workflow_state": run["state"], "fidelity_verdict": run["fidelity_verdict"],
                                  "pending_reviews": pending}), run["id"]),
            )
