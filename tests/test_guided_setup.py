"""Exercise the complete wizard DOM with fake regional responses, no browser/network."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from setup_wizard import create_wizard_app, validate_config
from store_directory import stores_for_country


class GuidedSetupTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_store_first_edit_remove_and_stale_catalog_responses(self):
        folder = Path(__file__).parent / "ui"
        available = subprocess.run(["node", "-e", "require('jsdom')"], cwd=folder,
                                   capture_output=True, timeout=10)
        if available.returncode:
            self.skipTest("Install DOM test dependencies: npm ci --prefix tests/ui")
        config = {"products": {
            "us": {"market": "US", "currency": "USD", "name": "Example US variant", "part": "US-EXAMPLE/A", "price": None},
            "ca": {"market": "CA", "currency": "CAD", "name": "Example CA variant", "part": "CA-EXAMPLE/A", "price": None}},
            "monitoring_areas": [
                {"id": "us", "market": "US", "location": "19702", "store_ids": []},
                {"id": "ca", "market": "CA", "location": "Toronto", "store_ids": []}]}
        with tempfile.TemporaryDirectory() as temporary:
            client = create_wizard_app(config_path=Path(temporary) / "unused.json").test_client()
            payload = {"html": client.get("/").get_data(as_text=True), "config": config,
                       "regions": client.get("/api/regions").get_json(),
                       "stores": {market: stores_for_country(market) for market in ("US", "CA", "FR", "DE", "MO")}}
            proc = subprocess.run(["node", str(folder / "guided.cjs")], input=json.dumps(payload),
                                  capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertGreaterEqual(result["assertions"], 35)
        saved = validate_config(result["saved"])
        self.assertEqual(len(saved["monitoring_areas"]), 3)
        fr = next(area for area in saved["monitoring_areas"] if area["market"] == "FR")
        self.assertEqual(len(fr["store_ids"]), 2)
        self.assertEqual(sum(p["market"] == "FR" for p in saved["products"].values()), 2)

