from __future__ import annotations

import json
from functools import lru_cache
from pathlib import PurePosixPath
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from .models import (
    CoordinateSpace,
    Evidence,
    Feature,
    FidelityFinding,
    IntakeFile,
    IntakeProjectDetail,
    CadXrefDependency,
    IntakeProjectSummary,
    IntakeStage,
    MasterCandidate,
    PublicationRootCandidate,
    CadInventory,
    CadLayerView,
    CadSpaceView,
    ClassificationSuggestionView,
    AssistantRunView,
    AssistantTaskView,
    SemanticSuggestionJobView,
    ModelSummary,
    ObjectDetail,
    ProjectDetail,
    ProjectSummary,
    SceneLayer,
    SceneManifest,
    SurfaceRegionDetection,
    SceneRoot,
    SceneSource,
    SceneSpatialFocus,
    SourceNode,
    SourceReference,
    SourceTree,
)
from .repository import BBox, RepositoryUnavailable
from .semantic_jobs import JOB_VIEW_COLUMNS
from .publication_roots import root_candidates, workspace_kind


class PostgisRepository:
    def __init__(self, database_url: str, workspace_code: str = "lct2026-pilots") -> None:
        self.database_url = database_url
        self.workspace_code = workspace_code

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def ping(self) -> None:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except psycopg.Error as exc:
            raise RepositoryUnavailable("PostGIS is unavailable") from exc

    @staticmethod
    def _coordinate(row: dict) -> CoordinateSpace:
        return CoordinateSpace(
            id=row["coordinate_space_id"],
            kind=row["coordinate_kind"],
            srid=row["srid"],
            unit=row["linear_unit"],
            status=row["crs_status"],
        )

    @classmethod
    def _summary(cls, row: dict) -> ProjectSummary:
        return ProjectSummary(
            id=row["id"],
            code=row["code"],
            title=row["title"],
            status=row["status"],
            current_revision_id=row["revision_id"],
            current_model_id=row["model_id"],
            model_version=row["model_version"],
            assembly_status=row["assembly_status"],
            crs_status=row["crs_status"],
        )

    def _project_query(self) -> str:
        return """
            SELECT p.id, p.code, p.title, p.status,
                   pr.id AS revision_id, pr.revision_no,
                   cm.id AS model_id, cm.version_no AS model_version, cm.assembly_status,
                   cs.id AS coordinate_space_id, cs.kind AS coordinate_kind,
                   cs.srid, cs.linear_unit, cs.status AS crs_status,
                   cm.semantic_coverage, cm.dependency_completeness
            FROM catalog.projects p
            JOIN catalog.workspaces w ON w.id = p.workspace_id
            JOIN LATERAL (
                SELECT value.* FROM catalog.project_revisions value
                WHERE value.project_id = p.id ORDER BY value.revision_no DESC LIMIT 1
            ) pr ON true
            JOIN LATERAL (
                SELECT value.* FROM catalog.canonical_models value
                WHERE value.project_revision_id = pr.id ORDER BY value.version_no DESC LIMIT 1
            ) cm ON true
            JOIN catalog.coordinate_spaces cs ON cs.id = cm.coordinate_space_id
            WHERE w.code = %s AND p.deleted_at IS NULL
        """

    def list_projects(self) -> list[ProjectSummary]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self._project_query() + " ORDER BY p.code", (self.workspace_code,))
            return [self._summary(row) for row in cursor.fetchall()]

    @staticmethod
    def _intake_summary(row: dict) -> IntakeProjectSummary:
        return IntakeProjectSummary(
            id=row["id"], code=row["code"], title=row["title"],
            project_status=row["project_status"], revision_id=row["revision_id"],
            revision_no=row["revision_no"], intake_state=row["intake_state"],
            fidelity_verdict=row["fidelity_verdict"], delivery_id=row["delivery_id"],
            file_count=row["file_count"], total_bytes=row["total_bytes"],
            cad_count=row["cad_count"], finding_count=row["finding_count"],
            critical_count=row["critical_count"], current_model_id=row["current_model_id"],
            updated_at=row["updated_at"],
        )

    def _intake_query(self) -> str:
        return """
            SELECT p.id,p.code,p.title,p.status AS project_status,
                   pr.id AS revision_id,pr.revision_no,pw.state AS intake_state,
                   pw.fidelity_verdict,pw.delivery_id,pw.updated_at,
                   (SELECT count(*)::integer FROM intake.delivery_entries de WHERE de.delivery_id=pw.delivery_id) AS file_count,
                   (SELECT COALESCE(sum(de.size_bytes),0)::bigint FROM intake.delivery_entries de WHERE de.delivery_id=pw.delivery_id) AS total_bytes,
                   (SELECT count(*)::integer FROM intake.delivery_entries de WHERE de.delivery_id=pw.delivery_id AND de.media_kind IN ('dwg','dxf')) AS cad_count,
                   (SELECT count(*)::integer FROM intake.fidelity_findings ff WHERE ff.revision_id=pr.id) AS finding_count,
                   (SELECT count(*)::integer FROM intake.fidelity_findings ff WHERE ff.revision_id=pr.id AND ff.severity='critical' AND ff.status='open') AS critical_count,
                   (SELECT cm.id FROM catalog.canonical_models cm
                    WHERE cm.project_revision_id=pr.id ORDER BY cm.version_no DESC LIMIT 1) AS current_model_id
            FROM catalog.projects p
            JOIN catalog.workspaces w ON w.id=p.workspace_id
            JOIN LATERAL (
              SELECT value.* FROM catalog.project_revisions value
              WHERE value.project_id=p.id ORDER BY revision_no DESC LIMIT 1
            ) pr ON true
            JOIN intake.project_workflows pw ON pw.revision_id=pr.id
            WHERE w.code=%s AND p.deleted_at IS NULL
        """

    def list_intake_projects(self) -> list[IntakeProjectSummary]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                self._intake_query() + " ORDER BY pw.updated_at DESC",
                (self.workspace_code,),
            )
            return [self._intake_summary(row) for row in cursor.fetchall()]

    def get_intake_project(self, project_id: UUID) -> IntakeProjectDetail | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                self._intake_query() + " AND p.id=%s",
                (self.workspace_code, project_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            summary = self._intake_summary(row)
            cursor.execute("SELECT properties->>'description' AS description FROM catalog.projects WHERE id=%s", (project_id,))
            description = cursor.fetchone()["description"]
            cursor.execute(
                """SELECT sa.id,de.relative_path,sa.original_name,de.media_kind,sa.size_bytes,sa.sha256,
                          de.role,sa.properties->>'detected_format' AS detected_format,
                          sa.properties->>'format_version' AS format_version,
                          CASE WHEN sa.properties->>'source_modified_ms' ~ '^[0-9]+$'
                               THEN to_timestamp((sa.properties->>'source_modified_ms')::double precision / 1000.0) END AS source_modified_at,
                          sa.recorded_at AS uploaded_at
                   FROM intake.delivery_entries de JOIN provenance.source_assets sa ON sa.id=de.source_asset_id
                   WHERE de.delivery_id=%s ORDER BY de.relative_path""",
                (summary.delivery_id,),
            )
            files = [IntakeFile(**item) for item in cursor.fetchall()]
            cursor.execute(
                """SELECT id,source_asset_id,stage,attempt_no,state,progress::float8 AS progress,
                          metrics,left(stdout,12000) AS stdout,left(stderr,12000) AS stderr,
                          error_summary,created_at,started_at,finished_at
                   FROM intake.processing_stage_attempts WHERE revision_id=%s
                   ORDER BY created_at,id""",
                (summary.revision_id,),
            )
            stages = [IntakeStage(**item) for item in cursor.fetchall()]
            cursor.execute(
                """SELECT ff.id,ff.source_asset_id,ff.code,ff.severity,ff.stage,ff.title,ff.detail,
                          ff.evidence,ff.status,COALESCE((
                            SELECT jsonb_build_object('action',fr.action,'reason',fr.reason,
                              'impact',fr.impact,'created_at',fr.created_at)
                            FROM intake.finding_resolutions fr WHERE fr.finding_id=ff.id
                            ORDER BY fr.created_at DESC LIMIT 1
                          ),'{}'::jsonb) AS resolution
                   FROM intake.fidelity_findings ff WHERE ff.revision_id=%s ORDER BY
                     CASE ff.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,ff.created_at""",
                (summary.revision_id,),
            )
            findings = [FidelityFinding(**item) for item in cursor.fetchall()]
            cursor.execute(
                """SELECT mc.source_asset_id,de.relative_path,de.role AS delivery_role,mc.score::float8 AS score,
                          mc.role,mc.cues,mc.selected
                   FROM intake.master_candidates mc
                   JOIN intake.delivery_entries de ON de.source_asset_id=mc.source_asset_id
                   WHERE mc.revision_id=%s ORDER BY mc.score DESC,de.relative_path""",
                (summary.revision_id,),
            )
            candidate_rows = cursor.fetchall()
            candidates = [MasterCandidate(**{key: item[key] for key in ("source_asset_id", "relative_path", "score", "role", "cues", "selected")}) for item in candidate_rows]
            cursor.execute(
                """SELECT ci.id,ci.source_asset_id,de.relative_path,ci.stage,ci.format,
                          ci.format_version,ci.parse_status,ci.tool_name,ci.tool_version,
                          ci.metrics,ci.artifact_locator
                   FROM intake.cad_inventories ci
                   JOIN intake.delivery_entries de ON de.source_asset_id=ci.source_asset_id
                   WHERE ci.revision_id=%s ORDER BY de.relative_path,ci.created_at""",
                (summary.revision_id,),
            )
            inventories = [CadInventory(**item) for item in cursor.fetchall()]
            cursor.execute(
                """SELECT cs.id,ci.source_asset_id,de.relative_path AS source_relative_path,
                          ci.stage AS inventory_stage,cs.name,cs.space_kind,cs.entity_count
                   FROM intake.cad_spaces cs
                   JOIN intake.cad_inventories ci ON ci.id=cs.inventory_id
                   JOIN intake.delivery_entries de ON de.delivery_id=%s
                                                  AND de.source_asset_id=ci.source_asset_id
                   WHERE ci.revision_id=%s
                     AND ci.stage IN ('converted_dxf','uploaded_dxf')
                   ORDER BY de.relative_path,
                            CASE cs.space_kind WHEN 'model' THEN 0 ELSE 1 END,cs.name""",
                (summary.delivery_id, summary.revision_id),
            )
            spaces = [CadSpaceView(**item) for item in cursor.fetchall()]
            cursor.execute(
                """SELECT cl.id,cs.id AS suggestion_id,cd.source_asset_id,de.relative_path AS source_relative_path,
                          cl.name,cl.entity_count,cl.mapping_status,cl.confidence::float8 AS confidence,
                          COALESCE(cs.reviewed_category,cs.suggested_category) AS suggested_category,cs.method,
                          COALESCE(cs.input_snapshot->'entity_types','{}'::jsonb) AS entity_types,
                          cs.axis_results,cs.review_status
                   FROM intake.cad_layers cl
                   JOIN intake.cad_documents cd ON cd.id=cl.cad_document_id
                   JOIN intake.delivery_entries de ON de.delivery_id=%s
                                                  AND de.source_asset_id=cd.source_asset_id
                   JOIN LATERAL (
                     SELECT candidate.* FROM intake.classification_suggestions candidate
                     WHERE candidate.cad_layer_id=cl.id AND candidate.revision_id=%s
                       AND candidate.review_status<>'superseded'
                     ORDER BY CASE WHEN candidate.method='laya-layer-jev-v1' THEN 0 ELSE 1 END,
                              candidate.created_at DESC
                     LIMIT 1
                   ) cs ON true
                   ORDER BY de.relative_path,cl.entity_count DESC,cl.name""",
                (summary.delivery_id, summary.revision_id),
            )
            layers = [CadLayerView(**item) for item in cursor.fetchall()]
            cursor.execute(
                """SELECT cs.id,cs.target_kind,cs.target_key,cs.source_asset_id,
                          COALESCE(cl.name,de.relative_path,cs.target_key) AS target_label,
                          cs.suggested_category,cs.confidence::float8 AS confidence,
                          cs.method,cs.cues,cs.alternatives,cs.review_status,
                          cs.taxonomy_version,cs.axis_results
                   FROM intake.classification_suggestions cs
                   LEFT JOIN intake.cad_layers cl ON cl.id=cs.cad_layer_id
                   LEFT JOIN intake.delivery_entries de ON de.delivery_id=%s
                                                        AND de.source_asset_id=cs.source_asset_id
                   WHERE cs.revision_id=%s
                   ORDER BY CASE cs.target_kind WHEN 'file' THEN 0 ELSE 1 END,
                            target_label,cs.created_at""",
                (summary.delivery_id, summary.revision_id),
            )
            suggestions = [ClassificationSuggestionView(**item) for item in cursor.fetchall()]
            cursor.execute(
                """SELECT cx.id,cd.source_asset_id,de.relative_path AS source_relative_path,
                          cx.referenced_asset_id,target.relative_path AS target_relative_path,
                          cx.reference_name,cx.original_path,cx.resolved_status AS status,cx.properties
                   FROM intake.cad_xrefs cx
                   JOIN intake.cad_documents cd ON cd.id=cx.cad_document_id
                   JOIN intake.delivery_entries de ON de.delivery_id=%s
                                                  AND de.source_asset_id=cd.source_asset_id
                   LEFT JOIN intake.delivery_entries target ON target.delivery_id=%s
                                                        AND target.source_asset_id=cx.referenced_asset_id
                   ORDER BY de.relative_path,cx.reference_name,cx.original_path""",
                (summary.delivery_id, summary.delivery_id),
            )
            xrefs = []
            for item in cursor.fetchall():
                properties = item.pop("properties") or {}
                xrefs.append(CadXrefDependency(
                    **item,
                    overlay=bool(properties.get("overlay", False)),
                    placement_count=len(properties.get("placements") or []),
                    matches=[str(value) for value in properties.get("matches") or []],
                ))
            cursor.execute(
                """SELECT source_asset_id,root_role FROM intake.publication_roots
                   WHERE revision_id=%s ORDER BY position,selected_at""",
                (summary.revision_id,),
            )
            selected_roots = {str(item["source_asset_id"]): item["root_role"] for item in cursor.fetchall()}
            path_by_id = {str(item["source_asset_id"]): item["relative_path"] for item in candidate_rows}
            root_rows = root_candidates(candidate_rows, [item.model_dump() for item in xrefs])
            publication_roots = []
            for item in root_rows:
                closure_ids = [str(item["source_asset_id"]), *[str(value) for value in item["dependency_asset_ids"]]]
                closure = set(closure_ids)
                critical_count = sum(
                    1 for finding in findings
                    if finding.severity == "critical" and finding.status == "open"
                    and (finding.source_asset_id is None or str(finding.source_asset_id) in closure)
                )
                source_id = str(item["source_asset_id"])
                publication_roots.append(PublicationRootCandidate(
                    source_asset_id=item["source_asset_id"], relative_path=str(item["relative_path"]),
                    workspace_kind=str(item["workspace_kind"]), default_role=str(item["default_role"]),
                    score=float(item.get("score") or 0), cues=list(item.get("cues") or []),
                    selected=source_id in selected_roots, selected_role=selected_roots.get(source_id),
                    dependency_asset_ids=item["dependency_asset_ids"],
                    dependency_paths=[path_by_id[value] for value in item["dependency_asset_ids"] if value in path_by_id],
                    dependency_count=int(item["dependency_count"]), unresolved_count=int(item["unresolved_count"]),
                    critical_count=critical_count, closure_fingerprint=str(item["closure_fingerprint"]),
                ))

            cursor.execute(
                """SELECT id,revision_id,input_fingerprint,schema_version,taxonomy_version,
                          provider_version,state,progress::float8 AS progress,summary,error_summary,
                          started_at,heartbeat_at,finished_at,created_at
                   FROM intake.assistant_runs WHERE revision_id=%s
                   ORDER BY created_at DESC LIMIT 10""",
                (summary.revision_id,),
            )
            runs = []
            for run_row in cursor.fetchall():
                cursor.execute(
                    """SELECT id,task_key,title,position,state,dependencies,attempts,
                              progress::float8 AS progress,error_summary,started_at,heartbeat_at,finished_at
                       FROM intake.assistant_tasks WHERE run_id=%s ORDER BY position""",
                    (run_row["id"],),
                )
                runs.append(AssistantRunView(**run_row, tasks=[AssistantTaskView(**task) for task in cursor.fetchall()]))
            cursor.execute(
                f"""SELECT {JOB_VIEW_COLUMNS}
                   FROM intake.semantic_suggestion_jobs WHERE revision_id=%s
                   ORDER BY created_at DESC LIMIT 20""",
                (summary.revision_id,),
            )
            semantic_jobs = [SemanticSuggestionJobView(**row) for row in cursor.fetchall()]
            return IntakeProjectDetail(
                **summary.model_dump(), description=description, files=files, stages=stages,
                findings=findings, master_candidates=candidates, publication_roots=publication_roots, inventories=inventories,
                cad_spaces=spaces, cad_layers=layers,
                classification_suggestions=suggestions, assistant_runs=runs,
                xref_dependencies=xrefs, semantic_suggestion_jobs=semantic_jobs,
            )

    def get_assistant_run(self, run_id: UUID) -> AssistantRunView | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT id,revision_id,input_fingerprint,schema_version,taxonomy_version,
                          provider_version,state,progress::float8 AS progress,summary,error_summary,
                          started_at,heartbeat_at,finished_at,created_at
                   FROM intake.assistant_runs WHERE id=%s""",
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                """SELECT id,task_key,title,position,state,dependencies,attempts,
                          progress::float8 AS progress,error_summary,started_at,heartbeat_at,finished_at
                   FROM intake.assistant_tasks WHERE run_id=%s ORDER BY position""",
                (run_id,),
            )
            return AssistantRunView(**row, tasks=[AssistantTaskView(**task) for task in cursor.fetchall()])

    def get_project(self, project_id: UUID) -> ProjectDetail | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(self._project_query() + " AND p.id = %s", (self.workspace_code, project_id))
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                """SELECT issue_kind, count(*) AS count
                   FROM api.input_quality_issues WHERE model_id = %s GROUP BY issue_kind""",
                (row["model_id"],),
            )
            quality = {item["issue_kind"]: item["count"] for item in cursor.fetchall()}
            quality.update(
                semantic_coverage=float(row["semantic_coverage"] or 0),
                dependency_completeness=float(row["dependency_completeness"] or 0),
            )
            return ProjectDetail(
                **self._summary(row).model_dump(),
                revision_no=row["revision_no"],
                coordinate_space=self._coordinate(row),
                quality=quality,
            )

    def list_models(self, project_id: UUID) -> list[ModelSummary] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT 1 FROM catalog.projects p JOIN catalog.workspaces w ON w.id=p.workspace_id
                   WHERE p.id=%s AND w.code=%s AND p.deleted_at IS NULL""",
                (project_id, self.workspace_code),
            )
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                """SELECT cm.id, cm.project_revision_id, cm.version_no, cm.model_kind,
                          cm.assembly_status, cs.id AS coordinate_space_id,
                          cs.kind AS coordinate_kind, cs.srid, cs.linear_unit,
                          cs.status AS crs_status
                   FROM catalog.canonical_models cm
                   JOIN catalog.project_revisions pr ON pr.id=cm.project_revision_id
                   JOIN catalog.coordinate_spaces cs ON cs.id=cm.coordinate_space_id
                   WHERE pr.project_id=%s ORDER BY pr.revision_no, cm.version_no""",
                (project_id,),
            )
            return [
                ModelSummary(
                    id=row["id"],
                    project_revision_id=row["project_revision_id"],
                    version=row["version_no"],
                    kind=row["model_kind"],
                    assembly_status=row["assembly_status"],
                    coordinate_space=self._coordinate(row),
                )
                for row in cursor.fetchall()
            ]

    def _model_row(self, cursor, model_id: UUID) -> dict | None:
        cursor.execute(
            """SELECT cm.id, cm.project_revision_id, cm.version_no, cm.assembly_status,
                      cm.properties, cs.id AS coordinate_space_id,
                      cs.kind AS coordinate_kind, cs.srid, cs.linear_unit,
                      cs.status AS crs_status
               FROM catalog.canonical_models cm
               JOIN catalog.coordinate_spaces cs ON cs.id=cm.coordinate_space_id
               WHERE cm.id=%s""",
            (model_id,),
        )
        return cursor.fetchone()

    @lru_cache(maxsize=128)
    def _root_feature_counts(self, model_id: UUID) -> dict[str | None, int]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT properties->>'publication_root_id' AS root_id, count(*) AS total
                   FROM geo.spatial_objects WHERE model_id=%s
                   GROUP BY properties->>'publication_root_id'""",
                (model_id,),
            )
            return {row["root_id"]: row["total"] for row in cursor.fetchall()}

    @lru_cache(maxsize=128)
    def get_manifest(self, model_id: UUID, root_id: UUID | None = None) -> SceneManifest | None:
        with self._connect() as connection, connection.cursor() as cursor:
            model = self._model_row(cursor, model_id)
            if model is None:
                return None
            root_entries = list((model.get("properties") or {}).get("roots") or [])
            selected = root_id or next(
                (UUID(item["source_asset_id"]) for item in root_entries if item.get("role") == "effective_design"),
                UUID(root_entries[0]["source_asset_id"]) if root_entries else None,
            )
            if root_id is not None and not any(str(root_id) == item.get("source_asset_id") for item in root_entries):
                return None
            root_clause = " AND so.properties->>'publication_root_id'=%s" if selected else ""
            root_params = (str(selected),) if selected else ()
            cursor.execute(
                f"""SELECT ST_XMin(bounds)::float8 AS min_x, ST_YMin(bounds)::float8 AS min_y,
                          ST_XMax(bounds)::float8 AS max_x, ST_YMax(bounds)::float8 AS max_y
                   FROM (SELECT ST_Extent(og.geom) AS bounds
                         FROM geo.object_geometries og
                         JOIN geo.spatial_objects so ON so.id=og.object_id
                         WHERE so.model_id=%s AND og.is_primary {root_clause}) value""",
                (model_id, *root_params),
            )
            extent_row = cursor.fetchone()
            if not extent_row or extent_row["min_x"] is None:
                extent = (0.0, 0.0, 1.0, 1.0)
            else:
                extent = tuple(float(extent_row[key]) for key in ("min_x", "min_y", "max_x", "max_y"))
            cursor.execute(
                """SELECT ST_XMin(focus_extent)::float8 AS min_x,
                          ST_YMin(focus_extent)::float8 AS min_y,
                          ST_XMax(focus_extent)::float8 AS max_x,
                          ST_YMax(focus_extent)::float8 AS max_y,
                          ST_X(focus_center)::float8 AS center_x,
                          ST_Y(focus_center)::float8 AS center_y,
                          method, algorithm_version, object_count,
                          total_object_count, coverage::float8 AS coverage
                   FROM geo.model_spatial_focus WHERE model_id=%s""",
                (model_id,),
            )
            focus_row = cursor.fetchone()
            spatial_focus = None if focus_row is None else SceneSpatialFocus(
                extent=tuple(float(focus_row[key]) for key in ("min_x", "min_y", "max_x", "max_y")),
                center=(float(focus_row["center_x"]), float(focus_row["center_y"])),
                method=focus_row["method"],
                algorithm_version=focus_row["algorithm_version"],
                object_count=focus_row["object_count"],
                total_object_count=focus_row["total_object_count"],
                coverage=focus_row["coverage"],
            )
            cursor.execute(
                f"""SELECT so.properties->>'layer_id' AS layer_id,
                          max(so.properties->>'source_layer') AS title,
                          array_agg(DISTINCT oc.code ORDER BY oc.code) AS class_codes,
                          array_agg(DISTINCT og.role ORDER BY og.role) AS geometry_roles,
                          count(*) AS feature_count
                   FROM geo.spatial_objects so
                   JOIN geo.object_classes oc ON oc.id=so.class_id
                   JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
                   WHERE so.model_id=%s {root_clause}
                   GROUP BY so.properties->>'layer_id'
                   ORDER BY max(so.properties->>'source_layer')""",
                (model_id, *root_params),
            )
            layers = [
                SceneLayer(
                    id=row["layer_id"],
                    title=row["title"] or row["layer_id"],
                    class_codes=row["class_codes"],
                    geometry_roles=row["geometry_roles"],
                    feature_count=row["feature_count"],
                    source_asset_id=selected if selected and "$0$" not in (row["title"] or "") else None,
                    source_path=next((item.get("relative_path") for item in root_entries if item.get("source_asset_id") == str(selected)), None) if "$0$" not in (row["title"] or "") else None,
                    source_layer_name=(row["title"] or row["layer_id"]).split("$0$")[-1],
                    origin_kind="xref" if "$0$" in (row["title"] or "") else "root" if selected else "unknown",
                    class_code=row["class_codes"][0] if len(row["class_codes"]) == 1 else None,
                )
                for row in cursor.fetchall()
            ]
            cursor.execute(
                f"""SELECT count(*) AS total,
                          count(*) FILTER (WHERE semantic_status='needs_review') AS needs_review
                   FROM geo.spatial_objects so WHERE model_id=%s {root_clause}""",
                (model_id, *root_params),
            )
            counts = cursor.fetchone()
            cursor.execute(
                f"""SELECT count(DISTINCT object_id) AS conflicts
                   FROM provenance.object_evidence oe
                   JOIN geo.spatial_objects so ON so.id=oe.object_id
                   WHERE so.model_id=%s AND oe.decision='conflict' {root_clause}""",
                (model_id, *root_params),
            )
            conflicts = cursor.fetchone()["conflicts"]
            counts_by_root = self._root_feature_counts(model_id)
            roots = [SceneRoot(
                id=UUID(item["source_asset_id"]), path=item["relative_path"],
                title=PurePosixPath(item["relative_path"].replace("\\", "/")).name,
                role=item.get("role", "reference_context"),
                workspace_kind=workspace_kind(item["relative_path"]) or "other",
                feature_count=counts_by_root.get(item["source_asset_id"], 0),
            ) for item in root_entries]
            active_entry = next((item for item in root_entries if item.get("source_asset_id") == str(selected)), None)
            sources = []
            if active_entry:
                sources.append(SceneSource(
                    asset_id=selected, path=active_entry["relative_path"],
                    title=PurePosixPath(active_entry["relative_path"].replace("\\", "/")).name,
                    relation="root", provenance_status="exact",
                ))
                sources.extend(SceneSource(
                    path=dependency.get("original_path") or dependency.get("child") or dependency.get("block", "XREF"),
                    title=PurePosixPath((dependency.get("original_path") or dependency.get("child") or dependency.get("block", "XREF")).replace("\\", "/")).name,
                    relation="xref", parent_path=dependency.get("parent"),
                    block_name=dependency.get("block"), original_path=dependency.get("original_path"),
                    provenance_status="inferred",
                ) for dependency in active_entry.get("dependencies", []))
            return SceneManifest(
                model_id=model_id,
                model_version=model["version_no"],
                coordinate_space=self._coordinate(model),
                extent=extent,
                spatial_focus=spatial_focus,
                layers=layers,
                issues={"needs_review": counts["needs_review"], "conflict": conflicts},
                feature_count=counts["total"],
                roots=roots, active_root_id=selected, sources=sources,
            )

    def get_features(
        self, model_id: UUID, bbox: BBox, layers: set[str] | None, lod: int,
        limit: int | None = None, offset: int = 0, root_id: UUID | None = None,
    ) -> list[Feature] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            model = self._model_row(cursor, model_id)
            if model is None:
                return None
            assembly_layer_clause = ""
            canonical_layer_clause = ""
            assembly_root_clause = ""
            canonical_root_clause = ""
            tolerance = (0.0, 0.08, 0.25, 0.75)[lod]
            assembly_geometry_column = ("geom", "geom_lod1", "geom_lod2", "geom_lod3")[lod]
            if root_id:
                assembly_root_clause = "AND representative.properties->>\'publication_root_id\'=%s"
                canonical_root_clause = "AND so.properties->>\'publication_root_id\'=%s"
            query_params: list[object] = [model_id, *bbox]
            if root_id:
                query_params.append(str(root_id))
            if layers:
                assembly_layer_clause = "AND ra.layer_id = ANY(%s)"
                query_params.append(list(layers))
            query_params.extend([tolerance, tolerance * 0.25, tolerance, model_id, *bbox])
            if root_id:
                query_params.append(str(root_id))
            if layers:
                canonical_layer_clause = "AND so.properties->>\'layer_id\' = ANY(%s)"
                query_params.append(list(layers))
            query_params.extend([limit or (12000 if lod <= 1 else 6000), offset])
            cursor.execute(
                f"""WITH rendered AS (
                      SELECT ra.id, representative.stable_key, oc.code AS class_code,
                             ra.layer_id, representative.name, representative.lifecycle,
                             representative.semantic_status,
                             representative.confidence::float8 AS confidence,
                             ra.geometry_role,
                             ST_AsGeoJSON(ra.{assembly_geometry_column})::jsonb AS geometry,
                             representative.properties || ra.properties AS properties
                      FROM geo.render_assemblies ra
                      JOIN geo.spatial_objects representative ON representative.id=ra.id
                      JOIN geo.object_classes oc ON oc.id=ra.class_id
                      WHERE ra.model_id=%s
                        AND ra.geom && ST_MakeEnvelope(%s,%s,%s,%s,0)
                        {assembly_root_clause}
                        {assembly_layer_clause}

                      UNION ALL

                      SELECT so.id, so.stable_key, oc.code AS class_code,
                             so.properties->>'layer_id' AS layer_id, so.name,
                             so.lifecycle, so.semantic_status, so.confidence::float8 AS confidence,
                             og.role AS geometry_role,
                             ST_AsGeoJSON(CASE WHEN %s > 0 THEN ST_SimplifyPreserveTopology(
                               og.geom, CASE WHEN og.role='crown' THEN %s ELSE %s END
                             ) ELSE og.geom END)::jsonb AS geometry,
                             so.properties
                      FROM geo.spatial_objects so
                      JOIN geo.object_classes oc ON oc.id=so.class_id
                      JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
                      LEFT JOIN geo.render_assembly_members ram ON ram.object_id=so.id
                      WHERE so.model_id=%s
                        AND ram.object_id IS NULL
                        AND og.geom && ST_MakeEnvelope(%s,%s,%s,%s,0)
                        {canonical_root_clause}
                        {canonical_layer_clause}
                    )
                    SELECT * FROM rendered
                    ORDER BY stable_key, id
                    LIMIT %s OFFSET %s""",
                query_params,
            )
            rows = cursor.fetchall()
            return [
                Feature(
                    id=row["id"],
                    stable_key=row["stable_key"],
                    class_code=row["class_code"],
                    layer_id=row["layer_id"],
                    name=row["name"],
                    lifecycle=row["lifecycle"],
                    semantic_status=row["semantic_status"],
                    confidence=row["confidence"],
                    geometry_role=row["geometry_role"],
                    geometry=row["geometry"] if isinstance(row["geometry"], dict) else json.loads(row["geometry"]),
                    properties=row["properties"],
                )
                for row in rows
            ]

    def detect_surface_region(
        self, model_id: UUID, root_id: UUID | None, x: float, y: float,
    ) -> SurfaceRegionDetection | None:
        with self._connect() as connection, connection.cursor() as cursor:
            model = self._model_row(cursor, model_id)
            if model is None:
                return None
            root_clause = "AND so.properties->>'publication_root_id'=%s" if root_id else ""
            params: list[object] = [x, y, model_id]
            if root_id:
                params.append(str(root_id))
            params.append(model_id)
            if root_id:
                params.append(str(root_id))
            cursor.execute(
                f"""
                WITH seed AS (
                  SELECT ST_SetSRID(ST_MakePoint(%s,%s),0) AS geom
                ), explicit AS (
                  SELECT og.geom, 0 AS priority, 'explicit_surface_polygon'::text AS source
                  FROM geo.spatial_objects so
                  JOIN geo.object_classes oc ON oc.id=so.class_id
                  JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
                  CROSS JOIN seed
                  WHERE so.model_id=%s {root_clause}
                    AND og.geom && ST_Expand(seed.geom,150)
                    AND oc.code IN ('vegetation.grass','surface.lawn')
                    AND GeometryType(og.geom) IN ('POLYGON','MULTIPOLYGON')
                    AND ST_Covers(og.geom,seed.geom)
                ), edge_source AS (
                  SELECT so.id,oc.code,
                    CASE WHEN GeometryType(og.geom) IN ('POLYGON','MULTIPOLYGON')
                      THEN ST_Boundary(og.geom) ELSE ST_CollectionExtract(og.geom,2) END AS geom
                  FROM geo.spatial_objects so
                  JOIN geo.object_classes oc ON oc.id=so.class_id
                  JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
                  CROSS JOIN seed
                  WHERE so.model_id=%s {root_clause}
                    AND og.geom && ST_Expand(seed.geom,150)
                    AND (
                      oc.code LIKE 'transport.%%' OR oc.code LIKE 'surface.%%'
                      OR oc.code LIKE 'structure.%%' OR oc.code='territory.work_boundary'
                      OR oc.code IN ('terrain.slope_toe','terrain.retaining_wall')
                    )
                    AND oc.code NOT LIKE 'utility.%%'
                    AND NOT ST_IsEmpty(og.geom)
                ), noded AS (
                  SELECT ST_Node(ST_UnaryUnion(ST_Collect(geom))) AS geom FROM edge_source
                  WHERE NOT ST_IsEmpty(geom)
                ), reconstructed AS (
                  SELECT polygon.geom,1 AS priority,'polygonized_surface_linework'::text AS source
                  FROM noded CROSS JOIN LATERAL ST_Dump(ST_Polygonize(ARRAY[noded.geom])) polygon
                  CROSS JOIN seed
                  WHERE ST_Covers(polygon.geom,seed.geom)
                ), candidates AS (
                  SELECT * FROM explicit UNION ALL SELECT * FROM reconstructed
                ), selected AS (
                  SELECT geom,priority,source FROM candidates
                  WHERE ST_Area(geom)>0.25 ORDER BY priority,ST_Area(geom) LIMIT 1
                )
                SELECT ST_AsGeoJSON(selected.geom)::jsonb AS geometry,
                       ST_Area(selected.geom)::float8 AS area,selected.source,
                       (SELECT count(*)::integer FROM edge_source e WHERE ST_Intersects(e.geom,ST_Boundary(selected.geom))) AS edge_count,
                       (SELECT COALESCE(array_agg(DISTINCT e.code ORDER BY e.code),ARRAY[]::text[])
                        FROM edge_source e WHERE ST_Intersects(e.geom,ST_Boundary(selected.geom))) AS classes
                FROM selected
                """,
                params,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return SurfaceRegionDetection(
                model_id=model_id, root_id=root_id, seed=(x, y),
                geometry=row["geometry"] if isinstance(row["geometry"], dict) else json.loads(row["geometry"]),
                area=row["area"], confidence=0.96 if row["source"] == "explicit_surface_polygon" else 0.72,
                edge_count=row["edge_count"], source=row["source"], contributing_classes=row["classes"],
            )

    def get_object(self, object_id: UUID) -> ObjectDetail | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT so.id, so.model_id, so.stable_key, oc.code AS class_code,
                          so.properties->>'layer_id' AS layer_id, so.name, so.lifecycle,
                          so.semantic_status, so.confidence::float8 AS confidence,
                          og.role AS geometry_role, ST_AsGeoJSON(og.geom)::jsonb AS geometry,
                          so.properties || COALESCE(ra.properties, '{}'::jsonb) AS properties,
                          sa.id AS asset_id, sf.id AS fragment_id,
                          sa.storage_locator AS path, sf.locator->>'layer' AS source_layer,
                          sf.locator->>'handle' AS source_handle, oe.transform_id
                   FROM geo.spatial_objects so
                   JOIN geo.object_classes oc ON oc.id=so.class_id
                   JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
                   LEFT JOIN geo.render_assemblies ra ON ra.id=so.id
                   LEFT JOIN LATERAL (
                       SELECT value.* FROM provenance.object_evidence value
                       WHERE value.object_id=so.id AND value.source_fragment_id IS NOT NULL
                       ORDER BY value.created_at LIMIT 1
                   ) oe ON true
                   LEFT JOIN provenance.source_fragments sf ON sf.id=oe.source_fragment_id
                   LEFT JOIN provenance.source_assets sa ON sa.id=sf.source_asset_id
                   WHERE so.id=%s""",
                (object_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return ObjectDetail(
                id=row["id"], model_id=row["model_id"], stable_key=row["stable_key"],
                class_code=row["class_code"], layer_id=row["layer_id"], name=row["name"],
                lifecycle=row["lifecycle"], semantic_status=row["semantic_status"],
                confidence=row["confidence"], geometry_role=row["geometry_role"],
                geometry=row["geometry"], properties=row["properties"],
                source=SourceReference(
                    asset_id=row["asset_id"], fragment_id=row["fragment_id"],
                    path=row["path"], layer=row["source_layer"], handle=row["source_handle"],
                    transform_id=row["transform_id"],
                ),
            )

    def get_evidence(self, object_id: UUID) -> list[Evidence] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM geo.spatial_objects WHERE id=%s", (object_id,))
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                """SELECT id, evidence_role AS role, attribute_name, asserted_value,
                          method, confidence::float8 AS confidence, decision,
                          source_fragment_id, external_feature_id, transform_id
                   FROM provenance.object_evidence WHERE object_id=%s ORDER BY created_at, id""",
                (object_id,),
            )
            return [Evidence(**row) for row in cursor.fetchall()]

    def get_source_tree(self, revision_id: UUID) -> SourceTree | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM catalog.project_revisions WHERE id=%s", (revision_id,))
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                """SELECT id, parent_asset_id AS parent_id, asset_kind AS kind,
                          original_name AS title, storage_locator AS display_path,
                          media_type, availability_status
                   FROM provenance.source_assets WHERE project_revision_id=%s
                   ORDER BY storage_locator""",
                (revision_id,),
            )
            return SourceTree(revision_id=revision_id, nodes=[SourceNode(**row) for row in cursor.fetchall()])
