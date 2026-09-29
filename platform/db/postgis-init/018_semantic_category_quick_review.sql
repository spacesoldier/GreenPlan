\set ON_ERROR_STOP on
BEGIN;

INSERT INTO intake.classification_labels(taxonomy_version,axis,code,title,definition)
VALUES (
  'cad-v2-sp42', 'object_class', 'utility.unknown',
  'Инженерные сети, тип не уточнён',
  'Канонический укрупнённый класс для слоя сети, точный вид которой пока не установлен'
)
ON CONFLICT (taxonomy_version,axis,code) DO UPDATE
SET title=EXCLUDED.title, definition=EXCLUDED.definition;

INSERT INTO ops.schema_migrations(version, description)
VALUES ('018', 'Grouped CAD category review and canonical layer-name auto-confirmation')
ON CONFLICT (version) DO NOTHING;

COMMIT;
