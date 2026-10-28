"""Do not announce stock-outs from incomplete Apple checks or leak webhook URLs."""
import contextlib
from io import StringIO
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher


def stock(key, status):
    return {
        "key": key, "status": status,
        "product_id": key.split(":")[0], "productName": "iPhone",
        "market": "US", "storeNumber": key.split(":")[1],
        "storeName": "Christiana Mall", "city": "Newark", "state": "DE",
    }


class PartialStockTransitionTests(unittest.TestCase):
    def test_partially_unavailable_does_not_emit_false_stockout_or_erase_state(self):
        target = stock("iphone:R102", "available")
        apparent_down = stock("iphone:R102", "unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            history = Path(tmp) / "history.json"
            state.write_text(json.dumps({
                "available_keys": [target["key"]], "watcher_error": False,
            }), encoding="utf-8")
            with (
                patch.object(watcher, "STATE_FILE", state),
                patch.object(watcher, "HISTORY_FILE", history),
                patch.object(watcher, "send_stock_changes") as send,
                patch.object(watcher, "fetch_all", side_effect=[
                    ([apparent_down], ["CA batch unavailable"]),
                    ([apparent_down], []),
                    ([apparent_down], []),
                ]),
            ):
                watcher.poll_once()
                self.assertEqual(watcher.latest["status"], "partial")
                self.assertEqual(send.call_args.args, ([], []))
                self.assertIn(target["key"], watcher.load_state()["available_keys"])
                self.assertEqual(watcher.app.test_client().get("/api/history").get_json()["events"], [])

                watcher.poll_once()
                self.assertEqual(send.call_args.args, ([], [apparent_down]))
                self.assertNotIn(target["key"], watcher.load_state()["available_keys"])

                watcher.poll_once()
                self.assertEqual(send.call_args.args, ([], []))
                events = watcher.app.test_client().get("/api/history").get_json()["events"]
                self.assertEqual([event["type"] for event in events], ["unavailable"])

    def test_unknown_anywhere_defers_stockouts_even_without_explicit_error(self):
        down = stock("iphone:R102", "unavailable")
        unknown = stock("ipad:R121", "unknown")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps({
                "available_keys": ["iphone:R102"],
            }), encoding="utf-8")
            with (
                patch.object(watcher, "STATE_FILE", state),
                patch.object(watcher, "HISTORY_FILE", Path(tmp) / "history.json"),
                patch.object(watcher, "send_stock_changes") as send,
                patch.object(watcher, "fetch_all", return_value=([down, unknown], [])),
            ):
                watcher.poll_once()
                self.assertEqual(watcher.latest["status"], "partial")
                self.assertEqual(send.call_args.args, ([], []))
                self.assertEqual(watcher.load_state()["available_keys"], ["iphone:R102"])

    def test_partial_scan_still_allows_confirmed_positive_availability(self):
        known_down = stock("iphone:R102", "unavailable")
        new_up = stock("ipad:R121", "available")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text(json.dumps({
                "available_keys": ["iphone:R102"],
            }), encoding="utf-8")
            with (
                patch.object(watcher, "STATE_FILE", state),
                patch.object(watcher, "HISTORY_FILE", Path(tmp) / "history.json"),
                patch.object(watcher, "send_stock_changes") as send,
                patch.object(watcher, "fetch_all", return_value=([
                    known_down, new_up,
                ], ["one area failed"])),
            ):
                watcher.poll_once()
                self.assertEqual(send.call_args.args, ([new_up], []))
                self.assertEqual(
                    set(watcher.load_state()["available_keys"]),
                    {"iphone:R102", "ipad:R121"},
                )

    def test_dashboard_does_not_show_unconfirmed_negative_as_sold_out(self):
        from dashboard_groups import build_model_groups
        products = {
            "iphone": {
                "market": "US", "watch_model": "iphone-18-pro",
                "name": "iPhone", "part": "ABC01LL/A",
                "currency": "USD", "price": None,
            },
            "ipad": {
                "market": "US", "name": "iPad", "part": "ABC02LL/A",
                "currency": "USD", "price": None,
            },
        }
        negative = dict(
            stock("iphone:R102", "unavailable"),
            storeName="Christiana Mall",
        )
        positive = dict(
            stock("ipad:R102", "available"),
            storeName="Christiana Mall",
        )
        groups = build_model_groups(
            products, [negative, positive],
            scan_status="partial", checked_at="2026-10-28T04:00:00+00:00",
        )
        iphone = next(group for group in groups if group["model_id"] == "iphone-18-pro")
        ipad = next(group for group in groups if group["title"] == "iPad")
        self.assertEqual(iphone["status"], "partial")
        self.assertEqual(iphone["stores"][0]["status"], "unknown")
        self.assertEqual(iphone["stores"][0]["variants"][0]["status"], "unknown")
        self.assertIn("awaiting a complete recheck", iphone["stores"][0]["variants"][0]["quote"])
        self.assertEqual(ipad["stores"][0]["status"], "available")
        self.assertEqual(ipad["available_stores"], 1)
        completed = build_model_groups(
            products, [negative, positive],
            scan_status="available", checked_at="checked",
        )
        confirmed = next(group for group in completed if group["model_id"] == "iphone-18-pro")
        self.assertEqual(confirmed["stores"][0]["status"], "unavailable")

    def test_discord_errors_do_not_print_private_webhook_link(self):
        secret = "https://discord.com/api/webhooks/privateid/secret-token"
        def broken_post(*args, **kwargs):
            raise RuntimeError("Request failed for " + secret)
        output = StringIO()
        with (
            patch.object(watcher, "DISCORD_WEBHOOK", secret),
            patch.object(watcher.requests, "post", side_effect=broken_post),
            contextlib.redirect_stdout(output),
        ):
            watcher.safe_discord("test alert")
        self.assertNotIn(secret, output.getvalue())
        self.assertNotIn("secret-token", output.getvalue())
        self.assertIn("RuntimeError", output.getvalue())


if __name__ == "__main__":
    unittest.main()
