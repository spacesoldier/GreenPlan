import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from db import record_publication

DATASET_ROOT = Path(os.environ.get("DATASET_ROOT", "/dataset")).resolve()
WORK_ROOT = Path(os.environ.get("WORK_ROOT", "/work")).resolve()
EXPORT_ROOT = Path(os.environ.get("EXPORT_ROOT", "/exports")).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def street_path(input_path: str) -> tuple[Path, Path]:
    parts = Path(input_path).parts
    street_index = next((i for i, part in enumerate(parts) if __import__("re").match(r"^\d+\.\s*", part)), None)
    if street_index is None:
        return Path(), Path(input_path)
    if street_index == len(parts) - 1:
        raise ValueError(f"street project path has no file segment: {input_path}")
    return Path(*parts[:street_index + 1]), Path(*parts[street_index + 1:])


def targets(input_path: str, destination: str) -> list[tuple[str, Path]]:
    street, relative = street_path(input_path)
    if relative.suffix.lower() != ".dwg":
        raise ValueError(f"expected DWG input, got {relative}")
    dxf_relative = relative.with_suffix(".dxf")
    output: list[tuple[str, Path]] = []
    if destination in {"dataset", "both"}:
        output.append(("dataset_dxf", DATASET_ROOT / street / "dxf" / dxf_relative))
    if destination in {"portable", "both"}:
        # The portable root starts with a street, not the common dataset collection.
        portable_root = EXPORT_ROOT / "dxf-only"
        output.append(("portable_dxf", portable_root / street.name / dxf_relative if street.name else portable_root / dxf_relative))
    return output


def copy_verified(source: Path, target: Path, digest: str, overwrite: bool) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = sha256(target)
        if existing == digest:
            return "already_present"
        if not overwrite:
            raise FileExistsError(f"refusing to replace different file: {target}")
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".greenplan-", delete=False) as temporary:
        temp_path = Path(temporary.name)
        with source.open("rb") as stream:
            shutil.copyfileobj(stream, temporary, length=1024 * 1024)
    if sha256(temp_path) != digest:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"checksum changed while copying {source}")
    os.replace(temp_path, target)
    return "copied"


def materialize(record: dict, destination: str, dry_run: bool = False, overwrite: bool = False) -> list[dict]:
    source = (WORK_ROOT / record["work_path"]).resolve()
    if WORK_ROOT not in source.parents or not source.is_file():
        raise FileNotFoundError(source)
    results = []
    for publication, target in targets(record["input_path"], destination):
        if dry_run:
            status = "would_copy"
        else:
            status = copy_verified(source, target, record["sha256"], overwrite)
            record_publication(record["job_id"], publication, str(target), record["sha256"], record["size_bytes"])
        results.append({"publication": publication, "target": str(target), "status": status})
    return results
