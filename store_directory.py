"""Offline snapshot of Apple's public worldwide retail directory.

Store presence is not evidence that a pickup endpoint or a product is supported.
No requests, scanning threads, user configuration or private data are involved.
"""
from functools import lru_cache
import json
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parent / "data" / "apple_stores.json"
VALIDATION_FILE = DATA_FILE.with_name("regional_validation.json")


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


@lru_cache(maxsize=1)
def _validation():
    if not VALIDATION_FILE.is_file():
        return {}
    report = json.loads(VALIDATION_FILE.read_text(encoding="utf-8"))
    return {entry["market"]: {**entry, "observed_at": report["observed_at"]}
            for entry in report["markets"]}


def validation_for_country(code):
    """Public bounded observations, never a guarantee of current inventory."""
    evidence = _validation().get(code)
    return dict(evidence) if evidence is not None else None
