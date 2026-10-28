"""Offline coverage for multi-area US/Canada pickup monitoring."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher
from monitoring_areas import MAX_MONITORING_AREAS, legacy_areas, validate_monitoring_areas
from setup_wizard import validate_config


US_PRODUCT = {"market": "US", "name": "Phone US", "part": "PART-US", "price": 1000, "currency": "USD"}
CA_PRODUCT = {"market": "CA", "name": "Phone CA", "part": "PART-CA", "price": 1400, "currency": "CAD"}
PRODUCTS = {"us_phone": US_PRODUCT, "ca_phone": CA_PRODUCT}


def store(store_id, state="DE"):
    return {"storeNumber": store_id, "storeName": store_id, "city": "Example", "state": state}


def simplified_item(raw, pid):
    return {
        "key": f"{pid}:{raw['storeNumber']}",
        "product_id": pid,
        "storeNumber": raw["storeNumber"],
        "storeName": raw["storeName"],
        "market": PRODUCTS[pid]["market"],
        "status": raw.get("status", "available"),
        "price": 1000,
        "total": 1000,
    }


class MonitoringAreaTests(unittest.TestCase):
    def test_multiple_countries_and_store_subsets_are_valid(self):
        areas = [
            {"id": "de", "market": "US", "location": "19702", "store_ids": []},
            {"id": "toronto", "market": "CA", "location": "M5B 2H1", "store_ids": ["R121"]},
            {"id": "montreal", "market": "CA", "location": "Montreal", "store_ids": []},
        ]
        self.assertEqual(validate_monitoring_areas(areas, PRODUCTS), areas)

    def test_unsupported_country_does_not_silently_work(self):
        with self.assertRaisesRegex(ValueError, "Unsupported country"):
            validate_monitoring_areas([{"id": "fr", "market": "FR", "location": "75001"}], PRODUCTS)

    def test_duplicate_country_location_is_rejected(self):
        areas = [
            {"id": "toronto", "market": "CA", "location": "Toronto"},
            {"id": "toronto_other", "market": "CA", "location": "TORONTO"},
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate search location"):
            validate_monitoring_areas(areas, PRODUCTS)

    def test_us_requires_five_digit_zip(self):
        with self.assertRaisesRegex(ValueError, "five-digit ZIP"):
            validate_monitoring_areas([{"id": "nyc", "market": "US", "location": "New York"}], PRODUCTS)

    def test_eight_area_cap(self):
        areas = [{"id": f"area_{i}", "market": "US", "location": f"{i:05d}"} for i in range(MAX_MONITORING_AREAS + 1)]
        with self.assertRaisesRegex(ValueError, "1-8"):
            validate_monitoring_areas(areas, PRODUCTS)

    def test_legacy_migration_keeps_canadian_store_target(self):
        areas = legacy_areas({"DE": "19702"}, "M5B 2H1", "R121", PRODUCTS)
        self.assertEqual(len(areas), 2)
        self.assertEqual(areas[0]["location"], "19702")
        self.assertEqual(areas[1]["store_ids"], ["R121"])

    def test_wizard_accepts_new_areas_without_legacy_locations(self):
        data = {
            "products": PRODUCTS,
            "allowed_states": [],
            "search_zips": {},
            "ca_location": "",
            "ca_target_store": "",
            "ca_tax_rate": 0.13,
            "monitoring_areas": [
                {"id": "us", "market": "US", "location": "19702", "store_ids": []},
                {"id": "ca", "market": "CA", "location": "Toronto", "store_ids": []},
            ],
        }
        clean = validate_config(data)
        self.assertEqual(len(clean["monitoring_areas"]), 2)

    def test_overlapping_areas_do_not_duplicate_results(self):
        areas = [
            {"id": "us1", "market": "US", "location": "19702", "store_ids": []},
            {"id": "us2", "market": "US", "location": "10001", "store_ids": []},
            {"id": "ca1", "market": "CA", "location": "M5B 2H1", "store_ids": []},
            {"id": "ca2", "market": "CA", "location": "Montreal", "store_ids": ["R999"]},
        ]
        seen_locations = []
        def fetch(_url, location, _product_ids):
            seen_locations.append(location)
            if location in ("19702", "10001"):
                return [store("R102")]
            if location == "M5B 2H1":
                return [store("R121")]
            return [store("R999"), store("OTHER")]
        with (
            patch.object(watcher, "MONITORING_AREAS", areas),
            patch.object(watcher, "US_PRODUCT_IDS", ["us_phone"]),
            patch.object(watcher, "CA_PRODUCT_IDS", ["ca_phone"]),
            patch.object(watcher, "ALLOWED_STATES", {"DE"}),
            patch.object(watcher, "fetch_market", side_effect=fetch),
            patch.object(watcher, "parse_item", side_effect=simplified_item),
            patch.object(watcher.time, "sleep"),
        ):
            rows, errors = watcher.fetch_all()
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 3)
        self.assertEqual(seen_locations, ["19702", "10001", "M5B 2H1", "Montreal"])
        self.assertEqual({row["storeNumber"] for row in rows}, {"R102", "R121", "R999"})

    def test_rate_limit_stops_remaining_searches(self):
        areas = [
            {"id": "us1", "market": "US", "location": "19702", "store_ids": []},
            {"id": "us2", "market": "US", "location": "10001", "store_ids": []},
            {"id": "us3", "market": "US", "location": "14225", "store_ids": []},
        ]
        called = []
        def fetch(_url, location, _product_ids):
            called.append(location)
            if location == "10001":
                raise RuntimeError("APPLE_429")
            return [store("R102")]
        with (
            patch.object(watcher, "MONITORING_AREAS", areas),
            patch.object(watcher, "US_PRODUCT_IDS", ["us_phone"]),
            patch.object(watcher, "CA_PRODUCT_IDS", []),
            patch.object(watcher, "ALLOWED_STATES", {"DE"}),
            patch.object(watcher, "fetch_market", side_effect=fetch),
            patch.object(watcher, "parse_item", side_effect=simplified_item),
            patch.object(watcher.time, "sleep"),
        ):
            rows, errors = watcher.fetch_all()
        self.assertEqual(called, ["19702", "10001"])
        self.assertEqual(len(rows), 1)
        self.assertTrue(any("rate limit" in error for error in errors))

    def test_conflicting_observations_do_not_announce_false_change(self):
        first = {"key": "us_phone:R102", "status": "available"}
        second = {"key": "us_phone:R102", "status": "unavailable"}
        merged = watcher.merge_area_results(first, second)
        self.assertEqual(merged["status"], "unknown")
        self.assertIn("Conflicting", merged["quote"])


if __name__ == "__main__":
    unittest.main()
