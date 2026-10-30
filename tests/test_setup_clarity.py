"""Offline checks for explicit preview, draft, saved and restart setup states."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from setup_wizard import WIZARD_HTML


class ClearWatchlistTests(unittest.TestCase):
    def test_wizard_explains_three_distinct_states(self):
        for label in (
            'id="watchSummary"',
            'id="watchSummaryCount"',
            'id="watchAreaSummary"',
            'id="previewWarning"',
            'id="setupState"',
            'id="saveDock"',
            'id="saveSticky"',
            'id="discardPreview"',
            'id="stepRestart"',
            "Variants found — not added yet",
            "Changes not saved",
            "Configuration saved on this computer",
            "restart the watcher",
            "These are only search results",
            "Finding variants is only a preview",
            "3. Save private configuration",
        ):
            self.assertIn(label, WIZARD_HTML)

    def test_unadded_preview_is_not_silently_saved(self):
        self.assertIn('if(modelPreview&&!el("modelOptions").hidden)', WIZARD_HTML)
        self.assertIn(
            "You found variants but have not added them.",
            WIZARD_HTML,
        )
        self.assertIn('el("saveSticky").addEventListener("click",()=>el("save").click())', WIZARD_HTML)
        self.assertIn('el("watchSummary").scrollIntoView', WIZARD_HTML)
        self.assertIn('markDirty();', WIZARD_HTML)

    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable")
    def test_saved_preview_and_dirty_states_in_real_js(self):
        proc = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10, check=False,
        )
        match = re.match(r"v?(\d+)\.", proc.stdout)
        if not match or int(match.group(1)) < 18:
            self.skipTest("Requires Node 18+ to evaluate modern wizard JavaScript")

        start = WIZARD_HTML.index("function refreshSetupState(){")
        end = WIZARD_HTML.index("const splitIds =", start)
        source = WIZARD_HTML[start:end]
        fixture = r"""
const nodes=new Map();
function el(id){
  if(!nodes.has(id)){
    nodes.set(id,{
      textContent:"",hidden:false,dataset:{},
      classList:{toggle(){}}
    });
  }
  return nodes.get(id);
}
let hasSavedFile=true;
let hasUnsavedChanges=false;
let isLoadingConfig=false;
let modelPreview=null;
let renderCount=0;
let warnCount=0;
function renderMonitoredModels(){renderCount++}
function updateAreaWarning(){warnCount++}
const document={
 querySelectorAll(selector){
   if(selector===".product-entry")return [{},{}];
   if(selector===".region-entry")return [{}];
   return [];
 },
 body:{classList:{toggle(){}}}
};
"""
        assertions = r"""
refreshSetupState();
if(el("setupState").dataset.state!=="saved")throw Error("Saved status not shown");
if(!el("saveDock").hidden)throw Error("Save dock must be hidden for saved state");
if(!el("setupStateDetail").textContent.includes("Restart"))throw Error("Restart instruction missing");
modelPreview={count:16};el("modelOptions").hidden=false;
refreshSetupState();
if(el("setupState").dataset.state!=="preview")throw Error("Preview is not distinct from saved");
if(!el("saveDock").hidden)throw Error("Finding variants must not dirty the config");
markDirty();
if(el("setupState").dataset.state!=="dirty")throw Error("Draft change not reflected");
if(el("saveDock").hidden)throw Error("Sticky Save not visible for unsaved changes");
if(renderCount!==1||warnCount!==1)throw Error("Summary not refreshed on edits");
hasUnsavedChanges=false;modelPreview=null;
refreshSetupState();
if(el("setupState").dataset.state!=="saved"||!el("saveDock").hidden)
  throw Error("Saved status not restored");
"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test-wizard-state.js"
            path.write_text(fixture + "\n" + source + "\n" + assertions, encoding="utf-8")
            check = subprocess.run(
                ["node", str(path)], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=15, check=False,
            )
        self.assertEqual(check.returncode, 0, check.stderr)


if __name__ == "__main__":
    unittest.main()
