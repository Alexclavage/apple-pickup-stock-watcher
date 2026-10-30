"""Release-candidate smoke tests: fresh sample install, privacy and docs coherence.

All tests are offline. The subprocess loads a temporary *example* config and
does not launch a watcher or contact Apple, currency providers or Discord.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import requests
import app as watcher


ROOT = Path(__file__).resolve().parent.parent


class ReleaseCandidateTests(unittest.TestCase):
    def test_fresh_sample_config_runs_real_preflight_offline(self):
        sample = ROOT / "config.example.json"
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            config = temp / "config.json"
            shutil.copyfile(sample, config)
            before = config.read_bytes()
            env = dict(os.environ)
            env.update({
                "WATCHER_CONFIG": str(config),
                "STATE_FILE": str(temp / "state.json"),
                "HISTORY_FILE": str(temp / "history.json"),
                "DISCORD_WEBHOOK": "",
                "WATCHER_DISABLE_DISCORD": "1",
            })
            result = subprocess.run(
                [sys.executable, str(ROOT / "preflight.py"), "--json"],
                cwd=str(ROOT), env=env, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=20, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ready"])
            self.assertTrue(payload["private_config"])
            self.assertEqual(
                {m["market"] for m in payload["markets"]},
                {"US", "CA"},
            )
            self.assertEqual(
                payload["requests_per_cycle"],
                sum(m["requests_per_cycle"] for m in payload["markets"]),
            )
            self.assertEqual(payload["discord_mode"], "disabled for local testing")
            self.assertEqual(config.read_bytes(), before)
            self.assertFalse((temp / "state.json").exists())
            self.assertFalse((temp / "history.json").exists())

    def test_local_env_example_has_unique_sanitized_keys(self):
        env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
        keys = []
        for raw in env_text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            self.assertIn("=", line)
            name, value = line.split("=", 1)
            self.assertRegex(name, r"^[A-Z][A-Z0-9_]*$")
            self.assertNotIn(name, keys)
            keys.append(name)
            self.assertNotIn("discord.com/api/webhooks/", value.lower())
        self.assertIn("DISCORD_WEBHOOK", keys)
        self.assertIn("WATCHER_CONFIG", keys)
        self.assertIn("STATE_FILE", keys)

    def test_documentation_exists_and_explains_local_first(self):
        for path in (
            "README.md", "docs/ARCHITECTURE.md",
            "docs/RELEASE_CHECKLIST.md", "LICENSE", "SECURITY.md",
        ):
            self.assertTrue((ROOT / path).is_file(), path)
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for phrase in (
            "preflight.py", "setup_wizard.py", "WATCHER_DISABLE_DISCORD=1",
            "127.0.0.1:8080", "France", "experimental",
            "not affiliated with Apple",
        ):
            self.assertIn(phrase.lower(), text.lower())

    def test_corrupt_but_valid_json_state_cannot_kill_polling_worker(self):
        # Valid JSON is not necessarily a valid state object. Previously a
        # top-level [] crashed both poll_once and its exception handler.
        sample = {
            "key": "us_pro_512:R102",
            "product_id": "us_pro_512",
            "storeNumber": "R102",
            "market": "US",
            "status": "available",
        }
        bad_states = (
            "[]", '"unexpected"', "null",
            '{"available_keys": "not a list"}',
            '{"available_keys": [["unhashable"]]}',
            '{"watcher_error": "not a boolean"}',
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_file = root / "state.json"
            for invalid in bad_states:
                with self.subTest(contents=invalid):
                    state_file.write_text(invalid, encoding="utf-8")
                    with (
                        patch.object(watcher, "STATE_FILE", state_file),
                        patch.object(watcher, "HISTORY_FILE", root / "history.json"),
                        patch.object(watcher, "send_stock_changes"),
                        patch.object(watcher, "fetch_all", return_value=([sample], [])),
                    ):
                        delay = watcher.poll_once()
                        self.assertEqual(delay, watcher.INTERVAL)
                        self.assertEqual(watcher.latest["status"], "available")
                        self.assertEqual(
                            watcher.load_state()["available_keys"], [sample["key"]]
                        )

    def test_runtime_rejects_nonfinite_prices_from_manually_edited_json(self):
        sample = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        first_product = next(iter(sample["products"]))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "config.json"
            for bad_price in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(price=str(bad_price)):
                    sample["products"][first_product]["price"] = bad_price
                    target.write_text(json.dumps(sample), encoding="utf-8")
                    env = dict(os.environ)
                    env.update({
                        "WATCHER_CONFIG": str(target),
                        "DISCORD_WEBHOOK": "",
                        "WATCHER_DISABLE_DISCORD": "1",
                    })
                    process = subprocess.run(
                        [sys.executable, "-c", "import app"],
                        cwd=str(ROOT), env=env, capture_output=True,
                        text=True, encoding="utf-8", errors="replace",
                        timeout=20, check=False,
                    )
                    self.assertNotEqual(process.returncode, 0)
                    self.assertIn("finite nonnegative numeric price", process.stderr)

    def test_apple_network_error_does_not_echo_location_or_sku(self):
        location = "SECRET-POSTCODE"
        part = "SECRET-PART-123"
        unsafe_url = (
            "https://www.apple.com/shop/retail/pickup-message?"
            f"location={location}&parts.0={part}"
        )
        # Mirrors how requests can include a full request URL in its error.
        with (
            patch.dict(watcher.PRODUCTS, {
                "redact_test": {
                    "market": "US", "name": "Example", "part": part,
                    "price": None, "currency": "USD",
                }
            }),
            patch.object(
                watcher.requests, "get",
                side_effect=requests.ConnectionError("Failed to connect " + unsafe_url),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Apple connection failed") as found:
                watcher.fetch_market(watcher.US_URL, location, ["redact_test"])
        for private_value in (location, part, unsafe_url):
            self.assertNotIn(private_value, str(found.exception))


if __name__ == "__main__":
    unittest.main()
