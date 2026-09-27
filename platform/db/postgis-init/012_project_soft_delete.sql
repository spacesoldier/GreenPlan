\set ON_ERROR_STOP on

BEGIN;

ALTER TABLE catalog.projects
  ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
  ADD COLUMN IF NOT EXISTS deletion_reason text;

ALTER TABLE catalog.projects
  DROP CONSTRAINT IF EXISTS projects_workspace_id_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS projects_workspace_code_active_uq
  ON catalog.projects(workspace_id, code)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS projects_deleted_at_idx
  ON catalog.projects(deleted_at)
  WHERE deleted_at IS NOT NULL;

INSERT INTO ops.schema_migrations(version, description)
VALUES ('012', 'Reversible project soft delete and reusable project codes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
