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


class ReviewCandidateNoopContractTests(unittest.TestCase):
    def test_empty_index_after_a_successful_review_is_an_idempotent_noop(self):
        import yaml

        workflow = (WORKFLOWS / "review-candidate.yml").read_text(encoding="utf-8")
        loaded = yaml.load(workflow, Loader=yaml.BaseLoader)
        job = loaded["jobs"]["review"]
        self.assertEqual(job["environment"], "production")
        self.assertEqual(job["if"], "github.ref == 'refs/heads/main'")
        self.assertEqual(loaded["permissions"]["contents"], "read")

        apply_step = next(step for step in job["steps"] if step["name"] == "Apply and preserve the human decision")
        self.assertEqual(apply_step["id"], "apply")
        quiet_branch = apply_step["run"].split("git diff --cached --quiet", 1)[1].split("git commit", 1)[0]
        self.assertIn("idempotent no-op", quiet_branch)
        self.assertIn("exit 0", quiet_branch)
        self.assertNotIn("exit 1", quiet_branch)
        self.assertIn('echo "noop=true" >> "$GITHUB_OUTPUT"', quiet_branch)

        merge_step = next(step for step in job["steps"] if step["name"] == "Merge the reviewed change through a gated pull request")
        self.assertEqual(merge_step["if"], "${{ success() && steps.apply.outputs.noop != 'true' }}")
        self.assertIn("git pull --rebase origin main", merge_step["run"])
        self.assertIn('gh pr create --base main --head "$BRANCH"', merge_step["run"])
        self.assertIn('gh pr checks "$BRANCH" --watch --interval 10', merge_step["run"])
        self.assertIn('gh pr merge "$BRANCH" --merge --delete-branch', merge_step["run"])

        notify_step = next(step for step in job["steps"] if step["name"] == "Send isolated approval notification")
        self.assertIn("steps.apply.outputs.noop != 'true'", notify_step["if"])
        self.assertIn("inputs.decision == 'approve'", notify_step["if"])


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


class VerifyUnverifiedWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (WORKFLOWS / "verify-unverified.yml").read_text(encoding="utf-8")

    def test_dispatch_and_weekly_cost_window_schedule(self):
        self.assertIn("workflow_dispatch:", self.workflow)
        self.assertIn('cron: "30 18 * * 1"', self.workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", self.workflow)
        self.assertEqual(self.workflow.count("workflow_dispatch:"), 1)

    def test_never_touches_canonical_platforms_or_approves(self):
        self.assertNotIn("git add data/platforms", self.workflow)
        self.assertNotIn("--approve", self.workflow)
        self.assertNotIn("review_candidates --approve", self.workflow)
        self.assertNotIn("last_verified", self.workflow)

    def test_app_token_concurrency_and_hash_locked_deps(self):
        self.assertIn(
            "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
            self.workflow,
        )
        self.assertIn("token: ${{ steps.app-token.outputs.token }}", self.workflow)
        self.assertIn("group: freetoken-main-writer", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)
        self.assertIn("pip install --require-hashes -r scripts/requirements.lock", self.workflow)

    def test_publishes_candidates_but_never_deploys(self):
        self.assertIn("python -m scripts.publish_candidates", self.workflow)
        self.assertIn("python scripts/verify_unverified.py --list-only", self.workflow)
        self.assertIn("--finalize", self.workflow)
        self.assertNotIn("npm run build", self.workflow)
        self.assertNotIn("git push origin main", self.workflow)


if __name__ == "__main__":
    unittest.main()
