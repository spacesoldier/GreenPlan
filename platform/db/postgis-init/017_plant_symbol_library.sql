\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE biology.cad_symbol_libraries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL,
  title text NOT NULL,
  source_asset_id uuid NOT NULL REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  diagnostic_asset_id uuid REFERENCES provenance.source_assets(id) ON DELETE RESTRICT,
  content_fingerprint text NOT NULL UNIQUE,
  importer_name text NOT NULL,
  importer_version text NOT NULL,
  drawing_version text,
  drawing_units text NOT NULL DEFAULT 'unknown',
  status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'needs_review', 'approved', 'retired', 'failed')),
  layer_count integer NOT NULL DEFAULT 0 CHECK (layer_count >= 0),
  block_count integer NOT NULL DEFAULT 0 CHECK (block_count >= 0),
  symbol_count integer NOT NULL DEFAULT 0 CHECK (symbol_count >= 0),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (code, content_fingerprint)
);

CREATE TABLE biology.plant_symbols (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  library_id uuid NOT NULL REFERENCES biology.cad_symbol_libraries(id) ON DELETE CASCADE,
  source_fragment_id uuid NOT NULL REFERENCES provenance.source_fragments(id) ON DELETE RESTRICT,
  source_block_name text NOT NULL,
  normalized_name text NOT NULL,
  block_record_handle text,
  candidate_kind text NOT NULL DEFAULT 'plant' CHECK (candidate_kind IN ('plant', 'generic_vegetation', 'service', 'unknown')),
  instance_count integer NOT NULL DEFAULT 0 CHECK (instance_count >= 0),
  entity_count integer NOT NULL DEFAULT 0 CHECK (entity_count >= 0),
  base_point jsonb NOT NULL DEFAULT '{}'::jsonb,
  extents jsonb NOT NULL DEFAULT '{}'::jsonb,
  entity_types jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_layers jsonb NOT NULL DEFAULT '[]'::jsonb,
  style_summary jsonb NOT NULL DEFAULT '[]'::jsonb,
  hatch_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  nested_blocks jsonb NOT NULL DEFAULT '[]'::jsonb,
  attribute_schema jsonb NOT NULL DEFAULT '[]'::jsonb,
  attribute_examples jsonb NOT NULL DEFAULT '[]'::jsonb,
  geometry_locator jsonb NOT NULL DEFAULT '{}'::jsonb,
  preview_status text NOT NULL DEFAULT 'pending' CHECK (preview_status IN ('pending', 'ready', 'too_complex', 'failed')),
  preview_locator text,
  review_status text NOT NULL DEFAULT 'needs_review' CHECK (review_status IN ('draft', 'needs_review', 'approved', 'rejected', 'retired')),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (library_id, source_block_name)
);
CREATE INDEX plant_symbols_library_review_idx ON biology.plant_symbols(library_id, review_status);
CREATE INDEX plant_symbols_normalized_name_idx ON biology.plant_symbols(normalized_name);

CREATE TABLE biology.plant_symbol_profile_links (
  symbol_id uuid NOT NULL REFERENCES biology.plant_symbols(id) ON DELETE CASCADE,
  plant_profile_id uuid NOT NULL REFERENCES biology.plant_profiles(id) ON DELETE RESTRICT,
  decision text NOT NULL DEFAULT 'candidate' CHECK (decision IN ('candidate', 'accepted', 'rejected', 'superseded')),
  method text NOT NULL,
  confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  reviewed_by uuid REFERENCES core.actors(id) ON DELETE RESTRICT,
  reviewed_at timestamptz,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol_id, plant_profile_id),
  CHECK (decision NOT IN ('accepted', 'rejected') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('017', 'Versioned CAD plant symbol libraries and reviewed plant profile links')
ON CONFLICT (version) DO NOTHING;

COMMIT;
