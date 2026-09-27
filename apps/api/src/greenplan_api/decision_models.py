from __future__ import annotations

import json
from dataclasses import dataclass
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
