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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import discover_new_platforms as radar


def page(score):
    return {"title": "t", "text": "x", "score": score, "url": "https://x"}


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        env = patch.dict('os.environ', {'RUNNER_TEMP': self.tmp.name})
        env.start(); self.addCleanup(env.stop)

    def sweep(self, seeds, pages, existing=()):
        # ROOT 也要挪开：一个高分命中会把候选 YAML 写进真正的
        # data/candidates，跑一次测试就往仓库里丢一份假平台。
        with patch.object(radar, 'ROOT', Path(self.tmp.name)), \
             patch.object(radar, 'TARGET_SEEDS', list(seeds)), \
             patch.object(radar, 'get_existing_domains', lambda: set(existing)), \
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
                 patch.object(radar, 'extract_page_data', lambda url: page(1)):
                self.assertEqual(radar.run_discovery(), 0)


if __name__ == '__main__':
    unittest.main()
