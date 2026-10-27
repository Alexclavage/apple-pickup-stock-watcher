"""Offline tests for the local-only visual configuration wizard."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from setup_wizard import InvalidConfig, create_wizard_app, validate_config


def example():
    return {
        "products": {
            "us_pro_512": {
                "market": "US",
                "name": "Example iPhone",
                "part": "ABC123LL/A",
                "price": 999,
                "currency": "USD",
            }
        },
        "search_zips": {"DELAWARE": "19702"},
        "allowed_states": ["DE", "PA"],
        "us_priority_store": "R102",
        "ca_location": "",
        "ca_target_store": "",
        "ca_tax_rate": 0.13,
    }


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config_path = self.root / "config.json"
        self.sample_path = self.root / "config.example.json"
        self.sample_path.write_text(json.dumps(example()), encoding="utf-8")
        self.app = create_wizard_app(self.config_path, self.sample_path)
        self.client = self.app.test_client()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'const TOKEN = "([^"]+)"', response.data)
        self.assertIsNotNone(match)
        self.token = match.group(1).decode("ascii")

    def save(self, data, token=True, headers=None):
        headers = dict(headers or {})
        if token:
            headers["X-Setup-Token"] = self.token
        return self.client.post("/api/config", json=data, headers=headers)

    def test_example_is_loaded_without_creating_private_config(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["exists"])
        self.assertEqual(payload["config"]["products"], example()["products"])
        self.assertFalse(self.config_path.exists())

    def test_valid_configuration_saved_with_backup(self):
        data = example()
        data["alert_store_ids"] = ["R102"]
        data["alert_product_ids"] = ["us_pro_512"]
        data["custom_user_setting"] = {"preserve": "yes"}
        saved = self.save(data)
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertTrue(self.config_path.is_file())
        result = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(result["alert_store_ids"], ["R102"])
        self.assertEqual(result["custom_user_setting"], {"preserve": "yes"})
        self.assertFalse((self.root / "config.json.bak").exists())
        data["ca_tax_rate"] = 0.14
        self.assertEqual(self.save(data).status_code, 200)
        backup = json.loads((self.root / "config.json.bak").read_text(encoding="utf-8"))
        self.assertEqual(backup["ca_tax_rate"], 0.13)
        self.assertEqual(json.loads(self.config_path.read_text())["ca_tax_rate"], 0.14)

    def test_invalid_request_does_not_overwrite_existing_config(self):
        self.assertEqual(self.save(example()).status_code, 200)
        original = self.config_path.read_bytes()
        invalid = example()
        invalid["products"]["us_pro_512"]["price"] = -10
        response = self.save(invalid)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.config_path.read_bytes(), original)

    def test_wizard_rejects_cross_origin_writes(self):
        response = self.save(example(), headers={"Origin": "https://malicious.example"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.config_path.exists())

    def test_wizard_rejects_missing_csrf_token(self):
        response = self.save(example(), token=False)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.config_path.exists())

    def test_wizard_rejects_remote_ip_and_host_header(self):
        self.assertEqual(self.client.get("/", environ_overrides={"REMOTE_ADDR": "192.0.2.5"}).status_code, 403)
        self.assertEqual(self.client.get("/", headers={"Host": "malicious.example"}).status_code, 403)

    def test_invalid_product_id_and_wrong_currency(self):
        data = example()
        data["products"]["?invalid"] = data["products"].pop("us_pro_512")
        with self.assertRaises(InvalidConfig):
            validate_config(data)
        data = example()
        data["products"]["us_pro_512"]["currency"] = "CAD"
        with self.assertRaises(InvalidConfig):
            validate_config(data)

    def test_rejects_unknown_alert_product(self):
        data = example()
        data["alert_product_ids"] = ["missing_product"]
        with self.assertRaises(InvalidConfig):
            validate_config(data)

    def test_empty_alert_list_is_valid_and_disables_notifications(self):
        data = example()
        data["alert_store_ids"] = []
        data["alert_product_ids"] = []
        clean = validate_config(data)
        self.assertEqual(clean["alert_store_ids"], [])
        self.assertEqual(clean["alert_product_ids"], [])

    def test_bad_zip_and_nonfinite_tax_are_invalid(self):
        data = example()
        data["search_zips"] = {"DELAWARE": "bad"}
        with self.assertRaises(InvalidConfig):
            validate_config(data)
        data = example()
        data["ca_tax_rate"] = float("nan")
        with self.assertRaises(InvalidConfig):
            validate_config(data)


if __name__ == "__main__":
    unittest.main()
