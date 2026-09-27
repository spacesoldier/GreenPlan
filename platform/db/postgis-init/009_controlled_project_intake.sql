\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS intake.project_workflows (
  revision_id uuid PRIMARY KEY REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  delivery_id uuid UNIQUE REFERENCES intake.deliveries(id) ON DELETE RESTRICT,
  state text NOT NULL DEFAULT 'draft' CHECK (state IN (
    'draft', 'receiving', 'inventoried', 'analyzing', 'review_required',
    'ready_to_publish', 'published', 'blocked', 'failed', 'retired'
  )),
  fidelity_verdict text CHECK (fidelity_verdict IN (
    'accepted', 'accepted_with_review', 'rejected', 'not_comparable'
  )),
  selected_master_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  last_run_id uuid REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  review_comment text,
  published_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (state <> 'published' OR published_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS intake.cad_inventories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  source_asset_id uuid NOT NULL REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  stage text NOT NULL CHECK (stage IN ('source', 'direct_reader', 'converted_dxf', 'uploaded_dxf')),
  format text NOT NULL CHECK (format IN ('dwg', 'dxf', 'unknown')),
  format_version text,
  parse_status text NOT NULL CHECK (parse_status IN ('pending', 'parsed', 'partial', 'failed', 'blocked')),
  tool_name text,
  tool_version text,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  artifact_locator text,
  fingerprint text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_asset_id, stage)
);
CREATE INDEX IF NOT EXISTS cad_inventories_revision_idx
  ON intake.cad_inventories(revision_id, stage);

CREATE TABLE IF NOT EXISTS intake.processing_stage_attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  source_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  processing_run_id uuid REFERENCES ops.processing_runs(id) ON DELETE RESTRICT,
  stage text NOT NULL,
  attempt_no integer NOT NULL DEFAULT 1 CHECK (attempt_no > 0),
  state text NOT NULL CHECK (state IN ('queued', 'running', 'completed', 'completed_with_warnings', 'failed', 'blocked', 'cancelled')),
  progress numeric(5,4) NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
  command jsonb NOT NULL DEFAULT '[]'::jsonb,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  stdout text NOT NULL DEFAULT '',
  stderr text NOT NULL DEFAULT '',
  error_summary text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz,
  UNIQUE (revision_id, source_asset_id, stage, attempt_no)
);
CREATE INDEX IF NOT EXISTS processing_stage_attempts_revision_idx
  ON intake.processing_stage_attempts(revision_id, created_at);

CREATE TABLE IF NOT EXISTS intake.fidelity_findings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  source_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  code text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  stage text NOT NULL,
  title text NOT NULL,
  detail text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'resolved', 'rejected')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fidelity_findings_revision_idx
  ON intake.fidelity_findings(revision_id, severity, status);

CREATE TABLE IF NOT EXISTS intake.master_candidates (
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  source_asset_id uuid NOT NULL REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  score numeric(6,3) NOT NULL,
  role text NOT NULL,
  cues jsonb NOT NULL DEFAULT '[]'::jsonb,
  selected boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (revision_id, source_asset_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS master_candidates_one_selected_idx
  ON intake.master_candidates(revision_id) WHERE selected;

CREATE TABLE IF NOT EXISTS intake.cad_spaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  inventory_id uuid NOT NULL REFERENCES intake.cad_inventories(id) ON DELETE CASCADE,
  name text NOT NULL,
  space_kind text NOT NULL CHECK (space_kind IN ('model', 'layout')),
  entity_count bigint NOT NULL DEFAULT 0 CHECK (entity_count >= 0),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (inventory_id, name)
);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('009', 'Controlled project intake, CAD inventories, stages and fidelity findings')
ON CONFLICT (version) DO NOTHING;

COMMIT;
