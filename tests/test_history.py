"""Offline tests for the bounded stock-event history."""
import tempfile
import unittest
from pathlib import Path

from history import append_history, read_history, transition_event


class HistoryTests(unittest.TestCase):
    def test_missing_and_corrupt_file_return_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            self.assertEqual(read_history(path), [])
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(read_history(path), [])

    def test_events_are_newest_first_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            for index in range(5):
                self.assertTrue(append_history(path, [{"at": str(index)}], max_entries=3))
            self.assertEqual([entry["at"] for entry in read_history(path)], ["4", "3", "2"])
            self.assertEqual(len(read_history(path, limit=2)), 2)

    def test_empty_updates_leave_history_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            self.assertTrue(append_history(path, [{"at": "first"}]))
            original = path.read_bytes()
            self.assertTrue(append_history(path, []))
            self.assertEqual(path.read_bytes(), original)

    def test_transition_event_contains_no_unknown_fields(self):
        item = {
            "product_id": "iphone",
            "productName": "iPhone",
            "market": "US",
            "storeNumber": "R102",
            "storeName": "Example",
            "city": "Sample",
            "state": "DE",
            "email": "should-not-be-stored",
            "quote": "unneeded",
        }
        event = transition_event(item, "available", "2026-10-27T00:00:00Z")
        self.assertEqual(event["type"], "available")
        self.assertNotIn("email", event)
        self.assertNotIn("quote", event)
        with self.assertRaises(ValueError):
            transition_event(item, "unknown", "timestamp")


if __name__ == "__main__":
    unittest.main()
