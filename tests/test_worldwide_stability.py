"""Confirmed worldwide failure modes; every request/notification is mocked."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import app as watcher
from dashboard_groups import build_model_groups
from monitoring_areas import validate_monitoring_areas
from regions import REGIONS, normalize_location
from setup_wizard import validate_config
from store_directory import stores_for_country


def product(market="FR"):
    return {"name": "Example regional iPhone", "market": market, "currency": REGIONS[market].currency,
            "part": "EXAMPLE-" + market + "/A", "price": None}


class WorldwideStabilityTests(unittest.TestCase):
    def test_brazil_missing_store_list_and_invalid_schemas_stay_unknown(self):
        malformed = [[], None, {"body": []}, {"body": {}}, {"body": {"stores": {}}},
                     {"body": {"stores": [None]}}, {"body": {"stores": [{}]}},
                     {"body": {"stores": [{"storeNumber": "R_NEW", "partsAvailability": []}]}},
                     {"body": {"stores": [{"storeNumber": "R_NEW", "partsAvailability": {"EXAMPLE/A": "bad"}}]}}]
        for body in malformed:
            with self.subTest(body=body), patch.object(watcher.requests, "get", return_value=Mock(status_code=200, json=lambda: body)):
                with self.assertRaisesRegex(RuntimeError, "availability unknown") as error:
                    watcher.fetch_market(REGIONS["BR"].pickup_url, "PUBLIC_TEST", [])
                self.assertNotIn("PUBLIC_TEST", str(error.exception))

    def test_valid_empty_store_list_remains_empty_not_unavailable(self):
        with patch.object(watcher.requests, "get", return_value=Mock(status_code=200, json=lambda: {"body": {"stores": []}})):
            self.assertEqual(watcher.fetch_market(REGIONS["BR"].pickup_url, "PUBLIC_TEST", []), [])

    def test_known_store_cannot_be_configured_or_reported_under_foreign_country(self):
        products = {"fr": product()}
        area = {"id": "fr", "market": "FR", "location": "75001", "store_ids": ["R102"]}
        with self.assertRaisesRegex(ValueError, "another country"):
            validate_monitoring_areas([area], products, enable_experimental=True)
        area["store_ids"] = []
        with (patch.object(watcher, "PRODUCTS", products), patch.object(watcher, "MARKET_PRODUCT_IDS", {"FR": ["fr"]}),
              patch.object(watcher, "MONITORING_AREAS", [area]), patch.object(watcher, "fetch_market", return_value=[{
                  "storeNumber": "R102", "partsAvailability": {products["fr"]["part"]: {"pickupDisplay": "available"}}}])):
            with self.assertRaisesRegex(RuntimeError, "another country"):
                watcher.fetch_all()

    def test_new_unknown_store_id_is_not_falsely_claimed_foreign(self):
        area = {"id": "fr", "market": "FR", "location": "75001", "store_ids": ["R_FUTURE"]}
        self.assertEqual(validate_monitoring_areas([area], {"fr": product()}, True), [area])

    def test_legacy_duplicate_variants_remain_loadable_and_alerts_are_deduplicated(self):
        cfg = {"products": {"a": product(), "b": {**product(), "part": product()["part"].lower()}},
               "enable_experimental_regions": True, "monitoring_areas": [
                   {"id": "fr", "market": "FR", "location": "75001", "store_ids": []}]}
        self.assertEqual(len(validate_config(cfg)["products"]), 2)
        item = {**product(), "storeNumber": "R_EXAMPLE", "product_id": "a"}
        with (patch.object(watcher, "normal_available_embed") as embed, patch.object(watcher, "safe_discord"),
              patch.object(watcher, "ALERT_STORE_IDS", None), patch.object(watcher, "ALERT_PRODUCT_IDS", None)):
            watcher.send_stock_changes([item, {**item, "product_id": "b"}], [])
            self.assertEqual(len(embed.call_args.args[0]), 1)

    def test_full_international_postcodes_and_unicode_are_preserved(self):
        for market, value in [("CN", "200021"), ("CN", "上海"), ("NL", "1017 PS"), ("BR", "22640-102"),
                              ("JP", "東京都"), ("KR", "서울"), ("TH", "กรุงเทพฯ"), ("IN", "मुंबई")]:
            self.assertEqual(normalize_location(market, value), value)
        for value in ("Paris\n", "Paris\x00", "<script>"):
            with self.assertRaises(ValueError):
                normalize_location("DE", value)

    def test_fr_de_ineligible_never_emits_a_stockout_or_repeat_available_alert(self):
        for market in ("FR", "DE"):
            p = product(market)
            store_id = stores_for_country(market)["stores"][0]["id"]
            raw = {"storeNumber": store_id, "storeName": "Example", "partsAvailability": {
                p["part"]: {"pickupDisplay": "ineligible", "storePickEligible": True,
                            "pickupSearchQuote": "Not available for pickup at this store"}}}
            with patch.object(watcher, "PRODUCTS", {"phone": p}):
                unknown = watcher.parse_item(raw, "phone")
            self.assertEqual(unknown["status"], "unknown")
            with tempfile.TemporaryDirectory() as temporary, patch.object(watcher, "STATE_FILE", Path(temporary) / "state.json"), \
                    patch.object(watcher, "HISTORY_FILE", Path(temporary) / "history.json"), patch.object(watcher, "send_stock_changes") as send:
                watcher.save_state({"available_keys": [unknown["key"]]})
                with patch.object(watcher, "fetch_all", return_value=([unknown], [])):
                    watcher.poll_once()
                self.assertEqual(send.call_args.args, ([], []))
                self.assertEqual(watcher.load_state()["available_keys"], [unknown["key"]])
                with patch.object(watcher, "fetch_all", return_value=([{**unknown, "status": "available"}], [])):
                    watcher.poll_once()
                self.assertEqual(send.call_args.args, ([], []))

    def test_snapshot_expires_without_relabeling_saved_alert_state(self):
        current = datetime(2026, 10, 31, 20, tzinfo=timezone.utc)
        old = (current - timedelta(hours=2)).isoformat()
        snapshot = {"status": "available", "checked_at": old, "items": [{"status": "available"}]}
        with patch.object(watcher, "INTERVAL", 120):
            shown = watcher.snapshot_for_display(snapshot, current)
        self.assertTrue(shown["stale"])
        self.assertEqual(shown["status"], "unknown")
        self.assertEqual(shown["items"], [])
        self.assertEqual(snapshot["items"][0]["status"], "available")
        for stamp in ("undated", "2026-10-31T20:00:00", (current + timedelta(hours=1)).isoformat()):
            self.assertTrue(watcher.snapshot_for_display({**snapshot, "checked_at": stamp}, current)["stale"])
        self.assertFalse(watcher.snapshot_for_display({**snapshot, "checked_at": current.isoformat()}, current)["stale"])

    def test_failed_attempt_keeps_previous_observation_date_but_no_current_api_stock(self):
        old = "2026-10-31T10:00:00+00:00"
        snapshot = {"status": "available", "checked_at": old, "observed_at": old, "items": [{"status": "available"}]}
        with (patch.object(watcher, "latest", snapshot), patch.object(watcher, "now", return_value="2026-10-31T11:00:00+00:00"),
              patch.object(watcher, "fetch_all", side_effect=RuntimeError("Apple HTTP 500")),
              patch.object(watcher, "load_state", return_value={}), patch.object(watcher, "save_state"), patch.object(watcher, "safe_discord")):
            watcher.poll_once()
            result = watcher.app.test_client().get("/api/status").get_json()
            html = watcher.app.test_client().get("/").get_data(as_text=True)
            self.assertEqual(result["observed_at"], old)
            self.assertEqual(result["checked_at"], "2026-10-31T11:00:00+00:00")
            self.assertEqual(result["items"], [])
            self.assertIn("Données anciennes", html)

    def test_dashboard_rejects_wrong_country_currency_or_variant_and_shows_missing_target(self):
        p = product()
        row = {"product_id": "fr", "market": "FR", "currency": "EUR", "part": p["part"],
               "storeNumber": "R_TARGET", "status": "available"}
        area = {"market": "FR", "store_ids": ["R_TARGET", "R_MISSING"]}
        group = build_model_groups({"fr": p}, [row], "available", "checked", [area])[0]
        self.assertEqual(group["status"], "partial")
        self.assertEqual(group["checked_stores"], 1)
        missing = next(s for s in group["stores"] if s["id"] == "R_MISSING")
        self.assertEqual(missing["status"], "unknown")
        self.assertFalse(missing["observed"])
        for changes in ({"market": "CA"}, {"currency": "CAD"}, {"part": "OTHER/A"}):
            group = build_model_groups({"fr": p}, [{**row, **changes}], "available", "checked", [area])[0]
            self.assertEqual(group["available_stores"], 0)

    def test_notifications_identify_country_store_and_regional_sku(self):
        item = {**product(), "productName": "Example variant", "storeNumber": "R_EXAMPLE", "storeName": "Example",
                "city": "Paris", "state": "", "total": None, "tax_rate": None}
        for builder in (watcher.normal_available_embed, watcher.unavailable_embed):
            text = builder([item])["description"]
            for expected in ("FR", "R_EXAMPLE", item["part"]):
                self.assertIn(expected, text)

