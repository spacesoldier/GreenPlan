export type CoordinateSpace = {
  id: string;
  kind: string;
  srid: number | null;
  unit: string;
  status: string;
};

export type Project = {
  id: string;
  code: string;
  title: string;
  status: string;
  current_revision_id: string;
  current_model_id: string;
  model_version: number;
  assembly_status: string;
  crs_status: string;
};

export type SceneLayer = {
  id: string;
  title: string;
  class_codes: string[];
  geometry_roles: string[];
  feature_count: number;
};

export type SceneManifest = {
  model_id: string;
  model_version: number;
  coordinate_space: CoordinateSpace;
  extent: [number, number, number, number];
  spatial_focus: {
    extent: [number, number, number, number];
    center: [number, number];
    method: string;
    algorithm_version: string;
    object_count: number;
    total_object_count: number;
    coverage: number;
  } | null;
  layers: SceneLayer[];
  issues: { needs_review: number; conflict: number };
  feature_count: number;
};

export type Geometry = {
  type: string;
  coordinates?: unknown;
  geometries?: Geometry[];
};

export type Feature = {
  id: string;
  stable_key: string;
  class_code: string;
  layer_id: string;
  name: string | null;
  lifecycle: string;
  semantic_status: string;
  confidence: number;
  geometry_role: string;
  geometry: Geometry;
  properties: Record<string, unknown>;
};

export type FeatureCollection = {
  resource_version: string;
  model_id: string;
  model_version: number;
  coordinate_space: CoordinateSpace;
  bbox: [number, number, number, number];
  features: Feature[];
  next_offset: number | null;
};

export type SourceNode = {
  id: string;
  parent_id: string | null;
  kind: string;
  title: string;
  display_path: string;
  media_type: string | null;
  availability_status: string;
};

export type ObjectDetail = Feature & {
  model_id: string;
  source: {
    asset_id: string;
    fragment_id: string;
    path: string;
    layer: string | null;
    handle: string | null;
    transform_id: string | null;
  };
};

export type Evidence = {
  id: string;
  role: string;
  attribute_name: string | null;
  asserted_value: unknown;
  method: string;
  confidence: number;
  decision: string;
};

export type IntakeProjectSummary = {
  id: string;
  code: string;
  title: string;
  project_status: string;
  revision_id: string;
  revision_no: number;
  intake_state: string;
  fidelity_verdict: string | null;
  delivery_id: string;
  file_count: number;
  total_bytes: number;
  cad_count: number;
  finding_count: number;
  critical_count: number;
  current_model_id: string | null;
  updated_at: string;
};

export type IntakeFile = {
  id: string;
  relative_path: string;
  original_name: string;
  media_kind: string | null;
  size_bytes: number;
  sha256: string;
  role: string | null;
  detected_format: string | null;
  format_version: string | null;
  source_modified_at: string | null;
  uploaded_at: string;
};

export type IntakeStage = {
  id: string;
  source_asset_id: string | null;
  stage: string;
  attempt_no: number;
  state: string;
  progress: number;
  metrics: Record<string, unknown>;
  stdout: string;
  stderr: string;
  error_summary: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type FidelityFinding = {
  id: string;
  source_asset_id: string | null;
  code: string;
  severity: "info" | "warning" | "critical";
  stage: string;
  title: string;
  detail: string;
  evidence: Record<string, unknown>;
  status: string;
  resolution: { action?: string; reason?: string; impact?: Record<string, unknown>; created_at?: string };
};

export type MasterCandidate = {
  source_asset_id: string;
  relative_path: string;
  score: number;
  role: string;
  cues: string[];
  selected: boolean;
};

export type CadInventory = {
  id: string;
  source_asset_id: string;
  relative_path: string;
  stage: string;
  format: string;
  format_version: string | null;
  parse_status: string;
  tool_name: string | null;
  tool_version: string | null;
  metrics: Record<string, unknown>;
  artifact_locator: string | null;
};

export type CadSpace = {
  id: string;
  source_asset_id: string;
  source_relative_path: string;
  inventory_stage: string;
  name: string;
  space_kind: "model" | "layout";
  entity_count: number;
};

export type CadLayer = {
  id: string;
  suggestion_id: string;
  source_asset_id: string;
  source_relative_path: string;
  name: string;
  entity_count: number;
  mapping_status: string;
  confidence: number | null;
  suggested_category: string;
  method: string;
  entity_types: Record<string, number>;
  axis_results: ClassificationSuggestion["axis_results"];
  review_status: string;
};

export type ClassificationSuggestion = {
  id: string;
  target_kind: "file" | "cad_layer" | "cad_block" | "cad_text";
  target_key: string;
  source_asset_id: string | null;
  target_label: string;
  suggested_category: string;
  confidence: number;
  method: string;
  cues: string[];
  alternatives: Array<{ category: string; confidence: number }>;
  review_status: string;
  taxonomy_version: string | null;
  axis_results: {
    taxonomy_version?: string;
    review_required?: boolean;
    axes?: Record<string, { label: string; confidence: number; cues: string[] }>;
  };
};

export type AssistantTask = {
  id: string;
  task_key: string;
  title: string;
  position: number;
  state: string;
  dependencies: string[];
  attempts: number;
  progress: number;
  error_summary: string | null;
  started_at: string | null;
  heartbeat_at: string | null;
  finished_at: string | null;
};

export type AssistantRun = {
  id: string;
  revision_id: string;
  input_fingerprint: string;
  schema_version: string;
  taxonomy_version: string;
  provider_version: string;
  state: string;
  progress: number;
  summary: Record<string, unknown>;
  error_summary: string | null;
  started_at: string | null;
  heartbeat_at: string | null;
  finished_at: string | null;
  created_at: string;
  tasks: AssistantTask[];
};

export type SemanticSuggestionJob = {
  id: string;
  source_asset_id: string;
  provider: string;
  model: string;
  state: string;
  total_count: number;
  completed_count: number;
  failed_count: number;
  error_summary: string | null;
  started_at: string | null;
  heartbeat_at: string | null;
  finished_at: string | null;
  created_at: string;
};

export type IntakeProjectDetail = IntakeProjectSummary & {
  description: string | null;
  files: IntakeFile[];
  stages: IntakeStage[];
  findings: FidelityFinding[];
  master_candidates: MasterCandidate[];
  inventories: CadInventory[];
  cad_spaces: CadSpace[];
  cad_layers: CadLayer[];
  classification_suggestions: ClassificationSuggestion[];
  assistant_runs: AssistantRun[];
  xref_dependencies: CadXrefDependency[];
  semantic_suggestion_jobs: SemanticSuggestionJob[];
};

export type CadXrefDependency = {
  id: string;
  source_asset_id: string;
  source_relative_path: string;
  referenced_asset_id: string | null;
  target_relative_path: string | null;
  reference_name: string;
  original_path: string | null;
  status: string;
  overlay: boolean;
  placement_count: number;
  matches: string[];
};
