from io import BytesIO

import ezdxf
import pytest

from greenplan_api.intake_service import (
    candidate_score,
    compare_inventory_metrics,
    detect_cad_format,
    dxf_inventory,
    media_kind_for,
    normalize_relative_path,
    descendant_matches,
    store_stream,
    safe_archive_member,
)
from greenplan_api.classification import classify_delivery_path, needs_model_assist
from greenplan_api.decision_models import (
    CAD_LAYER_CATEGORY_CRITERIA,
    DecisionProviderError,
    TypedChoiceQuestion,
    canonical_layer_category_match,
    laya_layer_category,
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




def test_xref_prefers_unique_descendant_candidate_below_host_directory():
    source = "Улица/Проектное решение/DWG/head.dwg"
    nested = "Улица/Проектное решение/DWG/XREF/base.dwg"
    elsewhere = "Улица/Исходные данные/base.dwg"
    assert descendant_matches(source, [elsewhere, nested]) == [nested]


def test_xref_keeps_all_descendant_candidates_for_manual_choice():
    source = "Улица/Проектное решение/DWG/head.dwg"
    assert descendant_matches(source, ["Улица/Проектное решение/DWG/A/base.dwg", "Улица/Проектное решение/DWG/B/base.dwg"]) == ["Улица/Проектное решение/DWG/A/base.dwg", "Улица/Проектное решение/DWG/B/base.dwg"]



def test_fidelity_comparison_uses_only_metrics_available_on_both_sides():
    result = compare_inventory_metrics(
        {"entity_count": 12, "layer_count": 3},
        {"entity_count": 12, "layer_count": 4, "layout_count": 2},
    )
    assert result == {
        "comparable": True,
        "checked_fields": ["entity_count", "layer_count"],
        "differences": {"layer_count": {"source": 3, "converted": 4}},
    }


def test_fidelity_comparison_stays_not_comparable_without_shared_metrics():
    assert compare_inventory_metrics({"reader": "LibreDWG"}, {"entity_count": 12}) == {
        "comparable": False, "checked_fields": [], "differences": {},
    }

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


def test_canonical_layer_names_are_auto_confirmable_but_ambiguity_is_not():
    assert canonical_layer_category_match("Кабель связи")[:2] == ("utility.telecom.cable", 1.0)
    assert canonical_layer_category_match("Проектируемый водопровод")[0] == "utility.water.pipeline"
    assert canonical_layer_category_match("Водопровд")[0] == "utility.water.pipeline"
    assert canonical_layer_category_match("Инженерные сети")[0] == "utility.unknown"
    for name in ("Трубопроводы", "Подземные коммуникации", "Существующие подземные коммуникации"):
        assert canonical_layer_category_match(name)[0] == "utility.unknown"
    for name in ("Теплосеть", "Теплосети", "Тепловые сети", "Теплотрасса", "Теплопровод"):
        assert canonical_layer_category_match(name)[0] == "utility.heat.pipeline"
    for name in ("Возд линия", "Возд. линии", "Воздушная линия", "Воздушные линии", "Возд линии телеграф"):
        assert canonical_layer_category_match(name)[0] == "utility.power.overhead"
    for name in (
        "Навес", "Навесы", "Памятник", "Памятники", "Мост", "Мосты",
        "Павильон", "Павильоны", "Фонтан", "Фонтаны",
        "Ограда", "Ограды", "Вентилятор", "Вентиляторы",
        "Спецсооружение", "Спец. сооружения", "Специальное сооружение",
    ):
        assert canonical_layer_category_match(name)[0] == "structure.building"
    assert canonical_layer_category_match("Кабель связи силовой") is None
    assert canonical_layer_category_match("A-42-X") is None


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


def test_layer_provider_uses_allowlisted_snapshot_and_validates_category(monkeypatch):
    captured = {}

    def fake_decide(_url, *, state, questions, timeout, api_key):
        captured.update(state)
        assert set(questions["object_class"].choices) == set(CAD_LAYER_CATEGORY_CRITERIA)
        return {"object_class": type("Answer", (), {
            "choice": "utility.unknown", "confidence": 0.82,
            "probabilities": {"utility.unknown": 0.82, "unknown": 0.18},
        })()}

    monkeypatch.setattr("greenplan_api.decision_models.typed_decide", fake_decide)
    result = laya_layer_category(
        "http://laya:8000",
        feature_snapshot={
            "schema_version": "cad-layer-features-v1", "layer_name": "КЛ связи",
            "entity_types": {"LINE": 12}, "entity_count": 12,
            "document_role": "general_plan", "relative_path": "plan.dwg",
            "geometry": "must not leave the service", "secret": "no",
        },
    )
    assert result.category == "utility.unknown"
    assert result.confidence == 0.82
    assert "geometry" not in captured and "secret" not in captured
    assert set(captured) == {"schema_version", "layer_name", "entity_types", "entity_count", "document_role", "relative_path"}


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


def test_xref_assembly_records_engineer_waived_missing_reference(tmp_path):
    head = ezdxf.new("R2018")
    block = head.blocks.new("MISSING")
    block.block.dxf.flags = 4
    block.block.dxf.xref_path = "missing/reference.dwg"
    head.modelspace().add_blockref("MISSING", (0, 0))
    head_path = tmp_path / "head.dxf"
    head.saveas(head_path)

    assembled, manifest = assemble_xrefs(
        head_path,
        lambda _parent, _original: None,
        lambda _parent, original: original == "missing/reference.dwg",
    )

    assert assembled is not None
    assert manifest.dependencies == []
    assert manifest.skipped_unresolved == [{
        "parent": str(head_path.resolve()),
        "block": "MISSING",
        "path": "missing/reference.dwg",
    }]
