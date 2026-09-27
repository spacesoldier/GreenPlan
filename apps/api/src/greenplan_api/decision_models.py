from __future__ import annotations

import json
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


def laya_delivery_role(
    base_url: str,
    *,
    relative_path: str,
    detected_format: str,
    timeout: float = 8.0,
    api_key: str | None = None,
) -> ClassificationSuggestion:
    payload = {
        "state": {"relative_path": relative_path, "detected_format": detected_format},
        "questions": {
            "delivery_role": {
                "type": "choice",
                "instructions": "Определи роль файла в архитектурно-ландшафтном CAD-проекте.",
                "criteria": DELIVERY_ROLE_CRITERIA,
            }
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
            result = json.load(response)
        answer = result["answers"]["delivery_role"]
        category = str(answer["choice"])
        if category not in DELIVERY_ROLE_CRITERIA:
            raise KeyError(category)
        probabilities = answer.get("probabilities") or answer.get("probs") or {}
        confidence = float(answer.get("confidence", probabilities.get(category, 0.0)))
    except Exception as exc:
        raise DecisionProviderError(f"Laya decision failed: {exc}") from exc
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
