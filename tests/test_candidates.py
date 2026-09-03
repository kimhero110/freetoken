import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import extract, review_candidates


class CandidateWorkflowTests(unittest.TestCase):
    @staticmethod
    def platform(slug="demo", intro="Old", amount=1):
        return {
            "slug": slug,
            "name": "Demo",
            "intro": intro,
            "website": "https://example.com",
            "doc_url": "https://example.com/docs",
            "api_base_url": "https://api.example.com/v1",
            "free_quota": {"amount": amount, "unit": "tokens", "type": "每日", "conditions": []},
            "status": "active",
            "registration": {"url": "https://example.com/signup"},
            "requirements": {"phone": "unknown", "card": "unknown", "region": "unknown", "rpm": None, "tpm": None},
            "capabilities": {"protocol": "custom", "supports_claude_code": False, "api_key_required": True},
            "evidence": [{"url": "https://example.com/source", "checked_at": "2026-09-01"}],
        }

    def test_extraction_writes_auditable_candidate_without_mutating_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            platforms = root / "platforms"
            candidates = root / "candidates"
            platforms.mkdir()
            original = {
                "slug": "demo",
                "name": "Demo",
                "intro": "Old",
                "free_quota": {"amount": 1},
            }
            platform_path = platforms / "demo.yaml"
            platform_path.write_text(yaml.safe_dump(original), encoding="utf-8")
            source_hash = "a" * 64
            provider = extract.Provider("test", "Test", "https://example.com", "model", "key")

            with patch.object(extract, "PLATFORMS_DIR", platforms), patch.object(
                extract, "CANDIDATES_DIR", candidates
            ):
                output = extract.write_update_candidate(
                    "demo",
                    "https://example.com/source",
                    source_hash,
                    "Official source excerpt",
                    {"intro": "New", "free_quota": {"amount": 2}},
                    provider,
                )

            self.assertEqual(yaml.safe_load(platform_path.read_text()), original)
            proposal = yaml.safe_load(output.read_text(encoding="utf-8"))
            self.assertEqual(proposal["current"]["intro"], "Old")
            self.assertEqual(proposal["proposed"]["intro"], "New")
            self.assertEqual(proposal["source_hash"], source_hash)
            self.assertEqual(proposal["platform_hash"], review_candidates._platform_hash(original))

    def test_llm_json_rejects_non_finite_numbers(self):
        self.assertIsNone(extract.parse_json_safely('{"amount": NaN}'))
        self.assertIsNone(extract.validate_extracted({
            "intro": "Unsafe",
            "free_quota": {"amount": float("inf"), "unit": "tokens", "type": "每日"},
        }))

    def test_failed_approval_restores_platform_and_hash_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates"
            platforms = root / "platforms"
            cache = root / "cache"
            candidates.mkdir()
            platforms.mkdir()
            cache.mkdir()
            platform_path = platforms / "demo.yaml"
            original_platform = self.platform()
            platform_path.write_text(yaml.safe_dump(original_platform), encoding="utf-8")
            platform_hash = review_candidates._platform_hash(original_platform)
            hashes_path = cache / "hashes.json"
            hashes_path.write_text(json.dumps({"old": "hash"}), encoding="utf-8")
            candidate_path = candidates / "update-demo-aaaaaaaaaaaa.yaml"
            candidate_path.write_text(
                yaml.safe_dump(
                    {
                        "candidate_type": "platform_update",
                        "platform_slug": "demo",
                        "source_url": "https://example.com/source",
                        "source_hash": "a" * 64,
                        "platform_hash": platform_hash,
                        "current": {"intro": "Old", "free_quota": original_platform["free_quota"]},
                        "proposed": {"intro": "New", "free_quota": {"amount": 2}},
                    }
                ),
                encoding="utf-8",
            )

            failure = subprocess.CalledProcessError(1, "compile")
            generated = (root / "platforms.json", root / "site-platforms.json", root / "sitemap.xml")
            for path in generated:
                path.write_text("before", encoding="utf-8")
            with patch.object(review_candidates, "CANDIDATES_DIR", candidates), patch.object(
                review_candidates, "PLATFORMS_DIR", platforms
            ), patch.object(review_candidates, "HASHES_FILE", hashes_path), patch.object(
                review_candidates, "GENERATED_FILES", generated
            ), patch.object(review_candidates, "LOCK_FILE", cache / "review.lock"), patch.object(
                review_candidates, "REVIEWS_DIR", root / "reviews"
            ), patch.object(review_candidates, "_source_hash", return_value="a" * 64), patch.object(
                review_candidates.subprocess, "run", side_effect=failure
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    review_candidates.approve_candidate(candidate_path.stem)

            self.assertEqual(yaml.safe_load(platform_path.read_text()), original_platform)
            self.assertEqual(json.loads(hashes_path.read_text()), {"old": "hash"})
            self.assertTrue(candidate_path.exists())
            self.assertTrue(all(path.read_text(encoding="utf-8") == "before" for path in generated))

    def test_new_platform_candidate_can_be_approved_and_archived(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates"
            platforms = root / "platforms"
            cache = root / "cache"
            candidates.mkdir()
            platforms.mkdir()
            cache.mkdir()
            candidate = candidates / "demo.yaml"
            candidate.write_text(yaml.safe_dump({
                "candidate_type": "new_platform",
                "status": "pending_review",
                "platform_slug": "demo",
                "proposed": self.platform(),
            }), encoding="utf-8")

            with patch.object(review_candidates, "CANDIDATES_DIR", candidates), patch.object(
                review_candidates, "PLATFORMS_DIR", platforms
            ), patch.object(review_candidates, "HASHES_FILE", cache / "hashes.json"), patch.object(
                review_candidates, "GENERATED_FILES", ()
            ), patch.object(review_candidates, "LOCK_FILE", cache / "review.lock"), patch.object(
                review_candidates, "REVIEWS_DIR", root / "reviews"
            ), patch.object(review_candidates.subprocess, "run"):
                self.assertTrue(review_candidates.approve_candidate("demo"))

            self.assertFalse(candidate.exists())
            self.assertTrue((platforms / "demo.yaml").exists())
            audit = yaml.safe_load((root / "reviews" / "demo-approved.yaml").read_text(encoding="utf-8"))
            self.assertEqual(audit["review"]["decision"], "approved")

    def test_stale_update_candidate_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates"
            platforms = root / "platforms"
            cache = root / "cache"
            candidates.mkdir()
            platforms.mkdir()
            cache.mkdir()
            platform = self.platform(intro="Changed after extraction")
            (platforms / "demo.yaml").write_text(yaml.safe_dump(platform), encoding="utf-8")
            platform_hash = review_candidates._platform_hash(platform)
            candidate = candidates / "update-demo-aaaaaaaaaaaa.yaml"
            candidate.write_text(yaml.safe_dump({
                "candidate_type": "platform_update",
                "platform_slug": "demo",
                "source_url": "https://example.com/source",
                "source_hash": "a" * 64,
                "platform_hash": platform_hash,
                "current": {"intro": "Old", "free_quota": platform["free_quota"]},
                "proposed": {"intro": "New", "free_quota": {"amount": 2}},
            }), encoding="utf-8")

            with patch.object(review_candidates, "CANDIDATES_DIR", candidates), patch.object(
                review_candidates, "PLATFORMS_DIR", platforms
            ), patch.object(review_candidates, "HASHES_FILE", cache / "hashes.json"), patch.object(
                review_candidates, "GENERATED_FILES", ()
            ), patch.object(review_candidates, "LOCK_FILE", cache / "review.lock"), patch.object(
                review_candidates, "REVIEWS_DIR", root / "reviews"
            ), patch.object(review_candidates, "_source_hash", return_value="a" * 64):
                with self.assertRaisesRegex(ValueError, "正式数据已在候选生成后变更"):
                    review_candidates.approve_candidate(candidate.stem)


if __name__ == "__main__":
    unittest.main()
