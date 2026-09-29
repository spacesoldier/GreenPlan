from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .models import (
    AssistantRunView,
    Evidence,
    Feature,
    ModelSummary,
    ObjectDetail,
    ProjectDetail,
    ProjectSummary,
    SceneManifest,
    SurfaceRegionDetection,
    SourceTree,
    IntakeProjectDetail,
    IntakeProjectSummary,
)

BBox = tuple[float, float, float, float]


class RepositoryUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class FeatureRecord:
    model_id: UUID
    bbox: BBox
    feature: Feature
    detail: ObjectDetail


class Repository(Protocol):
    def ping(self) -> None: ...

    def list_projects(self) -> list[ProjectSummary]: ...

    def get_project(self, project_id: UUID) -> ProjectDetail | None: ...

    def list_models(self, project_id: UUID) -> list[ModelSummary] | None: ...

    def get_manifest(self, model_id: UUID, root_id: UUID | None = None) -> SceneManifest | None: ...

    def get_features(
        self, model_id: UUID, bbox: BBox, layers: set[str] | None, lod: int,
        limit: int | None = None, offset: int = 0, root_id: UUID | None = None,
    ) -> list[Feature] | None: ...

    def detect_surface_region(
        self, model_id: UUID, root_id: UUID | None, x: float, y: float,
    ) -> SurfaceRegionDetection | None: ...

    def get_object(self, object_id: UUID) -> ObjectDetail | None: ...

    def get_evidence(self, object_id: UUID) -> list[Evidence] | None: ...

    def get_source_tree(self, revision_id: UUID) -> SourceTree | None: ...

    def list_intake_projects(self) -> list[IntakeProjectSummary]: ...

    def get_intake_project(self, project_id: UUID) -> IntakeProjectDetail | None: ...

    def get_assistant_run(self, run_id: UUID) -> AssistantRunView | None: ...


def intersects(left: BBox, right: BBox) -> bool:
    return not (
        left[2] < right[0]
        or left[0] > right[2]
        or left[3] < right[1]
        or left[1] > right[3]
    )


class InMemoryRepository:
    def __init__(
        self,
        *,
        projects: list[ProjectDetail],
        models: list[ModelSummary],
        manifests: list[SceneManifest],
        features: list[FeatureRecord],
        evidence: dict[UUID, list[Evidence]],
        source_trees: list[SourceTree],
    ) -> None:
        self.available = True
        self._projects = {item.id: item for item in projects}
        self._models = {item.id: item for item in models}
        self._manifests = {item.model_id: item for item in manifests}
        self._features = features
        self._objects = {item.feature.id: item.detail for item in features}
        self._evidence = evidence
        self._source_trees = {item.revision_id: item for item in source_trees}

    def ping(self) -> None:
        if not self.available:
            raise RepositoryUnavailable("repository is unavailable")

    def list_projects(self) -> list[ProjectSummary]:
        self.ping()
        return [
            ProjectSummary(
                **{
                    field_name: getattr(item, field_name)
                    for field_name in ProjectSummary.model_fields
                }
            )
            for item in self._projects.values()
        ]

    def get_project(self, project_id: UUID) -> ProjectDetail | None:
        self.ping()
        return self._projects.get(project_id)

    def list_models(self, project_id: UUID) -> list[ModelSummary] | None:
        self.ping()
        if project_id not in self._projects:
            return None
        revision_id = self._projects[project_id].current_revision_id
        return [item for item in self._models.values() if item.project_revision_id == revision_id]

    def get_manifest(self, model_id: UUID, root_id: UUID | None = None) -> SceneManifest | None:
        self.ping()
        manifest = self._manifests.get(model_id)
        if manifest is None or not manifest.roots:
            return manifest
        active = root_id or manifest.active_root_id or next(
            (item.id for item in manifest.roots if item.role == "effective_design"), manifest.roots[0].id,
        )
        if not any(item.id == active for item in manifest.roots):
            return None
        return manifest.model_copy(update={"active_root_id": active})

    def get_features(
        self, model_id: UUID, bbox: BBox, layers: set[str] | None, lod: int,
        limit: int | None = None, offset: int = 0, root_id: UUID | None = None,
    ) -> list[Feature] | None:
        self.ping()
        if model_id not in self._manifests:
            return None
        items = [
            record.feature
            for record in self._features
            if record.model_id == model_id
            and intersects(record.bbox, bbox)
            and (not layers or record.feature.layer_id in layers)
            and (root_id is None or record.feature.properties.get("publication_root_id") == str(root_id))
        ]
        return items[offset:] if limit is None else items[offset:offset + limit]

    def detect_surface_region(
        self, model_id: UUID, root_id: UUID | None, x: float, y: float,
    ) -> SurfaceRegionDetection | None:
        self.ping()
        return None

    def get_object(self, object_id: UUID) -> ObjectDetail | None:
        self.ping()
        return self._objects.get(object_id)

    def get_evidence(self, object_id: UUID) -> list[Evidence] | None:
        self.ping()
        if object_id not in self._objects:
            return None
        return self._evidence.get(object_id, [])

    def get_source_tree(self, revision_id: UUID) -> SourceTree | None:
        self.ping()
        return self._source_trees.get(revision_id)
