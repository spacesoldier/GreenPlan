from pathlib import Path

import ezdxf

from greenplan_api.import_plant_symbols import candidate_kind, extract_library_manifest, normalize_name


def test_name_normalization_keeps_source_semantics() -> None:
    assert normalize_name("Клён_красный 10") == "клен красный"
    assert candidate_kind("Клен Гиннала") == "plant"
    assert candidate_kind("A$C3AC663BE") == "service"
    assert candidate_kind("Дерево_Х_С") == "generic_vegetation"


def test_manifest_preserves_fill_style_attributes_and_nested_blocks(tmp_path: Path) -> None:
    document = ezdxf.new("R2018")
    nested = document.blocks.new("ветка")
    nested.add_line((0, 0), (1, 1))
    plant = document.blocks.new("Клён_красный 10")
    plant.add_circle((0, 0), 2, dxfattribs={"layer": "контур", "color": 3})
    hatch = plant.add_hatch(color=5, dxfattribs={"layer": "заливка", "true_color": 0x55AA33})
    hatch.paths.add_polyline_path([(0, 0), (1, 0), (1, 1), (0, 1)], is_closed=True)
    plant.add_blockref("ветка", (0, 0))
    plant.add_attdef("PORODA", (0, 0), "Клён красный")
    insert = document.modelspace().add_blockref("Клён_красный 10", (10, 20))
    insert.add_attrib("PORODA", "Клён красный")
    path = tmp_path / "symbols.dxf"
    document.saveas(path)

    manifest = extract_library_manifest(path)

    assert manifest["insert_count"] == 1
    assert len(manifest["symbols"]) == 1
    symbol = manifest["symbols"][0]
    assert symbol["normalized_name"] == "клен красный"
    assert symbol["entity_types"] == {"CIRCLE": 1, "HATCH": 1, "INSERT": 1, "ATTDEF": 1}
    assert symbol["hatch_summary"]["count"] == 1
    assert symbol["hatch_summary"]["boundary_path_count"] == 1
    assert symbol["nested_blocks"] == [{"name": "ветка", "insert_count": 1}]
    assert symbol["attribute_schema"][0]["tag"] == "PORODA"
    assert symbol["attribute_examples"] == [{"PORODA": "Клён красный"}]
