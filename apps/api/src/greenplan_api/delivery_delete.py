from __future__ import annotations

from pathlib import Path
import shutil
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .intake_service import IntakeConflict, normalize_relative_path


def remove_delivery_path(database_url: str, intake_root: Path, project_id: UUID, relative_path: str) -> int:
    """Remove a file or virtual folder from one delivery without deleting source blobs."""
    target = normalize_relative_path(relative_path)
    derived_paths: set[str] = set()
    job_ids: set[UUID] = set()
    asset_ids: list[UUID] = []
    revision_id: UUID | None = None

    with psycopg.connect(database_url, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT pr.id AS revision_id,pw.delivery_id,pw.state
               FROM catalog.projects p
               JOIN LATERAL (
                 SELECT value.* FROM catalog.project_revisions value
                 WHERE value.project_id=p.id ORDER BY revision_no DESC LIMIT 1
               ) pr ON true
               JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               WHERE p.id=%s AND p.deleted_at IS NULL FOR UPDATE OF pw""",
            (project_id,),
        )
        project = cursor.fetchone()
        if project is None:
            raise KeyError(project_id)
        if project["state"] in {"analyzing", "published"}:
            raise IntakeConflict("files cannot be removed while analysis or publication is active")
        revision_id = project["revision_id"]

        cursor.execute(
            """CREATE TEMP TABLE delete_entries ON COMMIT DROP AS
               WITH RECURSIVE selected AS (
                 SELECT de.id,de.source_asset_id FROM intake.delivery_entries de
                 WHERE de.delivery_id=%s AND (
                   de.relative_path=%s OR left(de.relative_path,length(%s)+1)=%s||'/'
                   OR left(de.relative_path,length(%s)+3)=%s||'::/')
                 UNION
                 SELECT child.id,child.source_asset_id FROM intake.delivery_entries child
                 JOIN selected parent ON child.parent_entry_id=parent.id
               ) SELECT DISTINCT id,source_asset_id FROM selected""",
            (project["delivery_id"], target, target, target, target, target),
        )
        cursor.execute("SELECT count(*) AS count FROM delete_entries")
        if not cursor.fetchone()["count"]:
            raise KeyError(target)
        cursor.execute(
            """CREATE TEMP TABLE delete_assets ON COMMIT DROP AS
               WITH RECURSIVE selected AS (
                 SELECT sa.id FROM provenance.source_assets sa
                 WHERE sa.id IN (SELECT source_asset_id FROM delete_entries WHERE source_asset_id IS NOT NULL)
                 UNION
                 SELECT child.id FROM provenance.source_assets child
                 JOIN selected parent ON child.parent_asset_id=parent.id
               ) SELECT DISTINCT id FROM selected"""
        )
        cursor.execute("SELECT id FROM delete_assets")
        asset_ids = [row["id"] for row in cursor.fetchall()]
        if not asset_ids:
            raise IntakeConflict("the selected tree node has no removable project files")
        cursor.execute("SELECT count(*) AS count FROM rules.document_editions WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        if cursor.fetchone()["count"]:
            raise IntakeConflict("the selected files already participate in normative evidence")

        cursor.execute("SELECT id FROM intake.conversion_jobs WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        job_ids = {row["id"] for row in cursor.fetchall()}
        cursor.execute(
            """SELECT storage_locator FROM intake.conversion_artifacts
               WHERE source_asset_id IN (SELECT id FROM delete_assets)
                  OR job_id IN (SELECT id FROM intake.conversion_jobs WHERE source_asset_id IN (SELECT id FROM delete_assets))"""
        )
        derived_paths.update(row["storage_locator"] for row in cursor.fetchall() if row["storage_locator"])
        cursor.execute("SELECT artifact_locator FROM intake.cad_inventories WHERE source_asset_id IN (SELECT id FROM delete_assets) AND artifact_locator IS NOT NULL")
        derived_paths.update(row["artifact_locator"] for row in cursor.fetchall() if row["artifact_locator"])
        cursor.execute("CREATE TEMP TABLE delete_documents ON COMMIT DROP AS SELECT id FROM intake.cad_documents WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        cursor.execute("CREATE TEMP TABLE delete_layers ON COMMIT DROP AS SELECT id FROM intake.cad_layers WHERE cad_document_id IN (SELECT id FROM delete_documents)")
        cursor.execute("CREATE TEMP TABLE delete_fragments ON COMMIT DROP AS SELECT id FROM provenance.source_fragments WHERE source_asset_id IN (SELECT id FROM delete_assets)")

        cursor.execute("""DELETE FROM intake.classification_reviews WHERE suggestion_id IN (
            SELECT id FROM intake.classification_suggestions
            WHERE source_asset_id IN (SELECT id FROM delete_assets) OR cad_layer_id IN (SELECT id FROM delete_layers))""")
        cursor.execute("DELETE FROM intake.classification_suggestions WHERE source_asset_id IN (SELECT id FROM delete_assets) OR cad_layer_id IN (SELECT id FROM delete_layers)")
        cursor.execute("DELETE FROM intake.semantic_suggestion_jobs WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        cursor.execute("DELETE FROM intake.finding_resolutions WHERE finding_id IN (SELECT id FROM intake.fidelity_findings WHERE revision_id=%s)", (revision_id,))
        cursor.execute("DELETE FROM intake.fidelity_findings WHERE revision_id=%s", (revision_id,))
        cursor.execute("UPDATE intake.project_workflows SET last_run_id=NULL WHERE revision_id=%s", (revision_id,))
        cursor.execute("DELETE FROM intake.assistant_runs WHERE revision_id=%s", (revision_id,))
        cursor.execute("""DELETE FROM intake.publications WHERE artifact_id IN (
            SELECT id FROM intake.conversion_artifacts
            WHERE source_asset_id IN (SELECT id FROM delete_assets)
               OR job_id IN (SELECT id FROM intake.conversion_jobs WHERE source_asset_id IN (SELECT id FROM delete_assets)))""")
        cursor.execute("""DELETE FROM intake.conversion_artifacts
            WHERE source_asset_id IN (SELECT id FROM delete_assets)
               OR job_id IN (SELECT id FROM intake.conversion_jobs WHERE source_asset_id IN (SELECT id FROM delete_assets))""")
        cursor.execute("DELETE FROM intake.conversion_jobs WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        cursor.execute("""DELETE FROM intake.cad_entities
            WHERE cad_document_id IN (SELECT id FROM delete_documents)
               OR cad_layer_id IN (SELECT id FROM delete_layers)
               OR source_fragment_id IN (SELECT id FROM delete_fragments)""")
        cursor.execute("DELETE FROM intake.cad_xrefs WHERE cad_document_id IN (SELECT id FROM delete_documents)")
        cursor.execute("""UPDATE intake.cad_xrefs SET referenced_asset_id=NULL,resolved_status='missing',
            properties=properties||jsonb_build_object('removed_from_delivery',true)
            WHERE referenced_asset_id IN (SELECT id FROM delete_assets)""")
        cursor.execute("DELETE FROM intake.cad_layers WHERE id IN (SELECT id FROM delete_layers)")
        cursor.execute("DELETE FROM intake.cad_documents WHERE id IN (SELECT id FROM delete_documents)")
        cursor.execute("DELETE FROM intake.cad_inventories WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        cursor.execute("DELETE FROM intake.feature_snapshots WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        cursor.execute("DELETE FROM intake.master_candidates WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        cursor.execute("DELETE FROM intake.processing_stage_attempts WHERE source_asset_id IN (SELECT id FROM delete_assets)")
        cursor.execute("""UPDATE intake.project_workflows SET selected_master_asset_id=NULL,state='receiving',
            fidelity_verdict=NULL,review_comment=NULL,published_at=NULL,updated_at=now() WHERE revision_id=%s""", (revision_id,))
        cursor.execute("UPDATE intake.delivery_entries SET parent_entry_id=NULL WHERE parent_entry_id IN (SELECT id FROM delete_entries)")
        cursor.execute("DELETE FROM intake.delivery_entries WHERE source_asset_id IN (SELECT id FROM delete_assets) OR id IN (SELECT id FROM delete_entries)")
        cursor.execute("UPDATE provenance.source_assets SET parent_asset_id=NULL WHERE parent_asset_id IN (SELECT id FROM delete_assets)")
        cursor.execute("DELETE FROM provenance.source_fragments WHERE id IN (SELECT id FROM delete_fragments)")
        cursor.execute("DELETE FROM provenance.source_assets WHERE id IN (SELECT id FROM delete_assets)")
        cursor.execute(
            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,metadata)
               VALUES ('remove_delivery_path','intake','deliveries',%s,%s)""",
            (project["delivery_id"], Jsonb({"relative_path": target, "removed_assets": len(asset_ids)})),
        )

    # Source blobs are retained. Only disposable conversion output is swept.
    root = intake_root.resolve()
    removable: set[Path] = {root / "jobs" / str(job_id) for job_id in job_ids}
    if revision_id is not None:
        removable.update(root / "derived" / str(revision_id) / str(asset_id) for asset_id in asset_ids)
    for locator in derived_paths:
        candidate = (root / locator).resolve()
        if root in candidate.parents and candidate.relative_to(root).parts[:1] in {("jobs",), ("derived",)}:
            removable.add(candidate)
    for candidate in sorted(removable, key=lambda path: len(path.parts), reverse=True):
        try:
            if candidate.is_dir():
                shutil.rmtree(candidate)
            else:
                candidate.unlink(missing_ok=True)
        except OSError:
            pass
    return len(asset_ids)
