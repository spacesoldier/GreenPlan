\set ON_ERROR_STOP on

BEGIN;

DROP INDEX IF EXISTS intake.master_candidates_one_selected_idx;

CREATE TABLE IF NOT EXISTS intake.publication_roots (
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  source_asset_id uuid NOT NULL REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  root_role text NOT NULL CHECK (root_role IN ('effective_design', 'reference_context', 'historical')),
  position integer NOT NULL DEFAULT 0 CHECK (position >= 0),
  closure_fingerprint text,
  selected_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (revision_id, source_asset_id)
);
CREATE INDEX IF NOT EXISTS publication_roots_revision_position_idx
  ON intake.publication_roots(revision_id, position, source_asset_id);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('019', 'Multi-root publication selection and XREF closure manifests')
ON CONFLICT (version) DO NOTHING;

COMMIT;
