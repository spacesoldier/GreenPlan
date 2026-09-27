\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS intake.classification_review_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id uuid NOT NULL REFERENCES catalog.projects(id) ON DELETE RESTRICT,
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  decision text NOT NULL CHECK (decision IN ('accept','reject','correct')),
  category text,
  suggestion_ids uuid[] NOT NULL CHECK (cardinality(suggestion_ids) > 0),
  taxonomy_version text,
  comment text,
  reviewer_id uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  fingerprint text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (revision_id, fingerprint)
);

ALTER TABLE intake.classification_reviews
  ADD COLUMN IF NOT EXISTS batch_id uuid REFERENCES intake.classification_review_batches(id) ON DELETE RESTRICT;

CREATE TABLE IF NOT EXISTS intake.finding_resolutions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  finding_id uuid NOT NULL REFERENCES intake.fidelity_findings(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES catalog.projects(id) ON DELETE RESTRICT,
  action text NOT NULL CHECK (action IN ('waive','reopen','block')),
  reason text NOT NULL,
  impact jsonb NOT NULL DEFAULT '{}'::jsonb,
  reviewer_id uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS finding_resolutions_finding_idx
  ON intake.finding_resolutions(finding_id, created_at DESC);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('013', 'CAD workbench batch classification review and finding resolutions')
ON CONFLICT (version) DO NOTHING;

COMMIT;
