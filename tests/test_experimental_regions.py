"""Offline tests for opt-in FR/GB regional adapters and pricing."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher
from regions import REGIONS, normalize_location, region_for
from monitoring_areas import validate_monitoring_areas
from setup_wizard import InvalidConfig, validate_config, create_wizard_app


PRODUCTS = {
    "fr_phone": {"market": "FR", "name": "French phone", "part": "MG6J4F/A", "price": 1299, "currency": "EUR"},
    "gb_phone": {"market": "GB", "name": "British phone", "part": "MG6J4QN/A", "price": 1199, "currency": "GBP"},
}


class RegionalPreviewTests(unittest.TestCase):
    def test_fr_gb_are_explicit_and_experimental(self):
        self.assertEqual(REGIONS["FR"].currency, "EUR")
        self.assertEqual(REGIONS["GB"].currency, "GBP")
        self.assertEqual(REGIONS["FR"].pickup_url, "https://www.apple.com/fr/shop/retail/pickup-message")
        self.assertEqual(REGIONS["GB"].pickup_url, "https://www.apple.com/uk/shop/retail/pickup-message")
        with self.assertRaisesRegex(ValueError, "experimental"):
            region_for("FR")
        with self.assertRaisesRegex(ValueError, "experimental"):
            region_for("GB")
        self.assertEqual(region_for("FR", True).code, "FR")

    def test_postcodes_and_city_names(self):
        self.assertEqual(normalize_location("FR", "75001"), "75001")
        self.assertEqual(normalize_location("FR", "Paris"), "Paris")
        self.assertEqual(normalize_location("GB", "SW1A 1AA"), "SW1A 1AA")
        self.assertEqual(normalize_location("GB", "London"), "London")
        with self.assertRaisesRegex(ValueError, "France"):
            normalize_location("FR", "123")
        with self.assertRaisesRegex(ValueError, "UK"):
            normalize_location("GB", "!bad")

    def test_regions_require_opt_in(self):
        areas = [
            {"id": "paris", "market": "FR", "location": "75001", "store_ids": []},
            {"id": "london", "market": "GB", "location": "SW1A 1AA", "store_ids": []},
        ]
        with self.assertRaisesRegex(ValueError, "experimental"):
            validate_monitoring_areas(areas, PRODUCTS)
        self.assertEqual(validate_monitoring_areas(areas, PRODUCTS, enable_experimental=True), areas)

    def test_wizard_disables_europe_without_explicit_flag(self):
        cfg = {
            "products": PRODUCTS,
            "monitoring_areas": [
                {"id": "paris", "market": "FR", "location": "75001", "store_ids": []},
                {"id": "london", "market": "GB", "location": "London", "store_ids": []},
            ],
            "search_zips": {},
            "allowed_states": [],
            "ca_location": "",
            "ca_target_store": "",
            "ca_tax_rate": 0.13,
        }
        with self.assertRaisesRegex(InvalidConfig, "experimental"):
            validate_config(cfg)
        cfg["enable_experimental_regions"] = True
        validated = validate_config(cfg)
        self.assertEqual(validated["products"]["gb_phone"]["currency"], "GBP")
        self.assertEqual(len(validated["monitoring_areas"]), 2)

    def test_wrong_currency_is_rejected(self):
        cfg = {
            "enable_experimental_regions": True,
            "products": {**PRODUCTS, "mismatch": dict(PRODUCTS["fr_phone"], currency="GBP")},
            "monitoring_areas": [{"id": "paris", "market": "FR", "location": "75001", "store_ids": []}],
        }
        with self.assertRaises(InvalidConfig):
            validate_config(cfg)

    def test_eu_price_treated_as_vat_inclusive_without_invented_tax(self):
        with patch.object(watcher, "get_eur_rate", side_effect=lambda currency: ((1.0 if currency == "EUR" else 1.16), None)):
            french = watcher.money_info(PRODUCTS["fr_phone"], {})
            british = watcher.money_info(PRODUCTS["gb_phone"], {})
        self.assertTrue(french["tax_included"])
        self.assertIsNone(french["tax_amount"])
        self.assertEqual(french["total"], 1299)
        self.assertEqual(british["total_eur"], round(1199 * 1.16, 2))
        self.assertEqual(watcher.money_symbol("EUR"), "€")
        self.assertEqual(watcher.money_symbol("GBP"), "£")

    def test_region_specific_urls_and_products_used_for_multi_area_polling(self):
        areas = [
            {"id": "paris", "market": "FR", "location": "75001", "store_ids": ["R438"]},
            {"id": "london", "market": "GB", "location": "SW1A 1AA", "store_ids": ["R363"]},
        ]
        calls = []
        def fake_fetch(url, location, ids):
            calls.append((url, location, tuple(ids)))
            return [{"storeNumber": "R438" if location == "75001" else "R363", "storeName": "Example", "city": "Example", "state": ""}]
        def fake_parse(raw, pid):
            return {
                "key": f"{pid}:{raw['storeNumber']}", "product_id": pid,
                "storeNumber": raw["storeNumber"], "storeName": raw["storeName"],
                "market": PRODUCTS[pid]["market"], "status": "unavailable", "total": PRODUCTS[pid]["price"],
            }
        with (
            patch.object(watcher, "MONITORING_AREAS", areas),
            patch.object(watcher, "MARKET_PRODUCT_IDS", {"FR":["fr_phone"], "GB":["gb_phone"]}),
            patch.object(watcher, "PRODUCTS", PRODUCTS),
            patch.object(watcher, "fetch_market", side_effect=fake_fetch),
            patch.object(watcher, "parse_item", side_effect=fake_parse),
            patch.object(watcher.time, "sleep"),
        ):
            items, errors = watcher.fetch_all()
        self.assertEqual(errors, [])
        self.assertEqual(len(items), 2)
        self.assertEqual(calls, [
            (REGIONS["FR"].pickup_url, "75001", ("fr_phone",)),
            (REGIONS["GB"].pickup_url, "SW1A 1AA", ("gb_phone",)),
        ])

    def test_dashboard_supports_prices_and_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Path(directory) / "config.json"
            sample = Path(directory) / "config.example.json"
            sample.write_text('{"products":{"us_phone":{"market":"US","name":"Phone","part":"TESTLL/A","price":1,"currency":"USD"}},"search_zips":{"NY":"10001"},"allowed_states":[]}', encoding="utf-8")
            wizard = create_wizard_app(f, sample)
            response = wizard.test_client().get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"France (experimental)", response.data)
            self.assertIn(b"Enable France/UK preview", response.data)
        self.assertEqual(watcher.app.test_client().get("/").status_code, 200)


if __name__ == "__main__":
    unittest.main()
