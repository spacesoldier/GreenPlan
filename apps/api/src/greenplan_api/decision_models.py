from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Mapping
from urllib.request import Request, urlopen

from .classification import ClassificationSuggestion


DELIVERY_ROLE_CRITERIA = {
    "project_solution": "Проектное решение, генеральный план, дендроплан или итоговый чертёж",
    "source_data": "Исходные данные, геоподоснова, топосъёмка или материалы заказчика",
    "survey_existing": "Обследование существующего состояния или зелёных насаждений",
    "xref_dependency": "Внешняя CAD-ссылка или подложка, необходимая другому чертежу",
    "register": "Ведомость, опись, перечень или табличный реестр",
    "normative": "Норматив, СП, СНиП, ГОСТ или методический документ",
    "archive": "Архивная, устаревшая или резервная версия",
    "service_noise": "Служебные метаданные, временный файл или мусор",
    "unknown": "Недостаточно признаков для классификации",
}

CAD_LAYER_CATEGORY_CRITERIA = {
    "vegetation.tree": "Дерево",
    "vegetation.shrub": "Кустарник",
    "vegetation.grass": "Травянистая растительность и газон",
    "vegetation.mixed": "Смешанные зелёные насаждения",
    "structure.building": "Здание или строение",
    "structure.wall.external": "Наружная стена здания",
    "structure.support": "Опора, мачта, эстакада или мостовая опора",
    "structure.retaining_wall": "Подпорная стенка",
    "transport.road.carriageway": "Проезжая часть",
    "transport.road.edge": "Край проезжей части или укреплённой полосы обочины",
    "transport.road.curb": "Бортовой камень",
    "transport.pedestrian.path_edge": "Край тротуара или садовой дорожки",
    "transport.tram.track_edge": "Край трамвайного полотна",
    "transport.cycleway.edge": "Край велосипедной дорожки",
    "transport.ditch.edge": "Бровка канавы",
    "utility.unknown": "Инженерные сети, тип не уточнён",
    "utility.water.pipeline": "Водопровод",
    "utility.drainage.pipeline": "Дренаж или водосток",
    "utility.sewer.pipeline": "Канализация",
    "utility.heat.pipeline": "Тепловая сеть",
    "utility.gas.pipeline": "Газопровод",
    "utility.power.cable": "Силовой кабель",
    "utility.power.overhead": "Воздушная линия электропередачи",
    "utility.telecom.cable": "Кабель связи",
    "territory.work_boundary": "Граница работ",
    "territory.visibility_zone": "Треугольник или зона видимости",
    "territory.metro_technical_zone": "Техническая зона метрополитена",
    "territory.sanitary_protection_zone": "Санитарно-защитная зона",
    "territory.utility_protection_zone": "Охранная зона инженерной сети",
    "terrain.slope_toe": "Подошва откоса или бровка террасы",
    "terrain.groundwater_level": "Уровень грунтовых вод",
    "terrain": "Рельеф (тип не уточнён)",
    "not_applicable": "Текст, размер, рамка, штамп, легенда или служебная графика",
    "unknown": "Недостаточно данных или смешанное содержимое",
}

LAYER_FEATURE_ALLOWLIST = (
    "schema_version", "layer_name", "entity_types", "entity_count", "document_role", "relative_path",
)


CAD_LAYER_SEMANTIC_ALIASES: dict[str, tuple[str, ...]] = {
    "structure.building": (
        "навес", "навесы",
        "памятник", "памятники",
        "мост", "мосты",
        "павильон", "павильоны",
        "фонтан", "фонтаны",
        "ограда", "ограды", "ограждение", "ограждения",
        "вентилятор", "вентиляторы",
        "спецсооружение", "спецсооружения",
        "спец сооружение", "спец сооружения",
        "специальное сооружение", "специальные сооружения",
    ),
    "utility.power.overhead": (
        "возд линия", "возд линии", "воздушная линия", "воздушные линии",
    ),
    "utility.heat.pipeline": (
        "тепловая сеть", "тепловые сети", "теплосеть", "теплосети", "теплосетей",
        "теплотрасса", "теплотрассы", "теплопровод",
    ),
}


_AUTO_LAYER_PREFIXES = {
    "слой", "новый", "новая", "новое", "новые", "существующий", "существующая",
    "существующее", "проектируемый", "проектируемая", "проектируемое", "проектный",
    "проектная", "проектное", "планируемый", "планируемая", "планируемое",
}

def _normalise_category_text(value: str) -> str:
    tokens = re.sub(r"[^a-zа-я0-9]+", " ", value.casefold().replace("ё", "е")).split()
    tokens = [token for token in tokens if not token.isdigit()]
    while tokens and tokens[0] in _AUTO_LAYER_PREFIXES:
        tokens.pop(0)
    return " ".join(tokens)

def _category_aliases(code: str, description: str) -> tuple[str, ...]:
    if code == "not_applicable":
        base = ("текст", "размер", "рамка", "штамп", "легенда", "служебная графика")
    elif code == "utility.unknown":
        base = (
            "инженерная сеть", "инженерные сети",
            "инженерная коммуникация", "инженерные коммуникации",
            "подземная коммуникация", "подземные коммуникации",
            "трубопровод", "трубопроводы",
        )
    else:
        base = tuple(part.strip() for part in re.split(r"\s+или\s+", description) if part.strip())
    return tuple(dict.fromkeys((*base, *CAD_LAYER_SEMANTIC_ALIASES.get(code, ()))))

def canonical_layer_category_match(layer_name: str) -> tuple[str, float, str] | None:
    """Return only a unique, near-literal canonical class match safe for auto-confirmation."""
    name = _normalise_category_text(layer_name)
    if not name:
        return None
    name_tokens = set(name.split())
    candidates: list[tuple[float, str, str]] = []
    for code, description in CAD_LAYER_CATEGORY_CRITERIA.items():
        if code == "unknown":
            continue
        for raw_alias in _category_aliases(code, description):
            alias = _normalise_category_text(raw_alias)
            if not alias:
                continue
            alias_tokens = set(alias.split())
            if name == alias:
                score = 1.0
            elif alias_tokens.issubset(name_tokens) and len(name_tokens - alias_tokens) <= 2:
                score = 0.97 - 0.01 * len(name_tokens - alias_tokens)
            else:
                score = SequenceMatcher(None, name, alias).ratio()
                if score < 0.94:
                    continue
            candidates.append((score, code, alias))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    best_score, best_code, best_alias = candidates[0]
    competing = {code for score, code, _alias in candidates if best_score - score < 0.01}
    if len(competing) != 1:
        return None
    return best_code, best_score, f"Название слоя близко к каноническому классу: {best_alias}"


class DecisionProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TypedChoiceQuestion:
    instructions: str
    choices: Mapping[str, str]


@dataclass(frozen=True)
class TypedChoiceAnswer:
    choice: str
    confidence: float
    probabilities: dict[str, float]


def validate_typed_answers(
    result: object,
    questions: Mapping[str, TypedChoiceQuestion],
) -> dict[str, TypedChoiceAnswer]:
    """Validate a provider response before it can become an advisory suggestion."""
    try:
        payload = result if isinstance(result, dict) else {}
        raw_answers = payload["answers"]
        if not isinstance(raw_answers, dict) or set(raw_answers) != set(questions):
            raise ValueError("answer question ids do not match request")
        answers: dict[str, TypedChoiceAnswer] = {}
        for question_id, question in questions.items():
            raw = raw_answers[question_id]
            choice = str(raw["choice"])
            if choice not in question.choices:
                raise ValueError(f"unknown choice {choice!r} for {question_id!r}")
            probabilities = {str(key): float(value) for key, value in (raw.get("probabilities") or raw.get("probs") or {}).items()}
            if any(key not in question.choices for key in probabilities):
                raise ValueError(f"unknown probability label for {question_id!r}")
            confidence = float(raw.get("confidence", probabilities.get(choice, 0.0)))
            if not 0 <= confidence <= 1 or any(not 0 <= value <= 1 for value in probabilities.values()):
                raise ValueError("confidence and probabilities must be between 0 and 1")
            answers[question_id] = TypedChoiceAnswer(choice, confidence, probabilities)
        return answers
    except (KeyError, TypeError, ValueError) as exc:
        raise DecisionProviderError(f"invalid typed decision response: {exc}") from exc


def typed_decide(
    base_url: str,
    *,
    state: Mapping[str, object],
    questions: Mapping[str, TypedChoiceQuestion],
    timeout: float = 8.0,
    api_key: str | None = None,
) -> dict[str, TypedChoiceAnswer]:
    payload = {
        "state": dict(state),
        "questions": {
            key: {"type": "choice", "instructions": value.instructions, "criteria": dict(value.choices)}
            for key, value in questions.items()
        },
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        f"{base_url.rstrip('/')}/v1/systemone",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return validate_typed_answers(json.load(response), questions)
    except DecisionProviderError:
        raise
    except Exception as exc:
        raise DecisionProviderError(f"typed decision failed: {exc}") from exc


def laya_delivery_role(
    base_url: str,
    *,
    relative_path: str,
    detected_format: str,
    timeout: float = 8.0,
    api_key: str | None = None,
) -> ClassificationSuggestion:
    answers = typed_decide(
        base_url,
        state={"relative_path": relative_path, "detected_format": detected_format},
        questions={"delivery_role": TypedChoiceQuestion(
            instructions="Определи роль файла в архитектурно-ландшафтном CAD-проекте.",
            choices=DELIVERY_ROLE_CRITERIA,
        )},
        timeout=timeout,
        api_key=api_key,
    )
    answer = answers["delivery_role"]
    category = answer.choice
    probabilities = answer.probabilities
    confidence = answer.confidence
    alternatives = sorted(
        ((str(key), float(value)) for key, value in probabilities.items() if key != category),
        key=lambda item: -item[1],
    )[:3]
    return ClassificationSuggestion(
        category=category,
        confidence=max(0.0, min(1.0, confidence)),
        cues=("Laya typed choice",),
        alternatives=tuple(alternatives),
        method="laya-jev-http-v1",
    )


def laya_layer_category(
    base_url: str,
    *,
    feature_snapshot: Mapping[str, object],
    timeout: float = 20.0,
    api_key: str | None = None,
) -> ClassificationSuggestion:
    """Request an advisory category using only the approved CAD layer feature schema."""
    state = {key: feature_snapshot[key] for key in LAYER_FEATURE_ALLOWLIST if key in feature_snapshot}
    answers = typed_decide(
        base_url,
        state=state,
        questions={"object_class": TypedChoiceQuestion(
            instructions=(
                "Определи наиболее вероятную категорию слоя ландшафтного CAD-проекта. "
                "Не делай вывод по одной букве; при неоднозначности выбери unknown."
            ),
            choices=CAD_LAYER_CATEGORY_CRITERIA,
        )},
        timeout=timeout,
        api_key=api_key,
    )
    answer = answers["object_class"]
    alternatives = sorted(
        ((key, value) for key, value in answer.probabilities.items() if key != answer.choice),
        key=lambda item: -item[1],
    )[:3]
    return ClassificationSuggestion(
        category=answer.choice,
        confidence=answer.confidence,
        cues=("Laya multilingual typed choice",),
        alternatives=tuple(alternatives),
        method="laya-layer-jev-v1",
    )
