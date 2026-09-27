from uuid import UUID

from .models import (
    CoordinateSpace,
    Evidence,
    Feature,
    ModelSummary,
    ObjectDetail,
    ProjectDetail,
    SceneLayer,
    SceneManifest,
    SceneSpatialFocus,
    SourceNode,
    SourceReference,
    SourceTree,
)
from .repository import FeatureRecord, InMemoryRepository


def uid(value: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{value:012d}")


def fixture_repository() -> InMemoryRepository:
    coordinate_spaces = [
        CoordinateSpace(id=uid(101), kind="cad_local", unit="metre", status="candidate"),
        CoordinateSpace(id=uid(102), kind="local_metric", unit="metre", status="verified"),
    ]
    projects = [
        ProjectDetail(
            id=uid(1),
            code="peschanaya",
            title="Песчаный переулок",
            status="active",
            current_revision_id=uid(11),
            current_model_id=uid(21),
            model_version=1,
            assembly_status="needs_review",
            crs_status="candidate",
            revision_no=1,
            coordinate_space=coordinate_spaces[0],
            quality={"needs_review": 1, "conflicts": 1, "semantic_coverage": 0.72},
        ),
        ProjectDetail(
            id=uid(2),
            code="kulikovskaya",
            title="Куликовская улица",
            status="active",
            current_revision_id=uid(12),
            current_model_id=uid(22),
            model_version=1,
            assembly_status="needs_review",
            crs_status="verified",
            revision_no=1,
            coordinate_space=coordinate_spaces[1],
            quality={"needs_review": 2, "conflicts": 0, "semantic_coverage": 0.64},
        ),
    ]
    models = [
        ModelSummary(
            id=project.current_model_id,
            project_revision_id=project.current_revision_id,
            version=project.model_version,
            kind="combined",
            assembly_status=project.assembly_status,
            coordinate_space=project.coordinate_space,
        )
        for project in projects
    ]
    manifests = [
        SceneManifest(
            model_id=project.current_model_id,
            model_version=1,
            coordinate_space=project.coordinate_space,
            extent=(0, 0, 500, 300),
            spatial_focus=SceneSpatialFocus(
                extent=(10, 10, 240, 240),
                center=(125, 125),
                method="fixture_primary_cluster",
                algorithm_version="1",
                object_count=3,
                total_object_count=3,
                coverage=1,
            ),
            layers=[
                SceneLayer(
                    id="buildings",
                    title="Здания",
                    class_codes=["structure.building"],
                    geometry_roles=["footprint"],
                    feature_count=720,
                ),
                SceneLayer(
                    id="constraints",
                    title="Ограничения и неизвестные объекты",
                    class_codes=["unknown.constraint", "utility.water.pipeline"],
                    geometry_roles=["centerline", "footprint"],
                    feature_count=11280,
                ),
            ],
            issues={"needs_review": int(project.quality["needs_review"]), "conflict": int(project.quality["conflicts"])},
            feature_count=12000,
        )
        for project in projects
    ]

    source_asset = uid(501)
    source_fragment = uid(511)
    source = SourceReference(
        asset_id=source_asset,
        fragment_id=source_fragment,
        path="ГП/План.dwg",
        layer="ЗДАНИЯ",
        handle="A12",
    )

    def make_record(
        *,
        object_id: UUID,
        model_id: UUID,
        stable_key: str,
        class_code: str,
        layer_id: str,
        semantic_status: str,
        bbox: tuple[float, float, float, float],
        geometry: dict,
        name: str,
    ) -> FeatureRecord:
        feature = Feature(
            id=object_id,
            stable_key=stable_key,
            class_code=class_code,
            layer_id=layer_id,
            name=name,
            lifecycle="existing",
            semantic_status=semantic_status,
            confidence=0.97 if semantic_status == "confirmed" else 0.35,
            geometry_role="footprint",
            geometry=geometry,
        )
        return FeatureRecord(
            model_id=model_id,
            bbox=bbox,
            feature=feature,
            detail=ObjectDetail(
                **feature.model_dump(), model_id=model_id, source=source
            ),
        )

    building_id = uid(301)
    feature_records = [
        make_record(
            object_id=building_id,
            model_id=uid(21),
            stable_key="building-a",
            class_code="structure.building",
            layer_id="buildings",
            semantic_status="confirmed",
            bbox=(10, 10, 30, 30),
            geometry={"type": "Polygon", "coordinates": [[[10, 10], [30, 10], [30, 30], [10, 30], [10, 10]]]},
            name="Корпус 1",
        ),
        make_record(
            object_id=uid(302),
            model_id=uid(21),
            stable_key="unknown-a",
            class_code="unknown.constraint",
            layer_id="constraints",
            semantic_status="needs_review",
            bbox=(45, 20, 55, 40),
            geometry={"type": "LineString", "coordinates": [[45, 20], [55, 40]]},
            name="Неопознанная линия",
        ),
        make_record(
            object_id=uid(303),
            model_id=uid(21),
            stable_key="building-far",
            class_code="structure.building",
            layer_id="buildings",
            semantic_status="confirmed",
            bbox=(200, 200, 240, 240),
            geometry={"type": "Polygon", "coordinates": [[[200, 200], [240, 200], [240, 240], [200, 240], [200, 200]]]},
            name="Корпус 2",
        ),
        make_record(
            object_id=uid(304),
            model_id=uid(22),
            stable_key="kulikovskaya-building-a",
            class_code="structure.building",
            layer_id="buildings",
            semantic_status="confirmed",
            bbox=(15, 15, 35, 35),
            geometry={"type": "Polygon", "coordinates": [[[15, 15], [35, 15], [35, 35], [15, 35], [15, 15]]]},
            name="Жилой дом",
        ),
    ]
    evidence = {
        building_id: [
            Evidence(
                id=uid(601),
                role="attribute",
                attribute_name="height_m",
                asserted_value=12.0,
                method="cad_attribute",
                confidence=0.8,
                decision="candidate",
                source_fragment_id=source_fragment,
            ),
            Evidence(
                id=uid(602),
                role="contradiction",
                attribute_name="height_m",
                asserted_value=15.0,
                method="project_note",
                confidence=0.7,
                decision="conflict",
                source_fragment_id=source_fragment,
            ),
        ]
    }
    source_trees = [
        SourceTree(
            revision_id=project.current_revision_id,
            nodes=[
                SourceNode(
                    id=source_asset if index == 0 else uid(502),
                    kind="file",
                    title="План.dwg",
                    display_path="ГП/План.dwg",
                    media_type="image/vnd.dwg",
                    availability_status="available",
                )
            ],
        )
        for index, project in enumerate(projects)
    ]
    return InMemoryRepository(
        projects=projects,
        models=models,
        manifests=manifests,
        features=feature_records,
        evidence=evidence,
        source_trees=source_trees,
    )
