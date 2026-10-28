"""Validate the wizard's inline JavaScript with a compatible Node.js version.

The browser UI uses modern JavaScript (async/await, optional chaining, etc.).
Old Node.js installations on a developer's PATH cannot parse it, even though
modern browsers can. Modern CI must still execute this syntax check.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from setup_wizard import WIZARD_HTML


MINIMUM_NODE_MAJOR = 18


class WizardJavaScriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable; browser JavaScript syntax check skipped")
    def test_inline_javascript_parses(self):
        version = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if version.returncode != 0:
            self.fail(f"Cannot check Node.js version: {version.stderr}")
        match = re.match(r"v?(\d+)\.", version.stdout.strip())
        if match is None:
            self.fail(f"Unrecognized Node.js version: {version.stdout!r}")
        major_version = int(match.group(1))
        if major_version < MINIMUM_NODE_MAJOR:
            self.skipTest(
                f"Installed Node.js {version.stdout.strip()} is too old for this "
                f"modern-browser JavaScript syntax check; use Node.js {MINIMUM_NODE_MAJOR}+ "
                "to run it. This does not disable the browser UI."
            )

        self.assertEqual(WIZARD_HTML.count("<script>"), 1)
        source = WIZARD_HTML.split("<script>", 1)[1].split("</script>", 1)[0]
        source = source.replace("{{ token | tojson }}", '"test-csrf-token"')
        with tempfile.TemporaryDirectory() as folder:
            script_path = Path(folder) / "setup-wizard-check.js"
            script_path.write_text(source, encoding="utf-8")
            run = subprocess.run(
                ["node", "--check", str(script_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
