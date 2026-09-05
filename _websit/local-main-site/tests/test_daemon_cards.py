import unittest

from daemon import cards


class LarkEscapeTests(unittest.TestCase):
    def test_escapes_at_injection(self):
        malicious = '<at user_id="all">所有人</at>'
        escaped = cards.lark_escape(malicious)
        self.assertNotIn("<at", escaped)
        self.assertIn("&lt;at", escaped)

    def test_escapes_ampersand_and_brackets(self):
        self.assertEqual(cards.lark_escape("a&b<c>d"), "a&amp;b&lt;c&gt;d")

    def test_non_string_coerced(self):
        self.assertEqual(cards.lark_escape(123), "123")


class CardBuilderTests(unittest.TestCase):
    def test_candidate_card_contains_footer_and_escaped_fields(self):
        card = cards.candidate_card("#p001", "tip-x-1", "Evil<at>Co", ["+ 10 刀额度", "- 无"], ["tools=unknown"])
        content = card["card"]["elements"][0]["text"]["content"]
        self.assertIn("&lt;at&gt;", content)
        self.assertIn("#p001", content)
        self.assertIn("tip-x-1", content)
        self.assertIn("通过", content)

    def test_help_card_lists_all_commands(self):
        content = cards.help_card()["card"]["elements"][0]["text"]["content"]
        for verb in ("平台", "文章", "通过", "拒绝", "确认", "待审", "状态", "撤销", "谁我"):
            self.assertIn(verb, content)

    def test_error_card_problem_cause_fix(self):
        content = cards.error_card("失败", "原因<X>", "建议")[  "card"]["elements"][0]["text"]["content"]
        self.assertIn("原因&lt;X&gt;", content)
        self.assertIn("建议", content)

    def test_pending_list_empty_state_is_warm(self):
        card = cards.pending_list_card([])
        self.assertIn("无待审候选", card["card"]["header"]["title"]["content"])

    def test_daily_card_includes_approval_counter(self):
        content = cards.daily_card(["a", "b"], "9/10", ["r1"], 3)["card"]["elements"][0]["text"]["content"]
        self.assertIn("3 次", content)

    def test_anomaly_card_has_revoke_button(self):
        card = cards.anomaly_card("批准", "run 1")
        buttons = card["card"]["elements"][-1]["actions"]
        self.assertTrue(any("settings/personal-access-tokens" in b.get("url", "") for b in buttons))

    def test_card_json_is_serializable(self):
        payload = cards.card_json(cards.help_card())
        self.assertIsInstance(payload, str)
        self.assertIn("命令手册", payload)


if __name__ == "__main__":
    unittest.main()
