"""SQLite storage. All private data is kept outside the public web tree."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.environ.get("PHOTO_BOOTH_DATA_DIR", str(ROOT / ".local"))).expanduser().resolve()
ORIGINALS = DATA_DIR / "originals"
THUMBS = DATA_DIR / "thumbs"
PREVIEWS = DATA_DIR / "previews"
DB_PATH = DATA_DIR / "studio.sqlite3"

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS photos (
  id TEXT PRIMARY KEY,
  original_name TEXT NOT NULL,
  original_path TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL DEFAULT '',
  taken_at TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL DEFAULT '',
  district TEXT NOT NULL DEFAULT '',
  location_query TEXT NOT NULL DEFAULT '',
  device TEXT NOT NULL DEFAULT '' CHECK(device IN ('','iPhone 6','iPhone 11','iPhone 14','Sony NEX-C3','Sony a6400','Canon G3QL')),
  exif_lat REAL,
  exif_lng REAL,
  featured INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  published_at TEXT
);
CREATE TABLE IF NOT EXISTS collections (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS photo_collections (
  photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (photo_id, collection_id)
);
CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL COLLATE NOCASE UNIQUE
);
CREATE TABLE IF NOT EXISTS photo_tags (
  photo_id TEXT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (photo_id, tag_id)
);
CREATE TABLE IF NOT EXISTS guess_where_entries (
  photo_id TEXT PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
  latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
  longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
  precision TEXT NOT NULL CHECK(precision IN ('exact','approximate')),
  difficulty TEXT NOT NULL DEFAULT 'medium' CHECK(difficulty IN ('easy','medium','hard')),
  answer_name TEXT NOT NULL,
  answer_description TEXT NOT NULL DEFAULT '',
  answer_radius_km INTEGER NOT NULL CHECK(answer_radius_km IN (1,10,50,100)),
  enabled INTEGER NOT NULL DEFAULT 1,
  confirmed INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS publish_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target TEXT NOT NULL,
  photo_count INTEGER NOT NULL,
  details TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_photo_status ON photos(status);
CREATE INDEX IF NOT EXISTS idx_photo_created ON photos(created_at);
"""

def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for folder in (ORIGINALS, THUMBS, PREVIEWS):
        folder.mkdir(parents=True, exist_ok=True)
    # FastAPI may enter, use, and close a sync dependency on different worker
    # threads. Each request still owns its connection; allow that hand-off.
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.executescript(SCHEMA)
    return conn

def setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default
