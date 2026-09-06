import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.check_runner import paid_result, public_result
from scripts.check_state import GitState, StateError, empty_state
from scripts import publish_candidates, extract
import json
import os
import sys
import yaml


class MemoryState:
    def __init__(self):
        self.state = empty_state()

    def update(self, mutate):
        state = copy.deepcopy(self.state)
        result = mutate(state)
        self.state = state
        return result


class PaidCallTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryState()
        self.request = Mock(return_value={"intro": "public result"})

    def call(self, **changes):
        args = dict(store=self.store, key='a' * 64, source='b' * 64, run='1',
                    request=self.request, validate=lambda value: value, limit=2)
        args.update(changes)
        return paid_result(**args)

    def test_saved_response_is_reused_on_new_run(self):
        self.call()
        self.call(run='2')
        self.assertEqual(self.request.call_count, 1)

    def test_state_unavailable_makes_no_request(self):
        with patch.object(self.store, 'update', side_effect=StateError('offline')):
            with self.assertRaises(StateError):
                self.call()
        self.request.assert_not_called()

    def test_crash_before_send_leaves_intent_and_never_replays(self):
        self.request.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.call()
        with self.assertRaisesRegex(StateError, 'UNCERTAIN'):
            self.call(run='2')
        self.assertEqual(self.request.call_count, 1)

    def test_response_lost_before_save_cannot_be_reissued(self):
        original = self.store.update
        n = 0
        def broken_save(mutate):
            nonlocal n
            n += 1
            if n == 2:
                raise StateError('save failed')
            return original(mutate)
        with patch.object(self.store, 'update', side_effect=broken_save):
            with self.assertRaises(StateError):
                self.call()
        with self.assertRaisesRegex(StateError, 'UNCERTAIN'):
            self.call(run='2')
        self.assertEqual(self.request.call_count, 1)

    def test_transport_failure_is_uncertain_and_not_retried(self):
        self.request.side_effect = TimeoutError()
        with self.assertRaisesRegex(StateError, 'UNCERTAIN'):
            self.call()
        with self.assertRaises(StateError):
            self.call(run='2')
        self.assertEqual(self.request.call_count, 1)

    def test_changed_provider_does_not_bypass_source_dedup(self):
        self.call()
        with self.assertRaisesRegex(StateError, 'SOURCE_ALREADY_ATTEMPTED'):
            self.call(key='c' * 64)
        self.assertEqual(self.request.call_count, 1)

    def test_historical_block_and_zero_budget_make_no_calls(self):
        self.store.state['history']['b' * 64] = 'legacy_unconfirmed'
        with self.assertRaises(StateError):
            self.call()
        with self.assertRaises(StateError):
            self.call(limit=0)
        self.request.assert_not_called()

    def test_run_budget_is_persistent(self):
        self.call(limit=1)
        with self.assertRaisesRegex(StateError, 'BUDGET_EXHAUSTED'):
            self.call(key='c' * 64, source='d' * 64, limit=1)

    def test_secret_result_is_not_persisted(self):
        self.request.return_value = {'intro': 'sk-' + 'x' * 32}
        with self.assertRaises(StateError):
            self.call()
        self.assertNotIn('result', self.store.state['calls']['a' * 64])


class GitCASTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.remote = self.root / 'remote.git'
        for args in [('init', '--bare', str(self.remote)), ('init', str(self.repo))]:
            subprocess.run(['git', *args], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.repo), 'remote', 'add', 'origin', str(self.remote)], check=True)
        self.store = GitState(self.repo)

    def tearDown(self):
        # Windows Git object files may be read-only; tempfile handles their cleanup.
        self.temp.cleanup()

    def test_missing_state_fails_closed(self):
        with self.assertRaisesRegex(StateError, 'NOT_INITIALIZED'):
            self.store.read()

    def test_competing_writers_cannot_overwrite_winner(self):
        self.store.update(lambda state: None, initialize=True)
        head, state = self.store.read()
        other = copy.deepcopy(state)
        state['history']['first'] = 'blocked'
        other['history']['second'] = 'blocked'
        self.assertTrue(self.store.commit(head, state))
        self.assertFalse(self.store.commit(head, other))
        self.assertEqual(self.store.read()[1]['history'], {'first': 'blocked'})

    def test_push_acknowledgement_loss_is_reconciled(self):
        self.store.update(lambda state: None, initialize=True)
        original = self.store.git
        def lose_ack(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[0] == 'push':
                raise StateError('ack lost')
            return result
        with patch.object(self.store, 'git', side_effect=lose_ack):
            self.store.update(lambda state: state['history'].update({'known': 'blocked'}))
        self.assertEqual(self.store.read()[1]['history'], {'known': 'blocked'})


class PublisherTests(unittest.TestCase):
    def setUp(self):
        GitCASTests.setUp(self)
        self.store.git('checkout', '-b', 'main')
        (self.repo / 'unrelated.txt').write_text('original')
        self.store.git('add', '.')
        self.store.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-m', 'initial')
        self.store.git('push', 'origin', 'main')

    def tearDown(self):
        GitCASTests.tearDown(self)

    def test_empty_directory_does_not_invoke_gh(self):
        self.assertEqual(publish_candidates.publish(self.repo), {'status': 'empty'})

    def test_dirty_input_worktree_does_not_leak_into_candidate_pr(self):
        (self.repo / 'unrelated.txt').write_text('private dirty edit')
        target = self.repo / 'data/candidates/demo.yaml'
        target.parent.mkdir(parents=True)
        target.write_text(yaml.safe_dump({'candidate_type': 'new_platform', 'status': 'pending_review',
                                         'proposed': {'intro': 'public'}}), encoding='utf-8')
        pulls = []
        original = publish_candidates.command
        def fake_gh(repo, *args, **kwargs):
            if args[0] != 'gh':
                return original(repo, *args, **kwargs)
            if args[1:3] == ('repo', 'view'):
                return subprocess.CompletedProcess(args, 0, json.dumps({'nameWithOwner': 'example/repo'}), '')
            if args[1:3] == ('pr', 'list'):
                return subprocess.CompletedProcess(args, 0, json.dumps(pulls), '')
            if args[1:3] == ('pr', 'create'):
                pulls.append({'number': 1, 'state': 'OPEN', 'headRefName': args[args.index('--head') + 1],
                              'headRepositoryOwner': {'login': 'example'}, 'headRepository': {'name': 'repo'}})
            return subprocess.CompletedProcess(args, 0, '', '')
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'example/repo'}), patch.object(publish_candidates, 'command', side_effect=fake_gh):
            first = publish_candidates.publish(self.repo)
            second = publish_candidates.publish(self.repo)
        self.assertEqual(len(pulls), 1)
        self.assertEqual(first['pr'], second['pr'])
        branch = 'auto/check-' + first['manifest'][:24]
        self.store.git('fetch', 'origin', branch)
        changed = self.store.git('diff', '--name-only', 'main', 'FETCH_HEAD').stdout.splitlines()
        self.assertEqual(changed, ['data/candidates/demo.yaml'])
        self.assertEqual((self.repo / 'unrelated.txt').read_text(), 'private dirty edit')


class ExtractionEntryTests(unittest.TestCase):
    def test_missing_input_is_not_no_changes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sys, 'argv', ['extract', '--dry-run', '--input-dir', directory]):
            self.assertEqual(extract.main(), 1)
            data = json.loads((Path(directory) / 'extract-summary.json').read_text())
            self.assertEqual(data['error'], 'INPUT_MISSING')

    def test_empty_budget_variables_do_not_break_dry_run(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sys, 'argv', ['extract', '--dry-run', '--input-dir', directory]), patch.dict(os.environ, {'CHECK_MAX_CALLS': '', 'CHECK_MAX_OUTPUT_TOKENS': ''}):
            (Path(directory) / 'changed.json').write_text('[]')
            with patch.object(extract, 'execute_llm_call') as request:
                self.assertEqual(extract.main(), 0)
                request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
