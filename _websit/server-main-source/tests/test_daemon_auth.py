import unittest

from daemon import auth
from daemon.config import ConfigError, load_config


class AuthTests(unittest.TestCase):
    def test_owner_authorized(self):
        self.assertTrue(auth.is_authorized("ou_owner", "ou_owner"))

    def test_stranger_rejected_even_in_bootstrap(self):
        self.assertFalse(auth.is_authorized("ou_stranger", "ou_owner", bootstrap=True))
        self.assertFalse(auth.is_authorized("", "ou_owner"))

    def test_whoami_answered_in_bootstrap_only_for_strangers(self):
        self.assertTrue(auth.should_answer_whoami("ou_owner", "ou_owner", bootstrap=False))
        self.assertFalse(auth.should_answer_whoami("ou_stranger", "ou_owner", bootstrap=False))
        self.assertTrue(auth.should_answer_whoami("ou_stranger", "ou_owner", bootstrap=True))

    def test_redact(self):
        self.assertEqual(auth.redact_open_id("ou_1234567890abcdef"), "ou_12345")


class ConfigTests(unittest.TestCase):
    def test_missing_env_raises_with_names(self):
        with self.assertRaisesRegex(ConfigError, "FEISHU_APP_ID"):
            load_config(env={})

    def test_full_env_parses_with_defaults(self):
        config = load_config(env={
            "FEISHU_APP_ID": "cli_1", "FEISHU_APP_SECRET": "s", "OWNER_OPEN_ID": "ou_1",
            "GITHUB_PAT": "pat", "GITHUB_REPO": "kimhero110/freetoken",
        })
        self.assertEqual(config["watchdog_minutes"], 30)
        self.assertFalse(config["bootstrap"])
        self.assertEqual(config["confirm_ttl_seconds"], 300)

    def test_bootstrap_flag(self):
        config = load_config(env={
            "FEISHU_APP_ID": "a", "FEISHU_APP_SECRET": "b", "OWNER_OPEN_ID": "c",
            "GITHUB_PAT": "d", "GITHUB_REPO": "e", "BOOTSTRAP": "1",
        })
        self.assertTrue(config["bootstrap"])


if __name__ == "__main__":
    unittest.main()
