from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
from pathlib import PurePosixPath
from typing import Iterable, Mapping


PUBLICATION_ROOT_ROLES = {"effective_design", "reference_context", "historical"}
WORKSPACE_KINDS = {"project_solution", "source_data", "archive"}


def workspace_kind(path: str, delivery_role: str | None = None) -> str | None:
    value = path.replace("\\", "/").casefold().replace("ё", "е")
    parts = [part for part in PurePosixPath(value).parts[:-1] if part]
    if delivery_role == "archive" or any("архив" in part or "archive" in part for part in parts):
        return "archive"
    if delivery_role in {"source_data", "survey", "register"} or any(
        "исходн" in part or "обслед" in part or "подоснов" in part for part in parts
    ):
        return "source_data"
    if delivery_role == "project_solution" or any(
        "проект" in part and ("решен" in part or "документ" in part) for part in parts
    ):
        return "project_solution"
    return None


def default_root_role(kind: str) -> str:
    return {
        "project_solution": "effective_design",
        "source_data": "reference_context",
        "archive": "historical",
    }[kind]


def dependency_graph(
    document_ids: Iterable[str], dependencies: Iterable[Mapping[str, object]],
) -> tuple[dict[str, list[str]], set[str], dict[str, int]]:
    documents = set(document_ids)
    outgoing: dict[str, list[str]] = {asset_id: [] for asset_id in documents}
    incoming: set[str] = set()
    unresolved: dict[str, int] = {asset_id: 0 for asset_id in documents}
    for edge in dependencies:
        source = str(edge["source_asset_id"])
        if source not in documents:
            continue
        target_value = edge.get("referenced_asset_id")
        status = str(edge.get("status") or edge.get("resolved_status") or "missing")
        if status == "resolved" and target_value is not None and str(target_value) in documents:
            target = str(target_value)
            outgoing[source].append(target)
            incoming.add(target)
        elif status not in {"ignored"}:
            unresolved[source] += 1
    for values in outgoing.values():
        values.sort()
    return outgoing, incoming, unresolved


def closure_for_root(root_id: str, outgoing: Mapping[str, list[str]]) -> list[str]:
    visited: set[str] = set()
    queue = deque([root_id])
    while queue:
        asset_id = queue.popleft()
        if asset_id in visited:
            continue
        visited.add(asset_id)
        queue.extend(outgoing.get(asset_id, ()))
    return sorted(visited)


def root_candidates(
    documents: Iterable[Mapping[str, object]], dependencies: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows = [dict(item) for item in documents]
    by_id = {str(item["source_asset_id"]): item for item in rows}
    outgoing, incoming, unresolved = dependency_graph(by_id, dependencies)
    result: list[dict[str, object]] = []
    for asset_id, item in by_id.items():
        kind = workspace_kind(str(item["relative_path"]), str(item.get("delivery_role") or ""))
        if asset_id in incoming or kind not in WORKSPACE_KINDS:
            continue
        closure = closure_for_root(asset_id, outgoing)
        unresolved_count = sum(unresolved.get(value, 0) for value in closure)
        fingerprint = sha256(json.dumps(closure, separators=(",", ":")).encode()).hexdigest()
        result.append({
            **item,
            "source_asset_id": asset_id,
            "workspace_kind": kind,
            "default_role": default_root_role(kind),
            "dependency_asset_ids": [value for value in closure if value != asset_id],
            "dependency_count": max(0, len(closure) - 1),
            "unresolved_count": unresolved_count,
            "closure_fingerprint": fingerprint,
        })
    order = {"project_solution": 0, "source_data": 1, "archive": 2}
    return sorted(result, key=lambda item: (
        order[str(item["workspace_kind"])],
        -float(item.get("score") or 0),
        str(item["relative_path"]).casefold(),
    ))
