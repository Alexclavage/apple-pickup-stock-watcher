"""Offline tests for targeted Discord alerts and Apple rate limiting."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app as watcher


class AlertAndRateLimitTests(unittest.TestCase):
    def test_alert_filters_apply_to_notifications(self):
        priority = {"storeNumber": "R102", "product_id": "us_pro_512", "market": "US"}
        other = {"storeNumber": "R121", "product_id": "ca_pro_512", "market": "CA"}
        with (
            patch.object(watcher, "ALERT_STORE_IDS", {"R102"}),
            patch.object(watcher, "ALERT_PRODUCT_IDS", {"us_pro_512"}),
            patch.object(watcher, "priority_store_embed", return_value={"title": "priority"}),
            patch.object(watcher, "safe_discord") as send,
        ):
            self.assertTrue(watcher.is_alert_target(priority))
            self.assertFalse(watcher.is_alert_target(other))
            watcher.send_stock_changes([priority, other], [])
            send.assert_called_once_with(embeds=[{"title": "priority"}])

    def test_omitted_filters_allow_all_stores(self):
        item = {"storeNumber": "R999", "product_id": "anything"}
        with patch.object(watcher, "ALERT_STORE_IDS", None), patch.object(watcher, "ALERT_PRODUCT_IDS", None):
            self.assertTrue(watcher.is_alert_target(item))

    def test_empty_alert_store_list_mutes_all(self):
        item = {"storeNumber": "R102", "product_id": "us_pro_512"}
        with patch.object(watcher, "ALERT_STORE_IDS", set()):
            self.assertFalse(watcher.is_alert_target(item))

    def test_large_stock_alerts_fit_discord_embed_description_limits(self):
        # A many-SKU/many-store scan previously generated >4096-character
        # descriptions and Discord could reject the whole message with 400.
        item = {
            "market": "US",
            "currency": "USD",
            "productName": "iPhone " + ("long model name " * 35),
            "part": "ABC123LL/A",
            "storeName": "Apple Store " + ("long location " * 40),
            "storeNumber": "R102",
            "city": "Newark",
            "state": "DE",
            "price": None,
            "total": None,
            "quote": "Available Today",
        }
        many = [dict(item, storeNumber=f"R{index:03d}") for index in range(120)]
        for builder in (watcher.normal_available_embed, watcher.unavailable_embed):
            with self.subTest(builder=builder.__name__):
                embed = builder(many)
                self.assertLess(len(embed["description"]), 3900)
                self.assertIn("autre(s)", embed["description"])
                self.assertEqual(embed["title"].split()[1], "120")

    def test_http_429_is_classified_as_rate_limit(self):
        with patch.object(watcher.requests, "get", return_value=Mock(status_code=429)):
            with self.assertRaisesRegex(RuntimeError, "APPLE_429"):
                watcher.fetch_market(watcher.US_URL, "19702", ["us_pro_512"])

    def test_partial_rate_limit_causes_cooldown(self):
        sample = {"key": "sample:R001", "status": "unavailable"}
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(watcher, "STATE_FILE", Path(directory) / "state.json"),
                patch.object(watcher, "HISTORY_FILE", Path(directory) / "history.json"),
                patch.object(watcher, "send_stock_changes"),
                patch.object(watcher, "fetch_all", return_value=([sample], ["DELAWARE: Apple 429"])),
            ):
                delay = watcher.poll_once()
                self.assertEqual(delay, max(watcher.INTERVAL, 900))
                self.assertEqual(watcher.latest["status"], "partial")


if __name__ == "__main__":
    unittest.main()
