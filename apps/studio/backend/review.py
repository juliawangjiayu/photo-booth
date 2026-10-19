"""Validate and atomically persist a complete photo review."""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from .devices import MANAGED_DEVICES


class ReviewValidationError(ValueError):
    pass


def validate_review_date(value: str) -> bool:
    try:
        if len(value) == 7:
            year, month = map(int, value.split("-"))
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
            raise ReviewValidationError("Tags must be 1-50 characters")
        seen.add(key)
        cleaned.append(tag)
    return cleaned


def apply_review(conn, photo_id: str, payload: Mapping[str, Any]) -> None:
    if not validate_review_date(str(payload["taken_at"])):
        raise ReviewValidationError("Date must include at least a valid month")
    if payload["device"] not in MANAGED_DEVICES:
        raise ReviewValidationError("Choose a camera/device")

    collection_ids = list(dict.fromkeys(payload["collectionIds"]))
    if not collection_ids:
        raise ReviewValidationError("Choose at least one Collection")
    missing = [
        collection_id
        for collection_id in collection_ids
        if not conn.execute(
            "SELECT 1 FROM collections WHERE id=?", (collection_id,)
        ).fetchone()
    ]
    if missing:
        raise ReviewValidationError(f"Unknown Collection: {missing[0]}")

    guess = payload.get("guess")
    if payload["guess_enabled"] and (
        not guess
        or not str(guess["answer_name"]).strip()
        or not guess["confirmed"]
    ):
        raise ReviewValidationError("Guess Where needs an answer and confirmed Pin")
    tags = _clean_tags(list(payload.get("tags") or []))

    conn.execute("SAVEPOINT atomic_review")
    try:
        conn.execute(
            """UPDATE photos SET title='',taken_at=?,description=?,country='',region='',city='',
               district='',location_query='',device=?,featured=?,status='modified',
               updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (
                payload["taken_at"],
                payload["description"],
                payload["device"],
                int(payload["featured"]),
                photo_id,
            ),
        )
        conn.execute("DELETE FROM photo_collections WHERE photo_id=?", (photo_id,))
        conn.executemany(
            "INSERT INTO photo_collections(photo_id,collection_id,position) VALUES(?,?,?)",
            [
                (photo_id, collection_id, index)
                for index, collection_id in enumerate(collection_ids)
            ],
        )
        conn.execute("DELETE FROM photo_tags WHERE photo_id=?", (photo_id,))
        for tag in tags:
            conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (tag,))
            tag_id = conn.execute(
                "SELECT id FROM tags WHERE name=? COLLATE NOCASE", (tag,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO photo_tags(photo_id,tag_id) VALUES(?,?)",
                (photo_id, tag_id),
            )

        if payload["guess_enabled"]:
            conn.execute(
                """INSERT INTO guess_where_entries(
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
                     updated_at=CURRENT_TIMESTAMP""",
                (
                    photo_id,
                    guess["latitude"],
                    guess["longitude"],
                    guess["precision"],
                    guess["difficulty"],
                    guess["answer_name"].strip(),
                    guess["answer_description"].strip(),
                    guess["answer_radius_km"],
                    1,
                    1,
                ),
            )
        else:
            conn.execute(
                "DELETE FROM guess_where_entries WHERE photo_id=?", (photo_id,)
            )
    except Exception:
        conn.execute("ROLLBACK TO atomic_review")
        conn.execute("RELEASE atomic_review")
        raise
    conn.execute("RELEASE atomic_review")
