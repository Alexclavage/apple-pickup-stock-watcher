"""Worldwide directory and regional candidates: offline safety regressions."""
import json
import re
import tempfile
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import app as watcher
from catalog_discovery import catalog_url, parse_catalog_html
from regions import REGIONS, normalize_location, region_for
from setup_wizard import create_wizard_app, validate_config
from store_directory import directory_countries, stores_for_country
import store_directory
from setup_wizard import WIZARD_HTML


class WorldwideTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_directory_ui_blocks_unverified_selection_and_ignores_stale_responses(self):
        version = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        if not re.match(r"v(1[89]|[2-9][0-9])\.", version.stdout):
            self.skipTest("Node 18+ required")
        source = WIZARD_HTML.split("function renderDirectory(){", 1)[1].split("async function start(){", 1)[0]
        fixture = r'''
const assert=require('node:assert/strict');
const nodes=new Map();
function el(id){
 if(!nodes.has(id))nodes.set(id,{value:'',disabled:false,hidden:false,textContent:'',checked:false,
   replaceChildren(){this.value=''},append(option){if(!this.value)this.value=option.value},
   addEventListener(name,fn){this[name]=fn}});
 return nodes.get(id);
}
const document={createElement(){return {}},querySelectorAll(){return []}};
let regionInfo={US:{experimental:false},JP:{experimental:true},HK:{experimental:true}};
let directoryRows=[],directoryRequest=0,added=0,statusText='';
function status(text){statusText=text}
function regionRow(){added++}
function splitIds(s){return s.split(',').filter(Boolean)}
const pending=new Map();
const fetch=(url)=>new Promise(resolve=>pending.set(url,resolve));
'''
        checks = r'''
(async()=>{
 el('directoryMarket').value='MO';
 directoryRows=[{id:'R697',name:'Cotai Strip',city:'Macao',url:'https://www.apple.com/mo-en/retail/cotaistrip/'}];
 renderDirectory();assert.equal(el('addDirectoryStore').disabled,true);
 el('addDirectoryStore').click();assert.equal(added,0);
 el('directoryMarket').value='JP';el('directoryStore').value='R697';
 el('addDirectoryStore').click();assert.equal(added,0);
 assert.match(statusText,/experimental/);
 const first=loadDirectory();
 el('directoryMarket').value='HK';const second=loadDirectory();
 const latest={stores:[{id:'R409',name:'Causeway Bay',city:'Hong Kong',url:'https://www.apple.com/hk/en/retail/causewaybay/'}],observed_at:'2026-10-30'};
 pending.get('/api/stores?market=HK')({ok:true,json:async()=>latest});await second;
 pending.get('/api/stores?market=JP')({ok:true,json:async()=>({stores:[],observed_at:'old'})});await first;
 assert.equal(directoryRows[0].id,'R409');assert.match(el('directoryStatus').textContent,/Experimental/);
 el('directorySearch').value='R409';renderDirectory();assert.equal(el('directoryStore').value,'R409');
 el('directorySearch').value='no such store';renderDirectory();assert.equal(el('addDirectoryStore').disabled,true);
 regionInfo.HK.validation={pickup_observed:true,distinct_variants_observed:2,stores_returned:6};
 el('directorySearch').value='';
 const third=loadDirectory();
 pending.get('/api/stores?market=HK')({ok:true,json:async()=>latest});await third;
 assert.match(el('directoryStatus').textContent,/limited live check/);
 assert.match(el('directoryStatus').textContent,/Other combinations remain unverified/);
 regionInfo.HK.validation={catalog_parsed:true,pickup_observed:false};
 const fourth=loadDirectory();
 pending.get('/api/stores?market=HK')({ok:true,json:async()=>latest});await fourth;
 assert.match(el('directoryStatus').textContent,/pickup coverage was incomplete/);
 assert.equal(pending.size,2);
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "worldwide-ui-test.js"
            script.write_text(fixture + "function renderDirectory(){" + source + checks, encoding="utf-8")
            proc = subprocess.run(["node", str(script)], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_snapshot_ids_and_urls_are_official_and_globally_unique(self):
        countries = directory_countries()
        self.assertEqual(len(countries), 27)
        self.assertEqual(sum(c["stores"] for c in countries), 535)
        seen = set()
        for country in countries:
            payload = stores_for_country(country["code"])
            self.assertEqual(payload["observed_at"], "2026-10-30")
            for store in payload["stores"]:
                self.assertRegex(store["id"], r"^R[0-9]+$")
                self.assertNotIn(store["id"], seen)
                seen.add(store["id"])
                url = urlsplit(store["url"])
                self.assertEqual(url.scheme, "https")
                self.assertIn(url.netloc, {"www.apple.com", "www.apple.com.cn"})
                self.assertIn("/retail/", url.path)
        # Caller edits must not corrupt the cached directory.
        payload["stores"][0]["name"] = "Changed"
        self.assertNotEqual(stores_for_country(country["code"])["stores"][0]["name"], "Changed")

    def test_bounded_validation_evidence_does_not_promote_experimental_market(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "regional_validation.json"
            evidence.write_text(json.dumps({"observed_at": "2026-10-30", "markets": [
                {"market": "GB", "catalog_parsed": True, "pickup_observed": True,
                 "stores_returned": 12, "unknown_observations": 0, "known_observations": 24,
                 "distinct_variants_observed": 2},
                {"market": "FR", "catalog_parsed": True, "pickup_observed": False}], "followups": [
                {"market": "FR", "catalog_parsed": True, "pickup_observed": True,
                 "stores_returned": 1, "known_observations": 2,
                 "unknown_observations": 0, "distinct_variants_observed": 2}]}), encoding="utf-8")
            store_directory._validation.cache_clear()
            try:
                with patch.object(store_directory, "VALIDATION_FILE", evidence):
                    metadata = create_wizard_app().test_client().get("/api/regions").get_json()
                    self.assertTrue(metadata["GB"]["experimental"])
                    self.assertTrue(metadata["GB"]["validation"]["pickup_observed"])
                    self.assertTrue(metadata["FR"]["validation"]["pickup_observed"])
                    self.assertTrue(metadata["FR"]["experimental"])
                    self.assertIsNone(metadata["JP"]["validation"])
                    copy = store_directory.validation_for_country("GB")
                    copy["pickup_observed"] = False
                    self.assertTrue(store_directory.validation_for_country("GB")["pickup_observed"])
            finally:
                store_directory._validation.cache_clear()

    def test_malformed_optional_evidence_cannot_claim_a_verified_check(self):
        samples = ["not JSON", "[]", '{"observed_at":"2026-10-30","markets":"bad"}',
                   json.dumps({"observed_at": "2026-10-30", "markets": [
                       {"market": "GB", "catalog_parsed": True, "pickup_observed": "false"},
                       {"market": "FR", "catalog_parsed": True, "pickup_observed": True,
                        "stores_returned": 1, "distinct_variants_observed": 2,
                        "unknown_observations": 1}]})]
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            try:
                with patch.object(store_directory, "VALIDATION_FILE", evidence):
                    for sample in samples:
                        evidence.write_text(sample, encoding="utf-8")
                        store_directory._validation.cache_clear()
                        metadata = create_wizard_app().test_client().get("/api/regions").get_json()
                        self.assertIsNone(metadata["GB"]["validation"])
                        self.assertIsNone(metadata["FR"]["validation"])
                        self.assertTrue(metadata["GB"]["experimental"])
            finally:
                store_directory._validation.cache_clear()

    def test_all_candidates_require_opt_in_and_regional_currency(self):
        for code, region in REGIONS.items():
            with self.subTest(market=code):
                config = {
                    "products": {"phone": {"market": code, "currency": region.currency,
                                             "name": "Example", "part": "EXAMPLE/A", "price": None}},
                    "monitoring_areas": [{"id": "area", "market": code,
                                          "location": "10001", "store_ids": []}],
                }
                if region.experimental:
                    with self.assertRaisesRegex(ValueError, "experimental"):
                        validate_config(config)
                config["enable_experimental_regions"] = True
                self.assertEqual(validate_config(config)["products"]["phone"]["currency"], region.currency)
                config["products"]["phone"]["currency"] = "WRONG"
                with self.assertRaisesRegex(ValueError, "currency"):
                    validate_config(config)
        self.assertEqual({c["code"] for c in directory_countries()} - set(REGIONS), {"MO"})
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            region_for("MO", True)

    def test_unicode_locations_and_control_characters(self):
        for code, value in (("JP", "東京都"), ("KR", "서울"), ("CN", "上海"),
                            ("TH", "กรุงเทพมหานคร"), ("TR", "İstanbul")):
            self.assertEqual(normalize_location(code, value), value)
        for value in ("Tokyo\n", "https://example.com", "Tokyo\x00", "Tokyo\t100"):
            with self.assertRaises(ValueError):
                normalize_location("JP", value)

    def test_catalog_uses_regional_currency_and_china_domain(self):
        page = b'productSelectionData:{"products":[{"partNumber":"EXAMPLE/A"}]}'
        for market, region in REGIONS.items():
            rows = parse_catalog_html(page, market, "iphone-17")
            self.assertEqual(rows[0]["currency"], region.currency)
            url = catalog_url(market, "iphone-17", experimental=True)
            self.assertEqual(urlsplit(url).hostname,
                             "www.apple.com.cn" if market == "CN" else "www.apple.com")
        with self.assertRaises(ValueError):
            region_for("https://example.com", True)

    def test_high_denomination_prices_are_not_discarded_by_dollar_sized_cap(self):
        for market, amount in (("JP", 250000), ("KR", 2500000), ("TR", 149999)):
            page = ('productSelectionData:{"products":[{"partNumber":"EXAMPLE/A",'
                    '"price":{"fullPrice":'+str(amount)+'}}]}').encode()
            row = parse_catalog_html(page, market, "iphone-17")[0]
            self.assertEqual(row["price"], amount)
            config = {"enable_experimental_regions": True,
                      "products": {"phone": row},
                      "monitoring_areas": [{"id": "local", "market": market,
                                            "location": "10001", "store_ids": []}]}
            self.assertEqual(validate_config(config)["products"]["phone"]["price"], amount)

    def test_new_market_does_not_inherit_us_or_canadian_taxes(self):
        for code, region in REGIONS.items():
            if code in {"US", "CA", "FR", "GB"}:
                continue
            with patch.object(watcher, "get_eur_rate") as fx:
                result = watcher.money_info({"market": code, "currency": region.currency, "price": 100},
                                            {"state": "DE"})
            self.assertIsNone(result["tax_rate"])
            self.assertIsNone(result["total"])
            self.assertIsNone(result["tax_included"])
            fx.assert_not_called()

    def test_public_directory_api_is_offline_local_and_cannot_write_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.json"
            wizard = create_wizard_app(config_path=path)
            client = wizard.test_client()
            with patch("requests.sessions.Session.request", side_effect=AssertionError("No network")):
                metadata = client.get("/api/regions").get_json()
                self.assertEqual(metadata["JP"]["currency"], "JPY")
                self.assertTrue(metadata["JP"]["experimental"])
                self.assertNotIn("MO", metadata)
                self.assertEqual(len(client.get("/api/stores?market=JP").get_json()["stores"]), 11)
                self.assertEqual(client.get("/api/stores?market=MO").status_code, 200)
                self.assertEqual(client.get("/api/stores?market=ZZ").status_code, 422)
                self.assertEqual(client.get("/api/stores", environ_base={"REMOTE_ADDR": "192.0.2.1"}).status_code, 403)
                self.assertEqual(client.get("/api/stores", headers={"Host": "evil.example"}).status_code, 403)
                html = client.get("/").get_data(as_text=True)
                self.assertIn("Japan (experimental)", html)
                self.assertIn("Macao (2)", html)
                self.assertNotIn("{{region", html)
            self.assertFalse(path.exists())

    def test_regional_polling_routes_and_errors_remain_unknown(self):
        for code, region in REGIONS.items():
            if code in {"US", "CA"}:
                continue
            product = {"market": code, "currency": region.currency, "price": None,
                       "part": "EXAMPLE/A", "name": "Example"}
            area = {"id": "test", "market": code, "location": "10001", "store_ids": ["R001"]}
            with (patch.object(watcher, "PRODUCTS", {"phone": product}),
                  patch.object(watcher, "MONITORING_AREAS", [area]),
                  patch.object(watcher, "MARKET_PRODUCT_IDS", {code: ["phone"]}),
                  patch.object(watcher, "fetch_market") as fetch):
                fetch.return_value = [{"storeNumber": "R001", "storeName": "Example",
                                       "partsAvailability": {"EXAMPLE/A": {"pickupDisplay": "available"}}}]
                rows, errors = watcher.fetch_all()
                fetch.assert_called_once_with(region.pickup_url, "10001", ["phone"])
                self.assertFalse(errors)
                self.assertEqual(rows[0]["status"], "available")
                fetch.return_value = []
                with self.assertRaises(RuntimeError):
                    watcher.fetch_all()


if __name__ == "__main__":
    unittest.main()
