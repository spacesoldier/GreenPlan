\set ON_ERROR_STOP on

BEGIN;

CREATE OR REPLACE FUNCTION audit.prevent_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit.events is append-only';
END;
$$;

CREATE TRIGGER audit_events_no_update
BEFORE UPDATE OR DELETE ON audit.events
FOR EACH ROW EXECUTE FUNCTION audit.prevent_mutation();

CREATE OR REPLACE FUNCTION catalog.assert_model_mutable(p_model_id uuid)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  model_status text;
BEGIN
  SELECT assembly_status INTO model_status
  FROM catalog.canonical_models
  WHERE id = p_model_id;

  IF model_status IS NULL THEN
    RAISE EXCEPTION 'canonical model % does not exist', p_model_id;
  END IF;

  IF model_status IN ('approved', 'retired') THEN
    RAISE EXCEPTION 'canonical model % is immutable in status %', p_model_id, model_status;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION geo.guard_spatial_object_model()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    PERFORM catalog.assert_model_mutable(OLD.model_id);
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    PERFORM catalog.assert_model_mutable(NEW.model_id);
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER spatial_objects_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.spatial_objects
FOR EACH ROW EXECUTE FUNCTION geo.guard_spatial_object_model();

CREATE OR REPLACE FUNCTION geo.guard_object_child_model()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  old_object_id uuid;
  new_object_id uuid;
  parent_model_id uuid;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    old_object_id := (to_jsonb(OLD)->>'object_id')::uuid;
    SELECT model_id INTO parent_model_id FROM geo.spatial_objects WHERE id = old_object_id;
    PERFORM catalog.assert_model_mutable(parent_model_id);
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    new_object_id := (to_jsonb(NEW)->>'object_id')::uuid;
    SELECT model_id INTO parent_model_id FROM geo.spatial_objects WHERE id = new_object_id;
    PERFORM catalog.assert_model_mutable(parent_model_id);
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER object_geometries_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.object_geometries
FOR EACH ROW EXECUTE FUNCTION geo.guard_object_child_model();
CREATE TRIGGER network_components_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.network_components
FOR EACH ROW EXECUTE FUNCTION geo.guard_object_child_model();
CREATE TRIGGER buildings_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.buildings
FOR EACH ROW EXECUTE FUNCTION geo.guard_object_child_model();
CREATE TRIGGER terrain_surfaces_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.terrain_surfaces
FOR EACH ROW EXECUTE FUNCTION geo.guard_object_child_model();
CREATE TRIGGER soil_units_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.soil_units
FOR EACH ROW EXECUTE FUNCTION geo.guard_object_child_model();
CREATE TRIGGER underground_obstacles_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.underground_obstacles
FOR EACH ROW EXECUTE FUNCTION geo.guard_object_child_model();
CREATE TRIGGER vegetation_objects_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.vegetation_objects
FOR EACH ROW EXECUTE FUNCTION geo.guard_object_child_model();

CREATE OR REPLACE FUNCTION geo.enforce_object_geometry_srid()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  expected_srid integer;
BEGIN
  SELECT cs.srid INTO expected_srid
  FROM geo.spatial_objects so
  JOIN catalog.canonical_models cm ON cm.id = so.model_id
  JOIN catalog.coordinate_spaces cs ON cs.id = cm.coordinate_space_id
  WHERE so.id = NEW.object_id;

  IF expected_srid IS NOT NULL AND ST_SRID(NEW.geom) <> expected_srid THEN
    RAISE EXCEPTION 'geometry SRID % does not match model SRID %', ST_SRID(NEW.geom), expected_srid;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER object_geometries_srid_check
BEFORE INSERT OR UPDATE OF object_id, geom ON geo.object_geometries
FOR EACH ROW EXECUTE FUNCTION geo.enforce_object_geometry_srid();

CREATE OR REPLACE FUNCTION planning.guard_proposal_acceptance()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.status IN ('accepted', 'published') AND OLD.status IS DISTINCT FROM NEW.status THEN
    IF NOT EXISTS (
      SELECT 1 FROM planning.decision_checks dc WHERE dc.proposal_id = NEW.id
    ) THEN
      RAISE EXCEPTION 'proposal % has no decision checks', NEW.id;
    END IF;

    IF EXISTS (
      SELECT 1
      FROM planning.decision_checks dc
      WHERE dc.proposal_id = NEW.id
        AND (dc.result = 'fail' OR (dc.result = 'unknown' AND dc.safety_critical))
    ) THEN
      RAISE EXCEPTION 'proposal % has failing or safety-critical unknown checks', NEW.id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER proposals_acceptance_gate
BEFORE UPDATE OF status ON planning.proposals
FOR EACH ROW EXECUTE FUNCTION planning.guard_proposal_acceptance();

CREATE VIEW api.model_objects AS
SELECT
  so.id,
  so.model_id,
  oc.code AS class_code,
  oc.path AS class_path,
  so.stable_key,
  so.name,
  so.lifecycle,
  so.semantic_status,
  so.confidence,
  og.role AS geometry_role,
  og.geom,
  og.accuracy_m,
  og.validity_status,
  so.properties
FROM geo.spatial_objects so
JOIN geo.object_classes oc ON oc.id = so.class_id
LEFT JOIN geo.object_geometries og ON og.object_id = so.id AND og.is_primary;

CREATE VIEW api.object_provenance AS
SELECT
  so.id AS object_id,
  oc.code AS class_code,
  oe.evidence_role,
  oe.attribute_name,
  oe.asserted_value,
  oe.method,
  oe.confidence,
  oe.decision,
  sf.id AS source_fragment_id,
  sa.id AS source_asset_id,
  sa.original_name,
  ef.id AS external_feature_id,
  ed.provider,
  ef.provider_type,
  ef.provider_id,
  oe.transform_id
FROM geo.spatial_objects so
JOIN geo.object_classes oc ON oc.id = so.class_id
JOIN provenance.object_evidence oe ON oe.object_id = so.id
LEFT JOIN provenance.source_fragments sf ON sf.id = oe.source_fragment_id
LEFT JOIN provenance.source_assets sa ON sa.id = sf.source_asset_id
LEFT JOIN provenance.external_features ef ON ef.id = oe.external_feature_id
LEFT JOIN provenance.external_datasets ed ON ed.id = ef.dataset_id;

CREATE VIEW api.plan_explanations AS
SELECT
  pr.id AS plan_revision_id,
  p.id AS proposal_id,
  p.stable_key,
  p.status AS proposal_status,
  p.plant_profile_id,
  dc.id AS check_id,
  dc.check_kind,
  dc.result,
  dc.safety_critical,
  dc.actual_value,
  dc.required_value,
  dc.unit,
  dc.actual_distance_m,
  dc.required_distance_m,
  r.code AS rule_code,
  pv.locator AS provision_locator,
  rd.code AS document_code,
  rd.title AS document_title,
  dc.source_object_id,
  dc.details
FROM planning.plan_revisions pr
JOIN planning.proposals p ON p.plan_revision_id = pr.id
LEFT JOIN planning.decision_checks dc ON dc.proposal_id = p.id
LEFT JOIN rules.rules r ON r.id = dc.rule_id
LEFT JOIN rules.provisions pv ON pv.id = r.provision_id
LEFT JOIN rules.document_editions de ON de.id = pv.edition_id
LEFT JOIN rules.regulatory_documents rd ON rd.id = de.document_id;

CREATE VIEW api.input_quality_issues AS
SELECT
  so.model_id,
  so.id AS object_id,
  oc.code AS class_code,
  so.semantic_status,
  so.confidence,
  'object_semantics'::text AS issue_kind
FROM geo.spatial_objects so
JOIN geo.object_classes oc ON oc.id = so.class_id
WHERE so.semantic_status = 'needs_review' OR oc.path <@ 'unknown'::ltree
UNION ALL
SELECT
  cm.id AS model_id,
  NULL::uuid AS object_id,
  NULL::text AS class_code,
  cs.status AS semantic_status,
  NULL::numeric AS confidence,
  'coordinate_space'::text AS issue_kind
FROM catalog.canonical_models cm
JOIN catalog.coordinate_spaces cs ON cs.id = cm.coordinate_space_id
WHERE cs.status <> 'verified';

INSERT INTO ops.schema_migrations(version, description)
VALUES ('0003', 'Integrity triggers and API views');

COMMIT;
