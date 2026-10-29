"""Offline preflight and Discord opt-out tests; never call Apple/Discord."""
import contextlib
from io import StringIO
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher
import preflight


def product(market, part):
    return {
        "market": market, "name": "Example", "part": part,
        "currency": {"US": "USD", "CA": "CAD"}[market], "price": None,
    }


class OfflinePreflightTests(unittest.TestCase):
    def test_good_configuration_with_us_and_ca_is_ready(self):
        products = {
            "us": product("US", "AAA01LL/A"),
            "ca": product("CA", "BBB01VC/A"),
        }
        areas = [
            {"id": "de", "market": "US", "location": "19702"},
            {"id": "toronto", "market": "CA", "location": "M5B 2H1"},
        ]
        report = preflight.make_report(
            products, areas, True, 2, 300, discord_configured=True,
            discord_disabled=True,
        )
        self.assertTrue(report["ready"])
        self.assertEqual(report["requests_per_cycle"], 2)
        self.assertEqual(report["discord_mode"], "disabled for local testing")
        self.assertEqual(
            [(m["market"], m["areas"]) for m in report["markets"]],
            [("CA", 1), ("US", 1)],
        )
        self.assertEqual(report["issues"], [])

    def test_missing_country_area_and_sample_fallback_are_not_ready(self):
        products = {"us": product("US", "AAA01LL/A"), "ca": product("CA", "BBB01VC/A")}
        areas = [{"market": "US", "id": "de", "location": "19702"}]
        report = preflight.make_report(products, areas, False, 1, 300)
        self.assertFalse(report["ready"])
        self.assertEqual(len(report["issues"]), 2)
        self.assertIn("CA", " ".join(report["issues"]))
        self.assertIn("sample defaults", " ".join(report["issues"]))

    def test_duplicate_sku_warning_does_not_hide_request_cost(self):
        products = {f"p{i}": product("US", "SAME01LL/A") for i in range(13)}
        areas = [{"id": "de", "market": "US", "location": "19702"}]
        report = preflight.make_report(products, areas, True, 2, 300)
        self.assertTrue(report["ready"])
        self.assertEqual(report["markets"][0]["requests_per_cycle"], 2)
        self.assertIn("12 duplicate", " ".join(report["notes"]))

    def test_json_report_redacts_webhook_sku_postal_code_and_custom_secrets(self):
        products = {
            "secret_product": product("US", "PRIVATE_SKU"),
            "ca": product("CA", "ANOTHER_SECRET"),
        }
        areas = [{"id": "private_location", "market": "US", "location": "SECRET POSTAL"}]
        report = preflight.make_report(products, areas, True, 1, 300,
                                       discord_configured=True)
        encoded = json.dumps(report)
        for sensitive in ("PRIVATE_SKU", "ANOTHER_SECRET", "SECRET POSTAL", "private_location"):
            self.assertNotIn(sensitive, encoded)
        self.assertIn("may send real messages", encoded)

    def test_real_command_without_network_or_writing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_config = root / "config.json"
            fake_config.write_text("{}", encoding="utf-8")
            output = StringIO()
            with (
                patch.object(watcher, "CONFIG_PATH", fake_config),
                patch.object(watcher, "PRODUCTS", {"us": product("US", "AAA01LL/A")}),
                patch.object(watcher, "MONITORING_AREAS", [
                    {"id": "de", "market": "US", "location": "19702"},
                ]),
                patch.object(watcher, "REQUESTS_PER_SCAN", 1),
                patch.object(watcher, "WATCHER_DISABLE_DISCORD", True),
                patch.object(watcher, "DISCORD_WEBHOOK", "https://discord.com/api/webhooks/SECRET"),
                patch.object(watcher.requests, "get") as get,
                patch.object(watcher.requests, "post") as post,
                contextlib.redirect_stdout(output),
            ):
                code = preflight.main(["--json"])
                self.assertEqual(code, 0)
                get.assert_not_called()
                post.assert_not_called()
            data = json.loads(output.getvalue())
            self.assertTrue(data["ready"])
            self.assertEqual(data["discord_mode"], "disabled for local testing")
            self.assertNotIn("SECRET", output.getvalue())
            self.assertEqual(fake_config.read_text(encoding="utf-8"), "{}")

    def test_disable_discord_opt_out_does_not_post_even_with_real_webhook(self):
        with (
            patch.object(watcher, "DISCORD_WEBHOOK", "https://discord.com/api/webhooks/SECRET"),
            patch.object(watcher, "WATCHER_DISABLE_DISCORD", True),
            patch.object(watcher.requests, "post") as post,
        ):
            watcher.safe_discord("Test event", embeds=[{"title": "Stock available"}])
            post.assert_not_called()

    def test_disable_discord_flag_does_not_change_other_runtime_logic(self):
        with (
            patch.object(watcher, "DISCORD_WEBHOOK", ""),
            patch.object(watcher, "WATCHER_DISABLE_DISCORD", False),
            patch.object(watcher.requests, "post") as post,
        ):
            watcher.safe_discord("No webhook")
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
