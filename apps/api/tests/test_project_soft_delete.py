from greenplan_api.postgis_repository import PostgisRepository


def test_project_queries_exclude_soft_deleted_rows():
    repository = PostgisRepository("postgresql://unused")

    assert "p.deleted_at IS NULL" in repository._project_query()
    assert "p.deleted_at IS NULL" in repository._intake_query()
