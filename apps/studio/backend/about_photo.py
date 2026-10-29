"""Private storage and public export helpers for the standalone About portrait."""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .db import DATA_DIR, setting
from .images import ALLOWED, make_resized

ABOUT_PHOTOS = DATA_DIR / "about-photos"
MAX_ABOUT_UPLOAD_BYTES = 80 * 1024 * 1024
_ABOUT_KEY = re.compile(r"^[a-f0-9]{64}\.(?:jpg|jpeg|png|webp|tif|tiff|heic|heif)$")


def safe_about_name(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1] or "about-photo"


def save_about_photo(name: str, source) -> tuple[str, str]:
    display_name = safe_about_name(name)
    suffix = Path(display_name).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError(f"Unsupported image type: {suffix or '(none)'}")

    content = bytearray()
    while chunk := source.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > MAX_ABOUT_UPLOAD_BYTES:
            raise ValueError("About photo exceeds 80 MB upload limit")
    if not content:
        raise ValueError("About photo is empty")

    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 100_000_000:
                raise ValueError("About photo dimensions are too large")
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("Could not decode About photo") from exc

    key = f"{hashlib.sha256(content).hexdigest()}{suffix}"
    target = about_photo_path(key)
    assert target is not None
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(content)
    return key, display_name


def about_photo_path(key: str) -> Path | None:
    if not _ABOUT_KEY.fullmatch(key):
        return None
    return ABOUT_PHOTOS / key


def about_photo_state(conn) -> dict | None:
    key = setting(conn, "about_photo_file")
    if not key:
        return None
    path = about_photo_path(key)
    return {
        "name": setting(conn, "about_photo_name", "about-photo"),
        "url": f"/api/settings/about-photo?v={key}",
        "available": bool(path and path.is_file()),
    }


def export_about_photo(conn, web_root: Path, generated_dir: Path) -> dict | None:
    key = setting(conn, "about_photo_file")
    config = None
    if key:
        source = about_photo_path(key)
        if not source or not source.is_file():
            raise ValueError("The configured About photo is missing locally; upload it again before exporting")
        destination = web_root / "public" / "about" / "about-photo.webp"
        width, height = make_resized(source, destination, 2200, 86)
        config = {"src": "/about/about-photo.webp", "width": width, "height": height}
    (generated_dir / "about-photo.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config
