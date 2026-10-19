"""Private Guess Where grading shared by local previews and future server APIs."""
from __future__ import annotations

import json
import math
import os
from urllib.request import Request, urlopen

RESULTS = {"correct", "close", "incorrect"}


def grade_pin(answer_lat: float, answer_lng: float, guess_lat: float, guess_lng: float, radius_km: float) -> dict:
    """Grade a pin by great-circle distance from the private answer."""
    if radius_km <= 0:
        raise ValueError("Answer radius must be positive")
    phi1, phi2 = math.radians(answer_lat), math.radians(guess_lat)
    d_phi = math.radians(guess_lat - answer_lat)
    d_lam = math.radians(guess_lng - answer_lng)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    distance = 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    result = "correct" if distance <= radius_km else "close" if distance <= radius_km * 3 else "incorrect"
    raw_score = round(5000 * math.exp(-0.8 * max(0, distance / radius_km - 1)))
    if result == "correct":
        score = 5000
    elif result == "close":
        score = min(4999, max(1009, raw_score))
    else:
        score = min(1008, raw_score)
    return {
        "result": result,
        "score": score,
        "confidence": 1.0,
        "explanation": f"The pin is {distance:.1f} km from the answer.",
        "distance_km": round(distance, 3),
    }


def request_model(payload: dict, api_key: str, base_url: str) -> dict:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    req = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def grade_text(entry: dict, player_answer: str, requester=request_model) -> dict:
    api_key = os.environ.get("PHOTO_BOOTH_LLM_API_KEY", "").strip()
    model = os.environ.get("PHOTO_BOOTH_LLM_MODEL", "").strip()
    base_url = os.environ.get("PHOTO_BOOTH_LLM_BASE_URL", "https://api.openai.com/v1").strip()
    if not api_key or not model:
        raise RuntimeError("Set PHOTO_BOOTH_LLM_API_KEY and PHOTO_BOOTH_LLM_MODEL to enable text grading")
    system = (
        "Grade a geography-game text answer. Return JSON only with result (correct, close, or incorrect), "
        "score (an integer from 0 to 5000), confidence (0 to 1), and a short explanation. A correct answer "
        "must score 5000. A close answer must score from 1009 to 4999. An incorrect answer must score from "
        "0 to 1008. Treat aliases, translations, administrative hierarchy, and reasonable specificity "
        "consistently with the supplied coordinate radius."
    )
    private_context = {
        "canonicalPlace": entry["answer_name"],
        "authorDescription": entry.get("answer_description", ""),
        "latitude": entry["latitude"],
        "longitude": entry["longitude"],
        "correctRadiusKm": entry["answer_radius_km"],
        "closeRadiusKm": entry["answer_radius_km"] * 3,
        "playerAnswer": player_answer,
    }
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(private_context, ensure_ascii=False)},
        ],
    }
    try:
        response = requester(payload, api_key, base_url)
        content = response["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Language model did not return valid JSON grading data") from exc
    result = parsed.get("result")
    score = parsed.get("score")
    confidence = parsed.get("confidence")
    explanation = parsed.get("explanation")
    score_is_valid = (
        isinstance(score, (int, float))
        and not isinstance(score, bool)
        and float(score).is_integer()
        and 0 <= score <= 5000
        and (
            (result == "correct" and score == 5000)
            or (result == "close" and 1009 <= score <= 4999)
            or (result == "incorrect" and score <= 1008)
        )
    )
    if result not in RESULTS or not score_is_valid or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1 or not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("Language model returned an invalid grading result")
    return {
        "result": result,
        "score": int(score),
        "confidence": float(confidence),
        "explanation": explanation.strip()[:500],
    }
