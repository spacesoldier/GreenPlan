from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoordinateSpace(ApiModel):
    id: UUID
    kind: str
    srid: int | None = None
    unit: str
    status: str


class ProjectSummary(ApiModel):
    id: UUID
    code: str
    title: str
    status: str
    current_revision_id: UUID
    current_model_id: UUID
    model_version: int
    assembly_status: str
    crs_status: str


class ProjectList(ApiModel):
    resource_version: Literal["1"] = "1"
    items: list[ProjectSummary]


class ProjectDetail(ProjectSummary):
    revision_no: int
    coordinate_space: CoordinateSpace
    quality: dict[str, int | float | str]


class ModelSummary(ApiModel):
    id: UUID
    project_revision_id: UUID
    version: int
    kind: str
    assembly_status: str
    coordinate_space: CoordinateSpace


class ModelList(ApiModel):
    resource_version: Literal["1"] = "1"
    project_id: UUID
    items: list[ModelSummary]


class SceneLayer(ApiModel):
    id: str
    title: str
    class_codes: list[str]
    geometry_roles: list[str]
    feature_count: int


class SceneSpatialFocus(ApiModel):
    extent: tuple[float, float, float, float]
    center: tuple[float, float]
    method: str
    algorithm_version: str
    object_count: int
    total_object_count: int
    coverage: float = Field(gt=0, le=1)


class SceneManifest(ApiModel):
    resource_version: Literal["1"] = "1"
    model_id: UUID
    model_version: int
    coordinate_space: CoordinateSpace
    extent: tuple[float, float, float, float]
    spatial_focus: SceneSpatialFocus | None = None
    layers: list[SceneLayer]
    issues: dict[str, int]
    feature_count: int


class Feature(ApiModel):
    id: UUID
    stable_key: str
    class_code: str
    layer_id: str
    name: str | None = None
    lifecycle: str
    semantic_status: str
    confidence: float = Field(ge=0, le=1)
    geometry_role: str
    geometry: dict[str, Any]
    properties: dict[str, Any] = Field(default_factory=dict)


class FeatureCollection(ApiModel):
    resource_version: Literal["1"] = "1"
    model_id: UUID
    model_version: int
    coordinate_space: CoordinateSpace
    bbox: tuple[float, float, float, float]
    features: list[Feature]
    next_offset: int | None = None


class SourceReference(ApiModel):
    asset_id: UUID
    fragment_id: UUID
    path: str
    layer: str | None = None
    handle: str | None = None
    transform_id: UUID | None = None


class ObjectDetail(Feature):
    model_id: UUID
    source: SourceReference


class Evidence(ApiModel):
    id: UUID
    role: str
    attribute_name: str | None = None
    asserted_value: Any = None
    method: str
    confidence: float = Field(ge=0, le=1)
    decision: str
    source_fragment_id: UUID | None = None
    external_feature_id: UUID | None = None
    transform_id: UUID | None = None


class EvidenceList(ApiModel):
    resource_version: Literal["1"] = "1"
    object_id: UUID
    items: list[Evidence]


class SourceNode(ApiModel):
    id: UUID
    parent_id: UUID | None = None
    kind: str
    title: str
    display_path: str
    media_type: str | None = None
    availability_status: str


class SourceTree(ApiModel):
    resource_version: Literal["1"] = "1"
    revision_id: UUID
    nodes: list[SourceNode]


class IntakeProjectCreate(ApiModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=2, max_length=240)
    description: str | None = Field(default=None, max_length=2000)


class IntakeProjectSummary(ApiModel):
    id: UUID
    code: str
    title: str
    project_status: str
    revision_id: UUID
    revision_no: int
    intake_state: str
    fidelity_verdict: str | None = None
    delivery_id: UUID
    file_count: int = 0
    total_bytes: int = 0
    cad_count: int = 0
    finding_count: int = 0
    critical_count: int = 0
    current_model_id: UUID | None = None
    updated_at: datetime


class IntakeProjectList(ApiModel):
    resource_version: Literal["1"] = "1"
    items: list[IntakeProjectSummary]


class IntakeFile(ApiModel):
    id: UUID
    relative_path: str
    original_name: str
    media_kind: str | None = None
    size_bytes: int
    sha256: str
    role: str | None = None
    detected_format: str | None = None
    format_version: str | None = None


class IntakeStage(ApiModel):
    id: UUID
    source_asset_id: UUID | None = None
    stage: str
    attempt_no: int
    state: str
    progress: float
    metrics: dict[str, Any] = Field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    error_summary: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FidelityFinding(ApiModel):
    id: UUID
    source_asset_id: UUID | None = None
    code: str
    severity: str
    stage: str
    title: str
    detail: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    status: str


class MasterCandidate(ApiModel):
    source_asset_id: UUID
    relative_path: str
    score: float
    role: str
    cues: list[str] = Field(default_factory=list)
    selected: bool


class CadInventory(ApiModel):
    id: UUID
    source_asset_id: UUID
    relative_path: str
    stage: str
    format: str
    format_version: str | None = None
    parse_status: str
    tool_name: str | None = None
    tool_version: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_locator: str | None = None


class ClassificationSuggestionView(ApiModel):
    id: UUID
    target_kind: str
    target_key: str
    source_asset_id: UUID | None = None
    target_label: str
    suggested_category: str
    confidence: float
    method: str
    cues: list[str] = Field(default_factory=list)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    review_status: str
    taxonomy_version: str | None = None
    axis_results: dict[str, Any] = Field(default_factory=dict)


class AssistantTaskView(ApiModel):
    id: UUID
    task_key: str
    title: str
    position: int
    state: str
    dependencies: list[str] = Field(default_factory=list)
    attempts: int
    progress: float
    error_summary: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None


class AssistantRunView(ApiModel):
    id: UUID
    revision_id: UUID
    input_fingerprint: str
    schema_version: str
    taxonomy_version: str
    provider_version: str
    state: str
    progress: float
    summary: dict[str, Any] = Field(default_factory=dict)
    error_summary: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    tasks: list[AssistantTaskView] = Field(default_factory=list)


class ClassificationReviewRequest(ApiModel):
    decision: Literal["accept", "reject"]
    category: str | None = Field(default=None, max_length=160)
    comment: str | None = Field(default=None, max_length=2000)


class IntakeProjectDetail(IntakeProjectSummary):
    description: str | None = None
    files: list[IntakeFile] = Field(default_factory=list)
    stages: list[IntakeStage] = Field(default_factory=list)
    findings: list[FidelityFinding] = Field(default_factory=list)
    master_candidates: list[MasterCandidate] = Field(default_factory=list)
    inventories: list[CadInventory] = Field(default_factory=list)
    classification_suggestions: list[ClassificationSuggestionView] = Field(default_factory=list)
    assistant_runs: list[AssistantRunView] = Field(default_factory=list)


class IntakeUploadResult(ApiModel):
    asset_id: UUID
    relative_path: str
    sha256: str
    size_bytes: int
    detected_format: str
    deduplicated: bool


class IntakeActionResult(ApiModel):
    revision_id: UUID
    state: str
    fidelity_verdict: str | None = None
    message: str


class IntakeReviewRequest(ApiModel):
    decision: Literal["accept", "reject"]
    comment: str = Field(min_length=3, max_length=2000)
    selected_master_asset_id: UUID | None = None
