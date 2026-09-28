\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS intake.semantic_suggestion_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES catalog.projects(id) ON DELETE RESTRICT,
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  source_asset_id uuid NOT NULL REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  provider text NOT NULL,
  model text NOT NULL,
  input_fingerprint text NOT NULL,
  state text NOT NULL CHECK (state IN ('queued','running','completed','completed_with_warnings','failed','cancelled')),
  total_count integer NOT NULL DEFAULT 0,
  completed_count integer NOT NULL DEFAULT 0,
  failed_count integer NOT NULL DEFAULT 0,
  error_summary text,
  started_at timestamptz,
  heartbeat_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS semantic_suggestion_jobs_project_idx
  ON intake.semantic_suggestion_jobs(project_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS semantic_suggestion_jobs_active_idx
  ON intake.semantic_suggestion_jobs(revision_id, source_asset_id, provider, model)
  WHERE state IN ('queued','running');

INSERT INTO ops.schema_migrations(version, description)
VALUES ('014', 'Background semantic suggestion jobs for CAD layers')
ON CONFLICT (version) DO NOTHING;

COMMIT;
