\set ON_ERROR_STOP on

BEGIN;

-- These codes are valid CAD review outcomes, so they must also resolve to
-- canonical geo.object_classes when an engineer confirms a layer.
INSERT INTO geo.object_classes(id, code, path, parent_id, title, is_constraint_source)
SELECT
  '21000000-0000-0000-0000-000000000014',
  'utility.unknown',
  'utility.unknown',
  parent.id,
  'Инженерная сеть неуточнённого типа',
  true
FROM geo.object_classes parent
WHERE parent.code = 'utility'
ON CONFLICT (code) DO NOTHING;

INSERT INTO geo.object_classes(id, code, path, parent_id, title, is_constraint_source)
VALUES ('20000000-0000-0000-0000-000000000009', 'terrain', 'terrain', NULL, 'Рельеф', true)
ON CONFLICT (code) DO NOTHING;

UPDATE intake.cad_layers layer
SET candidate_class_id = object_class.id
FROM geo.object_classes object_class
WHERE layer.mapping_status = 'confirmed'
  AND layer.properties->>'reviewed_class_code' = object_class.code
  AND layer.candidate_class_id IS DISTINCT FROM object_class.id;

INSERT INTO ops.schema_migrations(version, description)
VALUES ('015', 'Align CAD review outcomes with canonical object classes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
