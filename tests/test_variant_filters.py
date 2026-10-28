"""Tests for user-selected color, capacity and carrier filters.

Carrier metadata is never inferred from a missing Apple attribute, and a SKU
repeated with conflicting carrier metadata must become 'unknown'.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from catalog_discovery import parse_catalog_html
from model_watch import model_catalog_result, validate_request_budget, ModelSelectionError
from setup_wizard import create_wizard_app, validate_config


def apple_html(products):
    return (
        b"<script>window.PRODUCT_SELECTION_BOOTSTRAP = "
        + json.dumps({"productSelectionData": {"products": products}}).encode("utf-8")
        + b";</script>"
    )


def row(part, color, storage, carrier=None, family="iphone18pro"):
    raw = {
        "partNumber": part,
        "familyType": family,
        "dimensionColor": color,
        "dimensionCapacity": storage,
    }
    if carrier is not None:
        raw["dimensionCarrier"] = carrier
    return raw


class VariantFilterTests(unittest.TestCase):
    def test_exposes_explicit_color_storage_and_unlocked_carrier(self):
        items = parse_catalog_html(
            apple_html([
                row("MG1LL/A", "silver", "512gb", "sim-free"),
                row("MG2LL/A", "black", "1tb", "Verizon"),
                row("MG3LL/A", "silver", "256gb"),
            ]),
            "US",
            "iphone-18-pro",
        )
        by_sku = {p["part"]: p for p in items}
        self.assertEqual(by_sku["MG1LL/A"]["color"], "Silver")
        self.assertEqual(by_sku["MG1LL/A"]["storage"], "512 GB")
        self.assertEqual(by_sku["MG1LL/A"]["carrier"], "unlocked")
        self.assertEqual(by_sku["MG2LL/A"]["storage"], "1 TB")
        self.assertEqual(by_sku["MG2LL/A"]["carrier"], "Verizon")
        self.assertIsNone(by_sku["MG3LL/A"]["carrier"])
        preview = model_catalog_result("iphone-18-pro", "US", items)
        self.assertEqual(preview["options"]["colors"], ["Black", "Silver"])
        self.assertEqual(preview["options"]["storages"], ["1 TB", "256 GB", "512 GB"])
        self.assertEqual(preview["options"]["carriers"], ["Verizon", "unlocked"])
        self.assertEqual(preview["options"]["carrier_unknown"], 1)

    def test_unlabeled_iphone_is_not_assumed_unlocked(self):
        items = parse_catalog_html(
            apple_html([row("MG1LL/A", "silver", "512gb")]),
            "US",
            "iphone-18-pro",
        )
        preview = model_catalog_result("iphone-18-pro", "US", items)
        self.assertEqual(preview["options"]["carriers"], [])
        self.assertEqual(preview["options"]["carrier_unknown"], 1)

    def test_duplicate_sku_with_conflicting_carriers_is_unknown(self):
        items = parse_catalog_html(
            apple_html([
                row("MG1LL/A", "silver", "512gb", "AT&T"),
                row("MG1LL/A", "silver", "512gb", "Verizon"),
                row("MG1LL/A", "silver", "512gb", "AT&T"),
            ]),
            "US",
            "iphone-18-pro",
        )
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]["carrier"])
        self.assertEqual(
            model_catalog_result("iphone-18-pro", "US", items)["options"]["carriers"],
            [],
        )

    def test_large_catalog_can_be_previewed_but_not_monitored_unfiltered(self):
        items = [
            {
                "market": "US", "family": "iphone-18-pro", "family_type": "iphone18pro",
                "part": f"MG{i:03d}LL/A", "name": f"iPhone Pro {i}",
                "currency": "USD", "price": None,
                "color": "Silver" if i % 2 == 0 else "Black",
                "storage": "512 GB",
                "carrier": None,
            }
            for i in range(70)
        ]
        preview = model_catalog_result("iphone-18-pro", "US", items)
        self.assertEqual(preview["count"], 70)
        selected = {
            str(i): {**p, "watch_model": "iphone-18-pro"}
            for i, p in enumerate(preview["products"])
            if p["color"] == "Silver"
        }
        self.assertEqual(len(selected), 35)
        self.assertEqual(
            validate_request_budget(
                selected,
                [{"market": "US", "location": "19702", "store_ids": [], "id": "area"}],
            ),
            3,
        )
        all_products = {str(i): p for i, p in enumerate(preview["products"])}
        with self.assertRaisesRegex(ModelSelectionError, "Too many iphone-18-pro variants"):
            validate_request_budget(
                all_products,
                [{"market": "US", "location": "19702", "store_ids": [], "id": "area"}],
            )

    def test_wizard_config_persists_variant_metadata(self):
        products = {
            "a": {
                "market": "CA",
                "part": "MG1VC/A",
                "name": "iPhone 18 Pro Silver 512 GB",
                "price": None,
                "currency": "CAD",
                "watch_model": "iphone-18-pro",
                "color": "Silver",
                "storage": "512 GB",
                "carrier": "unlocked",
            }
        }
        cfg = {
            "products": products,
            "monitoring_areas": [{
                "id": "toronto", "market": "CA", "location": "Toronto", "store_ids": [],
            }],
            "search_zips": {}, "allowed_states": [], "ca_tax_rate": 0.13,
        }
        result = validate_config(cfg)
        self.assertEqual(result["products"]["a"]["color"], "Silver")
        self.assertEqual(result["products"]["a"]["storage"], "512 GB")
        self.assertEqual(result["products"]["a"]["carrier"], "unlocked")

    def test_wizard_has_optional_variant_filters_and_model_preview_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / "config.example.json"
            sample.write_text(json.dumps({
                "products": {
                    "a": {"market": "US", "part": "MG1LL/A", "name": "Example",
                          "currency": "USD", "price": None},
                },
                "search_zips": {"NY": "10001"},
                "allowed_states": [],
            }), encoding="utf-8")
            app = create_wizard_app(root / "config.json", sample)
            client = app.test_client()
            html = client.get("/").data
            for element_id in (
                b'id="modelColor"', b'id="modelStorage"', b'id="modelCarrier"',
                b'id="applyModelFilters"', b'id="modelOptions"',
            ):
                self.assertIn(element_id, html)
            token = re.search(rb'const TOKEN = "([^"]+)"', html).group(1).decode()
            fixtures = parse_catalog_html(
                apple_html([row("MG1LL/A", "silver", "512gb")]),
                "US",
                "iphone-18-pro",
            )
            with patch("setup_wizard.fetch_catalog", return_value={"items": fixtures, "cached": True}):
                result = client.post(
                    "/api/catalog/model",
                    json={"model_id": "iphone-18-pro", "market": "US"},
                    headers={"X-Setup-Token": token},
                )
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["options"]["storages"], ["512 GB"])
            self.assertEqual(result.json["options"]["carrier_unknown"], 1)


if __name__ == "__main__":
    unittest.main()
