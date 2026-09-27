import math
import os
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import anyio
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__
from .fixtures import fixture_repository
from .models import (
    EvidenceList,
    FeatureCollection,
    IntakeActionResult,
    IntakeProjectCreate,
    IntakeProjectDetail,
    IntakeProjectList,
    IntakeReviewRequest,
    ClassificationReviewRequest,
    AssistantRunView,
    IntakeUploadResult,
    ModelList,
    ObjectDetail,
    ProjectDetail,
    ProjectList,
    SceneManifest,
    SourceTree,
)
from .repository import BBox, Repository, RepositoryUnavailable
from .intake_service import (
    IntakeConflict,
    analyze_revision,
    create_project as create_intake_project,
    detect_cad_format,
    normalize_relative_path,
    publish_revision,
    refresh_workflow,
    register_upload,
    review_revision,
    review_classification,
    soft_delete_project,
    store_stream,
)
from .assistant import create_or_resume_run, execute_run, reconcile_project_runs


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(request: Request, status_code: int, code: str, message: str, details=None):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "correlation_id": request.state.correlation_id,
            }
        },
        headers={"X-Correlation-ID": request.state.correlation_id},
    )


def parse_bbox(raw: str) -> BBox:
    try:
        values = tuple(float(value.strip()) for value in raw.split(","))
    except ValueError as exc:
        raise ApiError(422, "invalid_bbox", "bbox must contain four numbers") from exc
    if len(values) != 4 or not all(math.isfinite(value) for value in values):
        raise ApiError(422, "invalid_bbox", "bbox must contain four finite numbers")
    min_x, min_y, max_x, max_y = values
    if min_x >= max_x or min_y >= max_y:
        raise ApiError(422, "invalid_bbox", "bbox minimums must be less than maximums")
    return min_x, min_y, max_x, max_y


def default_repository() -> Repository:
    mode = os.getenv("GREENPLAN_DATA_MODE", "fixture")
    if mode == "fixture":
        return fixture_repository()
    if mode == "postgis":
        database_url = os.getenv("GREENPLAN_DATABASE_URL")
        if not database_url:
            raise RuntimeError("GREENPLAN_DATABASE_URL is required in postgis mode")
        from .postgis_repository import PostgisRepository

        return PostgisRepository(database_url)
    raise RuntimeError(f"unsupported GREENPLAN_DATA_MODE={mode!r}")


def create_app(repository: Repository | None = None) -> FastAPI:
    app = FastAPI(
        title="GreenPlan Domain API",
        version=__version__,
    )
    app.state.repository = repository or default_repository()

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        request.state.correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return error_response(
            request,
            422,
            "validation_error",
            "request validation failed",
            exc.errors(),
        )

    def get_repository(request: Request) -> Repository:
        return request.app.state.repository

    Repo = Annotated[Repository, Depends(get_repository)]

    def intake_settings(repo: Repo):
        database_url = getattr(repo, "database_url", None)
        workspace_code = getattr(repo, "workspace_code", "lct2026-pilots")
        if not database_url:
            raise ApiError(501, "intake_unavailable", "project intake requires the PostGIS repository")
        root = Path(os.getenv("GREENPLAN_INTAKE_ROOT", "/intake"))
        return database_url, workspace_code, root

    @app.get("/health/live", tags=["health"])
    def liveness():
        return {"status": "ok", "service": "greenplan-api", "version": __version__}

    @app.get("/health/ready", tags=["health"])
    def readiness(repo: Repo):
        try:
            repo.ping()
        except RepositoryUnavailable as exc:
            raise ApiError(503, "repository_unavailable", str(exc)) from exc
        return {"status": "ready"}

    @app.get("/v1/projects", response_model=ProjectList, tags=["projects"])
    def list_projects(repo: Repo):
        return ProjectList(items=repo.list_projects())

    @app.get("/v1/intake/projects", response_model=IntakeProjectList, tags=["intake"])
    def list_intake_projects(repo: Repo):
        intake_settings(repo)
        return IntakeProjectList(items=repo.list_intake_projects())

    @app.post("/v1/intake/projects", response_model=IntakeProjectDetail, status_code=201, tags=["intake"])
    def create_project(payload: IntakeProjectCreate, repo: Repo):
        database_url, workspace_code, root = intake_settings(repo)
        try:
            project_id = create_intake_project(
                database_url, workspace_code, payload.code, payload.title, payload.description,
            )
        except IntakeConflict as exc:
            raise ApiError(409, "project_code_conflict", str(exc)) from exc
        refresh_workflow(database_url, root, project_id)
        return repo.get_intake_project(project_id)

    @app.get("/v1/intake/projects/{project_id}", response_model=IntakeProjectDetail, tags=["intake"])
    def get_intake_project(project_id: UUID, repo: Repo):
        database_url, _workspace_code, root = intake_settings(repo)
        if repo.get_intake_project(project_id) is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        refresh_workflow(database_url, root, project_id)
        reconcile_project_runs(database_url, project_id)
        project = repo.get_intake_project(project_id)
        if project is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        return project

    @app.delete("/v1/intake/projects/{project_id}", status_code=204, tags=["intake"])
    def delete_intake_project(project_id: UUID, repo: Repo):
        database_url, workspace_code, _root = intake_settings(repo)
        try:
            soft_delete_project(database_url, workspace_code, project_id)
        except KeyError as exc:
            raise ApiError(404, "project_not_found", "intake project does not exist") from exc
        return Response(status_code=204)

    @app.post(
        "/v1/intake/projects/{project_id}/files",
        response_model=IntakeUploadResult,
        status_code=201,
        tags=["intake"],
    )
    async def upload_intake_file(
        project_id: UUID,
        repo: Repo,
        relative_path: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
    ):
        database_url, _workspace_code, root = intake_settings(repo)
        if repo.get_intake_project(project_id) is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        try:
            safe_path = normalize_relative_path(relative_path)
        except ValueError as exc:
            raise ApiError(422, "unsafe_relative_path", str(exc)) from exc
        await file.seek(0)
        checksum, size, locator, deduplicated, header = await anyio.to_thread.run_sync(
            store_stream, root, file.file,
        )
        detected_format, format_version = detect_cad_format(header)
        try:
            asset_id = register_upload(
                database_url, project_id, safe_path, checksum, size, locator,
                detected_format, format_version, deduplicated,
            )
        except KeyError as exc:
            raise ApiError(404, "project_not_found", "intake project does not exist") from exc
        except IntakeConflict as exc:
            raise ApiError(409, "file_path_conflict", str(exc)) from exc
        return IntakeUploadResult(
            asset_id=asset_id, relative_path=safe_path, sha256=checksum,
            size_bytes=size, detected_format=detected_format, deduplicated=deduplicated,
        )

    @app.post("/v1/intake/projects/{project_id}/analyze", response_model=IntakeActionResult, status_code=202, tags=["intake"])
    def analyze_intake_project(project_id: UUID, background: BackgroundTasks, repo: Repo):
        database_url, _workspace_code, root = intake_settings(repo)
        project = repo.get_intake_project(project_id)
        if project is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        if not project.files:
            raise ApiError(409, "empty_delivery", "upload at least one file before analysis")
        background.add_task(
            analyze_revision, database_url, root, project_id, os.getenv("CELERY_BROKER_URL"),
        )
        return IntakeActionResult(
            revision_id=project.revision_id, state="analyzing",
            fidelity_verdict=project.fidelity_verdict, message="analysis queued",
        )

    @app.post(
        "/v1/intake/projects/{project_id}/assistant-runs",
        response_model=AssistantRunView,
        status_code=202,
        tags=["intake"],
    )
    def start_intake_assistant(project_id: UUID, background: BackgroundTasks, repo: Repo):
        database_url, _workspace_code, root = intake_settings(repo)
        project = repo.get_intake_project(project_id)
        if project is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        try:
            run_id, created = create_or_resume_run(database_url, project_id)
        except ValueError as exc:
            raise ApiError(409, "empty_delivery", str(exc)) from exc
        run = repo.get_assistant_run(run_id)
        if run is None:
            raise ApiError(500, "assistant_run_missing", "assistant run was not persisted")
        if created or run.state in {"queued", "running", "failed"}:
            background.add_task(
                execute_run, database_url, root, project_id, run_id, os.getenv("CELERY_BROKER_URL"),
            )
        return run

    @app.get(
        "/v1/intake/projects/{project_id}/assistant-runs/{run_id}",
        response_model=AssistantRunView,
        tags=["intake"],
    )
    def get_intake_assistant_run(project_id: UUID, run_id: UUID, repo: Repo):
        database_url, _workspace_code, root = intake_settings(repo)
        if repo.get_intake_project(project_id) is None:
            raise ApiError(404, "assistant_run_not_found", "assistant run does not exist")
        refresh_workflow(database_url, root, project_id)
        reconcile_project_runs(database_url, project_id)
        project = repo.get_intake_project(project_id)
        run = repo.get_assistant_run(run_id)
        if project is None or run is None or run.revision_id != project.revision_id:
            raise ApiError(404, "assistant_run_not_found", "assistant run does not exist")
        return run

    @app.post("/v1/intake/projects/{project_id}/review", response_model=IntakeActionResult, tags=["intake"])
    def review_intake_project(project_id: UUID, payload: IntakeReviewRequest, repo: Repo):
        database_url, _workspace_code, root = intake_settings(repo)
        if repo.get_intake_project(project_id) is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        refresh_workflow(database_url, root, project_id)
        try:
            revision_id, state, verdict = review_revision(
                database_url, project_id, payload.decision, payload.comment,
                payload.selected_master_asset_id,
            )
        except KeyError as exc:
            raise ApiError(404, "project_not_found", "intake project does not exist") from exc
        except IntakeConflict as exc:
            raise ApiError(409, "fidelity_gate_failed", str(exc)) from exc
        return IntakeActionResult(
            revision_id=revision_id, state=state, fidelity_verdict=verdict,
            message="review decision recorded",
        )

    @app.post("/v1/intake/projects/{project_id}/classifications/{suggestion_id}/review", tags=["intake"])
    def review_intake_classification(
        project_id: UUID,
        suggestion_id: UUID,
        payload: ClassificationReviewRequest,
        repo: Repo,
    ):
        database_url, _workspace_code, _root = intake_settings(repo)
        if repo.get_intake_project(project_id) is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        try:
            review_classification(
                database_url, project_id, suggestion_id, payload.decision,
                payload.category, payload.comment,
            )
        except KeyError as exc:
            raise ApiError(404, "classification_not_found", "classification suggestion does not exist") from exc
        return {"status": "recorded", "suggestion_id": str(suggestion_id)}

    @app.post("/v1/intake/projects/{project_id}/publish", response_model=IntakeActionResult, tags=["intake"])
    def publish_intake_project(project_id: UUID, repo: Repo):
        database_url, _workspace_code, root = intake_settings(repo)
        if repo.get_intake_project(project_id) is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        try:
            model_id = publish_revision(database_url, root, project_id)
        except IntakeConflict as exc:
            raise ApiError(409, "publication_blocked", str(exc)) from exc
        project = repo.get_intake_project(project_id)
        if project is None:
            raise ApiError(404, "project_not_found", "intake project does not exist")
        return IntakeActionResult(
            revision_id=project.revision_id, state="published", fidelity_verdict=project.fidelity_verdict,
            message=f"canonical model {model_id} published",
        )

    @app.get("/v1/projects/{project_id}", response_model=ProjectDetail, tags=["projects"])
    def get_project(project_id: UUID, repo: Repo):
        project = repo.get_project(project_id)
        if project is None:
            raise ApiError(404, "project_not_found", "project does not exist")
        return project

    @app.get("/v1/projects/{project_id}/models", response_model=ModelList, tags=["projects"])
    def list_models(project_id: UUID, repo: Repo):
        models = repo.list_models(project_id)
        if models is None:
            raise ApiError(404, "project_not_found", "project does not exist")
        return ModelList(project_id=project_id, items=models)

    @app.get(
        "/v1/project-revisions/{revision_id}/source-tree",
        response_model=SourceTree,
        tags=["sources"],
    )
    def get_source_tree(revision_id: UUID, repo: Repo):
        tree = repo.get_source_tree(revision_id)
        if tree is None:
            raise ApiError(404, "revision_not_found", "project revision does not exist")
        return tree

    @app.get(
        "/v1/models/{model_id}/scene-manifest",
        response_model=SceneManifest,
        tags=["scene"],
    )
    def get_scene_manifest(model_id: UUID, repo: Repo):
        manifest = repo.get_manifest(model_id)
        if manifest is None:
            raise ApiError(404, "model_not_found", "model does not exist")
        return manifest

    @app.get(
        "/v1/models/{model_id}/features",
        response_model=FeatureCollection,
        tags=["scene"],
    )
    def get_features(
        model_id: UUID,
        repo: Repo,
        response: Response,
        bbox: str | None = None,
        layers: str | None = None,
        lod: Annotated[int, Query(ge=0, le=3)] = 0,
        limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        manifest = repo.get_manifest(model_id)
        if manifest is None:
            raise ApiError(404, "model_not_found", "model does not exist")
        if bbox is None and manifest.feature_count > 1000:
            raise ApiError(422, "bbox_required", "bbox is required for non-small models")
        parsed_bbox = parse_bbox(bbox) if bbox is not None else manifest.extent
        layer_set = {item.strip() for item in layers.split(",") if item.strip()} if layers else None
        page = repo.get_features(model_id, parsed_bbox, layer_set, lod, limit + 1, offset) or []
        has_more = len(page) > limit
        features = page[:limit]
        response.headers["Cache-Control"] = "private, max-age=300, stale-while-revalidate=3600"
        return FeatureCollection(
            model_id=model_id,
            model_version=manifest.model_version,
            coordinate_space=manifest.coordinate_space,
            bbox=parsed_bbox,
            features=features,
            next_offset=offset + limit if has_more else None,
        )

    @app.get("/v1/objects/{object_id}", response_model=ObjectDetail, tags=["objects"])
    def get_object(object_id: UUID, repo: Repo):
        item = repo.get_object(object_id)
        if item is None:
            raise ApiError(404, "object_not_found", "object does not exist")
        return item

    @app.get(
        "/v1/objects/{object_id}/evidence",
        response_model=EvidenceList,
        tags=["objects"],
    )
    def get_evidence(object_id: UUID, repo: Repo):
        items = repo.get_evidence(object_id)
        if items is None:
            raise ApiError(404, "object_not_found", "object does not exist")
        return EvidenceList(object_id=object_id, items=items)

    return app


app = create_app()
