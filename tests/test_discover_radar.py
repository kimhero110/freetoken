# -*- coding: utf-8 -*-
"""雷达扫不到东西，和雷达坏了，是两回事。

以前只要 13 个种子里有一个不应答，整次定时运行就是红的。连续失败十天，
没有任何地方说过一句话——因为红叉本身已经变成常态。
"""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import discover_new_platforms as radar


def page(score):
    return {"title": "t", "text": "x", "score": score, "url": "https://x"}


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict('os.environ', {'RUNNER_TEMP': self.tmp.name})
        env.start(); self.addCleanup(env.stop)

    def sweep(self, seeds, pages, existing=(), apis=None):
        # ROOT 也要挪开：一个高分命中会把候选 YAML 写进真正的
        # data/candidates，跑一次测试就往仓库里丢一份假平台。
        apis = apis or {}
        with patch.object(radar, 'ROOT', Path(self.tmp.name)), \
             patch.object(radar, 'TARGET_SEEDS', list(seeds)), \
             patch.object(radar, 'get_existing_domains', lambda: set(existing)), \
             patch.object(radar, 'api_signature', lambda url: apis.get(url)), \
             patch.object(radar, 'extract_page_data', lambda url: pages.get(url)):
            code = radar.run_discovery()
        path = Path(self.tmp.name)/'fetch-summary.json'
        summary = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        return code, summary

    def test_an_unreachable_seed_does_not_fail_the_sweep(self):
        code, _ = self.sweep(['https://up.example', 'https://down.example'],
                             {'https://up.example': page(1)})
        self.assertEqual(code, 0)

    def test_finding_nothing_new_is_a_normal_outcome(self):
        code, _ = self.sweep(['https://up.example'], {'https://up.example': page(0)})
        self.assertEqual(code, 0)

    def test_a_total_blackout_is_still_a_failure(self):
        code, _ = self.sweep(['https://a.example', 'https://b.example'], {})
        self.assertEqual(code, 1)

    def test_a_sweep_with_nothing_left_to_probe_is_not_a_failure(self):
        code, summary = self.sweep(['https://a.example'], {}, existing={'a.example'})
        self.assertEqual(code, 0)
        self.assertEqual([s['status'] for s in summary['sources']], ['indexed'])

    def test_the_summary_names_every_seed_and_what_happened_to_it(self):
        _, summary = self.sweep(['https://up.example', 'https://down.example', 'https://old.example'],
                                {'https://up.example': page(5)}, existing={'old.example'})
        got = {s['url']: s['status'] for s in summary['sources']}
        self.assertEqual(got, {'https://up.example': 'discovered',
                               'https://down.example': 'probe_failed',
                               'https://old.example': 'indexed'})
        self.assertEqual(summary['attempted'], 3)
        self.assertEqual(summary['succeeded'], 2)

    def test_an_unreachable_seed_says_why(self):
        _, summary = self.sweep(['https://down.example'], {})
        entry = summary['sources'][0]
        self.assertEqual(entry['error'], 'SEED_UNREACHABLE')

    def test_a_seed_keeps_its_identity_between_sweeps(self):
        # 来源 id 认的是种子地址，不是页面内容：被挡了一个月的目标，
        # 每次都还是同一个它，而不是每次都是新面孔。
        first = self.sweep(['https://down.example'], {})[1]['sources'][0]['source']
        second = self.sweep(['https://down.example'], {})[1]['sources'][0]['source']
        self.assertEqual(first, second)

    def test_a_high_scoring_hit_is_written_as_a_candidate(self):
        self.sweep(['https://up.example'], {'https://up.example': page(5)})
        written = list((Path(self.tmp.name)/'data'/'candidates').glob('*.yaml'))
        self.assertEqual([p.name for p in written], ['up.yaml'])

    def test_a_missing_runner_temp_does_not_break_the_sweep(self):
        with patch.dict('os.environ', {}, clear=True):
            with patch.object(radar, 'ROOT', Path(self.tmp.name)), \
                 patch.object(radar, 'TARGET_SEEDS', ['https://up.example']), \
                 patch.object(radar, 'get_existing_domains', lambda: set()), \
                 patch.object(radar, 'api_signature', lambda url: None), \
                 patch.object(radar, 'extract_page_data', lambda url: page(1)):
                self.assertEqual(radar.run_discovery(), 0)


class SignalTests(unittest.TestCase):
    """落地页读不出东西，不代表这个站没有 API。"""

    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict('os.environ', {'RUNNER_TEMP': self.tmp.name})
        env.start(); self.addCleanup(env.stop)

    def sweep(self, seeds, pages, apis=None, existing=()):
        apis = apis or {}
        with patch.object(radar, 'ROOT', Path(self.tmp.name)), \
             patch.object(radar, 'TARGET_SEEDS', list(seeds)), \
             patch.object(radar, 'get_existing_domains', lambda: set(existing)), \
             patch.object(radar, 'api_signature', lambda url: apis.get(url)), \
             patch.object(radar, 'extract_page_data', lambda url: pages.get(url)):
            code = radar.run_discovery()
        summary = json.loads((Path(self.tmp.name)/'fetch-summary.json').read_text(encoding='utf-8'))
        drafts = {p.stem: yaml.safe_load(p.read_text(encoding='utf-8'))
                  for p in (Path(self.tmp.name)/'data'/'candidates').glob('*.yaml')}
        return code, summary, drafts

    def test_an_openai_endpoint_qualifies_a_site_its_homepage_would_not(self):
        # doubao、chatglm、modelbest 的首页抓下来是一串空壳，关键词得分 0；
        # 它们的 /v1/models 一个请求就回 401，这件事本身就说明了一切。
        sign = {'endpoint': 'https://api.shell.example/v1/models', 'evidence': 'HTTP 401 需要鉴权'}
        _, summary, drafts = self.sweep(['https://shell.example'],
                                        {'https://shell.example': page(0)},
                                        {'https://shell.example': sign})
        self.assertEqual(summary['sources'][0]['status'], 'discovered')
        self.assertTrue(summary['sources'][0]['openai_compatible'])
        self.assertIn('shell', drafts)

    def test_the_detected_endpoint_becomes_the_api_base(self):
        # 以前一律写 {website}/v1，几乎每一家都是错的——真正的地址在 api.<域名> 上。
        sign = {'endpoint': 'https://api.shell.example/v1/models', 'evidence': 'HTTP 401 需要鉴权'}
        _, _, drafts = self.sweep(['https://shell.example'],
                                  {'https://shell.example': page(0)},
                                  {'https://shell.example': sign})
        self.assertEqual(drafts['shell']['proposed']['api_base_url'],
                         'https://api.shell.example/v1')
        self.assertIn('OpenAI 兼容', drafts['shell']['proposed']['tags'])

    def test_without_an_endpoint_the_guessed_base_is_still_used(self):
        _, _, drafts = self.sweep(['https://wordy.example'], {'https://wordy.example': page(5)})
        self.assertEqual(drafts['wordy']['proposed']['api_base_url'], 'https://wordy.example/v1')
        self.assertNotIn('OpenAI 兼容', drafts['wordy']['proposed']['tags'])

    def test_a_site_answering_only_at_its_endpoint_is_not_unreachable(self):
        sign = {'endpoint': 'https://api.dark.example/v1/models', 'evidence': 'HTTP 401 需要鉴权'}
        code, summary, drafts = self.sweep(['https://dark.example'], {}, {'https://dark.example': sign})
        self.assertEqual(code, 0)
        self.assertEqual(summary['sources'][0]['status'], 'discovered')
        self.assertIn('dark', drafts)

    def test_neither_page_nor_endpoint_is_unreachable(self):
        _, summary, _ = self.sweep(['https://gone.example'], {})
        self.assertEqual(summary['sources'][0]['status'], 'probe_failed')

    def test_a_sweep_does_not_hand_the_queue_more_than_it_can_read(self):
        seeds = ['https://s%02d.example' % i for i in range(20)]
        pages = {u: page(5) for u in seeds}
        _, _, drafts = self.sweep(seeds, pages)
        self.assertEqual(len(drafts), radar.CANDIDATE_LIMIT)

    def test_an_endpoint_is_worth_about_three_keywords(self):
        seeds = ['https://s%02d.example' % i for i in range(radar.CANDIDATE_LIMIT)]
        pages = {u: page(4) for u in seeds}
        # 有端点但页面平淡的，排得上；页面读得好的，不该被它挤掉。
        seeds += ['https://quiet.example', 'https://wordy.example']
        pages['https://quiet.example'] = page(2)
        pages['https://wordy.example'] = page(6)
        apis = {'https://quiet.example': {'endpoint': 'https://api.quiet.example/v1/models',
                                          'evidence': 'HTTP 401 需要鉴权'}}
        _, _, drafts = self.sweep(seeds, pages, apis)
        self.assertIn('quiet', drafts)
        self.assertIn('wordy', drafts)
        self.assertEqual(len(drafts), radar.CANDIDATE_LIMIT)

    def test_a_candidate_already_waiting_is_not_written_again(self):
        folder = Path(self.tmp.name)/'data'/'candidates'
        folder.mkdir(parents=True)
        (folder/'wordy.yaml').write_text('old: true\n', encoding='utf-8')
        self.sweep(['https://wordy.example'], {'https://wordy.example': page(5)})
        self.assertEqual((folder/'wordy.yaml').read_text(encoding='utf-8'), 'old: true\n')

    def test_a_draft_does_not_claim_a_free_tier_nobody_checked(self):
        # 雷达只证明了这个站存在、像个 API 平台。"探测到免费额度"是它没有
        # 权利替对方说的话，而这份草稿是要上公开站点的。
        _, _, drafts = self.sweep(['https://wordy.example'], {'https://wordy.example': page(5)})
        quota = drafts['wordy']['proposed']['free_quota']
        self.assertEqual(quota['amount'], '待核实')
        self.assertIn('待人工核实', drafts['wordy']['proposed']['intro'])

    def test_the_evidence_lists_every_page_the_sweep_actually_read(self):
        found = dict(page(5), page='https://wordy.example/pricing')
        sign = {'endpoint': 'https://api.wordy.example/v1/models', 'evidence': 'HTTP 401 需要鉴权'}
        _, _, drafts = self.sweep(['https://wordy.example'], {'https://wordy.example': found},
                                  {'https://wordy.example': sign})
        urls = [e['url'] for e in drafts['wordy']['proposed']['evidence']]
        self.assertEqual(urls, ['https://wordy.example', 'https://wordy.example/pricing',
                                'https://api.wordy.example/v1/models'])


class PageReadingTests(unittest.TestCase):
    """首页不是整个站，对这些站来说还是信息最少的那一页。"""

    def pages(self, bodies):
        def read(url):
            if url not in bodies:
                raise RuntimeError('404')
            return {'title': bodies[url][0], 'text': bodies[url][1],
                    'score': radar.score_text(bodies[url][1]), 'url': url}
        return patch.object(radar, 'read_page', read)

    def test_pricing_can_carry_a_site_its_homepage_could_not(self):
        with self.pages({'https://x.example': ('X', 'welcome'),
                         'https://x.example/pricing': ('', 'free tier api key pricing tokens')}):
            found = radar.extract_page_data('https://x.example')
        self.assertGreaterEqual(found['score'], 3)
        self.assertEqual(found['page'], 'https://x.example/pricing')

    def test_the_name_comes_from_the_front_page_not_the_best_page(self):
        with self.pages({'https://x.example': ('X 平台', 'welcome'),
                         'https://x.example/docs': ('', 'free tier api key pricing tokens')}):
            found = radar.extract_page_data('https://x.example')
        self.assertEqual(found['title'], 'X 平台')

    def test_a_site_where_nothing_can_be_read_returns_nothing(self):
        with self.pages({}):
            self.assertIsNone(radar.extract_page_data('https://x.example'))


if __name__ == '__main__':
    unittest.main()
