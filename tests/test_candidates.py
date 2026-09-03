import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import extract, review_candidates


class CandidateWorkflowTests(unittest.TestCase):
    @staticmethod
    def platform(slug="demo", intro="Old", amount=1):
        return {
            "schema_version": 2,
            "slug": slug,
            "name": "Demo",
            "category": "Demo",
            "intro": intro,
            "website": "https://example.com",
            "doc_url": "https://example.com/docs",
            "api_base_url": "https://api.example.com/v1",
            "free_quota": {"amount": amount, "unit": "tokens", "type": "每日", "conditions": []},
            "status": "active",
            "registration": {"url": "https://example.com/signup"},
            "requirements": {"phone": "unknown", "card": "unknown", "region": "unknown", "rpm": None, "tpm": None},
            "capabilities": {
                "operations": [],
                "tools": {
                    "curl": "unknown", "openai_python": "unknown", "openai_node": "unknown",
                    "cursor": "unknown", "openclaw": "unknown", "cherry_studio": "unknown",
                },
            },
            "evidence": [{"url": "https://example.com/source", "checked_at": "2026-09-01"}],
        }

    @classmethod
    def capability_platform(cls):
        platform = cls.platform()
        platform["capabilities"]["operations"] = [{
            "id": "chat_completions",
            "protocol": "openai",
            "endpoint_url": "https://api.example.com/v1/chat/completions",
            "models": ["demo-model"],
            "auth": {"type": "bearer", "header": "Authorization", "query_param": None, "env_var": "DEMO_API_KEY"},
            "verification": {"status": "claimed", "checked_at": None, "evidence_url": None},
        }]
        return platform

    @staticmethod
    def probe_candidate(platform, decision="live", platform_hash=None):
        endpoint = platform["capabilities"]["operations"][0]["endpoint_url"]
        import hashlib
        return {
            "candidate_type": "capability_probe",
            "candidate_version": 1,
            "platform_slug": "demo",
            "platform_hash": platform_hash or review_candidates._platform_hash(platform),
            "operation_id": "chat_completions",
            "endpoint_url": endpoint,
            "endpoint_hash": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
            "model": "demo-model",
            "observed_status_code": 200 if decision == "live" else 401,
            "latency_ms": 25,
            "protocol_valid": decision == "live",
            "decision": decision,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "evidence_url": "https://github.com/example/repository/actions/runs/123456",
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

    def test_live_probe_promotes_operation_and_only_the_probed_http_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates, platforms, cache = root / "candidates", root / "platforms", root / "cache"
            candidates.mkdir(); platforms.mkdir(); cache.mkdir()
            platform = self.capability_platform()
            platform_path = platforms / "demo.yaml"
            platform_path.write_text(yaml.safe_dump(platform), encoding="utf-8")
            candidate = candidates / "probe-demo-chat-completions.yaml"
            candidate.write_text(yaml.safe_dump(self.probe_candidate(platform)), encoding="utf-8")

            with patch.object(review_candidates, "CANDIDATES_DIR", candidates), patch.object(
                review_candidates, "PLATFORMS_DIR", platforms
            ), patch.object(review_candidates, "HASHES_FILE", cache / "hashes.json"), patch.object(
                review_candidates, "GENERATED_FILES", ()
            ), patch.object(review_candidates, "LOCK_FILE", cache / "review.lock"), patch.object(
                review_candidates, "REVIEWS_DIR", root / "reviews"
            ), patch.object(review_candidates.subprocess, "run"):
                self.assertTrue(review_candidates.approve_candidate(candidate.stem))

            updated = yaml.safe_load(platform_path.read_text(encoding="utf-8"))
            operation = updated["capabilities"]["operations"][0]
            self.assertEqual(operation["verification"]["status"], "live")
            self.assertEqual(operation["verification"]["checked_at"], datetime.now(timezone.utc).date().isoformat())
            self.assertEqual(updated["capabilities"]["tools"]["curl"], "live")
            self.assertEqual(updated["capabilities"]["tools"]["openai_python"], "unknown")
            self.assertEqual(updated["capabilities"]["tools"]["openai_node"], "unknown")
            self.assertEqual(updated["capabilities"]["tools"]["cursor"], "unknown")

    def test_stale_probe_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates, platforms, cache = root / "candidates", root / "platforms", root / "cache"
            candidates.mkdir(); platforms.mkdir(); cache.mkdir()
            platform = self.capability_platform()
            platform_path = platforms / "demo.yaml"
            platform_path.write_text(yaml.safe_dump(platform), encoding="utf-8")
            candidate = candidates / "probe-demo-chat-completions.yaml"
            candidate.write_text(yaml.safe_dump(self.probe_candidate(platform, platform_hash="a" * 64)), encoding="utf-8")

            with patch.object(review_candidates, "CANDIDATES_DIR", candidates), patch.object(
                review_candidates, "PLATFORMS_DIR", platforms
            ), patch.object(review_candidates, "HASHES_FILE", cache / "hashes.json"), patch.object(
                review_candidates, "GENERATED_FILES", ()
            ), patch.object(review_candidates, "LOCK_FILE", cache / "review.lock"), patch.object(
                review_candidates, "REVIEWS_DIR", root / "reviews"
            ):
                with self.assertRaisesRegex(ValueError, "能力探测后变更"):
                    review_candidates.approve_candidate(candidate.stem)
            self.assertEqual(yaml.safe_load(platform_path.read_text(encoding="utf-8")), platform)
            self.assertTrue(candidate.exists())

    def test_failed_probe_cannot_downgrade_and_can_be_rejected_with_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates, platforms, cache = root / "candidates", root / "platforms", root / "cache"
            candidates.mkdir(); platforms.mkdir(); cache.mkdir()
            platform = self.capability_platform()
            platform_path = platforms / "demo.yaml"
            platform_path.write_text(yaml.safe_dump(platform), encoding="utf-8")
            candidate = candidates / "probe-demo-chat-completions.yaml"
            candidate.write_text(yaml.safe_dump(self.probe_candidate(platform, decision="failed")), encoding="utf-8")

            patches = (
                patch.object(review_candidates, "CANDIDATES_DIR", candidates),
                patch.object(review_candidates, "PLATFORMS_DIR", platforms),
                patch.object(review_candidates, "HASHES_FILE", cache / "hashes.json"),
                patch.object(review_candidates, "GENERATED_FILES", ()),
                patch.object(review_candidates, "LOCK_FILE", cache / "review.lock"),
                patch.object(review_candidates, "REVIEWS_DIR", root / "reviews"),
            )
            for item in patches:
                item.start()
            try:
                with self.assertRaisesRegex(ValueError, "只能拒绝并归档"):
                    review_candidates.approve_candidate(candidate.stem)
                self.assertEqual(yaml.safe_load(platform_path.read_text(encoding="utf-8")), platform)
                self.assertTrue(review_candidates.reject_candidate(candidate.stem))
            finally:
                for item in reversed(patches):
                    item.stop()
            audit = yaml.safe_load((root / "reviews" / "probe-demo-chat-completions-rejected.yaml").read_text(encoding="utf-8"))
            self.assertEqual(audit["review"]["decision"], "rejected")


if __name__ == "__main__":
    unittest.main()
