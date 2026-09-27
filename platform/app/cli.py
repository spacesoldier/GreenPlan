import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

from celery_app import app
from db import all_libredwg_job_ids, batch_summary, completed_oda_artifacts, create_job, failed_libredwg_job_ids, initialize, job_details, oda_artifact, set_job, upsert_asset, upsert_project
from publish import materialize

ROOT = Path(os.environ.get("DATASET_ROOT", "/dataset"))
ARCHIVE_ROOT = Path(os.environ.get("ARCHIVE_ROOT", "/archive-extracted"))
PROJECT_RE = re.compile(r"^\d+\.\s*")
DWG_SIGNATURES = {"AC1015", "AC1018", "AC1021", "AC1024", "AC1027", "AC1032"}


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def classify(path: Path) -> tuple[str, float, list[str]]:
    lowered = "/".join(path.parts).lower()
    suffix = path.suffix.lower()
    cues: list[str] = []
    if suffix in {".dwg", ".dxf"}:
        media = "cad"
    elif suffix == ".pdf":
        media = "pdf"
    else:
        media = "other"
    if "исходн" in lowered or "/апот" in lowered or "/ирд" in lowered:
        cues.append("source-directory")
        return "material_basis", 0.90, cues
    if "архив" in lowered:
        cues.append("archive-directory")
        return "archive", 0.80, cues
    if "проектное решение" in lowered or "проектн" in lowered:
        cues.append("project-solution-directory")
        if any(token in lowered for token in ("генеральный план", "генплан", "/гр_", "дендроплан", "разбивочно-посад")):
            cues.append("plan-name")
            return "project_head_candidate", 0.82, cues
        return "project_delivery", 0.62, cues
    if any(token in lowered for token in ("генеральный план", "генплан", "дендроплан")):
        cues.append("plan-name-outside-known-folder")
        return "plan_candidate", 0.55, cues
    return "unclassified", 0.10, cues


def project_dirs() -> list[Path]:
    return sorted(
        (p for p in ROOT.rglob("*") if p.is_dir() and len(p.relative_to(ROOT).parts) <= 2 and PROJECT_RE.match(p.name)),
        key=lambda p: str(p),
    )


def ingest_project(project_dir: Path) -> dict:
    assets: list[tuple[Path, str, float, list[str]]] = []
    role_counts: Counter[str] = Counter()
    for path in project_dir.rglob("*"):
        if not path.is_file() or "PaxHeader" in path.parts or "dxf" in path.relative_to(project_dir).parts:
            continue
        role, confidence, cues = classify(path.relative_to(ROOT))
        assets.append((path, role, confidence, cues))
        role_counts[role] += 1
    structure = {
        "method": "path-heuristic-v1",
        "root": relative(project_dir),
        "asset_count": len(assets),
        "roles": dict(role_counts),
        "note": "Candidates only: per-project taxonomy and semantic confirmation are a next-stage task.",
    }
    project_id = upsert_project(relative(project_dir), project_dir.name, structure)
    for path, role, confidence, cues in assets:
        media = "cad" if path.suffix.lower() in {".dwg", ".dxf"} else "pdf" if path.suffix.lower() == ".pdf" else "other"
        upsert_asset(project_id, relative(path), media, role, confidence, cues, path.stat().st_size)
    return {"id": project_id, "path": relative(project_dir), **structure}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dwg_signature(path: Path) -> str:
    with path.open("rb") as stream:
        return stream.read(6).decode("ascii", errors="replace")


def project_dir_for(path: Path) -> Path:
    parts = path.relative_to(ROOT).parts
    index = next((i for i, part in enumerate(parts) if PROJECT_RE.match(part)), None)
    if index is None:
        return ROOT
    return ROOT.joinpath(*parts[:index + 1])


def dataset_root_project() -> dict:
    structure = {
        "method": "path-heuristic-v1",
        "root": ".",
        "asset_count": 0,
        "roles": {},
        "note": "Files outside numbered street projects.",
    }
    project_id = upsert_project(".", "dataset root", structure)
    return {"id": project_id, "path": ".", **structure}


def register(path: Path, project: dict) -> tuple[str, bool]:
    role, confidence, cues = classify(path.relative_to(ROOT))
    asset_id = upsert_asset(project["id"], relative(path), "cad", role, confidence, cues, path.stat().st_size)
    return create_job(project["id"], asset_id, relative(path), sha256(path))


def register_archive(path: Path, project: dict) -> tuple[str, bool]:
    virtual = str(path.resolve().relative_to(ARCHIVE_ROOT.resolve()))
    asset_id = upsert_asset(
        project["id"], virtual, "cad", "archive", 0.98,
        ["extracted-archive-member", "manifested-source"], path.stat().st_size,
    )
    return create_job(project["id"], asset_id, virtual, sha256(path))


def submit(input_path: str) -> str:
    path = (ROOT / input_path).resolve()
    if ROOT.resolve() not in path.parents or not path.is_file() or path.suffix.lower() != ".dwg":
        raise ValueError("submit accepts an existing .dwg path relative to DATASET_ROOT")
    if dwg_signature(path) not in DWG_SIGNATURES:
        raise ValueError("input does not have a supported DWG signature")
    project_dir = project_dir_for(path)
    project = dataset_root_project() if project_dir == ROOT else ingest_project(project_dir)
    job_id, created = register(path, project)
    if created:
        app.send_task("tasks.oda_convert", args=[job_id], queue="oda")
    return job_id


def project_dwgs(project_dir: Path) -> list[Path]:
    result = []
    for path in project_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".dwg":
            continue
        relative_parts = path.relative_to(project_dir).parts
        if "PaxHeader" in relative_parts or "dxf" in relative_parts:
            continue
        if dwg_signature(path) in DWG_SIGNATURES:
            result.append(path)
    return sorted(result, key=str)


def submit_all(limit: int | None = None, dry_run: bool = False) -> dict:
    selected: list[tuple[Path, Path]] = []
    by_project: dict[str, dict] = {}
    for project_dir in project_dirs():
        paths = project_dwgs(project_dir)
        if limit is not None:
            paths = paths[:max(0, limit - len(selected))]
        by_project[relative(project_dir)] = {
            "files": len(paths),
            "bytes": sum(path.stat().st_size for path in paths),
        }
        selected.extend((project_dir, path) for path in paths)
        if limit is not None and len(selected) >= limit:
            break
    if limit is None or len(selected) < limit:
        scoped = {path for _, path in selected}
        unscoped = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix.lower() != ".dwg" or path in scoped:
                continue
            parts = path.relative_to(ROOT).parts
            if "PaxHeader" in parts or "dxf" in parts:
                continue
            if dwg_signature(path) in DWG_SIGNATURES and not any(PROJECT_RE.match(part) for part in parts):
                unscoped.append(path)
        unscoped.sort(key=str)
        if limit is not None:
            unscoped = unscoped[:max(0, limit - len(selected))]
        if unscoped:
            by_project["."] = {"files": len(unscoped), "bytes": sum(path.stat().st_size for path in unscoped)}
            selected.extend((ROOT, path) for path in unscoped)
    result = {
        "dry_run": dry_run,
        "selected": len(selected),
        "bytes": sum(path.stat().st_size for _, path in selected),
        "projects": by_project,
        "created": 0,
        "existing": 0,
    }
    if dry_run:
        return result
    projects: dict[Path, dict] = {}
    for project_dir, path in selected:
        if project_dir not in projects:
            projects[project_dir] = dataset_root_project() if project_dir == ROOT else ingest_project(project_dir)
        job_id, created = register(path, projects[project_dir])
        if created:
            app.send_task("tasks.oda_convert", args=[job_id], queue="oda")
            result["created"] += 1
        else:
            result["existing"] += 1
    return result


def submit_archives(limit: int | None = None, dry_run: bool = False) -> dict:
    paths = []
    if ARCHIVE_ROOT.exists():
        for path in ARCHIVE_ROOT.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() == ".dwg":
                if dwg_signature(path) in DWG_SIGNATURES:
                    paths.append(path)
    paths.sort(key=str)
    if limit is not None:
        paths = paths[:limit]
    result = {
        "dry_run": dry_run,
        "selected": len(paths),
        "bytes": sum(path.stat().st_size for path in paths),
        "created": 0,
        "existing": 0,
    }
    if dry_run:
        return result
    projects: dict[Path, dict] = {}
    for path in paths:
        virtual_parts = path.relative_to(ARCHIVE_ROOT).parts
        project_index = next((i for i, part in enumerate(virtual_parts) if PROJECT_RE.match(part)), None)
        if project_index is None:
            continue
        project_dir = ROOT.joinpath(*virtual_parts[:project_index + 1])
        if project_dir not in projects:
            projects[project_dir] = ingest_project(project_dir)
        job_id, created = register_archive(path, projects[project_dir])
        if created:
            app.send_task("tasks.oda_convert", args=[job_id], queue="oda")
            result["created"] += 1
        else:
            result["existing"] += 1
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="GreenPlan CAD conversion platform control")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    ingest = commands.add_parser("ingest-projects")
    ingest.add_argument("--limit", type=int)
    submit_parser = commands.add_parser("submit")
    submit_parser.add_argument("dataset_path")
    submit_all_parser = commands.add_parser("submit-all")
    submit_all_parser.add_argument("--limit", type=int)
    submit_all_parser.add_argument("--dry-run", action="store_true")
    submit_archives_parser = commands.add_parser("submit-archives")
    submit_archives_parser.add_argument("--limit", type=int)
    submit_archives_parser.add_argument("--dry-run", action="store_true")
    commands.add_parser("batch-status")
    retry_libredwg = commands.add_parser("retry-libredwg-failed")
    retry_libredwg.add_argument("--limit", type=int)
    retry_libredwg_all = commands.add_parser("retry-libredwg-all")
    retry_libredwg_all.add_argument("--limit", type=int)
    retry_libredwg_dxf_all = commands.add_parser("retry-libredwg-dxf-all")
    retry_libredwg_dxf_all.add_argument("--limit", type=int)
    status = commands.add_parser("status")
    status.add_argument("job_id")
    publish = commands.add_parser("publish")
    publish.add_argument("job_id")
    publish.add_argument("--destination", choices=("dataset", "portable", "both"), default="both")
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--overwrite", action="store_true")
    publish_all = commands.add_parser("publish-completed")
    publish_all.add_argument("--destination", choices=("dataset", "portable", "both"), default="both")
    publish_all.add_argument("--limit", type=int)
    publish_all.add_argument("--dry-run", action="store_true")
    publish_all.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.command == "init-db":
        initialize()
        print("schema ready")
    elif args.command == "ingest-projects":
        result = [ingest_project(path) for path in project_dirs()[:args.limit]]
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif args.command == "submit":
        print(submit(args.dataset_path))
    elif args.command == "submit-all":
        print(json.dumps(submit_all(args.limit, args.dry_run), ensure_ascii=False, indent=2, default=str))
    elif args.command == "submit-archives":
        print(json.dumps(submit_archives(args.limit, args.dry_run), ensure_ascii=False, indent=2, default=str))
    elif args.command == "batch-status":
        print(json.dumps(batch_summary(), ensure_ascii=False, indent=2, default=str))
    elif args.command == "retry-libredwg-failed":
        job_ids = failed_libredwg_job_ids(args.limit)
        for job_id in job_ids:
            set_job(job_id, "libredwg_queued", error=None)
            app.send_task("tasks.libredwg_probe", args=[job_id], queue="libredwg")
        print(json.dumps({"queued": len(job_ids)}, ensure_ascii=False, indent=2))
    elif args.command == "retry-libredwg-all":
        job_ids = all_libredwg_job_ids(args.limit)
        for job_id in job_ids:
            set_job(job_id, "libredwg_queued", error=None)
            app.send_task("tasks.libredwg_probe", args=[job_id], queue="libredwg")
        print(json.dumps({"queued": len(job_ids)}, ensure_ascii=False, indent=2))
    elif args.command == "retry-libredwg-dxf-all":
        job_ids = all_libredwg_job_ids(args.limit)
        for job_id in job_ids:
            app.send_task("tasks.libredwg_dxf_probe", args=[job_id], queue="libredwg")
        print(json.dumps({"queued": len(job_ids)}, ensure_ascii=False, indent=2))
    elif args.command == "status":
        print(json.dumps(job_details(args.job_id), ensure_ascii=False, indent=2, default=str))
    elif args.command == "publish":
        print(json.dumps(materialize(oda_artifact(args.job_id), args.destination, args.dry_run, args.overwrite), ensure_ascii=False, indent=2))
    elif args.command == "publish-completed":
        result = []
        for record in completed_oda_artifacts(args.limit, args.destination):
            try:
                result.extend(materialize(record, args.destination, args.dry_run, args.overwrite))
            except FileNotFoundError as exc:
                result.append({"job_id": record["job_id"], "status": "missing_work_artifact", "error": str(exc)})
            except FileExistsError as exc:
                result.append({"job_id": record["job_id"], "status": "target_conflict", "error": str(exc)})
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
