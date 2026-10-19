"""Run with: pytest -q tests"""
from __future__ import annotations
import io
import hashlib
import json
import os
import ssl
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STUDIO_PARENT = ROOT / "apps" / "studio"
if str(STUDIO_PARENT) not in sys.path:
    sys.path.insert(0, str(STUDIO_PARENT))

@pytest.fixture
def secret_store():
    from backend.secret_store import MemorySecretStore

    return MemorySecretStore()


@pytest.fixture
def client(tmp_path, monkeypatch, secret_store):
    monkeypatch.setenv("PHOTO_BOOTH_DATA_DIR", str(tmp_path / "data"))
    for mod in list(sys.modules):
        if mod.startswith("backend"):
            del sys.modules[mod]
    from backend.main import app, get_secret_store
    app.dependency_overrides[get_secret_store] = lambda: secret_store
    with TestClient(app) as test:
        yield test
    app.dependency_overrides.clear()

def photo_bytes(color=(107,136,127)):
    pic=Image.new("RGB",(640,450),color)
    output=io.BytesIO()
    pic.save(output,format="JPEG")
    return output.getvalue()

def create_collection(client, title='Inbox'):
    response = client.post('/api/collections', json={'title': title})
    assert response.status_code == 200, response.text
    return response.json()['id']


def upload(client, collection_id=None, filename='Evening in Tokyo.jpg', image_data=None):
    collection_id = collection_id or create_collection(client)
    response=client.post(
        '/api/photos/import',
        data={'collection_id': collection_id},
        files={'files':(filename,image_data or photo_bytes(),'image/jpeg')},
    )
    assert response.status_code==200,response.text
    return response.json()['added'][0]


def review_payload(client, photo_id, **overrides):
    photo = client.get(f'/api/photos/{photo_id}').json()
    payload = {
        'taken_at': '2025-03',
        'description': '',
        'device': 'Sony a6400',
        'featured': False,
        'collectionIds': photo['collectionIds'],
        'tags': [],
        'guess_enabled': False,
        'guess': None,
    }
    payload.update(overrides)
    return payload


def complete_review(client, photo_id, **overrides):
    response = client.put(
        f'/api/photos/{photo_id}/review',
        json=review_payload(client, photo_id, **overrides),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_google_map_config_masks_key_and_bootstrap_returns_it_only_for_local_ui(client, secret_store):
    api_key = "AIza-test-google-browser-key-1234567890"
    response = client.put(
        "/api/maps/config",
        json={"api_key": api_key, "map_id": "photo-booth-local"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200, response.text
    config = response.json()
    assert config["apiKeyConfigured"] is True
    assert config["apiKeyMask"].startswith(api_key[:4])
    assert config["apiKeyMask"].endswith(api_key[-4:])
    assert api_key not in json.dumps(config)
    assert config["mapId"] == "photo-booth-local"

    masked = client.get("/api/maps/config").json()
    assert api_key not in json.dumps(masked)
    bootstrap = client.get(
        "/api/maps/bootstrap",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert bootstrap.status_code == 200, bootstrap.text
    assert bootstrap.json() == {"apiKey": api_key, "mapId": "photo-booth-local"}

    blocked = client.get(
        "/api/maps/bootstrap",
        headers={"Origin": "https://example.com"},
    )
    assert blocked.status_code == 403

    from backend.db import connect
    conn = connect()
    try:
        stored = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM settings")}
    finally:
        conn.close()
    assert stored["google_maps_map_id"] == "photo-booth-local"
    assert api_key not in json.dumps(stored)
    assert secret_store.get("google-maps-browser-key") == api_key


def test_google_map_key_can_be_replaced_and_cleared_without_entering_sqlite(client, secret_store):
    first = "AIza-first-google-browser-key-123456"
    second = "AIza-second-google-browser-key-654321"
    assert client.put("/api/maps/config", json={"api_key": first, "map_id": "map-one"}).status_code == 200
    replaced = client.put("/api/maps/config", json={"api_key": second, "map_id": "map-two"})
    assert replaced.status_code == 200, replaced.text
    assert secret_store.get("google-maps-browser-key") == second
    assert first not in json.dumps(replaced.json())
    assert second not in json.dumps(replaced.json())

    cleared = client.put(
        "/api/maps/config",
        json={"clear_api_key": True, "map_id": "map-two"},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["apiKeyConfigured"] is False
    assert cleared.json()["apiKeyMask"] == ""
    assert secret_store.get("google-maps-browser-key") == ""

    from backend.db import connect
    conn = connect()
    try:
        serialized = json.dumps([dict(row) for row in conn.execute("SELECT * FROM settings")])
    finally:
        conn.close()
    assert first not in serialized
    assert second not in serialized


def test_google_map_config_rejects_non_local_mutation_origin(client, secret_store):
    response = client.put(
        "/api/maps/config",
        json={"api_key": "AIza-blocked-key-123456789", "map_id": "blocked"},
        headers={"Origin": "https://example.com"},
    )
    assert response.status_code == 403
    assert secret_store.get("google-maps-browser-key") == ""


def test_import_requires_an_existing_collection_before_processing(client):
    missing = client.post('/api/photos/import', files={
        'files': ('photo.jpg', photo_bytes(), 'image/jpeg'),
    })
    assert missing.status_code == 422

    unknown = client.post('/api/photos/import', data={'collection_id': 'c_missing'}, files={
        'files': ('photo.jpg', photo_bytes(), 'image/jpeg'),
    })
    assert unknown.status_code == 422
    assert client.get('/api/photos').json() == []


def test_import_links_new_and_duplicate_photos_to_the_selected_collection(client):
    first_collection = create_collection(client, 'First')
    second_collection = create_collection(client, 'Second')
    photo_id = upload(client, first_collection)

    duplicate = client.post('/api/photos/import', data={'collection_id': second_collection}, files={
        'files': ('copy.jpg', photo_bytes(), 'image/jpeg'),
    })
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()['added'] == []
    assert duplicate.json()['duplicates'] == [{'name': 'copy.jpg', 'photoId': photo_id}]
    assert duplicate.json()['reviewIds'] == [photo_id]
    assert set(client.get(f'/api/photos/{photo_id}').json()['collectionIds']) == {
        first_collection, second_collection,
    }
    assert len(client.get('/api/photos').json()) == 1


def test_repeated_file_in_one_import_has_one_row_link_and_queue_entry(client):
    collection_id = create_collection(client)
    response = client.post('/api/photos/import', data={'collection_id': collection_id}, files=[
        ('files', ('one.jpg', photo_bytes(), 'image/jpeg')),
        ('files', ('two.jpg', photo_bytes(), 'image/jpeg')),
    ])
    assert response.status_code == 200, response.text
    assert len(client.get('/api/photos').json()) == 1
    assert len(response.json()['reviewIds']) == 1
    assert client.get('/api/collections').json()[0]['count'] == 1


def test_duplicate_with_a_different_extension_leaves_one_archived_original(client):
    from backend.db import ORIGINALS
    collection_id = create_collection(client)
    photo_id = upload(client, collection_id, filename='first.jpg')
    duplicate = client.post('/api/photos/import', data={'collection_id': collection_id}, files={
        'files': ('copy.jpeg', photo_bytes(), 'image/jpeg'),
    })
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()['duplicates'] == [{'name': 'copy.jpeg', 'photoId': photo_id}]
    assert len(list(ORIGINALS.iterdir())) == 1


def test_import_keeps_exif_date_and_managed_device_as_review_defaults(client):
    picture = Image.new('RGB', (640, 450), (107, 136, 127))
    exif = Image.Exif()
    exif[36867] = '2020:08:07 12:34:56'
    exif[271] = 'SONY'
    exif[272] = 'ILCE-6400'
    output = io.BytesIO()
    picture.save(output, format='JPEG', exif=exif)
    collection_id = create_collection(client)
    response = client.post('/api/photos/import', data={'collection_id': collection_id}, files={
        'files': ('sony.jpg', output.getvalue(), 'image/jpeg'),
    })
    assert response.status_code == 200, response.text
    photo = client.get(f"/api/photos/{response.json()['added'][0]}").json()
    assert photo['taken_at'] == '2020-08-07'
    assert photo['device'] == 'Sony a6400'


@pytest.mark.parametrize('taken_at', ['', '2025', '2025-13'])
def test_review_rejects_dates_without_a_valid_month(client, taken_at):
    photo_id = upload(client)
    response = client.put(
        f'/api/photos/{photo_id}/review',
        json=review_payload(client, photo_id, taken_at=taken_at),
    )
    assert response.status_code == 422
    assert client.get(f'/api/photos/{photo_id}').json()['status'] == 'draft'


@pytest.mark.parametrize('taken_at', ['2025-03', '2025-03-11'])
def test_review_accepts_month_or_full_date(client, taken_at):
    photo_id = upload(client)
    saved = complete_review(client, photo_id, taken_at=taken_at)
    assert saved['taken_at'] == taken_at
    assert saved['status'] == 'modified'


def test_review_requires_device_and_collection(client):
    photo_id = upload(client)
    assert client.put(
        f'/api/photos/{photo_id}/review',
        json=review_payload(client, photo_id, device=''),
    ).status_code == 422
    assert client.put(
        f'/api/photos/{photo_id}/review',
        json=review_payload(client, photo_id, collectionIds=[]),
    ).status_code == 422


def test_review_rejects_removed_title_and_gallery_location_fields(client):
    photo_id = upload(client)
    payload = review_payload(client, photo_id)
    payload.update({
        'title': 'No longer used',
        'country': 'Japan',
        'region': 'Tokyo',
        'city': 'Tokyo',
        'district': 'Shibuya',
        'location_query': 'Shibuya, Tokyo',
    })
    response = client.put(f'/api/photos/{photo_id}/review', json=payload)
    assert response.status_code == 422


def test_review_saves_homepage_and_case_insensitive_tags(client):
    photo_id = upload(client)
    saved = complete_review(
        client, photo_id, featured=True,
        tags=['Street', 'street', 'Night'],
    )
    assert saved['featured'] is True
    assert saved['status'] == 'modified'
    assert set(saved['tags']) == {'Street', 'Night'}
    assert client.get('/api/tags').json() == {'tags': ['Night', 'Street']}

    unchecked = complete_review(client, photo_id, featured=False)
    assert unchecked['featured'] is False


def test_unchecking_guess_where_removes_an_existing_private_answer(client):
    photo_id = upload(client)
    guess = {
        'latitude': 31.2295, 'longitude': 121.4428,
        'precision': 'approximate', 'difficulty': 'medium',
        'answer_name': '静安区, 上海市, 中国',
        'answer_description': '', 'answer_radius_km': 10,
        'enabled': True, 'confirmed': True,
    }
    assert complete_review(
        client, photo_id, guess_enabled=True, guess=guess,
    )['guess']['confirmed'] is True
    removed = complete_review(client, photo_id, guess_enabled=False, guess=None)
    assert removed['guess'] is None


def test_atomic_review_rolls_back_when_a_late_database_write_fails(client):
    import sqlite3
    from backend.db import connect
    from backend.review import apply_review

    photo_id = upload(client)
    payload = review_payload(client, photo_id, description='Must roll back', guess_enabled=True, guess={
        'latitude': 31.2295, 'longitude': 121.4428,
        'precision': 'approximate', 'difficulty': 'medium',
        'answer_name': 'Shanghai', 'answer_description': '',
        'answer_radius_km': 10, 'enabled': True, 'confirmed': True,
    })
    conn = connect()
    try:
        conn.execute('''CREATE TEMP TRIGGER fail_guess BEFORE INSERT ON guess_where_entries
                        BEGIN SELECT RAISE(ABORT, 'forced late failure'); END''')
        with pytest.raises(sqlite3.IntegrityError, match='forced late failure'):
            apply_review(conn, photo_id, payload)
        row = conn.execute('SELECT description,status FROM photos WHERE id=?', (photo_id,)).fetchone()
        assert dict(row) == {'description': '', 'status': 'draft'}
        assert conn.execute(
            'SELECT COUNT(*) FROM guess_where_entries WHERE photo_id=?', (photo_id,)
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_needs_review_counts_only_drafts_and_reviewed_duplicate_skips_queue(client):
    collection_id = create_collection(client)
    photo_id = upload(client, collection_id)
    assert client.get('/api/stats').json()['needReview'] == 1
    complete_review(client, photo_id)
    assert client.get('/api/stats').json()['needReview'] == 0

    duplicate = client.post('/api/photos/import', data={'collection_id': collection_id}, files={
        'files': ('again.jpg', photo_bytes(), 'image/jpeg'),
    })
    assert duplicate.status_code == 200
    assert duplicate.json()['reviewIds'] == []


def test_partial_patch_and_bulk_edit_cannot_complete_or_modify_a_draft(client):
    photo_id = upload(client)
    patch = client.patch(f'/api/photos/{photo_id}', json={'description': 'partial'})
    assert patch.status_code == 409
    bulk = client.post('/api/photos/bulk', json={
        'ids': [photo_id], 'addCollectionIds': [], 'addTags': ['partial'],
    })
    assert bulk.status_code == 409
    photo = client.get(f'/api/photos/{photo_id}').json()
    assert photo['status'] == 'draft'
    assert photo['description'] == ''
    assert photo['tags'] == []


def test_legacy_guess_endpoints_cannot_modify_a_draft(client):
    photo_id = upload(client)
    guess = {
        'latitude': 35.6762, 'longitude': 139.6503,
        'precision': 'approximate', 'difficulty': 'medium',
        'confirmed': True, 'answer_name': 'Tokyo',
        'answer_description': '', 'answer_radius_km': 50,
    }
    assert client.put(f'/api/guess/{photo_id}', json=guess).status_code == 409
    assert client.delete(f'/api/guess/{photo_id}').status_code == 409
    assert client.get(f'/api/photos/{photo_id}').json()['guess'] is None


def test_publish_skips_drafts_and_omits_unused_title_and_location(client, tmp_path):
    draft_id = upload(client, filename='draft.jpg')
    reviewed_id = upload(
        client,
        filename='reviewed.jpg',
        image_data=photo_bytes((80, 120, 160)),
    )
    complete_review(client, reviewed_id, taken_at='2025-03')
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'package.json').write_text('{"name":"test-web"}')
    response = client.post('/api/publish/export', json={'web_root': str(web)})
    assert response.status_code == 200, response.text
    assert response.json()['count'] == 1
    data = json.loads((web / 'src/generated/photography.json').read_text())
    assert [item['id'] for item in data] == [reviewed_id]
    assert 'title' not in data[0]
    assert 'location' not in data[0]
    assert draft_id not in json.dumps(data)


def test_atomic_review_and_export_keep_original_and_private_guess_data_safe(client, tmp_path):
    from backend.db import connect
    photo_id = upload(client)
    conn = connect()
    original = Path(conn.execute(
        'SELECT original_path FROM photos WHERE id=?', (photo_id,)
    ).fetchone()[0])
    conn.close()
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    complete_review(client, photo_id, featured=True, tags=['Travel'],
        guess_enabled=True, guess={
            'latitude': 31.2295, 'longitude': 121.4428,
            'precision': 'approximate', 'difficulty': 'medium',
            'answer_name': '静安区, 上海市, 中国',
            'answer_description': '上海市中心附近', 'answer_radius_km': 10,
            'enabled': True, 'confirmed': True,
        })
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'package.json').write_text('{"name":"test-web"}')
    assert client.post('/api/publish/export', json={'web_root': str(web)}).status_code == 200
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    exported = (web / 'src/generated/photography.json').read_text()
    for private_value in ('31.2295', '121.4428', '静安区, 上海市, 中国', '上海市中心附近'):
        assert private_value not in exported

def test_import_dedupe_review_and_no_title_or_gallery_location(client):
    photo_id=upload(client)
    response=client.get(f'/api/photos/{photo_id}')
    assert response.status_code==200
    photo=response.json()
    assert photo['exif_lat'] is None
    assert photo['exif_lng'] is None
    assert photo['title']==''
    assert photo['taken_at']==''
    assert client.get(f'/api/photos/{photo_id}/thumbnail').status_code==200
    duplicate=client.post(
        '/api/photos/import',
        data={'collection_id': photo['collectionIds'][0]},
        files={'files':('Another filename.jpg',photo_bytes(),'image/jpeg')},
    ).json()
    assert duplicate['added']==[] and duplicate['duplicates']
    change=complete_review(
        client, photo_id, taken_at='2025-03', description='A memory',
    )
    assert change['title']==''
    assert change['country']==''
    assert change['description']=='A memory'
    assert change['collectionIds']==photo['collectionIds']
    assert client.get('/api/stats').json()['ready']==1

def test_collections_tags_and_guess_not_in_public_json(client,tmp_path):
    photo_id=upload(client)
    c1=client.post('/api/collections',json={'title':'After Dark'}).json()['id']
    c2=client.post('/api/collections',json={'title':'Travel'}).json()['id']
    changed=complete_review(
        client, photo_id, taken_at='2025-03-11',
        collectionIds=[c1,c2], tags=['night','Street'],
    )
    assert set(changed['collectionIds'])=={c1,c2}
    assert set(changed['tags'])=={'Street','night'}
    assert client.put(f'/api/guess/{photo_id}',json={'latitude':35.6895,'longitude':139.6917,'precision':'approximate','difficulty':'medium','confirmed':True,'answer_name':'Tokyo','answer_description':'','answer_radius_km':50}).status_code==200
    web=tmp_path/'web'
    web.mkdir()
    (web/'package.json').write_text('{"name":"test-web"}')
    published=client.post('/api/publish/export',json={'web_root':str(web)})
    assert published.status_code==200,published.text
    data=json.loads((web/'src/generated/photography.json').read_text())
    serialized=json.dumps(data)
    assert photo_id in serialized
    assert '35.6895' not in serialized
    assert '139.6917' not in serialized
    assert 'exif_lat' not in serialized
    assert 'latitude' not in serialized
    assert 'answer_name' not in serialized
    assert 'answer_description' not in serialized
    assert 'answer_radius_km' not in serialized
    assert 'location' not in data[0]
    assert (web/'public/photos'/f'{photo_id}.webp').is_file()
    # Generated images drop metadata too.
    with Image.open(web/'public/photos'/f'{photo_id}.webp') as img:
        assert not img.getexif()


def test_metadata_guess_and_export_never_modify_the_original(client, tmp_path):
    from backend.db import connect
    photo_id = upload(client)
    conn = connect()
    original = Path(conn.execute('SELECT original_path FROM photos WHERE id=?', (photo_id,)).fetchone()[0])
    conn.close()
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    complete_review(client, photo_id, taken_at='2025-03', device='iPhone 14')
    assert client.put(f'/api/guess/{photo_id}', json={
        'latitude':35.6762, 'longitude':139.6503, 'precision':'approximate',
        'difficulty':'medium', 'confirmed':True, 'answer_name':'Tokyo',
        'answer_description':'Around Tokyo Bay', 'answer_radius_km':50,
    }).status_code == 200
    assert client.post(f'/api/guess/{photo_id}/grade-pin', json={'latitude':35.7, 'longitude':139.7}).status_code == 200
    web = tmp_path/'web'
    web.mkdir()
    (web/'package.json').write_text('{"name":"test-web"}')
    assert client.post('/api/publish/export', json={'web_root':str(web)}).status_code == 200
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before


def test_delete_photo_removes_managed_data_but_keeps_archived_original(client):
    from backend.db import PREVIEWS, THUMBS, connect

    collection_id = create_collection(client, 'Keep the original')
    photo_id = upload(client, collection_id)
    complete_review(
        client,
        photo_id,
        tags=['Travel'],
        guess_enabled=True,
        guess={
            'latitude': 31.2295,
            'longitude': 121.4428,
            'precision': 'approximate',
            'difficulty': 'medium',
            'answer_name': 'Shanghai',
            'answer_description': 'Near the city centre',
            'answer_radius_km': 10,
            'enabled': True,
            'confirmed': True,
        },
    )
    conn = connect()
    original = Path(conn.execute(
        'SELECT original_path FROM photos WHERE id=?', (photo_id,),
    ).fetchone()[0])
    conn.close()
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    thumbnail = THUMBS / f'{photo_id}.webp'
    preview = PREVIEWS / f'{photo_id}.webp'
    assert thumbnail.is_file()
    assert preview.is_file()

    response = client.delete(f'/api/photos/{photo_id}')

    assert response.status_code == 200, response.text
    assert response.json() == {'ok': True, 'originalKept': True}
    assert client.get(f'/api/photos/{photo_id}').status_code == 404
    assert original.is_file()
    assert hashlib.sha256(original.read_bytes()).hexdigest() == original_hash
    assert not thumbnail.exists()
    assert not preview.exists()
    assert client.get('/api/collections').json()[0]['count'] == 0
    conn = connect()
    try:
        assert conn.execute(
            'SELECT COUNT(*) FROM photo_collections WHERE photo_id=?', (photo_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            'SELECT COUNT(*) FROM photo_tags WHERE photo_id=?', (photo_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            'SELECT COUNT(*) FROM guess_where_entries WHERE photo_id=?', (photo_id,),
        ).fetchone()[0] == 0
    finally:
        conn.close()


def test_delete_unknown_photo_returns_not_found(client):
    response = client.delete('/api/photos/p_missing')
    assert response.status_code == 404

def test_only_valid_photos_publish_and_bad_dates_rejected(client,tmp_path):
    photo_id=upload(client)
    bad=client.put(
        f'/api/photos/{photo_id}/review',
        json=review_payload(client, photo_id, taken_at='2025-99-99'),
    )
    assert bad.status_code==422
    assert client.get('/api/publish/preview').json()['ready']==0
    bad_guess=client.put(f'/api/guess/{photo_id}',json={'latitude':99,'longitude':0})
    assert bad_guess.status_code==422
    complete_review(client, photo_id, taken_at='2025-03')
    assert client.get('/api/publish/preview').json()['ready']==1

def test_bulk_tags_location(client):
    photo_id=upload(client)
    complete_review(client, photo_id)
    response=client.post('/api/photos/bulk',json={'ids':[photo_id], 'addCollectionIds':[], 'addTags':['street'], 'location':{'city':'Paris','country':'France'}})
    assert response.status_code==200,response.text
    p=client.get(f'/api/photos/{photo_id}').json()
    assert p['tags']==['street']
    assert p['city']=='Paris'

def test_cross_origin_mutation_blocked(client):
    response=client.post('/api/collections',json={'title':'Bad'},headers={'Origin':'https://evil.example'})
    assert response.status_code==403
    assert client.get('/api/collections').json()==[]


def test_sqlite_request_connection_can_move_between_fastapi_worker_threads(client):
    from backend.db import connect
    conn = connect()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            count = pool.submit(lambda: conn.execute('SELECT COUNT(*) FROM photos').fetchone()[0]).result()
        assert count == 0
    finally:
        conn.close()


def test_geocode_https_request_uses_a_populated_trust_store(monkeypatch):
    from backend import geocode

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'[]'

    def fake_urlopen(request, *, timeout, context):
        captured['context'] = context
        return Response()

    monkeypatch.setattr(geocode, 'urlopen', fake_urlopen)

    assert geocode.request_json('https://example.invalid/search') == []
    context = captured['context']
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.cert_store_stats()['x509_ca'] > 0


@pytest.mark.parametrize(('make','model','expected'), [
    ('Apple', 'iPhone 6', 'iPhone 6'),
    ('Apple', 'iPhone 11', 'iPhone 11'),
    ('Apple', 'iPhone 14', 'iPhone 14'),
    ('SONY', 'NEX-C3', 'Sony NEX-C3'),
    ('Sony', 'ILCE-6400', 'Sony a6400'),
    ('Canon', 'Canon PowerShot G3 X', 'Canon G3QL'),
    ('Unknown', 'Mystery Camera', ''),
])
def test_device_metadata_is_normalized_to_managed_values(make, model, expected):
    from backend.devices import normalize_device
    assert normalize_device(make, model) == expected


def test_device_can_be_edited_but_only_to_a_managed_value(client, tmp_path):
    photo_id = upload(client)
    rejected_review = client.put(
        f'/api/photos/{photo_id}/review',
        json=review_payload(client, photo_id, device='Other camera'),
    )
    assert rejected_review.status_code == 422
    changed = complete_review(client, photo_id, device='Sony a6400')
    assert changed['device'] == 'Sony a6400'
    rejected = client.patch(f'/api/photos/{photo_id}', json={'device':'Other camera'})
    assert rejected.status_code == 422

    web = tmp_path/'web'
    web.mkdir()
    (web/'package.json').write_text('{"name":"test-web"}')
    assert client.post('/api/publish/export', json={'web_root':str(web)}).status_code == 200
    public = json.loads((web/'src/generated/photography.json').read_text())
    assert public[0]['device'] == 'Sony a6400'


def test_guess_answer_requires_canonical_name_and_valid_radius(client):
    photo_id = upload(client)
    complete_review(client, photo_id)
    without_name = client.put(f'/api/guess/{photo_id}', json={
        'latitude':35.6762, 'longitude':139.6503, 'precision':'approximate',
        'difficulty':'medium', 'confirmed':True, 'answer_name':'',
        'answer_description':'Somewhere around central Tokyo', 'answer_radius_km':10,
    })
    assert without_name.status_code == 422
    invalid_radius = client.put(f'/api/guess/{photo_id}', json={
        'latitude':35.6762, 'longitude':139.6503, 'precision':'approximate',
        'difficulty':'medium', 'confirmed':True, 'answer_name':'Tokyo',
        'answer_description':'Somewhere around central Tokyo', 'answer_radius_km':0,
    })
    assert invalid_radius.status_code == 422
    unsupported_radius = client.put(f'/api/guess/{photo_id}', json={
        'latitude':35.6762, 'longitude':139.6503, 'precision':'approximate',
        'difficulty':'medium', 'confirmed':True, 'answer_name':'Tokyo',
        'answer_description':'Somewhere around central Tokyo', 'answer_radius_km':40,
    })
    assert unsupported_radius.status_code == 422

    saved = client.put(f'/api/guess/{photo_id}', json={
        'latitude':35.6762, 'longitude':139.6503, 'precision':'approximate',
        'difficulty':'medium', 'confirmed':True, 'answer_name':'Tokyo',
        'answer_description':'Somewhere around central Tokyo', 'answer_radius_km':1,
    })
    assert saved.status_code == 200, saved.text
    guess = saved.json()['guess']
    assert guess['answer_name'] == 'Tokyo'
    assert guess['answer_description'] == 'Somewhere around central Tokyo'
    assert guess['answer_radius_km'] == 1
    assert client.get('/api/stats').json()['gamePool'] == 1


def test_guess_answer_radius_defaults_to_10_km(client):
    photo_id = upload(client)
    complete_review(client, photo_id)
    saved = client.put(f'/api/guess/{photo_id}', json={
        'latitude':35.6762, 'longitude':139.6503, 'precision':'approximate',
        'difficulty':'medium', 'confirmed':True, 'answer_name':'Tokyo',
        'answer_description':'Somewhere around central Tokyo',
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()['guess']['answer_radius_km'] == 10


def test_pin_grading_uses_the_same_radius_for_correct_close_and_incorrect():
    import math
    from backend.grading import grade_pin
    correct = grade_pin(0, 0, 0, 0.08, 10)
    close = grade_pin(0, 0, 0, 0.15, 10)
    incorrect = grade_pin(0, 0, 0, 0.40, 10)
    assert correct['result'] == 'correct'
    assert correct['score'] == 5000
    assert close['result'] == 'close'
    assert 1000 <= close['score'] < correct['score']
    assert incorrect['result'] == 'incorrect'
    assert 0 <= incorrect['score'] < close['score']

    just_close = grade_pin(0, 0, 0, math.degrees(10.0001 / 6371.0088), 10)
    just_incorrect = grade_pin(0, 0, 0, math.degrees(30.0001 / 6371.0088), 10)
    assert just_close['result'] == 'close'
    assert just_close['score'] <= 4999
    assert just_incorrect['result'] == 'incorrect'
    assert just_incorrect['score'] <= 1008


def test_text_grading_validates_structured_model_output(monkeypatch):
    from backend import grading
    entry = {
        'answer_name':'Tokyo', 'answer_description':'Around Tokyo Bay',
        'latitude':35.6762, 'longitude':139.6503, 'answer_radius_km':50,
    }
    monkeypatch.setenv('PHOTO_BOOTH_LLM_API_KEY', 'test-key')
    monkeypatch.setenv('PHOTO_BOOTH_LLM_MODEL', 'test-model')
    valid_response = {'choices':[{'message':{'content':'{"result":"close","score":2300,"confidence":0.82,"explanation":"Same metro area."}'}}]}
    result = grading.grade_text(entry, 'Yokohama', requester=lambda *_: valid_response)
    assert result == {'result':'close', 'score':2300, 'confidence':0.82, 'explanation':'Same metro area.'}
    invalid_score = {'choices':[{'message':{'content':'{"result":"close","score":5500,"confidence":0.82,"explanation":"Same metro area."}'}}]}
    with pytest.raises(ValueError, match='invalid grading result'):
        grading.grade_text(entry, 'Yokohama', requester=lambda *_: invalid_score)
    malformed = {'choices':[{'message':{'content':'not json'}}]}
    with pytest.raises(ValueError, match='valid JSON'):
        grading.grade_text(entry, 'Yokohama', requester=lambda *_: malformed)


def test_grading_preview_endpoints_and_missing_model_config(client, monkeypatch):
    photo_id = upload(client)
    complete_review(client, photo_id)
    saved = client.put(f'/api/guess/{photo_id}', json={
        'latitude':35.6762, 'longitude':139.6503, 'precision':'approximate',
        'difficulty':'medium', 'confirmed':True, 'answer_name':'Tokyo',
        'answer_description':'Around Tokyo Bay', 'answer_radius_km':50,
    })
    assert saved.status_code == 200
    pin = client.post(f'/api/guess/{photo_id}/grade-pin', json={'latitude':35.7, 'longitude':139.7})
    assert pin.status_code == 200, pin.text
    assert pin.json()['result'] == 'correct'
    monkeypatch.delenv('PHOTO_BOOTH_LLM_API_KEY', raising=False)
    monkeypatch.delenv('PHOTO_BOOTH_LLM_MODEL', raising=False)
    text = client.post(f'/api/guess/{photo_id}/grade-text', json={'answer':'Tokyo'})
    assert text.status_code == 503
    assert 'PHOTO_BOOTH_LLM' in text.json()['detail']


def test_git_publish_from_nested_monorepo(client,tmp_path):
    """Only generated assets should be staged, even if webroot is apps/web."""
    from backend.publish import publish_git
    photo_id=upload(client)
    complete_review(client, photo_id, taken_at='2025-06')
    repo=tmp_path/'mono'
    web=repo/'apps'/'web'
    web.mkdir(parents=True)
    (web/'package.json').write_text('{"name":"web"}')
    def git(*args):
        out=subprocess.run(['git','-C',str(repo),*args],text=True,capture_output=True)
        assert out.returncode==0,out.stderr
        return out.stdout.strip()
    git('init','-b','main')
    git('config','user.email','tests@example.org')
    git('config','user.name','Photo Booth Test')
    (repo/'README.md').write_text('Hello')
    git('add','README.md')
    git('commit','-m','initial')
    bare=tmp_path/'remote.git'
    run=subprocess.run(['git','init','--bare',str(bare)],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    git('remote','add','origin',str(bare))
    assert client.post('/api/publish/export',json={'web_root':str(web)}).status_code==200
    (repo/'unrelated.txt').write_text('should stay local')
    result=publish_git(str(web),'New photographs')
    assert result['pushed']
    assert not (repo/'unrelated.txt').is_relative_to(web)
    assert 'unrelated.txt' in git('status','--short')
    assert not any('unrelated' in name for name in result['files'])
    assert 'apps/web/src/generated/photography.json' in result['files']
