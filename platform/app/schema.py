SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id uuid PRIMARY KEY,
  dataset_path text NOT NULL UNIQUE,
  title text NOT NULL,
  structure jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_assets (
  id uuid PRIMARY KEY,
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  dataset_path text NOT NULL UNIQUE,
  media_kind text NOT NULL,
  role text NOT NULL,
  confidence numeric NOT NULL,
  cues jsonb NOT NULL DEFAULT '[]'::jsonb,
  size_bytes bigint,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS source_assets_project_id_idx ON source_assets(project_id);

CREATE TABLE IF NOT EXISTS conversion_jobs (
  id uuid PRIMARY KEY,
  project_id uuid NOT NULL REFERENCES projects(id),
  source_asset_id uuid REFERENCES source_assets(id),
  input_path text NOT NULL,
  input_sha256 text NOT NULL,
  state text NOT NULL CHECK (state IN ('queued', 'oda_running', 'libredwg_queued', 'libredwg_running', 'completed', 'completed_with_warnings', 'failed')),
  warning_count integer NOT NULL DEFAULT 0,
  error_summary text,
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS conversion_stages (
  id bigserial PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES conversion_jobs(id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS conversion_stages_job_id_idx ON conversion_stages(job_id);

CREATE TABLE IF NOT EXISTS conversion_artifacts (
  id bigserial PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES conversion_jobs(id) ON DELETE CASCADE,
  stage text NOT NULL,
  kind text NOT NULL,
  work_path text NOT NULL,
  sha256 text NOT NULL,
  size_bytes bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(job_id, work_path)
);

CREATE TABLE IF NOT EXISTS published_artifacts (
  id bigserial PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES conversion_jobs(id) ON DELETE CASCADE,
  publication text NOT NULL CHECK (publication IN ('dataset_dxf', 'portable_dxf')),
  target_path text NOT NULL,
  sha256 text NOT NULL,
  size_bytes bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(publication, target_path)
);
"""
