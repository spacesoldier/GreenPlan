\set ON_ERROR_STOP on

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS ltree;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS provenance;
CREATE SCHEMA IF NOT EXISTS biology;
CREATE SCHEMA IF NOT EXISTS rules;
CREATE SCHEMA IF NOT EXISTS planning;
CREATE SCHEMA IF NOT EXISTS intake;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS api;

CREATE TABLE ops.schema_migrations (
  version text PRIMARY KEY,
  description text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.organizations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  name text NOT NULL,
  organization_kind text NOT NULL CHECK (organization_kind IN (
    'customer', 'contractor', 'operator', 'data_provider', 'developer', 'other'
  )),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.actors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('human', 'service')),
  external_subject text UNIQUE,
  display_name text NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.organization_memberships (
  organization_id uuid NOT NULL REFERENCES core.organizations(id) ON DELETE CASCADE,
  actor_id uuid NOT NULL REFERENCES core.actors(id) ON DELETE CASCADE,
  role_code text NOT NULL,
  valid_during tstzrange,
  PRIMARY KEY (organization_id, actor_id, role_code)
);

CREATE TABLE catalog.workspaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  customer_id uuid REFERENCES core.organizations(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'active', 'completed', 'archived')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE catalog.workspace_memberships (
  workspace_id uuid NOT NULL REFERENCES catalog.workspaces(id) ON DELETE CASCADE,
  actor_id uuid NOT NULL REFERENCES core.actors(id) ON DELETE CASCADE,
  role_code text NOT NULL CHECK (role_code IN ('owner', 'editor', 'reviewer', 'viewer', 'operator')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, actor_id, role_code)
);

CREATE TABLE catalog.projects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES catalog.workspaces(id) ON DELETE RESTRICT,
  code text NOT NULL,
  title text NOT NULL,
  project_kind text NOT NULL DEFAULT 'territory_planning',
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'completed', 'archived')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, code)
);

CREATE TABLE catalog.project_revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES catalog.projects(id) ON DELETE RESTRICT,
  revision_no integer NOT NULL CHECK (revision_no > 0),
  received_at timestamptz,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  content_fingerprint text NOT NULL,
  status text NOT NULL DEFAULT 'registered' CHECK (status IN (
    'registered', 'inventory_complete', 'interpreted', 'approved', 'superseded', 'blocked'
  )),
  supersedes_id uuid REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  notes text,
  UNIQUE (project_id, revision_no),
  UNIQUE (project_id, content_fingerprint),
  CHECK (supersedes_id IS NULL OR supersedes_id <> id)
);

CREATE TABLE catalog.territories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  territory_kind text NOT NULL CHECK (territory_kind IN (
    'street', 'site', 'work_zone', 'district', 'linear_corridor', 'collection', 'other'
  )),
  jurisdiction_code text,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE catalog.project_territories (
  project_id uuid NOT NULL REFERENCES catalog.projects(id) ON DELETE RESTRICT,
  territory_id uuid NOT NULL REFERENCES catalog.territories(id) ON DELETE RESTRICT,
  role text NOT NULL CHECK (role IN ('primary', 'context', 'reference', 'adjacent')),
  PRIMARY KEY (project_id, territory_id, role)
);

CREATE TABLE catalog.coordinate_spaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  kind text NOT NULL CHECK (kind IN ('epsg', 'local_metric', 'cad_local', 'sheet')),
  srid integer,
  linear_unit text NOT NULL CHECK (linear_unit IN ('metre', 'millimetre', 'centimetre', 'foot', 'unknown')),
  axis_definition jsonb NOT NULL DEFAULT '{}'::jsonb,
  wkt text,
  status text NOT NULL DEFAULT 'asserted' CHECK (status IN ('asserted', 'candidate', 'verified', 'rejected')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((kind = 'epsg' AND srid IS NOT NULL) OR kind <> 'epsg')
);

CREATE TABLE catalog.canonical_models (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  territory_id uuid NOT NULL REFERENCES catalog.territories(id) ON DELETE RESTRICT,
  coordinate_space_id uuid NOT NULL REFERENCES catalog.coordinate_spaces(id) ON DELETE RESTRICT,
  model_kind text NOT NULL CHECK (model_kind IN ('existing', 'design_reference', 'combined', 'generated')),
  version_no integer NOT NULL CHECK (version_no > 0),
  assembly_status text NOT NULL DEFAULT 'assembling' CHECK (assembly_status IN (
    'assembling', 'needs_review', 'approved', 'blocked', 'retired'
  )),
  dependency_completeness numeric(4,3) CHECK (dependency_completeness BETWEEN 0 AND 1),
  semantic_coverage numeric(4,3) CHECK (semantic_coverage BETWEEN 0 AND 1),
  parent_model_id uuid REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  created_by_run_id uuid,
  approved_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (project_revision_id, territory_id, model_kind, version_no),
  CHECK (parent_model_id IS NULL OR parent_model_id <> id),
  CHECK (assembly_status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE catalog.model_dependencies (
  model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  dependency_model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  role text NOT NULL CHECK (role IN ('baseline', 'reference', 'context', 'derived_from')),
  PRIMARY KEY (model_id, dependency_model_id, role),
  CHECK (model_id <> dependency_model_id)
);

CREATE TABLE ops.software_components (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  version text NOT NULL,
  container_digest text,
  source_revision text,
  config_schema_version text,
  recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX software_components_identity_uq ON ops.software_components(
  name, version, COALESCE(container_digest, ''), COALESCE(source_revision, '')
);

CREATE TABLE ops.processing_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_kind text NOT NULL CHECK (run_kind IN (
    'inventory', 'conversion', 'cad_parse', 'semantic_mapping', 'model_assembly',
    'osm_import', 'conflation', 'rule_build', 'constraint_build', 'planning',
    'validation', 'publication', 'export', 'render'
  )),
  state text NOT NULL DEFAULT 'queued' CHECK (state IN (
    'queued', 'running', 'completed', 'completed_with_warnings', 'failed', 'cancelled'
  )),
  input_fingerprint text,
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  deterministic_seed bigint,
  parent_run_id uuid REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  requested_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  started_at timestamptz,
  finished_at timestamptz,
  error_summary text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (parent_run_id IS NULL OR parent_run_id <> id),
  CHECK (finished_at IS NULL OR started_at IS NOT NULL)
);

CREATE TABLE ops.run_components (
  run_id uuid NOT NULL REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  component_id uuid NOT NULL REFERENCES ops.software_components(id) ON DELETE RESTRICT,
  role text NOT NULL,
  PRIMARY KEY (run_id, component_id, role)
);

ALTER TABLE catalog.canonical_models
  ADD CONSTRAINT canonical_models_created_by_run_fk
  FOREIGN KEY (created_by_run_id) REFERENCES ops.processing_runs(id) ON DELETE RESTRICT;

CREATE TABLE geo.object_classes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  path ltree NOT NULL UNIQUE,
  parent_id uuid REFERENCES geo.object_classes(id) ON DELETE RESTRICT,
  title text NOT NULL,
  geometry_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_constraint_source boolean NOT NULL DEFAULT false,
  attribute_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX object_classes_path_gist_idx ON geo.object_classes USING gist (path);

CREATE TABLE geo.spatial_objects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  class_id uuid NOT NULL REFERENCES geo.object_classes(id) ON DELETE RESTRICT,
  stable_key text,
  name text,
  lifecycle text NOT NULL DEFAULT 'existing' CHECK (lifecycle IN (
    'existing', 'proposed', 'to_remove', 'to_relocate', 'historical', 'unknown'
  )),
  semantic_status text NOT NULL DEFAULT 'inferred' CHECK (semantic_status IN (
    'inferred', 'confirmed', 'needs_review', 'rejected'
  )),
  confidence numeric(4,3) NOT NULL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
  valid_during tstzrange,
  supersedes_object_id uuid REFERENCES geo.spatial_objects(id) ON DELETE RESTRICT,
  created_by_run_id uuid REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (supersedes_object_id IS NULL OR supersedes_object_id <> id)
);
CREATE UNIQUE INDEX spatial_objects_model_stable_key_uq
  ON geo.spatial_objects(model_id, stable_key) WHERE stable_key IS NOT NULL;
CREATE INDEX spatial_objects_model_class_lifecycle_idx
  ON geo.spatial_objects(model_id, class_id, lifecycle);

CREATE TABLE geo.object_geometries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  object_id uuid NOT NULL REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN (
    'position', 'centerline', 'footprint', 'boundary', 'surface', 'volume',
    'crown', 'root_zone', 'explicit_protection_zone', 'label_anchor', 'other'
  )),
  geom geometry(Geometry) NOT NULL,
  accuracy_m numeric CHECK (accuracy_m >= 0),
  z_policy text NOT NULL DEFAULT 'unknown' CHECK (z_policy IN ('absent', 'absolute', 'relative', 'unknown')),
  is_primary boolean NOT NULL DEFAULT false,
  validity_status text NOT NULL DEFAULT 'valid' CHECK (validity_status IN (
    'valid', 'repaired', 'invalid', 'needs_review'
  )),
  derivation_method text,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (NOT ST_IsEmpty(geom))
);
CREATE INDEX object_geometries_geom_gist_idx ON geo.object_geometries USING gist (geom);
CREATE INDEX object_geometries_object_role_idx ON geo.object_geometries(object_id, role);
CREATE UNIQUE INDEX object_geometries_primary_role_uq
  ON geo.object_geometries(object_id, role) WHERE is_primary;

CREATE TABLE geo.object_relations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_object_id uuid NOT NULL REFERENCES geo.spatial_objects(id) ON DELETE RESTRICT,
  predicate text NOT NULL CHECK (predicate IN (
    'part_of', 'belongs_to_network', 'connects_to', 'feeds', 'crosses',
    'contains', 'adjacent_to', 'same_as', 'supersedes', 'derived_from', 'conflicts_with'
  )),
  object_object_id uuid NOT NULL REFERENCES geo.spatial_objects(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'inferred' CHECK (status IN ('inferred', 'confirmed', 'needs_review', 'rejected')),
  confidence numeric(4,3) NOT NULL DEFAULT 0 CHECK (confidence BETWEEN 0 AND 1),
  distance_m numeric CHECK (distance_m >= 0),
  relation_geom geometry(Geometry),
  derivation_run_id uuid REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (subject_object_id <> object_object_id),
  UNIQUE (subject_object_id, predicate, object_object_id)
);
CREATE INDEX object_relations_subject_idx ON geo.object_relations(subject_object_id, predicate);
CREATE INDEX object_relations_object_idx ON geo.object_relations(object_object_id, predicate);
CREATE INDEX object_relations_geom_gist_idx ON geo.object_relations USING gist (relation_geom);

CREATE TABLE geo.network_systems (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  code text NOT NULL,
  title text,
  utility_kind text NOT NULL,
  owner_organization_id uuid REFERENCES core.organizations(id) ON DELETE RESTRICT,
  operational_status text CHECK (operational_status IN ('active', 'inactive', 'planned', 'abandoned', 'unknown')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (model_id, code)
);

CREATE TABLE geo.network_components (
  object_id uuid PRIMARY KEY REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  network_system_id uuid REFERENCES geo.network_systems(id) ON DELETE RESTRICT,
  component_kind text NOT NULL,
  medium text,
  placement text NOT NULL DEFAULT 'unknown' CHECK (placement IN ('underground', 'overhead', 'surface', 'unknown')),
  diameter_mm numeric CHECK (diameter_mm > 0),
  pressure_class text,
  voltage_kv numeric CHECK (voltage_kv >= 0),
  depth_m numeric CHECK (depth_m >= 0),
  operational_status text CHECK (operational_status IN ('active', 'inactive', 'planned', 'abandoned', 'unknown')),
  attribute_status text NOT NULL DEFAULT 'partial' CHECK (attribute_status IN ('complete', 'partial', 'unknown', 'conflict'))
);

CREATE TABLE geo.buildings (
  object_id uuid PRIMARY KEY REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  usage_code text,
  construction_type text,
  height_m numeric CHECK (height_m > 0),
  levels_above_ground numeric CHECK (levels_above_ground >= 0),
  height_status text NOT NULL DEFAULT 'unknown' CHECK (height_status IN ('confirmed', 'inferred', 'synthetic', 'unknown')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE geo.terrain_surfaces (
  object_id uuid PRIMARY KEY REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  surface_kind text NOT NULL CHECK (surface_kind IN ('existing', 'design', 'survey', 'synthetic')),
  vertical_datum text,
  elevation_accuracy_m numeric CHECK (elevation_accuracy_m >= 0)
);

CREATE TABLE geo.soil_units (
  object_id uuid PRIMARY KEY REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  soil_unit_code text,
  assessment_status text NOT NULL DEFAULT 'unknown' CHECK (assessment_status IN ('measured', 'inferred', 'synthetic', 'unknown'))
);

CREATE TABLE geo.soil_horizons (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  soil_unit_object_id uuid NOT NULL REFERENCES geo.soil_units(object_id) ON DELETE CASCADE,
  horizon_no integer NOT NULL CHECK (horizon_no > 0),
  top_depth_m numeric NOT NULL CHECK (top_depth_m >= 0),
  bottom_depth_m numeric NOT NULL,
  soil_texture text,
  bulk_density_kg_m3 numeric CHECK (bulk_density_kg_m3 > 0),
  ph_min numeric,
  ph_max numeric,
  organic_matter_fraction numeric CHECK (organic_matter_fraction BETWEEN 0 AND 1),
  drainage_class text,
  salinity_class text,
  value_status text NOT NULL DEFAULT 'unknown' CHECK (value_status IN ('measured', 'inferred', 'synthetic', 'unknown')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (soil_unit_object_id, horizon_no),
  CHECK (bottom_depth_m > top_depth_m),
  CHECK (ph_min IS NULL OR ph_max IS NULL OR ph_min <= ph_max)
);

CREATE TABLE geo.underground_obstacles (
  object_id uuid PRIMARY KEY REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  obstacle_kind text NOT NULL,
  top_depth_m numeric CHECK (top_depth_m >= 0),
  bottom_depth_m numeric CHECK (bottom_depth_m >= 0),
  CHECK (top_depth_m IS NULL OR bottom_depth_m IS NULL OR bottom_depth_m >= top_depth_m)
);

CREATE TABLE geo.groundwater_observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  position geometry(Point) NOT NULL,
  observed_at timestamptz,
  depth_m numeric NOT NULL CHECK (depth_m >= 0),
  accuracy_m numeric CHECK (accuracy_m >= 0),
  source_status text NOT NULL CHECK (source_status IN ('measured', 'inferred', 'historical', 'unknown')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX groundwater_observations_position_gist_idx
  ON geo.groundwater_observations USING gist (position);

CREATE TABLE provenance.external_datasets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider text NOT NULL,
  dataset_name text NOT NULL,
  snapshot_at timestamptz,
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  source_url text,
  media_type text NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint CHECK (size_bytes >= 0),
  license_code text,
  license_url text,
  attribution_text text,
  coverage geometry(MultiPolygon, 4326),
  importer_name text,
  importer_version text,
  import_config_hash text,
  status text NOT NULL DEFAULT 'registered' CHECK (status IN ('registered', 'imported', 'failed', 'retired')),
  UNIQUE (provider, sha256)
);
CREATE INDEX external_datasets_coverage_gist_idx ON provenance.external_datasets USING gist (coverage);

CREATE TABLE provenance.source_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_revision_id uuid REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  external_dataset_id uuid REFERENCES provenance.external_datasets(id) ON DELETE RESTRICT,
  parent_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  asset_kind text NOT NULL CHECK (asset_kind IN (
    'file', 'archive', 'archive_member', 'document', 'dataset', 'generated_artifact', 'other'
  )),
  media_type text,
  original_name text,
  storage_locator text,
  sha256 text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint CHECK (size_bytes >= 0),
  observed_at timestamptz,
  availability_status text NOT NULL DEFAULT 'available' CHECK (availability_status IN ('available', 'unavailable', 'retired')),
  license_code text,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  CHECK (project_revision_id IS NOT NULL OR external_dataset_id IS NOT NULL),
  CHECK (parent_asset_id IS NULL OR parent_asset_id <> id)
);
CREATE INDEX source_assets_revision_idx ON provenance.source_assets(project_revision_id);
CREATE INDEX source_assets_sha256_idx ON provenance.source_assets(sha256);

CREATE TABLE provenance.source_fragments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_asset_id uuid NOT NULL REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  fragment_kind text NOT NULL CHECK (fragment_kind IN (
    'cad_entity', 'cad_layer', 'cad_block', 'pdf_region', 'spreadsheet_range',
    'document_provision', 'image_region', 'dataset_feature', 'other'
  )),
  locator jsonb NOT NULL,
  locator_hash text NOT NULL,
  extracted_text text,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_asset_id, fragment_kind, locator_hash)
);

CREATE TABLE provenance.external_features (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id uuid NOT NULL REFERENCES provenance.external_datasets(id) ON DELETE RESTRICT,
  provider_type text NOT NULL,
  provider_id text NOT NULL,
  provider_version integer,
  feature_kind text NOT NULL,
  tags jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_geom geometry(Geometry, 4326),
  validity_status text NOT NULL DEFAULT 'valid' CHECK (validity_status IN ('valid', 'repaired', 'invalid', 'needs_review')),
  UNIQUE (dataset_id, provider_type, provider_id)
);
CREATE INDEX external_features_geom_gist_idx ON provenance.external_features USING gist (source_geom);
CREATE INDEX external_features_kind_idx ON provenance.external_features(dataset_id, feature_kind);

CREATE TABLE provenance.transforms (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_space_id uuid NOT NULL REFERENCES catalog.coordinate_spaces(id) ON DELETE RESTRICT,
  target_space_id uuid NOT NULL REFERENCES catalog.coordinate_spaces(id) ON DELETE RESTRICT,
  method text NOT NULL CHECK (method IN ('translation', 'rigid', 'similarity', 'affine', 'projected_crs', 'manual', 'other')),
  parameters jsonb NOT NULL,
  rms_error_m numeric CHECK (rms_error_m >= 0),
  max_error_m numeric CHECK (max_error_m >= 0),
  status text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'verified', 'rejected', 'retired')),
  applicable_for text[] NOT NULL DEFAULT ARRAY[]::text[],
  reviewed_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  reviewed_at timestamptz,
  created_by_run_id uuid REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (source_space_id <> target_space_id),
  CHECK (status <> 'verified' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);

CREATE TABLE provenance.transform_control_points (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  transform_id uuid NOT NULL REFERENCES provenance.transforms(id) ON DELETE CASCADE,
  point_no integer NOT NULL CHECK (point_no > 0),
  source_point geometry(Point) NOT NULL,
  target_point geometry(Point) NOT NULL,
  residual_m numeric CHECK (residual_m >= 0),
  source_fragment_id uuid REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (transform_id, point_no)
);

CREATE TABLE provenance.object_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  object_id uuid NOT NULL REFERENCES geo.spatial_objects(id) ON DELETE RESTRICT,
  source_fragment_id uuid REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  external_feature_id uuid REFERENCES provenance.external_features(id) ON DELETE RESTRICT,
  evidence_role text NOT NULL CHECK (evidence_role IN ('existence', 'classification', 'geometry', 'attribute', 'contradiction')),
  attribute_name text,
  asserted_value jsonb,
  transform_id uuid REFERENCES provenance.transforms(id) ON DELETE RESTRICT,
  method text NOT NULL,
  confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  decision text NOT NULL DEFAULT 'candidate' CHECK (decision IN ('candidate', 'accepted', 'conflict', 'rejected', 'stale')),
  reviewed_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(source_fragment_id, external_feature_id) = 1),
  CHECK (decision NOT IN ('accepted', 'rejected') OR reviewed_by IS NOT NULL)
);
CREATE INDEX object_evidence_object_role_idx ON provenance.object_evidence(object_id, evidence_role);
CREATE INDEX object_evidence_fragment_idx ON provenance.object_evidence(source_fragment_id);
CREATE INDEX object_evidence_external_feature_idx ON provenance.object_evidence(external_feature_id);

CREATE TABLE biology.taxa (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id uuid REFERENCES biology.taxa(id) ON DELETE RESTRICT,
  rank text NOT NULL CHECK (rank IN ('family', 'genus', 'species', 'subspecies', 'cultivar', 'group', 'unknown')),
  scientific_name text NOT NULL,
  common_names jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deprecated', 'needs_review')),
  UNIQUE (rank, scientific_name)
);

CREATE TABLE biology.plant_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  life_form text NOT NULL CHECK (life_form IN ('tree', 'shrub', 'grass', 'flower', 'groundcover', 'mixed')),
  taxon_id uuid REFERENCES biology.taxa(id) ON DELETE RESTRICT,
  planting_stock_class text,
  design_horizon_years integer CHECK (design_horizon_years >= 0),
  growth_form text,
  maintenance_regime text,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'retired', 'needs_review')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  approved_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  approved_at timestamptz,
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE biology.growth_stages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE CHECK (code IN ('at_planting', 'design_horizon', 'mature')),
  title text NOT NULL,
  ordinal integer NOT NULL UNIQUE CHECK (ordinal > 0)
);

CREATE TABLE biology.profile_dimensions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plant_profile_id uuid NOT NULL REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  growth_stage_id uuid NOT NULL REFERENCES biology.growth_stages(id) ON DELETE RESTRICT,
  height_min_m numeric CHECK (height_min_m >= 0),
  height_max_m numeric CHECK (height_max_m >= 0),
  crown_diameter_min_m numeric CHECK (crown_diameter_min_m >= 0),
  crown_diameter_max_m numeric CHECK (crown_diameter_max_m >= 0),
  crown_base_height_min_m numeric CHECK (crown_base_height_min_m >= 0),
  root_spread_min_m numeric CHECK (root_spread_min_m >= 0),
  root_spread_max_m numeric CHECK (root_spread_max_m >= 0),
  root_depth_min_m numeric CHECK (root_depth_min_m >= 0),
  root_depth_max_m numeric CHECK (root_depth_max_m >= 0),
  confidence numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'needs_review', 'retired')),
  UNIQUE (plant_profile_id, growth_stage_id),
  CHECK (height_min_m IS NULL OR height_max_m IS NULL OR height_min_m <= height_max_m),
  CHECK (crown_diameter_min_m IS NULL OR crown_diameter_max_m IS NULL OR crown_diameter_min_m <= crown_diameter_max_m),
  CHECK (root_spread_min_m IS NULL OR root_spread_max_m IS NULL OR root_spread_min_m <= root_spread_max_m),
  CHECK (root_depth_min_m IS NULL OR root_depth_max_m IS NULL OR root_depth_min_m <= root_depth_max_m)
);

CREATE TABLE biology.requirement_definitions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  value_kind text NOT NULL CHECK (value_kind IN ('numeric', 'category', 'boolean', 'geometry')),
  canonical_unit text,
  safety_critical boolean NOT NULL DEFAULT false,
  description text
);

CREATE TABLE biology.plant_requirements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plant_profile_id uuid NOT NULL REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  growth_stage_id uuid REFERENCES biology.growth_stages(id) ON DELETE RESTRICT,
  requirement_definition_id uuid NOT NULL REFERENCES biology.requirement_definitions(id) ON DELETE RESTRICT,
  comparison_operator text NOT NULL CHECK (comparison_operator IN ('>=', '>', '<=', '<', '=', 'between', 'in', 'contains')),
  value_min numeric,
  value_max numeric,
  categorical_value jsonb,
  unit text,
  geometry_role text,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'needs_review', 'retired')),
  source_fragment_id uuid REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  approved_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  approved_at timestamptz,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (value_min IS NULL OR value_max IS NULL OR value_min <= value_max),
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE biology.profile_evidence (
  plant_profile_id uuid NOT NULL REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  source_fragment_id uuid NOT NULL REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  evidence_role text NOT NULL CHECK (evidence_role IN ('taxonomy', 'dimension', 'requirement', 'suitability', 'contradiction')),
  confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  PRIMARY KEY (plant_profile_id, source_fragment_id, evidence_role)
);

CREATE TABLE geo.vegetation_objects (
  object_id uuid PRIMARY KEY REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  life_form text NOT NULL CHECK (life_form IN ('tree', 'shrub', 'grass', 'flower', 'groundcover', 'mixed')),
  taxon_id uuid REFERENCES biology.taxa(id) ON DELETE RESTRICT,
  plant_profile_id uuid REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  count integer NOT NULL DEFAULT 1 CHECK (count > 0),
  height_m numeric CHECK (height_m >= 0),
  crown_diameter_m numeric CHECK (crown_diameter_m >= 0),
  trunk_diameter_cm numeric CHECK (trunk_diameter_cm >= 0),
  condition_code text,
  planting_status text,
  attribute_status text NOT NULL DEFAULT 'partial' CHECK (attribute_status IN ('complete', 'partial', 'unknown', 'conflict'))
);

CREATE TABLE rules.jurisdictions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  parent_id uuid REFERENCES rules.jurisdictions(id) ON DELETE RESTRICT,
  valid_during daterange,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE rules.regulatory_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  title text NOT NULL,
  document_kind text NOT NULL,
  issuer_organization_id uuid REFERENCES core.organizations(id) ON DELETE RESTRICT,
  jurisdiction_id uuid REFERENCES rules.jurisdictions(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'repealed', 'draft', 'unknown')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE rules.document_editions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES rules.regulatory_documents(id) ON DELETE RESTRICT,
  edition_label text NOT NULL,
  effective_during daterange,
  official_url text,
  source_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  sha256 text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  status text NOT NULL DEFAULT 'unverified' CHECK (status IN ('unverified', 'verified', 'superseded', 'repealed')),
  verified_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  verified_at timestamptz,
  UNIQUE (document_id, edition_label),
  CHECK (status <> 'verified' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL))
);

CREATE TABLE rules.provisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  edition_id uuid NOT NULL REFERENCES rules.document_editions(id) ON DELETE RESTRICT,
  locator text NOT NULL,
  heading text,
  verified_excerpt text,
  source_fragment_id uuid REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'verified', 'retired')),
  verified_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  verified_at timestamptz,
  UNIQUE (edition_id, locator),
  CHECK (status <> 'verified' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL))
);

CREATE TABLE rules.intervention_classes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  path ltree NOT NULL UNIQUE,
  parent_id uuid REFERENCES rules.intervention_classes(id) ON DELETE RESTRICT,
  title text NOT NULL,
  active boolean NOT NULL DEFAULT true
);
CREATE INDEX intervention_classes_path_gist_idx ON rules.intervention_classes USING gist (path);

CREATE TABLE rules.rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  version_no integer NOT NULL DEFAULT 1 CHECK (version_no > 0),
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'approved', 'retired', 'rejected')),
  provision_id uuid NOT NULL REFERENCES rules.provisions(id) ON DELETE RESTRICT,
  jurisdiction_id uuid REFERENCES rules.jurisdictions(id) ON DELETE RESTRICT,
  effect_type text NOT NULL CHECK (effect_type IN (
    'prohibit', 'minimum_clearance', 'allow', 'allow_with_conditions',
    'require_approval', 'require_review', 'informational'
  )),
  geometry_operator text NOT NULL CHECK (geometry_operator IN (
    'buffer_centerline', 'buffer_footprint', 'inside', 'outside', 'no_overlap',
    'vertical_clearance', 'custom_review'
  )),
  distance_m numeric CHECK (distance_m >= 0),
  comparison_operator text CHECK (comparison_operator IN ('>=', '>', '<=', '<', '=', 'between')),
  priority integer NOT NULL DEFAULT 100,
  conditions jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_during daterange,
  safety_critical boolean NOT NULL DEFAULT true,
  approved_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  approved_at timestamptz,
  supersedes_rule_id uuid REFERENCES rules.rules(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
  CHECK (supersedes_rule_id IS NULL OR supersedes_rule_id <> id)
);

CREATE TABLE rules.rule_subject_classes (
  rule_id uuid NOT NULL REFERENCES rules.rules(id) ON DELETE RESTRICT,
  intervention_class_id uuid NOT NULL REFERENCES rules.intervention_classes(id) ON DELETE RESTRICT,
  PRIMARY KEY (rule_id, intervention_class_id)
);

CREATE TABLE rules.rule_object_classes (
  rule_id uuid NOT NULL REFERENCES rules.rules(id) ON DELETE RESTRICT,
  object_class_id uuid NOT NULL REFERENCES geo.object_classes(id) ON DELETE RESTRICT,
  include_descendants boolean NOT NULL DEFAULT true,
  PRIMARY KEY (rule_id, object_class_id)
);

CREATE TABLE rules.rule_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL,
  version_no integer NOT NULL CHECK (version_no > 0),
  title text NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'retired')),
  published_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  published_at timestamptz,
  content_fingerprint text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (code, version_no),
  UNIQUE (content_fingerprint),
  CHECK (status <> 'published' OR (published_by IS NOT NULL AND published_at IS NOT NULL))
);

CREATE TABLE rules.rule_set_members (
  rule_set_id uuid NOT NULL REFERENCES rules.rule_sets(id) ON DELETE RESTRICT,
  rule_id uuid NOT NULL REFERENCES rules.rules(id) ON DELETE RESTRICT,
  PRIMARY KEY (rule_set_id, rule_id)
);

CREATE TABLE planning.plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES catalog.projects(id) ON DELETE RESTRICT,
  territory_id uuid NOT NULL REFERENCES catalog.territories(id) ON DELETE RESTRICT,
  code text NOT NULL,
  title text NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'completed', 'archived')),
  created_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, code)
);

CREATE TABLE planning.plan_specs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id uuid NOT NULL REFERENCES planning.plans(id) ON DELETE RESTRICT,
  version_no integer NOT NULL CHECK (version_no > 0),
  baseline_model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  rule_set_id uuid NOT NULL REFERENCES rules.rule_sets(id) ON DELETE RESTRICT,
  deterministic_seed bigint NOT NULL,
  objectives jsonb NOT NULL DEFAULT '{}'::jsonb,
  constraints jsonb NOT NULL DEFAULT '{}'::jsonb,
  budget jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'retired')),
  published_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  published_at timestamptz,
  content_fingerprint text NOT NULL,
  UNIQUE (plan_id, version_no),
  UNIQUE (content_fingerprint),
  CHECK (status <> 'published' OR (published_by IS NOT NULL AND published_at IS NOT NULL))
);

CREATE TABLE planning.plan_spec_profiles (
  plan_spec_id uuid NOT NULL REFERENCES planning.plan_specs(id) ON DELETE RESTRICT,
  plant_profile_id uuid NOT NULL REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  intervention_class_id uuid NOT NULL REFERENCES rules.intervention_classes(id) ON DELETE RESTRICT,
  min_count integer CHECK (min_count >= 0),
  max_count integer CHECK (max_count >= 0),
  weight numeric NOT NULL DEFAULT 1 CHECK (weight >= 0),
  PRIMARY KEY (plan_spec_id, plant_profile_id)
);

CREATE TABLE planning.constraint_zones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  source_object_id uuid NOT NULL REFERENCES geo.spatial_objects(id) ON DELETE RESTRICT,
  rule_id uuid NOT NULL REFERENCES rules.rules(id) ON DELETE RESTRICT,
  intervention_class_id uuid NOT NULL REFERENCES rules.intervention_classes(id) ON DELETE RESTRICT,
  plant_profile_id uuid REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  effect_type text NOT NULL CHECK (effect_type IN (
    'prohibit', 'minimum_clearance', 'allow', 'allow_with_conditions',
    'require_approval', 'require_review', 'informational'
  )),
  geom geometry(Geometry) NOT NULL,
  distance_m numeric CHECK (distance_m >= 0),
  status text NOT NULL CHECK (status IN ('effective', 'needs_review', 'invalid')),
  derivation_run_id uuid NOT NULL REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (NOT ST_IsEmpty(geom))
);
CREATE INDEX constraint_zones_geom_gist_idx ON planning.constraint_zones USING gist (geom);
CREATE INDEX constraint_zones_lookup_idx ON planning.constraint_zones(
  model_id, intervention_class_id, plant_profile_id, effect_type
);

CREATE TABLE planning.plan_revisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_spec_id uuid NOT NULL REFERENCES planning.plan_specs(id) ON DELETE RESTRICT,
  revision_no integer NOT NULL CHECK (revision_no > 0),
  processing_run_id uuid NOT NULL REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'generated' CHECK (status IN (
    'generated', 'checked', 'needs_review', 'accepted', 'rejected', 'blocked', 'published'
  )),
  objective_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_model_id uuid REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  reviewed_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (plan_spec_id, revision_no),
  CHECK (status NOT IN ('accepted', 'rejected', 'published') OR reviewed_by IS NOT NULL),
  CHECK (status <> 'published' OR output_model_id IS NOT NULL)
);

CREATE TABLE planning.candidate_sites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_revision_id uuid NOT NULL REFERENCES planning.plan_revisions(id) ON DELETE RESTRICT,
  plant_profile_id uuid REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  geom geometry(Geometry) NOT NULL,
  generation_method text NOT NULL,
  score numeric,
  status text NOT NULL CHECK (status IN ('generated', 'evaluated', 'selected', 'rejected', 'needs_review')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (NOT ST_IsEmpty(geom))
);
CREATE INDEX candidate_sites_geom_gist_idx ON planning.candidate_sites USING gist (geom);

CREATE TABLE planning.site_capacity_assessments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_site_id uuid NOT NULL REFERENCES planning.candidate_sites(id) ON DELETE RESTRICT,
  plant_profile_id uuid NOT NULL REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  growth_stage_id uuid REFERENCES biology.growth_stages(id) ON DELETE RESTRICT,
  rootable_area_m2 numeric CHECK (rootable_area_m2 >= 0),
  effective_depth_m numeric CHECK (effective_depth_m >= 0),
  rootable_volume_m3 numeric CHECK (rootable_volume_m3 >= 0),
  open_soil_area_m2 numeric CHECK (open_soil_area_m2 >= 0),
  crown_clearance_status text CHECK (crown_clearance_status IN ('pass', 'fail', 'unknown')),
  remediation_possible boolean,
  status text NOT NULL CHECK (status IN ('sufficient', 'remediable', 'insufficient', 'unknown')),
  accuracy_m numeric CHECK (accuracy_m >= 0),
  method text NOT NULL,
  processing_run_id uuid NOT NULL REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE planning.capacity_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid NOT NULL REFERENCES planning.site_capacity_assessments(id) ON DELETE CASCADE,
  requirement_id uuid REFERENCES biology.plant_requirements(id) ON DELETE RESTRICT,
  metric_code text NOT NULL,
  actual_value numeric,
  required_value numeric,
  unit text,
  result text NOT NULL CHECK (result IN ('pass', 'fail', 'unknown', 'not_applicable')),
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE planning.intervention_packages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_revision_id uuid NOT NULL REFERENCES planning.plan_revisions(id) ON DELETE RESTRICT,
  code text NOT NULL,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'checked', 'accepted', 'rejected', 'published')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (plan_revision_id, code)
);

CREATE TABLE planning.proposals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_revision_id uuid NOT NULL REFERENCES planning.plan_revisions(id) ON DELETE RESTRICT,
  candidate_site_id uuid REFERENCES planning.candidate_sites(id) ON DELETE RESTRICT,
  intervention_package_id uuid REFERENCES planning.intervention_packages(id) ON DELETE RESTRICT,
  intervention_class_id uuid NOT NULL REFERENCES rules.intervention_classes(id) ON DELETE RESTRICT,
  plant_profile_id uuid REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  stable_key text NOT NULL,
  quantity integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
  status text NOT NULL DEFAULT 'generated' CHECK (status IN (
    'generated', 'checked', 'needs_review', 'accepted', 'rejected', 'blocked', 'published'
  )),
  score numeric,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (plan_revision_id, stable_key)
);

CREATE TABLE planning.proposal_geometries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id uuid NOT NULL REFERENCES planning.proposals(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('position', 'footprint', 'crown', 'root_zone', 'work_zone', 'other')),
  geom geometry(Geometry) NOT NULL,
  growth_stage_id uuid REFERENCES biology.growth_stages(id) ON DELETE RESTRICT,
  is_primary boolean NOT NULL DEFAULT false,
  CHECK (NOT ST_IsEmpty(geom))
);
CREATE INDEX proposal_geometries_geom_gist_idx ON planning.proposal_geometries USING gist (geom);
CREATE UNIQUE INDEX proposal_geometries_primary_role_uq
  ON planning.proposal_geometries(proposal_id, role, COALESCE(growth_stage_id, '00000000-0000-0000-0000-000000000000'::uuid))
  WHERE is_primary;

CREATE TABLE planning.site_preparation_actions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  intervention_package_id uuid NOT NULL REFERENCES planning.intervention_packages(id) ON DELETE RESTRICT,
  action_kind text NOT NULL CHECK (action_kind IN (
    'excavate', 'fill', 'soil_replace', 'engineered_soil', 'raised_bed',
    'decompact', 'drainage', 'irrigation', 'root_barrier', 'other'
  )),
  footprint geometry(Geometry) NOT NULL,
  top_z_m numeric,
  bottom_z_m numeric,
  material_spec jsonb NOT NULL DEFAULT '{}'::jsonb,
  volume_m3 numeric CHECK (volume_m3 >= 0),
  cost_estimate numeric CHECK (cost_estimate >= 0),
  carbon_kg_co2e numeric,
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'checked', 'accepted', 'rejected')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (NOT ST_IsEmpty(footprint)),
  CHECK (top_z_m IS NULL OR bottom_z_m IS NULL OR top_z_m >= bottom_z_m)
);
CREATE INDEX site_preparation_actions_geom_gist_idx ON planning.site_preparation_actions USING gist (footprint);

CREATE TABLE planning.decision_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  proposal_id uuid NOT NULL REFERENCES planning.proposals(id) ON DELETE RESTRICT,
  check_kind text NOT NULL CHECK (check_kind IN (
    'regulatory', 'biological', 'spatial', 'construction', 'input_quality'
  )),
  result text NOT NULL CHECK (result IN ('pass', 'fail', 'unknown', 'not_applicable')),
  safety_critical boolean NOT NULL DEFAULT false,
  rule_id uuid REFERENCES rules.rules(id) ON DELETE RESTRICT,
  source_object_id uuid REFERENCES geo.spatial_objects(id) ON DELETE RESTRICT,
  constraint_zone_id uuid REFERENCES planning.constraint_zones(id) ON DELETE RESTRICT,
  requirement_id uuid REFERENCES biology.plant_requirements(id) ON DELETE RESTRICT,
  actual_value numeric,
  required_value numeric,
  unit text,
  actual_distance_m numeric CHECK (actual_distance_m >= 0),
  required_distance_m numeric CHECK (required_distance_m >= 0),
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  processing_run_id uuid NOT NULL REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX decision_checks_proposal_result_idx ON planning.decision_checks(proposal_id, result);

CREATE TABLE planning.rejections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_site_id uuid REFERENCES planning.candidate_sites(id) ON DELETE RESTRICT,
  proposal_id uuid REFERENCES planning.proposals(id) ON DELETE RESTRICT,
  reason_code text NOT NULL,
  explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(candidate_site_id, proposal_id) = 1)
);

CREATE TABLE intake.deliveries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  root_locator text NOT NULL,
  content_fingerprint text NOT NULL,
  received_at timestamptz,
  status text NOT NULL DEFAULT 'registered' CHECK (status IN ('registered', 'inventoried', 'processed', 'blocked', 'retired')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (project_revision_id, content_fingerprint)
);

CREATE TABLE intake.delivery_entries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  delivery_id uuid NOT NULL REFERENCES intake.deliveries(id) ON DELETE RESTRICT,
  source_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  parent_entry_id uuid REFERENCES intake.delivery_entries(id) ON DELETE RESTRICT,
  relative_path text NOT NULL,
  entry_kind text NOT NULL CHECK (entry_kind IN ('directory', 'file', 'archive', 'archive_member', 'symlink', 'other')),
  media_kind text,
  size_bytes bigint CHECK (size_bytes >= 0),
  sha256 text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
  role text,
  confidence numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
  cues jsonb NOT NULL DEFAULT '[]'::jsonb,
  UNIQUE (delivery_id, relative_path),
  CHECK (parent_entry_id IS NULL OR parent_entry_id <> id)
);

CREATE TABLE intake.conversion_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_asset_id uuid NOT NULL REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  processing_run_id uuid REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN (
    'queued', 'oda_running', 'libredwg_queued', 'libredwg_running',
    'completed', 'completed_with_warnings', 'failed', 'cancelled'
  )),
  warning_count integer NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
  error_summary text,
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);

CREATE TABLE intake.conversion_stages (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES intake.conversion_jobs(id) ON DELETE CASCADE,
  stage text NOT NULL,
  state text NOT NULL,
  command jsonb NOT NULL DEFAULT '[]'::jsonb,
  exit_code integer,
  stdout text NOT NULL DEFAULT '',
  stderr text NOT NULL DEFAULT '',
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
CREATE INDEX conversion_stages_job_idx ON intake.conversion_stages(job_id, id);

CREATE TABLE intake.conversion_artifacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES intake.conversion_jobs(id) ON DELETE RESTRICT,
  source_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  stage text NOT NULL,
  kind text NOT NULL,
  storage_locator text NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, storage_locator)
);

CREATE TABLE intake.publications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  artifact_id uuid NOT NULL REFERENCES intake.conversion_artifacts(id) ON DELETE RESTRICT,
  publication_kind text NOT NULL,
  target_locator text NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  published_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (publication_kind, target_locator)
);

CREATE TABLE intake.cad_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_asset_id uuid NOT NULL REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  format text NOT NULL CHECK (format IN ('dwg', 'dxf')),
  format_version text,
  coordinate_space_id uuid REFERENCES catalog.coordinate_spaces(id) ON DELETE RESTRICT,
  units text,
  extents geometry(Polygon),
  parse_status text NOT NULL CHECK (parse_status IN ('pending', 'parsed', 'partial', 'failed', 'needs_review')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_asset_id)
);

CREATE TABLE intake.cad_xrefs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cad_document_id uuid NOT NULL REFERENCES intake.cad_documents(id) ON DELETE RESTRICT,
  referenced_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  reference_name text NOT NULL,
  original_path text,
  resolved_status text NOT NULL CHECK (resolved_status IN ('resolved', 'missing', 'ambiguous', 'ignored')),
  transform_id uuid REFERENCES provenance.transforms(id) ON DELETE RESTRICT,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE intake.cad_layers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cad_document_id uuid NOT NULL REFERENCES intake.cad_documents(id) ON DELETE RESTRICT,
  source_fragment_id uuid REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  name text NOT NULL,
  entity_count bigint NOT NULL DEFAULT 0 CHECK (entity_count >= 0),
  candidate_class_id uuid REFERENCES geo.object_classes(id) ON DELETE RESTRICT,
  mapping_status text NOT NULL DEFAULT 'unmapped' CHECK (mapping_status IN ('unmapped', 'candidate', 'confirmed', 'rejected')),
  confidence numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (cad_document_id, name)
);

CREATE TABLE intake.cad_entities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cad_document_id uuid NOT NULL REFERENCES intake.cad_documents(id) ON DELETE RESTRICT,
  cad_layer_id uuid REFERENCES intake.cad_layers(id) ON DELETE RESTRICT,
  source_fragment_id uuid NOT NULL REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  handle text NOT NULL,
  entity_type text NOT NULL,
  block_path text,
  bbox geometry(Polygon),
  diagnostic_geom geometry(Geometry),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE UNIQUE INDEX cad_entities_document_handle_block_uq ON intake.cad_entities(
  cad_document_id, handle, COALESCE(block_path, '')
);
CREATE INDEX cad_entities_bbox_gist_idx ON intake.cad_entities USING gist (bbox);
CREATE INDEX cad_entities_geom_gist_idx ON intake.cad_entities USING gist (diagnostic_geom);

CREATE TABLE audit.events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_id uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  action text NOT NULL,
  entity_schema text NOT NULL,
  entity_table text NOT NULL,
  entity_id uuid,
  run_id uuid REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  before_digest text,
  after_digest text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX audit_events_entity_idx ON audit.events(entity_schema, entity_table, entity_id, occurred_at);
CREATE INDEX audit_events_run_idx ON audit.events(run_id, occurred_at);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('0001', 'GreenPlan domain schema v1');

COMMIT;
