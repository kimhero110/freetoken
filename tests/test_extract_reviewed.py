import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import extract


URL = "https://example.com/pricing"
TEXT = "Current official pricing terms"
SOURCE_HASH = extract.hashlib.sha256(TEXT.encode()).hexdigest()
ENTRY = {
    "name": "Demo",
    "source_urls": [URL],
    "free_quota": {
        "amount": "15 million",
        "unit": "tokens",
        "type": "one-time",
        "details": "Granted to new accounts.",
    },
    "intro": "Demo includes a real signup quota.",
}
NULL_WIPE = {
    "free_quota": {"amount": None, "unit": None, "type": None, "conditions": []},
    "intro": "Generic description",
}


class ReviewedExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.platforms = self.root / "data" / "platforms"
        self.candidates = self.root / "data" / "candidates"
        self.reviews = self.root / "data" / "reviews"
        self.run_dir = self.root / "run"
        for path in (self.platforms, self.candidates, self.reviews, self.run_dir):
            path.mkdir(parents=True)
        (self.platforms / "demo.yaml").write_text(
            yaml.safe_dump(ENTRY, allow_unicode=True), encoding="utf-8"
        )
        (self.run_dir / "changed.json").write_text(json.dumps([{
            "platform": "demo", "url": URL, "hash": SOURCE_HASH, "text": TEXT,
        }]), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def write_review(self, decision, proposed):
        record = {
            "candidate_type": "platform_update",
            "status": "pending_review",
            "platform_slug": "demo",
            "source_url": URL,
            "source_hash": SOURCE_HASH,
            "proposed": proposed,
            "review": {"decision": decision, "reviewed_at": "2026-10-26T01:00:00+00:00"},
        }
        (self.reviews / f"demo-{decision}.yaml").write_text(
            yaml.safe_dump(record, allow_unicode=True), encoding="utf-8"
        )

    def run_extract(self, paid_result=None, execute_result=None):
        provider = extract.Provider(
            id="test", name="Test", base_url="https://example.invalid",
            model="test-model", api_key="test-key",
        )
        argv = ["extract", "--provider", "test", "--input-dir", str(self.run_dir)]
        env = {
            "CHECK_PAID_ENABLED": "true",
            "CHECK_MAX_CALLS": "4",
            "CHECK_MAX_OUTPUT_TOKENS": "1024",
        }
        paid_side_effect = paid_result or (lambda *args, **kwargs: kwargs["request"]())
        with patch.object(extract, "ROOT", self.root), \
             patch.object(extract, "PLATFORMS_DIR", self.platforms), \
             patch.object(extract, "CANDIDATES_DIR", self.candidates), \
             patch.object(sys, "argv", argv), \
             patch.dict(os.environ, env), \
             patch("scripts.check_state.GitState"), \
             patch.object(extract, "resolve_providers", return_value={"test": provider}), \
             patch.object(extract, "preflight", return_value={"matched": True}), \
             patch.object(extract, "is_beijing_off_peak", return_value=True), \
             patch.object(extract, "execute_llm_call", return_value=execute_result) as llm, \
             patch("scripts.check_runner.paid_result", side_effect=paid_side_effect) as paid:
            code = extract.main()
        summary = json.loads((self.run_dir / "extract-summary.json").read_text())
        return code, summary, paid, llm

    def test_approved_matching_review_skips_without_an_llm_call(self):
        self.write_review("approved", {
            "free_quota": ENTRY["free_quota"], "intro": ENTRY["intro"],
        })
        code, summary, paid, llm = self.run_extract()
        self.assertEqual(code, 0)
        self.assertEqual(summary["sources"][0]["status"], "verified_unchanged")
        paid.assert_not_called()
        llm.assert_not_called()

    def test_rejected_null_wipe_creates_keep_current_renewal_without_llm(self):
        self.write_review("rejected", NULL_WIPE)
        code, summary, paid, llm = self.run_extract()
        self.assertEqual(code, 0)
        self.assertEqual(summary["sources"][0]["status"], "candidate_ready")
        candidate = yaml.safe_load(next(self.candidates.glob("*.yaml")).read_text())
        self.assertEqual(candidate["proposed"], {
            "free_quota": ENTRY["free_quota"], "intro": ENTRY["intro"],
        })
        self.assertEqual(candidate["verification_conclusion"], "renew_keep_current")
        paid.assert_not_called()
        llm.assert_not_called()

    def test_existing_pending_renewal_is_not_duplicated(self):
        self.write_review("rejected", NULL_WIPE)
        existing = extract.build_update_candidate(
            ENTRY, "demo", URL, SOURCE_HASH, "",
            {"free_quota": ENTRY["free_quota"], "intro": ENTRY["intro"]},
            {"type": "reviewed_rejection_renewal"},
        )
        existing["verification_conclusion"] = "renew_keep_current"
        held = self.candidates / f"update-demo-{SOURCE_HASH[:12]}.yaml"
        held.write_text(yaml.safe_dump(existing), encoding="utf-8")
        code, summary, paid, llm = self.run_extract()
        self.assertEqual(code, 0)
        self.assertEqual(summary["sources"][0]["status"], "pending_review")
        self.assertEqual(summary["sources"][0]["superseded_by"], held.stem)
        self.assertEqual(list(self.candidates.glob("*.yaml")), [held])
        paid.assert_not_called()
        llm.assert_not_called()

    def test_other_rejection_proceeds_to_extraction(self):
        proposed = {
            "free_quota": {"amount": 5, "unit": "credits", "type": "永久", "conditions": []},
            "intro": "A different rejected proposal",
        }
        extracted = {
            "free_quota": {"amount": 8, "unit": "credits", "type": "永久", "conditions": []},
            "intro": "Fresh extraction",
        }
        self.write_review("rejected", proposed)
        code, summary, paid, llm = self.run_extract(execute_result=extracted)
        self.assertEqual(code, 0)
        self.assertEqual(summary["sources"][0]["status"], "candidate_ready")
        paid.assert_called_once()
        llm.assert_called_once()


if __name__ == "__main__":
    unittest.main()
