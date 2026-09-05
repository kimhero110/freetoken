import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import probe_capabilities
from scripts.safe_http import PinnedResponse


class ProbeCapabilityTests(unittest.TestCase):
    def _platform(self, slug="deepseek", env_var="DEEPSEEK_API_KEY"):
        return {
            "schema_version": 2,
            "slug": slug,
            "name": "DeepSeek",
            "category": "Demo",
            "intro": "Demo",
            "website": "https://example.com",
            "doc_url": "https://example.com/docs",
            "api_base_url": "https://api.deepseek.com",
            "free_models": ["deepseek-v4-flash"],
            "free_quota": {"amount": 1, "unit": "tokens", "type": "trial", "conditions": []},
            "status": "active",
            "registration": {"url": "https://example.com/signup"},
            "requirements": {"phone": "unknown", "card": "unknown", "region": "unknown", "rpm": None, "tpm": None},
            "capabilities": {
                "operations": [{
                    "id": "chat_completions",
                    "protocol": "openai",
                    "endpoint_url": "https://api.deepseek.com/chat/completions",
                    "models": ["deepseek-v4-flash"],
                    "auth": {"type": "bearer", "header": "Authorization", "query_param": None, "env_var": env_var},
                    "verification": {"status": "claimed", "checked_at": None, "evidence_url": None},
                }],
                "tools": {tool: "unknown" for tool in ("curl", "openai_python", "openai_node", "cursor", "openclaw", "cherry_studio")},
            },
            "evidence": [{"url": "https://example.com/docs"}],
        }

    def test_success_writes_only_a_safe_protocol_observation(self):
        secret = "probe-secret-must-not-leak"
        provider_body = b'{"choices":[{"message":{"role":"assistant","content":"private response"}}]}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            platforms = root / "platforms"
            candidates = root / "candidates"
            platforms.mkdir()
            (platforms / "deepseek.yaml").write_text(yaml.safe_dump(self._platform()), encoding="utf-8")
            captured = {}

            def request(url, **kwargs):
                captured["calls"] = captured.get("calls", 0) + 1
                captured.update({"url": url, **kwargs})
                return PinnedResponse(200, {"content-type": "application/json"}, provider_body)

            output = io.StringIO()
            with patch.object(probe_capabilities, "PLATFORMS_DIR", platforms), patch.object(
                probe_capabilities, "CANDIDATES_DIR", candidates
            ), patch.object(probe_capabilities, "pinned_public_https_request", side_effect=request), patch.dict(os.environ, {
                 "DEEPSEEK_API_KEY": secret,
                 "GITHUB_SERVER_URL": "https://github.com",
                 "GITHUB_REPOSITORY": "example/repository",
                 "GITHUB_RUN_ID": "123456",
            }, clear=True), contextlib.redirect_stdout(output):
                success, candidate_path = probe_capabilities.probe("deepseek", "chat_completions", "raw_http")

            self.assertTrue(success)
            candidate_text = candidate_path.read_text(encoding="utf-8")
            candidate = yaml.safe_load(candidate_text)
            self.assertEqual(candidate["decision"], "live")
            self.assertEqual(candidate["tool"], "raw_http")
            self.assertEqual(candidate["promotion_target"], "curl")
            self.assertTrue(candidate["protocol_valid"])
            self.assertEqual(candidate["observed_status_code"], 200)
            self.assertEqual(candidate["evidence_url"], "https://github.com/example/repository/actions/runs/123456")
            self.assertEqual(json.loads(captured["body"])["max_tokens"], 16)
            self.assertFalse(json.loads(captured["body"])["stream"])
            self.assertEqual(captured["calls"], 1)
            self.assertNotIn(secret, candidate_text + output.getvalue())
            self.assertNotIn("private response", candidate_text + output.getvalue())
            self.assertNotIn(probe_capabilities.FIXED_MESSAGE, candidate_text + output.getvalue())

    def test_missing_secret_writes_failed_candidate_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            platforms = root / "platforms"
            candidates = root / "candidates"
            platforms.mkdir()
            (platforms / "deepseek.yaml").write_text(yaml.safe_dump(self._platform()), encoding="utf-8")
            with patch.object(probe_capabilities, "PLATFORMS_DIR", platforms), patch.object(
                probe_capabilities, "CANDIDATES_DIR", candidates
            ), patch.object(probe_capabilities, "pinned_public_https_request") as request, patch.dict(
                os.environ, {}, clear=True
            ):
                success, path = probe_capabilities.probe("deepseek", "chat_completions", "raw_http")
            self.assertFalse(success)
            request.assert_not_called()
            candidate = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(candidate["decision"], "failed")
            self.assertIsNone(candidate["observed_status_code"])

    def test_protocol_response_requires_non_empty_assistant_content(self):
        self.assertFalse(probe_capabilities._protocol_valid({"choices": [{"message": {}}]}))
        self.assertFalse(probe_capabilities._protocol_valid({"choices": [{"message": {"role": "assistant", "content": ""}}]}))

    def test_all_configured_skips_missing_credentials_and_probes_each_configured_once(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "one",
            "GROQ_API_KEY": "two",
        }, clear=True), patch.object(probe_capabilities, "probe", return_value=(True, Path("candidate.yaml"))) as probe:
            result = probe_capabilities.probe_all_configured("chat_completions", ("raw_http",))

        self.assertEqual(result, 0)
        self.assertEqual(
            [call.args for call in probe.call_args_list],
            [("deepseek", "chat_completions", "raw_http"), ("groq", "chat_completions", "raw_http")],
        )

    def test_all_configured_errors_without_naming_secrets_when_none_are_configured(self):
        stderr = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(stderr):
            result = probe_capabilities.probe_all_configured("chat_completions", ("raw_http",))
        self.assertEqual(result, 2)
        self.assertNotIn("API_KEY", stderr.getvalue())

    def test_all_configured_retains_all_candidates_and_fails_on_mixed_results(self):
        results = [(True, Path("first.yaml")), (False, Path("second.yaml"))]
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "one",
            "GROQ_API_KEY": "two",
        }, clear=True), patch.object(probe_capabilities, "probe", side_effect=results) as probe:
            result = probe_capabilities.probe_all_configured("chat_completions", ("raw_http",))
        self.assertEqual(result, 1)
        self.assertEqual(probe.call_count, 2)

    def test_fixed_credential_mapping_rejects_canonical_secret_name_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            platforms = Path(directory)
            (platforms / "deepseek.yaml").write_text(
                yaml.safe_dump(self._platform(env_var="ATTACKER_CHOSEN_SECRET")), encoding="utf-8"
            )
            with patch.object(probe_capabilities, "PLATFORMS_DIR", platforms):
                with self.assertRaisesRegex(ValueError, "fixed probe configuration"):
                    probe_capabilities._load_operation("deepseek", "chat_completions")

    def test_fixed_probe_rejects_canonical_endpoint_or_model_changes(self):
        for field, value in (("endpoint_url", "https://attacker.example/chat/completions"), ("models", ["other-model"])):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                platform = self._platform()
                platform["capabilities"]["operations"][0][field] = value
                platforms = Path(directory)
                (platforms / "deepseek.yaml").write_text(yaml.safe_dump(platform), encoding="utf-8")
                with patch.object(probe_capabilities, "PLATFORMS_DIR", platforms):
                    with self.assertRaisesRegex(ValueError, "fixed probe configuration"):
                        probe_capabilities._load_operation("deepseek", "chat_completions")

    def test_candidate_creation_never_overwrites_an_existing_observation(self):
        candidate = {
            "checked_at": "2026-09-03T12:00:00+00:00",
            "operation_id": "chat_completions",
            "platform_slug": "deepseek",
            "tool": "raw_http",
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(
            probe_capabilities, "CANDIDATES_DIR", Path(directory)
        ):
            probe_capabilities._write_candidate(candidate)
            with self.assertRaises(FileExistsError):
                probe_capabilities._write_candidate(candidate)


if __name__ == "__main__":
    unittest.main()
