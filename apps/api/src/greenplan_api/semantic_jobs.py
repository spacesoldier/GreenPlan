from __future__ import annotations

from hashlib import sha256
import json
import os
from typing import Any
from urllib.request import urlopen
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .decision_models import DecisionProviderError, canonical_layer_category_match, laya_layer_category
from .dxf_ingest import classify_layer


PROVIDER = "laya"
MODEL = "convaiinnovations/laya:multilingual"
METHOD = "laya-layer-jev-v1"
SEMANTIC_JOB_SCOPE = "selected_document"
JOB_VIEW_COLUMNS = """id,source_asset_id,scope,provider,model,state,
                      total_count,completed_count,failed_count,error_summary,started_at,heartbeat_at,
                      finished_at,created_at"""

def assistant_category_is_assignable(category: str) -> bool:
    return category != "unknown"


class NoUnclassifiedLayers(RuntimeError):
    pass


SEMANTIC_LAYER_SCOPE_SQL = """SELECT cl.id AS cad_layer_id,cs.target_key,cs.feature_snapshot_id,
                      cs.axis_results,fs.features,cs.taxonomy_version
               FROM intake.cad_layers cl
               JOIN intake.cad_documents cd ON cd.id=cl.cad_document_id
               JOIN intake.classification_suggestions cs
                 ON cs.cad_layer_id=cl.id AND cs.revision_id=%s AND cs.method='multi-axis-rules-v2'
               JOIN intake.feature_snapshots fs ON fs.id=cs.feature_snapshot_id
               WHERE cd.source_asset_id=%s AND cl.mapping_status<>'confirmed' ORDER BY cl.name"""


def _connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def semantic_provider_ready(base_url: str, timeout: float = 1.5) -> bool:
    try:
        with urlopen(f"{base_url.rstrip('/')}/health", timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def create_semantic_suggestion_job(
    database_url: str, project_id: UUID, source_asset_id: UUID,
) -> tuple[dict[str, Any], bool]:
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT pr.id AS revision_id,(count(cl.id) FILTER (WHERE cl.mapping_status<>'confirmed'))::int AS layer_count,
                      COALESCE((string_agg(fs.fingerprint,',' ORDER BY fs.fingerprint) FILTER (WHERE cl.mapping_status<>'confirmed')), '') AS fingerprints
               FROM catalog.project_revisions pr
               JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               JOIN intake.delivery_entries de ON de.delivery_id=pw.delivery_id AND de.source_asset_id=%s
               JOIN intake.cad_documents cd ON cd.source_asset_id=de.source_asset_id
               JOIN intake.cad_layers cl ON cl.cad_document_id=cd.id
               LEFT JOIN intake.classification_suggestions cs
                 ON cs.cad_layer_id=cl.id AND cs.method='multi-axis-rules-v2'
               LEFT JOIN intake.feature_snapshots fs ON fs.id=cs.feature_snapshot_id
               WHERE pr.project_id=%s
               GROUP BY pr.id,pr.revision_no ORDER BY pr.revision_no DESC LIMIT 1""",
            (source_asset_id, project_id),
        )
        scope = cursor.fetchone()
        if scope is None:
            raise KeyError("CAD document or layers do not exist")
        if not scope["layer_count"]:
            raise NoUnclassifiedLayers("Все слои выбранного CAD-файла уже имеют назначенный класс")
        fingerprint = sha256(json.dumps({
            "revision_id": str(scope["revision_id"]), "source_asset_id": str(source_asset_id),
            "provider": PROVIDER, "model": MODEL, "features": scope["fingerprints"],
        }, sort_keys=True).encode()).hexdigest()
        cursor.execute(
            f"""SELECT {JOB_VIEW_COLUMNS} FROM intake.semantic_suggestion_jobs
               WHERE revision_id=%s AND source_asset_id=%s AND provider=%s AND model=%s
                 AND state IN ('queued','running') ORDER BY created_at DESC LIMIT 1""",
            (scope["revision_id"], source_asset_id, PROVIDER, MODEL),
        )
        existing = cursor.fetchone()
        if existing:
            return existing, False
        job_id = uuid4()
        cursor.execute(
            f"""INSERT INTO intake.semantic_suggestion_jobs(
                   id,project_id,revision_id,source_asset_id,provider,model,input_fingerprint,state,total_count)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',%s) RETURNING {JOB_VIEW_COLUMNS}""",
            (job_id, project_id, scope["revision_id"], source_asset_id, PROVIDER, MODEL, fingerprint, scope["layer_count"]),
        )
        return cursor.fetchone(), True


def get_semantic_suggestion_job(database_url: str, project_id: UUID, job_id: UUID) -> dict[str, Any] | None:
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            f"""SELECT {JOB_VIEW_COLUMNS}
               FROM intake.semantic_suggestion_jobs WHERE project_id=%s AND id=%s""",
            (project_id, job_id),
        )
        return cursor.fetchone()


def enqueue_semantic_suggestion_job(broker_url: str, job_id: UUID) -> None:
    from celery import Celery

    Celery("greenplan-api", broker=broker_url).send_task(
        "greenplan.semantic.suggest_layers", args=[str(job_id)], queue="semantic",
    )


def execute_semantic_suggestion_job(database_url: str, laya_url: str, job_id: UUID) -> None:
    if not laya_url:
        with _connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE intake.semantic_suggestion_jobs SET state='failed',
                          error_summary='LAYA_URL is not configured for semantic worker',finished_at=now()
                   WHERE id=%s AND state IN ('queued','running')""",
                (job_id,),
            )
        return
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE intake.semantic_suggestion_jobs SET state='running',started_at=now(),heartbeat_at=now()
               WHERE id=%s AND state='queued' RETURNING project_id,revision_id,source_asset_id,total_count""",
            (job_id,),
        )
        job = cursor.fetchone()
        if job is None:
            return
        # Deliberately file-scoped: do not traverse cad_xrefs or sibling documents.
        cursor.execute(
            SEMANTIC_LAYER_SCOPE_SQL,
            (job["revision_id"], job["source_asset_id"]),
        )
        layers = cursor.fetchall()

    completed = 0
    failed = 0
    consecutive_failures = 0
    errors: list[str] = []
    for layer in layers:
        try:
            layer_name = str(layer["features"].get("layer_name", ""))
            canonical_match = canonical_layer_category_match(layer_name)
            lexical_match = classify_layer(layer_name)
            if canonical_match:
                category, confidence, cue = canonical_match
                cues = [cue]
                alternatives = [{"category": category, "confidence": confidence}]
                resolution_method = "canonical_layer_alias_v2"
                model_invoked = False
            elif lexical_match.class_code != "unknown.constraint" and lexical_match.confidence >= 0.90:
                category, confidence = lexical_match.class_code, lexical_match.confidence
                cues = [f"Русская CAD-основа или сокращение: {lexical_match.reason}"]
                alternatives = [{"category": category, "confidence": confidence}]
                resolution_method = "cad_lexeme_rules_v1"
                model_invoked = False
            else:
                suggestion = laya_layer_category(
                    laya_url, feature_snapshot=layer["features"], api_key=os.getenv("LAYA_API_KEY"),
                )
                category, confidence = suggestion.category, suggestion.confidence
                cues = list(suggestion.cues)
                alternatives = [{"category": key, "confidence": value} for key, value in suggestion.alternatives]
                resolution_method = "decision_model"
                model_invoked = True
            axis_results = dict(layer["axis_results"] or {})
            axes = dict(axis_results.get("axes") or {})
            axes["object_class"] = {"label": category, "confidence": confidence, "cues": cues}
            axis_results["axes"] = axes
            axis_results["review_required"] = category == "unknown"
            axis_results["auto_confirmed"] = not model_invoked
            axis_results["assistant_assigned"] = assistant_category_is_assignable(category)
            axis_results["resolution_method"] = resolution_method
            with _connect(database_url) as connection, connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO intake.classification_suggestions(
                           revision_id,target_kind,target_key,source_asset_id,cad_layer_id,suggested_category,
                           confidence,method,input_snapshot,cues,alternatives,taxonomy_version,axis_results,
                           feature_snapshot_id,provider_run)
                       VALUES (%s,'cad_layer',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (revision_id,target_kind,target_key,method) DO UPDATE SET
                         suggested_category=EXCLUDED.suggested_category,confidence=EXCLUDED.confidence,
                         input_snapshot=EXCLUDED.input_snapshot,cues=EXCLUDED.cues,
                         alternatives=EXCLUDED.alternatives,axis_results=EXCLUDED.axis_results,
                         feature_snapshot_id=EXCLUDED.feature_snapshot_id,provider_run=EXCLUDED.provider_run,
                         review_status='pending',reviewed_category=NULL,review_comment=NULL,reviewed_at=NULL
                       WHERE intake.classification_suggestions.review_status='pending'
                       RETURNING id""",
                    (
                        job["revision_id"], layer["target_key"], job["source_asset_id"], layer["cad_layer_id"],
                        category, confidence, METHOD, Jsonb(layer["features"]),
                        Jsonb(cues), Jsonb(alternatives),
                        layer["taxonomy_version"], Jsonb(axis_results), layer["feature_snapshot_id"],
                        Jsonb({"provider": PROVIDER, "model": MODEL, "job_id": str(job_id),
                               "model_invoked": model_invoked,
                               "resolver": resolution_method}),
                    ),
                )
                saved_suggestion = cursor.fetchone()
                if saved_suggestion and assistant_category_is_assignable(category):
                    cursor.execute(
                        """UPDATE intake.classification_suggestions
                           SET review_status='accepted',reviewed_category=%s,
                               review_comment='Назначено ассистентом классификации',reviewed_at=now()
                           WHERE id=%s AND review_status='pending' RETURNING id""",
                        (category, saved_suggestion["id"]),
                    )
                    confirmed = cursor.fetchone()
                    if confirmed:
                        cursor.execute("SELECT id FROM geo.object_classes WHERE code=%s", (category,))
                        object_class = cursor.fetchone()
                        cursor.execute(
                            """UPDATE intake.cad_layers SET mapping_status='confirmed',
                                      candidate_class_id=%s,confidence=%s,
                                      properties=properties || %s WHERE id=%s""",
                            (object_class["id"] if object_class else None, confidence,
                             Jsonb({"reviewed_class_code": category,
                                    "resolution_method": resolution_method}),
                             layer["cad_layer_id"]),
                        )
                        cursor.execute(
                            """INSERT INTO intake.classification_reviews(
                                   suggestion_id,project_id,decision,axis_values,scope,comment)
                               VALUES (%s,%s,'accept',%s,'file',
                                       'Назначено ассистентом классификации с сохранением происхождения')""",
                            (saved_suggestion["id"], job["project_id"], Jsonb(axis_results)),
                        )
                        cursor.execute(
                            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,metadata)
                               VALUES ('assistant_assign_layer_category','intake',
                                       'classification_suggestions',%s,%s)""",
                            (saved_suggestion["id"], Jsonb({"category": category,
                              "confidence": confidence, "method": resolution_method})),
                        )
                completed += 1
                consecutive_failures = 0
                cursor.execute(
                    """UPDATE intake.semantic_suggestion_jobs SET completed_count=%s,failed_count=%s,
                              heartbeat_at=now() WHERE id=%s""",
                    (completed, failed, job_id),
                )
        except (DecisionProviderError, psycopg.Error) as exc:
            failed += 1
            consecutive_failures += 1
            errors.append(str(exc))
            if consecutive_failures >= 3:
                failed += len(layers) - completed - failed
                break

    state = "completed" if failed == 0 else "completed_with_warnings" if completed else "failed"
    error_summary = "; ".join(dict.fromkeys(errors))[:2000] or None
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE intake.semantic_suggestion_jobs SET state=%s,completed_count=%s,failed_count=%s,
                      error_summary=%s,heartbeat_at=now(),finished_at=now() WHERE id=%s""",
            (state, completed, failed, error_summary, job_id),
        )
        cursor.execute(
            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,metadata)
               VALUES ('semantic_suggestion_job','intake','semantic_suggestion_jobs',%s,%s)""",
            (job_id, Jsonb({"state": state, "completed": completed, "failed": failed, "provider": PROVIDER, "model": MODEL})),
        )
