#!/usr/bin/env python3
"""Create a ZIP64 DXF-only package with Windows-safe paths and a mapping."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path

FORBIDDEN = re.compile(r'[<>:"/\\|?*]')
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def sanitize_component(component: str, limit: int = 80) -> str:
    cleaned = FORBIDDEN.sub("_", component).rstrip(" .")
    if not cleaned:
        cleaned = "_"
    stem = cleaned.split(".", 1)[0].upper()
    if stem in RESERVED:
        cleaned = f"_{cleaned}"
    if len(cleaned) <= limit:
        return cleaned
    suffix = Path(cleaned).suffix
    room = max(8, limit - len(suffix) - 12)
    return f"{cleaned[:room]}~{short_hash(component)}{suffix}"


def windows_path(parts: tuple[str, ...], max_length: int = 210) -> str:
    safe = [sanitize_component(part) for part in parts]
    result = "/".join(safe)
    if len(result) <= max_length:
        return result
    # Shorten the longest directories first; preserve the .dxf suffix.
    order = sorted(range(len(safe) - 1), key=lambda i: len(safe[i]), reverse=True)
    for index in order:
        original = safe[index]
        if len(original) > 28:
            safe[index] = f"{original[:16]}~{short_hash(parts[index])}"
        result = "/".join(safe)
        if len(result) <= max_length:
            return result
    filename = safe[-1]
    suffix = Path(filename).suffix
    safe[-1] = f"{filename[:24]}~{short_hash('/'.join(parts))}{suffix}"
    result = "/".join(safe)
    if len(result) > max_length:
        raise ValueError(f"cannot shorten path to {max_length} characters: {result}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root-name", default="greenplan-dxf")
    args = parser.parse_args()

    source = args.source.resolve()
    files = sorted((path for path in source.rglob("*.dxf") if path.is_file()), key=str)
    if not files:
        raise SystemExit("no DXF files found")
    mappings: list[tuple[Path, str, str]] = []
    used: dict[str, str] = {}
    for path in files:
        original = path.relative_to(source).as_posix()
        safe_relative = windows_path(path.relative_to(source).parts)
        archive_path = f"{args.root_name}/{safe_relative}"
        folded = archive_path.casefold()
        if folded in used and used[folded] != original:
            target = Path(safe_relative)
            archive_path = (
                f"{args.root_name}/{target.parent.as_posix()}/"
                f"{target.stem}~{short_hash(original)}{target.suffix}"
            )
            folded = archive_path.casefold()
        if folded in used:
            raise ValueError(f"unresolved Windows path collision: {original} and {used[folded]}")
        used[folded] = original
        mappings.append((path, original, archive_path))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    csv_buffer = io.StringIO(newline="")
    writer = csv.writer(csv_buffer)
    writer.writerow(["original_relative_path", "windows_archive_path", "size_bytes"])
    for path, original, archive_path in mappings:
        writer.writerow([original, archive_path, path.stat().st_size])
    readme = (
        "GreenPlan DXF package for Windows\r\n"
        "=====================================\r\n\r\n"
        "This ZIP64 archive contains DXF files only. Paths were sanitized and shortened\r\n"
        "for Windows compatibility. See MANIFEST/windows_path_mapping.csv for the exact\r\n"
        "mapping to the original dataset paths. DXF file contents were not modified.\r\n"
    )
    total = sum(path.stat().st_size for path, _, _ in mappings)
    print(f"Packing {len(mappings)} DXF files ({total} bytes) into {args.output}", flush=True)
    with zipfile.ZipFile(
        args.output, "x", compression=zipfile.ZIP_DEFLATED,
        compresslevel=6, allowZip64=True,
    ) as archive:
        archive.writestr("README-WINDOWS.txt", readme)
        archive.writestr("MANIFEST/windows_path_mapping.csv", csv_buffer.getvalue().encode("utf-8-sig"))
        for index, (path, _, archive_path) in enumerate(mappings, 1):
            archive.write(path, archive_path)
            if index % 50 == 0 or index == len(mappings):
                print(f"{index}/{len(mappings)}", flush=True)
    print(f"Created {args.output} ({args.output.stat().st_size} bytes)", flush=True)


if __name__ == "__main__":
    main()
