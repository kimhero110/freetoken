import hashlib
import io
import json
import tempfile
import unittest
import yaml
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.verify_unverified import (
    classify_verification,
    main,
    needs_verification,
    select_verification_targets,
)

NULL_QUOTA = {"free_quota": {"amount": None, "unit": None, "type": None, "conditions": []}, "intro": "无免费额度"}


def platform_entry(**overrides):
    entry = {
        "slug": "demo",
        "name": "Demo",
        "status": "active",
        "last_verified": "2026-10-26",
        "free_quota": {"amount": 100, "unit": "tokens", "type": "每日"},
        "source_urls": ["https://example.com/docs"],
    }
    entry.update(overrides)
    return entry


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.platforms = Path(self.temp.name) / "platforms"
        self.platforms.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write_platform(self, slug, entry):
        (self.platforms / f"{slug}.yaml").write_text(
            yaml.safe_dump(entry, allow_unicode=True), encoding="utf-8"
        )

    def test_picks_unverified_pending_tagged_and_never_verified(self):
        self.write_platform("unverified-one", platform_entry(status="unverified"))
        self.write_platform("pending-one", platform_entry(free_quota={"amount": "待核实", "type": "待核实", "unit": "Tokens"}))
        self.write_platform("tagged-one", platform_entry(tags=["待人工复核", "OpenAI 兼容"]))
        self.write_platform("radar-one", platform_entry(tags=["雷达新源"], last_verified=None))
        self.write_platform("never-verified", platform_entry(last_verified=None))
        targets = select_verification_targets(self.platforms)
        self.assertEqual(
            [t["slug"] for t in targets],
            ["never-verified", "pending-one", "radar-one", "tagged-one", "unverified-one"],
        )
        by_slug = {t["slug"]: t for t in targets}
        self.assertIn("status:unverified", by_slug["unverified-one"]["reasons"])
        self.assertIn("free_quota:待核实", by_slug["pending-one"]["reasons"])
        self.assertIn("tag:待人工复核", by_slug["tagged-one"]["reasons"])
        self.assertIn("tag:雷达新源", by_slug["radar-one"]["reasons"])
        self.assertIn("last_verified:missing", by_slug["never-verified"]["reasons"])
        self.assertEqual(by_slug["pending-one"]["source_urls"], ["https://example.com/docs"])

    def test_skips_clean_active_verified_platform(self):
        self.write_platform("clean-one", platform_entry())
        self.assertEqual(select_verification_targets(self.platforms), [])
        self.assertFalse(needs_verification(platform_entry()))

    def test_needs_verification_any_rule(self):
        self.assertTrue(needs_verification(platform_entry(status="unverified")))
        self.assertTrue(needs_verification(platform_entry(tags=["雷达新源"])))
        self.assertTrue(needs_verification(platform_entry(free_quota={"type": "待核实"})))
        self.assertTrue(needs_verification(platform_entry(last_verified="")))


class ClassifyTests(unittest.TestCase):
    def test_positive_finite_quota_with_known_type_is_free_tier(self):
        extracted = {"free_quota": {"amount": 1000, "unit": "tokens", "type": "每日", "conditions": []}, "intro": "x"}
        self.assertEqual(classify_verification("pricing docs", extracted), "has_free_tier")

    def test_positive_quota_without_known_type_stays_unclear(self):
        extracted = {"free_quota": {"amount": 1000, "unit": None, "type": "促销", "conditions": []}, "intro": "x"}
        self.assertEqual(classify_verification("pricing docs", extracted), "unclear")

    def test_null_quota_without_hints_is_no_free_tier(self):
        self.assertEqual(classify_verification("pay as you go pricing", NULL_QUOTA), "no_free_tier")

    def test_null_quota_next_to_free_hints_is_unclear(self):
        for text in (
            "Sign up to get a free tier for new users",
            "我们提供 免费额度 与免费试用",
            "新用户注册即赠送 credits",
            "includes a complimentary allowance",
            "trial credit for 14 days",
            "free tokens every day",
            "FREE CREDIT on signup",
        ):
            with self.subTest(text=text):
                self.assertEqual(classify_verification(text, NULL_QUOTA), "unclear")

    def test_fetch_failure_is_unclear(self):
        extracted = {"free_quota": {"amount": 100, "unit": "tokens", "type": "永久", "conditions": []}, "intro": "x"}
        self.assertEqual(classify_verification(None, extracted), "unclear")
        self.assertEqual(classify_verification("", extracted), "unclear")
        self.assertEqual(classify_verification("   \n ", extracted), "unclear")

    def test_invalid_extraction_is_unclear(self):
        self.assertEqual(classify_verification("docs", None), "unclear")
        self.assertEqual(classify_verification("docs", {"free_quota": "nope"}), "unclear")
        self.assertEqual(classify_verification("docs", {"intro": ""}), "unclear")

    def test_zero_amount_is_unclear(self):
        extracted = {"free_quota": {"amount": 0, "unit": None, "type": "每日", "conditions": []}, "intro": "x"}
        self.assertEqual(classify_verification("docs", extracted), "unclear")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.platforms = root / "platforms"
        self.candidates = root / "candidates"
        self.work = root / "work"
        self.platforms.mkdir()
        self.candidates.mkdir()
        self.candidates.mkdir(exist_ok=True)
        entry = platform_entry(
            slug="demo",
            status="unverified",
            last_verified=None,
            free_quota={"amount": "待核实", "type": "待核实"},
            source_urls=["https://example.com/docs"],
        )
        (self.platforms / "demo.yaml").write_text(
            yaml.safe_dump(entry, allow_unicode=True), encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def base_args(self):
        return [
            "--platforms-dir", str(self.platforms),
            "--candidates-dir", str(self.candidates),
            "--input-dir", str(self.work),
            "--output-dir", str(self.work),
        ]

    def summary(self):
        return json.loads((self.work / "verify-summary.json").read_text(encoding="utf-8"))

    def test_list_only_returns_json_without_network(self):
        def boom(url):
            raise AssertionError("network must not be called in --list-only")
        with patch("scripts.verify_unverified.fetch_text", side_effect=boom):
            code, output = self.run_cli(["--list-only"] + self.base_args())
        self.assertEqual(code, 0)
        targets = json.loads(output)
        self.assertEqual([t["slug"] for t in targets], ["demo"])
        self.assertEqual(targets[0]["source_urls"], ["https://example.com/docs"])
        self.assertFalse(self.work.exists())

    def test_unclear_never_writes_candidate_file(self):
        with patch("scripts.verify_unverified.fetch_text", return_value="some pricing page without hints"), \
                patch.dict("os.environ", {}, clear=True):
            code, _ = self.run_cli(self.base_args())
        self.assertEqual(code, 0)
        self.assertEqual(list(self.candidates.glob("*.yaml")), [])
        summary = self.summary()
        self.assertEqual(summary["counts"], {"has_free_tier": 0, "no_free_tier": 0, "unclear": 1})
        self.assertEqual(summary["platforms"][0]["conclusion"], "unclear")
        self.assertIn("needs_extract", summary["platforms"][0]["reasons"])

    def test_no_free_tier_with_existing_pending_candidate_is_in_summary(self):
        candidate = {
            "candidate_type": "platform_update",
            "status": "pending_review",
            "platform_slug": "demo",
            "source_url": "https://example.com/docs",
            "source_hash": hashlib.sha256(b"x").hexdigest(),
            "captured_at": "2026-10-26T00:00:00+00:00",
            "proposed": NULL_QUOTA,
        }
        (self.candidates / "update-demo-aaaaaaaaaaaa.yaml").write_text(
            yaml.safe_dump(candidate, allow_unicode=True), encoding="utf-8"
        )
        text = "transparent pay as you go api pricing"
        with patch("scripts.verify_unverified.fetch_text", return_value=text), \
                patch.dict("os.environ", {}, clear=True):
            code, _ = self.run_cli(self.base_args())
        self.assertEqual(code, 0)
        summary = self.summary()
        self.assertEqual(summary["counts"]["no_free_tier"], 1)
        record = summary["platforms"][0]
        self.assertEqual(record["conclusion"], "no_free_tier")
        self.assertEqual(record["sources"][0]["candidate"], "update-demo-aaaaaaaaaaaa")
        annotated = yaml.safe_load((self.candidates / "update-demo-aaaaaaaaaaaa.yaml").read_text(encoding="utf-8"))
        self.assertEqual(annotated["verification_conclusion"], "no_free_tier")

    def test_free_hints_next_to_null_quota_stays_unclear(self):
        candidate = {
            "candidate_type": "platform_update",
            "status": "pending_review",
            "platform_slug": "demo",
            "source_url": "https://example.com/docs",
            "source_hash": hashlib.sha256(b"x").hexdigest(),
            "captured_at": "2026-10-26T00:00:00+00:00",
            "proposed": NULL_QUOTA,
        }
        (self.candidates / "update-demo-bbbbbbbbbbbb.yaml").write_text(
            yaml.safe_dump(candidate, allow_unicode=True), encoding="utf-8"
        )
        with patch("scripts.verify_unverified.fetch_text", return_value="everyone gets a free tier on signup"), \
                patch.dict("os.environ", {}, clear=True):
            code, _ = self.run_cli(self.base_args())
        self.assertEqual(code, 0)
        summary = self.summary()
        self.assertEqual(summary["counts"]["unclear"], 1)
        self.assertIn("free_tier_hints_present", summary["platforms"][0]["reasons"])

    def test_fetch_failure_is_unclear_and_never_extract_queued(self):
        with patch("scripts.verify_unverified.fetch_text", return_value=None), \
                patch.dict("os.environ", {"CHECK_PAID_ENABLED": "true"}, clear=True):
            code, _ = self.run_cli(self.base_args())
        self.assertEqual(code, 0)
        summary = self.summary()
        self.assertEqual(summary["counts"]["unclear"], 1)
        self.assertIn("fetch_failed", summary["platforms"][0]["reasons"])
        self.assertEqual(summary["extract_needed"], 0)
        self.assertFalse((self.work / "changed.json").exists())

    def test_paid_path_queues_forced_changed_and_finalize_classifies(self):
        env = {"CHECK_PAID_ENABLED": "true"}
        text = "transparent pay as you go api pricing"
        with patch("scripts.verify_unverified.fetch_text", return_value=text), \
                patch.dict("os.environ", env, clear=True):
            code, _ = self.run_cli(self.base_args())
        self.assertEqual(code, 0)
        changed = json.loads((self.work / "changed.json").read_text(encoding="utf-8"))
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["platform"], "demo")
        self.assertEqual(changed[0]["hash"], hashlib.sha256(text.encode("utf-8")).hexdigest())
        self.assertEqual(changed[0]["text"], text)

        # extract.py would write a candidate for the queued source; finalize then
        # classifies from the cached source text without another fetch.
        candidate = {
            "candidate_type": "platform_update",
            "status": "pending_review",
            "platform_slug": "demo",
            "source_url": "https://example.com/docs",
            "source_hash": changed[0]["hash"],
            "captured_at": "2026-10-26T01:00:00+00:00",
            "proposed": NULL_QUOTA,
        }
        (self.candidates / "update-demo-cccccccccccc.yaml").write_text(
            yaml.safe_dump(candidate, allow_unicode=True), encoding="utf-8"
        )

        def boom(url):
            raise AssertionError("finalize must not refetch")
        with patch("scripts.verify_unverified.fetch_text", side_effect=boom), \
                patch.dict("os.environ", env, clear=True):
            code, _ = self.run_cli(["--finalize"] + self.base_args())
        self.assertEqual(code, 0)
        summary = self.summary()
        self.assertEqual(summary["mode"], "finalize")
        self.assertEqual(summary["platforms"][0]["conclusion"], "no_free_tier")
        self.assertEqual(summary["extract_needed"], 0)

    def test_skip_extract_never_queues_changed(self):
        with patch("scripts.verify_unverified.fetch_text", return_value="docs without hints"), \
                patch.dict("os.environ", {"CHECK_PAID_ENABLED": "true"}, clear=True):
            code, _ = self.run_cli(["--skip-extract"] + self.base_args())
        self.assertEqual(code, 0)
        self.assertFalse((self.work / "changed.json").exists())
        summary = self.summary()
        self.assertEqual(summary["mode"], "collect_skip_extract")
        self.assertEqual(summary["counts"]["unclear"], 1)


if __name__ == "__main__":
    unittest.main()
