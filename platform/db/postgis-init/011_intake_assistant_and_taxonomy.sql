\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS intake.classification_taxonomies (
  version text PRIMARY KEY,
  title text NOT NULL,
  schema jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('draft', 'active', 'retired')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intake.classification_labels (
  taxonomy_version text NOT NULL REFERENCES intake.classification_taxonomies(version) ON DELETE RESTRICT,
  axis text NOT NULL CHECK (axis IN ('domain', 'lifecycle', 'representation', 'object_class', 'document_role')),
  code text NOT NULL,
  title text NOT NULL,
  definition text NOT NULL DEFAULT '',
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (taxonomy_version, axis, code)
);

INSERT INTO intake.classification_taxonomies(version,title,schema,status)
VALUES (
  'cad-v1',
  'GreenPlan CAD multi-axis taxonomy v1',
  '{"axes":["domain","lifecycle","representation","object_class","document_role"],"allow_unknown":true,"allow_not_applicable":true}'::jsonb,
  'active'
)
ON CONFLICT (version) DO NOTHING;

INSERT INTO intake.classification_labels(taxonomy_version,axis,code,title)
SELECT 'cad-v1', value.axis, value.code, value.title
FROM (VALUES
  ('domain','vegetation','Растительность'), ('domain','transport','Транспорт'),
  ('domain','utility','Инженерные сети'), ('domain','building','Здания'),
  ('domain','terrain','Рельеф'), ('domain','boundary','Границы'),
  ('domain','protection_zone','Охранные зоны'), ('domain','annotation','Аннотации'),
  ('domain','mixed','Смешанный слой'), ('domain','unknown','Не определено'),
  ('lifecycle','existing','Существующее'), ('lifecycle','proposed','Проектируемое'),
  ('lifecycle','demolition','Демонтаж'), ('lifecycle','replacement','Замена'),
  ('lifecycle','reference','Справочное'), ('lifecycle','mixed','Смешанный слой'),
  ('lifecycle','unknown','Не определено'),
  ('representation','point','Точка'), ('representation','centerline','Осевая линия'),
  ('representation','footprint','Контур'), ('representation','crown','Крона'),
  ('representation','hatch','Заливка'), ('representation','symbol','Условный знак'),
  ('representation','text','Текст'), ('representation','dimension','Размер'),
  ('representation','legend','Легенда'), ('representation','sheet_frame','Штамп или рамка'),
  ('representation','construction','Вспомогательная графика'),
  ('representation','mixed','Смешанный слой'), ('representation','unknown','Не определено'),
  ('object_class','unknown','Не определено'), ('object_class','not_applicable','Неприменимо'),
  ('document_role','survey','Обследование'), ('document_role','general_plan','Генеральный план'),
  ('document_role','dendroplan','Дендроплан'), ('document_role','source_base','Исходная подоснова'),
  ('document_role','xref','Внешняя ссылка'), ('document_role','printable_sheet','Печатный лист'),
  ('document_role','unknown','Не определено'), ('document_role','not_applicable','Неприменимо')
) AS value(axis,code,title)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS intake.feature_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  source_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  target_kind text NOT NULL,
  target_key text NOT NULL,
  schema_version text NOT NULL,
  fingerprint text NOT NULL,
  features jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (revision_id, target_kind, target_key, schema_version, fingerprint)
);

ALTER TABLE intake.classification_suggestions
  ADD COLUMN IF NOT EXISTS taxonomy_version text REFERENCES intake.classification_taxonomies(version) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS axis_results jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS feature_snapshot_id uuid REFERENCES intake.feature_snapshots(id) ON DELETE RESTRICT,
  ADD COLUMN IF NOT EXISTS provider_run jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Keep reviewed history intact, but remove obsolete flat layer suggestions from the active queue.
UPDATE intake.classification_suggestions
SET review_status='superseded'
WHERE target_kind='cad_layer'
  AND method<>'multi-axis-rules-v2'
  AND review_status='pending';

CREATE TABLE IF NOT EXISTS intake.classification_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  suggestion_id uuid NOT NULL REFERENCES intake.classification_suggestions(id) ON DELETE RESTRICT,
  project_id uuid NOT NULL REFERENCES catalog.projects(id) ON DELETE RESTRICT,
  decision text NOT NULL CHECK (decision IN ('accept', 'reject', 'correct')),
  axis_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  scope text NOT NULL DEFAULT 'project' CHECK (scope IN ('file', 'project', 'contractor', 'global')),
  comment text,
  reviewer_id uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS classification_reviews_suggestion_idx
  ON intake.classification_reviews(suggestion_id, created_at);

CREATE TABLE IF NOT EXISTS intake.assistant_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  revision_id uuid NOT NULL REFERENCES catalog.project_revisions(id) ON DELETE RESTRICT,
  input_fingerprint text NOT NULL,
  schema_version text NOT NULL,
  taxonomy_version text NOT NULL REFERENCES intake.classification_taxonomies(version) ON DELETE RESTRICT,
  provider_version text NOT NULL,
  state text NOT NULL CHECK (state IN (
    'queued','running','review_required','completed','blocked','failed','cancelled'
  )),
  progress numeric(5,4) NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
  cancel_requested boolean NOT NULL DEFAULT false,
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_summary text,
  started_at timestamptz,
  heartbeat_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (revision_id, input_fingerprint)
);
CREATE INDEX IF NOT EXISTS assistant_runs_revision_idx
  ON intake.assistant_runs(revision_id, created_at DESC);

CREATE TABLE IF NOT EXISTS intake.assistant_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES intake.assistant_runs(id) ON DELETE CASCADE,
  task_key text NOT NULL,
  title text NOT NULL,
  position integer NOT NULL CHECK (position >= 0),
  state text NOT NULL CHECK (state IN (
    'pending','running','completed','completed_with_warnings','blocked','failed','cancelled'
  )),
  dependencies text[] NOT NULL DEFAULT '{}',
  input_fingerprint text NOT NULL,
  output_fingerprint text,
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  progress numeric(5,4) NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 1),
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_summary text,
  started_at timestamptz,
  heartbeat_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, task_key)
);
CREATE INDEX IF NOT EXISTS assistant_tasks_run_idx
  ON intake.assistant_tasks(run_id, position);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('011', 'Persistent intake assistant runs, typed task DAG, feature snapshots and multi-axis taxonomy')
ON CONFLICT (version) DO NOTHING;

COMMIT;
