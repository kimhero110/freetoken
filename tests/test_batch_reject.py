"""清积压不该按十几次按钮，否则没有人会去清。"""
import unittest
from unittest.mock import call, patch

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


if __name__ == "__main__":
    unittest.main()
