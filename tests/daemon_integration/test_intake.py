"""Offline tests against the real pinned Lark SDK; never contact external services."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from daemon.feishu_client import FeishuClient, extract_message
from daemon.gh_client import GhError, GitHubClient
from daemon.journal import Journal
from daemon.main import Bot, REVIEW_WORKFLOW, PLATFORM_WORKFLOW, ARTICLE_WORKFLOW
from daemon.state import TicketStore

def event(sender="ou_owner", text="帮助", event_id="event-1"):
    return P2ImMessageReceiveV1({"header": {"event_id": event_id}, "event": {
        "sender": {"sender_id": {"open_id": sender}},
        "message": {"message_type": "text", "content": json.dumps({"text": text}),
                    "chat_id": "oc_chat", "message_id": "om_message"}}})


def bot():
    result = Bot.__new__(Bot)
    result.config = {"github_repo": "owner/repo", "owner_open_id": "ou_owner", "bootstrap": False,
                     "commit_sha": "dev", "watchdog_minutes": 30}
    result.store = TicketStore()
    result.gh = Mock()
    result.gh.dispatch_identity.return_value = ("operator", "a" * 40)
    result.feishu = Mock()
    result.feishu.send_card.return_value = "om_card"
    result.journal = Mock()
    return result


def ticket_and_run(b, workflow=REVIEW_WORKFLOW):
    ticket = b.store.new_ticket("approve", "candidate-a", owner="ou_owner")
    ticket.dispatch_actor, ticket.dispatch_sha = "operator", "a" * 40
    run = {"id": 10, "run_attempt": 1, "path": f".github/workflows/{workflow}",
           "repository": {"full_name": "owner/repo"}, "head_branch": "main", "head_sha": "a" * 40,
           "actor": {"login": "operator"}, "event": "workflow_dispatch", "status": "waiting",
           "display_title": f"intake:{ticket.ticket_id}:approve:candidate-a"}
    return ticket, run


class MessageTests(unittest.TestCase):
    def test_real_sdk_owner_stranger_bootstrap_and_missing_identity(self):
        b = bot()
        self.assertEqual(extract_message(event()), ("ou_owner", "oc_chat", "om_message", "帮助"))
        b.handle(*extract_message(event()))
        b.feishu.send_card.assert_called_once()
        b.feishu.reset_mock()
        b.handle(*extract_message(event("ou_stranger")))
        b.feishu.send_card.assert_not_called()
        b.config["bootstrap"] = True
        b.handle(*extract_message(event("ou_stranger", "谁我")))
        b.feishu.send_card.assert_called_once()
        self.assertIsNone(extract_message(event(None)))

    def test_sdk_header_deduplicates_redelivery(self):
        b = bot()
        with tempfile.TemporaryDirectory() as directory:
            b.journal = Journal(Path(directory) / "journal.jsonl")
            b.handle = Mock()
            b.on_event(event())
            b.on_event(event())
            b.handle.assert_called_once()

    def test_reply_and_proactive_requests_have_correct_recipients(self):
        client = FeishuClient.__new__(FeishuClient)
        client.client = Mock()
        response = SimpleNamespace(success=lambda: True, data=SimpleNamespace(message_id="om_new"))
        client.client.im.v1.message.reply.return_value = response
        client.client.im.v1.message.create.return_value = response
        self.assertEqual(client.send_card("oc_chat", {}, "om_parent"), "om_new")
        request = client.client.im.v1.message.reply.call_args.args[0]
        self.assertEqual(request.paths["message_id"], "om_parent")
        for recipient, kind in [("oc_chat", "chat_id"), ("ou_owner", "open_id")]:
            self.assertEqual(client.send_card(recipient, {}, receive_id_type=kind), "om_new")
            request = client.client.im.v1.message.create.call_args.args[0]
            self.assertEqual(request.receive_id_type, kind)
            self.assertEqual(request.request_body.receive_id, recipient)
        client.client.im.v1.message.create.return_value = SimpleNamespace(success=lambda: False, code=400, msg="failed")
        self.assertEqual(client.send_card("oc_chat", {}), "")

    def test_daily_digest_uses_owner_open_id(self):
        b = bot()
        b.gh.list_candidates.return_value = []
        b.gh.list_runs.return_value = []
        b.journal.load_events.return_value = []
        b.send_daily_digest()
        self.assertEqual(b.feishu.send_card.call_args.args[0], "ou_owner")
        self.assertEqual(b.feishu.send_card.call_args.kwargs, {"receive_id_type": "open_id"})


class DispatchTests(unittest.TestCase):
    def test_platform_and_article_inputs(self):
        for kind, workflow, fields in [
            ("platform", PLATFORM_WORKFLOW, {"url", "note", "ticket_id"}),
            ("article", ARTICLE_WORKFLOW, {"url", "note", "ticket_id", "mode"}),
        ]:
            b = bot()
            with patch("daemon.main.threading.Thread"):
                b.cmd_submit("oc_chat", "om_parent", "ou_owner", kind, "https://example.com 参数:提纲")
            call = b.gh.dispatch_workflow.call_args
            self.assertEqual(call.args[0], workflow)
            self.assertEqual(set(call.kwargs["inputs"]), fields)
            if kind == "article":
                self.assertEqual(call.kwargs["inputs"]["mode"], "outline")
            ticket = next(iter(b.store.tickets.values()))
            self.assertEqual(ticket.dispatch_actor, "operator")
            self.assertEqual(ticket.dispatch_sha, "a" * 40)

    def test_confirm_dispatch_carries_ticket_and_candidate(self):
        b = bot()
        ticket = b.store.new_ticket("reject", "candidate-a", owner="ou_owner")
        code = b.store.issue_confirm(ticket)
        with patch("daemon.main.threading.Thread"):
            b.cmd_confirm("oc_chat", "om_parent", "ou_owner", code)
        inputs = b.gh.dispatch_workflow.call_args.kwargs["inputs"]
        self.assertEqual((inputs["ticket_id"], inputs["candidate_id"], inputs["decision"]),
                         (ticket.ticket_id, "candidate-a", "reject"))


class ApprovalTests(unittest.TestCase):
    def test_review_to_publish_chain_approves_only_its_merge(self):
        b = bot()
        ticket, review = ticket_and_run(b)
        publish = dict(review, id=20, path=".github/workflows/publish.yml", event="push",
                       head_sha="b" * 40, actor={"login": "merge-bot"})
        unrelated = dict(publish, id=999, head_sha="c" * 40)
        b.gh.list_runs.side_effect = [[review], [unrelated, publish]]
        b.gh.get_run.side_effect = lambda run_id: review if run_id == 10 else publish
        b.gh.pending_deployments.return_value = [{"environment": {"name": "production", "id": 123}}]
        b.gh.reviewed_merge.return_value = {"sha": "b" * 40, "actor": "merge-bot"}
        with patch("daemon.main.time.sleep"), patch.object(b, "_await_completion", return_value="success"):
            b.track_approval(ticket, "oc_chat")
        self.assertEqual(ticket.phase, "done")
        self.assertEqual(ticket.run_ids, [10, 20])
        self.assertEqual([call.args[0] for call in b.gh.approve_deployment.call_args_list], [10, 20])

    def test_merge_lookup_failure_stops_before_publication(self):
        b = bot()
        ticket, review = ticket_and_run(b)
        b.gh.get_run.return_value = review
        b.gh.reviewed_merge.side_effect = GhError("NETWORK", "offline")
        with patch.object(b, "_await_gate", return_value=10), patch.object(b, "_approve_gate", return_value=True), \
             patch.object(b, "_await_completion", return_value="success"), patch.object(b, "_find_publish_run") as find:
            b.track_approval(ticket, "oc_chat")
        find.assert_not_called()
        self.assertEqual(ticket.phase, "failed")

    def test_waiting_run_selected_in_any_order_and_completed_not_lost(self):
        for status in ["waiting", "pending", "requested", "queued", "completed"]:
            for reverse in [False, True]:
                b = bot()
                ticket, run = ticket_and_run(b)
                run["status"] = status
                other = dict(run, id=999, display_title="intake:other:approve:candidate-b")
                b.gh.list_runs.return_value = [other, run] if reverse else [run, other]
                with patch("daemon.main.time.sleep"):
                    self.assertEqual(b._await_gate(ticket, "oc_chat", REVIEW_WORKFLOW), 10)
                self.assertEqual(ticket.run_ids, [10])

    def test_identity_mismatches_and_ambiguous_runs_fail_closed(self):
        b = bot()
        ticket, run = ticket_and_run(b)
        for key, value in {"head_sha": "b" * 40, "head_branch": "other", "event": "push",
                           "actor": {"login": "stranger"}, "path": ".github/workflows/other.yml",
                           "repository": {"full_name": "other/repo"}, "display_title": "other"}.items():
            with self.subTest(key=key):
                self.assertFalse(b._matches_run(ticket, dict(run, **{key: value}), REVIEW_WORKFLOW))
        b.gh.list_runs.return_value = [run, dict(run, id=11)]
        with patch("daemon.main.time.sleep"):
            self.assertIsNone(b._await_gate(ticket, "oc_chat", REVIEW_WORKFLOW))
        b.gh.approve_deployment.assert_not_called()

    def test_gate_revalidates_identity_and_environment_and_journals_success(self):
        for scenario in ["valid", "other-run", "other-env", "multiple-envs"]:
            b = bot()
            ticket, run = ticket_and_run(b)
            ticket.run_ids = [10]
            b.gh.get_run.return_value = run if scenario != "other-run" else dict(run, head_sha="b" * 40)
            pending = {"environment": {"id": 123, "name": "production" if scenario != "other-env" else "staging"}}
            b.gh.pending_deployments.return_value = [pending] * (2 if scenario == "multiple-envs" else 1)
            with patch("daemon.main.time.sleep"):
                self.assertEqual(b._approve_gate(ticket, "oc_chat", 10, "test"), scenario == "valid")
            if scenario == "valid":
                b.gh.approve_deployment.assert_called_once_with(10, 123, "test")
                self.assertTrue(any(c.args[0].get("type") == "gate_approved" for c in b.journal.append.call_args_list))
            else:
                b.gh.approve_deployment.assert_not_called()

    def test_publish_matches_only_merged_sha_and_actor_even_when_delayed(self):
        b = bot()
        ticket, run = ticket_and_run(b)
        ticket.publish_sha, ticket.publish_actor = "b" * 40, "freetoken-bot[bot]"
        publish = dict(run, id=20, path=".github/workflows/publish.yml", event="push", head_sha="b" * 40,
                       actor={"login": "freetoken-bot[bot]"})
        unrelated = dict(publish, id=999, head_sha="c" * 40)
        b.gh.list_runs.side_effect = [[unrelated], [unrelated, publish]]
        with patch("daemon.main.time.sleep"):
            self.assertEqual(b._find_publish_run(ticket)["id"], 20)
        self.assertFalse(b._matches_run(ticket, dict(publish, actor={"login": "other"}), "publish.yml"))
        restored = TicketStore()
        restored.prime([ticket.to_event()])
        self.assertTrue(b._matches_run(restored.tickets[ticket.ticket_id], publish, "publish.yml"))

    def test_review_merge_is_resolved_from_exact_run_attempt_branch(self):
        client = GitHubClient("fake-token", "owner/repo")
        pull = {"number": 7, "merged_at": "2026-09-05", "head": {"ref": "auto/review-10-2", "repo": {"full_name": "owner/repo"}},
                "base": {"ref": "main", "repo": {"full_name": "owner/repo"}}}
        client._request = Mock(side_effect=[[dict(pull, head={"ref": "auto/review-11-2"}), pull],
                                           {"merged": True, "merge_commit_sha": "b" * 40, "merged_by": {"login": "bot"}}])
        self.assertEqual(client.reviewed_merge({"id": 10, "run_attempt": 2}), {"sha": "b" * 40, "actor": "bot"})
        self.assertIn("auto%2Freview-10-2", client._request.call_args_list[0].args[1])
        client._request = Mock(return_value=[])
        self.assertIsNone(client.reviewed_merge({"id": 10, "run_attempt": 2}))


if __name__ == "__main__":
    unittest.main()
