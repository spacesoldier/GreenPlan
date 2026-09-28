from uuid import UUID


EXPECTED_ROUTES = {
    "/health/live",
    "/health/ready",
    "/v1/projects",
    "/v1/projects/{project_id}",
    "/v1/projects/{project_id}/models",
    "/v1/project-revisions/{revision_id}/source-tree",
    "/v1/models/{model_id}/scene-manifest",
    "/v1/models/{model_id}/features",
    "/v1/objects/{object_id}",
    "/v1/objects/{object_id}/evidence",
}


def test_liveness_is_independent_from_repository(client, repository):
    repository.available = False

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "greenplan-api", "version": "0.1.0"}


def test_readiness_reports_repository_failure(client, repository):
    repository.available = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "repository_unavailable"


def test_openapi_exposes_phase_two_contract(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert EXPECTED_ROUTES <= set(response.json()["paths"])


def test_openapi_exposes_project_soft_delete(client):
    response = client.get("/openapi.json")

    assert "delete" in response.json()["paths"]["/v1/intake/projects/{project_id}"]


def test_openapi_exposes_cad_workbench_review_operations(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/v1/intake/projects/{project_id}/classifications/batch-review"]
    assert "post" in paths["/v1/intake/projects/{project_id}/findings/{finding_id}/resolve"]


def test_openapi_exposes_background_semantic_suggestions(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/v1/intake/projects/{project_id}/semantic-suggestion-jobs"]
    assert "get" in paths["/v1/intake/projects/{project_id}/semantic-suggestion-jobs/{job_id}"]


def test_invalid_uuid_uses_stable_error_envelope(client):
    response = client.get("/v1/projects/not-a-uuid")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["correlation_id"]


def test_project_list_contains_both_pilots_and_explicit_versions(client):
    response = client.get("/v1/projects")

    assert response.status_code == 200
    body = response.json()
    assert body["resource_version"] == "1"
    assert {item["code"] for item in body["items"]} == {"peschanaya", "kulikovskaya"}
    for item in body["items"]:
        UUID(item["id"])
        UUID(item["current_revision_id"])
        UUID(item["current_model_id"])
        assert item["model_version"] == 1


def test_project_detail_exposes_revision_assembly_and_crs(client):
    project = client.get("/v1/projects").json()["items"][0]

    response = client.get(f"/v1/projects/{project['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["current_revision_id"] == project["current_revision_id"]
    assert body["current_model_id"] == project["current_model_id"]
    assert body["assembly_status"] == "needs_review"
    assert body["coordinate_space"]["status"] == "candidate"
    assert body["coordinate_space"]["unit"] == "metre"


def test_explicit_unknown_model_is_not_replaced_with_latest(client):
    response = client.get("/v1/models/ffffffff-ffff-4fff-8fff-ffffffffffff/scene-manifest")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"


def test_scene_manifest_exposes_persisted_spatial_focus(client):
    project = client.get("/v1/projects").json()["items"][0]

    response = client.get(f"/v1/models/{project['current_model_id']}/scene-manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["extent"] == [0.0, 0.0, 500.0, 300.0]
    assert body["spatial_focus"] == {
        "extent": [10.0, 10.0, 240.0, 240.0],
        "center": [125.0, 125.0],
        "method": "fixture_primary_cluster",
        "algorithm_version": "1",
        "object_count": 3,
        "total_object_count": 3,
        "coverage": 1.0,
    }
