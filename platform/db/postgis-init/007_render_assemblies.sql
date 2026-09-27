\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE geo.render_assemblies (
  id uuid PRIMARY KEY REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  model_id uuid NOT NULL REFERENCES catalog.canonical_models(id) ON DELETE CASCADE,
  class_id uuid NOT NULL REFERENCES geo.object_classes(id) ON DELETE RESTRICT,
  layer_id text NOT NULL,
  source_handle text NOT NULL,
  geometry_role text NOT NULL DEFAULT 'assembly',
  geom geometry(Geometry, 0) NOT NULL,
  member_count integer NOT NULL CHECK (member_count > 0),
  algorithm_version text NOT NULL,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  computed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (model_id, class_id, layer_id, source_handle),
  CHECK (ST_SRID(geom) = 0),
  CHECK (NOT ST_IsEmpty(geom))
);
CREATE INDEX render_assemblies_model_idx ON geo.render_assemblies(model_id);
CREATE INDEX render_assemblies_geom_gist_idx ON geo.render_assemblies USING gist(geom);

CREATE TABLE geo.render_assembly_members (
  assembly_id uuid NOT NULL REFERENCES geo.render_assemblies(id) ON DELETE CASCADE,
  object_id uuid NOT NULL UNIQUE REFERENCES geo.spatial_objects(id) ON DELETE CASCADE,
  ordinal integer NOT NULL CHECK (ordinal > 0),
  geometry_role text NOT NULL,
  PRIMARY KEY (assembly_id, object_id),
  UNIQUE (assembly_id, ordinal)
);
CREATE INDEX render_assembly_members_object_idx ON geo.render_assembly_members(object_id);

CREATE OR REPLACE FUNCTION geo.refresh_model_render_assemblies(target_model_id uuid)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
  result_count integer;
BEGIN
  DELETE FROM geo.render_assemblies WHERE model_id=target_model_id;

  WITH candidates AS (
    SELECT so.id, so.model_id, so.class_id, so.stable_key,
           so.properties->>'layer_id' AS layer_id,
           COALESCE(so.properties->>'source_handle', source.source_handle) AS source_handle,
           og.role, og.geom
    FROM geo.spatial_objects so
    JOIN geo.object_classes oc ON oc.id=so.class_id
    JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
    LEFT JOIN LATERAL (
      SELECT sf.locator->>'handle' AS source_handle
      FROM provenance.object_evidence oe
      JOIN provenance.source_fragments sf ON sf.id=oe.source_fragment_id
      WHERE oe.object_id=so.id AND sf.locator ? 'handle'
      ORDER BY oe.created_at, oe.id
      LIMIT 1
    ) source ON true
    WHERE so.model_id=target_model_id
      AND oc.code LIKE 'vegetation.%'
      AND COALESCE(so.properties->>'source_handle', source.source_handle) IS NOT NULL
      AND NOT ST_IsEmpty(og.geom)
  ),
  grouped AS (
    SELECT (array_agg(id ORDER BY stable_key, id))[1] AS representative_id,
           model_id, class_id, layer_id, source_handle,
           ST_Collect(geom ORDER BY
             CASE role WHEN 'position' THEN 0 WHEN 'crown' THEN 2 ELSE 1 END,
             stable_key, id
           ) AS geom,
           count(*)::integer AS member_count
    FROM candidates
    GROUP BY model_id, class_id, layer_id, source_handle
  )
  INSERT INTO geo.render_assemblies(
    id, model_id, class_id, layer_id, source_handle, geometry_role,
    geom, member_count, algorithm_version, properties
  )
  SELECT representative_id, model_id, class_id, layer_id, source_handle, 'assembly',
         geom, member_count, '1',
         jsonb_build_object(
           'render_assembly', true,
           'member_count', member_count,
           'source_handle', source_handle,
           'assembly_algorithm_version', '1'
         )
  FROM grouped;

  WITH candidates AS (
    SELECT so.id, so.model_id, so.class_id, so.stable_key,
           so.properties->>'layer_id' AS layer_id,
           COALESCE(so.properties->>'source_handle', source.source_handle) AS source_handle,
           og.role
    FROM geo.spatial_objects so
    JOIN geo.object_classes oc ON oc.id=so.class_id
    JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
    LEFT JOIN LATERAL (
      SELECT sf.locator->>'handle' AS source_handle
      FROM provenance.object_evidence oe
      JOIN provenance.source_fragments sf ON sf.id=oe.source_fragment_id
      WHERE oe.object_id=so.id AND sf.locator ? 'handle'
      ORDER BY oe.created_at, oe.id
      LIMIT 1
    ) source ON true
    WHERE so.model_id=target_model_id
      AND oc.code LIKE 'vegetation.%'
      AND COALESCE(so.properties->>'source_handle', source.source_handle) IS NOT NULL
      AND NOT ST_IsEmpty(og.geom)
  ),
  ordered AS (
    SELECT candidates.*,
           row_number() OVER (
             PARTITION BY model_id, class_id, layer_id, source_handle
             ORDER BY CASE role WHEN 'position' THEN 0 WHEN 'crown' THEN 2 ELSE 1 END,
                      stable_key, id
           )::integer AS ordinal
    FROM candidates
  )
  INSERT INTO geo.render_assembly_members(assembly_id, object_id, ordinal, geometry_role)
  SELECT ra.id, ordered.id, ordered.ordinal, ordered.role
  FROM ordered
  JOIN geo.render_assemblies ra
    ON ra.model_id=ordered.model_id
   AND ra.class_id=ordered.class_id
   AND ra.layer_id=ordered.layer_id
   AND ra.source_handle=ordered.source_handle;

  SELECT count(*) INTO result_count
  FROM geo.render_assemblies WHERE model_id=target_model_id;
  RETURN result_count;
END;
$$;

SELECT id AS model_id, geo.refresh_model_render_assemblies(id) AS assembly_count
FROM catalog.canonical_models
WHERE EXISTS (SELECT 1 FROM geo.spatial_objects so WHERE so.model_id=canonical_models.id);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('007', 'Derived CAD render assemblies with canonical membership');

COMMIT;
