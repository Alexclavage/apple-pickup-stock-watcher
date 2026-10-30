"""Check that monitoring events reach the read-only history API."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as watcher


class HistoryIntegrationTests(unittest.TestCase):
    def test_confirmed_changes_appear_in_api_but_unknown_does_not(self):
        available = {
            "key": "product:R102", "status": "available",
            "product_id": "product", "productName": "Phone", "market": "US",
            "storeNumber": "R102", "storeName": "Example", "city": "Example", "state": "DE",
        }
        unknown = dict(available, status="unknown")
        unavailable = dict(available, status="unavailable")
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(watcher, "STATE_FILE", Path(directory) / "state.json"),
                patch.object(watcher, "HISTORY_FILE", Path(directory) / "history.json"),
                patch.object(watcher, "send_stock_changes"),
                patch.object(
                    watcher, "fetch_all",
                    side_effect=[
                        ([available], []),
                        ([unknown], ["Temporary Apple outage"]),
                        ([unavailable], []),
                    ],
                ),
            ):
                watcher.poll_once()
                watcher.poll_once()
                watcher.poll_once()
                response = watcher.app.test_client().get("/api/history")
                self.assertEqual(response.status_code, 200)
                events = response.get_json()["events"]
                self.assertEqual([event["type"] for event in events], ["unavailable", "available"])
                self.assertEqual([event["store_id"] for event in events], ["R102", "R102"])


if __name__ == "__main__":
    unittest.main()
