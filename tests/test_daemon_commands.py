import unittest

from daemon import commands


class CommandParsingTests(unittest.TestCase):
    def test_basic_platform_command(self):
        command = commands.parse("平台 https://example.com 送 10 刀")
        self.assertEqual(command.verb, "platform")
        self.assertEqual(command.arg, "https://example.com 送 10 刀")

    def test_fullwidth_space_and_trailing_punctuation(self):
        command = commands.parse("平台　https://example.com 。！！")
        self.assertEqual(command.verb, "platform")
        self.assertEqual(command.arg, "https://example.com")

    def test_bare_url_detected(self):
        command = commands.parse("https://example.com/promo")
        self.assertEqual(command.verb, "bare_url")

    def test_unknown_command(self):
        command = commands.parse("你好世界")
        self.assertEqual(command.verb, "unknown")

    def test_empty(self):
        self.assertEqual(commands.parse("   ").verb, "empty")
        self.assertEqual(commands.parse("").verb, "empty")

    def test_english_aliases(self):
        self.assertEqual(commands.parse("pending").verb, "pending")
        self.assertEqual(commands.parse("HELP").verb, "help")
        self.assertEqual(commands.parse("确认 123456").verb, "confirm")

    def test_url_validation(self):
        self.assertTrue(commands.validate_url("https://a.io"))
        self.assertFalse(commands.validate_url("http://a.io"))
        self.assertFalse(commands.validate_url("ftp://x"))
        self.assertFalse(commands.validate_url(""))
        self.assertFalse(commands.validate_url("https://" + "a" * 400))

    def test_candidate_id_validation(self):
        self.assertTrue(commands.validate_candidate_id("probe-deepseek-123"))
        self.assertFalse(commands.validate_candidate_id("../etc/passwd"))
        self.assertFalse(commands.validate_candidate_id("UPPER"))
        self.assertFalse(commands.validate_candidate_id("a" * 201))
        self.assertFalse(commands.validate_candidate_id(""))

    def test_short_id_parsing(self):
        self.assertEqual(commands.validate_short_id("#p042"), 42)
        self.assertEqual(commands.validate_short_id("p042"), 42)
        self.assertEqual(commands.validate_short_id("42"), 42)
        self.assertIsNone(commands.validate_short_id("#p99999"))
        self.assertIsNone(commands.validate_short_id("abc"))

    def test_confirm_code_validation(self):
        self.assertTrue(commands.validate_confirm_code("123456"))
        self.assertTrue(commands.validate_confirm_code(" 123456 "))
        self.assertFalse(commands.validate_confirm_code("12345"))
        self.assertFalse(commands.validate_confirm_code("1234567"))
        self.assertFalse(commands.validate_confirm_code("12 456"))


if __name__ == "__main__":
    unittest.main()
