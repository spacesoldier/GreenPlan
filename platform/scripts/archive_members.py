#!/usr/bin/env python3
"""Inventory and safely extract DWG files hidden in per-project archive folders."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

ARCHIVE_DIR_NAMES = {"архив", "архивы"}
ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z"}
DWG_SIGNATURES = {b"AC1015", b"AC1018", b"AC1021", b"AC1024", b"AC1027", b"AC1032"}
PROJECT_RE = re.compile(r"^\d+\.\s*")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def archive_folder(path: Path, dataset_root: Path) -> bool:
    return any(part.casefold() in ARCHIVE_DIR_NAMES for part in path.relative_to(dataset_root).parts[:-1])


def project_parts(path: Path, dataset_root: Path) -> tuple[tuple[str, ...], int]:
    parts = path.relative_to(dataset_root).parts
    index = next((i for i, part in enumerate(parts) if PROJECT_RE.match(part)), -1)
    if index < 0:
        raise ValueError(f"archive is not inside a numbered project: {path}")
    return parts, index


def virtual_output_dir(archive: Path, dataset_root: Path, output_root: Path) -> Path:
    parts, project_index = project_parts(archive, dataset_root)
    before = parts[: project_index + 1]
    within_project = parts[project_index + 1 :]
    return output_root.joinpath(*before, "_archives", *within_project)


def list_members(archive: Path) -> tuple[list[dict], str]:
    result = subprocess.run(
        ["7z", "l", "-slt", "--", str(archive)],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"7z exit {result.returncode}")
    tail = result.stdout.split("----------", 1)
    if len(tail) != 2:
        raise RuntimeError("7z did not return a member table")
    members: list[dict] = []
    for block in re.split(r"\n\s*\n", tail[1]):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if " = " in line:
                key, value = line.split(" = ", 1)
                fields[key] = value
        if fields.get("Path"):
            members.append(fields)
    return members, result.stderr.strip()


def safe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    return not pure.is_absolute() and ".." not in pure.parts and not re.match(r"^[A-Za-z]:", normalized)


def relevant_members(members: list[dict]) -> list[str]:
    selected = []
    for member in members:
        name = member["Path"]
        if not safe_member(name):
            raise ValueError(f"unsafe archive member path: {name!r}")
        if member.get("Folder") == "+":
            continue
        if Path(name).suffix.casefold() == ".dwg" or Path(name).suffix.casefold() in ARCHIVE_SUFFIXES:
            selected.append(name)
    return selected


def extract_selected(archive: Path, destination: Path, names: list[str]) -> str:
    destination.mkdir(parents=True, exist_ok=True)
    if not names:
        return ""
    result = subprocess.run(
        ["7z", "x", "-y", "-aoa", f"-o{destination}", "--", str(archive), *names],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"7z exit {result.returncode}")
    return "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)


def discover(dataset_root: Path) -> tuple[list[Path], list[Path]]:
    archives: list[Path] = []
    excluded: list[Path] = []
    for path in dataset_root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in ARCHIVE_SUFFIXES:
            continue
        relative = path.relative_to(dataset_root)
        if len(relative.parts) == 1:
            excluded.append(path)
        elif "PaxHeader" in relative.parts:
            excluded.append(path)
        elif archive_folder(path, dataset_root):
            archives.append(path)
    return sorted(archives, key=str), sorted(excluded, key=str)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=Path(__file__).resolve().parents[2] / "dataset")
    parser.add_argument("--output-root", type=Path, default=Path("/tmp/greenplan-archive-extracted-sol"))
    parser.add_argument("--extract", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    dataset_root = args.dataset_root.resolve()
    output_root = args.output_root.resolve()
    archives, excluded = discover(dataset_root)
    records: list[dict] = []
    pending: list[tuple[Path, Path, str]] = []
    for archive in archives:
        pending.append((archive, virtual_output_dir(archive, dataset_root, output_root), "dataset"))

    seen_archives: set[tuple[str, str]] = set()
    while pending:
        archive, destination, origin = pending.pop(0)
        key = (str(archive.resolve()), str(destination))
        if key in seen_archives:
            continue
        seen_archives.add(key)
        record = {
            "archive": str(archive),
            "origin": origin,
            "destination": str(destination),
            "status": "inventoried",
        }
        try:
            members, listing_warning = list_members(archive)
            selected = relevant_members(members)
            record.update(
                members=len(members),
                selected=len(selected),
                dwg_members=sum(Path(name).suffix.casefold() == ".dwg" for name in selected),
                nested_archives=sum(Path(name).suffix.casefold() in ARCHIVE_SUFFIXES for name in selected),
                unpacked_bytes=sum(int(item.get("Size", "0") or 0) for item in members),
                listing_warning=listing_warning,
            )
            if args.extract:
                record["extract_log"] = extract_selected(archive, destination, selected)
                record["status"] = "extracted"
                for path in destination.rglob("*"):
                    if path.is_symlink():
                        path.unlink()
                        continue
                    if path.is_file() and path.suffix.casefold() in ARCHIVE_SUFFIXES:
                        pending.append((path, path.with_name(path.name + ".contents"), str(archive)))
        except Exception as exc:
            record.update(status="failed", error=str(exc))
        records.append(record)

    dwgs = []
    if args.extract and output_root.exists():
        for path in sorted(output_root.rglob("*"), key=str):
            if not path.is_file() or path.is_symlink() or path.suffix.casefold() != ".dwg":
                continue
            signature = path.read_bytes()[:6]
            dwgs.append(
                {
                    "path": str(path.relative_to(output_root)),
                    "bytes": path.stat().st_size,
                    "sha256": digest(path),
                    "signature": signature.decode("ascii", errors="replace"),
                    "valid_dwg": signature in DWG_SIGNATURES,
                }
            )
    summary = {
        "dataset_root": str(dataset_root),
        "output_root": str(output_root),
        "extract": args.extract,
        "seed_archives": len(archives),
        "excluded_top_level_or_pax": [str(path.relative_to(dataset_root)) for path in excluded],
        "archives_processed": len(records),
        "archives_failed": sum(item["status"] == "failed" for item in records),
        "listed_unpacked_bytes": sum(item.get("unpacked_bytes", 0) for item in records),
        "dwg_files": len(dwgs),
        "valid_dwg_files": sum(item["valid_dwg"] for item in dwgs),
        "unique_valid_dwg_sha256": len({item["sha256"] for item in dwgs if item["valid_dwg"]}),
        "records": records,
        "dwgs": dwgs,
    }
    manifest = args.manifest or output_root / "archive-manifest.json"
    if args.extract:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["archives_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
