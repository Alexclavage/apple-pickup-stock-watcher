"""Guard against false stock-outs, underbudgeted Apple requests and config leaks."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher
from model_watch import expected_requests, validate_request_budget
from setup_wizard import create_wizard_app


def area(location="19702"):
    return {"id": "de", "market": "US", "location": location, "store_ids": []}


def product(i, sku=None):
    return {
        "market": "US", "name": f"Phone {i}", "part": sku or f"SKU{i:03d}LL/A",
        "price": None, "currency": "USD",
    }


class PollBatchAndConfigPrivacyTests(unittest.TestCase):
    def test_multiple_product_ids_with_same_sku_still_consume_request_slots(self):
        # The worker sends each configured product ID in separate parts.N
        # params: do not deduplicate when enforcing its request cap.
        same_sku = {f"p{i}": product(i, "DUP01LL/A") for i in range(25)}
        self.assertEqual(expected_requests(same_sku, [area()]), 3)
        self.assertEqual(
            validate_request_budget(same_sku, [area(), {"id": "ny", "market": "US", "location": "10001"}]),
            6,
        )

    def test_failed_last_sku_batch_is_partial_not_unavailable(self):
        products = {f"p{i}": product(i) for i in range(13)}
        calls = []
        def response(_url, _location, ids):
            calls.append(len(ids))
            if len(calls) == 2:
                return []  # The second batch returned no matching stores.
            return [{
                "storeNumber": "R102", "storeName": "Christiana Mall",
                "city": "Newark", "state": "DE",
            }]
        def parse(_store, pid):
            return {
                "key": f"{pid}:R102", "product_id": pid, "market": "US",
                "storeNumber": "R102", "storeName": "Christiana Mall",
                "city": "Newark", "state": "DE", "status": "unavailable",
                "price": None, "total": None,
            }
        with (
            patch.object(watcher, "PRODUCTS", products),
            patch.object(watcher, "US_PRODUCT_IDS", list(products)),
            patch.object(watcher, "CA_PRODUCT_IDS", []),
            patch.object(watcher, "MONITORING_AREAS", [area()]),
            patch.object(watcher, "ALLOWED_STATES", {"DE"}),
            patch.object(watcher, "fetch_market", side_effect=response),
            patch.object(watcher, "parse_item", side_effect=parse),
            patch.object(watcher.time, "sleep"),
            patch.object(watcher, "send_stock_changes"),
            tempfile.TemporaryDirectory() as tmp,
            patch.object(watcher, "STATE_FILE", Path(tmp) / "state.json"),
            patch.object(watcher, "HISTORY_FILE", Path(tmp) / "history.json"),
        ):
            watcher.poll_once()
            self.assertEqual(calls, [12, 1])
            self.assertEqual(watcher.latest["status"], "partial")
            self.assertIn("batch 2", watcher.latest["error"])
            self.assertEqual(len(watcher.latest["items"]), 12)

    def test_store_filter_is_verified_for_every_batch(self):
        products = {f"p{i}": product(i) for i in range(13)}
        calls = []
        def response(_url, _location, ids):
            calls.append(len(ids))
            number = "R102" if len(calls) == 1 else "R777"
            return [{"storeNumber": number, "storeName": number, "state": "DE"}]
        with (
            patch.object(watcher, "PRODUCTS", products),
            patch.object(watcher, "US_PRODUCT_IDS", list(products)),
            patch.object(watcher, "CA_PRODUCT_IDS", []),
            patch.object(watcher, "MONITORING_AREAS", [{
                "id": "de", "market": "US", "location": "19702",
                "store_ids": ["R102"],
            }]),
            patch.object(watcher, "ALLOWED_STATES", {"DE"}),
            patch.object(watcher, "fetch_market", side_effect=response),
            patch.object(watcher, "parse_item", side_effect=lambda raw,pid: {
                "key": f"{pid}:R102", "product_id": pid,
                "market": "US", "storeNumber": "R102", "storeName": "R102",
                "status": "unavailable", "total": None,
            }),
            patch.object(watcher.time, "sleep"),
        ):
            items, errors = watcher.fetch_all()
        self.assertEqual(len(items), 12)
        self.assertTrue(any("batch 2" in e and "not verified" in e for e in errors))

    def test_unknown_config_fields_not_returned_but_preserved_when_saving(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample_path = root / "config.example.json"
            config_path = root / "config.json"
            cfg = {
                "products": {"us": product(1)},
                "monitoring_areas": [area()],
                "search_zips": {},
                "allowed_states": [],
                "ca_location": "",
                "ca_target_store": "",
                "ca_tax_rate": 0.13,
                "legacy_private_token": "SECRET_NOT_FOR_BROWSER",
                "custom_preference": {"mode": "legacy"},
            }
            sample_path.write_text(json.dumps(cfg), encoding="utf-8")
            config_path.write_text(json.dumps(cfg), encoding="utf-8")
            app = create_wizard_app(config_path, sample_path)
            client = app.test_client()
            index = client.get("/").get_data(as_text=True)
            token_match = re.search(r'const TOKEN = "([^"]+)"', index)
            self.assertIsNotNone(token_match)
            token = token_match.group(1)
            response = client.get("/api/config")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("SECRET_NOT_FOR_BROWSER", response.get_data(as_text=True))
            self.assertNotIn("legacy_private_token", response.get_data(as_text=True))
            self.assertNotIn("custom_preference", response.get_data(as_text=True))
            clean = response.get_json()["config"]
            clean["ca_tax_rate"] = 0.14
            write = client.post("/api/config", json=clean, headers={"X-Setup-Token": token})
            self.assertEqual(write.status_code, 200, write.get_json())
            self.assertNotIn("SECRET_NOT_FOR_BROWSER", write.get_data(as_text=True))
            persisted = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["ca_tax_rate"], 0.14)
            self.assertEqual(persisted["legacy_private_token"], "SECRET_NOT_FOR_BROWSER")
            self.assertEqual(persisted["custom_preference"], {"mode": "legacy"})
            backup = json.loads((root / "config.json.bak").read_text(encoding="utf-8"))
            self.assertEqual(backup["ca_tax_rate"], 0.13)

    def test_alert_for_all_removes_saved_filters_but_keeps_private_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "config.example.json"
            target = root / "config.json"
            cfg = {
                "products": {"us": product(1)},
                "monitoring_areas": [area()],
                "search_zips": {},
                "allowed_states": [],
                "alert_store_ids": ["R102"],
                "alert_product_ids": ["us"],
                "secret_extension": "PRESERVE_ME",
            }
            sample.write_text(json.dumps(cfg), encoding="utf-8")
            target.write_text(json.dumps(cfg), encoding="utf-8")
            client = create_wizard_app(target, sample).test_client()
            token = re.search(
                r'const TOKEN = "([^"]+)"', client.get("/").get_data(as_text=True)
            ).group(1)
            clean = client.get("/api/config").get_json()["config"]
            clean.pop("alert_store_ids")
            clean.pop("alert_product_ids")
            result = client.post("/api/config", json=clean, headers={"X-Setup-Token": token})
            self.assertEqual(result.status_code, 200, result.get_json())
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertNotIn("alert_store_ids", saved)
            self.assertNotIn("alert_product_ids", saved)
            self.assertEqual(saved["secret_extension"], "PRESERVE_ME")

    def test_invalid_existing_config_is_not_overwritten_on_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "config.example.json"
            config = root / "config.json"
            cfg = {
                "products": {"us": product(1)},
                "monitoring_areas": [area()],
                "allowed_states": [],
            }
            sample.write_text(json.dumps(cfg), encoding="utf-8")
            config.write_text("{broken", encoding="utf-8")
            app = create_wizard_app(config, sample)
            client = app.test_client()
            token = re.search(
                r'const TOKEN = "([^"]+)"', client.get("/").get_data(as_text=True)
            ).group(1)
            response = client.post("/api/config", json=cfg, headers={"X-Setup-Token": token})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(config.read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
    unittest.main()
