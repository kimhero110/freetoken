import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_summary
from scripts.check_summary import stage_failed


class RecordingState:
    def update(self, mutate):
        state = {'runs': {}}
        mutate(state)
        return state


class SummaryOutcomeTests(unittest.TestCase):
    def result(self, **changes):
        result = {
            'stages': {'fetch': 'success', 'extract': 'success', 'publish': 'success'},
            'fetch': {'attempted': 52, 'succeeded': 44},
            'extract': {'status': 'completed'},
        }
        result.update(changes)
        return result

    def test_partial_fetch_and_budget_deferral_are_not_fatal(self):
        result = self.result(
            stages={'fetch': 'failure', 'extract': 'failure', 'publish': 'success'},
            extract={'status': 'deferred', 'sources': [
                {'source': 'a' * 64, 'status': 'candidate_ready'},
                {'source': 'b' * 64, 'status': 'skipped_budget',
                 'error': 'RUN_BUDGET_EXHAUSTED'},
            ]},
        )
        self.assertFalse(stage_failed(result))

    def test_severely_degraded_fetch_is_fatal(self):
        result = self.result(
            stages={'fetch': 'failure', 'extract': 'success', 'publish': 'success'},
            fetch={'attempted': 10, 'succeeded': 4},
        )
        self.assertTrue(stage_failed(result))

    def test_real_extract_or_publish_failure_is_fatal(self):
        result = self.result(
            stages={'fetch': 'success', 'extract': 'failure', 'publish': 'success'},
            extract={'status': 'failed', 'error': 'CHECK_FAILED'},
        )
        self.assertTrue(stage_failed(result))
        result = self.result(
            stages={'fetch': 'success', 'extract': 'success', 'publish': 'failure'})
        self.assertTrue(stage_failed(result))

    def test_main_returns_zero_for_partial_success(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'fetch-summary.json').write_text(json.dumps({
                'attempted': 52, 'succeeded': 44, 'sources': [],
            }))
            (folder / 'extract-summary.json').write_text(json.dumps({
                'status': 'deferred', 'sources': [
                    {'source': 'a' * 64, 'status': 'candidate_ready'},
                    {'source': 'b' * 64, 'status': 'skipped_budget'},
                ],
            }))
            (folder / 'publish-summary.json').write_text(json.dumps({
                'status': 'pr_created', 'pr': 147,
            }))
            env = {'RUNNER_TEMP': directory, 'FETCH_OUTCOME': 'failure',
                   'EXTRACT_OUTCOME': 'failure', 'PUBLISH_OUTCOME': 'success'}
            with patch.dict(os.environ, env, clear=False), \
                 patch.object(check_summary, 'GitState', return_value=RecordingState()):
                self.assertEqual(check_summary.main(), 0)
            result = json.loads((folder / 'run-summary.json').read_text())
            self.assertEqual(result['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
