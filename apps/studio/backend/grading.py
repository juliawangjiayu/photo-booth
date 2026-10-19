"""Private Guess Where grading shared by local previews and future server APIs."""
from __future__ import annotations

import math


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
