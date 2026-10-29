from __future__ import annotations
import json
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, File, Form, UploadFile, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict

from .db import DATA_DIR, ORIGINALS, THUMBS, PREVIEWS, connect, setting, set_setting
from .images import process_upload
from .about_photo import about_photo_path, about_photo_state, save_about_photo
from .publish import collect, export_site, publish_git
from .grading import grade_pin
from .review import ReviewValidationError, apply_review, validate_review_date
from .secret_store import SecretStore, get_secret_store
from .ai_config import (
    AiConfigConflict, AiConfigError, activate_draft, draft_dict,
    list_versions, load_or_create_draft, restore_version, save_draft, record_test,
    version_dict,
)
from .ai_places import PlaceInterpretationError, interpret_place
from .ai_publish import AiPublishError, build_release, normalize_endpoint, publish_release

LOCAL_UI_ORIGINS = {
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect(); conn.close()
    yield

app = FastAPI(title="Photo Booth Local API", version="0.1.0", lifespan=lifespan)
# Only localhost clients. No wildcard CORS on a local file-management service.
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type"])

@app.middleware("http")
async def local_request_guard(request, call_next):
    # Browser pages from unrelated origins must not mutate private local data.
    from fastapi.responses import JSONResponse
    origin = request.headers.get("origin", "")
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and origin and origin not in LOCAL_UI_ORIGINS:
        return JSONResponse({"detail": "Cross-origin mutation denied"}, status_code=403)
    return await call_next(request)


def db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()

def photo_dict(conn, row):
    p = dict(row)
    p["featured"] = bool(p["featured"])
    p["thumbnailUrl"] = f"/api/photos/{p['id']}/thumbnail"
    p["previewUrl"] = f"/api/photos/{p['id']}/preview"
    p["collectionIds"] = [r[0] for r in conn.execute("SELECT collection_id FROM photo_collections WHERE photo_id=? ORDER BY position,collection_id", (p["id"],))]
    p["tags"] = [r[0] for r in conn.execute("SELECT t.name FROM tags t JOIN photo_tags pt ON t.id=pt.tag_id WHERE pt.photo_id=? ORDER BY t.name", (p["id"],))]
    g = conn.execute("SELECT * FROM guess_where_entries WHERE photo_id=?", (p["id"],)).fetchone()
    p["guess"] = dict(g) if g else None
    if g:
        p["guess"]["enabled"] = bool(g["enabled"])
        p["guess"]["confirmed"] = bool(g["confirmed"])
    p.pop("sha256", None)
    p.pop("original_path", None)
    return p

def load_photo(conn, id):
    row = conn.execute("SELECT * FROM photos WHERE id=?", (id,)).fetchone()
    if not row:
        raise HTTPException(404, "Photo not found")
    return row

class PhotoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    taken_at: str | None = Field(default=None, max_length=10)
    description: str | None = Field(default=None, max_length=5000)
    country: str | None = Field(default=None, max_length=150)
    region: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=150)
    district: str | None = Field(default=None, max_length=150)
    location_query: str | None = Field(default=None, max_length=300)
    device: Literal["", "iPhone 6", "iPhone 11", "iPhone 14", "Sony NEX-C3", "Sony a6400", "Canon G3QL"] | None = None
    featured: bool | None = None
    collectionIds: list[str] | None = None
    tags: list[str] | None = None

class BulkUpdate(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=1000)
    addCollectionIds: list[str] = Field(default_factory=list)
    addTags: list[str] = Field(default_factory=list)
    location: dict[str, str] | None = None

class CollectionInput(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=3000)

class GuessInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    precision: Literal["exact", "approximate"] = "exact"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    answer_name: str = Field(min_length=1, max_length=200)
    answer_description: str = Field(default="", max_length=1000)
    answer_radius_km: Literal[1, 10, 50, 100] = 10
    enabled: bool = True
    confirmed: bool = False

class PhotoReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    taken_at: str = Field(max_length=10)
    description: str = Field(default="", max_length=5000)
    device: Literal[
        "iPhone 6", "iPhone 11", "iPhone 14",
        "Sony NEX-C3", "Sony a6400", "Canon G3QL",
    ]
    featured: bool = False
    collectionIds: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list, max_length=100)
    guess_enabled: bool = False
    guess: GuessInput | None = None

class PinGradeInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

class SettingInput(BaseModel):
    web_root: str | None = None


class GoogleMapsConfigInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    map_id: str = Field(default="DEMO_MAP_ID", max_length=200)


class AiDraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: int | None = None
    retry_count: int | None = None
    prompt_text: str | None = None


class AiSecretInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    api_key: str | None = None
    clear: bool = False


class AiPlaceTestInput(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class AiRemoteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoint: str | None = Field(default=None, max_length=500)
    publisher_token: str | None = Field(default=None, max_length=1000)
    clear_token: bool = False


class AiPublishInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    include_deepseek_key: bool = False

class ExportInput(BaseModel):
    web_root: str = Field(min_length=1)

class GitInput(BaseModel):
    web_root: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=150)

@app.get("/api/health")
def health():
    return {"ok": True, "localData": str(DATA_DIR)}

@app.get("/api/stats")
def stats(conn=Depends(db)):
    count = conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    ready, _ = collect(conn)
    needs_review = conn.execute(
        "SELECT COUNT(*) FROM photos WHERE status='draft'"
    ).fetchone()[0]
    pool = conn.execute("SELECT COUNT(*) FROM guess_where_entries WHERE enabled=1 AND confirmed=1 AND TRIM(answer_name)<>''").fetchone()[0]
    return {"photos": count, "ready": len(ready), "needReview": needs_review, "gamePool": pool, "collections": conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]}

@app.get("/api/photos")
def list_photos(q: str = "", collection: str = "", status: str = "", game: bool = False, conn=Depends(db)):
    where = ["1=1"]
    params = []
    if q.strip():
        where.append("(p.title LIKE ? OR p.original_name LIKE ? OR p.city LIKE ? OR p.country LIKE ?)")
        params.extend([f"%{q.strip()}%"] * 4)
    if collection:
        where.append("EXISTS(SELECT 1 FROM photo_collections pc WHERE pc.photo_id=p.id AND pc.collection_id=?)")
        params.append(collection)
    if status:
        where.append("p.status=?"); params.append(status)
    if game:
        where.append("EXISTS(SELECT 1 FROM guess_where_entries g WHERE g.photo_id=p.id)")
    rows = conn.execute(f"SELECT p.* FROM photos p WHERE {' AND '.join(where)} ORDER BY p.created_at DESC,p.id DESC", params).fetchall()
    return [photo_dict(conn, p) for p in rows]

@app.post("/api/photos/import")
def import_photos(
    collection_id: str = Form(...),
    files: list[UploadFile] = File(...),
    conn=Depends(db),
):
    collection = conn.execute(
        "SELECT id FROM collections WHERE id=?", (collection_id,)
    ).fetchone()
    if not collection:
        raise HTTPException(422, "Choose an existing Collection before importing")
    if len(files) > 100:
        raise HTTPException(400, "Import up to 100 photos at a time")
    added, duplicates, errors, review_ids = [], [], [], []
    for file in files:
        try:
            p = process_upload(file.filename or "unknown", file.file)
            existing = conn.execute(
                "SELECT id,status,original_path FROM photos WHERE sha256=?", (p["sha256"],)
            ).fetchone()
            if existing:
                photo_id = existing["id"]
                duplicate_copy = Path(p["original_path"])
                if duplicate_copy != Path(existing["original_path"]):
                    duplicate_copy.unlink(missing_ok=True)
                duplicates.append({"name": file.filename, "photoId": photo_id})
                status = existing["status"]
            else:
                photo_id = p["id"]
                conn.execute(
                    "INSERT INTO photos(id,original_name,original_path,sha256,title,taken_at,device,exif_lat,exif_lng) VALUES(?,?,?,?,?,?,?,?,?)",
                    (photo_id, p["original_name"], p["original_path"], p["sha256"], "", p["taken_at"], p["device"], p["exif_lat"], p["exif_lng"]),
                )
                added.append(photo_id)
                status = "draft"
            conn.execute(
                "INSERT OR IGNORE INTO photo_collections(photo_id,collection_id) VALUES(?,?)",
                (photo_id, collection_id),
            )
            if status == "draft" and photo_id not in review_ids:
                review_ids.append(photo_id)
        except (ValueError, OSError, sqlite3.DatabaseError) as exc:
            errors.append({"name": file.filename, "error": str(exc)})
    conn.commit()
    return {
        "added": added,
        "duplicates": duplicates,
        "errors": errors,
        "reviewIds": review_ids,
    }

@app.get("/api/photos/{photo_id}")
def get_photo(photo_id: str, conn=Depends(db)):
    return photo_dict(conn, load_photo(conn, photo_id))


@app.delete("/api/photos/{photo_id}")
def delete_photo(photo_id: str, conn=Depends(db)):
    load_photo(conn, photo_id)
    conn.execute("DELETE FROM photos WHERE id=?", (photo_id,))
    conn.commit()
    for folder in (THUMBS, PREVIEWS):
        try:
            (folder / f"{photo_id}.webp").unlink(missing_ok=True)
        except OSError:
            # A stale derived preview is safe to leave behind and can be
            # cleaned up later; the archived original is never touched.
            pass
    return {"ok": True, "originalKept": True}


@app.put("/api/photos/{photo_id}/review")
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

@app.get("/api/photos/{photo_id}/{variant}")
def serve_photo(photo_id: str, variant: Literal["thumbnail", "preview"], conn=Depends(db)):
    load_photo(conn, photo_id)
    folder = THUMBS if variant == "thumbnail" else PREVIEWS
    target = folder / f"{photo_id}.webp"
    if not target.is_file():
        raise HTTPException(404, "Image preview not found")
    return FileResponse(target, media_type="image/webp", headers={"Cache-Control": "private,max-age=3600"})

@app.patch("/api/photos/{photo_id}")
def edit_photo(photo_id: str, changes: PhotoUpdate, conn=Depends(db)):
    row = load_photo(conn, photo_id)
    if row["status"] == "draft":
        raise HTTPException(409, "Complete this photo through Needs Review first")
    updates = changes.model_dump(exclude_unset=True)
    collections = updates.pop("collectionIds", None)
    tags = updates.pop("tags", None)
    if "taken_at" in updates and updates["taken_at"] and not validate_review_date(updates["taken_at"]):
        raise HTTPException(422, "Use YYYY-MM or YYYY-MM-DD for date")
    scalar = {key: (int(val) if key == "featured" else val) for key, val in updates.items() if val is not None}
    if scalar:
        clause = ", ".join(f"{key}=?" for key in scalar)
        conn.execute(f"UPDATE photos SET {clause},status='modified',updated_at=CURRENT_TIMESTAMP WHERE id=?", (*scalar.values(), photo_id))
    if collections is not None:
        for cid in collections:
            if not conn.execute("SELECT id FROM collections WHERE id=?", (cid,)).fetchone():
                raise HTTPException(422, f"Unknown collection: {cid}")
        conn.execute("DELETE FROM photo_collections WHERE photo_id=?", (photo_id,))
        conn.executemany("INSERT INTO photo_collections(photo_id,collection_id,position) VALUES(?,?,?)", [(photo_id, cid, i) for i, cid in enumerate(dict.fromkeys(collections))])
    if tags is not None:
        conn.execute("DELETE FROM photo_tags WHERE photo_id=?", (photo_id,))
        for tag in dict.fromkeys(t.strip() for t in tags if t.strip()):
            if len(tag) > 50:
                raise HTTPException(422, "Tag too long")
            conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (tag,))
            tid = conn.execute("SELECT id FROM tags WHERE name=? COLLATE NOCASE", (tag,)).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO photo_tags(photo_id,tag_id) VALUES(?,?)", (photo_id, tid))
    if collections is not None or tags is not None:
        conn.execute("UPDATE photos SET status='modified',updated_at=CURRENT_TIMESTAMP WHERE id=?", (photo_id,))
    conn.commit()
    return photo_dict(conn, load_photo(conn, photo_id))

@app.post("/api/photos/bulk")
def bulk_update(body: BulkUpdate, conn=Depends(db)):
    location = body.location or {}
    allowed = {"country", "region", "city", "district", "location_query"}
    if set(location) - allowed:
        raise HTTPException(422, "Invalid location fields")
    for cid in body.addCollectionIds:
        if not conn.execute("SELECT 1 FROM collections WHERE id=?", (cid,)).fetchone():
            raise HTTPException(422, f"Unknown collection {cid}")
    for pid in dict.fromkeys(body.ids):
        row = conn.execute("SELECT status FROM photos WHERE id=?", (pid,)).fetchone()
        if row and row["status"] == "draft":
            raise HTTPException(409, "Complete this photo through Needs Review first")
    updated = 0
    for pid in dict.fromkeys(body.ids):
        if not conn.execute("SELECT 1 FROM photos WHERE id=?", (pid,)).fetchone():
            continue
        for cid in body.addCollectionIds:
            conn.execute("INSERT OR IGNORE INTO photo_collections(photo_id,collection_id) VALUES(?,?)", (pid, cid))
        for tag in dict.fromkeys(t.strip() for t in body.addTags if t.strip()):
            if len(tag) > 50:
                raise HTTPException(422, "Tag too long")
            conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (tag,))
            tid = conn.execute("SELECT id FROM tags WHERE name=? COLLATE NOCASE", (tag,)).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO photo_tags(photo_id,tag_id) VALUES(?,?)", (pid, tid))
        for field, value in location.items():
            conn.execute(f"UPDATE photos SET {field}=? WHERE id=?", (value[:300], pid))
        conn.execute("UPDATE photos SET status='modified',updated_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))
        updated += 1
    conn.commit()
    return {"updated": updated}

@app.get("/api/tags")
def list_tags(conn=Depends(db)):
    return {
        "tags": [
            row[0]
            for row in conn.execute(
                "SELECT name FROM tags ORDER BY name COLLATE NOCASE"
            )
        ]
    }

@app.get("/api/collections")
def collections(conn=Depends(db)):
    return [dict(r) | {"count": conn.execute("SELECT COUNT(*) FROM photo_collections WHERE collection_id=?", (r["id"],)).fetchone()[0]} for r in conn.execute("SELECT * FROM collections ORDER BY created_at DESC,id")]

@app.post("/api/collections")
def create_collection(body: CollectionInput, conn=Depends(db)):
    cid = "c_" + uuid.uuid4().hex[:12]
    conn.execute("INSERT INTO collections(id,title,description) VALUES(?,?,?)", (cid,body.title.strip(),body.description))
    conn.commit()
    return {"id": cid, **body.model_dump()}

@app.patch("/api/collections/{collection_id}")
def edit_collection(collection_id: str, body: CollectionInput, conn=Depends(db)):
    cursor = conn.execute("UPDATE collections SET title=?,description=? WHERE id=?", (body.title.strip(),body.description,collection_id))
    if cursor.rowcount == 0:
        raise HTTPException(404, "Collection not found")
    conn.commit()
    return {"id": collection_id, **body.model_dump()}

@app.delete("/api/collections/{collection_id}")
def delete_collection(collection_id: str, conn=Depends(db)):
    conn.execute("DELETE FROM collections WHERE id=?", (collection_id,))
    conn.commit()
    return {"ok": True}

@app.post("/api/collections/{collection_id}/reorder")
def reorder_collection(collection_id: str, photo_ids: list[str], conn=Depends(db)):
    existing = {r[0] for r in conn.execute("SELECT photo_id FROM photo_collections WHERE collection_id=?", (collection_id,))}
    if len(photo_ids) != len(existing) or set(photo_ids) != existing:
        raise HTTPException(422, "Provide all and only photo IDs in this collection")
    conn.executemany("UPDATE photo_collections SET position=? WHERE collection_id=? AND photo_id=?", [(i,collection_id,pid) for i,pid in enumerate(photo_ids)])
    conn.commit()
    return {"ok": True}

@app.put("/api/guess/{photo_id}")
def set_guess(photo_id: str, body: GuessInput, conn=Depends(db)):
    row = load_photo(conn, photo_id)
    if row["status"] == "draft":
        raise HTTPException(409, "Complete this photo through Needs Review first")
    conn.execute("""INSERT INTO guess_where_entries(photo_id,latitude,longitude,precision,difficulty,answer_name,answer_description,answer_radius_km,enabled,confirmed)
      VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(photo_id) DO UPDATE SET latitude=excluded.latitude,longitude=excluded.longitude,
      precision=excluded.precision,difficulty=excluded.difficulty,answer_name=excluded.answer_name,
      answer_description=excluded.answer_description,answer_radius_km=excluded.answer_radius_km,
      enabled=excluded.enabled,confirmed=excluded.confirmed,updated_at=CURRENT_TIMESTAMP""",
      (photo_id,body.latitude,body.longitude,body.precision,body.difficulty,body.answer_name.strip(),body.answer_description.strip(),body.answer_radius_km,int(body.enabled),int(body.confirmed)))
    conn.commit()
    return photo_dict(conn,load_photo(conn,photo_id))

@app.delete("/api/guess/{photo_id}")
def delete_guess(photo_id: str, conn=Depends(db)):
    row = load_photo(conn, photo_id)
    if row["status"] == "draft":
        raise HTTPException(409, "Complete this photo through Needs Review first")
    conn.execute("DELETE FROM guess_where_entries WHERE photo_id=?", (photo_id,))
    conn.commit()
    return {"ok": True}

def load_playable_guess(conn, photo_id: str):
    row = conn.execute("SELECT * FROM guess_where_entries WHERE photo_id=? AND enabled=1 AND confirmed=1 AND TRIM(answer_name)<>''", (photo_id,)).fetchone()
    if not row:
        raise HTTPException(409, "Guess Where answer is not ready")
    return dict(row)

@app.post("/api/guess/{photo_id}/grade-pin")
def grade_pin_preview(photo_id: str, body: PinGradeInput, conn=Depends(db)):
    entry = load_playable_guess(conn, photo_id)
    return grade_pin(entry["latitude"], entry["longitude"], body.latitude, body.longitude, entry["answer_radius_km"])

@app.get("/api/settings")
def get_settings(conn=Depends(db)):
    return {"web_root": setting(conn,"web_root"), "about_photo": about_photo_state(conn)}

@app.patch("/api/settings")
def update_settings(body: SettingInput, conn=Depends(db)):
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key,value.strip()))
    conn.commit()
    return get_settings(conn)


@app.post("/api/settings/about-photo")
def upload_about_photo(file: UploadFile = File(...), conn=Depends(db)):
    try:
        key, name = save_about_photo(file.filename or "", file.file)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    set_setting(conn, "about_photo_file", key)
    set_setting(conn, "about_photo_name", name)
    conn.commit()
    return get_settings(conn)


@app.get("/api/settings/about-photo")
def get_about_photo(v: str = "", conn=Depends(db)):
    key = setting(conn, "about_photo_file")
    if not key or (v and v != key):
        raise HTTPException(404, "About photo not found")
    path = about_photo_path(key)
    if not path or not path.is_file():
        raise HTTPException(404, "About photo not found")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


def _masked_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def _google_maps_config(conn, secrets: SecretStore) -> dict:
    api_key = secrets.get("google-maps-browser-key")
    return {
        "apiKeyConfigured": bool(api_key),
        "apiKeyMask": _masked_secret(api_key),
        "mapId": setting(conn, "google_maps_map_id", "DEMO_MAP_ID"),
    }


@app.get("/api/maps/config")
def get_google_maps_config(
    conn=Depends(db),
    secrets: SecretStore = Depends(get_secret_store),
):
    return _google_maps_config(conn, secrets)


@app.put("/api/maps/config")
def update_google_maps_config(
    body: GoogleMapsConfigInput,
    conn=Depends(db),
    secrets: SecretStore = Depends(get_secret_store),
):
    if body.clear_api_key and body.api_key is not None:
        raise HTTPException(422, "Choose either a replacement key or clear the existing key")
    if body.clear_api_key:
        secrets.delete("google-maps-browser-key")
    elif body.api_key is not None:
        api_key = body.api_key.strip()
        if not api_key:
            raise HTTPException(422, "Google Maps API key cannot be blank")
        secrets.set("google-maps-browser-key", api_key)
    set_setting(conn, "google_maps_map_id", body.map_id.strip() or "DEMO_MAP_ID")
    conn.commit()
    return _google_maps_config(conn, secrets)


@app.get("/api/maps/bootstrap")
def google_maps_bootstrap(
    request: Request,
    conn=Depends(db),
    secrets: SecretStore = Depends(get_secret_store),
):
    origin = request.headers.get("origin", "")
    if origin and origin not in LOCAL_UI_ORIGINS:
        raise HTTPException(403, "Local frontend only")
    return {
        "apiKey": secrets.get("google-maps-browser-key"),
        "mapId": setting(conn, "google_maps_map_id", "DEMO_MAP_ID"),
    }


def _ai_secret_state(secrets: SecretStore) -> dict:
    value = secrets.get('deepseek-api-key')
    return {'configured': bool(value), 'mask': _masked_secret(value)}


def _ai_remote_state(conn, secrets: SecretStore) -> dict:
    token = secrets.get('ai-place-publisher-token')
    last = conn.execute(
        """SELECT version,remote_published_at,remote_publish_receipt
           FROM ai_place_versions WHERE remote_published_at IS NOT NULL
           ORDER BY remote_published_at DESC,version DESC LIMIT 1"""
    ).fetchone()
    return {
        'endpoint': setting(conn, 'ai_place_remote_endpoint'),
        'tokenConfigured': bool(token),
        'tokenMask': _masked_secret(token),
        'lastPublishedVersion': last['version'] if last else None,
        'lastPublishedAt': last['remote_published_at'] if last else None,
        'lastReceipt': last['remote_publish_receipt'] if last else '',
    }


@app.get('/api/ai-places/config')
def get_ai_places_config(conn=Depends(db), secrets: SecretStore = Depends(get_secret_store)):
    draft = load_or_create_draft(conn)
    active = next((version_dict(item) for item in list_versions(conn) if item.version == draft.active_version), None)
    return {
        'draft': draft_dict(draft), 'active': active,
        'secret': _ai_secret_state(secrets), 'remote': _ai_remote_state(conn, secrets),
    }


@app.patch('/api/ai-places/draft')
def update_ai_places_draft(body: AiDraftInput, conn=Depends(db)):
    try:
        return draft_dict(save_draft(conn, body.model_dump(exclude_unset=True, exclude_none=True)))
    except (AiConfigError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None


@app.put('/api/ai-places/secrets/deepseek')
def update_deepseek_secret(body: AiSecretInput, conn=Depends(db), secrets: SecretStore = Depends(get_secret_store)):
    if body.clear == (body.api_key is not None):
        raise HTTPException(422, 'Choose a replacement key or clear the existing key')
    if body.clear:
        secrets.delete('deepseek-api-key')
    else:
        value = (body.api_key or '').strip()
        if not value:
            raise HTTPException(422, 'DeepSeek API key cannot be blank')
        secrets.set('deepseek-api-key', value)
    conn.execute("UPDATE ai_place_draft SET test_state='untested',tested_hash='',test_summary='' WHERE singleton_id=1")
    conn.commit()
    return _ai_secret_state(secrets)


@app.post('/api/ai-places/test')
def test_ai_places(body: AiPlaceTestInput, conn=Depends(db), secrets: SecretStore = Depends(get_secret_store)):
    draft = load_or_create_draft(conn)
    key = secrets.get('deepseek-api-key')
    if not key:
        raise HTTPException(503, 'Configure the DeepSeek API key first')
    started = time.monotonic()
    try:
        result = interpret_place(body.text, draft, key)
    except PlaceInterpretationError as error:
        raise HTTPException(503, {'code': error.code, 'message': str(error)}) from None
    latency = round((time.monotonic() - started) * 1000)
    summary = f'{result.status}: {result.normalized_query or result.clarification}'
    try:
        record_test(conn, draft.config_hash, summary)
    except AiConfigConflict as error:
        raise HTTPException(409, str(error)) from None
    return {'interpretation': result.model_dump(), 'testedHash': draft.config_hash, 'modelLatencyMs': latency}


@app.post('/api/ai-places/interpret')
def interpret_active_ai_place(body: AiPlaceTestInput, conn=Depends(db), secrets: SecretStore = Depends(get_secret_store)):
    draft = load_or_create_draft(conn)
    if not draft.active_version:
        raise HTTPException(409, 'Activate a tested AI place configuration first')
    active = next((item for item in list_versions(conn) if item.version == draft.active_version), None)
    if not active:
        raise HTTPException(409, 'The locally active AI place configuration could not be found')
    key = secrets.get('deepseek-api-key')
    if not key:
        raise HTTPException(503, 'Configure the DeepSeek API key first')
    started = time.monotonic()
    try:
        result = interpret_place(body.text, active, key)
    except PlaceInterpretationError as error:
        raise HTTPException(503, {'code': error.code, 'message': str(error)}) from None
    latency = round((time.monotonic() - started) * 1000)
    return {
        'interpretation': result.model_dump(),
        'activeVersion': active.version,
        'configHash': active.config_hash,
        'modelLatencyMs': latency,
    }


@app.post('/api/ai-places/activate')
def activate_ai_places(conn=Depends(db)):
    try:
        return version_dict(activate_draft(conn))
    except AiConfigConflict as error:
        raise HTTPException(409, str(error)) from None


@app.get('/api/ai-places/versions')
def get_ai_places_versions(conn=Depends(db)):
    return [version_dict(item) for item in list_versions(conn)]


@app.post('/api/ai-places/versions/{version}/restore')
def restore_ai_places_version(version: int, conn=Depends(db)):
    try:
        return draft_dict(restore_version(conn, version))
    except AiConfigError as error:
        raise HTTPException(404, str(error)) from None


@app.put('/api/ai-places/remote')
def update_ai_places_remote(body: AiRemoteInput, conn=Depends(db), secrets: SecretStore = Depends(get_secret_store)):
    if body.clear_token and body.publisher_token is not None:
        raise HTTPException(422, 'Choose a replacement publisher token or clear the existing token')
    if body.endpoint is not None:
        endpoint = body.endpoint.strip()
        if endpoint:
            try:
                endpoint = normalize_endpoint(endpoint)
            except AiPublishError as error:
                raise HTTPException(422, str(error)) from None
        set_setting(conn, 'ai_place_remote_endpoint', endpoint)
    if body.clear_token:
        secrets.delete('ai-place-publisher-token')
    elif body.publisher_token is not None:
        token = body.publisher_token.strip()
        if not token:
            raise HTTPException(422, 'Publisher token cannot be blank')
        secrets.set('ai-place-publisher-token', token)
    conn.commit()
    return _ai_remote_state(conn, secrets)


@app.post('/api/ai-places/publish')
def publish_ai_places(body: AiPublishInput, conn=Depends(db), secrets: SecretStore = Depends(get_secret_store)):
    draft = load_or_create_draft(conn)
    if not draft.active_version:
        raise HTTPException(409, 'Activate a tested configuration before publishing')
    active = next((item for item in list_versions(conn) if item.version == draft.active_version), None)
    if not active:
        raise HTTPException(409, 'The locally active configuration could not be found')
    if draft.test_state != 'passed' or draft.tested_hash != draft.config_hash or active.config_hash != draft.config_hash:
        raise HTTPException(409, 'Test and activate the exact current draft before publishing')
    endpoint = setting(conn, 'ai_place_remote_endpoint')
    token = secrets.get('ai-place-publisher-token')
    deepseek_key = secrets.get('deepseek-api-key') if body.include_deepseek_key else ''
    try:
        release = build_release(active, body.include_deepseek_key, deepseek_key)
        receipt = publish_release(endpoint, token, release)
    except AiPublishError as error:
        status = 409 if error.code in {'invalid_endpoint', 'missing_token', 'missing_key'} else 503
        raise HTTPException(status, {'code': error.code, 'message': str(error)}) from None
    conn.execute(
        """UPDATE ai_place_versions SET
             remote_published_at=CURRENT_TIMESTAMP,remote_publish_receipt=?
           WHERE version=? AND config_hash=?""",
        (receipt['receipt'], active.version, active.config_hash),
    )
    conn.commit()
    state = _ai_remote_state(conn, secrets)
    return {
        'version': active.version, 'promptHash': active.config_hash,
        'receipt': receipt['receipt'], 'publishedAt': state['lastPublishedAt'],
    }

@app.get("/api/publish/preview")
def publish_preview(conn=Depends(db)):
    photos, issues = collect(conn)
    pending = conn.execute("SELECT COUNT(*) FROM guess_where_entries WHERE enabled=1 AND confirmed=0").fetchone()[0]
    return {"ready": len(photos),"issues": issues,"unconfirmedGameEntries": pending,"note": "Game coordinates remain local; D1 sync is a separate integration."}

@app.post("/api/publish/export")
def export(body: ExportInput):
    try:
        return export_site(body.web_root)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, str(exc))

@app.post("/api/publish/github")
def push_to_github(body: GitInput):
    try:
        return publish_git(body.web_root,body.message)
    except (OSError, ValueError) as exc:
        raise HTTPException(400, str(exc))
