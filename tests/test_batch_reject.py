"""清积压不该按十几次按钮，否则没有人会去清。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import review_candidates


class BatchRejectTests(unittest.TestCase):
    def reject(self, text, results=None):
        outcomes = list(results or [])

        def one(item):
            return outcomes.pop(0) if outcomes else True
        with patch.object(review_candidates, "reject_candidate", side_effect=one) as rejected:
            ok = review_candidates.reject_many(text)
        return ok, [c.args[0] for c in rejected.call_args_list]

    def test_one_id_still_works(self):
        ok, called = self.reject("update-chutes-ai-42ea1a3529c8")
        self.assertTrue(ok)
        self.assertEqual(called, ["update-chutes-ai-42ea1a3529c8"])

    def test_a_comma_separated_list_is_processed_in_order(self):
        ok, called = self.reject("update-a, update-b ,update-c")
        self.assertTrue(ok)
        self.assertEqual(called, ["update-a", "update-b", "update-c"])

    def test_a_repeated_id_is_only_attempted_once(self):
        _, called = self.reject("update-a,update-a")
        self.assertEqual(called, ["update-a"])

    def test_one_bad_id_does_not_abandon_the_rest(self):
        # 前面已经归档的不会因为后面一条打错而回滚，所以停下来没有好处。
        ok, called = self.reject("update-a,update-bad,update-c", results=[True, False, True])
        self.assertFalse(ok)
        self.assertEqual(called, ["update-a", "update-bad", "update-c"])

    def test_an_empty_list_is_refused(self):
        ok, called = self.reject("  , ,")
        self.assertFalse(ok)
        self.assertEqual(called, [])


class ApproveStaysSingleTests(unittest.TestCase):
    def test_approving_a_list_is_refused(self):
        # 批准会改正式数据并触发构建与发布，一次一条人才看得住。
        with patch.object(review_candidates, "approve_candidate") as approved, \
             patch("sys.argv", ["review_candidates.py", "--approve", "update-a,update-b"]):
            code = review_candidates.main()
        approved.assert_not_called()
        self.assertEqual(code, 2)

    def test_approving_one_is_unchanged(self):
        with patch.object(review_candidates, "approve_candidate", return_value=True) as approved, \
             patch("sys.argv", ["review_candidates.py", "--approve", "update-a"]):
            code = review_candidates.main()
        approved.assert_called_once_with("update-a")
        self.assertEqual(code, 0)


class RepeatRejectionTests(unittest.TestCase):
    """Re-rejecting a candidate that already has a rejected archive must not raise.

    October review runs died on the first id because ``*-rejected.yaml`` already
    existed, so none of the later candidates in the batch were archived.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.candidates = root / "candidates"
        self.reviews = root / "reviews"
        self.cache = root / "cache"
        self.candidates.mkdir()
        self.reviews.mkdir()
        self.cache.mkdir()
        self.patches = [
            patch.object(review_candidates, "CANDIDATES_DIR", self.candidates),
            patch.object(review_candidates, "REVIEWS_DIR", self.reviews),
            patch.object(review_candidates, "LOCK_FILE", self.cache / "review.lock"),
            patch.object(review_candidates, "HASHES_FILE", self.cache / "hashes.json"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def write_candidate(self, stem, payload):
        path = self.candidates / f"{stem}.yaml"
        path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return path

    def test_identical_republish_is_removed_and_original_audit_is_kept(self):
        payload = {"candidate_type": "new_platform", "platform_slug": "aimlapi", "status": "pending_review"}
        archived = {
            **payload,
            "review": {
                "decision": "rejected",
                "reviewed_at": "2026-09-23T13:13:11.375447+00:00",
                "reviewer": "kimhero110",
            },
        }
        self.write_candidate("aimlapi", payload)
        archive = self.reviews / "aimlapi-rejected.yaml"
        archive.write_text(yaml.safe_dump(archived, allow_unicode=True, sort_keys=False), encoding="utf-8")
        original = archive.read_bytes()

        self.assertTrue(review_candidates.reject_candidate("aimlapi"))

        self.assertFalse((self.candidates / "aimlapi.yaml").exists())
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual([path.name for path in self.reviews.glob("aimlapi-rejected*.yaml")], ["aimlapi-rejected.yaml"])

    def test_changed_payload_is_archived_beside_the_original_and_a_retry_skips(self):
        original_payload = {"candidate_type": "new_platform", "platform_slug": "demo", "intro": "old"}
        revised_payload = {"candidate_type": "new_platform", "platform_slug": "demo", "intro": "new"}
        archive = self.reviews / "demo-rejected.yaml"
        archive.write_text(
            yaml.safe_dump({**original_payload, "review": {"decision": "rejected", "reviewer": "kimhero110"}}, allow_unicode=True),
            encoding="utf-8",
        )
        original = archive.read_bytes()
        self.write_candidate("demo", revised_payload)

        self.assertTrue(review_candidates.reject_candidate("demo"))

        self.assertFalse((self.candidates / "demo.yaml").exists())
        self.assertEqual(archive.read_bytes(), original)
        siblings = sorted(path.name for path in self.reviews.glob("demo-rejected*.yaml"))
        self.assertEqual(len(siblings), 2)
        extra = next(name for name in siblings if name != "demo-rejected.yaml")
        extra_record = yaml.safe_load((self.reviews / extra).read_text(encoding="utf-8"))
        self.assertEqual(extra_record["intro"], "new")
        self.assertEqual(extra_record["review"]["decision"], "rejected")

        self.write_candidate("demo", revised_payload)
        self.assertTrue(review_candidates.reject_candidate("demo"))
        self.assertFalse((self.candidates / "demo.yaml").exists())
        self.assertEqual(sorted(path.name for path in self.reviews.glob("demo-rejected*.yaml")), siblings)
        self.assertEqual(archive.read_bytes(), original)

    def test_first_duplicate_does_not_abort_the_rest_of_the_batch(self):
        payload = {"candidate_type": "new_platform", "platform_slug": "aimlapi", "status": "pending_review"}
        self.write_candidate("aimlapi", payload)
        (self.reviews / "aimlapi-rejected.yaml").write_text(
            yaml.safe_dump({**payload, "review": {"decision": "rejected", "reviewer": "kimhero110"}}, allow_unicode=True),
            encoding="utf-8",
        )
        self.write_candidate("update-featherless-ai-2c740d9a5f67", {
            "candidate_type": "new_platform",
            "platform_slug": "featherless-ai",
            "status": "pending_review",
        })

        self.assertTrue(review_candidates.reject_many(
            "aimlapi,update-featherless-ai-2c740d9a5f67"
        ))

        self.assertFalse((self.candidates / "aimlapi.yaml").exists())
        self.assertFalse((self.candidates / "update-featherless-ai-2c740d9a5f67.yaml").exists())
        archived = yaml.safe_load(
            (self.reviews / "update-featherless-ai-2c740d9a5f67-rejected.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(archived["review"]["decision"], "rejected")

    def test_duplicate_platform_update_still_records_the_source_hash(self):
        payload = {
            "candidate_type": "platform_update",
            "platform_slug": "demo",
            "source_url": "https://example.com/source",
            "source_hash": "a" * 64,
        }
        self.write_candidate("update-demo-aaaaaaaaaaaa", payload)
        (self.reviews / "update-demo-aaaaaaaaaaaa-rejected.yaml").write_text(
            yaml.safe_dump({**payload, "review": {"decision": "rejected"}}, allow_unicode=True),
            encoding="utf-8",
        )

        self.assertTrue(review_candidates.reject_candidate("update-demo-aaaaaaaaaaaa"))

        hashes = json.loads((self.cache / "hashes.json").read_text(encoding="utf-8"))
        self.assertEqual(hashes["https://example.com/source"], "a" * 64)
        self.assertFalse((self.candidates / "update-demo-aaaaaaaaaaaa.yaml").exists())

    def test_existing_approval_is_still_refused(self):
        path = self.write_candidate("demo", {"candidate_type": "new_platform", "platform_slug": "demo"})
        (self.reviews / "demo-approved.yaml").write_text("candidate_type: new_platform\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "审核记录已存在: demo-approved.yaml"):
            review_candidates._archive_candidate(path, "approved")

        self.assertTrue(path.exists())
        self.assertFalse((self.reviews / "demo-rejected.yaml").exists())

    def test_a_longer_id_is_not_the_same_rejection(self):
        payload = {"candidate_type": "new_platform", "platform_slug": "port", "status": "pending_review"}
        self.write_candidate("port", payload)
        (self.reviews / "portkey-rejected.yaml").write_text(
            yaml.safe_dump({**payload, "platform_slug": "portkey", "review": {"decision": "rejected"}}, allow_unicode=True),
            encoding="utf-8",
        )

        self.assertTrue(review_candidates.reject_candidate("port"))

        self.assertTrue((self.reviews / "port-rejected.yaml").exists())
        self.assertTrue((self.reviews / "portkey-rejected.yaml").exists())


if __name__ == "__main__":
    unittest.main()
