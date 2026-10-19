"""Conservative photo intake: originals copied unchanged, EXIF kept private."""
from __future__ import annotations
import hashlib
import io
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass  # HEIC support is optional in environments without pillow-heif.
from .db import ORIGINALS, THUMBS, PREVIEWS
from .devices import normalize_device

ALLOWED = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif"}

def exiftool_meta(path: Path) -> dict:
    if not shutil.which("exiftool"):
        return {}
    try:
        run = subprocess.run(
            ["exiftool", "-json", "-n", "-DateTimeOriginal", "-CreateDate", "-GPSLatitude", "-GPSLongitude", "-Make", "-Model", str(path)],
            check=True, capture_output=True, text=True, timeout=20
        )
        return json.loads(run.stdout)[0]
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, KeyError):
        return {}

def read_metadata(path: Path) -> dict:
    data = exiftool_meta(path)
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            data.setdefault("Make", exif.get(271) or "")
            data.setdefault("Model", exif.get(272) or "")
            if not data.get("DateTimeOriginal"):
                stamp = exif.get(36867) or exif.get(306)
                if stamp:
                    data["DateTimeOriginal"] = str(stamp)
            # Pillow fallback if ExifTool is not installed or GPS tags are absent.
            if "GPSLatitude" not in data or "GPSLongitude" not in data:
                try:
                    gps = exif.get_ifd(34853)  # GPSInfo EXIF IFD
                    def degrees(tags):
                        return float(tags[0]) + float(tags[1]) / 60 + float(tags[2]) / 3600
                    if gps.get(2) and gps.get(4):
                        lat = degrees(gps[2])
                        lng = degrees(gps[4])
                        if str(gps.get(1, "N")).upper().startswith("S"):
                            lat = -lat
                        if str(gps.get(3, "E")).upper().startswith("W"):
                            lng = -lng
                        data.setdefault("GPSLatitude", lat)
                        data.setdefault("GPSLongitude", lng)
                except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError):
                    pass
    except (OSError, UnidentifiedImageError):
        pass
    date_text = str(data.get("DateTimeOriginal") or data.get("CreateDate") or "")
    date_text = date_text[:10].replace(":", "-")
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
    except ValueError:
        date_text = ""
    lat = data.get("GPSLatitude")
    lng = data.get("GPSLongitude")
    if not (isinstance(lat, (int, float)) and -90 <= lat <= 90):
        lat = None
    if not (isinstance(lng, (int, float)) and -180 <= lng <= 180):
        lng = None
    return {
        "taken_at": date_text,
        "exif_lat": lat,
        "exif_lng": lng,
        "device": normalize_device(data.get("Make"), data.get("Model")),
    }

def make_resized(src: Path, dest: Path, max_size: int, quality: int = 82) -> tuple[int, int]:
    with Image.open(src) as source:
        im = ImageOps.exif_transpose(source)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        if im.mode == "RGBA":
            background = Image.new("RGB", im.size, (246, 245, 241))
            background.paste(im, mask=im.getchannel("A"))
            im = background
        im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Re-encoding deliberately drops EXIF, including GPS.
        im.save(dest, format="WEBP", quality=quality, method=5)
        return im.size

def process_upload(name: str, source, limit: int = 80 * 1024 * 1024) -> dict:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError(f"Unsupported file type: {suffix or '(none)'}")
    sha = hashlib.sha256()
    chunks = io.BytesIO()
    total = 0
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError("File exceeds 80 MB upload limit")
        sha.update(chunk)
        chunks.write(chunk)
    if not total:
        raise ValueError("Empty file")
    digest = sha.hexdigest()
    photo_id = "p_" + digest[:20]
    target = ORIGINALS / f"{photo_id}{suffix}"
    if not target.exists():
        target.write_bytes(chunks.getvalue())
    try:
        make_resized(target, THUMBS / f"{photo_id}.webp", 480, 74)
        make_resized(target, PREVIEWS / f"{photo_id}.webp", 1600, 85)
        meta = read_metadata(target)
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise ValueError(f"Could not decode photo: {exc}") from exc
    return {"id": photo_id, "sha256": digest, "original_path": str(target), "original_name": Path(name).name, **meta}
