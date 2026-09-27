\set ON_ERROR_STOP on

BEGIN;

CREATE OR REPLACE FUNCTION catalog.guard_canonical_model_record()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' AND OLD.assembly_status IN ('approved', 'retired') THEN
    RAISE EXCEPTION 'canonical model % is immutable in status %', OLD.id, OLD.assembly_status;
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.assembly_status IN ('approved', 'retired') THEN
    IF OLD.assembly_status = 'approved'
       AND NEW.assembly_status = 'retired'
       AND (to_jsonb(NEW) - 'assembly_status') = (to_jsonb(OLD) - 'assembly_status') THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION 'canonical model % is immutable in status %', OLD.id, OLD.assembly_status;
  END IF;

  RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER canonical_models_immutable_after_approval
BEFORE UPDATE OR DELETE ON catalog.canonical_models
FOR EACH ROW EXECUTE FUNCTION catalog.guard_canonical_model_record();

CREATE OR REPLACE FUNCTION catalog.guard_model_dependency()
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

CREATE TRIGGER model_dependencies_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON catalog.model_dependencies
FOR EACH ROW EXECUTE FUNCTION catalog.guard_model_dependency();

CREATE OR REPLACE FUNCTION geo.guard_model_owned_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  old_model_id uuid;
  new_model_id uuid;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    old_model_id := (to_jsonb(OLD)->>'model_id')::uuid;
    PERFORM catalog.assert_model_mutable(old_model_id);
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    new_model_id := (to_jsonb(NEW)->>'model_id')::uuid;
    PERFORM catalog.assert_model_mutable(new_model_id);
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER network_systems_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.network_systems
FOR EACH ROW EXECUTE FUNCTION geo.guard_model_owned_row();
CREATE TRIGGER groundwater_observations_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.groundwater_observations
FOR EACH ROW EXECUTE FUNCTION geo.guard_model_owned_row();

CREATE OR REPLACE FUNCTION geo.guard_object_relation_model()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  parent_model_id uuid;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    SELECT model_id INTO parent_model_id FROM geo.spatial_objects WHERE id = OLD.subject_object_id;
    PERFORM catalog.assert_model_mutable(parent_model_id);
    SELECT model_id INTO parent_model_id FROM geo.spatial_objects WHERE id = OLD.object_object_id;
    PERFORM catalog.assert_model_mutable(parent_model_id);
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    SELECT model_id INTO parent_model_id FROM geo.spatial_objects WHERE id = NEW.subject_object_id;
    PERFORM catalog.assert_model_mutable(parent_model_id);
    SELECT model_id INTO parent_model_id FROM geo.spatial_objects WHERE id = NEW.object_object_id;
    PERFORM catalog.assert_model_mutable(parent_model_id);
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER object_relations_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.object_relations
FOR EACH ROW EXECUTE FUNCTION geo.guard_object_relation_model();

CREATE OR REPLACE FUNCTION geo.guard_soil_horizon_model()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  soil_object_id uuid;
  parent_model_id uuid;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    soil_object_id := OLD.soil_unit_object_id;
    SELECT model_id INTO parent_model_id FROM geo.spatial_objects WHERE id = soil_object_id;
    PERFORM catalog.assert_model_mutable(parent_model_id);
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    soil_object_id := NEW.soil_unit_object_id;
    SELECT model_id INTO parent_model_id FROM geo.spatial_objects WHERE id = soil_object_id;
    PERFORM catalog.assert_model_mutable(parent_model_id);
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER soil_horizons_model_mutable
BEFORE INSERT OR UPDATE OR DELETE ON geo.soil_horizons
FOR EACH ROW EXECUTE FUNCTION geo.guard_soil_horizon_model();

INSERT INTO ops.schema_migrations(version, description)
VALUES ('0004', 'Complete canonical model immutability guards');

COMMIT;
