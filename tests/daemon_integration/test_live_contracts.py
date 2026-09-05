"""Offline regressions for failures discovered during production integration."""
import unittest
from unittest.mock import Mock, patch

from daemon.gh_client import GitHubClient, GhError
from daemon.main import SELFTEST_WORKFLOW
from test_intake import bot, event


class LiveContracts(unittest.TestCase):
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
