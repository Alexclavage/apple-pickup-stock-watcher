"""Validate the wizard's inline JavaScript when Node.js is installed.

Use a UTF-8 temporary file rather than piping non-ASCII JavaScript through
stdin. Windows console encodings (e.g. cp949) and older Node versions can
otherwise fail with UnicodeEncodeError or "node: bad option: -".
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from setup_wizard import WIZARD_HTML


class WizardJavaScriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable")
    def test_inline_javascript_parses(self):
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
