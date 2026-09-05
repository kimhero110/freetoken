import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class SecurityInvariantTests(unittest.TestCase):
    def test_feishu_credentials_have_no_repository_defaults(self):
        source = (ROOT / "scripts" / "feishu_notifier.py").read_text(encoding="utf-8")
        self.assertNotIn("open.feishu.cn/open-apis/bot/v2/hook/", source)
        self.assertNotRegex(source, re.compile(r"DEFAULT_(?:WEBHOOK|SECRET)\s*="))

    def test_feishu_configuration_is_empty_when_secrets_are_missing(self):
        from scripts.feishu_notifier import get_feishu_secret, get_feishu_webhook

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_feishu_webhook(), "")
            self.assertEqual(get_feishu_secret(), "")

    def test_workflow_inputs_are_not_interpolated_into_shell_source(self):
        workflow = (ROOT / ".github" / "workflows" / "update.yml").read_text(
            encoding="utf-8"
        )
        run_blocks = "\n".join(
            match.group(1)
            for match in re.finditer(
                r"^\s+run:\s*\|\s*\n((?:\s{10,}.*\n?)*)", workflow, re.MULTILINE
            )
        )
        self.assertNotIn("${{ inputs.", run_blocks)
        self.assertIn('python scripts/extract.py "${ARGS[@]}"', run_blocks)

    def test_repository_writers_serialize_duplicate_runs_and_rebase_before_push(self):
        for name in ("update.yml", "discover.yml", "probe-capabilities.yml", "review-candidate.yml"):
            workflow = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8"
            )
            self.assertIn("group: freetoken-main-writer", workflow)
            self.assertIn("cancel-in-progress: false", workflow)
            self.assertIn("git pull --rebase origin main", workflow)

    def test_production_deploy_only_accepts_main(self):
        workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        self.assertIn("if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'", workflow)
        self.assertIn("environment: production", workflow)

    def test_secret_bearing_manual_workflows_only_run_main(self):
        for name in ("update.yml", "discover.yml", "push_wechat.yml", "feishu-test.yml", "probe-capabilities.yml"):
            workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn("if: github.ref == 'refs/heads/main'", workflow, name)

    def test_actions_are_pinned_to_commits(self):
        workflows = (ROOT / ".github" / "workflows").glob("*.yml")
        for path in workflows:
            for line in path.read_text(encoding="utf-8").splitlines():
                if "uses: actions/" in line:
                    reference = line.split("@", 1)[1].split()[0]
                    self.assertRegex(reference, r"^[a-f0-9]{40}$", path.name)

    def test_ci_installs_only_hash_locked_python_dependencies(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = path.read_text(encoding="utf-8")
            if "pip install" in workflow:
                self.assertIn("pip install --require-hashes -r scripts/requirements.lock", workflow)

    def test_ssh_deploy_requires_host_verification_and_non_root_user(self):
        source = (ROOT / "scripts" / "sync_to_tencent.py").read_text(encoding="utf-8")
        self.assertNotIn("StrictHostKeyChecking=no", source)
        self.assertIn("StrictHostKeyChecking=yes", source)
        self.assertNotIn("SERVER_USER = 'root'", source)

    def test_server_deploy_normalizes_artifact_permissions_for_nginx(self):
        source = (ROOT / "deploy" / "deploy_freetoken.sh").read_text(encoding="utf-8")
        self.assertIn('find "$next_dir" -type d -exec chmod 755 {} +', source)
        self.assertIn('find "$next_dir" -type f -exec chmod 644 {} +', source)

    def test_deploy_does_not_use_unconditional_force_push(self):
        workflow = (ROOT / ".github" / "workflows" / "update.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("git push --force origin deploy", workflow)
        self.assertNotIn("git push --force", workflow)

    def test_scheduled_extraction_only_commits_candidates(self):
        workflow = (ROOT / ".github" / "workflows" / "update.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("git add data/candidates/", workflow)
        self.assertNotIn("git add data/platforms/", workflow)
        self.assertNotIn("npm run build", workflow)
        self.assertNotIn("HEAD:deploy", workflow)

    def test_capability_probe_is_weekly_allowlisted_and_commits_only_candidates(self):
        workflow = (ROOT / ".github" / "workflows" / "probe-capabilities.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "17 3 * * 2"', workflow)
        self.assertIn("type: choice", workflow)
        for provider in (
            "deepseek", "siliconflow", "aliyun-bailian", "moonshot-kimi", "google-ai-studio",
            "groq", "volcengine", "zhipu-ai", "openrouter", "gmi-cloud-minimax",
        ):
            self.assertIn(f"- {provider}", workflow)
        self.assertIn("--operation chat_completions", workflow)
        self.assertIn("--all-configured", workflow)
        self.assertIn("probe_secret_coverage.py", workflow)
        self.assertIn("--tool openai_python", workflow)
        self.assertIn("--tool openai_node", workflow)
        self.assertIn("git add --all -- data/candidates/", workflow)
        self.assertNotIn("git add data/platforms/", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("if: steps.probe.outcome == 'failure'", workflow)

    def test_review_workflow_is_main_only_and_passes_inputs_via_environment(self):
        workflow = (ROOT / ".github" / "workflows" / "review-candidate.yml").read_text(
            encoding="utf-8"
        )
        run_blocks = "\n".join(
            match.group(1)
            for match in re.finditer(r"^\s+run:\s*\|\s*\n((?:\s{10,}.*\n?)*)", workflow, re.MULTILINE)
        )
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertNotIn("${{ inputs.", run_blocks)
        self.assertNotIn("${{ github.actor }}", run_blocks)
        self.assertIn("GITHUB_ACTOR=\"$REVIEWER\"", run_blocks)
        self.assertIn("environment: production", workflow)
        self.assertIn('^[a-z0-9]+(-[a-z0-9]+)*$', run_blocks)
        self.assertIn('${#CANDIDATE_ID}', run_blocks)
        self.assertIn('--approve "$CANDIDATE_ID"', run_blocks)
        self.assertIn('--reject "$CANDIDATE_ID"', run_blocks)
        self.assertIn("Send isolated approval notification", workflow)
        notification_step = workflow.split("- name: Send isolated approval notification", 1)[1]
        self.assertNotIn("git ", notification_step)
        notification_secret_lines = [line for line in notification_step.splitlines() if "secrets." in line]
        self.assertEqual(len(notification_secret_lines), 2)
        self.assertTrue(all("FEISHU_" in line for line in notification_secret_lines))
        decision_step = workflow.split("- name: Apply and preserve the human decision", 1)[1].split("- name:", 1)[0]
        self.assertNotIn("secrets.", decision_step)

    def test_review_workflow_mints_app_token_before_authenticated_writes(self):
        workflow = (ROOT / ".github" / "workflows" / "review-candidate.yml").read_text(
            encoding="utf-8"
        )
        mint_step = workflow.split("- name: Mint GitHub App token", 1)[1].split("- name:", 1)[0]
        self.assertIn("actions/create-github-app-token@", mint_step)
        self.assertEqual(mint_step.count("secrets."), 2)
        self.assertIn("APP_ID", mint_step)
        self.assertIn("APP_PRIVATE_KEY", mint_step)
        checkout_step = workflow.split("- name: Check out repository", 1)[1].split("- name:", 1)[0]
        self.assertIn("token: ${{ steps.app-token.outputs.token }}", checkout_step)
        self.assertIn('gh pr checks "$BRANCH" --watch', workflow)
        self.assertIn('gh pr merge "$BRANCH" --merge --delete-branch', workflow)

    def test_data_writer_workflows_use_gated_pull_requests(self):
        for name in ("update.yml", "discover.yml", "probe-capabilities.yml"):
            workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn("actions/create-github-app-token@", workflow, name)
            self.assertIn("token: ${{ steps.app-token.outputs.token }}", workflow, name)
            self.assertIn("gh pr create --base main", workflow, name)
            self.assertIn("gh pr merge", workflow, name)
            self.assertNotIn("git push origin main", workflow, name)
            self.assertNotIn("[skip ci]", workflow, name)

    def test_candidate_ids_and_platform_slugs_reject_path_traversal(self):
        from scripts.review_candidates import _candidate_file, _safe_slug

        for invalid in ("../config", "a/b", "A", "", "a..b"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    _safe_slug(invalid)
                with self.assertRaises(ValueError):
                    _candidate_file(invalid)
        with self.assertRaises(ValueError):
            _candidate_file("a" * 201)


if __name__ == "__main__":
    unittest.main()
