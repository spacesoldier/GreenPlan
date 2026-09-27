from io import BytesIO

import ezdxf
import pytest

from greenplan_api.intake_service import (
    candidate_score,
    detect_cad_format,
    dxf_inventory,
    media_kind_for,
    normalize_relative_path,
    store_stream,
    safe_archive_member,
)
from greenplan_api.classification import classify_delivery_path, needs_model_assist
from greenplan_api.decision_models import (
    DecisionProviderError,
    TypedChoiceQuestion,
    validate_typed_answers,
)
from greenplan_api.cad_assembly import assemble_xrefs, delivery_xref_resolver, xref_insertions


def test_relative_path_preserves_structure_and_rejects_escape():
    assert normalize_relative_path(r"Песчаный\ГР_Песчаный.dwg") == "Песчаный/ГР_Песчаный.dwg"
    with pytest.raises(ValueError):
        normalize_relative_path("../secret.dwg")
    with pytest.raises(ValueError):
        normalize_relative_path("/absolute.dwg")


def test_cad_detection_uses_content_not_extension():
    assert detect_cad_format(b"AC1032more bytes") == ("dwg", "AC1032")
    assert detect_cad_format(b"0\nSECTION\n2\nHEADER\n") == ("dxf", None)
    assert detect_cad_format(b"not actually cad") == ("unknown", None)


def test_content_store_is_deduplicated(tmp_path):
    first = store_stream(tmp_path, BytesIO(b"same payload"))
    second = store_stream(tmp_path, BytesIO(b"same payload"))
    assert first[:3] == second[:3]
    assert first[3] is False
    assert second[3] is True


def test_archive_member_path_cannot_escape_or_import_service_metadata():
    assert safe_archive_member("archive/xrefs/site.dwg") == "archive/xrefs/site.dwg"
    assert safe_archive_member("../secret.dwg") is None
    assert safe_archive_member("PaxHeaders.123/file.dwg") is None


def test_master_candidate_prefers_general_plan_over_xref():
    head_score, head_role, _ = candidate_score("Проект/ГР_Песчаный переулок.dwg")
    xref_score, xref_role, _ = candidate_score("Проект/xref/подложка.dwg")
    assert head_score > xref_score
    assert head_role == "project_head_candidate"
    assert xref_role == "cad_support"


def test_gp_filename_is_a_master_candidate():
    score, role, cues = candidate_score("улица Старый Гай_ГП.dwg")
    assert score >= 25
    assert role == "project_head_candidate"
    assert "гп в имени файла" in cues


def test_dxf_inventory_sees_model_layout_layers_hatch_and_xref(tmp_path):
    document = ezdxf.new("R2018")
    document.layers.add("GREEN")
    document.modelspace().add_circle((10, 20), 3, dxfattribs={"layer": "GREEN"})
    document.layouts.new("ГП-1")
    block = document.blocks.new("SITE_XREF")
    block.block.dxf.flags = 4
    block.block.dxf.xref_path = "xref/site.dwg"
    target = tmp_path / "plan.dxf"
    document.saveas(target)

    inventory = dxf_inventory(target)

    assert inventory["entity_count"] == 1
    assert inventory["entity_types"]["CIRCLE"] == 1
    assert inventory["layout_count"] == 2  # Layout1 plus ГП-1
    assert inventory["layer_entity_counts"]["GREEN"] == 1
    assert inventory["xrefs"][0]["path"] == "xref/site.dwg"


@pytest.mark.parametrize(
    ("path", "detected", "category"),
    [
        ("Проектное решение/DWG/Генеральный план.dwg", "dwg", "project_solution"),
        ("улица Старый Гай_ГП.dwg", "dwg", "project_solution"),
        ("Исходные данные/Геоподоснова.dwg", "dwg", "source_data"),
        ("Проектное решение/Xrefs/roads.dwg", "dwg", "xref_dependency"),
        ("Архив/вариант 2024.zip", "unknown", "archive"),
        ("Обследование/перечетная ведомость.xlsx", "unknown", "register"),
        ("Обследование/перечетная ведомость.xlsm", "unknown", "register"),
    ],
)
def test_delivery_classifier_is_explainable(path, detected, category):
    suggestion = classify_delivery_path(path, detected)
    assert suggestion.category == category
    assert suggestion.confidence >= 0.5
    assert suggestion.cues


@pytest.mark.parametrize(
    ("path", "media_kind"),
    [
        ("register.xls", "application/vnd.ms-excel"),
        ("register.xlsm", "application/vnd.ms-excel.sheet.macroEnabled.12"),
        ("register.xlsb", "application/vnd.ms-excel.sheet.binary.macroEnabled.12"),
        ("register.ods", "application/vnd.oasis.opendocument.spreadsheet"),
    ],
)
def test_spreadsheet_media_kinds(path, media_kind):
    assert media_kind_for(path, "unknown") == media_kind


def test_unclear_delivery_entry_is_sent_to_model_assist():
    suggestion = classify_delivery_path("misc/AB-42.bin")
    assert suggestion.category == "unknown"
    assert needs_model_assist(suggestion)


def test_typed_provider_rejects_unknown_labels_and_question_ids():
    questions = {
        "domain": TypedChoiceQuestion(
            instructions="Classify domain",
            choices={"vegetation": "Plants", "unknown": "Insufficient evidence"},
        )
    }
    valid = validate_typed_answers(
        {"answers": {"domain": {"choice": "vegetation", "confidence": 0.8,
                                 "probabilities": {"vegetation": 0.8, "unknown": 0.2}}}},
        questions,
    )
    assert valid["domain"].choice == "vegetation"

    with pytest.raises(DecisionProviderError):
        validate_typed_answers(
            {"answers": {"domain": {"choice": "transport", "confidence": 0.9,
                                     "probabilities": {"transport": 0.9}}}},
            questions,
        )
    with pytest.raises(DecisionProviderError):
        validate_typed_answers(
            {"answers": {"unexpected": {"choice": "vegetation", "confidence": 1.0}}},
            questions,
        )


def test_xref_assembly_embeds_child_and_preserves_insert_transform(tmp_path):
    child = ezdxf.new("R2018")
    child.modelspace().add_line((0, 0), (2, 0), dxfattribs={"layer": "ROAD"})
    child_path = tmp_path / "support" / "roads.dxf"
    child_path.parent.mkdir()
    child.saveas(child_path)

    head = ezdxf.new("R2018")
    block = head.blocks.new("ROADS")
    block.block.dxf.flags = 4
    block.block.dxf.xref_path = "support/roads.dwg"
    head.modelspace().add_blockref("ROADS", (10, 20), dxfattribs={"rotation": 90})
    head_path = tmp_path / "head.dxf"
    head.saveas(head_path)

    resolver = delivery_xref_resolver(
        {"head.dxf": head_path, "support/roads.dwg": child_path},
        {head_path.resolve(): "head.dxf", child_path.resolve(): "support/roads.dwg"},
    )
    assembled, manifest = assemble_xrefs(head_path, resolver)
    placements = xref_insertions(assembled, "ROADS")
    virtual = list(assembled.modelspace().query("INSERT")[0].virtual_entities())

    assert len(manifest.dependencies) == 1
    assert placements[0]["insert"][:2] == [10.0, 20.0]
    assert placements[0]["rotation"] == 90.0
    assert virtual[0].dxftype() == "LINE"
    assert tuple(round(value, 5) for value in list(virtual[0].dxf.start)[:2]) == (10.0, 20.0)
    assert tuple(round(value, 5) for value in list(virtual[0].dxf.end)[:2]) == (10.0, 22.0)
