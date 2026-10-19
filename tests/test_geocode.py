from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
STUDIO_PARENT = ROOT / "apps" / "studio"
if str(STUDIO_PARENT) not in sys.path:
    sys.path.insert(0, str(STUDIO_PARENT))


NOMINATIM_RESULT = {
    "display_name": "上海外滩美术馆, 20, 虎丘路, 上海市, 中国",
    "lat": "31.2431755",
    "lon": "121.4830203",
    "address": {
        "country": "中国",
        "state": "上海市",
        "city": "上海市",
        "suburb": "外滩街道",
    },
}

PHOTON_DUPLICATE = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [121.4830203, 31.2431755]},
    "properties": {
        "name": "上海外滩美术馆",
        "housenumber": "20",
        "street": "虎丘路",
        "district": "外滩街道",
        "city": "上海市",
        "state": "上海市",
        "country": "中国",
    },
}

PHOTON_FUZZY_RESULT = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [121.4337292, 31.2062561]},
    "properties": {
        "name": "武康大楼",
        "housenumber": "1850",
        "street": "武康路",
        "district": "湖南路街道",
        "city": "徐汇区",
        "state": "上海市",
        "country": "中国",
    },
}

PHOTON_PEAK_TRAM_RESULT = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [114.1519796, 22.27093]},
    "properties": {
        "name": "山頂纜車",
        "street": "白加道",
        "district": "山頂",
        "city": "香港",
        "state": "香港",
        "country": "中国",
    },
}

NOMINATIM_PEAK_STATION_RESULT = {
    "display_name": "山頂, 芬梨道, 爐峰峽, 中西區, 香港島, 香港, 中国",
    "lat": "22.2711230",
    "lon": "114.1501414",
    "address": {
        "country": "中国",
        "state": "香港",
        "city": "香港",
        "suburb": "香港島",
    },
}

NOMINATIM_TAICHUNG_ART_MUSEUM_RESULT = {
    "display_name": "國立臺灣美術館, 2, 五權西路一段, 西區, 臺中市, 臺灣",
    "lat": "24.1414905",
    "lon": "120.663268",
    "address": {
        "country": "臺灣",
        "city": "臺中市",
        "city_district": "西區",
    },
}

PHOTON_PARTIAL_HONG_KONG_RESULT = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [114.1480221, 22.2849664]},
    "properties": {
        "name": "太平山街 Tai Ping Shan Street",
        "district": "中西區",
        "city": "香港",
        "state": "香港",
        "country": "中国",
    },
}


def test_forward_merges_fuzzy_results_and_deduplicates_same_coordinates(monkeypatch):
    from backend import geocode

    geocode._cache.clear()

    def fake_request(url: str, **_kwargs):
        if "photon.komoot.io" in url:
            return {"features": [PHOTON_DUPLICATE, PHOTON_FUZZY_RESULT]}
        return [NOMINATIM_RESULT]

    monkeypatch.setattr(geocode, "request_json", fake_request)

    results = geocode.forward("wukang build shanghai")

    assert len(results) == 2
    assert results[0]["name"].startswith("上海外滩美术馆")
    assert results[1]["name"].startswith("武康大楼")
    assert results[1]["latitude"] == 31.2062561
    assert results[1]["longitude"] == 121.4337292


def test_forward_uses_photon_when_nominatim_is_unavailable(monkeypatch):
    from backend import geocode

    geocode._cache.clear()

    def fake_request(url: str, **_kwargs):
        if "nominatim.openstreetmap.org" in url:
            raise TimeoutError("nominatim timed out")
        return {"features": [PHOTON_FUZZY_RESULT]}

    monkeypatch.setattr(geocode, "request_json", fake_request)

    results = geocode.forward("wukang build shanghai")

    assert len(results) == 1
    assert results[0]["name"].startswith("武康大楼")


def test_forward_keeps_exact_results_when_photon_is_unavailable(monkeypatch):
    from backend import geocode

    geocode._cache.clear()

    def fake_request(url: str, **_kwargs):
        if "photon.komoot.io" in url:
            raise TimeoutError("photon timed out")
        return [NOMINATIM_RESULT]

    monkeypatch.setattr(geocode, "request_json", fake_request)

    results = geocode.forward("上海外滩美术馆")

    assert len(results) == 1
    assert results[0]["name"].startswith("上海外滩美术馆")


def test_merge_places_keeps_fuzzy_candidates_when_exact_provider_is_full():
    from backend.geocode import merge_places

    exact = [
        {
            "name": f"Exact {index}",
            "latitude": 30.0 + index,
            "longitude": 120.0 + index,
        }
        for index in range(8)
    ]
    fuzzy = [{"name": "Fuzzy candidate", "latitude": 31.2062561, "longitude": 121.4337292}]

    results = merge_places(exact, fuzzy, limit=8)

    assert [place["name"] for place in results[:3]] == ["Exact 0", "Fuzzy candidate", "Exact 1"]


def test_forward_broadens_an_empty_chinese_place_description(monkeypatch):
    from backend import geocode

    geocode._cache.clear()

    def fake_request(url: str, **_kwargs):
        query = parse_qs(urlparse(url).query)["q"][0]
        if "nominatim.openstreetmap.org" in url:
            return [NOMINATIM_PEAK_STATION_RESULT] if query == "山顶 station" else []
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(geocode, "request_json", fake_request)

    results = geocode.forward("太平山顶 缆车站")

    assert len(results) == 1
    assert results[0]["name"].startswith("山頂")
    assert results[0]["latitude"] == 22.271123
    assert results[0]["longitude"] == 114.1501414
    assert results[0]["match_quality"] == "broader"


def test_forward_prefers_hong_kong_peak_station_over_partial_street_match(monkeypatch):
    from backend import geocode

    geocode._cache.clear()

    def fake_request(url: str, **_kwargs):
        query = parse_qs(urlparse(url).query)["q"][0]
        if query == "香港 山顶 station" and "nominatim.openstreetmap.org" in url:
            return [NOMINATIM_PEAK_STATION_RESULT]
        if query == "香港 太平山顶 缆车站" and "photon.komoot.io" in url:
            return {"type": "FeatureCollection", "features": [PHOTON_PARTIAL_HONG_KONG_RESULT]}
        if "photon.komoot.io" in url:
            return {"type": "FeatureCollection", "features": []}
        return []

    monkeypatch.setattr(geocode, "request_json", fake_request)

    results = geocode.forward("香港 太平山顶 缆车站")

    assert results[0]["latitude"] == 22.271123
    assert results[0]["longitude"] == 114.1501414
    assert results[0]["match_quality"] == "broader"


def test_broader_query_translates_a_museum_category_without_damaging_the_city_name():
    from backend.geocode import broader_query

    assert broader_query("台中市 美术馆") == "museum, 台中市"
    assert broader_query("臺中市 美術館") == "museum, 臺中市"


def test_broader_query_removes_an_administrative_suffix_instead_of_truncating_the_name():
    from backend.geocode import broader_query

    assert broader_query("台中市 夜市") == "台中 夜市"


def test_forward_finds_museums_by_city_and_generic_chinese_category(monkeypatch):
    from backend import geocode

    geocode._cache.clear()

    def fake_request(url: str, **_kwargs):
        query = parse_qs(urlparse(url).query)["q"][0]
        if query == "museum, 台中市" and "nominatim.openstreetmap.org" in url:
            return [NOMINATIM_TAICHUNG_ART_MUSEUM_RESULT]
        if "photon.komoot.io" in url:
            return {"type": "FeatureCollection", "features": []}
        return []

    monkeypatch.setattr(geocode, "request_json", fake_request)

    results = geocode.forward("台中市 美术馆")

    assert results[0]["name"].startswith("國立臺灣美術館")
    assert results[0]["latitude"] == 24.1414905
    assert results[0]["longitude"] == 120.663268
    assert results[0]["match_quality"] == "broader"


def test_forward_does_not_cache_an_empty_search_result(monkeypatch):
    from backend import geocode

    geocode._cache.clear()
    search_number = 0

    def fake_request(url: str, **_kwargs):
        nonlocal search_number
        if "nominatim.openstreetmap.org" in url:
            search_number += 1
            return [] if search_number == 1 else [NOMINATIM_TAICHUNG_ART_MUSEUM_RESULT]
        return {"type": "FeatureCollection", "features": []}

    monkeypatch.setattr(geocode, "request_json", fake_request)

    assert geocode.forward("temporary-empty-query") == []
    recovered_results = geocode.forward("temporary-empty-query")

    assert recovered_results[0]["name"].startswith("國立臺灣美術館")
