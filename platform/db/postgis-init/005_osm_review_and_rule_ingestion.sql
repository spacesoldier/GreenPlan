\set ON_ERROR_STOP on

BEGIN;

-- Regulatory documents can be global assets; they must not be attached to a
-- synthetic project revision merely to satisfy provenance.
ALTER TABLE provenance.source_assets ADD COLUMN scope_kind text;

UPDATE provenance.source_assets
SET scope_kind = CASE
  WHEN project_revision_id IS NOT NULL THEN 'project_revision'
  WHEN external_dataset_id IS NOT NULL THEN 'external_dataset'
  ELSE 'global'
END;

ALTER TABLE provenance.source_assets
  ALTER COLUMN scope_kind SET DEFAULT 'project_revision',
  ALTER COLUMN scope_kind SET NOT NULL,
  DROP CONSTRAINT source_assets_check,
  ADD CONSTRAINT source_assets_scope_kind_check CHECK (
    (scope_kind = 'project_revision' AND project_revision_id IS NOT NULL AND external_dataset_id IS NULL)
    OR (scope_kind = 'external_dataset' AND external_dataset_id IS NOT NULL AND project_revision_id IS NULL)
    OR (scope_kind = 'global' AND project_revision_id IS NULL AND external_dataset_id IS NULL)
  );

-- Clicking an OSM feature creates a review proposal, never a canonical object.
CREATE TABLE provenance.object_candidates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE RESTRICT,
  external_feature_id uuid NOT NULL REFERENCES provenance.external_features(id) ON DELETE RESTRICT,
  target_class_id uuid NOT NULL REFERENCES geo.object_classes(id) ON DELETE RESTRICT,
  transform_id uuid REFERENCES provenance.transforms(id) ON DELETE RESTRICT,
  proposed_geom geometry(Geometry),
  status text NOT NULL DEFAULT 'shortlisted' CHECK (status IN (
    'discovered', 'shortlisted', 'matched', 'accepted', 'rejected', 'conflict', 'stale'
  )),
  existing_object_id uuid REFERENCES geo.spatial_objects(id) ON DELETE RESTRICT,
  canonical_object_id uuid REFERENCES geo.spatial_objects(id) ON DELETE RESTRICT,
  match_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  reviewer_note text,
  proposed_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  proposed_at timestamptz NOT NULL DEFAULT now(),
  reviewed_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  reviewed_at timestamptz,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (model_id, external_feature_id, target_class_id),
  CHECK (status NOT IN ('accepted', 'rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
  CHECK (status <> 'accepted' OR canonical_object_id IS NOT NULL),
  CHECK (status <> 'matched' OR existing_object_id IS NOT NULL)
);
CREATE INDEX object_candidates_model_status_idx ON provenance.object_candidates(model_id, status);
CREATE INDEX object_candidates_external_feature_idx ON provenance.object_candidates(external_feature_id);
CREATE INDEX object_candidates_geom_gist_idx ON provenance.object_candidates USING gist (proposed_geom);

ALTER TABLE rules.document_editions
  ADD COLUMN retrieved_at timestamptz,
  ADD COLUMN checked_at timestamptz,
  ADD COLUMN media_type text,
  ADD COLUMN access_policy text NOT NULL DEFAULT 'link_only' CHECK (access_policy IN (
    'redistributable', 'internal_copy', 'link_only', 'restricted', 'unknown'
  )),
  ADD COLUMN consolidated_through date,
  ADD COLUMN acquisition_note text;

CREATE TABLE rules.document_ingestion_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  edition_id uuid NOT NULL REFERENCES rules.document_editions(id) ON DELETE RESTRICT,
  processing_run_id uuid NOT NULL UNIQUE REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  extractor_name text NOT NULL,
  extractor_version text,
  ocr_used boolean NOT NULL DEFAULT false,
  page_count integer CHECK (page_count >= 0),
  extraction_config jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN (
    'queued', 'extracting', 'extracted', 'needs_review', 'failed'
  )),
  quality_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Segments follow legal structure, while source fragments retain page/bbox.
CREATE TABLE rules.document_segments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  edition_id uuid NOT NULL REFERENCES rules.document_editions(id) ON DELETE RESTRICT,
  ingestion_run_id uuid NOT NULL REFERENCES rules.document_ingestion_runs(id) ON DELETE RESTRICT,
  source_fragment_id uuid NOT NULL REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  parent_segment_id uuid REFERENCES rules.document_segments(id) ON DELETE RESTRICT,
  ordinal integer NOT NULL CHECK (ordinal > 0),
  segment_kind text NOT NULL CHECK (segment_kind IN (
    'title', 'section', 'clause', 'subclause', 'table', 'table_row', 'note', 'annex', 'other'
  )),
  locator text NOT NULL,
  heading text,
  normalized_text text NOT NULL,
  extraction_confidence numeric(4,3) CHECK (extraction_confidence BETWEEN 0 AND 1),
  search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector('russian', coalesce(heading, '') || ' ' || normalized_text)
  ) STORED,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (ingestion_run_id, ordinal),
  UNIQUE (edition_id, source_fragment_id)
);
CREATE INDEX document_segments_edition_locator_idx ON rules.document_segments(edition_id, locator);
CREATE INDEX document_segments_search_gin_idx ON rules.document_segments USING gin (search_vector);

-- LLM output remains non-executable until a reviewer accepts it into rules.rules.
CREATE TABLE rules.rule_candidates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id uuid NOT NULL REFERENCES rules.document_ingestion_runs(id) ON DELETE RESTRICT,
  segment_id uuid NOT NULL REFERENCES rules.document_segments(id) ON DELETE RESTRICT,
  proposed_provision_locator text NOT NULL,
  proposed_effect_type text NOT NULL CHECK (proposed_effect_type IN (
    'prohibit', 'minimum_clearance', 'allow', 'allow_with_conditions',
    'require_approval', 'require_review', 'informational'
  )),
  proposed_geometry_operator text NOT NULL CHECK (proposed_geometry_operator IN (
    'buffer_centerline', 'buffer_footprint', 'inside', 'outside', 'no_overlap',
    'vertical_clearance', 'custom_review'
  )),
  proposed_distance_m numeric CHECK (proposed_distance_m >= 0),
  proposed_comparison_operator text CHECK (proposed_comparison_operator IN ('>=', '>', '<=', '<', '=', 'between')),
  proposed_conditions jsonb NOT NULL DEFAULT '{}'::jsonb,
  proposed_subject_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
  proposed_object_class_codes text[] NOT NULL DEFAULT ARRAY[]::text[],
  extraction_confidence numeric(4,3) NOT NULL CHECK (extraction_confidence BETWEEN 0 AND 1),
  validation_status text NOT NULL DEFAULT 'pending' CHECK (validation_status IN (
    'pending', 'valid', 'warning', 'invalid'
  )),
  validation_messages jsonb NOT NULL DEFAULT '[]'::jsonb,
  review_status text NOT NULL DEFAULT 'draft' CHECK (review_status IN (
    'draft', 'needs_review', 'accepted', 'rejected', 'superseded'
  )),
  accepted_rule_id uuid REFERENCES rules.rules(id) ON DELETE RESTRICT,
  reviewed_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  reviewed_at timestamptz,
  reviewer_note text,
  model_name text,
  model_version text,
  prompt_hash text,
  raw_output jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (review_status NOT IN ('accepted', 'rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
  CHECK (review_status <> 'accepted' OR accepted_rule_id IS NOT NULL)
);
CREATE INDEX rule_candidates_review_idx ON rules.rule_candidates(review_status, validation_status);
CREATE INDEX rule_candidates_segment_idx ON rules.rule_candidates(segment_id);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('005', 'OSM object review candidates and regulatory document ingestion');

COMMIT;
