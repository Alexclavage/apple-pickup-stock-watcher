"""Offline tests for one-click model selection and safe batch monitoring."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher
from model_watch import (
    MAX_PRODUCTS, ModelSelectionError, expand_model, expected_requests,
    family_for, model_catalog_result, validate_request_budget,
)
from setup_wizard import InvalidConfig, create_wizard_app, validate_config


def sample(market="US", model="iphone-18-pro", count=8, family_type="iphone18pro"):
    rows = []
    for i in range(count):
        rows.append({
            "market": market,
            "family": "iphone-18-pro",
            "family_type": family_type,
            "part": f"MX{i:03d}LL/A",
            "name": f"iPhone 18 Pro {i} Color",
            "currency": "USD" if market == "US" else "CAD",
            "price": None,
        })
    return rows


def region(market="US", location="19702"):
    return {"id": "area", "market": market, "location": location, "store_ids": []}


class ModelWatchTests(unittest.TestCase):
    def test_model_name_selects_all_colours_and_capacities(self):
        rows = sample(count=16)
        result = model_catalog_result("iphone-18-pro", "US", rows)
        self.assertEqual(result["count"], 16)
        self.assertEqual(result["missing_prices"], 16)
        self.assertEqual(len(set(p["part"] for p in result["products"])), 16)
        self.assertEqual({p["watch_model"] for p in result["products"]}, {"iphone-18-pro"})

    def test_pro_and_pro_max_do_not_get_mixed_up(self):
        rows = sample(count=8) + sample(count=6, family_type="iphone18promax")
        normal = expand_model("iphone-18-pro", "US", rows)
        big = expand_model("iphone-18-pro-max", "US", rows)
        self.assertEqual(len(normal), 8)
        self.assertEqual(len(big), 6)
        self.assertEqual(family_for("iphone-18-pro-max"), "iphone-18-pro")

    def test_unknown_model_and_empty_skus_fail_explicitly(self):
        with self.assertRaises(ModelSelectionError):
            family_for("../../anything")
        with self.assertRaisesRegex(ModelSelectionError, "No matching"):
            expand_model("iphone-18-pro", "CA", sample("US"))

    def test_more_than_48_variants_fail_not_silently_truncate(self):
        with self.assertRaisesRegex(ModelSelectionError, "above the 48-SKU"):
            expand_model("iphone-18-pro", "US", sample(count=49))

    def test_request_budget_batches_and_deduplicates_skus(self):
        products = {
            str(i): {"market": "US", "part": f"ITEM{i}LL/A"}
            for i in range(25)
        }
        products["duplicate"] = {"market": "US", "part": "ITEM0LL/A"}
        areas = [region(), {"id": "other", "market": "US", "location": "10001", "store_ids": []}]
        self.assertEqual(expected_requests(products, areas), 6)
        self.assertEqual(validate_request_budget(products, areas), 6)

    def test_guard_rejects_large_monitoring_scan(self):
        products = {str(i): {"market": "US", "part": f"ITEM{i}LL/A"} for i in range(49)}
        areas = [{"id": str(i), "market": "US", "location": "10001"} for i in range(6)]
        with self.assertRaisesRegex(ModelSelectionError, "Too many monitoring combinations"):
            validate_request_budget(products, areas)

    def test_unknown_prices_do_not_break_server_or_money_output(self):
        product = {
            "market": "US", "name": "No price", "part": "MJQ84LL/A",
            "price": None, "currency": "USD",
        }
        with patch.object(watcher, "PRODUCTS", {"unknown_price": product}):
            item = watcher.parse_item({
                "storeNumber": "R102", "storeName": "Example",
                "city": "Newark", "state": "DE",
                "partsAvailability": {"MJQ84LL/A": {"pickupDisplay": "available"}},
            }, "unknown_price")
        self.assertEqual(item["status"], "available")
        self.assertIsNone(item["total"])
        self.assertIsNone(item["price_eur"])
        self.assertIn("not confirmed", watcher.price_total_text(item).lower())
        self.assertEqual(watcher.app.test_client().get("/").status_code, 200)

    def test_wizard_accepts_generated_product_without_price(self):
        product = {
            "market": "US", "name": "iPhone 18 Pro Silver 512 GB",
            "part": "MJQ84LL/A", "price": None, "currency": "USD",
            "watch_model": "iphone-18-pro",
        }
        data = {
            "products": {"us_mjq": product},
            "monitoring_areas": [region()],
            "search_zips": {}, "allowed_states": [], "ca_tax_rate": 0.13,
        }
        result = validate_config(data)
        self.assertIsNone(result["products"]["us_mjq"]["price"])
        self.assertEqual(result["products"]["us_mjq"]["watch_model"], "iphone-18-pro")

    def test_invalid_watched_model_fails_validation(self):
        data = {
            "products": {"a": {
                "market": "US", "name": "X", "part": "MJQ84LL/A",
                "price": None, "currency": "USD", "watch_model": "made_up",
            }},
            "monitoring_areas": [region()],
        }
        with self.assertRaisesRegex(InvalidConfig, "Unknown monitored model"):
            validate_config(data)

    def test_batch_fetch_uses_12_skus_without_repeated_stores(self):
        products = {
            f"p{i}": {"market": "US", "name": "Example", "part": f"ITEM{i:03d}LL/A",
                     "currency": "USD", "price": None}
            for i in range(25)
        }
        calls = []
        def request(_url, _location, ids):
            calls.append(list(ids))
            return [{"storeNumber": "R102", "storeName": "Example", "city": "Newark", "state": "DE",
                     "partsAvailability": {products[x]["part"]: {"pickupDisplay": "unavailable"} for x in ids}}]
        with (
            patch.object(watcher, "PRODUCTS", products),
            patch.object(watcher, "US_PRODUCT_IDS", list(products)),
            patch.object(watcher, "MONITORING_AREAS", [region()]),
            patch.object(watcher, "fetch_market", side_effect=request),
            patch.object(watcher, "get_eur_rate", return_value=(1.0, None)),
            patch.object(watcher.time, "sleep"),
        ):
            found, errors = watcher.fetch_all()
        self.assertEqual(errors, [])
        self.assertEqual([len(x) for x in calls], [12, 12, 1])
        self.assertEqual(len(found), 25)

    def test_wizard_route_for_model_is_protected_and_uses_one_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample_path = root / "example.json"
            sample_path.write_text(json.dumps({
                "products": {"test": {"market": "US", "name": "Test", "part": "MJQ84LL/A",
                                      "price": 1399, "currency": "USD"}},
                "search_zips": {"NY": "10001"}, "allowed_states": [],
            }))
            webapp = create_wizard_app(root / "config.json", sample_path)
            client = webapp.test_client()
            html = client.get("/").data
            token = re.search(rb'const TOKEN = "([^"]+)"', html).group(1).decode("ascii")
            self.assertIn(b"1. Find variants", html)
            selection = {"model_id": "iphone-18-pro", "market": "US"}
            self.assertEqual(client.post("/api/catalog/model", json=selection).status_code, 403)
            with patch("setup_wizard.fetch_catalog", return_value={"items": sample(count=2), "cached": True}) as lookup:
                valid = client.post("/api/catalog/model", json=selection, headers={"X-Setup-Token": token})
                self.assertEqual(valid.status_code, 200, valid.json)
                self.assertEqual(valid.get_json()["count"], 2)
                lookup.assert_called_once_with("US", "iphone-18-pro", experimental=False)
            with patch("setup_wizard.fetch_catalog") as lookup:
                bad = client.post("/api/catalog/model", json={"model_id": "bad", "market": "US"},
                                  headers={"X-Setup-Token": token})
                self.assertEqual(bad.status_code, 422)
                lookup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
