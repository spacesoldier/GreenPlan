from greenplan_api.semantic_taxonomy import classify_layer_axes, feature_snapshot


def test_taxonomy_keeps_domain_lifecycle_and_representation_independent():
    result = classify_layer_axes(
        "ПРОЕКТ_ДЕРЕВЬЯ_КРОНЫ",
        entity_types=["LWPOLYLINE", "HATCH"],
        document_role="general_plan",
    )

    assert result.domain.label == "vegetation"
    assert result.lifecycle.label == "proposed"
    assert result.representation.label == "crown"
    assert result.document_role.label == "general_plan"
    assert result.object_class.label == "vegetation.proposed.tree"


def test_utility_annotation_does_not_become_pipeline_geometry():
    result = classify_layer_axes("ТЕКСТ_ВОДОПРОВОД", entity_types=["TEXT", "MTEXT"])

    assert result.domain.label == "utility"
    assert result.representation.label == "text"
    assert result.object_class.label == "not_applicable"


def test_unknown_and_mixed_layers_require_review():
    unknown = classify_layer_axes("A-42-X", entity_types=["LINE"])
    mixed = classify_layer_axes("ДОРОГИ_ГАЗОПРОВОД", entity_types=["LINE"])

    assert unknown.domain.label == "unknown"
    assert unknown.review_required is True
    assert mixed.review_required is True
    assert mixed.domain.label == "mixed"


def test_external_feature_snapshot_uses_an_explicit_allowlist():
    snapshot = feature_snapshot(
        layer_name="Деревья",
        entity_types={"CIRCLE": 14},
        entity_count=14,
        document_role="general_plan",
        relative_path="Проект/ГП.dwg",
        forbidden_geometry={"coordinates": [1, 2]},
        personal_data="secret",
    )

    assert snapshot == {
        "schema_version": "cad-layer-features-v1",
        "layer_name": "Деревья",
        "entity_types": {"CIRCLE": 14},
        "entity_count": 14,
        "document_role": "general_plan",
        "relative_path": "Проект/ГП.dwg",
    }
