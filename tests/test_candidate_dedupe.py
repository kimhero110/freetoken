"""同一个结论不该被重复归档二十七次。

查重原本按来源哈希。这些来源是营销首页，内容天天变、哈希跟着变，而提取结论
可以十五天不动——于是 chutes-ai 攒了 10 条、deepinfra 攒了 13 条待审候选，
每一条都在说同一句「免费额度没了」，没有一条被人看过。
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import extract

ENTRY = {'name': 'Demo', 'source_urls': ['https://example.com'],
         'free_quota': {'amount': 1}, 'intro': 'old'}
PROPOSED = {'free_quota': {'amount': None, 'unit': None, 'type': None, 'conditions': []},
            'intro': '无免费额度'}


class DedupeTests(unittest.TestCase):
    def run_extract(self, directory, pending_age_days, page='第二版页面'):
        root = Path(directory)
        platforms, candidates = root/'platforms', root/'candidates'
        platforms.mkdir(); candidates.mkdir()
        (platforms/'demo.yaml').write_text(yaml.safe_dump(ENTRY))

        first = extract.hashlib.sha256('第一版页面'.encode()).hexdigest()
        waiting = extract.build_update_candidate(ENTRY, 'demo', 'https://example.com', first, '', PROPOSED, {})
        waiting['captured_at'] = (datetime.now(timezone.utc)-timedelta(days=pending_age_days)).isoformat()
        held = candidates/('update-demo-%s.yaml' % first[:12])
        held.write_text(yaml.safe_dump(waiting))

        second = extract.hashlib.sha256(page.encode()).hexdigest()
        (root/'changed.json').write_text(json.dumps(
            [{'platform': 'demo', 'url': 'https://example.com', 'hash': second, 'text': page}]))

        import contextlib, io as _io
        printed = _io.StringIO()
        with patch.object(extract, 'PLATFORMS_DIR', platforms), \
             patch.object(extract, 'CANDIDATES_DIR', candidates), \
             patch.object(sys, 'argv', ['extract', '--input-dir', directory]), \
             patch.dict(os.environ, {'CHECK_PAID_ENABLED': 'true', 'CHECK_MAX_CALLS': '4',
                                     'CHECK_MAX_OUTPUT_TOKENS': '1024'}), \
             patch('scripts.check_state.GitState'), \
             patch.object(extract, 'resolve_providers', return_value={}), \
             patch.object(extract, 'OpenAI') as api, \
             patch.object(extract, 'execute_llm_call') as paid, \
             contextlib.redirect_stdout(printed):
            code = extract.main()
        summary = json.loads([l for l in printed.getvalue().splitlines() if l.startswith('{')][-1])
        return code, held, sorted(p.stem for p in candidates.glob('*.yaml')), api, paid, summary

    def test_a_changed_page_does_not_file_a_second_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            code, held, names, api, paid, _ = self.run_extract(directory, pending_age_days=3)
        self.assertEqual(code, 0)
        self.assertEqual(names, [held.stem])
        # 而且一次模型调用都没发生：人没审之前，再提一次也提不出新东西。
        api.assert_not_called()
        paid.assert_not_called()

    def test_the_run_says_which_proposal_is_holding_the_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            _, held, _, _, _, summary = self.run_extract(directory, pending_age_days=3)
        observed = summary['sources'][0]
        self.assertEqual(observed['status'], 'pending_review')
        self.assertEqual(observed['superseded_by'], held.stem)

    def test_a_proposal_nobody_looked_at_for_a_week_stops_holding_it(self):
        # 否则一个没人管的候选会把这个平台永远挡住，免费额度回来了也看不见。
        with tempfile.TemporaryDirectory() as directory:
            _, _, _, _, _, summary = self.run_extract(directory, pending_age_days=9)
        observed = summary['sources'][0]
        # 本用例没有配置 provider，所以它走到预算检查就停了。关键是它走到了那里——
        # 不再在查重这一步被挡掉。
        self.assertEqual(observed['error'], 'PROVIDER_OR_BUDGET_NOT_CONFIGURED')


if __name__ == '__main__':
    unittest.main()
