from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile
from typing import BinaryIO
from uuid import UUID, uuid4

import ezdxf
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .dxf_ingest import iter_primitives
from .dxf_ingest import classify_layer
from .classification import classify_delivery_path, needs_model_assist
from .cad_assembly import assemble_xrefs, delivery_xref_resolver, xref_insertions
from .decision_models import DecisionProviderError, laya_delivery_role
from .import_pilots import PilotSpec, ingest_geometry
from .semantic_taxonomy import classify_layer_axes, feature_snapshot


DWG_SIGNATURE = re.compile(rb"^AC\d{4}$")
DXF_BINARY_SIGNATURE = b"AutoCAD Binary DXF"


class IntakeConflict(RuntimeError):
    pass


def safe_archive_member(raw: str) -> str | None:
    value = raw.replace("\\", "/").strip("/")
    if not value or value.startswith("/") or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    if any(part.casefold().startswith("paxheader") or part.casefold() == "__macosx" for part in path.parts):
        return None
    return path.as_posix()


def _expand_nested_zip_archives(cursor, revision_id: UUID, delivery_id: UUID, root: Path) -> None:
    cursor.execute(
        """SELECT de.id AS entry_id,de.relative_path,sa.*
           FROM intake.delivery_entries de
           JOIN provenance.source_assets sa ON sa.id=de.source_asset_id
           WHERE de.delivery_id=%s AND lower(de.relative_path) LIKE '%%.zip'""",
        (delivery_id,),
    )
    for archive in cursor.fetchall():
        logical = archive["relative_path"].replace("\\", "/")
        # Dataset-level bundles are transport wrappers, not project material.
        if "/" not in logical:
            continue
        physical = (root / archive["storage_locator"]).resolve()
        if root not in physical.parents or not physical.is_file():
            continue
        cursor.execute("UPDATE provenance.source_assets SET asset_kind='archive' WHERE id=%s", (archive["id"],))
        cursor.execute("UPDATE intake.delivery_entries SET entry_kind='archive' WHERE id=%s", (archive["entry_id"],))
        try:
            with zipfile.ZipFile(physical) as bundle:
                members = [item for item in bundle.infolist() if not item.is_dir()]
                if len(members) > 10_000 or sum(item.file_size for item in members) > 2 * 1024**3:
                    raise IntakeConflict("archive exceeds safe member or unpacked-size limit")
                for item in members:
                    member = safe_archive_member(item.filename)
                    if member is None or item.flag_bits & 0x1 or item.file_size > 512 * 1024**2:
                        continue
                    if item.compress_size and item.file_size / item.compress_size > 200:
                        continue
                    derived_path = f"{logical}::/{member}"
                    cursor.execute(
                        "SELECT 1 FROM intake.delivery_entries WHERE delivery_id=%s AND relative_path=%s",
                        (delivery_id, derived_path),
                    )
                    if cursor.fetchone():
                        continue
                    with bundle.open(item) as stream:
                        digest, size, locator, deduplicated, header = store_stream(root, stream)
                    detected, version = detect_cad_format(header)
                    asset_id = uuid4()
                    cursor.execute(
                        """INSERT INTO provenance.source_assets(
                               id,project_revision_id,parent_asset_id,asset_kind,media_type,original_name,
                               storage_locator,sha256,size_bytes,availability_status,properties,scope_kind)
                           VALUES (%s,%s,%s,'archive_member',%s,%s,%s,%s,%s,'available',%s,'project_revision')""",
                        (
                            asset_id, revision_id, archive["id"], media_kind_for(member, detected),
                            PurePosixPath(member).name, locator, digest, size,
                            Jsonb({"relative_path": derived_path, "archive_member": member,
                                   "detected_format": detected, "format_version": version,
                                   "deduplicated_blob": deduplicated}),
                        ),
                    )
                    cursor.execute(
                        """INSERT INTO intake.delivery_entries(
                               delivery_id,source_asset_id,parent_entry_id,relative_path,entry_kind,
                               media_kind,size_bytes,sha256,role,cues)
                           VALUES (%s,%s,%s,%s,'archive_member',%s,%s,%s,'archive',%s)""",
                        (
                            delivery_id, asset_id, archive["entry_id"], derived_path,
                            detected if detected != "unknown" else PurePosixPath(member).suffix.casefold().lstrip("."),
                            size, digest, Jsonb(["archive member"]),
                        ),
                    )
                    if detected in {"dwg", "dxf"}:
                        cursor.execute(
                            """INSERT INTO intake.cad_inventories(
                                   revision_id,source_asset_id,stage,format,format_version,parse_status,
                                   tool_name,metrics,artifact_locator,fingerprint)
                               VALUES (%s,%s,'source',%s,%s,'pending','archive-expander',%s,%s,%s)""",
                            (revision_id, asset_id, detected, version, Jsonb({"archive_member": member}), locator, digest),
                        )
        except (zipfile.BadZipFile, IntakeConflict) as exc:
            cursor.execute(
                """INSERT INTO intake.fidelity_findings(
                       revision_id,source_asset_id,code,severity,stage,title,detail,evidence)
                   VALUES (%s,%s,'archive_scan_failed','warning','archive_inventory',
                           'Архив не разобран',%s,%s)""",
                (revision_id, archive["id"], str(exc), Jsonb({"relative_path": logical})),
            )


def normalize_relative_path(raw: str) -> str:
    value = raw.replace("\\", "/").strip()
    if not value or value.startswith("/") or "\x00" in value:
        raise ValueError("relative path is required")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative path contains an unsafe segment")
    normalized = path.as_posix()
    if len(normalized) > 1024:
        raise ValueError("relative path is too long")
    return normalized


def detect_cad_format(header: bytes) -> tuple[str, str | None]:
    signature = header[:6]
    if DWG_SIGNATURE.match(signature):
        return "dwg", signature.decode("ascii")
    if header.startswith(DXF_BINARY_SIGNATURE):
        return "dxf", "binary"
    text = header[:4096].decode("latin-1", errors="ignore").upper()
    if "SECTION" in text and ("HEADER" in text or "ENTITIES" in text):
        return "dxf", None
    return "unknown", None


def media_kind_for(path: str, detected_format: str) -> str:
    if detected_format in {"dwg", "dxf"}:
        return f"application/{detected_format}"
    suffix = PurePosixPath(path).suffix.casefold()
    return {
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
        ".xlsb": "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
        ".xlt": "application/vnd.ms-excel",
        ".xltx": "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
        ".xltm": "application/vnd.ms-excel.template.macroEnabled.12",
        ".csv": "text/csv",
        ".ods": "application/vnd.oasis.opendocument.spreadsheet",
        ".zip": "application/zip",
    }.get(suffix, "application/octet-stream")


def content_blob_path(root: Path, digest: str) -> Path:
    return root / "blobs" / "sha256" / digest[:2] / digest[2:4] / digest


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def store_stream(root: Path, stream: BinaryIO) -> tuple[str, int, str, bool, bytes]:
    root.mkdir(parents=True, exist_ok=True)
    temp_root = root / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    size = 0
    header = bytearray()
    with tempfile.NamedTemporaryFile(dir=temp_root, prefix="upload-", delete=False) as target:
        temporary = Path(target.name)
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            if len(header) < 4096:
                header.extend(chunk[: 4096 - len(header)])
            digest.update(chunk)
            size += len(chunk)
            target.write(chunk)
    checksum = digest.hexdigest()
    destination = content_blob_path(root, checksum)
    destination.parent.mkdir(parents=True, exist_ok=True)
    deduplicated = destination.exists()
    if deduplicated:
        temporary.unlink(missing_ok=True)
    else:
        os.replace(temporary, destination)
    return checksum, size, destination.relative_to(root).as_posix(), deduplicated, bytes(header)


def _connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row)


def _workspace_id(cursor, workspace_code: str) -> UUID:
    cursor.execute("SELECT id FROM catalog.workspaces WHERE code=%s", (workspace_code,))
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"workspace {workspace_code!r} does not exist")
    return row["id"]


def create_project(database_url: str, workspace_code: str, code: str, title: str, description: str | None) -> UUID:
    project_id = uuid4()
    revision_id = uuid4()
    delivery_id = uuid4()
    fingerprint = f"draft:{revision_id}"
    with _connect(database_url) as connection, connection.cursor() as cursor:
        workspace_id = _workspace_id(cursor, workspace_code)
        try:
            cursor.execute(
                """INSERT INTO catalog.projects(id,workspace_id,code,title,status,properties)
                   VALUES (%s,%s,%s,%s,'draft',%s)""",
                (project_id, workspace_id, code, title, Jsonb({"description": description})),
            )
        except psycopg.errors.UniqueViolation as exc:
            raise IntakeConflict("project code already exists") from exc
        cursor.execute(
            """INSERT INTO catalog.project_revisions(
                   id,project_id,revision_no,content_fingerprint,status,notes)
               VALUES (%s,%s,1,%s,'registered',%s)""",
            (revision_id, project_id, fingerprint, description),
        )
        cursor.execute(
            """INSERT INTO intake.deliveries(
                   id,project_revision_id,root_locator,content_fingerprint,status,properties)
               VALUES (%s,%s,%s,%s,'registered',%s)""",
            (delivery_id, revision_id, f"intake://{revision_id}", fingerprint, Jsonb({"uploaded": True})),
        )
        cursor.execute(
            """INSERT INTO intake.project_workflows(revision_id,delivery_id,state)
               VALUES (%s,%s,'draft')""",
            (revision_id, delivery_id),
        )
        cursor.execute(
            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,metadata)
               VALUES ('create','catalog','projects',%s,%s)""",
            (project_id, Jsonb({"revision_id": str(revision_id), "code": code})),
        )
    return project_id


def soft_delete_project(
    database_url: str,
    workspace_code: str,
    project_id: UUID,
    reason: str = "deleted from projects dashboard",
) -> bool:
    """Hide a project without deleting any delivery, evidence, artifact, or review row.

    Returns True when this call created the tombstone and False for an already deleted
    project. A missing project is distinct and raises KeyError.
    """
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT p.id,p.deleted_at
               FROM catalog.projects p
               JOIN catalog.workspaces w ON w.id=p.workspace_id
               WHERE p.id=%s AND w.code=%s""",
            (project_id, workspace_code),
        )
        project = cursor.fetchone()
        if project is None:
            raise KeyError(project_id)
        if project["deleted_at"] is not None:
            return False
        cursor.execute(
            """UPDATE catalog.projects
               SET deleted_at=now(),deletion_reason=%s,updated_at=now()
               WHERE id=%s AND deleted_at IS NULL""",
            (reason, project_id),
        )
        cursor.execute(
            """UPDATE intake.assistant_runs ar SET cancel_requested=true,heartbeat_at=now()
               FROM catalog.project_revisions pr
               WHERE ar.revision_id=pr.id AND pr.project_id=%s
                 AND ar.state IN ('queued','running')""",
            (project_id,),
        )
        cursor.execute(
            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,metadata)
               VALUES ('soft_delete','catalog','projects',%s,%s)""",
            (project_id, Jsonb({"reason": reason, "recoverable": True})),
        )
        return True


def register_upload(
    database_url: str,
    project_id: UUID,
    relative_path: str,
    digest: str,
    size: int,
    storage_locator: str,
    detected_format: str,
    format_version: str | None,
    deduplicated: bool,
) -> UUID:
    asset_id = uuid4()
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT pr.id AS revision_id, pw.delivery_id
               FROM catalog.projects p
               JOIN LATERAL (
                 SELECT value.* FROM catalog.project_revisions value
                 WHERE value.project_id=p.id ORDER BY revision_no DESC LIMIT 1
               ) pr ON true
               JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               WHERE p.id=%s AND p.deleted_at IS NULL""",
            (project_id,),
        )
        project = cursor.fetchone()
        if project is None:
            raise KeyError(project_id)
        cursor.execute(
            "SELECT 1 FROM intake.delivery_entries WHERE delivery_id=%s AND relative_path=%s",
            (project["delivery_id"], relative_path),
        )
        if cursor.fetchone():
            raise IntakeConflict("a file with this relative path is already uploaded")
        cursor.execute(
            """INSERT INTO provenance.source_assets(
                   id,project_revision_id,asset_kind,media_type,original_name,storage_locator,
                   sha256,size_bytes,availability_status,properties,scope_kind)
               VALUES (%s,%s,'file',%s,%s,%s,%s,%s,'available',%s,'project_revision')""",
            (
                asset_id,
                project["revision_id"],
                media_kind_for(relative_path, detected_format),
                PurePosixPath(relative_path).name,
                storage_locator,
                digest,
                size,
                Jsonb({
                    "relative_path": relative_path,
                    "detected_format": detected_format,
                    "format_version": format_version,
                    "deduplicated_blob": deduplicated,
                }),
            ),
        )
        cursor.execute(
            """INSERT INTO intake.delivery_entries(
                   delivery_id,source_asset_id,relative_path,entry_kind,media_kind,size_bytes,sha256,role,cues)
               VALUES (%s,%s,%s,'file',%s,%s,%s,%s,%s)""",
            (
                project["delivery_id"], asset_id, relative_path,
                detected_format if detected_format != "unknown" else PurePosixPath(relative_path).suffix.casefold().lstrip("."),
                size, digest, "unclassified", Jsonb([]),
            ),
        )
        if detected_format in {"dwg", "dxf"}:
            cursor.execute(
                """INSERT INTO intake.cad_inventories(
                       revision_id,source_asset_id,stage,format,format_version,parse_status,
                       tool_name,metrics,artifact_locator,fingerprint)
                   VALUES (%s,%s,'source',%s,%s,'pending','signature',%s,%s,%s)""",
                (
                    project["revision_id"], asset_id, detected_format, format_version,
                    Jsonb({"size_bytes": size}), storage_locator, digest,
                ),
            )
        cursor.execute(
            """UPDATE intake.project_workflows
               SET state='receiving',updated_at=now() WHERE revision_id=%s""",
            (project["revision_id"],),
        )
    return asset_id


def candidate_score(path: str) -> tuple[float, str, list[str]]:
    value = path.casefold().replace("ё", "е")
    score = 0.0
    cues: list[str] = []
    for token, points in (
        ("генеральный план", 40), ("генплан", 35), ("гр_", 28),
        ("проектное решение", 18), ("гп", 12), ("дендроплан", 8),
    ):
        if token in value:
            score += points
            cues.append(token)
    if value.endswith(".dwg"):
        score += 8
    elif value.endswith(".dxf"):
        score += 6
    if "/xref" in value or "/xrefs" in value:
        score -= 35
        cues.append("xref path")
    if re.search(r"(?:^|[_\s-])гп(?:[_\s.-]|$)", PurePosixPath(value).name):
        score += 12
        cues.append("гп в имени файла")
    role = "project_head_candidate" if score >= 25 else "cad_support"
    return score, role, cues


def dxf_inventory(path: Path) -> dict:
    document = ezdxf.readfile(path)
    model_counts: Counter[str] = Counter(entity.dxftype() for entity in document.modelspace())
    layer_counts: Counter[str] = Counter(str(entity.dxf.get("layer", "0")) for entity in document.modelspace())
    layer_entity_types: dict[str, Counter[str]] = {}
    for entity in document.modelspace():
        layer_name = str(entity.dxf.get("layer", "0"))
        layer_entity_types.setdefault(layer_name, Counter())[entity.dxftype()] += 1
    spaces = [{"name": "Model", "kind": "model", "entity_count": len(document.modelspace())}]
    for layout in document.layouts:
        if layout.name.casefold() == "model":
            continue
        spaces.append({"name": layout.name, "kind": "layout", "entity_count": len(layout)})
    xrefs = []
    for block in document.blocks:
        try:
            record = block.block_record
            if record.is_xref:
                xrefs.append({
                    "name": block.name,
                    "path": str(block.block.dxf.get("xref_path", "") or ""),
                    "overlay": bool(block.block.is_xref_overlay),
                    "placements": xref_insertions(document, block.name),
                })
        except (AttributeError, TypeError):
            continue
    extmin = document.header.get("$EXTMIN")
    extmax = document.header.get("$EXTMAX")
    extents = None
    if extmin is not None and extmax is not None:
        candidate_extents = [float(extmin[0]), float(extmin[1]), float(extmax[0]), float(extmax[1])]
        if candidate_extents[0] <= candidate_extents[2] and candidate_extents[1] <= candidate_extents[3]:
            extents = candidate_extents
    return {
        "dxf_version": document.dxfversion,
        "entity_count": sum(model_counts.values()),
        "entity_types": dict(model_counts),
        "layer_count": len(document.layers),
        "layer_entity_counts": dict(layer_counts),
        "layer_entity_types": {key: dict(value) for key, value in layer_entity_types.items()},
        "block_count": len(document.blocks),
        "layout_count": len(spaces) - 1,
        "spaces": spaces,
        "xrefs": xrefs,
        "extents": extents,
        "hatch_count": model_counts.get("HATCH", 0),
    }


def _record_dxf_inventory(cursor, revision_id: UUID, asset: dict, root: Path, stage: str, locator: str) -> None:
    path = (root / locator).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError(locator)
    try:
        metrics = dxf_inventory(path)
        cursor.execute(
            """SELECT source_asset_id,relative_path FROM intake.delivery_entries de
               JOIN intake.project_workflows pw ON pw.delivery_id=de.delivery_id
               WHERE pw.revision_id=%s""",
            (revision_id,),
        )
        delivery_rows = cursor.fetchall()
        delivery_paths = [row["relative_path"] for row in delivery_rows]
        asset_by_path = {row["relative_path"]: row["source_asset_id"] for row in delivery_rows}
        delivery_paths_folded = {value.replace("\\", "/").casefold(): value for value in delivery_paths}
        delivery_names: dict[str, list[str]] = {}
        for value in delivery_paths:
            delivery_names.setdefault(PurePosixPath(value.replace("\\", "/")).name.casefold(), []).append(value)
        resolved_xrefs = []
        parent_path = str(asset.get("properties", {}).get("relative_path") or "")
        for xref in metrics.get("xrefs", []):
            raw_path = str(xref.get("path") or "").replace("\\", "/")
            folded = raw_path.casefold().lstrip("./")
            relative_folded = (PurePosixPath(parent_path).parent / PurePosixPath(raw_path)).as_posix().casefold()
            exact = delivery_paths_folded.get(relative_folded) or delivery_paths_folded.get(folded)
            basename_matches = delivery_names.get(PurePosixPath(raw_path).name.casefold(), []) if raw_path else []
            matches = [exact] if exact else basename_matches
            matches = [value for value in matches if value]
            resolution = "resolved" if len(matches) == 1 else "missing" if not matches else "ambiguous"
            resolved_xrefs.append({
                **xref,
                "resolution": resolution,
                "matches": matches,
                "referenced_asset_id": str(asset_by_path[matches[0]]) if resolution == "resolved" else None,
            })
            if resolution != "resolved":
                cursor.execute(
                    """INSERT INTO intake.fidelity_findings(
                           revision_id,source_asset_id,code,severity,stage,title,detail,evidence)
                       VALUES (%s,%s,%s,'critical',%s,%s,%s,%s)""",
                    (
                        revision_id,
                        asset["id"],
                        f"xref_{resolution}",
                        stage,
                        "Внешняя ссылка не разрешена" if resolution == "missing" else "Внешняя ссылка неоднозначна",
                        f"XREF {xref.get('name') or raw_path!r}: {resolution}",
                        Jsonb({"xref": xref, "matches": matches}),
                    ),
                )
        metrics["xrefs"] = resolved_xrefs
        status = "parsed"
        error = None
    except Exception as exc:
        metrics = {"error": repr(exc)}
        status = "failed"
        error = exc
    cursor.execute(
        """INSERT INTO intake.cad_inventories(
               revision_id,source_asset_id,stage,format,format_version,parse_status,
               tool_name,tool_version,metrics,artifact_locator,fingerprint)
           VALUES (%s,%s,%s,'dxf',%s,%s,'ezdxf','1.4.4',%s,%s,%s)
           ON CONFLICT (source_asset_id,stage) DO UPDATE SET
             format_version=EXCLUDED.format_version,parse_status=EXCLUDED.parse_status,
             metrics=EXCLUDED.metrics,artifact_locator=EXCLUDED.artifact_locator,updated_at=now()
           RETURNING id""",
        (
            revision_id, asset["id"], stage, metrics.get("dxf_version"), status,
            Jsonb(metrics), locator, asset["sha256"],
        ),
    )
    inventory_id = cursor.fetchone()["id"]

    cursor.execute(
        """INSERT INTO intake.cad_documents(source_asset_id,format,format_version,parse_status,properties)
           VALUES (%s,'dxf',%s,%s,%s)
           ON CONFLICT (source_asset_id) DO UPDATE SET
             format=EXCLUDED.format,format_version=EXCLUDED.format_version,
             parse_status=EXCLUDED.parse_status,properties=EXCLUDED.properties
           RETURNING id""",
        (
            asset["id"], metrics.get("dxf_version"),
            "parsed" if status == "parsed" else "failed",
            Jsonb({"inventory_id": str(inventory_id), "stage": stage, "artifact_locator": locator}),
        ),
    )
    cad_document_id = cursor.fetchone()["id"]
    cursor.execute("DELETE FROM intake.cad_xrefs WHERE cad_document_id=%s", (cad_document_id,))
    for xref_item in metrics.get("xrefs", []):
        referenced_id = xref_item.get("referenced_asset_id")
        cursor.execute(
            """INSERT INTO intake.cad_xrefs(
                   cad_document_id,referenced_asset_id,reference_name,original_path,resolved_status,properties)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (
                cad_document_id, referenced_id, xref_item.get("name") or xref_item.get("path") or "unnamed",
                xref_item.get("path"), xref_item.get("resolution", "missing"),
                Jsonb({"overlay": xref_item.get("overlay", False), "placements": xref_item.get("placements", []), "matches": xref_item.get("matches", [])}),
            ),
        )
    for layer_name, entity_count in metrics.get("layer_entity_counts", {}).items():
        classification = classify_layer(layer_name)
        entity_types = metrics.get("layer_entity_types", {}).get(layer_name, {})
        delivery_role = classify_delivery_path(
            str(asset.get("properties", {}).get("relative_path") or ""), "dxf",
        ).category
        document_role = {
            "project_solution": "general_plan",
            "source_data": "source_base",
            "survey_existing": "survey",
            "xref_dependency": "xref",
        }.get(delivery_role, "unknown")
        axes = classify_layer_axes(
            layer_name, entity_types=entity_types, document_role=document_role,
        )
        snapshot = feature_snapshot(
            layer_name=layer_name,
            entity_types=entity_types,
            entity_count=entity_count,
            document_role=document_role,
            relative_path=str(asset.get("properties", {}).get("relative_path") or ""),
        )
        snapshot_fingerprint = sha256(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest()
        target_key = f"{asset['id']}:{layer_name}"
        cursor.execute(
            """INSERT INTO intake.feature_snapshots(
                   revision_id,source_asset_id,target_kind,target_key,schema_version,fingerprint,features)
               VALUES (%s,%s,'cad_layer',%s,%s,%s,%s)
               ON CONFLICT (revision_id,target_kind,target_key,schema_version,fingerprint)
               DO UPDATE SET features=EXCLUDED.features RETURNING id""",
            (revision_id, asset["id"], target_key, snapshot["schema_version"], snapshot_fingerprint, Jsonb(snapshot)),
        )
        feature_snapshot_id = cursor.fetchone()["id"]
        cursor.execute(
            """INSERT INTO intake.cad_layers(
                   cad_document_id,name,entity_count,mapping_status,confidence,properties)
               VALUES (%s,%s,%s,'candidate',%s,%s)
               ON CONFLICT (cad_document_id,name) DO UPDATE SET
                 entity_count=EXCLUDED.entity_count,confidence=EXCLUDED.confidence,
                 properties=EXCLUDED.properties
               RETURNING id""",
            (
                cad_document_id, layer_name, entity_count, classification.confidence,
                Jsonb({"suggested_class_code": classification.class_code, "reason": classification.reason,
                       "taxonomy": axes.as_dict()}),
            ),
        )
        layer_id = cursor.fetchone()["id"]
        cursor.execute(
            """INSERT INTO intake.classification_suggestions(
                   revision_id,target_kind,target_key,source_asset_id,cad_layer_id,suggested_category,
                   confidence,method,input_snapshot,cues,alternatives,taxonomy_version,axis_results,
                   feature_snapshot_id,provider_run)
               VALUES (%s,'cad_layer',%s,%s,%s,%s,%s,'multi-axis-rules-v2',%s,%s,'[]'::jsonb,
                       %s,%s,%s,%s)
               ON CONFLICT (revision_id,target_kind,target_key,method) DO UPDATE SET
                 cad_layer_id=EXCLUDED.cad_layer_id,suggested_category=EXCLUDED.suggested_category,
                 confidence=EXCLUDED.confidence,input_snapshot=EXCLUDED.input_snapshot,cues=EXCLUDED.cues,
                 taxonomy_version=EXCLUDED.taxonomy_version,axis_results=EXCLUDED.axis_results,
                 feature_snapshot_id=EXCLUDED.feature_snapshot_id,provider_run=EXCLUDED.provider_run""",
            (
                revision_id, target_key, asset["id"], layer_id,
                axes.object_class.label, axes.object_class.confidence,
                Jsonb(snapshot), Jsonb([classification.reason]), axes.taxonomy_version,
                Jsonb(axes.as_dict()), feature_snapshot_id,
                Jsonb({"provider": "deterministic_rules", "version": "rules-v2"}),
            ),
        )
    cursor.execute("DELETE FROM intake.cad_spaces WHERE inventory_id=%s", (inventory_id,))
    for space in metrics.get("spaces", []):
        cursor.execute(
            """INSERT INTO intake.cad_spaces(inventory_id,name,space_kind,entity_count,properties)
               VALUES (%s,%s,%s,%s,'{}'::jsonb)""",
            (inventory_id, space["name"], space["kind"], space["entity_count"]),
        )
    cursor.execute(
        """INSERT INTO intake.processing_stage_attempts(
               revision_id,source_asset_id,stage,attempt_no,state,progress,metrics,error_summary,started_at,finished_at)
           VALUES (%s,%s,%s,
                   COALESCE((SELECT max(attempt_no)+1 FROM intake.processing_stage_attempts
                             WHERE revision_id=%s AND source_asset_id=%s AND stage=%s),1),
                   %s,1,%s,%s,now(),now())""",
        (
            revision_id, asset["id"], f"{stage}_inventory",
            revision_id, asset["id"], f"{stage}_inventory",
            "failed" if error else "completed", Jsonb(metrics), str(error) if error else None,
        ),
    )
    if error:
        cursor.execute(
            """INSERT INTO intake.fidelity_findings(
                   revision_id,source_asset_id,code,severity,stage,title,detail,evidence)
               VALUES (%s,%s,'dxf_parse_failed','critical',%s,'DXF не прочитан',%s,%s)""",
            (revision_id, asset["id"], stage, str(error), Jsonb({"locator": locator})),
        )


def _enqueue_dwg(cursor, revision_id: UUID, asset: dict, broker_url: str | None) -> tuple[str, str, str, str, str] | None:
    cursor.execute(
        "SELECT id,state FROM intake.conversion_jobs WHERE source_asset_id=%s AND input_sha256=%s ORDER BY created_at DESC LIMIT 1",
        (asset["id"], asset["sha256"]),
    )
    existing = cursor.fetchone()
    if existing and existing["state"] not in {"failed", "cancelled"}:
        return None
    job_id = uuid4()
    cursor.execute(
        """INSERT INTO intake.conversion_jobs(id,source_asset_id,input_sha256,state)
           VALUES (%s,%s,%s,'queued')""",
        (job_id, asset["id"], asset["sha256"]),
    )
    cursor.execute(
        """INSERT INTO intake.processing_stage_attempts(
               revision_id,source_asset_id,stage,attempt_no,state,progress,metrics)
           VALUES (%s,%s,'direct_dwg_read',
                   COALESCE((SELECT max(attempt_no)+1 FROM intake.processing_stage_attempts
                             WHERE revision_id=%s AND source_asset_id=%s AND stage='direct_dwg_read'),1),
                   'queued',0,%s)""",
        (revision_id, asset["id"], revision_id, asset["id"], Jsonb({"job_id": str(job_id)})),
    )
    if not broker_url:
        cursor.execute(
            """UPDATE intake.processing_stage_attempts SET state='blocked',finished_at=now(),
                   error_summary='CELERY_BROKER_URL is not configured'
               WHERE revision_id=%s AND source_asset_id=%s AND stage='direct_dwg_read'""",
            (revision_id, asset["id"]),
        )
        cursor.execute("UPDATE intake.conversion_jobs SET state='failed',error_summary='converter queue is unavailable',finished_at=now() WHERE id=%s", (job_id,))
        cursor.execute(
            """INSERT INTO intake.fidelity_findings(
                   revision_id,source_asset_id,code,severity,stage,title,detail,evidence)
               VALUES (%s,%s,'converter_unavailable','critical','routing','DWG требует конвертер',
                       'Прямой reader не подключён, а очередь конвертации недоступна',%s)""",
            (revision_id, asset["id"], Jsonb({"job_id": str(job_id)})),
        )
        return None
    return (
        str(job_id), str(revision_id), str(asset["id"]),
        asset["storage_locator"], asset["properties"]["relative_path"],
    )


def analyze_revision(database_url: str, intake_root: Path, project_id: UUID, broker_url: str | None) -> None:
    intake_root = intake_root.resolve()
    queued_tasks: list[tuple[str, str, str, str, str]] = []
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT pr.id AS revision_id,pw.delivery_id
               FROM catalog.project_revisions pr
               JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               WHERE pr.project_id=%s ORDER BY pr.revision_no DESC LIMIT 1""",
            (project_id,),
        )
        workflow = cursor.fetchone()
        if workflow is None:
            raise KeyError(project_id)
        revision_id = workflow["revision_id"]
        cursor.execute("UPDATE intake.project_workflows SET state='analyzing',updated_at=now() WHERE revision_id=%s", (revision_id,))
        cursor.execute("UPDATE intake.deliveries SET status='inventoried' WHERE id=%s", (workflow["delivery_id"],))
        cursor.execute("DELETE FROM intake.fidelity_findings WHERE revision_id=%s", (revision_id,))
        cursor.execute("DELETE FROM intake.master_candidates WHERE revision_id=%s", (revision_id,))
        cursor.execute(
            """UPDATE intake.classification_suggestions SET review_status='superseded'
               WHERE revision_id=%s AND target_kind='cad_layer'
                 AND method<>'multi-axis-rules-v2' AND review_status='pending'""",
            (revision_id,),
        )
        _expand_nested_zip_archives(cursor, revision_id, workflow["delivery_id"], intake_root)
        cursor.execute(
            """SELECT sa.id,sa.storage_locator,sa.sha256,sa.size_bytes,sa.properties,de.relative_path
               FROM intake.delivery_entries de
               JOIN provenance.source_assets sa ON sa.id=de.source_asset_id
               WHERE de.delivery_id=%s ORDER BY de.relative_path""",
            (workflow["delivery_id"],),
        )
        assets = cursor.fetchall()
        for asset in assets:
            detected = asset["properties"].get("detected_format", "unknown")
            suggestion = classify_delivery_path(asset["relative_path"], detected)
            laya_url = os.getenv("LAYA_URL")
            if laya_url and needs_model_assist(suggestion):
                try:
                    suggestion = laya_delivery_role(
                        laya_url,
                        relative_path=asset["relative_path"],
                        detected_format=detected,
                        api_key=os.getenv("LAYA_API_KEY"),
                    )
                except DecisionProviderError:
                    # Model assistance is advisory and must not make intake unavailable.
                    pass
            cursor.execute(
                """UPDATE intake.delivery_entries SET role=%s,cues=%s
                   WHERE delivery_id=%s AND source_asset_id=%s""",
                (suggestion.category, Jsonb(list(suggestion.cues)), workflow["delivery_id"], asset["id"]),
            )
            cursor.execute(
                """INSERT INTO intake.classification_suggestions(
                       revision_id,target_kind,target_key,source_asset_id,suggested_category,
                       confidence,method,input_snapshot,cues,alternatives)
                   VALUES (%s,'file',%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (revision_id,target_kind,target_key,method) DO UPDATE SET
                     suggested_category=EXCLUDED.suggested_category,
                     confidence=EXCLUDED.confidence,input_snapshot=EXCLUDED.input_snapshot,
                     cues=EXCLUDED.cues,alternatives=EXCLUDED.alternatives""",
                (
                    revision_id, str(asset["id"]), asset["id"], suggestion.category,
                    suggestion.confidence, suggestion.method,
                    Jsonb({"relative_path": asset["relative_path"], "detected_format": detected,
                           "model_assist_requested": needs_model_assist(suggestion)}),
                    Jsonb(list(suggestion.cues)),
                    Jsonb([{"category": key, "confidence": value} for key, value in suggestion.alternatives]),
                ),
            )
            if detected not in {"dwg", "dxf"}:
                continue
            score, role, cues = candidate_score(asset["relative_path"])
            cursor.execute(
                """INSERT INTO intake.master_candidates(revision_id,source_asset_id,score,role,cues)
                   VALUES (%s,%s,%s,%s,%s)""",
                (revision_id, asset["id"], score, role, Jsonb(cues)),
            )
            if detected == "dxf":
                _record_dxf_inventory(cursor, revision_id, asset, intake_root, "uploaded_dxf", asset["storage_locator"])
            else:
                cursor.execute(
                    """UPDATE intake.cad_inventories SET parse_status='partial',tool_name='signature',
                           metrics=metrics || %s,updated_at=now()
                       WHERE source_asset_id=%s AND stage='source'""",
                    (Jsonb({"reader_route": "libredwg_then_oda"}), asset["id"]),
                )
                task = _enqueue_dwg(cursor, revision_id, asset, broker_url)
                if task:
                    queued_tasks.append(task)
        # Re-evaluate already converted artifacts against the current delivery.
        # This is essential when a user adds missing XREF files and runs analysis again.
        _sync_conversion_outputs(cursor, intake_root, revision_id, force=True)
        cursor.execute(
            """UPDATE intake.project_workflows SET state=CASE
                   WHEN EXISTS (SELECT 1 FROM intake.conversion_jobs cj
                                JOIN provenance.source_assets sa ON sa.id=cj.source_asset_id
                                WHERE sa.project_revision_id=%s AND cj.state NOT IN ('completed','completed_with_warnings','failed','cancelled'))
                   THEN 'analyzing' ELSE 'review_required' END,
                   updated_at=now() WHERE revision_id=%s""",
            (revision_id, revision_id),
        )
        cursor.execute("UPDATE catalog.project_revisions SET status='inventory_complete' WHERE id=%s", (revision_id,))
    if queued_tasks and broker_url:
        from celery import Celery

        client = Celery("greenplan-intake-client", broker=broker_url)
        for task in queued_tasks:
            try:
                client.send_task("tasks.intake_libredwg_probe", args=list(task), queue="libredwg")
            except Exception as exc:
                job_id, failed_revision_id, asset_id, _locator, _relative_path = task
                with _connect(database_url) as failed_connection, failed_connection.cursor() as failed_cursor:
                    failed_cursor.execute(
                        """UPDATE intake.conversion_jobs
                           SET state='failed',error_summary=%s,finished_at=now() WHERE id=%s""",
                        (f"queue dispatch failed: {exc}", job_id),
                    )
                    failed_cursor.execute(
                        """UPDATE intake.processing_stage_attempts
                           SET state='failed',progress=1,error_summary=%s,finished_at=now()
                           WHERE revision_id=%s AND source_asset_id=%s AND stage='direct_dwg_read'
                             AND attempt_no=(SELECT max(attempt_no) FROM intake.processing_stage_attempts
                               WHERE revision_id=%s AND source_asset_id=%s AND stage='direct_dwg_read')""",
                        (f"queue dispatch failed: {exc}", failed_revision_id, asset_id, failed_revision_id, asset_id),
                    )
                    failed_cursor.execute(
                        """INSERT INTO intake.fidelity_findings(
                               revision_id,source_asset_id,code,severity,stage,title,detail,evidence)
                           VALUES (%s,%s,'queue_dispatch_failed','critical','routing',
                                   'Задача анализа не отправлена в очередь',%s,%s)""",
                        (failed_revision_id, asset_id, str(exc), Jsonb({"job_id": job_id})),
                    )
                    failed_cursor.execute(
                        """UPDATE intake.project_workflows
                           SET state='review_required',fidelity_verdict='rejected',updated_at=now()
                           WHERE revision_id=%s""",
                        (failed_revision_id,),
                    )


def _sync_conversion_outputs(cursor, intake_root: Path, revision_id: UUID, *, force: bool = False) -> None:
    cursor.execute(
        """SELECT cj.id AS job_id,cj.state,ca.storage_locator,ca.sha256,
                  sa.id,sa.storage_locator AS source_locator,sa.properties,sa.sha256 AS source_sha256
           FROM intake.conversion_jobs cj
           JOIN provenance.source_assets sa ON sa.id=cj.source_asset_id
           JOIN intake.conversion_artifacts ca ON ca.job_id=cj.id AND ca.stage='oda' AND ca.kind='dxf'
           WHERE sa.project_revision_id=%s
             AND cj.state IN ('completed','completed_with_warnings')""",
        (revision_id,),
    )
    for row in cursor.fetchall():
        cursor.execute(
            "SELECT 1 FROM intake.cad_inventories WHERE source_asset_id=%s AND stage='converted_dxf'",
            (row["id"],),
        )
        if cursor.fetchone() and not force:
            continue
        asset = {
            "id": row["id"],
            "sha256": row["sha256"],
            "properties": row["properties"],
        }
        _record_dxf_inventory(cursor, revision_id, asset, intake_root, "converted_dxf", row["storage_locator"])
        cursor.execute(
            """INSERT INTO intake.fidelity_findings(
                   revision_id,source_asset_id,code,severity,stage,title,detail,evidence)
               VALUES (%s,%s,'independent_pre_inventory_incomplete','warning','fidelity',
                       'Сравнение DWG и DXF неполно',
                       'LibreDWG дал диагностическое чтение, но независимый source inventory недостаточен для доказательства полного равенства.',%s)""",
            (revision_id, row["id"], Jsonb({"job_id": str(row["job_id"]), "dxf_sha256": row["sha256"]})),
        )


def _resolve_verdict(cursor, revision_id: UUID) -> tuple[str, str]:
    cursor.execute(
        """SELECT count(*) FILTER (WHERE state NOT IN ('completed','completed_with_warnings','failed','cancelled')) AS pending,
                  count(*) FILTER (WHERE state='failed') AS failed
           FROM intake.conversion_jobs cj
           JOIN provenance.source_assets sa ON sa.id=cj.source_asset_id
           WHERE sa.project_revision_id=%s""",
        (revision_id,),
    )
    jobs = cursor.fetchone()
    if jobs["pending"]:
        return "analyzing", "not_comparable"
    cursor.execute(
        "SELECT count(*) AS critical FROM intake.fidelity_findings WHERE revision_id=%s AND severity='critical' AND status='open'",
        (revision_id,),
    )
    critical = cursor.fetchone()["critical"]
    if jobs["failed"] or critical:
        return "review_required", "rejected"
    cursor.execute("SELECT count(*) AS converted FROM intake.cad_inventories WHERE revision_id=%s AND stage='converted_dxf'", (revision_id,))
    converted = cursor.fetchone()["converted"]
    if converted:
        return "review_required", "not_comparable"
    return "review_required", "accepted_with_review"


def refresh_workflow(database_url: str, intake_root: Path, project_id: UUID) -> None:
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT pr.id AS revision_id,pw.state FROM catalog.project_revisions pr
               JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               WHERE pr.project_id=%s ORDER BY revision_no DESC LIMIT 1
               FOR UPDATE OF pw""",
            (project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return
        if row["state"] not in {"analyzing", "review_required"}:
            return
        _sync_conversion_outputs(cursor, intake_root.resolve(), row["revision_id"])
        state, verdict = _resolve_verdict(cursor, row["revision_id"])
        cursor.execute(
            """UPDATE intake.project_workflows SET state=%s,fidelity_verdict=%s,updated_at=now()
               WHERE revision_id=%s AND state NOT IN ('ready_to_publish','published','retired')""",
            (state, verdict, row["revision_id"]),
        )


def review_revision(
    database_url: str,
    project_id: UUID,
    decision: str,
    comment: str,
    selected_master_asset_id: UUID | None,
) -> tuple[UUID, str, str | None]:
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT pr.id AS revision_id,pw.fidelity_verdict
               FROM catalog.project_revisions pr JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               WHERE pr.project_id=%s ORDER BY revision_no DESC LIMIT 1""",
            (project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(project_id)
        if decision == "reject":
            cursor.execute(
                """UPDATE intake.project_workflows SET state='blocked',review_comment=%s,updated_at=now()
                   WHERE revision_id=%s""",
                (comment, row["revision_id"]),
            )
            return row["revision_id"], "blocked", row["fidelity_verdict"]
        if row["fidelity_verdict"] in {"rejected", None}:
            raise IntakeConflict("this revision cannot be accepted until critical findings are resolved")
        if selected_master_asset_id is None:
            cursor.execute(
                """SELECT source_asset_id FROM intake.master_candidates WHERE revision_id=%s
                   ORDER BY score DESC,source_asset_id LIMIT 1""",
                (row["revision_id"],),
            )
            candidate = cursor.fetchone()
            selected_master_asset_id = candidate["source_asset_id"] if candidate else None
        if selected_master_asset_id is None:
            raise IntakeConflict("no CAD master candidate is available")
        cursor.execute("UPDATE intake.master_candidates SET selected=(source_asset_id=%s) WHERE revision_id=%s", (selected_master_asset_id, row["revision_id"]))
        accepted_verdict = "accepted_with_review" if row["fidelity_verdict"] == "not_comparable" else "accepted"
        cursor.execute(
            """UPDATE intake.project_workflows SET state='ready_to_publish',fidelity_verdict=%s,
                   selected_master_asset_id=%s,review_comment=%s,updated_at=now()
               WHERE revision_id=%s""",
            (accepted_verdict, selected_master_asset_id, comment, row["revision_id"]),
        )
        return row["revision_id"], "ready_to_publish", accepted_verdict


def review_classification(
    database_url: str,
    project_id: UUID,
    suggestion_id: UUID,
    decision: str,
    category: str | None,
    comment: str | None,
) -> None:
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT cs.*,pw.delivery_id
               FROM intake.classification_suggestions cs
               JOIN catalog.project_revisions pr ON pr.id=cs.revision_id
               JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               WHERE pr.project_id=%s AND cs.id=%s""",
            (project_id, suggestion_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(suggestion_id)
        reviewed_category = category or row["suggested_category"]
        status = "accepted" if decision == "accept" else "rejected"
        axis_values = dict(row.get("axis_results") or {})
        if category:
            axes = dict(axis_values.get("axes") or {})
            axes["object_class"] = {
                "label": category,
                "confidence": 1.0,
                "cues": ["engineer review"],
            }
            axis_values["axes"] = axes
        cursor.execute(
            """INSERT INTO intake.classification_reviews(
                   suggestion_id,project_id,decision,axis_values,scope,comment)
               VALUES (%s,%s,%s,%s,'project',%s)""",
            (
                suggestion_id, project_id,
                "accept" if decision == "accept" and not category else "correct" if decision == "accept" else "reject",
                Jsonb(axis_values), comment,
            ),
        )
        cursor.execute(
            """UPDATE intake.classification_suggestions
               SET review_status=%s,reviewed_category=%s,review_comment=%s,reviewed_at=now()
               WHERE id=%s""",
            (status, reviewed_category if status == "accepted" else None, comment, suggestion_id),
        )
        if status == "accepted" and row["target_kind"] == "file" and row["source_asset_id"]:
            cursor.execute(
                """UPDATE intake.delivery_entries SET role=%s
                   WHERE delivery_id=%s AND source_asset_id=%s""",
                (reviewed_category, row["delivery_id"], row["source_asset_id"]),
            )
        if status == "accepted" and row["target_kind"] == "cad_layer" and row["cad_layer_id"]:
            cursor.execute("SELECT id FROM geo.object_classes WHERE code=%s", (reviewed_category,))
            object_class = cursor.fetchone()
            cursor.execute(
                """UPDATE intake.cad_layers SET mapping_status='confirmed',
                     candidate_class_id=%s,properties=properties || %s WHERE id=%s""",
                (
                    object_class["id"] if object_class else None,
                    Jsonb({"reviewed_class_code": reviewed_category}), row["cad_layer_id"],
                ),
            )
        elif status == "rejected" and row["target_kind"] == "cad_layer" and row["cad_layer_id"]:
            cursor.execute("UPDATE intake.cad_layers SET mapping_status='rejected' WHERE id=%s", (row["cad_layer_id"],))
        cursor.execute(
            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,metadata)
               VALUES ('review','intake','classification_suggestions',%s,%s)""",
            (suggestion_id, Jsonb({"decision": decision, "category": reviewed_category, "comment": comment})),
        )


def review_classifications_batch(
    database_url: str,
    project_id: UUID,
    suggestion_ids: list[UUID],
    decision: str,
    category: str | None,
    comment: str | None,
) -> UUID:
    ordered_ids = sorted(set(suggestion_ids), key=str)
    fingerprint = sha256(json.dumps({
        "ids": [str(value) for value in ordered_ids], "decision": decision,
        "category": category, "comment": comment,
    }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT cs.*,pr.id AS project_revision_id
               FROM intake.classification_suggestions cs
               JOIN catalog.project_revisions pr ON pr.id=cs.revision_id
               WHERE pr.project_id=%s AND cs.id=ANY(%s) AND cs.target_kind='cad_layer'
               FOR UPDATE""",
            (project_id, ordered_ids),
        )
        rows = cursor.fetchall()
        if len(rows) != len(ordered_ids):
            raise KeyError("one or more classification suggestions do not exist")
        revision_ids = {row["revision_id"] for row in rows}
        if len(revision_ids) != 1:
            raise IntakeConflict("batch review must belong to one project revision")
        revision_id = next(iter(revision_ids))
        cursor.execute(
            """INSERT INTO intake.classification_review_batches(
                   project_id,revision_id,decision,category,suggestion_ids,taxonomy_version,comment,fingerprint)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (revision_id,fingerprint) DO UPDATE SET fingerprint=EXCLUDED.fingerprint
               RETURNING id,(xmax=0) AS inserted""",
            (
                project_id, revision_id,
                "correct" if decision == "accept" and category else "accept" if decision == "accept" else "reject",
                category, ordered_ids, rows[0].get("taxonomy_version"), comment, fingerprint,
            ),
        )
        batch = cursor.fetchone()
        batch_id = batch["id"]
        if not batch["inserted"]:
            return batch_id
        for row in rows:
            reviewed_category = category or row["suggested_category"]
            status = "accepted" if decision == "accept" else "rejected"
            axis_values = dict(row.get("axis_results") or {})
            if category:
                axes = dict(axis_values.get("axes") or {})
                axes["object_class"] = {"label": category, "confidence": 1.0, "cues": ["batch engineer review"]}
                axis_values["axes"] = axes
            cursor.execute(
                """INSERT INTO intake.classification_reviews(
                       suggestion_id,project_id,decision,axis_values,scope,comment,batch_id)
                   VALUES (%s,%s,%s,%s,'project',%s,%s)""",
                (
                    row["id"], project_id,
                    "correct" if decision == "accept" and category else "accept" if decision == "accept" else "reject",
                    Jsonb(axis_values), comment, batch_id,
                ),
            )
            cursor.execute(
                """UPDATE intake.classification_suggestions
                   SET review_status=%s,reviewed_category=%s,review_comment=%s,reviewed_at=now()
                   WHERE id=%s""",
                (status, reviewed_category if status == "accepted" else None, comment, row["id"]),
            )
            if row["cad_layer_id"]:
                if status == "accepted":
                    cursor.execute("SELECT id FROM geo.object_classes WHERE code=%s", (reviewed_category,))
                    object_class = cursor.fetchone()
                    cursor.execute(
                        """UPDATE intake.cad_layers SET mapping_status='confirmed',candidate_class_id=%s,
                               properties=properties || %s WHERE id=%s""",
                        (object_class["id"] if object_class else None,
                         Jsonb({"reviewed_class_code": reviewed_category}), row["cad_layer_id"]),
                    )
                else:
                    cursor.execute("UPDATE intake.cad_layers SET mapping_status='rejected' WHERE id=%s", (row["cad_layer_id"],))
        cursor.execute(
            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,metadata)
               VALUES ('batch_review','intake','classification_review_batches',%s,%s)""",
            (batch_id, Jsonb({"count": len(rows), "decision": decision, "category": category, "fingerprint": fingerprint})),
        )
        return batch_id


def resolve_finding(
    database_url: str, project_id: UUID, finding_id: UUID, action: str, reason: str,
) -> dict:
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT ff.* FROM intake.fidelity_findings ff
               JOIN catalog.project_revisions pr ON pr.id=ff.revision_id
               WHERE pr.project_id=%s AND ff.id=%s FOR UPDATE""",
            (project_id, finding_id),
        )
        finding = cursor.fetchone()
        if finding is None:
            raise KeyError(finding_id)
        status = {"waive": "accepted", "reopen": "open", "block": "rejected"}[action]
        impact = {
            "edge_resolved": False,
            "publication_blocked": action == "block" or (finding["severity"] == "critical" and action != "waive"),
            "revision_scoped": True,
        }
        cursor.execute("UPDATE intake.fidelity_findings SET status=%s WHERE id=%s", (status, finding_id))
        cursor.execute(
            """INSERT INTO intake.finding_resolutions(finding_id,project_id,action,reason,impact)
               VALUES (%s,%s,%s,%s,%s) RETURNING id,created_at""",
            (finding_id, project_id, action, reason, Jsonb(impact)),
        )
        resolution = cursor.fetchone()
        cursor.execute(
            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,metadata)
               VALUES ('finding_resolution','intake','fidelity_findings',%s,%s)""",
            (finding_id, Jsonb({"action": action, "reason": reason, "impact": impact})),
        )
        return {"id": str(resolution["id"]), "status": status, "action": action, "impact": impact}


def publish_revision(database_url: str, intake_root: Path, project_id: UUID) -> UUID:
    with _connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT p.code,p.title,pr.id AS revision_id,pw.selected_master_asset_id,
                      sa.storage_locator,sa.sha256,sa.properties
               FROM catalog.projects p
               JOIN LATERAL (SELECT value.* FROM catalog.project_revisions value
                 WHERE value.project_id=p.id ORDER BY revision_no DESC LIMIT 1) pr ON true
               JOIN intake.project_workflows pw ON pw.revision_id=pr.id
               JOIN provenance.source_assets sa ON sa.id=pw.selected_master_asset_id
               WHERE p.id=%s AND pw.state='ready_to_publish'""",
            (project_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise IntakeConflict("revision is not ready to publish")
        cursor.execute(
            """SELECT DISTINCT ON (ci.source_asset_id)
                      ci.source_asset_id,ci.artifact_locator,de.relative_path
               FROM intake.cad_inventories ci
               JOIN intake.project_workflows pw ON pw.revision_id=ci.revision_id
               JOIN intake.delivery_entries de ON de.delivery_id=pw.delivery_id
                                                AND de.source_asset_id=ci.source_asset_id
               WHERE ci.revision_id=%s AND ci.parse_status='parsed'
                 AND ci.stage IN ('converted_dxf','uploaded_dxf')
               ORDER BY ci.source_asset_id,
                 CASE ci.stage WHEN 'converted_dxf' THEN 0 WHEN 'uploaded_dxf' THEN 1 ELSE 2 END""",
            (row["revision_id"],),
        )
        inventory_rows = cursor.fetchall()
        inventory = next((item for item in inventory_rows if item["source_asset_id"] == row["selected_master_asset_id"]), None)
        if inventory is None:
            raise IntakeConflict("selected master has no parsed DXF representation")
        intake_root = intake_root.resolve()
        primary = (intake_root / inventory["artifact_locator"]).resolve()
        if intake_root.resolve() not in primary.parents or not primary.is_file():
            raise FileNotFoundError(primary)
        path_map: dict[str, Path] = {}
        logical_by_file: dict[Path, str] = {}
        for item in inventory_rows:
            physical = (intake_root / item["artifact_locator"]).resolve()
            if intake_root not in physical.parents or not physical.is_file():
                continue
            path_map[item["relative_path"]] = physical
            logical_by_file[physical] = item["relative_path"]
        assembled_doc, assembly_manifest = assemble_xrefs(
            primary,
            delivery_xref_resolver(path_map, logical_by_file),
        )
        assembly_dir = intake_root / "assemblies" / str(row["revision_id"])
        assembly_dir.mkdir(parents=True, exist_ok=True)
        assembled_path = assembly_dir / "assembled.dxf"
        assembled_doc.saveas(assembled_path)
        assembled_sha = file_sha256(assembled_path)
        territory_id = uuid4()
        coordinate_id = uuid4()
        model_id = uuid4()
        territory_code = f"{row['code']}-{str(row['revision_id'])[:8]}"
        cursor.execute(
            """INSERT INTO catalog.territories(id,code,title,territory_kind,jurisdiction_code)
               VALUES (%s,%s,%s,'other','RU-MOW')""",
            (territory_id, territory_code, row["title"]),
        )
        cursor.execute("INSERT INTO catalog.project_territories(project_id,territory_id,role) VALUES (%s,%s,'primary') ON CONFLICT DO NOTHING", (project_id, territory_id))
        cursor.execute(
            """INSERT INTO catalog.coordinate_spaces(id,code,kind,linear_unit,status,axis_definition)
               VALUES (%s,%s,'cad_local','unknown','candidate',%s)""",
            (coordinate_id, f"{territory_code}-cad-local", Jsonb({"origin": "intake_dxf"})),
        )
        cursor.execute(
            """INSERT INTO catalog.canonical_models(
                   id,project_revision_id,territory_id,coordinate_space_id,model_kind,version_no,
                   assembly_status,dependency_completeness,semantic_coverage,properties)
               VALUES (%s,%s,%s,%s,'combined',1,'needs_review',1,0,%s)""",
            (
                model_id, row["revision_id"], territory_id, coordinate_id,
                Jsonb({
                    "intake_publish": True,
                    "source_sha256": row["sha256"],
                    "assembled_sha256": assembled_sha,
                    "assembly_locator": assembled_path.relative_to(intake_root).as_posix(),
                    "assembly_manifest": {
                        "root": assembly_manifest.root,
                        "dependencies": assembly_manifest.dependencies,
                        "skipped_overlays": assembly_manifest.skipped_overlays,
                    },
                }),
            ),
        )
        ids = {"model": model_id}
        stats = ingest_geometry(
            connection,
            PilotSpec(code=row["code"], title=row["title"], directory="", primary_dxf=""),
            assembled_path,
            ids,
            row["selected_master_asset_id"],
            0,
        )
        cursor.execute("UPDATE catalog.projects SET status='active',updated_at=now() WHERE id=%s", (project_id,))
        cursor.execute(
            "UPDATE catalog.project_revisions SET status='interpreted',content_fingerprint=%s WHERE id=%s",
            (row["sha256"], row["revision_id"]),
        )
        cursor.execute(
            "UPDATE intake.project_workflows SET state='published',published_at=now(),updated_at=now() WHERE revision_id=%s",
            (row["revision_id"],),
        )
        cursor.execute(
            """INSERT INTO audit.events(action,entity_schema,entity_table,entity_id,after_digest,metadata)
               VALUES ('publish','catalog','canonical_models',%s,%s,%s)""",
            (model_id, assembled_sha, Jsonb({**stats, "xref_dependencies": len(assembly_manifest.dependencies)})),
        )
        connection.commit()
        return model_id
