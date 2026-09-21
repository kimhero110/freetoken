"""The model list is evidence, not a verdict.

For twelve days every scheduled extraction was refused before it made a single
call, because api.deepseek.com had stopped listing deepseek-v4-flash in
/models. The model worked: on 2026-09-15 this repository's own capability
probe got HTTP 200 and a valid protocol response from the same model, at the
same provider, with the same secret, and recorded it as live.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.extract import Provider, preflight


SECRET = "sk-do-not-leak-this-0123456789"


def provider(model="deepseek-v4-flash"):
    return Provider(id="deepseek", name="DeepSeek", base_url="https://api.deepseek.com",
                    model=model, api_key=SECRET, temperature=0.1, response_format_json=True)


def listing(*ids):
    client = Mock()
    client.models.list.return_value = SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])
    return client


class PreflightTests(unittest.TestCase):
    def test_a_listed_model_is_reported_as_matching(self):
        with patch("scripts.extract.OpenAI", return_value=listing("deepseek-chat", "deepseek-v4-flash")):
            note = preflight(provider())
        self.assertTrue(note["matched"])
        self.assertIn("deepseek-v4-flash", note["listed"])

    def test_an_unlisted_model_is_recorded_rather_than_refused(self):
        with patch("scripts.extract.OpenAI", return_value=listing("deepseek-chat", "deepseek-reasoner")):
            note = preflight(provider())
        self.assertFalse(note["matched"])

    def test_the_note_names_what_was_asked_for_and_what_was_offered(self):
        # 原来的 MODEL_NOT_AVAILABLE 两样都不说，看一百遍也不知道该改成什么。
        with patch("scripts.extract.OpenAI", return_value=listing("deepseek-chat")):
            note = preflight(provider())
        self.assertEqual(note["model"], "deepseek-v4-flash")
        self.assertEqual(note["listed"], ["deepseek-chat"])
        self.assertEqual(note["provider"], "deepseek")

    def test_a_gateway_without_a_model_list_is_not_a_failure(self):
        with patch("scripts.extract.OpenAI", side_effect=RuntimeError("404")):
            note = preflight(provider())
        self.assertEqual(note["error"], "RuntimeError")
        self.assertIsNone(note["matched"])

    def test_no_credential_is_ever_placed_in_the_note(self):
        with patch("scripts.extract.OpenAI", return_value=listing("deepseek-chat")):
            note = preflight(provider())
        self.assertNotIn(SECRET, repr(note))
        self.assertNotIn("api_key", note)

    def test_a_long_list_is_truncated_so_a_summary_stays_readable(self):
        with patch("scripts.extract.OpenAI", return_value=listing(*("m%02d" % i for i in range(60)))):
            note = preflight(provider())
        self.assertEqual(len(note["listed"]), 40)


if __name__ == "__main__":
    unittest.main()
