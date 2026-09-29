from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .dxf_ingest import classify_layer


TAXONOMY_VERSION = "cad-v2-sp42"


@dataclass(frozen=True)
class AxisDecision:
    label: str
    confidence: float
    cues: tuple[str, ...] = ()


@dataclass(frozen=True)
class MultiAxisSuggestion:
    taxonomy_version: str
    domain: AxisDecision
    lifecycle: AxisDecision
    representation: AxisDecision
    object_class: AxisDecision
    document_role: AxisDecision
    review_required: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "taxonomy_version": self.taxonomy_version,
            "axes": {
                key: {"label": value.label, "confidence": value.confidence, "cues": list(value.cues)}
                for key, value in (
                    ("domain", self.domain), ("lifecycle", self.lifecycle),
                    ("representation", self.representation), ("object_class", self.object_class),
                    ("document_role", self.document_role),
                )
            },
            "review_required": self.review_required,
        }


def _match(value: str, mapping: Mapping[str, tuple[str, ...]]) -> list[str]:
    return [label for label, tokens in mapping.items() if any(token in value for token in tokens)]


def classify_layer_axes(
    layer_name: str,
    *,
    entity_types: Iterable[str] = (),
    document_role: str = "unknown",
) -> MultiAxisSuggestion:
    value = layer_name.casefold().replace("ё", "е")
    kinds = {kind.upper() for kind in entity_types}
    domain_matches = _match(value, {
        "vegetation": ("дерев", "кустар", "растен", "дендр", "газон", "озелен"),
        "transport": ("дорог", "тротуар", "проезд", "борт", "бордюр", "покрыт"),
        "utility": ("водопровод", "канализац", "водосток", "дренаж", "газопровод", "кабель", "мгтс", "теплосет"),
        "building": ("здан", "строен", "сооруж"),
        "terrain": ("рельеф", "горизонт", "отметк", "откос"),
        "boundary": ("границ", "красн", "участ"),
        "protection_zone": ("охран", "санитар"),
        "annotation": ("текст", "подпис", "размер", "легенд", "штамп"),
    })
    if len(domain_matches) > 1 and "annotation" in domain_matches:
        thematic = [item for item in domain_matches if item != "annotation"]
        domain_label = thematic[0] if len(thematic) == 1 else "mixed"
    else:
        domain_label = domain_matches[0] if len(domain_matches) == 1 else ("mixed" if domain_matches else "unknown")
    domain = AxisDecision(domain_label, 0.86 if domain_label not in {"unknown", "mixed"} else 0.25, tuple(domain_matches))

    lifecycle_matches = _match(value, {
        "proposed": ("проект", "посад", "нов", "п ", "_п_"),
        "existing": ("существ", "сущ", "обслед", "сохр"),
        "demolition": ("демонт", "снос", "удал", "выруб"),
        "replacement": ("замен", "пересад"),
        "reference": ("xref", "подоснов", "справоч"),
    })
    lifecycle_label = lifecycle_matches[0] if len(lifecycle_matches) == 1 else ("unknown" if not lifecycle_matches else "mixed")
    lifecycle = AxisDecision(lifecycle_label, 0.82 if lifecycle_label not in {"unknown", "mixed"} else 0.25, tuple(lifecycle_matches))

    if kinds and kinds <= {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}:
        representation_label, representation_confidence, representation_cues = "text", 0.98, ("text-only entities",)
    else:
        representation_matches = _match(value, {
            "crown": ("крон",), "hatch": ("штрих", "залив", "hatch"),
            "symbol": ("условн", "значок", "символ"), "text": ("текст", "подпис"),
            "dimension": ("размер",), "legend": ("легенд", "условные обознач"),
            "sheet_frame": ("штамп", "рамк"), "centerline": ("ось", "трасс"),
            "footprint": ("контур", "пятн"), "point": ("точк",),
            "construction": ("вспомог", "построен"),
        })
        representation_label = representation_matches[0] if len(representation_matches) == 1 else ("unknown" if not representation_matches else "mixed")
        representation_confidence = 0.85 if representation_label not in {"unknown", "mixed"} else 0.25
        representation_cues = tuple(representation_matches)
    representation = AxisDecision(representation_label, representation_confidence, representation_cues)

    flat = classify_layer(layer_name)
    physical = representation.label not in {"text", "dimension", "legend", "sheet_frame", "construction"}
    if not physical:
        object_class = AxisDecision("not_applicable", 0.99, ("non-physical representation",))
    elif flat.class_code == "unknown.constraint":
        object_class = AxisDecision("unknown", flat.confidence, (flat.reason,))
    else:
        object_class = AxisDecision(flat.class_code, flat.confidence, (flat.reason,))

    role = document_role if document_role else "unknown"
    document = AxisDecision(role, 1.0 if role not in {"unknown", "not_applicable"} else 0.25, ("document context",))
    review_required = any(
        axis.label in {"unknown", "mixed"} for axis in (domain, lifecycle, representation)
    ) or object_class.label == "unknown"
    return MultiAxisSuggestion(TAXONOMY_VERSION, domain, lifecycle, representation, object_class, document, review_required)


def feature_snapshot(**features: object) -> dict[str, object]:
    """Build the only state that a decision provider is allowed to receive."""
    allowed = ("layer_name", "entity_types", "entity_count", "document_role", "relative_path")
    return {"schema_version": "cad-layer-features-v1", **{key: features[key] for key in allowed if key in features}}
