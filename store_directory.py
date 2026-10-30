"""Offline snapshot of Apple's public worldwide retail directory.

Store presence is not evidence that a pickup endpoint or a product is supported.
No requests, scanning threads, user configuration or private data are involved.
"""
from functools import lru_cache
import json
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parent / "data" / "apple_stores.json"


@lru_cache(maxsize=1)
def _directory():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def directory_countries():
    return [{"code": c["code"], "name": c["name"], "stores": len(c["stores"])}
            for c in _directory()["countries"]]


def stores_for_country(code):
    for country in _directory()["countries"]:
        if country["code"] == code:
            return {
                "market": code, "source": _directory()["source"],
                "observed_at": _directory()["observed_at"],
                "stores": [dict(store) for store in country["stores"]],
            }
    raise ValueError("Country is not present in the official directory snapshot")
