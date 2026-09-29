from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid5

import ezdxf
from ezdxf import bbox
import psycopg
from psycopg.types.json import Jsonb


IMPORTER_NAME = "greenplan-ezdxf-plant-symbols"
IMPORTER_VERSION = "1"
NAMESPACE = UUID("a7d7aafd-b8d7-4fe9-b598-bfe864eff3e7")
SERVICE_NAME = re.compile(r"^(?:A\$C[0-9A-F]+|\*.+|[A-ZА-Я]?\d+)$", re.IGNORECASE)


def stable_uuid(value: str) -> UUID:
    return uuid5(NAMESPACE, value)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_name(value: str) -> str:
    value = value.replace("ё", "е").replace("Ё", "Е").replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip(" -")
    value = re.sub(r"\s+\d+$", "", value)
    return value.casefold()


def candidate_kind(name: str) -> str:
    normalized = normalize_name(name)
    if SERVICE_NAME.fullmatch(name) or len(normalized) <= 2:
        return "service"
    if normalized.startswith(("дерево ", "куст ")) or normalized in {"дерево", "куст"}:
        return "generic_vegetation"
    if re.search(r"[а-я]", normalized):
        return "plant"
    return "unknown"


def vector(value: Any) -> dict[str, float]:
    return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}


def extract_library_manifest(dxf_path: Path) -> dict[str, Any]:
    document = ezdxf.readfile(dxf_path)
    modelspace = document.modelspace()
    inserts = list(modelspace.query("INSERT"))
    instance_counts = Counter(entity.dxf.name for entity in inserts)
    instance_attributes: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entity in inserts:
        values = {attribute.dxf.tag: attribute.dxf.text for attribute in entity.attribs}
        if values and values not in instance_attributes[entity.dxf.name]:
            instance_attributes[entity.dxf.name].append(values)

    symbols: list[dict[str, Any]] = []
    for name in sorted(instance_counts, key=str.casefold):
        block = document.blocks.get(name)
        entities = list(block)
        type_counts = Counter(entity.dxftype() for entity in entities)
        layer_counts = Counter(entity.dxf.layer for entity in entities)
        styles = Counter(
            (
                entity.dxftype(),
                entity.dxf.layer,
                int(getattr(entity.dxf, "color", 256)),
                getattr(entity.dxf, "true_color", None),
                str(getattr(entity.dxf, "linetype", "BYLAYER")),
            )
            for entity in entities
        )
        hatch_patterns = Counter()
        boundary_paths = 0
        for entity in entities:
            if entity.dxftype() == "HATCH":
                hatch_patterns[(entity.dxf.pattern_name, bool(entity.dxf.solid_fill))] += 1
                boundary_paths += len(entity.paths)

        nested = Counter(entity.dxf.name for entity in block.query("INSERT"))
        attribute_schema = [
            {
                "tag": definition.dxf.tag,
                "default": definition.dxf.text,
                "prompt": getattr(definition.dxf, "prompt", ""),
            }
            for definition in block.query("ATTDEF")
        ]
        bounds = bbox.extents(block, fast=True)
        extents = {"min": vector(bounds.extmin), "max": vector(bounds.extmax)} if bounds.has_data else {}

        symbols.append(
            {
                "source_block_name": name,
                "normalized_name": normalize_name(name),
                "candidate_kind": candidate_kind(name),
                "block_record_handle": block.block_record_handle,
                "instance_count": instance_counts[name],
                "entity_count": len(entities),
                "base_point": vector(block.block.dxf.base_point),
                "extents": extents,
                "entity_types": dict(type_counts),
                "source_layers": [{"name": layer, "entity_count": count} for layer, count in layer_counts.most_common()],
                "style_summary": [
                    {
                        "entity_type": key[0], "layer": key[1], "aci_color": key[2],
                        "true_color": key[3], "linetype": key[4], "entity_count": count,
                    }
                    for key, count in styles.most_common()
                ],
                "hatch_summary": {
                    "count": sum(hatch_patterns.values()),
                    "boundary_path_count": boundary_paths,
                    "patterns": [
                        {"name": key[0], "solid": key[1], "count": count}
                        for key, count in hatch_patterns.most_common()
                    ],
                },
                "nested_blocks": [{"name": nested_name, "insert_count": count} for nested_name, count in nested.most_common()],
                "attribute_schema": attribute_schema,
                "attribute_examples": instance_attributes[name][:5],
                "geometry_locator": {"space": "BLOCKS", "block_record_handle": block.block_record_handle, "block_name": name},
            }
        )

    return {
        "drawing_version": document.dxfversion,
        "drawing_units": str(document.header.get("$INSUNITS", 0)),
        "layer_count": len(document.layers),
        "block_count": sum(1 for block in document.blocks if not block.name.startswith("*Paper_Space")),
        "model_entity_count": len(modelspace),
        "insert_count": len(inserts),
        "symbols": symbols,
    }


def _upsert_source(connection: psycopg.Connection, path: Path, digest: str, media_type: str, role: str) -> UUID:
    dataset_id = stable_uuid(f"external-dataset:{role}:{digest}")
    asset_id = stable_uuid(f"source-asset:{role}:{digest}")
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO provenance.external_datasets(
                 id,provider,dataset_name,media_type,sha256,size_bytes,importer_name,importer_version,status
               ) VALUES (%s,'greenplan-local-library',%s,%s,%s,%s,%s,%s,'imported')
               ON CONFLICT (provider,sha256) DO UPDATE SET
                 dataset_name=EXCLUDED.dataset_name,media_type=EXCLUDED.media_type,
                 size_bytes=EXCLUDED.size_bytes,importer_name=EXCLUDED.importer_name,
                 importer_version=EXCLUDED.importer_version,status='imported'
               RETURNING id""",
            (dataset_id, path.name, media_type, digest, path.stat().st_size, IMPORTER_NAME, IMPORTER_VERSION),
        )
        actual_dataset_id = cursor.fetchone()[0]
        cursor.execute(
            """INSERT INTO provenance.source_assets(
                 id,external_dataset_id,scope_kind,asset_kind,media_type,original_name,storage_locator,
                 sha256,size_bytes,availability_status,properties
               ) VALUES (%s,%s,'external_dataset','file',%s,%s,%s,%s,%s,'available',%s)
               ON CONFLICT (id) DO UPDATE SET
                 external_dataset_id=EXCLUDED.external_dataset_id,scope_kind='external_dataset',
                 storage_locator=EXCLUDED.storage_locator,
                 size_bytes=EXCLUDED.size_bytes,availability_status='available'
               RETURNING id""",
            (asset_id, actual_dataset_id, media_type, path.name, str(path), digest, path.stat().st_size, Jsonb({"library_role": role})),
        )
        return cursor.fetchone()[0]


def import_manifest(connection: psycopg.Connection, dwg_path: Path, dxf_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    dwg_hash = file_sha256(dwg_path)
    dxf_hash = file_sha256(dxf_path)
    fingerprint = sha256(f"{dwg_hash}:{dxf_hash}:{IMPORTER_NAME}:{IMPORTER_VERSION}".encode()).hexdigest()
    source_asset_id = _upsert_source(connection, dwg_path, dwg_hash, "application/acad", "canonical-dwg")
    diagnostic_asset_id = _upsert_source(connection, dxf_path, dxf_hash, "application/dxf", "diagnostic-dxf")
    library_id = stable_uuid(f"plant-symbol-library:{fingerprint}")
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO biology.cad_symbol_libraries(
                 id,code,title,source_asset_id,diagnostic_asset_id,content_fingerprint,
                 importer_name,importer_version,drawing_version,drawing_units,status,
                 layer_count,block_count,symbol_count,properties
               ) VALUES (%s,'greenplan-template-symbols','Шаблоны значков',%s,%s,%s,%s,%s,%s,%s,
                         'needs_review',%s,%s,%s,%s)
               ON CONFLICT (content_fingerprint) DO UPDATE SET
                 diagnostic_asset_id=EXCLUDED.diagnostic_asset_id,
                 importer_name=EXCLUDED.importer_name,importer_version=EXCLUDED.importer_version,
                 layer_count=EXCLUDED.layer_count,block_count=EXCLUDED.block_count,
                 symbol_count=EXCLUDED.symbol_count,properties=EXCLUDED.properties,updated_at=now()
               RETURNING id""",
            (
                library_id, source_asset_id, diagnostic_asset_id, fingerprint, IMPORTER_NAME,
                IMPORTER_VERSION, manifest["drawing_version"], manifest["drawing_units"],
                manifest["layer_count"], manifest["block_count"], len(manifest["symbols"]),
                Jsonb({"dwg_sha256": dwg_hash, "dxf_sha256": dxf_hash, "model_entity_count": manifest["model_entity_count"], "insert_count": manifest["insert_count"]}),
            ),
        )
        actual_library_id = cursor.fetchone()[0]
        for symbol in manifest["symbols"]:
            locator = symbol["geometry_locator"]
            locator_hash = sha256(json.dumps(locator, sort_keys=True).encode()).hexdigest()
            fragment_id = stable_uuid(f"cad-block:{dxf_hash}:{symbol['block_record_handle']}:{symbol['source_block_name']}")
            symbol_id = stable_uuid(f"plant-symbol:{actual_library_id}:{symbol['source_block_name']}")
            cursor.execute(
                """INSERT INTO provenance.source_fragments(
                     id,source_asset_id,fragment_kind,locator,locator_hash,extracted_text,properties
                   ) VALUES (%s,%s,'cad_block',%s,%s,%s,%s)
                   ON CONFLICT (source_asset_id,fragment_kind,locator_hash) DO UPDATE SET
                     extracted_text=EXCLUDED.extracted_text,properties=EXCLUDED.properties
                   RETURNING id""",
                (fragment_id, diagnostic_asset_id, Jsonb(locator), locator_hash, symbol["source_block_name"], Jsonb({"entity_types": symbol["entity_types"]})),
            )
            actual_fragment_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO biology.plant_symbols(
                     id,library_id,source_fragment_id,source_block_name,normalized_name,
                     block_record_handle,candidate_kind,instance_count,entity_count,base_point,
                     extents,entity_types,source_layers,style_summary,hatch_summary,nested_blocks,
                     attribute_schema,attribute_examples,geometry_locator,review_status,properties
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'needs_review',%s)
                   ON CONFLICT (library_id,source_block_name) DO UPDATE SET
                     source_fragment_id=EXCLUDED.source_fragment_id,normalized_name=EXCLUDED.normalized_name,
                     block_record_handle=EXCLUDED.block_record_handle,candidate_kind=EXCLUDED.candidate_kind,
                     instance_count=EXCLUDED.instance_count,entity_count=EXCLUDED.entity_count,
                     base_point=EXCLUDED.base_point,extents=EXCLUDED.extents,
                     entity_types=EXCLUDED.entity_types,source_layers=EXCLUDED.source_layers,
                     style_summary=EXCLUDED.style_summary,hatch_summary=EXCLUDED.hatch_summary,
                     nested_blocks=EXCLUDED.nested_blocks,attribute_schema=EXCLUDED.attribute_schema,
                     attribute_examples=EXCLUDED.attribute_examples,geometry_locator=EXCLUDED.geometry_locator,
                     properties=EXCLUDED.properties,updated_at=now()""",
                (
                    symbol_id, actual_library_id, actual_fragment_id, symbol["source_block_name"],
                    symbol["normalized_name"], symbol["block_record_handle"], symbol["candidate_kind"],
                    symbol["instance_count"], symbol["entity_count"], Jsonb(symbol["base_point"]),
                    Jsonb(symbol["extents"]), Jsonb(symbol["entity_types"]), Jsonb(symbol["source_layers"]),
                    Jsonb(symbol["style_summary"]), Jsonb(symbol["hatch_summary"]), Jsonb(symbol["nested_blocks"]),
                    Jsonb(symbol["attribute_schema"]), Jsonb(symbol["attribute_examples"]), Jsonb(locator),
                    Jsonb({"canonical_geometry": "source_dxf_block", "preview_required": True}),
                ),
            )
    connection.commit()
    return {
        "library_id": str(library_id), "fingerprint": fingerprint,
        "dwg_sha256": dwg_hash, "dxf_sha256": dxf_hash,
        "symbols": len(manifest["symbols"]),
        "symbols_with_hatch": sum(item["hatch_summary"]["count"] > 0 for item in manifest["symbols"]),
        "symbols_with_nested_blocks": sum(bool(item["nested_blocks"]) for item in manifest["symbols"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a DWG/DXF plant symbol library into GreenPlan")
    parser.add_argument("--database-url", default=os.getenv("GREENPLAN_DATABASE_URL"))
    parser.add_argument("--dwg", type=Path, default=Path(os.getenv("PLANT_SYMBOL_DWG", "/dataset/Шаблоны значков.dwg")))
    parser.add_argument("--dxf", type=Path, default=Path(os.getenv("PLANT_SYMBOL_DXF", "/dataset/dxf/Шаблоны значков.dxf")))
    parser.add_argument("--manifest", type=Path, help="write the extracted manifest to this JSON file")
    parser.add_argument("--dry-run", action="store_true", help="extract and report without writing PostGIS")
    args = parser.parse_args()
    if not args.dwg.is_file():
        raise SystemExit(f"DWG not found: {args.dwg}")
    if not args.dxf.is_file():
        raise SystemExit(f"DXF not found: {args.dxf}")
    manifest = extract_library_manifest(args.dxf)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.dry_run:
        result = {
            "drawing_version": manifest["drawing_version"], "layers": manifest["layer_count"],
            "blocks": manifest["block_count"], "inserts": manifest["insert_count"],
            "symbols": len(manifest["symbols"]),
            "symbols_with_hatch": sum(item["hatch_summary"]["count"] > 0 for item in manifest["symbols"]),
            "symbols_with_nested_blocks": sum(bool(item["nested_blocks"]) for item in manifest["symbols"]),
        }
    else:
        if not args.database_url:
            raise SystemExit("--database-url or GREENPLAN_DATABASE_URL is required unless --dry-run is used")
        with psycopg.connect(args.database_url) as connection:
            result = import_manifest(connection, args.dwg, args.dxf, manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
