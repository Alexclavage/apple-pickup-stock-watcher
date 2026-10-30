"""Network-isolated regression tests for explicit real integration commands."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

import integration_smoke as smoke


WEBHOOK = "https://discord.com/api/webhooks/1234567890/private-token-example"


class LiveIntegrationSmokeTests(unittest.TestCase):
    def test_network_commands_refuse_missing_user_confirmation(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(smoke.main(["apple"]), 2)
            self.assertEqual(smoke.main(["discord"]), 2)
        self.assertIn("REFUSED", output.getvalue())

    def test_discord_requires_valid_test_url_and_obeys_safe_mode(self):
        post = Mock()
        for webhook, disabled in (
            ("", False), ("https://evil.example/api/webhooks/123/token", False),
            (WEBHOOK, True),
        ):
            with self.subTest(webhook=bool(webhook), disabled=disabled):
                passed, message = smoke.send_discord_test(webhook, disabled, post=post)
                self.assertFalse(passed)
                self.assertNotIn(WEBHOOK, message)
        post.assert_not_called()

    def test_discord_sends_exactly_one_message_without_mentions(self):
        post = Mock(return_value=SimpleNamespace(status_code=204))
        passed, message = smoke.send_discord_test(WEBHOOK, False, post=post)
        self.assertTrue(passed)
        self.assertIn("exactly one", message)
        self.assertNotIn(WEBHOOK, message)
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args, (WEBHOOK,))
        self.assertEqual(kwargs["json"]["allowed_mentions"], {"parse": []})
        self.assertIn("NOT a real stock alert", kwargs["json"]["content"])
        self.assertEqual(kwargs["timeout"], 15)

    def test_discord_network_error_does_not_expose_secret(self):
        post = Mock(side_effect=RuntimeError("Problem connecting to " + WEBHOOK))
        passed, message = smoke.send_discord_test(WEBHOOK, False, post=post)
        self.assertFalse(passed)
        self.assertIn("RuntimeError", message)
        self.assertNotIn("private-token-example", message)
        post.assert_called_once()

    def test_summary_requires_distinct_observed_products_per_market(self):
        products = {
            "a": {"market": "CA", "part": "SKU-A"},
            "b": {"market": "CA", "part": "SKU-B"},
        }
        areas = [{"market": "CA"}]
        items = [
            {"market": "CA", "product_id": "a", "storeNumber": "R121", "status": "available"},
            {"market": "CA", "product_id": "b", "storeNumber": "R121", "status": "unavailable"},
        ]
        result = smoke.summarize_apple(products, areas, items, [])
        self.assertTrue(result["complete"])
        self.assertTrue(result["multiple_variants_observed"])
        partial = smoke.summarize_apple(products, areas, items[:1], [])
        self.assertFalse(partial["complete"])
        self.assertFalse(partial["multiple_variants_observed"])
        unknown = smoke.summarize_apple(
            products, areas, [items[0], {**items[1], "status": "unknown"}], []
        )
        self.assertFalse(unknown["complete"])
        self.assertFalse(unknown["multiple_variants_observed"])

    def test_apple_check_does_not_contact_network_for_single_sku_or_missing_config(self):
        with tempfile.TemporaryDirectory() as path:
            target = Path(path) / "config.json"
            fetch = Mock()
            watcher = SimpleNamespace(
                CONFIG_PATH=target,
                PRODUCTS={"a": {"market": "CA", "part": "AAA"}},
                MONITORING_AREAS=[{"market": "CA"}],
                fetch_all=fetch,
            )
            with redirect_stdout(StringIO()):
                self.assertEqual(smoke.check_apple_once(watcher), 2)
                target.write_text("{}", encoding="utf-8")
                self.assertEqual(smoke.check_apple_once(watcher), 2)
            fetch.assert_not_called()

    def test_apple_check_queries_once_and_redacts_private_values(self):
        with tempfile.TemporaryDirectory() as path:
            target = Path(path) / "config.json"
            target.write_text("{}", encoding="utf-8")
            postcode = "SECRETCODE"
            secret_part = "SECRET-SKU-1"
            items = [
                {"market": "CA", "product_id": "a", "storeNumber": "R121", "status": "available"},
                {"market": "CA", "product_id": "b", "storeNumber": "R121", "status": "unavailable"},
            ]
            def fetch():
                print("A log with " + postcode + " and " + secret_part)
                return items, []
            watcher = SimpleNamespace(
                CONFIG_PATH=target,
                PRODUCTS={
                    "a": {"market": "CA", "part": secret_part},
                    "b": {"market": "CA", "part": "SECOND-SKU"},
                },
                MONITORING_AREAS=[
                    {"market": "CA", "location": postcode, "id": "PRIVATE-ID"},
                ],
                fetch_all=Mock(side_effect=fetch),
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(smoke.check_apple_once(watcher), 0)
            watcher.fetch_all.assert_called_once_with()
            for private in (postcode, secret_part, "PRIVATE-ID"):
                self.assertNotIn(private, output.getvalue())
            self.assertIn("PASS", output.getvalue())

    def test_apple_partial_result_refuses_to_claim_stockout(self):
        with tempfile.TemporaryDirectory() as path:
            target = Path(path) / "config.json"
            target.write_text("{}", encoding="utf-8")
            watcher = SimpleNamespace(
                CONFIG_PATH=target,
                PRODUCTS={
                    "a": {"market": "CA", "part": "SKU-A"},
                    "b": {"market": "CA", "part": "SKU-B"},
                },
                MONITORING_AREAS=[{"market": "CA"}],
                fetch_all=Mock(return_value=(
                    [{"market": "CA", "product_id": "a",
                      "storeNumber": "R121", "status": "unavailable"}],
                    ["missing store"],
                )),
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(smoke.check_apple_once(watcher), 1)
            self.assertIn("INCOMPLETE", output.getvalue())
            self.assertIn("no assertion of sold-out", output.getvalue())


if __name__ == "__main__":
    unittest.main()
