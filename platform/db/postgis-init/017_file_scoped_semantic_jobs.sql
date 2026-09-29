\set ON_ERROR_STOP on
BEGIN;
ALTER TABLE intake.semantic_suggestion_jobs
  ADD COLUMN IF NOT EXISTS scope text NOT NULL DEFAULT 'selected_document';
ALTER TABLE intake.semantic_suggestion_jobs
  DROP CONSTRAINT IF EXISTS semantic_suggestion_jobs_scope_check;
ALTER TABLE intake.semantic_suggestion_jobs
  ADD CONSTRAINT semantic_suggestion_jobs_scope_check CHECK (scope='selected_document');
INSERT INTO ops.schema_migrations(version,description)
VALUES ('017','Semantic layer suggestions are scoped to one selected CAD document')
ON CONFLICT (version) DO NOTHING;
COMMIT;
