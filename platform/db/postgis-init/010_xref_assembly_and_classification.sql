\set ON_ERROR_STOP on

BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS cad_xrefs_definition_uq
  ON intake.cad_xrefs(cad_document_id, reference_name, COALESCE(original_path, ''));

CREATE TABLE IF NOT EXISTS intake.classification_suggestions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  target_kind text NOT NULL CHECK (target_kind IN ('file', 'cad_layer', 'cad_block', 'cad_text')),
  target_key text NOT NULL,
  source_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  cad_layer_id uuid REFERENCES intake.cad_layers(id) ON DELETE CASCADE,
  suggested_category text NOT NULL,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  method text NOT NULL,
  model_name text,
  model_version text,
  input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  cues jsonb NOT NULL DEFAULT '[]'::jsonb,
  alternatives jsonb NOT NULL DEFAULT '[]'::jsonb,
  review_status text NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'accepted', 'rejected', 'superseded')),
  reviewed_category text,
  reviewer_id uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  review_comment text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (revision_id, target_kind, target_key, method)
);
CREATE INDEX IF NOT EXISTS classification_suggestions_revision_idx
  ON intake.classification_suggestions(revision_id, target_kind, review_status);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('010', 'Resolved XREF assembly metadata and reviewable file/layer classification suggestions')
ON CONFLICT (version) DO NOTHING;

COMMIT;
