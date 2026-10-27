"""Offline regression tests: never call Apple or Discord."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher


class StockLogicTests(unittest.TestCase):
    def test_pickup_availability_classification(self):
        cases = [
            ({"pickupDisplay": "available"}, "available"),
            ({"pickupDisplay": "AVAILABLE"}, "available"),
            ({"pickupDisplay": "unavailable"}, "unavailable"),
            ({"pickupDisplay": "not-available"}, "unavailable"),
            ({"pickupDisplay": "comingSoon"}, "unknown"),
            ({}, "unknown"),
        ]
        for sample, expected in cases:
            with self.subTest(sample=sample):
                self.assertEqual(watcher.status_from_availability(sample), expected)

    def test_missing_product_availability_is_unknown(self):
        product_id = next(iter(watcher.PRODUCTS))
        store = {
            "storeNumber": "R999",
            "storeName": "Example Store",
            "city": "Example City",
            "state": "DE",
            "partsAvailability": {},
        }
        with patch.object(watcher, "money_info", return_value={}):
            item = watcher.parse_item(store, product_id)
        self.assertEqual(item["status"], "unknown")
        self.assertEqual(item["storeNumber"], "R999")

    def test_confirmed_unavailable_transition_is_reported_once(self):
        available = {"key": "example:R999", "status": "available"}
        unknown = {"key": "example:R999", "status": "unknown"}
        unavailable = {"key": "example:R999", "status": "unavailable"}
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            with patch.object(watcher, "STATE_FILE", state_file):
                with patch.object(watcher, "send_stock_changes") as send:
                    with patch.object(
                        watcher, "fetch_all",
                        side_effect=[
                            ([available], []),
                            ([unknown], ["partial"]),
                            ([unavailable], []),
                            ([unavailable], []),
                        ],
                    ):
                        watcher.poll_once()
                        watcher.poll_once()
                        watcher.poll_once()
                        watcher.poll_once()

                    self.assertEqual(send.call_count, 4)
                    self.assertEqual(send.call_args_list[0].args[0], [available])
                    self.assertEqual(send.call_args_list[1].args[0], [])
                    self.assertEqual(send.call_args_list[1].args[1], [])
                    self.assertEqual(send.call_args_list[2].args[1], [unavailable])
                    self.assertEqual(send.call_args_list[3].args[0], [])
                    self.assertEqual(send.call_args_list[3].args[1], [])

    def test_unreadable_state_is_treated_as_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            state_file.write_text("{invalid json", encoding="utf-8")
            with patch.object(watcher, "STATE_FILE", state_file):
                self.assertEqual(watcher.load_state(), {})


if __name__ == "__main__":
    unittest.main()
