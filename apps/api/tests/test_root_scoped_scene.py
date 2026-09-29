from dataclasses import replace
from uuid import uuid4

from greenplan_api.models import SceneRoot


def _rooted_repository(repository):
    model_id = next(iter(repository._manifests))
    design_id = uuid4()
    source_id = uuid4()
    manifest = repository._manifests[model_id]
    repository._manifests[model_id] = manifest.model_copy(update={
        "roots": [
            SceneRoot(id=source_id, path="Исходные данные/base.dwg", title="base.dwg", role="reference_context", workspace_kind="source_data", feature_count=1),
            SceneRoot(id=design_id, path="Проектное решение/plan.dwg", title="plan.dwg", role="effective_design", workspace_kind="project_solution", feature_count=2),
        ],
        "active_root_id": None,
    })
    rooted = []
    for index, record in enumerate(repository._features):
        root_id = design_id if index < 2 else source_id
        feature = record.feature.model_copy(update={
            "properties": {**record.feature.properties, "publication_root_id": str(root_id)},
        })
        rooted.append(replace(record, feature=feature))
    repository._features = rooted
    return model_id, design_id, source_id


def test_manifest_defaults_to_effective_design_root(client, repository):
    model_id, design_id, _source_id = _rooted_repository(repository)

    response = client.get(f"/v1/models/{model_id}/scene-manifest")

    assert response.status_code == 200
    assert response.json()["active_root_id"] == str(design_id)
    assert [item["workspace_kind"] for item in response.json()["roots"]] == [
        "source_data", "project_solution",
    ]


def test_features_are_scoped_to_requested_root(client, repository):
    model_id, _design_id, source_id = _rooted_repository(repository)

    response = client.get(f"/v1/models/{model_id}/features?bbox=0,0,300,300&root_id={source_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["active_root_id"] == str(source_id)
    assert body["features"]
    assert {item["properties"]["publication_root_id"] for item in body["features"]} == {str(source_id)}


def test_unknown_publication_root_is_typed_not_found(client, repository):
    model_id, _design_id, _source_id = _rooted_repository(repository)

    response = client.get(f"/v1/models/{model_id}/scene-manifest?root_id={uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "publication_root_not_found"
