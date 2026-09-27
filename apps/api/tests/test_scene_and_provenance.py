def first_project(client):
    return client.get("/v1/projects").json()["items"][0]


def test_features_require_bbox_for_non_small_model(client):
    model_id = first_project(client)["current_model_id"]

    response = client.get(f"/v1/models/{model_id}/features")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "bbox_required"


def test_invalid_bbox_and_lod_are_typed_client_errors(client):
    model_id = first_project(client)["current_model_id"]

    bad_bbox = client.get(f"/v1/models/{model_id}/features?bbox=10,10,5,5")
    bad_lod = client.get(f"/v1/models/{model_id}/features?bbox=0,0,100,100&lod=99")

    assert bad_bbox.status_code == 422
    assert bad_bbox.json()["error"]["code"] == "invalid_bbox"
    assert bad_lod.status_code == 422
    assert bad_lod.json()["error"]["code"] == "validation_error"


def test_bbox_returns_only_intersecting_features_and_preserves_unknown_state(client):
    model_id = first_project(client)["current_model_id"]

    response = client.get(f"/v1/models/{model_id}/features?bbox=0,0,60,60&lod=0")

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"] == model_id
    assert body["coordinate_space"]["unit"] == "metre"
    assert {feature["stable_key"] for feature in body["features"]} == {
        "building-a",
        "unknown-a",
    }
    unknown = next(item for item in body["features"] if item["stable_key"] == "unknown-a")
    assert unknown["semantic_status"] == "needs_review"
    assert unknown["class_code"] == "unknown.constraint"


def test_layer_filter_is_applied(client):
    model_id = first_project(client)["current_model_id"]

    response = client.get(
        f"/v1/models/{model_id}/features?bbox=0,0,100,100&layers=buildings&lod=1"
    )

    assert response.status_code == 200
    assert {item["class_code"] for item in response.json()["features"]} == {
        "structure.building"
    }


def test_feature_pages_do_not_overlap_and_signal_completion(client, repository):
    model_id = first_project(client)["current_model_id"]
    base = f"/v1/models/{model_id}/features?bbox=0,0,300,300&limit=1"

    first = client.get(base + "&offset=0")
    second = client.get(base + "&offset=1")
    final = client.get(base + "&offset=2")

    assert first.status_code == second.status_code == final.status_code == 200
    assert first.json()["features"][0]["id"] != second.json()["features"][0]["id"]
    assert first.json()["next_offset"] == 1
    assert second.json()["next_offset"] == 2
    assert final.json()["next_offset"] is None


def test_versioned_feature_pages_are_browser_cacheable(client):
    model_id = first_project(client)["current_model_id"]

    response = client.get(f"/v1/models/{model_id}/features?bbox=0,0,300,300&limit=1")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=300, stale-while-revalidate=3600"


def test_object_keeps_source_identity_and_conflicting_evidence(client):
    model_id = first_project(client)["current_model_id"]
    features = client.get(f"/v1/models/{model_id}/features?bbox=0,0,60,60").json()[
        "features"
    ]
    object_id = next(item["id"] for item in features if item["stable_key"] == "building-a")

    object_response = client.get(f"/v1/objects/{object_id}")
    evidence_response = client.get(f"/v1/objects/{object_id}/evidence")

    assert object_response.status_code == 200
    assert object_response.json()["source"]["asset_id"]
    assert object_response.json()["source"]["fragment_id"]
    assert object_response.json()["source"]["path"] == "ГП/План.dwg"
    evidence = evidence_response.json()["items"]
    heights = [item for item in evidence if item["attribute_name"] == "height_m"]
    assert len(heights) == 2
    assert {item["decision"] for item in heights} == {"candidate", "conflict"}
    assert {item["asserted_value"] for item in heights} == {12.0, 15.0}


def test_source_tree_uses_revision_identity_not_paths(client):
    project = first_project(client)

    response = client.get(
        f"/v1/project-revisions/{project['current_revision_id']}/source-tree"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision_id"] == project["current_revision_id"]
    assert body["nodes"][0]["id"]
    assert body["nodes"][0]["display_path"].endswith(".dwg")
