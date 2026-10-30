"""Offline checks for descriptive IDs and green selection feedback."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from setup_wizard import WIZARD_HTML


class ReadableIdentifiersAndToastTests(unittest.TestCase):
    def test_ui_exposes_rename_action_and_bottom_right_success_toast(self):
        for expected in (
            'id="toastZone"', 'class="toast-zone"', 'id="renameAreas"',
            'class="areaTitle"', 'areaIdFromLocation(', 'productIdForVariant(',
            'showToast("Added "+added', 'showToast("Removed "+variants.length',
            'showToast("Removed "+name', 'showToast("Removed area "+label',
        ):
            self.assertIn(expected, WIZARD_HTML)
        self.assertIn("position:fixed;right:20px;bottom:20px", WIZARD_HTML)
        self.assertIn("Save to apply", WIZARD_HTML)
        self.assertIn('aria-live="polite"', WIZARD_HTML)

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable")
    def test_generated_ids_are_meaningful_unique_and_schema_compatible(self):
        version = subprocess.run(
            ["node", "--version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, timeout=10,
        )
        match = re.match(r"v?(\d+)\.", version.stdout)
        if not match or int(match.group(1)) < 18:
            self.skipTest("Modern Node.js 18+ is required for JavaScript helper assertions")

        start = WIZARD_HTML.index("function slugPart(value){")
        end = WIZARD_HTML.index("function showToast(message){", start)
        helpers = WIZARD_HTML[start:end]
        checks = r"""
const device = {
  market:"CA",storage:"512 GB",color:"Silver",part:"MG001VC/A"
};
const skuId = productIdForVariant(device,"iphone-18-pro-max");
if(skuId !== "iphone_18_pro_max_512gb_silver_ca")
  throw new Error("Product ID mismatch: "+skuId);
if(!/^[a-z][a-z0-9_]{0,39}$/.test(skuId))
  throw new Error("Product ID violates schema");
const us = areaIdFromLocation("US","19702");
const canada = areaIdFromLocation("CA","M5B 2H1");
const city = areaIdFromLocation("CA","Toronto");
if(us!=="us_19702" || canada!=="ca_m5b2h1" || city!=="ca_toronto")
  throw new Error("Area ID mismatch: "+[us,canada,city].join(","));
const used = new Set();
const original = uniqueId(skuId,used,40);
const duplicate = uniqueId(skuId,used,40);
if(original!==skuId || duplicate===original || duplicate.length>40)
  throw new Error("Duplicate product IDs are not unique");
const old = new Set(["us_19702"]);
if(uniqueId("us_19702",old,32)!=="us_19702_2")
  throw new Error("Area ID collision not resolved");
if(productIdForVariant({
  market:"US",storage:"1 TB",color:"Deep Blue",carrier:"unlocked"
},"iphone-18-pro-max").length>40)
  throw new Error("Generated ID over length limit");
"""
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "id-helpers-test.js"
            script.write_text(helpers + "\n" + checks, encoding="utf-8")
            proc = subprocess.run(
                ["node", str(script)], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15, check=False,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
