"""Normalize camera metadata to Photo Booth's managed device choices."""
from __future__ import annotations

MANAGED_DEVICES = (
    "iPhone 6",
    "iPhone 11",
    "iPhone 14",
    "Sony NEX-C3",
    "Sony a6400",
    "Canon G3QL",
)


def normalize_device(make: object = "", model: object = "") -> str:
    """Return one managed value, or an empty string for unknown metadata."""
    text = " ".join(str(value or "").strip() for value in (make, model)).casefold()
    compact = "".join(ch for ch in text if ch.isalnum())
    if "iphone14" in compact:
        return "iPhone 14"
    if "iphone11" in compact:
        return "iPhone 11"
    if "iphone6" in compact:
        return "iPhone 6"
    if "nexc3" in compact:
        return "Sony NEX-C3"
    if "ilce6400" in compact or "a6400" in compact:
        return "Sony a6400"
    if "g3ql" in compact or "powershotg3" in compact:
        return "Canon G3QL"
    return ""
