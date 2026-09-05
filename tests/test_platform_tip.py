import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import platform_tip, review_candidates


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


class UpdateIntakeTests(unittest.TestCase):
    def test_generated_update_can_be_approved_and_archived(self):
        self._roundtrip()

    def test_generated_update_rejects_changed_source_and_preserves_candidate(self):
        self._roundtrip(changed_source=True)

    def _roundtrip(self, changed_source=False):
        from test_candidates import CandidateWorkflowTests
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            platforms, candidates = root / "platforms", root / "candidates"
            platforms.mkdir()
            platform = CandidateWorkflowTests.platform()
            original = yaml.safe_dump(platform)
            platform_file = platforms / "demo.yaml"
            platform_file.write_text(original, encoding="utf-8")
            source = "https://example.com/source"
            html = "<p>" + "Official quota details " * 20 + "</p>"
            for module in (platform_tip, review_candidates):
                stack.enter_context(patch.object(module, "PLATFORMS_DIR", platforms))
                stack.enter_context(patch.object(module, "CANDIDATES_DIR", candidates))
            for name, value in {"REVIEWS_DIR": root / "reviews", "LOCK_FILE": root / "review.lock",
                                "HASHES_FILE": root / "hashes.json", "GENERATED_FILES": ()}.items():
                stack.enter_context(patch.object(review_candidates, name, value))
            stack.enter_context(patch.object(platform_tip, "get_public_text", return_value=html))
            stack.enter_context(patch.object(platform_tip, "call_deepseek", return_value={
                "intro": "Updated quota", "free_quota": {"amount": 2, "unit": "tokens", "type": "每日"}}))
            stack.enter_context(patch("sys.argv", ["platform_tip.py", "--url", source, "--ticket-id", "pl-roundtrip"]))
            self.assertEqual(platform_tip.main(), 0)
            self.assertEqual(platform_file.read_text(encoding="utf-8"), original)
            candidate_file = candidates / "update-demo-pl-roundtrip.yaml"
            proposed = yaml.safe_load(candidate_file.read_text(encoding="utf-8"))
            self.assertEqual(proposed["current"]["intro"], "Old")
            self.assertEqual(len(proposed["platform_hash"]), 64)
            stack.enter_context(patch.object(review_candidates, "get_public_text", return_value=html + ("changed" if changed_source else "")))
            build = stack.enter_context(patch.object(review_candidates.subprocess, "run"))
            if changed_source:
                with self.assertRaisesRegex(ValueError, "来源页面已"):
                    review_candidates.approve_candidate(candidate_file.stem)
                self.assertTrue(candidate_file.exists())
                self.assertEqual(platform_file.read_text(encoding="utf-8"), original)
                build.assert_not_called()
            else:
                self.assertTrue(review_candidates.approve_candidate(candidate_file.stem))
                updated = yaml.safe_load(platform_file.read_text(encoding="utf-8"))
                self.assertEqual(updated["free_quota"]["amount"], 2)
                self.assertEqual(updated["intro"], "Updated quota")
                self.assertFalse(candidate_file.exists())
                self.assertTrue((root / "reviews" / f"{candidate_file.stem}-approved.yaml").exists())
                self.assertEqual(build.call_count, 2)

    def test_invalid_extraction_does_not_create_update(self):
        with tempfile.TemporaryDirectory() as directory:
            candidates = Path(directory) / "candidates"
            with patch.object(platform_tip, "CANDIDATES_DIR", candidates), patch.object(
                platform_tip, "find_match", return_value=("demo", {"source_urls": ["https://example.com/source"]}, True)
            ), patch.object(platform_tip, "get_public_text", return_value="x" * 200), patch.object(
                platform_tip, "call_deepseek", return_value={"intro": "new", "free_quota": {"amount": float("nan")}}
            ), patch("sys.argv", ["platform_tip.py", "--url", "https://example.com/source", "--ticket-id", "pl-invalid"]):
                self.assertEqual(platform_tip.main(), 4)
                self.assertFalse(candidates.exists())


if __name__ == "__main__":
    unittest.main()
