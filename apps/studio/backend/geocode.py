"""Low-volume, user-initiated location lookup using complementary OSM services."""
from __future__ import annotations
import json
import re
import ssl
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi

_lock = threading.Lock()
_last_request = 0.0
_cache: dict[str, object] = {}
_ssl_context = ssl.create_default_context(cafile=certifi.where())
_GENERIC_STATION_TERMS = {"缆车站", "纜車站", "火车站", "火車站", "地铁站", "地鐵站", "车站", "車站", "公交站"}
_GENERIC_PLACE_TERMS = {
    "美术馆": "museum",
    "美術館": "museum",
    "博物馆": "museum",
    "博物館": "museum",
}
_ADMIN_SUFFIXES = ("特别行政区", "特別行政區", "自治区", "自治區", "省", "市", "区", "區", "县", "縣")


def request_json(url: str):
    global _last_request
    if "nominatim.openstreetmap.org" in url:
        with _lock:
            delay = max(0, 1.05 - (time.monotonic() - _last_request))
            if delay:
                time.sleep(delay)
            _last_request = time.monotonic()
    req = Request(url, headers={"User-Agent": "PhotoBoothLocal/0.1 (personal photo library, https://github.com)", "Accept": "application/json"})
    with urlopen(req, timeout=9, context=_ssl_context) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_nominatim(row: dict) -> dict:
    a = row.get("address") or {}
    return {
        "name": row.get("display_name", ""),
        "latitude": float(row["lat"]), "longitude": float(row["lon"]),
        "country": a.get("country", ""),
        "region": a.get("state", "") or a.get("province", "") or a.get("region", ""),
        "city": a.get("city", "") or a.get("town", "") or a.get("village", "") or a.get("municipality", "") or a.get("county", ""),
        "district": a.get("city_district", "") or a.get("suburb", "") or a.get("borough", "") or a.get("neighbourhood", ""),
    }


def normalize_photon(feature: dict) -> dict:
    properties = feature.get("properties") or {}
    coordinates = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coordinates) < 2:
        raise ValueError("Photon result has no coordinates")

    street = " ".join(str(value).strip() for value in (properties.get("housenumber"), properties.get("street")) if value)
    parts = [
        properties.get("name", ""),
        street,
        properties.get("district", ""),
        properties.get("city", "") or properties.get("county", ""),
        properties.get("state", ""),
        properties.get("country", ""),
    ]
    display_parts: list[str] = []
    for part in parts:
        text = str(part).strip()
        if text and text.casefold() not in {existing.casefold() for existing in display_parts}:
            display_parts.append(text)

    return {
        "name": ", ".join(display_parts),
        "latitude": float(coordinates[1]),
        "longitude": float(coordinates[0]),
        "country": properties.get("country", ""),
        "region": properties.get("state", ""),
        "city": properties.get("city", "") or properties.get("county", ""),
        "district": properties.get("district", "") or properties.get("locality", ""),
    }


def merge_places(*groups: list[dict], limit: int = 8) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[float, float]] = set()
    max_group_size = max((len(group) for group in groups), default=0)
    for index in range(max_group_size):
        for group in groups:
            if index >= len(group):
                continue
            place = group[index]
            key = (round(place["latitude"], 5), round(place["longitude"], 5))
            if key in seen:
                continue
            seen.add(key)
            merged.append(place)
            if len(merged) == limit:
                return merged
    return merged


def broader_query(query: str) -> str:
    parts = query.strip().split()
    if len(parts) < 2:
        return ""

    place_category = _GENERIC_PLACE_TERMS.get(parts[-1])
    if place_category:
        return f"{place_category}, {' '.join(parts[:-1])}"

    if parts[-1] in _GENERIC_STATION_TERMS:
        location = parts[-2]
        if re.fullmatch(r"[\u3400-\u9fff]+", location) and len(location) > 2:
            location = location[-2:]
        return " ".join([*parts[:-2], location, "station"])

    broadened = list(parts)
    if re.fullmatch(r"[\u3400-\u9fff]+", broadened[0]):
        for suffix in _ADMIN_SUFFIXES:
            if broadened[0].endswith(suffix) and len(broadened[0]) - len(suffix) >= 2:
                broadened[0] = broadened[0][:-len(suffix)]
                break
    for index in range(1, len(broadened)):
        part = broadened[index]
        if re.fullmatch(r"[\u3400-\u9fff]+", part) and part.endswith("站") and len(part) > 2:
            broadened[index] = part[:-1]

    result = " ".join(broadened)
    return result if result.casefold() != query.strip().casefold() else ""


def search_once(query: str) -> tuple[list[dict], list[Exception]]:
    nominatim_url = "https://nominatim.openstreetmap.org/search?" + urlencode({
        "q": query,
        "format": "jsonv2",
        "limit": 8,
        "addressdetails": 1,
        "namedetails": 1,
        "accept-language": "zh-CN,zh,en",
    })
    photon_url = "https://photon.komoot.io/api/?" + urlencode({"q": query, "limit": 8})

    groups: list[list[dict]] = []
    failures: list[Exception] = []
    try:
        groups.append([normalize_nominatim(row) for row in request_json(nominatim_url)])
    except Exception as exc:
        failures.append(exc)
    try:
        photon_data = request_json(photon_url)
        groups.append([normalize_photon(feature) for feature in photon_data.get("features", [])])
    except Exception as exc:
        failures.append(exc)

    if not groups:
        raise RuntimeError("All location services are unavailable") from failures[0]

    return merge_places(*groups), failures


def forward(query: str) -> list[dict]:
    normalized_query = query.strip()
    key = "q:" + normalized_query.lower()
    if key in _cache:
        return _cache[key]  # type: ignore

    result, failures = search_once(normalized_query)
    fallback_query = broader_query(normalized_query)
    if fallback_query:
        fallback_result, fallback_failures = search_once(fallback_query)
        failures.extend(fallback_failures)
        if fallback_result:
            result = [{**place, "match_quality": "broader"} for place in fallback_result]

    if result and not failures:
        _cache[key] = result
    return result


def reverse(latitude: float, longitude: float) -> dict:
    key = f"reverse:{latitude:.5f}:{longitude:.5f}"
    if key in _cache:
        return _cache[key]  # type: ignore
    url = "https://nominatim.openstreetmap.org/reverse?" + urlencode({"lat": latitude, "lon": longitude, "format": "jsonv2", "zoom": 13, "addressdetails": 1})
    data = request_json(url)
    result = normalize_nominatim(data)
    _cache[key] = result
    return result
