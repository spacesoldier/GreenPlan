from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

import ezdxf
import psycopg
from psycopg.types.json import Jsonb

from .dxf_ingest import classify_layer, entity_to_geojson, iter_primitives


NAMESPACE = UUID("8f492100-88ae-4fd3-9133-a93da79b5dd0")


@dataclass(frozen=True)
class PilotSpec:
    code: str
    title: str
    directory: str
    primary_dxf: str


PILOTS = (
    PilotSpec(
        code="peschanaya",
        title="Песчаный переулок",
        directory="2. Песчаный переулок",
        primary_dxf="dxf/Проектное решение /DWG/ГР_Песчаный переулок.dxf",
    ),
    PilotSpec(
        code="kulikovskaya",
        title="Куликовская улица",
        directory="14. Куликовская улица",
        primary_dxf="dxf/Проектные решения/DWG/Генеральный план.dxf",
    ),
)


def stable_uuid(value: str) -> UUID:
    return uuid5(NAMESPACE, value)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def geometry_role(class_code: str, geometry_type: str, source_type: str | None = None) -> str:
    if class_code == "territory.work_boundary":
        return "boundary"
    if class_code == "structure.building":
        return "footprint"
    if class_code.startswith("utility.") or class_code.startswith("transport."):
        return "centerline" if geometry_type == "LineString" else "footprint"
    if class_code.startswith("vegetation."):
        if source_type == "CIRCLE":
            return "position"
        return "position" if geometry_type == "Point" else "crown"
    return "other"


def layer_caps(counts: Counter[str], max_total: int) -> dict[str, int]:
    if max_total <= 0 or max_total >= sum(counts.values()):
        return dict(counts)
    requested: dict[str, int] = {}
    for layer, count in counts.items():
        classification = classify_layer(layer)
        per_layer = 900 if classification.semantic_status != "needs_review" else 260
        requested[layer] = min(count, per_layer)
    requested_total = sum(requested.values())
    if requested_total <= max_total:
        return requested
    scale = max_total / requested_total
    caps = {layer: min(counts[layer], max(8, int(value * scale))) for layer, value in requested.items()}
    while sum(caps.values()) > max_total:
        candidate = max((name for name in caps if caps[name] > 8), key=lambda name: caps[name], default=None)
        if candidate is None:
            break
        caps[candidate] -= 1
    return caps


def selected_positions(count: int, limit: int) -> set[int]:
    if count <= limit:
        return set(range(count))
    if limit <= 1:
        return {0}
    return {round(index * (count - 1) / (limit - 1)) for index in range(limit)}


def ensure_catalog(connection: psycopg.Connection, spec: PilotSpec, primary_hash: str) -> dict[str, UUID]:
    ids = {
        "organization": stable_uuid("organization:moscow-dpp"),
        "workspace": stable_uuid("workspace:lct2026-pilots"),
        "project": stable_uuid(f"project:{spec.code}"),
        "revision": stable_uuid(f"revision:{spec.code}:{primary_hash}"),
        "territory": stable_uuid(f"territory:{spec.code}"),
        "coordinate": stable_uuid(f"coordinate:{spec.code}:cad-local"),
        "model": stable_uuid(f"model:{spec.code}:{primary_hash}:v1"),
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO core.organizations(id,code,name,organization_kind)
               VALUES (%s,'moscow-dpp','Департамент природопользования и охраны окружающей среды','customer')
               ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name""",
            (ids["organization"],),
        )
        cursor.execute(
            """INSERT INTO catalog.workspaces(id,code,title,customer_id,status)
               VALUES (%s,'lct2026-pilots','ЛЦТ 2026 — пилотные улицы',%s,'active')
               ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title,status=EXCLUDED.status""",
            (ids["workspace"], ids["organization"]),
        )
        cursor.execute(
            """INSERT INTO catalog.projects(id,workspace_id,code,title,status,properties)
               VALUES (%s,%s,%s,%s,'active',%s)
               ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title,status=EXCLUDED.status,properties=EXCLUDED.properties""",
            (ids["project"], ids["workspace"], spec.code, spec.title, Jsonb({"dataset_directory": spec.directory})),
        )
        cursor.execute(
            """INSERT INTO catalog.project_revisions(id,project_id,revision_no,content_fingerprint,status,notes)
               VALUES (%s,%s,1,%s,'interpreted','Imported from converted DXF pilot delivery')
               ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status,notes=EXCLUDED.notes""",
            (ids["revision"], ids["project"], primary_hash),
        )
        cursor.execute(
            """INSERT INTO catalog.territories(id,code,title,territory_kind,jurisdiction_code)
               VALUES (%s,%s,%s,'street','RU-MOW')
               ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title""",
            (ids["territory"], spec.code, spec.title),
        )
        cursor.execute(
            """INSERT INTO catalog.project_territories(project_id,territory_id,role)
               VALUES (%s,%s,'primary') ON CONFLICT DO NOTHING""",
            (ids["project"], ids["territory"]),
        )
        cursor.execute(
            """INSERT INTO catalog.coordinate_spaces(id,code,kind,linear_unit,status,axis_definition)
               VALUES (%s,%s,'cad_local','metre','candidate',%s)
               ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status,axis_definition=EXCLUDED.axis_definition""",
            (
                ids["coordinate"],
                f"{spec.code}-cad-local",
                Jsonb({"axis_order": "xy", "origin": "source_dxf", "warning": "EPSG is not asserted"}),
            ),
        )
        cursor.execute(
            """INSERT INTO catalog.canonical_models(
                   id,project_revision_id,territory_id,coordinate_space_id,model_kind,
                   version_no,assembly_status,dependency_completeness,semantic_coverage,properties)
               VALUES (%s,%s,%s,%s,'combined',1,'needs_review',0.650,0.000,%s)
               ON CONFLICT (id) DO UPDATE SET assembly_status='needs_review',properties=EXCLUDED.properties""",
            (
                ids["model"], ids["revision"], ids["territory"], ids["coordinate"],
                Jsonb({"importer": "greenplan-ezdxf", "primary_sha256": primary_hash}),
            ),
        )
    return ids


def reset_mutable_model(connection: psycopg.Connection, model_id: UUID, primary_asset_id: UUID) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """DELETE FROM provenance.object_evidence oe USING geo.spatial_objects so
               WHERE oe.object_id=so.id AND so.model_id=%s""",
            (model_id,),
        )
        cursor.execute(
            """DELETE FROM geo.object_geometries og USING geo.spatial_objects so
               WHERE og.object_id=so.id AND so.model_id=%s""",
            (model_id,),
        )
        cursor.execute("DELETE FROM geo.spatial_objects WHERE model_id=%s", (model_id,))
        cursor.execute(
            """DELETE FROM provenance.source_fragments
               WHERE source_asset_id=%s AND fragment_kind IN ('cad_layer','cad_entity')""",
            (primary_asset_id,),
        )


def register_assets(
    connection: psycopg.Connection, spec: PilotSpec, project_root: Path, revision_id: UUID, primary: Path
) -> UUID:
    primary_asset_id = stable_uuid(f"asset:{spec.code}:{primary.relative_to(project_root).as_posix()}")
    dxf_root = project_root / "dxf"
    files = sorted(
        path for path in dxf_root.rglob("*.dxf")
        if "_archives" not in path.relative_to(dxf_root).parts
    )
    with connection.cursor() as cursor:
        for path in files:
            relative = path.relative_to(project_root).as_posix()
            asset_id = stable_uuid(f"asset:{spec.code}:{relative}")
            is_primary = path == primary
            cursor.execute(
                """INSERT INTO provenance.source_assets(
                       id,project_revision_id,asset_kind,media_type,original_name,storage_locator,
                       sha256,size_bytes,availability_status,properties,scope_kind)
                   VALUES (%s,%s,'file','application/dxf',%s,%s,%s,%s,'available',%s,'project_revision')
                   ON CONFLICT (id) DO UPDATE SET storage_locator=EXCLUDED.storage_locator,
                       size_bytes=EXCLUDED.size_bytes,properties=EXCLUDED.properties""",
                (
                    asset_id, revision_id, path.name, relative,
                    file_sha256(path) if is_primary else None,
                    path.stat().st_size,
                    Jsonb({"primary_geometry_source": is_primary, "converted": True}),
                ),
            )
    return primary_asset_id


def ingest_geometry(
    connection: psycopg.Connection,
    spec: PilotSpec,
    primary: Path,
    ids: dict[str, UUID],
    primary_asset_id: UUID,
    max_entities: int,
    identity_scope: str | None = None,
    object_context: dict[str, Any] | None = None,
    refresh_derived: bool = True,
) -> dict[str, Any]:
    document = ezdxf.readfile(primary)
    scope_token = sha1(identity_scope.encode()).hexdigest()[:10] if identity_scope else ""
    context = dict(object_context or {})
    layer_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    for primitive in iter_primitives(document.modelspace()):
        layer_counts[primitive.effective_layer] += 1
        type_counts[primitive.entity.dxftype()] += 1

    caps = layer_caps(layer_counts, max_entities)
    targets = {layer: selected_positions(count, caps[layer]) for layer, count in layer_counts.items()}
    seen: Counter[str] = Counter()
    imported: Counter[str] = Counter()
    class_ids: dict[str, UUID] = {}
    with connection.cursor() as cursor:
        cursor.execute("SELECT code,id FROM geo.object_classes")
        class_ids = {
            (row["code"] if isinstance(row, dict) else row[0]):
            (row["id"] if isinstance(row, dict) else row[1])
            for row in cursor.fetchall()
        }

    object_rows = []
    geometry_rows = []
    fragment_rows = []
    evidence_rows = []
    primitive_index = 0
    for primitive in iter_primitives(document.modelspace()):
        layer = primitive.effective_layer
        position = seen[layer]
        seen[layer] += 1
        if position not in targets[layer]:
            primitive_index += 1
            continue
        geometry = entity_to_geojson(primitive.entity)
        if geometry is None:
            primitive_index += 1
            continue
        classification = classify_layer(layer)
        class_id = class_ids.get(classification.class_code) or class_ids["unknown.constraint"]
        handle = primitive.source_handle or f"virtual-{primitive_index}"
        identity = f"{spec.code}:{ids['model']}:{scope_token}:{handle}:{primitive_index}"
        object_id = stable_uuid(f"object:{identity}")
        geometry_id = stable_uuid(f"geometry:{identity}")
        fragment_id = stable_uuid(f"fragment:{identity}")
        evidence_id = stable_uuid(f"evidence:{identity}:classification")
        locator = {
            "layer": layer,
            "handle": handle,
            "primitive_index": primitive_index,
            "entity_type": primitive.entity.dxftype(),
        }
        locator_hash = sha1(json.dumps(locator, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        scene_layer_id = f"{classification.layer_id}-{scope_token}" if scope_token else classification.layer_id
        properties = {
            "layer_id": scene_layer_id,
            "source_layer": layer,
            "source_type": primitive.entity.dxftype(),
            "source_handle": handle,
            "classification_reason": classification.reason,
            "sampled": caps[layer] < layer_counts[layer],
            **context,
        }
        object_rows.append(
            (
                object_id, ids["model"], class_id, identity, layer,
                classification.semantic_status, classification.confidence, Jsonb(properties),
            )
        )
        geometry_rows.append(
            (
                geometry_id, object_id,
                geometry_role(classification.class_code, geometry["type"], primitive.entity.dxftype()),
                json.dumps(geometry, ensure_ascii=False), Jsonb({"source_entity_type": primitive.entity.dxftype()}),
            )
        )
        fragment_rows.append(
            (
                fragment_id, primary_asset_id, Jsonb(locator), locator_hash,
                Jsonb({"model_id": str(ids["model"]), "layer_id": scene_layer_id, **context}),
            )
        )
        evidence_rows.append(
            (
                evidence_id, object_id, fragment_id,
                Jsonb({"class_code": classification.class_code, "layer": layer}),
                classification.confidence,
            )
        )
        imported[layer] += 1
        primitive_index += 1

    with connection.cursor() as cursor:
        for layer, count in layer_counts.items():
            classification = classify_layer(layer)
            fragment_id = stable_uuid(f"layer-fragment:{spec.code}:{ids['model']}:{scope_token}:{layer}")
            locator = {"layer": layer, **({"publication_root": identity_scope} if identity_scope else {})}
            cursor.execute(
                """INSERT INTO provenance.source_fragments(
                       id,source_asset_id,fragment_kind,locator,locator_hash,properties)
                   VALUES (%s,%s,'cad_layer',%s,%s,%s) ON CONFLICT (id) DO UPDATE
                   SET properties=EXCLUDED.properties""",
                (
                    fragment_id, primary_asset_id, Jsonb(locator), sha1(layer.encode()).hexdigest(),
                    Jsonb({
                        "model_id": str(ids["model"]), "layer_id": (f"{classification.layer_id}-{scope_token}" if scope_token else classification.layer_id),
                        "class_code": classification.class_code, "semantic_status": classification.semantic_status,
                        "confidence": classification.confidence, "source_entity_count": count,
                        "imported_geometry_count": imported[layer],
                        **context,
                    }),
                ),
            )
        cursor.executemany(
            """INSERT INTO provenance.source_fragments(
                   id,source_asset_id,fragment_kind,locator,locator_hash,properties)
               VALUES (%s,%s,'cad_entity',%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
            fragment_rows,
        )
        cursor.executemany(
            """INSERT INTO geo.spatial_objects(
                   id,model_id,class_id,stable_key,name,semantic_status,confidence,properties)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET
                   class_id=EXCLUDED.class_id,name=EXCLUDED.name,semantic_status=EXCLUDED.semantic_status,
                   confidence=EXCLUDED.confidence,properties=EXCLUDED.properties""",
            object_rows,
        )
        cursor.executemany(
            """INSERT INTO geo.object_geometries(id,object_id,role,geom,is_primary,derivation_method,properties)
               VALUES (%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),0),true,'ezdxf-1.4.4',%s)
               ON CONFLICT (id) DO UPDATE SET geom=EXCLUDED.geom,properties=EXCLUDED.properties""",
            geometry_rows,
        )
        cursor.executemany(
            """INSERT INTO provenance.object_evidence(
                   id,object_id,source_fragment_id,evidence_role,attribute_name,asserted_value,
                   method,confidence,decision)
               VALUES (%s,%s,%s,'classification','semantic_class',%s,'layer_name_rule_v1',%s,'candidate')
               ON CONFLICT (id) DO NOTHING""",
            evidence_rows,
        )
        known = sum(value for layer, value in imported.items() if classify_layer(layer).semantic_status != "needs_review")
        total = sum(imported.values())
        cursor.execute(
            """UPDATE catalog.canonical_models SET semantic_coverage=%s, properties=properties || %s
               WHERE id=%s""",
            (
                (known / total) if total else 0,
                Jsonb({
                    "source_entity_count": sum(layer_counts.values()),
                    "imported_geometry_count": total,
                    "source_type_counts": dict(type_counts),
                    "primary_asset_id": str(primary_asset_id),
                    "dxf_version": document.dxfversion,
                }),
                ids["model"],
            ),
        )
        if refresh_derived:
            cursor.execute("SELECT geo.refresh_model_spatial_focus(%s)", (ids["model"],))
            cursor.execute("SELECT geo.refresh_model_render_assemblies(%s)", (ids["model"],))
    return {
        "source_entities": sum(layer_counts.values()),
        "imported_geometries": sum(imported.values()),
        "layers": len(layer_counts),
        "known_geometries": sum(value for layer, value in imported.items() if classify_layer(layer).semantic_status != "needs_review"),
    }


def import_pilot(
    connection: psycopg.Connection, dataset_root: Path, spec: PilotSpec, max_entities: int
) -> dict[str, Any]:
    project_root = dataset_root / spec.directory
    primary = project_root / spec.primary_dxf
    if not primary.is_file():
        raise FileNotFoundError(primary)
    primary_hash = file_sha256(primary)
    ids = ensure_catalog(connection, spec, primary_hash)
    primary_asset_id = register_assets(connection, spec, project_root, ids["revision"], primary)
    reset_mutable_model(connection, ids["model"], primary_asset_id)
    stats = ingest_geometry(connection, spec, primary, ids, primary_asset_id, max_entities)
    connection.commit()
    return {"code": spec.code, "model_id": str(ids["model"]), "primary": str(primary), **stats}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import real pilot DXF metadata and geometry")
    parser.add_argument("--database-url", default=os.getenv("GREENPLAN_DATABASE_URL"))
    parser.add_argument("--dataset-root", type=Path, default=Path(os.getenv("DATASET_ROOT", "/dataset/Пилотный проект 20 улиц")))
    parser.add_argument(
        "--max-entities",
        type=int,
        default=0,
        help="maximum primitives per project; 0 imports every supported primitive",
    )
    parser.add_argument("--project", choices=[item.code for item in PILOTS], action="append")
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("--database-url or GREENPLAN_DATABASE_URL is required")
    selected = [item for item in PILOTS if not args.project or item.code in args.project]
    results = []
    with psycopg.connect(args.database_url) as connection:
        for spec in selected:
            print(f"Importing {spec.title}...", flush=True)
            results.append(import_pilot(connection, args.dataset_root, spec, args.max_entities))
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
