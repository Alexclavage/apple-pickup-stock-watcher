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
    try:
        report = json.loads(VALIDATION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    if not isinstance(report, dict) or not isinstance(report.get("observed_at"), str):
        return {}
    entries = report.get("markets")
    if not isinstance(entries, list):
        return {}
    followups = report.get("followups", [])
    if isinstance(followups, list):
        entries = entries + followups
    evidence = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("market"), str):
            continue
        if type(entry.get("catalog_parsed")) is not bool or type(entry.get("pickup_observed")) is not bool:
            continue
        if entry["pickup_observed"] and (
            not entry["catalog_parsed"]
            or type(entry.get("stores_returned")) is not int or entry["stores_returned"] < 1
            or type(entry.get("distinct_variants_observed")) is not int or entry["distinct_variants_observed"] < 2
            or type(entry.get("unknown_observations")) is not int or entry["unknown_observations"] != 0
            or type(entry.get("known_observations")) is not int
            or entry["known_observations"] != entry["stores_returned"] * entry["distinct_variants_observed"]
        ):
            continue
        evidence[entry["market"]] = {**entry, "observed_at": report["observed_at"]}
    return evidence


def validation_for_country(code):
    """Public bounded observations, never a guarantee of current inventory."""
    evidence = _validation().get(code)
    return dict(evidence) if evidence is not None else None
