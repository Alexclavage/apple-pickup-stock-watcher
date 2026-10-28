"""Regression tests for missing-area safety and localhost-only defaults."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher
from dashboard_groups import build_model_groups
from monitoring_areas import uncovered_product_markets
from setup_wizard import WIZARD_HTML


PRODUCTS = {
    "us": {"market": "US", "name": "US iPhone", "part": "US111LL/A", "price": None, "currency": "USD"},
    "ca": {"market": "CA", "name": "CA iPhone", "part": "CA111VC/A", "price": None, "currency": "CAD"},
}


def area(id, market, location):
    return {"id": id, "market": market, "location": location, "store_ids": []}


def item(pid):
    return {
        "key": f"{pid}:R102",
        "product_id": pid,
        "market": PRODUCTS[pid]["market"],
        "productName": PRODUCTS[pid]["name"],
        "storeNumber": "R102",
        "storeName": "Christiana Mall",
        "city": "Newark",
        "state": "DE",
        "part": PRODUCTS[pid]["part"],
        "price": None,
        "currency": PRODUCTS[pid]["currency"],
        "status": "unavailable",
        "total": None,
    }


class CoverageAndSecurityTests(unittest.TestCase):
    def test_uncovered_country_is_detected_without_changing_configuration(self):
        self.assertEqual(
            uncovered_product_markets(PRODUCTS, [area("de", "US", "19702")]),
            ["CA"],
        )
        self.assertEqual(
            uncovered_product_markets(PRODUCTS, [
                area("de", "US", "19702"),
                area("toronto", "CA", "Toronto"),
            ]),
            [],
        )

    def test_us_check_cannot_report_ca_out_of_stock(self):
        areas = [area("de", "US", "19702")]
        with (
            patch.object(watcher, "PRODUCTS", PRODUCTS),
            patch.object(watcher, "US_PRODUCT_IDS", ["us"]),
            patch.object(watcher, "CA_PRODUCT_IDS", ["ca"]),
            patch.object(watcher, "MONITORING_AREAS", areas),
            patch.object(watcher, "ALLOWED_STATES", {"DE"}),
            patch.object(watcher, "fetch_market", return_value=[
                {"storeNumber": "R102", "storeName": "Christiana Mall", "state": "DE"},
            ]),
            patch.object(watcher, "parse_item", side_effect=lambda _raw, pid: item(pid)),
            patch.object(watcher, "send_stock_changes"),
            tempfile.TemporaryDirectory() as tmp,
            patch.object(watcher, "STATE_FILE", Path(tmp) / "state.json"),
            patch.object(watcher, "HISTORY_FILE", Path(tmp) / "history.json"),
        ):
            rows, errors = watcher.fetch_all()
            self.assertEqual(len(rows), 1)
            self.assertTrue(any("CA" in err and "NOT checked" in err for err in errors))
            watcher.poll_once()
            self.assertEqual(watcher.latest["status"], "partial")
            self.assertIn("CA", watcher.latest["error"])
            html = watcher.app.test_client().get("/").get_data(as_text=True)
            self.assertIn("Zones manquantes", html)
            self.assertIn("No monitoring area selected for this country", html)
            self.assertIn("PARTIAL", html)

    def test_empty_location_marks_partial_when_other_area_was_checked(self):
        areas = [area("de", "US", "19702"), area("nyc", "US", "10001")]
        def fetch(_url, location, _ids):
            if location == "19702":
                return [{"storeNumber": "R102", "storeName": "Christiana Mall", "state": "DE"}]
            return []
        with (
            patch.object(watcher, "PRODUCTS", {"us": PRODUCTS["us"]}),
            patch.object(watcher, "US_PRODUCT_IDS", ["us"]),
            patch.object(watcher, "CA_PRODUCT_IDS", []),
            patch.object(watcher, "MONITORING_AREAS", areas),
            patch.object(watcher, "ALLOWED_STATES", {"DE"}),
            patch.object(watcher, "fetch_market", side_effect=fetch),
            patch.object(watcher, "parse_item", side_effect=lambda _raw, pid: item(pid)),
            patch.object(watcher.time, "sleep"),
        ):
            rows, errors = watcher.fetch_all()
        self.assertEqual(len(rows), 1)
        self.assertTrue(any("nyc" in err and "unknown" in err for err in errors))

    def test_uncovered_market_group_is_unknown_even_during_good_us_scan(self):
        groups = build_model_groups(
            PRODUCTS, [item("us")],
            scan_status="partial",
            checked_at="2026-10-28T03:44:00+00:00",
            monitoring_areas=[area("de", "US", "19702")],
        )
        ca = next(group for group in groups if group["market"] == "CA")
        self.assertTrue(ca["area_missing"])
        self.assertEqual(ca["status"], "unknown")
        self.assertEqual(ca["checked_stores"], 0)
        self.assertIn("No monitoring area", ca["status_label"])

    def test_localhost_default_and_explicit_network_opt_in(self):
        self.assertEqual(watcher.dashboard_bind_host({}), "127.0.0.1")
        self.assertEqual(
            watcher.dashboard_bind_host({"WATCHER_HOST": "0.0.0.0"}),
            "0.0.0.0",
        )
        self.assertIn("No area for ", WIZARD_HTML)
        self.assertIn("these products will NOT be checked", WIZARD_HTML)

    def test_checked_timestamp_is_marked_up_for_browser_timezone(self):
        snapshot = {
            "status": "starting", "checked_at": "2026-10-28T03:44:00+00:00",
            "items": [], "error": None, "consecutive_errors": 0,
        }
        with patch.object(watcher, "latest", snapshot):
            html = watcher.app.test_client().get("/").get_data(as_text=True)
        self.assertIn('class="local-datetime"', html)
        self.assertIn('datetime="2026-10-28T03:44:00+00:00"', html)


if __name__ == "__main__":
    unittest.main()
