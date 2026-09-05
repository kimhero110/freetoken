import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def run_blocks(workflow: str) -> str:
    return "\n".join(
        match.group(1)
        for match in re.finditer(r"^\s+run:\s*\|\s*\n((?:\s{10,}.*\n?)*)", workflow, re.MULTILINE)
    )


class PlatformTipWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (WORKFLOWS / "feishu-platform-tip.yml").read_text(encoding="utf-8")

    def test_dispatch_trigger_with_exact_inputs(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        for field in ("url:", "note:", "ticket_id:"):
            self.assertIn(field, self.workflow)
        self.assertNotIn("repository_dispatch", self.workflow)

    def test_inputs_never_interpolated_into_shell(self):
        self.assertNotIn("${{ inputs.", run_blocks(self.workflow))

    def test_app_token_pinned_and_gated_pr(self):
        self.assertIn("actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1", self.workflow)
        self.assertIn("gh pr create --base main", self.workflow)
        self.assertIn("gh pr merge --auto --merge --delete-branch", self.workflow)
        self.assertIn('BRANCH="auto/tip-${TICKET_ID}"', self.workflow)
        self.assertNotIn("[skip ci]", self.workflow)

    def test_candidate_only_writes(self):
        self.assertIn("git add --all -- data/candidates/", self.workflow)
        self.assertNotIn("git add data/platforms/", self.workflow)


class ArticleRewriteWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (WORKFLOWS / "feishu-article-rewrite.yml").read_text(encoding="utf-8")

    def test_dispatch_inputs_with_mode_choice(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        for field in ("url:", "note:", "ticket_id:", "mode:"):
            self.assertIn(field, self.workflow)
        self.assertIn("- rewrite", self.workflow)
        self.assertIn("- outline", self.workflow)

    def test_draft_pr_is_never_auto_merged(self):
        self.assertIn("gh pr create --base main", self.workflow)
        self.assertIn("[draft]", self.workflow)
        self.assertNotIn("--auto", self.workflow)
        self.assertIn('BRANCH="auto/article-${TICKET_ID}"', self.workflow)

    def test_compiles_data_into_pr(self):
        self.assertIn("python scripts/compile_data.py", self.workflow)
        self.assertIn("data/articles.json", self.workflow)

    def test_inputs_never_interpolated_into_shell(self):
        self.assertNotIn("${{ inputs.", run_blocks(self.workflow))


class ReviewCandidateAnnotationContractTests(unittest.TestCase):
    def test_annotated_approval_inputs_exist_but_actor_stays_authoritative(self):
        workflow = (WORKFLOWS / "review-candidate.yml").read_text(encoding="utf-8")
        self.assertIn("approver_via:", workflow)
        self.assertIn("approver_id:", workflow)
        blocks = run_blocks(workflow)
        self.assertIn('REVIEWER: ${{ github.actor }}', workflow)
        self.assertNotIn("${{ inputs.approver", blocks)

    def test_dispatch_titles_and_inputs_match_daemon_contract(self):
        import yaml
        expected = {
            "feishu-platform-tip.yml": ({"url", "note", "ticket_id"}, "intake:${{ inputs.ticket_id }}"),
            "feishu-article-rewrite.yml": ({"url", "note", "ticket_id", "mode"}, "intake:${{ inputs.ticket_id }}"),
            "review-candidate.yml": ({"candidate_id", "decision", "approver_via", "approver_id", "ticket_id"},
                                     "intake:${{ inputs.ticket_id }}:${{ inputs.decision }}:${{ inputs.candidate_id }}"),
        }
        for filename, (fields, title) in expected.items():
            workflow = yaml.load((WORKFLOWS / filename).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
            self.assertEqual(set(workflow["on"]["workflow_dispatch"]["inputs"]), fields)
            self.assertEqual(workflow["run-name"], title)

    def test_build_runs_real_sdk_tests_in_isolated_environment(self):
        workflow = (WORKFLOWS / "publish.yml").read_text(encoding="utf-8")
        self.assertIn("python -m venv .venv-daemon", workflow)
        self.assertIn(".venv-daemon/bin/python -m pip install -r daemon/requirements.txt", workflow)
        self.assertIn(".venv-daemon/bin/python -m unittest discover -s tests/daemon_integration -v", workflow)


if __name__ == "__main__":
    unittest.main()
