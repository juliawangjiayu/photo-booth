"""Export only public assets. Guess answers are NEVER written to the web tree."""
from __future__ import annotations
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from .db import connect
from .about_photo import export_about_photo
from .images import make_resized
from .review import validate_review_date

MANAGED_PATHS = [
    "public/photos",
    "src/generated/photography.json",
    "src/generated/collections.json",
    "src/generated/about-photo.json",
]

def collect(conn):
    photo_rows = conn.execute("SELECT * FROM photos ORDER BY created_at DESC, id").fetchall()
    valid, issues = [], []
    for row in photo_rows:
        p = dict(row)
        errors = []
        if p["status"] == "draft":
            errors.append("Review not completed")
        if p["status"] != "draft" and not validate_review_date(p["taken_at"]):
            errors.append("Missing/invalid date (YYYY-MM or YYYY-MM-DD)")
        if not Path(p["original_path"]).is_file():
            errors.append("Original image missing")
        if errors:
            issues.append({"id": p["id"], "name": p["original_name"], "problems": errors})
        else:
            valid.append(p)
    return valid, issues

def export_site(web_root: str) -> dict:
    root = Path(web_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("Web project folder does not exist")
    if not (root / "package.json").exists():
        raise ValueError("Select a Next.js project folder containing package.json")
    conn = connect()
    try:
        photos, issues = collect(conn)
        if not photos:
            raise ValueError("No publishable photos. Complete photo review first.")
        public = root / "public" / "photos"
        generated = root / "src" / "generated"
        public.mkdir(parents=True, exist_ok=True)
        generated.mkdir(parents=True, exist_ok=True)
        output = []
        for row in photos:
            pid = row["id"]
            filename = f"{pid}.webp"
            thumb = f"{pid}-thumb.webp"
            out_file = public / filename
            thumb_file = public / thumb
            width, height = make_resized(Path(row["original_path"]), out_file, 2200, 86)
            make_resized(Path(row["original_path"]), thumb_file, 640, 76)
            col_ids = [r[0] for r in conn.execute(
                "SELECT collection_id FROM photo_collections WHERE photo_id=? ORDER BY position,collection_id", (pid,)
            )]
            tags = [r[0] for r in conn.execute(
                "SELECT t.name FROM tags t JOIN photo_tags pt ON pt.tag_id=t.id WHERE pt.photo_id=? ORDER BY t.name", (pid,)
            )]
            output.append({
                "id": pid, "takenAt": row["taken_at"],
                "description": row["description"] or None,
                "device": row["device"] or None,
                "image": {"src": f"/photos/{filename}", "thumbnail": f"/photos/{thumb}", "width": width, "height": height},
                "collections": col_ids, "tags": tags, "featured": bool(row["featured"])
            })
        collections = [dict(r) for r in conn.execute("SELECT * FROM collections ORDER BY created_at,id")]
        # Stable UTF-8 JSON output; zero longitude/latitude fields in public export.
        (generated / "photography.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (generated / "collections.json").write_text(json.dumps([
            {"id": c["id"], "title": c["title"], "description": c["description"]} for c in collections
        ], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        about_photo = export_about_photo(conn, root, generated)
        timestamp = datetime.now(timezone.utc).isoformat()
        conn.executemany("UPDATE photos SET status='published', published_at=? WHERE id=?", [(timestamp, p["id"]) for p in photos])
        managed_paths = [*MANAGED_PATHS]
        if about_photo is not None:
            managed_paths.append("public/about/about-photo.webp")
        result = {"count": len(photos), "skipped": issues, "webRoot": str(root), "files": managed_paths}
        conn.execute("INSERT INTO publish_records(target,photo_count,details) VALUES(?,?,?)", (str(root), len(photos), json.dumps(result)))
        conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('web_root',?)", (str(root),))
        conn.commit()
        return result
    finally:
        conn.close()

def run_git(root: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=90, check=False)
    if cp.returncode:
        raise ValueError((cp.stderr or cp.stdout or "Git command failed").strip()[:1200])
    return cp.stdout.strip()

def publish_git(web_root: str, message: str) -> dict:
    root = Path(web_root).expanduser().resolve()
    if not (root / "src" / "generated" / "photography.json").exists():
        raise ValueError("Export locally before publishing to GitHub")
    if not message.strip() or len(message) > 150:
        raise ValueError("Commit message must be 1-150 characters")
    # The selected Next.js app may be nested inside a monorepo. Discover Git root.
    try:
        repo_root = Path(run_git(root, "rev-parse", "--show-toplevel")).resolve()
        prefix = root.relative_to(repo_root)
    except (OSError, ValueError):
        raise ValueError("Selected Next.js folder is not inside a Git repository")
    relative_paths = [str(prefix / p) for p in MANAGED_PATHS]
    about_asset = root / "public" / "about" / "about-photo.webp"
    if about_asset.is_file():
        relative_paths.append(str(prefix / "public/about/about-photo.webp"))
    # Never include unrelated user changes or pre-staged files in our commit.
    if run_git(repo_root, "diff", "--cached", "--name-only"):
        raise ValueError("Existing staged changes detected. Commit/unstage them before Photo Booth publishes.")
    run_git(repo_root, "add", "-A", "--", *relative_paths)
    changed = run_git(repo_root, "diff", "--cached", "--name-only")
    if not changed:
        return {"pushed": False, "message": "No managed file changes to publish"}
    # Only stage our explicitly managed public files; game coordinates remain in local SQLite.
    run_git(repo_root, "commit", "-m", message.strip())
    branch = run_git(repo_root, "branch", "--show-current")
    if not branch:
        raise ValueError("Commit created, but branch is detached; push manually")
    run_git(repo_root, "push", "origin", branch)
    return {"pushed": True, "branch": branch, "files": changed.splitlines()}
