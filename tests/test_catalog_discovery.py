"""Offline tests for bounded Apple buy-page product catalog discovery."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import catalog_discovery as catalog
from setup_wizard import create_wizard_app


def example_page():
    selection = {
        "products": [
            {"partNumber": "MJQ84LL/A", "familyType": "iphone18pro", "dimensionCapacity": "512gb",
             "dimensionColor": "silver", "dimensionScreensize": "6_3inch"},
            {"partNumber": "MJQ84LL/A", "familyType": "iphone18pro", "dimensionCapacity": "512gb",
             "dimensionColor": "silver", "dimensionScreensize": "6_3inch"},
            {"partNumber": "MJQ74LL/A", "dimensionCapacity": "512gb", "dimensionColor": "black",
             "price": {"fullPrice": 1399}},
            {"partNumber": "bad SKU", "dimensionCapacity": "256gb"},
            {"partNumber": "FOO4LL/A", "price": {"fullPrice": "unknown"}},
        ],
        "sample": {"complex": 'quoted "text" and braces { inside } an escaped JSON string'},
    }
    return (b"<html><script>let PRODUCT_SELECTION_BOOTSTRAP = "
            + json.dumps({"productSelectionData": selection}).encode("utf-8")
            + b";</script></html>")


class FakeResponse:
    def __init__(self, body=None, status=200):
        self.status_code = status
        self.body = example_page() if body is None else body
        self.closed = False

    def iter_content(self, chunk_size=65536):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start:start + chunk_size]

    def close(self):
        self.closed = True


class CatalogDiscoveryTests(unittest.TestCase):
    def setUp(self):
        catalog._cache.clear()
        self.next_patch = patch.object(catalog, "_next_request", 0.0)
        self.next_patch.start()
        self.addCleanup(self.next_patch.stop)

    def test_parses_realistic_bootstrap_without_guessing_price(self):
        rows = catalog.parse_catalog_html(example_page(), "US", "iphone-18-pro")
        self.assertEqual(len(rows), 3)
        by_sku = {item["part"]: item for item in rows}
        self.assertIn("512Gb", by_sku["MJQ84LL/A"]["name"])
        self.assertIn("Silver", by_sku["MJQ84LL/A"]["name"])
        self.assertIsNone(by_sku["MJQ84LL/A"]["price"])
        self.assertEqual(by_sku["MJQ74LL/A"]["price"], 1399.0)
        self.assertIsNone(by_sku["FOO4LL/A"]["price"])

    def test_missing_or_ambiguous_data_fails_closed(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.parse_catalog_html(b"Apple has no product selection data", "CA", "iphone-18-pro")
        bad = b'{"legacy_productSelectionData":{"products":[{"partNumber":"TESTLL/A"}]}}'
        with self.assertRaises(catalog.CatalogError):
            catalog.parse_catalog_html(bad, "US", "iphone-18-pro")

    def test_allowlisted_urls_prevent_arbitrary_network_fetches(self):
        self.assertEqual(catalog.catalog_url("CA", "iphone-18-pro"),
                         "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro")
        with self.assertRaises(catalog.CatalogError):
            catalog.catalog_url("US", "../../private")
        with self.assertRaises(catalog.CatalogError):
            catalog.catalog_url("FR", "iphone-18-pro")
        self.assertTrue(catalog.catalog_url("FR", "iphone-18-pro", experimental=True).startswith("https://www.apple.com/fr/"))

    def test_one_fetch_and_cache_per_family(self):
        calls = []
        response = FakeResponse()
        def fetch(url, **kwargs):
            calls.append((url, kwargs))
            return response
        first = catalog.fetch_catalog("US", "iphone-18-pro", requester=fetch, clock=lambda: 1000)
        second = catalog.fetch_catalog("US", "iphone-18-pro", requester=fetch, clock=lambda: 1100)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0][1]["allow_redirects"])
        self.assertTrue(response.closed)

    def test_second_uncached_query_is_rate_limited(self):
        catalog.fetch_catalog("US", "iphone-18-pro", requester=lambda *_args, **_kw: FakeResponse(), clock=lambda: 2000)
        with self.assertRaisesRegex(catalog.CatalogError, "cooldown"):
            catalog.fetch_catalog("CA", "iphone-18-pro", requester=lambda *_args, **_kw: FakeResponse(), clock=lambda: 2010)

    def test_apple_http_541_pauses_fetching(self):
        with self.assertRaisesRegex(catalog.CatalogError, "15 minutes"):
            catalog.fetch_catalog("US", "iphone-18-pro", requester=lambda *_args, **_kw: FakeResponse(status=541), clock=lambda: 3000)
        with self.assertRaisesRegex(catalog.CatalogError, "cooldown"):
            catalog.fetch_catalog("US", "iphone-18-pro", requester=lambda *_args, **_kw: FakeResponse(), clock=lambda: 3400)

    def test_oversized_html_rejected(self):
        with self.assertRaisesRegex(catalog.CatalogError, "oversized"):
            catalog.parse_catalog_html(b"x" * (catalog.MAX_HTML_BYTES + 1), "US", "iphone-18-pro")

    def test_wizard_catalog_requires_request_token_and_local_host(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / "example.json"
            sample.write_text(json.dumps({
                "products": {"us_test": {"market": "US", "name": "Sample", "part": "MJQ84LL/A", "price": 1399, "currency": "USD"}},
                "search_zips": {"DE": "19702"},
                "allowed_states": ["DE"],
            }), encoding="utf-8")
            app = create_wizard_app(root / "config.json", sample)
            client = app.test_client()
            html = client.get("/").data
            self.assertIn(b"Find Apple SKUs", html)
            token = re.search(rb'const TOKEN = "([^"]+)"', html).group(1).decode("ascii")
            payload = {"market": "US", "family": "iphone-18-pro"}
            self.assertEqual(client.post("/api/catalog/discover", json=payload).status_code, 403)
            with patch("setup_wizard.fetch_catalog", return_value={"items": [{"part": "MJQ84LL/A"}], "cached": True}):
                allowed = client.post("/api/catalog/discover", json=payload, headers={"X-Setup-Token": token})
                self.assertEqual(allowed.status_code, 200)
                self.assertEqual(allowed.get_json()["items"][0]["part"], "MJQ84LL/A")
                denied = client.post("/api/catalog/discover", json=payload, headers={
                    "X-Setup-Token": token, "Origin": "https://evil.example"})
                self.assertEqual(denied.status_code, 403)

    def test_no_fake_stock_or_full_catalog_claim(self):
        self.assertNotIn("available", catalog.parse_catalog_html(example_page(), "US", "iphone-18-pro")[0])
        self.assertLessEqual(len(catalog.FAMILIES), 12)


if __name__ == "__main__":
    unittest.main()
