"""Offline model-centric dashboard tests; no Apple or Discord requests."""
import unittest
from unittest.mock import patch

import app as watcher
from dashboard_groups import build_model_groups


PRODUCTS = {
    "silver_us": {
        "watch_model": "iphone-18-pro", "market": "US",
        "name": "iPhone 18 Pro 512 GB Silver",
        "storage": "512 GB", "color": "Silver",
        "part": "ABC01LL/A", "price": None, "currency": "USD",
    },
    "black_us": {
        "watch_model": "iphone-18-pro", "market": "US",
        "name": "iPhone 18 Pro 1 TB Black",
        "storage": "1 TB", "color": "Black",
        "part": "ABC02LL/A", "price": 1500, "currency": "USD",
    },
    "silver_ca": {
        "watch_model": "iphone-18-pro", "market": "CA",
        "name": "iPhone 18 Pro 512 GB Silver",
        "storage": "512 GB", "color": "Silver",
        "part": "ABC03VC/A", "price": None, "currency": "CAD",
    },
    "manual_us": {
        "market": "US", "name": "Manual Mac mini",
        "part": "MAN01LL/A", "price": 600, "currency": "USD",
    },
}


def row(pid, store="R102", status="available", market=None):
    p = PRODUCTS[pid]
    return {
        "product_id": pid,
        "market": market or p["market"],
        "storeNumber": store,
        "storeName": "Christiana Mall" if store == "R102" else "Eaton Centre",
        "city": "Newark" if store == "R102" else "Toronto",
        "state": "DE" if store == "R102" else "ON",
        "status": status,
        "price": p["price"],
        "currency": p["currency"],
        "quote": "Sample pickup status",
    }


class GroupedDashboardTests(unittest.TestCase):
    def test_one_model_card_per_country_including_manual_products(self):
        groups = build_model_groups(
            PRODUCTS,
            [row("silver_us"), row("black_us", status="unavailable"),
             row("silver_ca", store="R121")],
            scan_status="available", checked_at="2026-10-28T01:00:00+00:00",
        )
        self.assertEqual(len(groups), 3)
        self.assertEqual([g["title"] for g in groups],
                         ["iPhone 18 Pro", "iPhone 18 Pro", "Manual Mac mini"])
        self.assertEqual(groups[0]["variant_count"], 2)
        self.assertEqual(groups[0]["colors"], ["Black", "Silver"])
        self.assertEqual(groups[0]["storages"], ["1 TB", "512 GB"])
        self.assertEqual(groups[0]["available_stores"], 1)
        self.assertEqual(groups[0]["stores"][0]["available"], 1)
        self.assertEqual(groups[0]["stores"][0]["unavailable"], 1)
        self.assertEqual(groups[0]["status"], "available")
        self.assertEqual(groups[1]["market"], "CA")
        self.assertEqual(groups[1]["stores"][0]["id"], "R121")
        self.assertEqual(groups[2]["status"], "unknown")

    def test_missing_variant_in_returned_store_is_unknown_not_sold_out(self):
        groups = build_model_groups(
            PRODUCTS, [row("black_us", status="unavailable")],
            scan_status="unavailable", checked_at="checked",
        )
        us = groups[0]
        self.assertEqual(us["status"], "partial")
        store = us["stores"][0]
        self.assertEqual(store["unknown"], 1)
        self.assertEqual(store["unavailable"], 1)
        self.assertEqual(store["status"], "unknown")
        missing = next(v for v in store["variants"] if v["product_id"] == "silver_us")
        self.assertEqual(missing["status"], "unknown")
        self.assertIn("Not returned", missing["quote"])

    def test_failed_scan_does_not_label_stale_available_stock_as_current(self):
        groups = build_model_groups(
            PRODUCTS, [row("silver_us")], scan_status="unknown", checked_at="checked",
        )
        self.assertEqual(groups[0]["stores"], [])
        self.assertEqual(groups[0]["status"], "unknown")
        self.assertFalse(groups[0]["reliable"])
        self.assertIn("No current", groups[0]["status_label"])

    def test_first_run_has_no_confirmed_stock_even_if_rows_passed(self):
        groups = build_model_groups(
            PRODUCTS, [row("silver_us")], scan_status="starting", checked_at=None,
        )
        self.assertEqual(groups[0]["stores"], [])
        self.assertEqual(groups[0]["status"], "unknown")

    def test_partial_cycle_keeps_stock_signal_but_marks_coverage_partial(self):
        groups = build_model_groups(
            PRODUCTS, [row("silver_us"), row("black_us", status="unavailable")],
            scan_status="partial", checked_at="checked",
        )
        self.assertEqual(groups[0]["status"], "partial")
        self.assertEqual(groups[0]["available_stores"], 1)
        self.assertEqual(groups[0]["stores"][0]["status"], "available")
        self.assertIn("coverage partial", groups[0]["status_label"])

    def test_only_checked_stores_could_be_unavailable(self):
        groups = build_model_groups(
            PRODUCTS, [row("silver_us", status="unavailable"), row("black_us", status="unavailable")],
            scan_status="unavailable", checked_at="checked",
        )
        self.assertEqual(groups[0]["status"], "unavailable")
        self.assertIn("checked stores", groups[0]["status_label"])
        self.assertEqual(groups[0]["stores"][0]["unknown"], 0)

    def test_dashboard_html_renders_groups_and_does_not_show_unverified_stock(self):
        snapshot = {
            "status": "unknown", "checked_at": "checked",
            "items": [row("silver_us")], "error": "Apple unavailable",
            "consecutive_errors": 1,
        }
        with patch.object(watcher, "PRODUCTS", PRODUCTS), patch.object(watcher, "latest", snapshot):
            response = watcher.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Show configured model variants (2)", html)
        self.assertIn("No current verified availability", html)
        self.assertIn("UNKNOWN — not a stock-out", html)
        self.assertNotIn("1 available variant", html)
        self.assertIn("Apple unavailable", html)


if __name__ == "__main__":
    unittest.main()
