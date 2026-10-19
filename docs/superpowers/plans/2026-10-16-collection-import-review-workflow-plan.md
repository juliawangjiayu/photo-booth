# Collection-first Import and Photo Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Collection selection mandatory before batch import, then guide the user through an atomic, sequential review of every draft photo before it can leave Needs Review.

**Architecture:** Keep `photos.status` as the only review-state marker: imports create or retain `draft`, while one atomic review endpoint writes the entire form and changes the status to `modified`. A lightweight frontend queue holds only photo IDs; the database remains the source of truth, and unfinished queue items are recovered from `status='draft'` rather than a new batch table.

**Tech Stack:** FastAPI, Pydantic, SQLite, pytest, React 19, TypeScript, Vite, Node's built-in test runner, MapLibre GL JS.

**Spec:** `docs/superpowers/specs/2026-10-16-collection-import-review-workflow-design.md`

## Global Constraints

- Require one existing or newly created Collection before an import starts.
- Never create a second photo row for a duplicate SHA-256; add the existing photo to the selected Collection instead.
- A review save is all-or-nothing; no partially reviewed photo metadata may persist.
- A review date must be `YYYY-MM` or `YYYY-MM-DD`; `YYYY` is invalid.
- A managed device is required to complete review; EXIF-derived values remain valid defaults.
- Homepage and Guess Where remain ordinary checked/unchecked checkboxes.
- Guess Where requires a canonical answer and a confirmed MapLibre Pin only when checked.
- Title, public Gallery location, description, and tags remain optional.
- Tags are selected from existing values or created inline; tag relationships remain many-to-many.
- Needs Review means exactly `photos.status = 'draft'`.
- Original image bytes must never be modified or deleted by import, review, tag, Collection, Guess Where, or export operations.
- Public export must never contain EXIF GPS or private Guess Where answers and coordinates.
- Existing `modified` and `published` photos are reviewed; existing `draft` photos enter the new review flow.
- Do not add an import-batches table or decision-tracking columns.
- The project directory is not a Git repository. Do not run `git init`; use the plan checkboxes and verification output as checkpoints instead of commit steps.

## Review Focus

- A Collection deleted after the dialog loads but before upload must yield 422 before any photo row is created; Task 1 pins this with an API test.
- The same file appearing twice in one request must create one photo, one Collection link, and one queue entry; Task 1 pins this with a repeated-file test.
- Tags differing only by case must reuse one tag row while preserving a stable displayed name; Task 2 pins this with a case-insensitive tag test.
- Saving a previously configured Guess Where photo with the checkbox off must remove its private answer in the same transaction; Task 2 pins this with an endpoint test.
- If a queued photo is no longer draft or no longer exists after refresh, the frontend must skip it without trapping the user; Task 4 pins this in the pure queue-state tests.

---

### Task 1: Collection-first Import Contract

**Files:**
- Modify: `apps/studio/backend/main.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: existing `process_upload(filename, file_object) -> dict` and `photo_collections(photo_id, collection_id, position)`.
- Produces: multipart `POST /api/photos/import` requiring `collection_id: str` and returning `{added, duplicates, errors, reviewIds}` where each duplicate is `{name, photoId}`.

- [x] **Step 1: Update the shared upload helper and write failing Collection import tests**

Add a Collection-aware helper and focused tests to `tests/test_api.py`:

```python
def create_collection(client, title='Inbox'):
    response = client.post('/api/collections', json={'title': title})
    assert response.status_code == 200, response.text
    return response.json()['id']

def upload(client, collection_id=None, filename='Evening in Tokyo.jpg'):
    collection_id = collection_id or create_collection(client)
    response = client.post(
        '/api/photos/import',
        data={'collection_id': collection_id},
        files={'files': (filename, photo_bytes(), 'image/jpeg')},
    )
    assert response.status_code == 200, response.text
    return response.json()['added'][0]

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
```

- [x] **Step 2: Run the import tests and confirm the contract is absent**

Run:

```bash
.venv313/bin/python -m pytest -q tests/test_api.py -k 'import_requires or import_links or repeated_file or import_keeps'
```

Expected: FAIL because `collection_id` is not required, duplicates are plain filenames, and Collection links/review IDs are not produced.

- [x] **Step 3: Implement the minimal Collection-first import behavior**

In `apps/studio/backend/main.py`, import `Form`, require the Collection before file processing, resolve duplicates to photo IDs, and deduplicate queue IDs while retaining request order:

```python
from fastapi import FastAPI, HTTPException, File, Form, UploadFile, Depends

@app.post('/api/photos/import')
def import_photos(
    collection_id: str = Form(...),
    files: list[UploadFile] = File(...),
    conn=Depends(db),
):
    collection = conn.execute(
        'SELECT id FROM collections WHERE id=?', (collection_id,)
    ).fetchone()
    if not collection:
        raise HTTPException(422, 'Choose an existing Collection before importing')
    if len(files) > 100:
        raise HTTPException(400, 'Import up to 100 photos at a time')

    added, duplicates, errors, review_ids = [], [], [], []
    for file in files:
        try:
            processed = process_upload(file.filename or 'unknown', file.file)
            existing = conn.execute(
                'SELECT id,status FROM photos WHERE sha256=?', (processed['sha256'],)
            ).fetchone()
            if existing:
                photo_id = existing['id']
                duplicates.append({'name': file.filename, 'photoId': photo_id})
            else:
                photo_id = processed['id']
                conn.execute(
                    '''INSERT INTO photos(
                         id,original_name,original_path,sha256,title,taken_at,device,exif_lat,exif_lng
                       ) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (
                        photo_id, processed['original_name'], processed['original_path'],
                        processed['sha256'], Path(processed['original_name']).stem.replace('_', ' '),
                        processed['taken_at'], processed['device'],
                        processed['exif_lat'], processed['exif_lng'],
                    ),
                )
                added.append(photo_id)
            conn.execute(
                'INSERT OR IGNORE INTO photo_collections(photo_id,collection_id) VALUES(?,?)',
                (photo_id, collection_id),
            )
            status = existing['status'] if existing else 'draft'
            if status == 'draft' and photo_id not in review_ids:
                review_ids.append(photo_id)
        except (ValueError, OSError, sqlite3.DatabaseError) as exc:
            errors.append({'name': file.filename, 'error': str(exc)})
    conn.commit()
    return {
        'added': added,
        'duplicates': duplicates,
        'errors': errors,
        'reviewIds': review_ids,
    }
```

- [x] **Step 4: Run the focused tests, then the complete backend suite**

Run:

```bash
.venv313/bin/python -m pytest -q tests/test_api.py -k 'import_requires or import_links or repeated_file or import_keeps'
.venv313/bin/python -m pytest -q tests
```

Expected: focused tests PASS. The full suite may expose old import calls that still lack `collection_id`; update those calls through the shared `upload` helper rather than weakening the new endpoint contract, then rerun until all tests pass.

- [x] **Step 5: Record the non-Git checkpoint**

Mark Task 1 complete in this plan after saving the passing test output. Do not initialize a repository.

---

### Task 2: Atomic Review Save, Guess Where, and Tags

**Files:**
- Create: `apps/studio/backend/review.py`
- Modify: `apps/studio/backend/main.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `MANAGED_DEVICES` from `backend.devices`, existing Collection/tag/Guess tables, and a mapping with the complete review payload.
- Produces: `validate_review_date(value: str) -> bool`, `apply_review(conn, photo_id: str, payload: Mapping[str, Any]) -> None`, `PUT /api/photos/{photo_id}/review -> Photo`, and `GET /api/tags -> {tags: string[]}`.

- [x] **Step 1: Write failing tests for required fields, tag reuse, Guess removal, and rollback**

Add a complete payload helper and the endpoint tests to `tests/test_api.py`:

```python
def review_payload(client, photo_id, **overrides):
    photo = client.get(f'/api/photos/{photo_id}').json()
    payload = {
        'title': '',
        'taken_at': '2025-03',
        'description': '',
        'country': '', 'region': '', 'city': '', 'district': '',
        'location_query': '',
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

def test_review_saves_empty_title_homepage_and_case_insensitive_tags(client):
    photo_id = upload(client)
    saved = complete_review(
        client, photo_id, title='', featured=True,
        tags=['Street', 'street', 'Night'],
    )
    assert saved['title'] == ''
    assert saved['featured'] is True
    assert saved['status'] == 'modified'
    assert set(saved['tags']) == {'Street', 'Night'}
    assert client.get('/api/tags').json() == {'tags': ['Night', 'Street']}

def test_unchecking_guess_where_removes_an_existing_private_answer(client):
    photo_id = upload(client)
    guess = {
        'latitude': 31.2295, 'longitude': 121.4428,
        'precision': 'approximate', 'difficulty': 'medium',
        'answer_name': '静安区, 上海市, 中国',
        'answer_description': '', 'answer_radius_km': 15,
        'enabled': True, 'confirmed': True,
    }
    assert complete_review(
        client, photo_id, guess_enabled=True, guess=guess,
    )['guess']['confirmed'] is True
    removed = complete_review(client, photo_id, guess_enabled=False, guess=None)
    assert removed['guess'] is None

def test_atomic_review_rolls_back_when_a_late_database_write_fails(client):
    from backend.db import connect
    from backend.review import apply_review

    photo_id = upload(client)
    payload = review_payload(client, photo_id, title='Must roll back', guess_enabled=True, guess={
        'latitude': 31.2295, 'longitude': 121.4428,
        'precision': 'approximate', 'difficulty': 'medium',
        'answer_name': 'Shanghai', 'answer_description': '',
        'answer_radius_km': 15, 'enabled': True, 'confirmed': True,
    })
    conn = connect()
    try:
        conn.execute('''CREATE TEMP TRIGGER fail_guess BEFORE INSERT ON guess_where_entries
                        BEGIN SELECT RAISE(ABORT, 'forced late failure'); END''')
        with pytest.raises(sqlite3.IntegrityError, match='forced late failure'):
            apply_review(conn, photo_id, payload)
        row = conn.execute('SELECT title,status FROM photos WHERE id=?', (photo_id,)).fetchone()
        assert dict(row) == {'title': 'Evening in Tokyo', 'status': 'draft'}
        assert conn.execute(
            'SELECT COUNT(*) FROM guess_where_entries WHERE photo_id=?', (photo_id,)
        ).fetchone()[0] == 0
    finally:
        conn.close()
```

- [x] **Step 2: Run the focused review tests and verify they fail**

Run:

```bash
.venv313/bin/python -m pytest -q tests/test_api.py -k 'review_rejects or review_accepts or review_requires or review_saves or unchecking_guess or atomic_review'
```

Expected: FAIL because the review module, review endpoint, and tags endpoint do not exist.

- [x] **Step 3: Create the review service with validation and a savepoint**

Create `apps/studio/backend/review.py` with one responsibility: validate and atomically persist a complete review.

```python
from __future__ import annotations
from datetime import date
from typing import Any, Mapping

from .devices import MANAGED_DEVICES

class ReviewValidationError(ValueError):
    pass

def validate_review_date(value: str) -> bool:
    try:
        if len(value) == 7:
            year, month = map(int, value.split('-'))
            return 1000 <= year <= 9999 and 1 <= month <= 12
        if len(value) == 10:
            date.fromisoformat(value)
            return True
    except (TypeError, ValueError):
        return False
    return False

def _clean_tags(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = value.strip()
        key = tag.casefold()
        if not tag or key in seen:
            continue
        if len(tag) > 50:
            raise ReviewValidationError('Tags must be 1-50 characters')
        seen.add(key)
        cleaned.append(tag)
    return cleaned

def apply_review(
    conn,
    photo_id: str,
    payload: Mapping[str, Any],
) -> None:
    if not validate_review_date(str(payload['taken_at'])):
        raise ReviewValidationError('Date must include at least a valid month')
    if payload['device'] not in MANAGED_DEVICES:
        raise ReviewValidationError('Choose a camera/device')
    collection_ids = list(dict.fromkeys(payload['collectionIds']))
    if not collection_ids:
        raise ReviewValidationError('Choose at least one Collection')
    missing = [collection_id for collection_id in collection_ids if not conn.execute(
        'SELECT 1 FROM collections WHERE id=?', (collection_id,)
    ).fetchone()]
    if missing:
        raise ReviewValidationError(f'Unknown Collection: {missing[0]}')
    guess = payload.get('guess')
    if payload['guess_enabled'] and (
        not guess or not str(guess['answer_name']).strip() or not guess['confirmed']
    ):
        raise ReviewValidationError('Guess Where needs an answer and confirmed Pin')
    tags = _clean_tags(list(payload.get('tags') or []))

    conn.execute('SAVEPOINT atomic_review')
    try:
        # Update only the scalar fields listed by the PhotoReviewInput contract.
        conn.execute(
            '''UPDATE photos SET title=?,taken_at=?,description=?,country=?,region=?,city=?,
               district=?,location_query=?,device=?,featured=?,status='modified',
               updated_at=CURRENT_TIMESTAMP WHERE id=?''',
            (
                payload['title'].strip(), payload['taken_at'], payload['description'],
                payload['country'], payload['region'], payload['city'], payload['district'],
                payload['location_query'], payload['device'], int(payload['featured']), photo_id,
            ),
        )
        conn.execute('DELETE FROM photo_collections WHERE photo_id=?', (photo_id,))
        conn.executemany(
            'INSERT INTO photo_collections(photo_id,collection_id,position) VALUES(?,?,?)',
            [(photo_id, collection_id, index) for index, collection_id in enumerate(collection_ids)],
        )
        conn.execute('DELETE FROM photo_tags WHERE photo_id=?', (photo_id,))
        for tag in tags:
            conn.execute('INSERT OR IGNORE INTO tags(name) VALUES(?)', (tag,))
            tag_id = conn.execute(
                'SELECT id FROM tags WHERE name=? COLLATE NOCASE', (tag,)
            ).fetchone()[0]
            conn.execute(
                'INSERT INTO photo_tags(photo_id,tag_id) VALUES(?,?)', (photo_id, tag_id)
            )
        if payload['guess_enabled']:
            conn.execute(
                '''INSERT INTO guess_where_entries(
                     photo_id,latitude,longitude,precision,difficulty,answer_name,
                     answer_description,answer_radius_km,enabled,confirmed
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(photo_id) DO UPDATE SET
                     latitude=excluded.latitude,longitude=excluded.longitude,
                     precision=excluded.precision,difficulty=excluded.difficulty,
                     answer_name=excluded.answer_name,
                     answer_description=excluded.answer_description,
                     answer_radius_km=excluded.answer_radius_km,
                     enabled=excluded.enabled,confirmed=excluded.confirmed,
                     updated_at=CURRENT_TIMESTAMP''',
                (
                    photo_id, guess['latitude'], guess['longitude'], guess['precision'],
                    guess['difficulty'], guess['answer_name'].strip(),
                    guess['answer_description'].strip(), guess['answer_radius_km'],
                    1, 1,
                ),
            )
        else:
            conn.execute('DELETE FROM guess_where_entries WHERE photo_id=?', (photo_id,))
    except Exception:
        conn.execute('ROLLBACK TO atomic_review')
        conn.execute('RELEASE atomic_review')
        raise
    conn.execute('RELEASE atomic_review')
```

Use the exact managed-device container exported by `devices.py`; if it is a tuple rather than a set, membership behavior remains correct.

- [x] **Step 4: Add Pydantic request models and API routes**

In `apps/studio/backend/main.py`, define a complete input contract rather than reusing partial `PhotoUpdate`:

```python
class PhotoReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(default='', max_length=200)
    taken_at: str = Field(max_length=10)
    description: str = Field(default='', max_length=5000)
    country: str = Field(default='', max_length=150)
    region: str = Field(default='', max_length=150)
    city: str = Field(default='', max_length=150)
    district: str = Field(default='', max_length=150)
    location_query: str = Field(default='', max_length=300)
    device: Literal[
        'iPhone 6', 'iPhone 11', 'iPhone 14',
        'Sony NEX-C3', 'Sony a6400', 'Canon G3QL',
    ]
    featured: bool = False
    collectionIds: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list, max_length=100)
    guess_enabled: bool = False
    guess: GuessInput | None = None

@app.get('/api/tags')
def list_tags(conn=Depends(db)):
    return {'tags': [row[0] for row in conn.execute(
        'SELECT name FROM tags ORDER BY name COLLATE NOCASE'
    )]}

@app.put('/api/photos/{photo_id}/review')
def save_photo_review(photo_id: str, body: PhotoReviewInput, conn=Depends(db)):
    load_photo(conn, photo_id)
    try:
        apply_review(conn, photo_id, body.model_dump())
        conn.commit()
    except ReviewValidationError as exc:
        conn.rollback()
        raise HTTPException(422, str(exc))
    except Exception:
        conn.rollback()
        raise
    return photo_dict(conn, load_photo(conn, photo_id))
```

Import `apply_review` and `ReviewValidationError` from `.review`.

- [x] **Step 5: Run the focused review tests, then the full backend suite**

Run:

```bash
.venv313/bin/python -m pytest -q tests/test_api.py -k 'review_rejects or review_accepts or review_requires or review_saves or unchecking_guess or atomic_review'
.venv313/bin/python -m pytest -q tests
```

Expected: all focused tests PASS. Adapt older tests that save a complete photo to call `complete_review`; keep direct `PATCH` tests only for already reviewed photos.

- [x] **Step 6: Record the non-Git checkpoint**

Mark Task 2 complete after preserving the passing output. Do not initialize a repository.

---

### Task 3: Draft-only Needs Review and Optional-title Publishing

**Files:**
- Modify: `apps/studio/backend/main.py`
- Modify: `apps/studio/backend/publish.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Consumes: `validate_review_date` from `backend.review` and the `status` values `draft`, `modified`, and `published`.
- Produces: stats where `needReview` counts only drafts, publishing that excludes drafts but allows empty titles, and mutation guards preventing partial draft edits.

- [x] **Step 1: Write failing tests for draft status, patch/bulk guards, reviewed duplicates, and publishing**

Add these tests to `tests/test_api.py`:

```python
def test_needs_review_counts_only_drafts_and_reviewed_duplicate_skips_queue(client):
    collection_id = create_collection(client)
    photo_id = upload(client, collection_id)
    assert client.get('/api/stats').json()['needReview'] == 1
    complete_review(client, photo_id, title='')
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

def test_publish_skips_drafts_but_allows_reviewed_photo_without_title(client, tmp_path):
    draft_id = upload(client, filename='draft.jpg')
    reviewed_id = upload(client, filename='reviewed.jpg')
    complete_review(client, reviewed_id, title='', taken_at='2025-03')
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'package.json').write_text('{"name":"test-web"}')
    response = client.post('/api/publish/export', json={'web_root': str(web)})
    assert response.status_code == 200, response.text
    assert response.json()['count'] == 1
    data = json.loads((web / 'src/generated/photography.json').read_text())
    assert [item['id'] for item in data] == [reviewed_id]
    assert data[0]['title'] == ''
    assert draft_id not in json.dumps(data)
```

- [x] **Step 2: Run the status and publishing tests and verify they fail**

Run:

```bash
.venv313/bin/python -m pytest -q tests/test_api.py -k 'needs_review_counts or partial_patch or publish_skips'
```

Expected: FAIL because Needs Review still derives from publish validation, draft patch/bulk calls are accepted, and empty title blocks publishing.

- [x] **Step 3: Make status the review source of truth**

In `apps/studio/backend/main.py`:

```python
@app.get('/api/stats')
def stats(conn=Depends(db)):
    count = conn.execute('SELECT COUNT(*) FROM photos').fetchone()[0]
    ready, _ = collect(conn)
    needs_review = conn.execute(
        "SELECT COUNT(*) FROM photos WHERE status='draft'"
    ).fetchone()[0]
    pool = conn.execute(
        """SELECT COUNT(*) FROM guess_where_entries
           WHERE enabled=1 AND confirmed=1 AND TRIM(answer_name)<>''"""
    ).fetchone()[0]
    return {
        'photos': count, 'ready': len(ready), 'needReview': needs_review,
        'gamePool': pool,
        'collections': conn.execute('SELECT COUNT(*) FROM collections').fetchone()[0],
    }
```

At the start of `edit_photo`, reject draft rows with 409. Before changing anything in `bulk_update`, load every requested photo status and reject the whole request if any target is draft:

```python
row = load_photo(conn, photo_id)
if row['status'] == 'draft':
    raise HTTPException(409, 'Complete this photo through Needs Review first')
```

- [x] **Step 4: Update publishing validation**

In `apps/studio/backend/publish.py`, import `validate_review_date`, remove the old year-accepting `validate_date`, and make `collect` reject drafts rather than empty titles:

```python
def collect(conn):
    photo_rows = conn.execute(
        'SELECT * FROM photos ORDER BY created_at DESC, id'
    ).fetchall()
    valid, issues = [], []
    for row in photo_rows:
        photo = dict(row)
        errors = []
        if photo['status'] == 'draft':
            errors.append('Review not completed')
        if photo['status'] != 'draft' and not validate_review_date(photo['taken_at']):
            errors.append('Missing/invalid date (YYYY-MM or YYYY-MM-DD)')
        if not Path(photo['original_path']).is_file():
            errors.append('Original image missing')
        if errors:
            issues.append({
                'id': photo['id'], 'name': photo['original_name'], 'problems': errors,
            })
        else:
            valid.append(photo)
    return valid, issues
```

Update `main.py` to use `validate_review_date` for reviewed-photo edits and remove imports of the old validator.

- [x] **Step 5: Run focused and complete backend verification**

Run:

```bash
.venv313/bin/python -m pytest -q tests/test_api.py -k 'needs_review_counts or partial_patch or publish_skips'
.venv313/bin/python -m pytest -q tests
```

Expected: all tests PASS, including original-file hash and public Guess Where privacy tests.

- [x] **Step 6: Record the non-Git checkpoint**

Mark Task 3 complete after saving the test output. Do not initialize a repository.

---

### Task 4: Typed Frontend API and Testable Review Workflow State

**Files:**
- Create: `apps/studio/frontend/src/reviewWorkflow.ts`
- Create: `apps/studio/frontend/tests/reviewWorkflow.test.ts`
- Modify: `apps/studio/frontend/src/types.ts`
- Modify: `apps/studio/frontend/src/api.ts`

**Interfaces:**
- Consumes: backend `{added, duplicates, errors, reviewIds}`, `/api/tags`, and `/api/photos/{id}/review` contracts from Tasks 1-2.
- Produces: `ImportResult`, `PhotoReviewInput`, `ReviewDraft`, `reviewProblems`, `canStartImport`, `normalizeReviewQueue`, `api.tags`, and `api.reviewPhoto` for later components.

- [x] **Step 1: Write failing pure-state tests**

Create `apps/studio/frontend/tests/reviewWorkflow.test.ts`:

```typescript
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  canStartImport,
  normalizeReviewQueue,
  reviewProblems,
  type ReviewDraft,
} from '../src/reviewWorkflow.ts';
import type { Photo } from '../src/types.ts';

const draft = (overrides: Partial<ReviewDraft> = {}): ReviewDraft => ({
  taken_at: '2025-03',
  device: 'Sony a6400',
  collectionIds: ['c_1'],
  featured: false,
  guess_enabled: false,
  guess: null,
  ...overrides,
});

test('import starts only with a collection and supported files', () => {
  assert.equal(canStartImport('', 3), false);
  assert.equal(canStartImport('c_1', 0), false);
  assert.equal(canStartImport('c_1', 3), true);
});

test('review requires a month, managed device, and collection', () => {
  assert.deepEqual(reviewProblems(draft()), []);
  assert.ok(reviewProblems(draft({taken_at: '2025'})).includes('Date must include a month'));
  assert.ok(reviewProblems(draft({device: ''})).includes('Choose a camera/device'));
  assert.ok(reviewProblems(draft({collectionIds: []})).includes('Choose a Collection'));
});

test('checked Guess Where requires a confirmed named answer', () => {
  const problems = reviewProblems(draft({guess_enabled: true, guess: null}));
  assert.ok(problems.includes('Confirm the Guess Where answer Pin'));
});

test('queue drops duplicates, missing photos, and photos no longer in draft', () => {
  const photos = [
    {id: 'draft', status: 'draft'},
    {id: 'done', status: 'modified'},
  ] as Photo[];
  assert.deepEqual(
    normalizeReviewQueue(['draft', 'missing', 'done', 'draft'], photos),
    ['draft'],
  );
});
```

- [x] **Step 2: Run the new test and confirm the module is missing**

Run:

```bash
cd apps/studio/frontend
node --test tests/reviewWorkflow.test.ts
```

Expected: FAIL with a module-not-found error for `reviewWorkflow.ts`.

- [x] **Step 3: Add exact frontend contract types**

In `src/types.ts`, add:

```typescript
export type ImportResult = {
  added: string[];
  duplicates: {name: string; photoId: string}[];
  errors: {name: string; error: string}[];
  reviewIds: string[];
};

export type PhotoReviewInput = {
  title: string;
  taken_at: string;
  description: string;
  country: string;
  region: string;
  city: string;
  district: string;
  location_query: string;
  device: Exclude<Device, ''>;
  featured: boolean;
  collectionIds: string[];
  tags: string[];
  guess_enabled: boolean;
  guess: Omit<Guess, 'photo_id'> | null;
};
```

- [x] **Step 4: Implement the pure workflow functions**

Create `src/reviewWorkflow.ts`:

```typescript
import type {Device, Guess, Photo} from './types';

export type ReviewDraft = {
  taken_at: string;
  device: Device;
  collectionIds: string[];
  featured: boolean;
  guess_enabled: boolean;
  guess: Omit<Guess, 'photo_id'> | null;
};

const validDate = (value: string) => {
  if (/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return true;
  if (!/^\d{4}-(0[1-9]|1[0-2])-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
};

export function canStartImport(collectionId: string, fileCount: number) {
  return Boolean(collectionId) && fileCount > 0;
}

export function reviewProblems(draft: ReviewDraft): string[] {
  const problems: string[] = [];
  if (!validDate(draft.taken_at)) problems.push('Date must include a month');
  if (!draft.device) problems.push('Choose a camera/device');
  if (!draft.collectionIds.length) problems.push('Choose a Collection');
  if (draft.guess_enabled && (!draft.guess?.confirmed || !draft.guess.answer_name.trim())) {
    problems.push('Confirm the Guess Where answer Pin');
  }
  return problems;
}

export function normalizeReviewQueue(ids: string[], photos: Photo[]): string[] {
  const status = new Map(photos.map(photo => [photo.id, photo.status]));
  return [...new Set(ids)].filter(id => status.get(id) === 'draft');
}
```

- [x] **Step 5: Update API methods**

In `src/api.ts`, import the new types and replace `api.import` with the Collection-aware signature:

```typescript
import type {
  Collection, GradeResult, Guess, ImportResult, Photo, PhotoReviewInput,
  Place, PublishPreview, Settings, Stats,
} from './types';

import: async (files: File[], collectionId: string) => {
  const form = new FormData();
  form.append('collection_id', collectionId);
  files.forEach(file => form.append('files', file));
  return request<ImportResult>('/api/photos/import', {method: 'POST', body: form});
},
tags: () => request<{tags: string[]}>('/api/tags'),
reviewPhoto: (id: string, body: PhotoReviewInput) =>
  request<Photo>(`/api/photos/${id}/review`, json('PUT', body)),
```

- [x] **Step 6: Run frontend state tests and type/build verification**

Run:

```bash
cd apps/studio/frontend
node --test tests/reviewWorkflow.test.ts tests/connection.test.ts
npm run build
```

Expected: both Node tests PASS. The build may now identify old calls to `api.import(files)`; do not weaken the new signature. Task 5 replaces those callers.

- [x] **Step 7: Record the non-Git checkpoint**

Mark Task 4 complete after preserving test output and the expected temporary caller errors, if any. Do not initialize a repository.

---

### Task 5: Collection-first Import Dialog

**Files:**
- Create: `apps/studio/frontend/src/ImportDialog.tsx`
- Create: `apps/studio/frontend/src/review.css`
- Modify: `apps/studio/frontend/src/main.tsx`
- Modify: `apps/studio/frontend/src/App.tsx`

**Interfaces:**
- Consumes: `Collection`, `ImportResult`, `canStartImport`, `api.createCollection`, and `api.import(files, collectionId)`.
- Produces: `ImportDialog` invoking `onImported(result: ImportResult)` and an App-level `reviewQueue` sourced from `result.reviewIds`.

- [x] **Step 1: Extend pure tests for accepted file filtering and stable review IDs**

Add to `tests/reviewWorkflow.test.ts` before component work:

```typescript
import {supportedPhotoFiles} from '../src/reviewWorkflow.ts';

test('import keeps only supported photo filenames in selection order', () => {
  const files = [
    {name: 'a.JPG'}, {name: 'notes.txt'}, {name: 'b.HEIC'}, {name: 'c.tiff'},
  ] as File[];
  assert.deepEqual(
    supportedPhotoFiles(files).map(file => file.name),
    ['a.JPG', 'b.HEIC', 'c.tiff'],
  );
});
```

- [x] **Step 2: Run the test and confirm `supportedPhotoFiles` is missing**

Run:

```bash
cd apps/studio/frontend
node --test tests/reviewWorkflow.test.ts
```

Expected: FAIL because `supportedPhotoFiles` is not exported.

- [x] **Step 3: Implement the supported-file helper**

Add to `src/reviewWorkflow.ts`:

```typescript
export function supportedPhotoFiles<T extends {name: string}>(files: T[]): T[] {
  return files.filter(file => /\.(jpe?g|png|webp|tiff?|heic|heif)$/i.test(file.name));
}
```

Run the test again and expect PASS.

- [x] **Step 4: Create the import dialog**

Create `src/ImportDialog.tsx` with this public contract:

```typescript
type Props = {
  collections: Collection[];
  initialFiles?: File[];
  initialMode?: 'files' | 'folder';
  onCollectionCreated: (collection: Collection) => void;
  onImported: (result: ImportResult) => void;
  onClose: () => void;
  toast: (message: string, isError?: boolean) => void;
};

export default function ImportDialog(props: Props) { /* local UI state only */ }
```

Implement these concrete behaviors:

- render a required Collection `<select>`;
- render an inline “New Collection” title field and create button using `api.createCollection`;
- hold selected files locally and show their count;
- provide separate file and folder picker buttons, with `webkitdirectory` applied to the folder input;
- call `supportedPhotoFiles` before enabling import;
- disable import until `canStartImport(collectionId, files.length)` is true;
- import in 25-file chunks using the same Collection ID;
- merge chunk results while deduplicating `reviewIds` in first-seen order;
- report duplicate and error counts without treating duplicates as failures;
- call `onImported` only after all chunks finish.

Use actual JSX rather than moving upload state back into `App.tsx`. Keep the component responsible for Collection choice, inline creation, file selection, chunking, and progress.

- [x] **Step 5: Wire the dialog and queue into App**

In `src/App.tsx`:

```typescript
const [importOpen, setImportOpen] = useState(false);
const [importMode, setImportMode] = useState<'files'|'folder'>('files');
const [droppedFiles, setDroppedFiles] = useState<File[]>([]);
const [reviewQueue, setReviewQueue] = useState<string[]>([]);
const [reviewIndex, setReviewIndex] = useState(0);
```

Replace direct upload handlers:

- Add Photos opens `ImportDialog` in files mode.
- Import Folder opens it in folder mode.
- Dropping files opens it with `initialFiles` rather than uploading immediately.
- `onImported` refreshes photos, normalizes `result.reviewIds`, stores the queue, sets index zero, and opens the first draft.
- If there are no review IDs, close the dialog and show the duplicate/error summary without opening the editor.

Do not yet implement Save and next; Task 6 supplies the review editor callbacks.

- [x] **Step 6: Add focused dialog styles and import them**

Put only new import/review/tag styles in `src/review.css` and import it from `src/main.tsx` after the existing stylesheet:

```typescript
import './styles.css';
import './review.css';
```

Style the Collection choice, inline creation, file summary, disabled start button, and responsive dialog without rewriting the existing global stylesheet.

- [x] **Step 7: Run state tests and build**

Run:

```bash
cd apps/studio/frontend
node --test tests/reviewWorkflow.test.ts tests/connection.test.ts
npm run build
```

Expected: tests PASS and the production build exits 0.

- [x] **Step 8: Record the non-Git checkpoint**

Mark Task 5 complete after preserving output. Do not initialize a repository.

---

### Task 6: Tag Picker and Sequential Review Editor

**Files:**
- Create: `apps/studio/frontend/src/TagPicker.tsx`
- Modify: `apps/studio/frontend/src/PhotoEditor.tsx`
- Modify: `apps/studio/frontend/src/App.tsx`
- Modify: `apps/studio/frontend/src/review.css`
- Modify: `apps/studio/frontend/tests/reviewWorkflow.test.ts`

**Interfaces:**
- Consumes: `api.tags`, `api.reviewPhoto`, `reviewProblems`, `PhotoReviewInput`, and the App-level queue from Task 5.
- Produces: a review-capable `PhotoEditor` with progress, Save and next, Save and exit, Save and finish, local-only unsaved state, and existing-or-create tag selection.

- [x] **Step 1: Write failing tests for tag normalization and completion actions**

Add pure helpers and tests before UI wiring:

```typescript
import {addTag, completionLabel} from '../src/reviewWorkflow.ts';

test('adding a tag trims input and reuses a case-insensitive existing value', () => {
  assert.deepEqual(addTag(['Street'], [], ' street '), {
    options: ['Street'], selected: ['Street'],
  });
  assert.deepEqual(addTag(['Street'], [], 'Night'), {
    options: ['Street', 'Night'], selected: ['Night'],
  });
});

test('completion button labels distinguish next, exit, and final photo', () => {
  assert.equal(completionLabel('next', 0, 3), 'Save and next');
  assert.equal(completionLabel('exit', 0, 3), 'Save and exit');
  assert.equal(completionLabel('next', 2, 3), 'Save and finish');
});
```

- [x] **Step 2: Run tests and confirm the helpers are missing**

Run:

```bash
cd apps/studio/frontend
node --test tests/reviewWorkflow.test.ts
```

Expected: FAIL because `addTag` and `completionLabel` are not exported.

- [x] **Step 3: Implement tag and label helpers**

Add to `src/reviewWorkflow.ts`:

```typescript
export function addTag(options: string[], selected: string[], raw: string) {
  const value = raw.trim();
  if (!value) return {options, selected};
  const existing = options.find(option => option.toLocaleLowerCase() === value.toLocaleLowerCase());
  const tag = existing ?? value;
  return {
    options: existing ? options : [...options, value],
    selected: selected.includes(tag) ? selected : [...selected, tag],
  };
}

export function completionLabel(
  action: 'next'|'exit', index: number, total: number,
) {
  if (action === 'exit') return 'Save and exit';
  return index === total - 1 ? 'Save and finish' : 'Save and next';
}
```

Rerun the test and expect PASS.

- [x] **Step 4: Build the existing-or-create tag picker**

Create `src/TagPicker.tsx`:

```typescript
type Props = {
  options: string[];
  selected: string[];
  onOptionsChange: (options: string[]) => void;
  onChange: (selected: string[]) => void;
};

export default function TagPicker(props: Props) { /* searchable checkbox list + create */ }
```

Required behavior:

- filter existing tags case-insensitively as the user types;
- toggle multiple existing values;
- show `Create “<trimmed value>”` only when no case-insensitive exact match exists;
- use `addTag` for creation so case variants cannot create duplicate choices;
- expose selected tags as removable chips;
- never save merely because a tag was created locally; persistence occurs only with the atomic review request.

- [x] **Step 5: Convert PhotoEditor save to the atomic review contract**

Extend `PhotoEditor` props:

```typescript
type ReviewContext = {
  index: number;
  total: number;
  onSavedAndNext: (photo: Photo) => void;
  onSavedAndExit: (photo: Photo) => void;
};

type Props = {
  photo: Photo;
  collections: Collection[];
  settings: Settings;
  review?: ReviewContext;
  allTags: string[];
  onTagsChange: (tags: string[]) => void;
  onSaved: (photo: Photo) => void;
  onClose: () => void;
  toast: (message: string, isError?: boolean) => void;
};
```

Change the form as follows:

- title is visibly optional and no longer contributes to validation;
- date displays the imported EXIF value and shows `YYYY-MM or YYYY-MM-DD` guidance;
- device is required and retains the six managed options;
- Homepage is a normal checkbox bound to `featured`;
- Guess Where is a normal checkbox bound to `gameEnabled`;
- tags use `TagPicker` rather than comma-separated text;
- map search, Pin confirmation, radius, precision, and difficulty remain conditional on Guess Where;
- form state is local until save; do not call `savePhoto`, `setGuess`, or `removeGuess` separately.

Construct one `PhotoReviewInput`, run `reviewProblems`, and then call `api.reviewPhoto`:

```typescript
const payload: PhotoReviewInput = {
  ...form,
  title: form.title.trim(),
  tags,
  guess_enabled: gameEnabled,
  guess: gameEnabled && coords && confirmed ? {
    latitude: coords.latitude,
    longitude: coords.longitude,
    precision,
    difficulty,
    answer_name: answerName.trim(),
    answer_description: answerDescription.trim(),
    answer_radius_km: answerRadius,
    enabled: true,
    confirmed: true,
  } : null,
};
```

The Guess object intentionally omits `photo_id`; the backend derives it from the route. On validation failure, display the first problem and keep the editor open. On API failure, keep all local form state intact.

- [x] **Step 6: Add queue controls and discard protection**

When `review` is present:

- show `Review photo {index + 1} of {total}`;
- show both Save and exit and the context-sensitive next/finish button;
- disable both while saving;
- call the matching callback only after `api.reviewPhoto` succeeds;
- if the editor is dirty, call `window.confirm('Discard unsaved changes?')` before closing;
- if the user confirms, close without any API mutation, leaving the photo draft.

For a non-queue editor, keep a single Save changes action, but use the same complete review endpoint so reviewed photos retain valid required data.

- [x] **Step 7: Wire tags and queue advancement in App**

In `App.tsx`:

- load `api.tags()` with the existing photos/Collections/stats refresh or in a parallel initial request;
- after a successful review save, merge any newly created tags into the shared options;
- Save and next removes the completed ID, refreshes data, normalizes the remaining queue, and opens the next existing draft;
- Save and exit clears the queue and closes the editor;
- finishing the last item clears the queue and reports completion;
- if normalization removes every remaining ID, close review mode instead of leaving an empty editor.

- [x] **Step 8: Add focused review and tag styles**

Extend `review.css` with queue progress, two-action footer, validation summary, tag search/options/chips, and responsive layout. Preserve the existing MapLibre modal stacking order and map height.

- [x] **Step 9: Run frontend tests and build**

Run:

```bash
cd apps/studio/frontend
node --test tests/reviewWorkflow.test.ts tests/connection.test.ts
npm run build
```

Expected: all Node tests PASS and Vite build exits 0. Fix actual type mismatches rather than casting the review payload to `unknown` or `any`.

- [x] **Step 10: Record the non-Git checkpoint**

Mark Task 6 complete after preserving output. Do not initialize a repository.

---

### Task 7: Needs Review Resume Flow, Documentation, and End-to-end Verification

**Files:**
- Modify: `apps/studio/frontend/src/App.tsx`
- Modify: `apps/studio/frontend/src/review.css`
- Modify: `README.md`
- Modify: `tests/test_api.py`
- Modify: `docs/superpowers/plans/2026-10-16-collection-import-review-workflow-plan.md` (checkboxes only)

**Interfaces:**
- Consumes: draft status semantics, queue normalization, import dialog, and review editor from Tasks 1-6.
- Produces: a resumable Needs Review user path and final verified behavior across backend, frontend, browser, and documentation.

- [x] **Step 1: Add one final backend privacy and original-integrity regression**

Extend the existing hash/privacy test so the complete atomic review path is exercised rather than only the old partial endpoints:

```python
def test_atomic_review_and_export_keep_original_and_private_guess_data_safe(client, tmp_path):
    from backend.db import connect
    photo_id = upload(client)
    conn = connect()
    original = Path(conn.execute(
        'SELECT original_path FROM photos WHERE id=?', (photo_id,)
    ).fetchone()[0])
    conn.close()
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    complete_review(client, photo_id, title='', featured=True, tags=['Travel'],
        guess_enabled=True, guess={
            'latitude': 31.2295, 'longitude': 121.4428,
            'precision': 'approximate', 'difficulty': 'medium',
            'answer_name': '静安区, 上海市, 中国',
            'answer_description': '上海市中心附近', 'answer_radius_km': 15,
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
```

- [x] **Step 2: Run the privacy test and confirm it fails before helper migration is complete**

Run:

```bash
.venv313/bin/python -m pytest -q tests/test_api.py -k atomic_review_and_export
```

Expected before final wiring: FAIL if any old save path or export rule remains. After Tasks 1-6 are fully wired, it must PASS.

- [x] **Step 3: Make Needs Review a draft-only resume surface**

In `App.tsx`:

- change the Needs Review filter to `photo.status === 'draft'`;
- on the Needs Review view, show a `Review remaining photos` primary action when drafts exist;
- start the queue with the currently visible draft IDs in the displayed sort order;
- clicking a draft card starts or continues a queue beginning at that card;
- reviewed Gallery and Guess Where panels continue to use their existing independent navigation;
- show `Untitled` only as Library presentation fallback, not as persisted metadata.

The queue must be reconstructed from current photo records on every refresh with `normalizeReviewQueue`.

- [x] **Step 4: Update README to match the shipped workflow**

Revise the feature and organizing sections to state:

- Collection selection/create is mandatory before import;
- review is sequential and atomic;
- date requires at least a month and prefers EXIF;
- device is required and prefers EXIF;
- title is optional;
- Homepage and Guess Where are checkboxes;
- tags are existing-or-create multi-select values;
- Needs Review contains only draft/unreviewed photos;
- duplicates are linked into the chosen Collection without copying original data.

Keep the macOS setup, location service attribution, LLM configuration, and privacy guidance intact.

- [x] **Step 5: Run all automated verification fresh**

Run from the repository root:

```bash
.venv313/bin/python -m pytest -q tests
```

Then run from `apps/studio/frontend`:

```bash
node --test tests/connection.test.ts tests/reviewWorkflow.test.ts
npm run build
```

Expected: zero test failures and build exit code 0. Report the existing FastAPI/Starlette deprecation warning and Vite chunk-size warning if they remain; do not describe warnings as failures.

- [x] **Step 6: Verify the live API contracts**

With the backend and frontend already running, use the local browser/API to verify:

- import without Collection returns 422;
- import with a Collection returns ordered `reviewIds`;
- duplicate import returns the existing `photoId` and adds the Collection;
- `GET /api/tags` returns selected/created values;
- review save changes status from draft to modified;
- `/api/stats` decreases `needReview` only after successful review.

Use temporary generated test images or user-approved existing test fixtures; do not delete user photos or reset `.local/studio.sqlite3`.

- [x] **Step 7: Perform the browser workflow verification**

In the local Photo Booth at `http://127.0.0.1:5173/`, verify the following visible behavior:

1. Add Photos opens the Collection-first dialog.
2. Import remains disabled with no Collection or no files.
3. Inline Collection creation selects the created Collection.
4. Importing multiple test images opens review at `1 / N`.
5. EXIF date/device appear when available; missing values block save.
6. A manually entered `YYYY-MM` date is accepted; `YYYY` is rejected.
7. Existing tags can be selected and a new tag can be created.
8. Homepage works checked and unchecked.
9. Guess Where unchecked saves without an answer; checked requires a named, confirmed map Pin.
10. Save and next advances exactly once.
11. Save and exit closes review and leaves remaining photos under Needs Review.
12. Review remaining photos resumes the draft queue.
13. Collection and Guess Where remain separate sidebar panels.

Do not save fabricated metadata onto the user's real photo. If no disposable fixture is available, create temporary in-memory/generated image fixtures through the API using a temporary `PHOTO_BOOTH_DATA_DIR` backend instance.

- [x] **Step 8: Final file and privacy audit**

Inspect the final changed files and confirm:

- no original-photo write path was introduced;
- no private Guess Where fields were added to `publish.py` output;
- no import-batch table or decision columns were added;
- all draft mutations flow through the atomic review endpoint;
- the implementation matches the approved spec.

- [x] **Step 9: Record completion**

Mark every completed checkbox in this plan. Since the project is not a Git repository, report the exact modified files and fresh verification results instead of a commit hash.
