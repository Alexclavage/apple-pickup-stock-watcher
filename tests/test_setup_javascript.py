"""Validate inline wizard JavaScript when Node.js is available on CI."""
import shutil
import subprocess
import unittest

from setup_wizard import WIZARD_HTML


class WizardJavaScriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable")
    def test_inline_javascript_parses(self):
        self.assertEqual(WIZARD_HTML.count("<script>"), 1)
        source = WIZARD_HTML.split("<script>", 1)[1].split("</script>", 1)[0]
        source = source.replace("{{ token | tojson }}", '"test-csrf-token"')
        run = subprocess.run(
            ["node", "--check", "-"],
            input=source,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
