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

    def test_non_openai_platforms_cannot_advertise_chat_endpoint(self):
        platform = yaml.safe_load(
            (ROOT / "data" / "platforms" / "tavily.yaml").read_text(encoding="utf-8")
        )
        platform["capabilities"]["chat_completions_url"] = "https://example.com/chat"
        self.assertIn(
            "non-OpenAI platforms cannot declare chat_completions_url",
            validate_platform(platform, "tavily"),
        )

    def test_executable_urls_reject_shell_breakout_characters(self):
        for url in ('https://example.com/";id;#', 'https://example.com/$(id)'):
            platform = yaml.safe_load(
                (ROOT / "data" / "platforms" / "deepseek.yaml").read_text(encoding="utf-8")
            )
            platform["capabilities"]["chat_completions_url"] = url
            with self.subTest(url=url):
                self.assertIn(
                    "OpenAI-compatible platforms require chat_completions_url",
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
