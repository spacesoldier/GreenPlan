\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE geo.model_spatial_focus (
  model_id uuid PRIMARY KEY REFERENCES catalog.canonical_models(id) ON DELETE CASCADE,
  focus_extent geometry(Polygon, 0) NOT NULL,
  focus_center geometry(Point, 0) NOT NULL,
  method text NOT NULL,
  algorithm_version text NOT NULL,
  object_count bigint NOT NULL CHECK (object_count > 0),
  total_object_count bigint NOT NULL CHECK (total_object_count >= object_count),
  coverage numeric(8,7) NOT NULL CHECK (coverage > 0 AND coverage <= 1),
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  computed_at timestamptz NOT NULL DEFAULT now(),
  CHECK (ST_SRID(focus_extent) = 0 AND ST_SRID(focus_center) = 0),
  CHECK (ST_Covers(focus_extent, focus_center))
);
CREATE INDEX model_spatial_focus_extent_gist_idx ON geo.model_spatial_focus USING gist (focus_extent);

CREATE OR REPLACE FUNCTION geo.refresh_model_spatial_focus(
  target_model_id uuid,
  epsilon double precision DEFAULT 25.0,
  minimum_points integer DEFAULT 8
)
RETURNS geo.model_spatial_focus
LANGUAGE plpgsql
AS $$
DECLARE
  winner record;
  stored geo.model_spatial_focus%ROWTYPE;
BEGIN
  IF epsilon <= 0 OR minimum_points < 1 THEN
    RAISE EXCEPTION 'invalid focus parameters: epsilon=%, minimum_points=%', epsilon, minimum_points;
  END IF;

  WITH anchors AS (
    SELECT so.id, ST_PointOnSurface(og.geom) AS anchor
    FROM geo.spatial_objects so
    JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
    WHERE so.model_id=target_model_id AND NOT ST_IsEmpty(og.geom)
  ),
  clustered AS (
    SELECT id, anchor,
           ST_ClusterDBSCAN(anchor, eps => epsilon, minpoints => minimum_points) OVER () AS cluster_id
    FROM anchors
  ),
  totals AS (
    SELECT count(*)::bigint AS total_count FROM anchors
  ),
  candidates AS (
    SELECT cluster_id, count(*)::bigint AS member_count,
           min(ST_X(anchor)) AS min_x, min(ST_Y(anchor)) AS min_y,
           max(ST_X(anchor)) AS max_x, max(ST_Y(anchor)) AS max_y
    FROM clustered
    WHERE cluster_id IS NOT NULL
    GROUP BY cluster_id
  )
  SELECT candidates.*, totals.total_count
  INTO winner
  FROM candidates CROSS JOIN totals
  ORDER BY member_count DESC, cluster_id
  LIMIT 1;

  IF winner IS NULL THEN
    SELECT NULL::integer AS cluster_id, count(*)::bigint AS member_count,
           min(ST_X(ST_PointOnSurface(og.geom))) AS min_x,
           min(ST_Y(ST_PointOnSurface(og.geom))) AS min_y,
           max(ST_X(ST_PointOnSurface(og.geom))) AS max_x,
           max(ST_Y(ST_PointOnSurface(og.geom))) AS max_y,
           count(*)::bigint AS total_count
    INTO winner
    FROM geo.spatial_objects so
    JOIN geo.object_geometries og ON og.object_id=so.id AND og.is_primary
    WHERE so.model_id=target_model_id AND NOT ST_IsEmpty(og.geom);
  END IF;

  IF winner.member_count = 0 THEN
    DELETE FROM geo.model_spatial_focus WHERE model_id=target_model_id;
    RETURN NULL;
  END IF;

  INSERT INTO geo.model_spatial_focus(
    model_id, focus_extent, focus_center, method, algorithm_version,
    object_count, total_object_count, coverage, parameters, computed_at
  ) VALUES (
    target_model_id,
    ST_MakeEnvelope(
      winner.min_x, winner.min_y,
      CASE WHEN winner.max_x > winner.min_x THEN winner.max_x ELSE winner.min_x + 0.001 END,
      CASE WHEN winner.max_y > winner.min_y THEN winner.max_y ELSE winner.min_y + 0.001 END,
      0
    ),
    ST_SetSRID(ST_MakePoint((winner.min_x + winner.max_x) / 2, (winner.min_y + winner.max_y) / 2), 0),
    CASE WHEN winner.cluster_id IS NULL THEN 'all_anchor_extent_fallback' ELSE 'dbscan_largest_anchor_cluster' END,
    '1',
    winner.member_count,
    winner.total_count,
    winner.member_count::numeric / winner.total_count,
    jsonb_build_object('epsilon', epsilon, 'minimum_points', minimum_points, 'anchor', 'point_on_surface'),
    now()
  )
  ON CONFLICT (model_id) DO UPDATE SET
    focus_extent=EXCLUDED.focus_extent,
    focus_center=EXCLUDED.focus_center,
    method=EXCLUDED.method,
    algorithm_version=EXCLUDED.algorithm_version,
    object_count=EXCLUDED.object_count,
    total_object_count=EXCLUDED.total_object_count,
    coverage=EXCLUDED.coverage,
    parameters=EXCLUDED.parameters,
    computed_at=EXCLUDED.computed_at
  RETURNING * INTO stored;

  RETURN stored;
END;
$$;

-- A simple vegetation circle is the position marker. Detailed polylines and
-- splines remain crowns and are therefore rendered above it.
UPDATE geo.object_geometries og
SET role='position'
FROM geo.spatial_objects so
JOIN geo.object_classes oc ON oc.id=so.class_id
WHERE og.object_id=so.id
  AND oc.code LIKE 'vegetation.%'
  AND og.properties->>'source_entity_type'='CIRCLE';

SELECT geo.refresh_model_spatial_focus(id)
FROM catalog.canonical_models
WHERE EXISTS (SELECT 1 FROM geo.spatial_objects so WHERE so.model_id=canonical_models.id);

INSERT INTO ops.schema_migrations(version, description)
VALUES ('006', 'Persisted primary spatial focus and vegetation position marker roles');

COMMIT;
