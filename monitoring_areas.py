"""Validate and migrate selected Apple Retail pickup search areas.

A monitoring area makes one regional pickup availability request per scan.
It does not imply coverage of every store in a city or country.
"""
import re
from regions import REGIONS, region_for, normalize_location

SUPPORTED_MARKETS = set(REGIONS)
MAX_MONITORING_AREAS = 8
AREA_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$")
STORE_ID = re.compile(r"^[a-zA-Z0-9_-]{2,20}$")
US_ZIP = re.compile(r"^[0-9]{5}$")


def validate_monitoring_areas(value, products, enable_experimental=False):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_MONITORING_AREAS:
        raise ValueError(f"monitoring_areas must contain 1-{MAX_MONITORING_AREAS} areas")
    markets_with_products = {p["market"] for p in products.values()}
    result = []
    seen_ids = set()
    seen_locations = set()
    for position, raw in enumerate(value, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Area {position} must be an object")
        area_id = raw.get("id")
        if not isinstance(area_id, str) or not AREA_ID.fullmatch(area_id):
            raise ValueError(f"Area {position} must have a valid id")
        if area_id in seen_ids:
            raise ValueError(f"Duplicate area ID: {area_id}")
        seen_ids.add(area_id)

        market = raw.get("market")
        try:
            region_for(market, enable_experimental)
        except ValueError as exc:
            raise ValueError(f"Unsupported country/market for area {area_id}: {exc}") from exc
        if market not in markets_with_products:
            raise ValueError(f"Area {area_id} has no configured {market} products")
        location = raw.get("location")
        if not isinstance(location, str) or not 2 <= len(location.strip()) <= 64:
            raise ValueError(f"Area {area_id} needs a location (2-64 characters)")
        try:
            location = normalize_location(market, location)
        except ValueError as exc:
            raise ValueError(f"Area {area_id}: {exc}") from exc
        dedup_key = (market, location.upper())
        if dedup_key in seen_locations:
            raise ValueError(f"Duplicate search location: {market} {location}")
        seen_locations.add(dedup_key)

        store_ids = raw.get("store_ids", [])
        if not isinstance(store_ids, list) or len(store_ids) > 30:
            raise ValueError(f"Area {area_id}: store_ids must be an array of at most 30 store IDs")
        if any(not isinstance(store, str) or not STORE_ID.fullmatch(store) for store in store_ids):
            raise ValueError(f"Area {area_id}: invalid Apple Store ID")
        if len(set(store_ids)) != len(store_ids):
            raise ValueError(f"Area {area_id}: store_ids contains duplicates")
        result.append({
            "id": area_id,
            "market": market,
            "location": location,
            "store_ids": list(store_ids),
        })
    return result


def legacy_areas(search_zips, ca_location, ca_target_store, products):
    """Map old US ZIP and single Canadian target to the new multi-area model."""
    markets = {product["market"] for product in products.values()}
    result = []
    if "US" in markets:
        for i, (name, zip_code) in enumerate(search_zips.items(), 1):
            result.append({
                "id": f"us_{i}",
                "market": "US",
                "location": zip_code,
                "store_ids": [],
            })
    if "CA" in markets and ca_location:
        result.append({
            "id": "ca_1",
            "market": "CA",
            "location": ca_location,
            "store_ids": [ca_target_store] if ca_target_store else [],
        })
    return validate_monitoring_areas(result, products)
