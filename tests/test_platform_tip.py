import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import platform_tip


class DomainTests(unittest.TestCase):
    def test_domain_of(self):
        self.assertEqual(platform_tip.domain_of("https://www.Example.com/a"), "example.com")
        self.assertEqual(platform_tip.domain_of("https://api.x.io"), "api.x.io")
        self.assertEqual(platform_tip.domain_of("not a url"), "")


class FindMatchTests(unittest.TestCase):
    def test_match_via_temp_platforms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo.yaml").write_text(yaml.safe_dump({
                "website": "https://example.com/",
                "api_base_url": "https://api.example.com",
                "source_urls": ["https://docs.example.com/pricing"],
            }), encoding="utf-8")
            with patch.object(platform_tip, "PLATFORMS_DIR", root):
                match = platform_tip.find_match("https://example.com/promo")
                self.assertIsNotNone(match)
                self.assertEqual(match[0], "demo")
                self.assertIsNone(platform_tip.find_match("https://other.io"))

    def test_note_candidate_for_existing_unauthorized_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = root / "cands"
            (root / "demo.yaml").write_text(yaml.safe_dump({"website": "https://example.com/"}), encoding="utf-8")
            with patch.object(platform_tip, "PLATFORMS_DIR", root), patch.object(
                platform_tip, "CANDIDATES_DIR", candidates
            ), patch.object(
                platform_tip, "get_public_text", return_value="<html><body>" + "x" * 200 + "</body></html>"
            ), patch("sys.argv", ["platform_tip.py", "--url", "https://example.com/flash-new", "--ticket-id", "pl-9"]):
                code = platform_tip.main()
            self.assertEqual(code, 0)
            notes = list(candidates.glob("note-demo-pl-9.yaml"))
            self.assertTrue(notes)
            data = yaml.safe_load(notes[0].read_text(encoding="utf-8"))
            self.assertEqual(data["candidate_type"], "source_note")


class BuildPlatformTests(unittest.TestCase):
    def test_build_platform_shape_and_source_url(self):
        extracted = {
            "slug": "New GPU Cloud!", "name": "新云", "category": "海外主流",
            "website": "https://newgpu.io", "free_quota": {"type": "注册赠送", "amount": 10, "unit": "USD"},
            "tags": ["GPU", "免费"],
        }
        platform = platform_tip.build_platform(extracted, "https://newgpu.io/promo", "备注")
        self.assertEqual(platform["slug"], "new-gpu-cloud")
        self.assertEqual(platform["schema_version"], 2)
        self.assertEqual(platform["source_urls"], ["https://newgpu.io/promo"])
        self.assertEqual(platform["evidence"][0]["url"], "https://newgpu.io/promo")
        self.assertEqual(platform["capabilities"]["tools"]["curl"], "unknown")
        self.assertEqual(platform["capabilities"]["operations"], [])
        self.assertEqual(platform["note"], "备注")

    def test_slug_fallback_from_url_when_llm_garbage(self):
        platform = platform_tip.build_platform({"slug": ""}, "https://fallback.example.com/x", "")
        self.assertEqual(platform["slug"], "fallback")

    def test_new_platform_candidate_with_slug_conflict_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = root / "cands"
            (root / "taken.yaml").write_text(yaml.safe_dump({"slug": "taken"}), encoding="utf-8")
            with patch.object(platform_tip, "PLATFORMS_DIR", root), patch.object(
                platform_tip, "CANDIDATES_DIR", candidates
            ), patch.object(
                platform_tip, "call_deepseek",
                return_value={"slug": "taken", "name": "T", "free_quota": {"amount": 1}, "tags": ["x"]},
            ), patch.object(
                platform_tip, "get_public_text", return_value="<html><body>" + "x" * 200 + "</body></html>"
            ), patch("sys.argv", ["platform_tip.py", "--url", "https://newthing.io/a", "--ticket-id", "pl-1"]):
                code = platform_tip.main()
            self.assertEqual(code, 0)
            self.assertTrue(list(candidates.glob("tip-taken-2-pl-1.yaml")))

    def test_invalid_url_rejected_before_any_work(self):
        with patch("sys.argv", ["platform_tip.py", "--url", "http://insecure.io", "--ticket-id", "pl-2"]):
            self.assertEqual(platform_tip.main(), 2)


if __name__ == "__main__":
    unittest.main()
