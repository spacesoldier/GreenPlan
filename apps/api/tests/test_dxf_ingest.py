from collections import Counter

import ezdxf

from greenplan_api.dxf_ingest import (
    classify_layer,
    entity_to_geojson,
    iter_primitives,
    select_layer_entities,
)
from greenplan_api.import_pilots import geometry_role, layer_caps


def test_insert_children_inherit_parent_layer_and_transform():
    doc = ezdxf.new("R2018")
    block = doc.blocks.new("TREE")
    block.add_circle((0, 0), radius=2, dxfattribs={"layer": "0"})
    block.add_line((-2, 0), (2, 0), dxfattribs={"layer": "CROWN_DETAIL"})
    doc.modelspace().add_blockref(
        "TREE", (100, 200), dxfattribs={"layer": "04 Дендроплан (растения)"}
    )

    primitives = list(iter_primitives(doc.modelspace()))

    assert [item.effective_layer for item in primitives] == [
        "04 Дендроплан (растения)",
        "CROWN_DETAIL",
    ]
    circle = entity_to_geojson(primitives[0].entity)
    assert circle is not None
    xs = [point[0] for point in circle["coordinates"][0]]
    ys = [point[1] for point in circle["coordinates"][0]]
    assert min(xs) == 98
    assert max(xs) == 102
    assert min(ys) == 198
    assert max(ys) == 202


def test_layer_semantics_are_explainable_and_unknown_stays_unknown():
    assert classify_layer("Новый_Водопровод_Ном._пера__243").class_code == "utility.water.pipeline"
    assert classify_layer("Кабель связи МГТС").class_code == "utility.telecom.cable"
    assert classify_layer("ДВ_ГП_П_Граница работ").class_code == "territory.work_boundary"
    assert classify_layer("04 Дендроплан (растения)").class_code == "vegetation.existing"
    unknown = classify_layer("Новый_! Съемка_Ном._пера__95")
    assert unknown.class_code == "unknown.constraint"
    assert unknown.semantic_status == "needs_review"
    assert unknown.confidence < 0.5


def test_geometry_conversion_supports_core_dxf_primitives():
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    entities = [
        msp.add_line((0, 0), (2, 3)),
        msp.add_lwpolyline([(0, 0), (3, 0), (3, 3)], close=True),
        msp.add_arc((10, 10), 5, 0, 90),
        msp.add_point((7, 8)),
    ]

    geometries = [entity_to_geojson(entity) for entity in entities]

    assert [item["type"] for item in geometries if item] == [
        "LineString",
        "Polygon",
        "LineString",
        "Point",
    ]
    assert geometries[1]["coordinates"][0][0] == geometries[1]["coordinates"][0][-1]


def test_heavy_layer_sampling_is_deterministic_and_keeps_coverage():
    records = [(f"h-{index}", index) for index in range(100)]

    first = select_layer_entities(records, limit=10)
    second = select_layer_entities(records, limit=10)

    assert first == second
    assert len(first) == 10
    assert first[0] == records[0]
    assert first[-1] == records[-1]
    assert Counter(value // 10 for _, value in first).keys() == set(range(10))


def test_unlimited_import_keeps_every_supported_primitive():
    counts = Counter({"survey": 100_000, "trees": 12_000})

    assert layer_caps(counts, max_total=0) == counts
    assert layer_caps(counts, max_total=200_000) == counts


def test_vegetation_circle_is_a_position_marker_below_crown_linework():
    assert geometry_role("vegetation.existing.tree", "Polygon", "CIRCLE") == "position"
    assert geometry_role("vegetation.existing.tree", "LineString", "SPLINE") == "crown"
