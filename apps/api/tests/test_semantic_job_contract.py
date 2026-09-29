import inspect

from greenplan_api.models import SemanticSuggestionJobView
from greenplan_api.postgis_repository import PostgisRepository
from greenplan_api.semantic_jobs import (
    JOB_VIEW_COLUMNS, SEMANTIC_JOB_SCOPE, SEMANTIC_LAYER_SCOPE_SQL, assistant_category_is_assignable,
)


def test_semantic_job_query_matches_public_response_contract():
    selected = {column.strip() for column in JOB_VIEW_COLUMNS.replace("\n", "").split(",")}
    assert selected == set(SemanticSuggestionJobView.model_fields)


def test_project_detail_reuses_semantic_job_response_columns():
    source = inspect.getsource(PostgisRepository.get_intake_project)
    assert "SELECT {JOB_VIEW_COLUMNS}" in source


def test_semantic_job_is_strictly_scoped_to_one_selected_document():
    assert SEMANTIC_JOB_SCOPE == "selected_document"
    assert "WHERE cd.source_asset_id=%s" in SEMANTIC_LAYER_SCOPE_SQL
    assert "cad_xrefs" not in SEMANTIC_LAYER_SCOPE_SQL
    assert "parent_asset_id" not in SEMANTIC_LAYER_SCOPE_SQL
    assert "cl.mapping_status<>'confirmed'" in SEMANTIC_LAYER_SCOPE_SQL


def test_assistant_assigns_every_meaningful_class_but_not_unknown():
    assert assistant_category_is_assignable("utility.water.pipeline") is True
    assert assistant_category_is_assignable("not_applicable") is True
    assert assistant_category_is_assignable("unknown") is False
