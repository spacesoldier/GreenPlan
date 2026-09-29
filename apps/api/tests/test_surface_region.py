from uuid import uuid4

from greenplan_api.models import SceneRoot, SurfaceRegionDetection


def test_surface_region_detection_uses_selected_root_and_seed(client, repository):
    model_id = next(iter(repository._manifests))
    root_id = uuid4()
    manifest = repository._manifests[model_id]
    repository._manifests[model_id] = manifest.model_copy(update={
        "roots": [SceneRoot(
            id=root_id,
            path="Проектное решение/plan.dwg",
            title="plan.dwg",
            role="effective_design",
            workspace_kind="project_solution",
            feature_count=1,
        )],
        "active_root_id": root_id,
    })
    calls = []

    def detect(request_model_id, request_root_id, x, y):
        calls.append((request_model_id, request_root_id, x, y))
        return SurfaceRegionDetection(
            model_id=request_model_id,
            root_id=request_root_id,
            seed=(x, y),
            geometry={"type": "Polygon", "coordinates": [[[10, 20], [12, 20], [12, 22], [10, 20]]]},
            area=2.0,
            confidence=0.82,
            edge_count=4,
            source="polygonized_surface_linework",
            contributing_classes=["transport.road.curb", "structure.building"],
        )

    repository.detect_surface_region = detect
    response = client.post(
        f"/v1/models/{model_id}/surface-regions:detect",
        json={"root_id": str(root_id), "x": 10.5, "y": 20.5},
    )

    assert response.status_code == 200
    assert response.json()["geometry"]["type"] == "Polygon"
    assert response.json()["root_id"] == str(root_id)
    assert calls == [(model_id, root_id, 10.5, 20.5)]


def test_surface_region_detection_returns_typed_not_found(client, repository):
    model_id = next(iter(repository._manifests))
    repository.detect_surface_region = lambda *_args: None

    response = client.post(
        f"/v1/models/{model_id}/surface-regions:detect",
        json={"x": 10.5, "y": 20.5},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "surface_region_not_found"
