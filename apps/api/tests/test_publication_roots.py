from uuid import UUID

from greenplan_api.intake_service import _load_publication_candidates
from greenplan_api.publication_roots import (
    closure_for_root,
    default_root_role,
    dependency_graph,
    root_candidates,
    workspace_kind,
)


def test_workspace_kind_and_default_roles_are_explicit():
    assert workspace_kind("Улица/Проектное решение/DWG/head.dwg", "project_solution") == "project_solution"
    assert workspace_kind("Улица/Исходные данные/base.dwg", "source_data") == "source_data"
    assert workspace_kind("Улица/Архив/old.dwg", "project_solution") == "archive"
    assert workspace_kind("Улица/misc/file.dwg", "unknown") is None
    assert default_root_role("project_solution") == "effective_design"
    assert default_root_role("source_data") == "reference_context"
    assert default_root_role("archive") == "historical"


def test_only_graph_roots_are_selectable_and_closure_is_transitive():
    documents = [
        {"source_asset_id": "head", "relative_path": "P/Проектное решение/head.dwg", "delivery_role": "project_solution", "score": 50},
        {"source_asset_id": "base", "relative_path": "P/Исходные данные/base.dwg", "delivery_role": "source_data", "score": 8},
        {"source_asset_id": "network", "relative_path": "P/Исходные данные/network.dwg", "delivery_role": "source_data", "score": 8},
        {"source_asset_id": "archive", "relative_path": "P/Архив/old.dwg", "delivery_role": "archive", "score": 8},
    ]
    dependencies = [
        {"source_asset_id": "head", "referenced_asset_id": "base", "status": "resolved"},
        {"source_asset_id": "base", "referenced_asset_id": "network", "status": "resolved"},
    ]
    candidates = root_candidates(documents, dependencies)
    assert [item["source_asset_id"] for item in candidates] == ["head", "archive"]
    assert candidates[0]["dependency_asset_ids"] == ["base", "network"]
    assert candidates[0]["dependency_count"] == 2


def test_unresolved_edges_are_counted_only_inside_the_root_closure():
    documents = [
        {"source_asset_id": "a", "relative_path": "P/Проектное решение/a.dwg", "delivery_role": "project_solution"},
        {"source_asset_id": "b", "relative_path": "P/Архив/b.dwg", "delivery_role": "archive"},
    ]
    dependencies = [
        {"source_asset_id": "a", "referenced_asset_id": None, "status": "missing"},
        {"source_asset_id": "b", "referenced_asset_id": None, "status": "ignored"},
    ]
    candidates = root_candidates(documents, dependencies)
    assert candidates[0]["unresolved_count"] == 1
    assert candidates[1]["unresolved_count"] == 0


def test_dependency_graph_preserves_shared_children_for_each_root():
    edges = [
        {"source_asset_id": "a", "referenced_asset_id": "shared", "status": "resolved"},
        {"source_asset_id": "b", "referenced_asset_id": "shared", "status": "resolved"},
    ]
    outgoing, incoming, _ = dependency_graph(["a", "b", "shared"], edges)
    assert incoming == {"shared"}
    assert closure_for_root("a", outgoing) == ["a", "shared"]
    assert closure_for_root("b", outgoing) == ["b", "shared"]


class _PublicationCursor:
    def __init__(self, batches):
        self.batches = list(batches)
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))

    def fetchall(self):
        return self.batches.pop(0)


def test_candidate_loader_scopes_xrefs_by_revision_document_assets():
    revision_id = UUID("11111111-1111-1111-1111-111111111111")
    asset_id = UUID("22222222-2222-2222-2222-222222222222")
    cursor = _PublicationCursor(([{
        "source_asset_id": asset_id,
        "relative_path": "P/Проектное решение/head.dwg",
        "delivery_role": "project_solution",
        "score": 10.0,
        "role": "master_candidate",
        "cues": [],
    }], []))

    candidates = _load_publication_candidates(cursor, revision_id)

    assert [item["source_asset_id"] for item in candidates] == [str(asset_id)]
    assert "cd.source_asset_id=ANY" in cursor.calls[1][0]
    assert cursor.calls[1][1] == ([asset_id],)
