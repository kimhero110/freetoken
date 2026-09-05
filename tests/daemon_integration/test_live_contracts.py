"""Offline regressions for failures discovered during production integration."""
import unittest
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from daemon.gh_client import GitHubClient, GhError
from daemon.feishu_client import FeishuClient, extract_message
from daemon import cards
from daemon.main import SELFTEST_WORKFLOW
from test_intake import bot, event, ticket_and_run


class LiveContracts(unittest.TestCase):
    def test_forbidden_is_not_rate_limit_and_write_is_not_retried(self):
        for headers, message, expected in [
            ({}, 'Resource not accessible by personal access token', 'PERMISSION'),
            ({'X-RateLimit-Remaining': '0'}, 'API rate limit exceeded', 'RATE'),
            ({}, 'You have exceeded a secondary rate limit', 'RATE'),
        ]:
            client = GitHubClient('test-token', 'owner/repo')
            client.session = Mock()
            client.session.request.return_value = SimpleNamespace(
                status_code=403, headers=headers, text=message, json=lambda: {'message': message})
            with self.assertRaises(GhError) as caught:
                client.approve_deployment(10, 5, 'confirmed test')
            self.assertEqual(caught.exception.kind, expected)
            self.assertEqual(client.session.request.call_count, 1)

    def test_permission_failure_finishes_ticket_and_updates_card_once(self):
        b = bot()
        ticket, run = ticket_and_run(b)
        ticket.run_ids = [10]
        ticket.phase = 'awaiting_gate'
        ticket.card_message_id = 'om_existing'
        b.gh.get_run.return_value = run
        b.gh.pending_deployments.return_value = [{'environment': {'id': 5, 'name': 'production'}, 'current_user_can_approve': True}]
        b.gh.approve_deployment.side_effect = GhError('PERMISSION', 'Resource not accessible by personal access token', 403)
        with patch('daemon.main.time.sleep'):
            self.assertFalse(b._approve_gate(ticket, 'oc_chat', 10, 'confirmed'))
        self.assertEqual(ticket.phase, 'failed')
        b.gh.approve_deployment.assert_called_once()
        b.gh.cancel_run.assert_called_once_with(10)
        b.feishu.patch_card.assert_called_once()
        self.assertIn('Deployments', json.dumps(b.feishu.patch_card.call_args.args[1]))

    def test_confirm_to_gate_to_completion_through_real_sdk_card_serialization(self):
        b = bot()
        b.feishu = FeishuClient.__new__(FeishuClient)
        b.feishu.client = Mock()
        api = b.feishu.client.im.v1.message
        for method in (api.reply, api.create, api.patch):
            method.return_value = SimpleNamespace(success=lambda: True, data=SimpleNamespace(message_id='om_card'))
        b.handle(*extract_message(event(text='联调')))
        ticket = next(iter(b.store.tickets.values()))
        b.gh.dispatch_workflow.assert_not_called()
        with patch('daemon.main.threading.Thread'):
            b.cmd_confirm('oc_chat', 'om_confirmation', 'ou_owner', ticket.confirm_code)
        run = {'id': 10, 'path': f'.github/workflows/{SELFTEST_WORKFLOW}', 'head_branch': 'main',
               'repository': {'full_name': 'owner/repo'}, 'event': 'workflow_dispatch',
               'display_title': f'intake:{ticket.ticket_id}', 'actor': {'login': 'operator'},
               'head_sha': 'a' * 40, 'status': 'waiting'}
        b.gh.list_runs.return_value = [run]
        b.gh.get_run.side_effect = [run, {**run, 'status': 'completed', 'conclusion': 'success'}]
        b.gh.pending_deployments.return_value = [{'environment': {'id': 5, 'name': 'production'}, 'current_user_can_approve': True}]
        with patch('daemon.main.time.sleep'):
            b.track_selftest(ticket, 'oc_chat')
        self.assertEqual(ticket.phase, 'done')
        b.gh.dispatch_workflow.assert_called_once()
        b.gh.approve_deployment.assert_called_once()
        for call in api.patch.call_args_list:
            content = json.loads(call.args[0].request_body.content)
            self.assertIn('elements', content)
            self.assertNotIn('card', content)

    def test_unchanged_phase_does_not_postpone_watchdog(self):
        b = bot()
        ticket, _ = ticket_and_run(b)
        ticket.phase, ticket.updated_at = 'awaiting_gate', 100
        b.tracked(ticket, 'awaiting_gate', cards.error_card('test', 'test', 'test'), 'oc_chat')
        self.assertEqual(ticket.updated_at, 100)

    def test_restart_reports_interruption_without_replaying_approval(self):
        b = bot()
        active, _ = ticket_and_run(b)
        active.phase, active.run_ids = 'awaiting_gate', [10]
        pending = b.store.new_ticket('selftest', 'no-content-change', owner='ou_owner')
        b.store.issue_confirm(pending)
        b.report_interrupted()
        self.assertEqual(active.phase, 'interrupted')
        self.assertEqual(pending.phase, 'created')
        self.assertIs(b.store.active_approval_for(active.arg), active)
        b.feishu.send_card.assert_called_once()
        b.gh.dispatch_workflow.assert_not_called()
        b.gh.approve_deployment.assert_not_called()

    def test_im_reply_create_and_patch_receive_card_not_webhook_envelope(self):
        client = FeishuClient.__new__(FeishuClient)
        client.client = Mock()
        response = SimpleNamespace(success=lambda: True, data=SimpleNamespace(message_id='om_new'))
        api = client.client.im.v1.message
        for method in (api.reply, api.create, api.patch):
            method.return_value = response
        card = cards.status_card(['identity'], '?', 'test', '0')
        client.send_card('oc_chat', card, 'om_parent')
        client.send_card('ou_owner', card, receive_id_type='open_id')
        client.patch_card('om_parent', card)
        for method in (api.reply, api.create, api.patch):
            content = json.loads(method.call_args.args[0].request_body.content)
            self.assertEqual(content, card['card'])
            self.assertIn('elements', content)
            self.assertNotIn('msg_type', content)
            self.assertNotIn('card', content)

    def test_missing_candidate_directory_requires_readable_parent(self):
        client = GitHubClient('test-token', 'owner/repo')
        client._request = Mock(side_effect=[GhError('CONTRACT', 'Not found', 404), [{'name': 'platforms'}]])
        self.assertEqual(client.list_candidates(), [])
        client._request = Mock(side_effect=[GhError('CONTRACT', 'Not found', 404), [{'name': 'candidates'}]])
        with self.assertRaises(GhError):
            client.list_candidates()
        client._request = Mock(side_effect=GhError('PAT_DEAD', 'Unauthorized', 401))
        with self.assertRaises(GhError):
            client.list_candidates()
        self.assertEqual(client._request.call_count, 1)

    def test_non_candidate_files_do_not_become_approval_items(self):
        client = GitHubClient('test-token', 'owner/repo')
        client._request = Mock(return_value=[{'name': '.gitkeep', 'type': 'file'}, {'name': 'a.yaml', 'type': 'file'}])
        self.assertEqual(client.list_candidates(), ['a'])

    def test_selftest_requires_owner_and_real_confirmation(self):
        b = bot()
        b.handle('ou_stranger', 'oc_chat', 'om_message', 'selftest')
        self.assertEqual(len(b.store.tickets), 0)
        b.handle('ou_owner', 'oc_chat', 'om_message', 'selftest')
        ticket = next(iter(b.store.tickets.values()))
        b.gh.dispatch_workflow.assert_not_called()
        with patch('daemon.main.threading.Thread'):
            b.cmd_confirm('oc_chat', 'om_message', 'ou_owner', ticket.confirm_code)
        b.gh.dispatch_workflow.assert_called_once_with(SELFTEST_WORKFLOW, inputs={'ticket_id': ticket.ticket_id})
        run = {'path': f'.github/workflows/{SELFTEST_WORKFLOW}', 'head_branch': 'main',
               'repository': {'full_name': 'owner/repo'}, 'event': 'workflow_dispatch',
               'display_title': f'intake:{ticket.ticket_id}', 'actor': {'login': 'operator'}, 'head_sha': 'a' * 40}
        self.assertTrue(b._matches_run(ticket, run, SELFTEST_WORKFLOW))
        self.assertFalse(b._matches_run(ticket, {**run, 'head_sha': 'b' * 40}, SELFTEST_WORKFLOW))


if __name__ == '__main__':
    unittest.main()
