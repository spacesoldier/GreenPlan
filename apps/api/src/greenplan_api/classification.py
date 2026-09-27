from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Iterable


@dataclass(frozen=True)
class ClassificationSuggestion:
    category: str
    confidence: float
    cues: tuple[str, ...]
    alternatives: tuple[tuple[str, float], ...] = ()
    method: str = "rules-v1"


def _normalized(value: str) -> str:
    return value.replace("\\", "/").casefold().replace("ё", "е")


def classify_delivery_path(path: str, detected_format: str = "unknown") -> ClassificationSuggestion:
    """Classify a delivery entry without mutating or moving the source file."""
    value = _normalized(path)
    name = PurePosixPath(value).name
    suffix = PurePosixPath(name).suffix
    scores: dict[str, float] = {
        "project_solution": 0.05,
        "source_data": 0.05,
        "survey_existing": 0.05,
        "xref_dependency": 0.05,
        "register": 0.05,
        "normative": 0.05,
        "archive": 0.05,
        "service_noise": 0.05,
        "unknown": 0.10,
    }
    cues: dict[str, list[str]] = {key: [] for key in scores}

    def add(category: str, points: float, reason: str) -> None:
        scores[category] += points
        cues[category].append(reason)

    tokens: tuple[tuple[str, str, float], ...] = (
        ("проектн", "project_solution", 0.62),
        ("генплан", "project_solution", 0.58),
        ("генеральный план", "project_solution", 0.62),
        ("дендроплан", "project_solution", 0.42),
        ("исходн", "source_data", 0.72),
        ("подоснов", "source_data", 0.62),
        ("топосъем", "source_data", 0.58),
        ("геоподоснов", "source_data", 0.62),
        ("обследован", "survey_existing", 0.65),
        ("существующ", "survey_existing", 0.48),
        ("перечет", "register", 0.82),
        ("ведомост", "register", 0.58),
        ("опись", "register", 0.56),
        ("норматив", "normative", 0.72),
        ("снип", "normative", 0.75),
        ("сп ", "normative", 0.42),
        ("/xref", "xref_dependency", 0.88),
        ("/xrefs", "xref_dependency", 0.88),
        ("внешн", "xref_dependency", 0.42),
        ("/архив", "archive", 0.88),
        ("/archive", "archive", 0.88),
        ("стар", "archive", 0.22),
    )
    for token, category, points in tokens:
        if token in value:
            add(category, points, token.strip("/ "))

    if suffix in {".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".xltm", ".csv", ".ods"}:
        add("register", 0.25, "tabular file")
    if detected_format in {"dwg", "dxf"} and re.search(r"(?:^|[_\s-])гп(?:[_\s.-]|$)", name):
        add("project_solution", 0.62, "ГП in CAD filename")
    if suffix in {".zip", ".rar", ".7z"}:
        add("archive", 0.48, "archive container")
    if name.startswith("paxheader/") or "/paxheader/" in value or name in {"thumbs.db", ".ds_store"}:
        add("service_noise", 0.95, "service metadata")
    if detected_format in {"dwg", "dxf"} and scores["project_solution"] <= 0.05:
        add("source_data", 0.10, "unclassified CAD")

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    category, raw = ordered[0]
    confidence = min(0.99, raw)
    if confidence < 0.35:
        category = "unknown"
        confidence = max(scores["unknown"], confidence)
    alternatives = tuple((key, round(min(value_score, 0.99), 3)) for key, value_score in ordered if key != category)[:3]
    return ClassificationSuggestion(
        category=category,
        confidence=round(confidence, 3),
        cues=tuple(cues[category]),
        alternatives=alternatives,
    )


def needs_model_assist(suggestion: ClassificationSuggestion, threshold: float = 0.72) -> bool:
    return suggestion.category == "unknown" or suggestion.confidence < threshold


def layer_input_text(layer_name: str, entity_types: Iterable[str]) -> str:
    kinds = ", ".join(sorted(set(entity_types)))
    return f"CAD layer: {layer_name}; entity types: {kinds or 'unknown'}"
