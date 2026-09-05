import unittest
import math
from pathlib import Path

import yaml

from scripts.platform_schema import validate_platform


ROOT = Path(__file__).resolve().parents[1]


class PlatformSchemaTests(unittest.TestCase):
    def test_every_platform_satisfies_the_public_data_contract(self):
        files = sorted((ROOT / "data" / "platforms").glob("*.yaml"))
        self.assertGreaterEqual(len(files), 40)
        for path in files:
            with self.subTest(platform=path.stem):
                platform = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertEqual(validate_platform(platform, path.stem), [])

    def test_openai_chat_requires_the_expected_endpoint_and_models(self):
        platform = yaml.safe_load(
            (ROOT / "data" / "platforms" / "deepseek.yaml").read_text(encoding="utf-8")
        )
        operation = platform["capabilities"]["operations"][0]
        operation["endpoint_url"] = "https://example.com/chat"
        operation["models"] = []
        errors = validate_platform(platform, "deepseek")
        self.assertIn("capabilities.operations[0] chat_completions requires models", errors)
        self.assertIn("capabilities.operations[0] OpenAI endpoint must end with /chat/completions", errors)

    def test_executable_urls_reject_shell_breakout_characters(self):
        for url in ('https://example.com/";id;#', 'https://example.com/$(id)'):
            platform = yaml.safe_load(
                (ROOT / "data" / "platforms" / "deepseek.yaml").read_text(encoding="utf-8")
            )
            platform["capabilities"]["operations"][0]["endpoint_url"] = url
            with self.subTest(url=url):
                self.assertIn(
                    "capabilities.operations[0].endpoint_url must be an HTTPS URL or null",
                    validate_platform(platform, "deepseek"),
                )

    def test_capability_objects_reject_unknown_fields(self):
        platform = yaml.safe_load(
            (ROOT / "data" / "platforms" / "deepseek.yaml").read_text(encoding="utf-8")
        )
        operation = platform["capabilities"]["operations"][0]
        platform["capabilities"]["legacy"] = True
        operation["legacy"] = True
        operation["auth"]["legacy"] = True
        operation["verification"]["legacy"] = True
        errors = validate_platform(platform, "deepseek")
        self.assertIn("capabilities contains unsupported fields: legacy", errors)
        self.assertIn("capabilities.operations[0] contains unsupported fields: legacy", errors)
        self.assertIn("capabilities.operations[0].auth contains unsupported fields: legacy", errors)
        self.assertIn("capabilities.operations[0].verification contains unsupported fields: legacy", errors)

    def test_auth_invariants_and_verification_date_are_enforced(self):
        platform = yaml.safe_load(
            (ROOT / "data" / "platforms" / "deepseek.yaml").read_text(encoding="utf-8")
        )
        operation = platform["capabilities"]["operations"][0]
        operation["auth"]["header"] = "X-Api-Key"
        operation["verification"]["checked_at"] = "2026-02-30"
        errors = validate_platform(platform, "deepseek")
        self.assertIn(
            "capabilities.operations[0].auth bearer auth requires Authorization header, env_var, and null query_param",
            errors,
        )
        self.assertIn("capabilities.operations[0].verification.checked_at must be a valid date", errors)

    def test_malformed_auth_values_return_errors_instead_of_raising(self):
        platform = yaml.safe_load(
            (ROOT / "data" / "platforms" / "deepseek.yaml").read_text(encoding="utf-8")
        )
        platform["capabilities"]["operations"][0]["auth"]["env_var"] = 123
        errors = validate_platform(platform, "deepseek")
        self.assertTrue(any("env_var" in error for error in errors))

    def test_verification_status_controls_required_provenance(self):
        platform = yaml.safe_load(
            (ROOT / "data" / "platforms" / "deepseek.yaml").read_text(encoding="utf-8")
        )
        verification = platform["capabilities"]["operations"][0]["verification"]
        verification.update({"status": "documented", "checked_at": None, "evidence_url": None})
        errors = validate_platform(platform, "deepseek")
        self.assertIn(
            "capabilities.operations[0].verification documented/live status requires checked_at and evidence_url",
            errors,
        )
        verification.update({"status": "claimed", "checked_at": "2026-09-03", "evidence_url": "https://example.com"})
        errors = validate_platform(platform, "deepseek")
        self.assertIn(
            "capabilities.operations[0].verification claimed/unknown status requires null checked_at and evidence_url",
            errors,
        )
        verification.update({"status": "failed", "checked_at": None, "evidence_url": None})
        self.assertIn(
            "capabilities.operations[0].verification failed status requires checked_at",
            validate_platform(platform, "deepseek"),
        )

    def test_quota_rejects_non_finite_numbers_and_unknown_fields(self):
        platform = yaml.safe_load(
            (ROOT / "data" / "platforms" / "deepseek.yaml").read_text(encoding="utf-8")
        )
        platform["free_quota"] = {"amount": math.inf, "unexpected": "value"}
        errors = validate_platform(platform, "deepseek")
        self.assertIn("free_quota.amount must be finite", errors)
        self.assertIn("free_quota contains unsupported fields: unexpected", errors)


if __name__ == "__main__":
    unittest.main()
