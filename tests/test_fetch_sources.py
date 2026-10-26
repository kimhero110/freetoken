import unittest
from pathlib import Path
import yaml

from scripts.fetch_sources import coverage_degraded
from scripts.source_verification import authorized_source_urls


ROOT = Path(__file__).resolve().parents[1]


class CoverageThresholdTests(unittest.TestCase):
    def test_no_attempts_is_not_degraded(self):
        self.assertFalse(coverage_degraded(0, 0))

    def test_half_success_is_not_degraded(self):
        self.assertFalse(coverage_degraded(10, 5))

    def test_just_under_half_is_degraded(self):
        self.assertTrue(coverage_degraded(10, 4))

    def test_single_total_failure_is_degraded(self):
        self.assertTrue(coverage_degraded(1, 0))

    def test_majority_success_is_not_degraded(self):
        self.assertFalse(coverage_degraded(3, 2))


class AuthorizedSourceUrlsTests(unittest.TestCase):
    def test_prefers_explicit_source_urls_when_present(self):
        entry = {
            "source_urls": ["https://example.com/pricing"],
            "evidence": [{"url": "https://example.com/docs"}],
        }
        self.assertEqual(authorized_source_urls(entry), ["https://example.com/pricing"])

    def test_falls_back_to_evidence_filtering_api_and_github_actions(self):
        entry = {
            "website": "https://example.com",
            "doc_url": "https://docs.github.com/en/github-models",
            "api_base_url": "https://api.example.com/v1",
            "capabilities": {
                "operations": [{
                    "endpoint_url": "https://gateway.example.com/chat/completions",
                }],
            },
            "evidence": [
                {"url": "https://example.com/pricing"},
                {"url": "https://docs.github.com/en/github-models"},
                {"url": "https://api-docs.deepseek.com/"},
                {"url": "https://api.example.com/v1/models"},
                {"url": "https://api.other.com/status"},
                {"url": "https://gateway.example.com/chat/completions"},
                {"url": "https://github.com/kimhero110/freetoken/actions/runs/123456"},
                {"url": "http://insecure.example.com/docs"},
            ],
        }
        self.assertEqual(
            authorized_source_urls(entry),
            [
                "https://example.com/pricing",
                "https://docs.github.com/en/github-models",
                "https://api-docs.deepseek.com/",
            ],
        )

    def test_every_canonical_platform_has_authorized_doc_sources(self):
        total = 0
        for path in sorted((ROOT / "data" / "platforms").glob("*.yaml")):
            entry = yaml.safe_load(path.read_text(encoding="utf-8"))
            urls = authorized_source_urls(entry)
            self.assertTrue(urls, f"{path.name} resolved to empty authorized_source_urls")
            for url in urls:
                self.assertNotIn("/v1/models", url)
                self.assertNotIn("/actions/runs/", url)
            total += len(urls)
        self.assertGreaterEqual(total, 49)
        self.assertLessEqual(total, 200)


if __name__ == "__main__":
    unittest.main()
