from greenplan_api.models import SemanticSuggestionJobView
from greenplan_api.semantic_jobs import JOB_VIEW_COLUMNS


def test_semantic_job_query_matches_public_response_contract():
    selected = {column.strip() for column in JOB_VIEW_COLUMNS.replace("\n", "").split(",")}
    assert selected == set(SemanticSuggestionJobView.model_fields)
