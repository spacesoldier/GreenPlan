from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

import ezdxf
from ezdxf.document import Drawing
from ezdxf import xref


class XrefAssemblyError(RuntimeError):
    pass


@dataclass
class AssemblyManifest:
    root: str
    dependencies: list[dict] = field(default_factory=list)
    skipped_overlays: list[dict] = field(default_factory=list)
    skipped_unresolved: list[dict] = field(default_factory=list)


def xref_insertions(document: Drawing, block_name: str) -> list[dict]:
    result: list[dict] = []
    for space in document.layouts:
        for insert in space.query("INSERT"):
            if str(insert.dxf.name).casefold() != block_name.casefold():
                continue
            matrix = list(insert.matrix44())
            result.append({
                "space": space.name,
                "handle": insert.dxf.get("handle"),
                "matrix": [float(value) for value in matrix],
                "insert": [float(value) for value in insert.dxf.insert],
                "rotation": float(insert.dxf.get("rotation", 0.0)),
                "scale": [
                    float(insert.dxf.get("xscale", 1.0)),
                    float(insert.dxf.get("yscale", 1.0)),
                    float(insert.dxf.get("zscale", 1.0)),
                ],
            })
    return result


def assemble_xrefs(
    root_path: Path,
    resolve: Callable[[Path, str], Path | None],
    skip_unresolved: Callable[[Path, str], bool] | None = None,
) -> tuple[Drawing, AssemblyManifest]:
    """Embed a resolved XREF graph into a copy loaded from disk.

    `resolve(parent_path, original_xref_path)` must return a converted DXF path.
    The original files are never modified.
    """
    root_path = root_path.resolve()
    manifest = AssemblyManifest(root=str(root_path))

    def load(path: Path, stack: tuple[Path, ...], *, root: bool) -> Drawing:
        path = path.resolve()
        if path in stack:
            chain = " -> ".join(str(item) for item in (*stack, path))
            raise XrefAssemblyError(f"XREF cycle: {chain}")
        document = ezdxf.readfile(path)
        next_stack = (*stack, path)
        # Make a stable copy because embedding mutates the block table.
        blocks = list(document.blocks)
        for block in blocks:
            try:
                record = block.block_record
                if not record.is_xref:
                    continue
                original = str(block.block.dxf.get("xref_path", "") or "")
                overlay = bool(block.block.is_xref_overlay)
            except (AttributeError, TypeError):
                continue
            if overlay and not root:
                manifest.skipped_overlays.append({
                    "parent": str(path), "block": block.name, "path": original,
                })
                continue
            resolved = resolve(path, original)
            if resolved is None:
                if skip_unresolved is not None and skip_unresolved(path, original):
                    manifest.skipped_unresolved.append({
                        "parent": str(path), "block": block.name, "path": original,
                    })
                    continue
                raise XrefAssemblyError(f"unresolved XREF {block.name!r}: {original!r} in {path}")
            child = load(resolved, next_stack, root=False)
            placements = xref_insertions(document, block.name)
            # ezdxf validates the XREF path before invoking load_fn. Point the
            # disposable in-memory document at the resolved DXF artifact.
            block.block.dxf.xref_path = str(resolved.resolve())
            xref.embed(
                block,
                load_fn=lambda _filename, prepared=child: prepared,
                conflict_policy=xref.ConflictPolicy.XREF_PREFIX,
            )
            manifest.dependencies.append({
                "parent": str(path),
                "child": str(resolved.resolve()),
                "block": block.name,
                "original_path": original,
                "overlay": overlay,
                "placements": placements,
            })
        return document

    return load(root_path, (), root=True), manifest


def delivery_xref_resolver(path_map: dict[str, Path], logical_parent_by_file: dict[Path, str]):
    """Build deterministic delivery resolver: relative, exact, then unique basename."""
    folded = {key.replace("\\", "/").casefold(): value for key, value in path_map.items()}
    by_name: dict[str, list[Path]] = {}
    for logical, physical in path_map.items():
        by_name.setdefault(PurePosixPath(logical.replace("\\", "/")).name.casefold(), []).append(physical)

    def resolve(parent_file: Path, original: str) -> Path | None:
        raw = original.replace("\\", "/").strip()
        parent_logical = logical_parent_by_file.get(parent_file.resolve(), "")
        relative = (PurePosixPath(parent_logical).parent / PurePosixPath(raw)).as_posix().casefold()
        candidate = folded.get(relative) or folded.get(raw.casefold().lstrip("./"))
        if candidate:
            return candidate
        matches = by_name.get(PurePosixPath(raw).name.casefold(), [])
        return matches[0] if len(matches) == 1 else None

    return resolve
