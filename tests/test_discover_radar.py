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


class DeduplicationAndCooldownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'data' / 'platforms').mkdir(parents=True)
        (self.root / 'data' / 'reviews').mkdir(parents=True)

    def test_get_existing_domains_reads_schema_v2_doc_url_and_registration_url(self):
        (self.root / 'data' / 'platforms' / 'vendor-one.yaml').write_text(yaml.safe_dump({
            'schema_version': 2,
            'slug': 'vendor-one',
            'website': 'https://www.vendorone.ai',
            'doc_url': 'https://docs.vendorone-docs.io/guide',
            'registration': {'url': 'https://console.vendorone-auth.com/signup'},
            'api_base_url': 'https://api.vendorone.ai/v1',
        }), encoding='utf-8')
        (self.root / 'data' / 'platforms' / 'baidu-qianfan.yaml').write_text(yaml.safe_dump({
            'schema_version': 2,
            'slug': 'baidu-qianfan',
            'website': 'https://cloud.baidu.com/product/wenxinworkshop',
            'doc_url': 'https://cloud.baidu.com/doc/WENXINWORKSHOP/index.html',
            'registration': {'url': 'https://console.bce.baidu.com/'},
        }), encoding='utf-8')

        with patch.object(radar, 'ROOT', self.root):
            domains = radar.get_existing_domains()

        self.assertIn('vendorone.ai', domains)
        self.assertIn('docs.vendorone-docs.io', domains)
        self.assertIn('vendorone-docs', domains)
        self.assertIn('console.vendorone-auth.com', domains)
        self.assertIn('vendorone-auth', domains)
        self.assertIn('cloud.baidu.com', domains)
        self.assertNotIn('cloud', domains)
        self.assertNotIn('docs', domains)
        self.assertNotIn('console', domains)

    def test_rejected_reviews_are_skipped_within_90_day_cooldown_and_reopen_after(self):
        from datetime import datetime, timedelta, timezone

        now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
        reviews = self.root / 'data' / 'reviews'
        (reviews / 'aimlapi-rejected.yaml').write_text(yaml.safe_dump({
            'candidate_type': 'new_platform',
            'platform_slug': 'aimlapi',
            'proposed': {
                'slug': 'aimlapi',
                'website': 'https://aimlapi.com',
                'doc_url': 'https://aimlapi.com/docs',
                'registration': {'url': 'https://aimlapi.com/signup'},
            },
            'review': {
                'decision': 'rejected',
                'reviewed_at': (now - timedelta(days=30)).isoformat(),
            },
        }), encoding='utf-8')
        (reviews / 'oldseed-rejected.yaml').write_text(yaml.safe_dump({
            'candidate_type': 'new_platform',
            'platform_slug': 'oldseed',
            'proposed': {
                'slug': 'oldseed',
                'website': 'https://oldseed.example',
            },
            'review': {
                'decision': 'rejected',
                'reviewed_at': (now - timedelta(days=95)).isoformat(),
            },
        }), encoding='utf-8')
        (reviews / 'update-featherless-ai-2c740d9a5f67-rejected.yaml').write_text(yaml.safe_dump({
            'candidate_type': 'platform_update',
            'platform_slug': 'featherless-ai',
            'source_url': 'https://featherless.ai',
            'review': {
                'decision': 'rejected',
                'reviewed_at': (now - timedelta(days=5)).isoformat(),
            },
        }), encoding='utf-8')

        with patch.object(radar, 'ROOT', self.root):
            rejected = radar.get_rejected_domains(now=now)
        self.assertIn('aimlapi', rejected)
        self.assertIn('aimlapi.com', rejected)
        self.assertNotIn('oldseed', rejected)
        self.assertNotIn('featherless.ai', rejected)

        with patch.dict('os.environ', {'RUNNER_TEMP': self.tmp.name}), \
             patch.object(radar, 'ROOT', self.root), \
             patch.object(radar, 'TARGET_SEEDS', ['https://aimlapi.com', 'https://fresh.example']), \
             patch.object(radar, 'get_rejected_domains', lambda: rejected), \
             patch.object(radar, 'api_signature', lambda url: None), \
             patch.object(radar, 'extract_page_data', lambda url: page(5)):
            code = radar.run_discovery()

        self.assertEqual(code, 0)
        summary = json.loads((self.root / 'fetch-summary.json').read_text(encoding='utf-8'))
        by_url = {item['url']: item['status'] for item in summary['sources']}
        self.assertEqual(by_url, {
            'https://aimlapi.com': 'rejected_cooldown',
            'https://fresh.example': 'discovered',
        })
        written = [p.name for p in (self.root / 'data' / 'candidates').glob('*.yaml')]
        self.assertEqual(written, ['fresh.yaml'])



class ExpanderSeedTests(unittest.TestCase):
    """目录页里长出来的域名，才是雷达真正的生长点。"""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'config').mkdir(parents=True)
        (self.root / 'data' / 'platforms').mkdir(parents=True)
        (self.root / 'data' / 'reviews').mkdir(parents=True)
        (self.root / 'data' / 'candidates').mkdir(parents=True)

    def _write_config(self, rows):
        payload = {'expanders': rows}
        (self.root / 'config' / 'discovery-seed-sources.yaml').write_text(
            yaml.safe_dump(payload, allow_unicode=True), encoding='utf-8')

    def test_expanders_contribute_origins_absent_from_target_seeds(self):
        self._write_config([{
            'id': 'demo',
            'url': 'https://lists.example/free.md',
            'enabled': True,
            'max_origins': 10,
        }])
        body = (
            '# Free APIs\n'
            '- [Brand New](https://aifree.dev/offer/x) · [official](https://brand-new-llm.example/pricing)\n'
            '- [Also](https://also-fresh.example/docs)\n'
        )
        with patch.object(radar, 'ROOT', self.root), \
             patch.object(radar, 'TARGET_SEEDS', ['https://already.example']), \
             patch.object(radar, 'get_public_text', lambda url, **kw: body):
            targets = radar.load_seed_targets()
        self.assertIn('https://already.example', targets)
        self.assertIn('https://brand-new-llm.example', targets)
        self.assertIn('https://also-fresh.example', targets)
        # Still not in the hardcoded bootstrap — that is the growth claim.
        self.assertNotIn('https://brand-new-llm.example', radar.TARGET_SEEDS)

    def test_malformed_and_same_host_and_blocked_links_are_ignored(self):
        html = """
        <html><body>
          <a href="http://insecure.example">no</a>
          <a href="mailto:hi@x.example">mail</a>
          <a href="/relative">rel</a>
          <a href="https://lists.example/other">same host</a>
          <a href="https://github.com/foo/bar">social</a>
          <a href="https://twitter.com/x">social</a>
          <a href="https://keep-me.example/path?q=1">yes</a>
        </body></html>
        """
        got = radar.extract_origins_from_document(html, 'https://lists.example/free', 20)
        self.assertEqual(got, ['https://keep-me.example'])

    def test_expander_fetch_failure_does_not_break_seed_loading(self):
        self._write_config([{
            'id': 'broken',
            'url': 'https://lists.example/down.md',
            'enabled': True,
            'max_origins': 5,
        }])
        def boom(url, **kw):
            raise RuntimeError('blocked')
        with patch.object(radar, 'ROOT', self.root), \
             patch.object(radar, 'TARGET_SEEDS', ['https://seed.example']), \
             patch.object(radar, 'get_public_text', boom):
            targets = radar.load_seed_targets()
        self.assertEqual(targets, ['https://seed.example'])

    def test_expanded_origin_still_respects_existing_and_reject_cooldown(self):
        self._write_config([{
            'id': 'demo',
            'url': 'https://lists.example/free.md',
            'enabled': True,
            'max_origins': 10,
        }])
        body = (
            '[official](https://indexed.example/pricing)\n'
            '[official](https://rejected.example/pricing)\n'
            '[official](https://fresh-from-list.example/pricing)\n'
        )
        env = patch.dict('os.environ', {'RUNNER_TEMP': self.tmp.name})
        env.start(); self.addCleanup(env.stop)
        with patch.object(radar, 'ROOT', self.root), \
             patch.object(radar, 'TARGET_SEEDS', []), \
             patch.object(radar, 'get_public_text', lambda url, **kw: body), \
             patch.object(radar, 'get_existing_domains', lambda: {'indexed.example', 'indexed'}), \
             patch.object(radar, 'get_rejected_domains', lambda: {'rejected.example', 'rejected'}), \
             patch.object(radar, 'api_signature', lambda url: None), \
             patch.object(radar, 'extract_page_data',
                          lambda url: page(5) if 'fresh-from-list' in url else None):
            code = radar.run_discovery()
        self.assertEqual(code, 0)
        summary = json.loads((self.root / 'fetch-summary.json').read_text(encoding='utf-8'))
        by_url = {item['url']: item['status'] for item in summary['sources']}
        self.assertEqual(by_url['https://indexed.example'], 'indexed')
        self.assertEqual(by_url['https://rejected.example'], 'rejected_cooldown')
        self.assertEqual(by_url['https://fresh-from-list.example'], 'discovered')
        written = [p.name for p in (self.root / 'data' / 'candidates').glob('*.yaml')]
        self.assertEqual(written, ['fresh-from-list.yaml'])



if __name__ == '__main__':
    unittest.main()
