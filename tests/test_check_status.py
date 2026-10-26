import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.check_heartbeat import HEARTBEAT_MAX_AGE, explain, healthy
from scripts.check_status import (
    MAX_SOURCES,
    MAX_STATUS_BYTES,
    StatusError,
    canonical_payload,
    fetch_published,
    ledger_problems,
    missing_slots,
    refresh_public_status,
    source_failure_streaks,
    stamp,
    status_raw_url,
    update_workflow_deferred,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def git(*args, cwd):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True)


class Response:
    def __init__(self, body, status=200):
        self.status = status
        self._body = body.encode() if isinstance(body, str) else body

    def read(self, limit=-1):
        if limit is None or limit < 0 or limit > len(self._body):
            return self._body
        return self._body[:limit]

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class HeartbeatWindowTests(unittest.TestCase):
    def document(self, updated_at):
        return {'version': 1, 'monitoring': 'ok', 'notification_failures': 0, 'updated_at': updated_at}

    def test_frozen_daemon_file_is_still_a_failed_heartbeat(self):
        frozen = self.document('2026-09-23T04:34:36.123415+00:00')
        self.assertFalse(healthy(frozen, NOW))
        self.assertIn('stale', explain(frozen, NOW))

    def test_publisher_delay_under_eight_hours_stays_healthy(self):
        recent = self.document((NOW - timedelta(hours=7, minutes=59)).isoformat())
        self.assertTrue(healthy(recent, NOW))
        boundary = self.document((NOW - timedelta(seconds=HEARTBEAT_MAX_AGE)).isoformat())
        self.assertTrue(healthy(boundary, NOW))
        overdue = self.document((NOW - timedelta(seconds=HEARTBEAT_MAX_AGE + 1)).isoformat())
        self.assertFalse(healthy(overdue, NOW))

    def test_monitoring_and_notification_failures_still_fail_closed(self):
        self.assertFalse(healthy({'version': 1, 'monitoring': 'unknown', 'notification_failures': 0,
                                  'updated_at': NOW.isoformat()}, NOW))
        self.assertFalse(healthy({'version': 1, 'monitoring': 'ok', 'notification_failures': 2,
                                  'updated_at': NOW.isoformat()}, NOW))


class ScheduleAndLedgerTests(unittest.TestCase):
    def test_long_daytime_gap_does_not_imply_missing_run(self):
        start = stamp('2026-09-06T00:00:00Z')
        now = stamp('2026-09-06T16:00:00Z')
        self.assertEqual(missing_slots('update.yml', [], start, now), [])

    def test_manual_run_cannot_cover_missing_schedule(self):
        start = stamp('2026-09-06T17:00:00Z')
        now = stamp('2026-09-06T21:00:00Z')
        run = {'event': 'workflow_dispatch', 'head_branch': 'main', 'created_at': '2026-09-06T18:00:00Z'}
        self.assertEqual(len(missing_slots('update.yml', [run], start, now)), 1)
        run['event'] = 'schedule'
        self.assertEqual(missing_slots('update.yml', [run], start, now), [])

    def test_recent_failure_counts_and_stale_or_deferred_do_not(self):
        fresh = 'b' * 64
        stale = 'a' * 64
        waiting = 'c' * 64
        ledger = {'version': 1, 'calls': {}, 'history': {}, 'runs': {'1': {
            'completed_at': '2026-09-01T00:00:00Z', 'workflow_file': 'update.yml', 'status': 'completed',
            'fetch': {'sources': []},
            'extract': {'sources': [{'source': stale, 'status': 'failed'}]}},
            '2': {
            'completed_at': '2026-10-24T11:00:00Z', 'workflow_file': 'update.yml', 'status': 'completed',
            'fetch': {'checked_at': '2026-10-24T11:00:00Z', 'attempted': 2, 'succeeded': 2, 'sources': []},
            'extract': {'sources': [
                {'source': fresh, 'status': 'failed'},
                {'source': waiting, 'status': 'deferred'}]}}}}
        problems, _summary = ledger_problems(ledger, NOW.timestamp())
        self.assertEqual(problems, ['extract:' + fresh[:24]])

    def test_pending_review_is_not_an_incident(self):
        source = 'd' * 64
        ledger = {'version': 1, 'calls': {}, 'history': {}, 'runs': {'1': {
            'completed_at': '2026-10-24T11:00:00Z', 'workflow_file': 'update.yml', 'status': 'completed',
            'fetch': {'checked_at': '2026-10-24T11:00:00Z', 'attempted': 1, 'succeeded': 1, 'sources': [
                {'source': source, 'status': 'fetch_failed'}]},
            'extract': {'sources': [
                {'source': 'e' * 64, 'status': 'pending_review'},
                {'source': 'f' * 64, 'status': 'deferred'}]}}}}
        problems, _summary = ledger_problems(ledger, NOW.timestamp())
        self.assertEqual(problems, ['fetch:' + source[:24]])

    def test_streak_counts_consecutive_failures_and_resets(self):
        source = 'b' * 64
        other = 'c' * 64

        def run(stamp, source, status):
            return {
                'completed_at': stamp, 'workflow_file': 'update.yml', 'status': 'failed',
                'fetch': {'sources': [{'source': other, 'status': 'fetch_failed'}]},
                'extract': {'sources': [{'source': source, 'status': status}]},
            }

        ledger = {'version': 1, 'calls': {}, 'history': {}, 'runs': {
            '1': run('2026-10-22T01:00:00Z', source, 'failed'),
            '2': run('2026-10-22T20:00:00Z', source, 'failed'),
            '3': run('2026-10-23T01:00:00Z', source, 'pending_review'),
            '4': run('2026-10-23T20:00:00Z', source, 'failed'),
        }}
        streaks = source_failure_streaks(ledger, NOW.timestamp())
        self.assertEqual(streaks['extract:' + source[:24]], 1)
        self.assertEqual(streaks['fetch:' + other[:24]], 4)
        ledger['runs']['3']['extract']['sources'][0]['status'] = 'failed'
        streaks = source_failure_streaks(ledger, NOW.timestamp())
        self.assertEqual(streaks['extract:' + source[:24]], 4)
        self.assertEqual(source_failure_streaks(ledger, (NOW + timedelta(days=4)).timestamp()), {})

    def test_deferred_pause_is_not_a_workflow_outage(self):
        source = 'e' * 64
        ledger = {'version': 1, 'calls': {}, 'history': {}, 'runs': {'1': {
            'completed_at': '2026-10-24T01:15:00Z', 'workflow_file': 'update.yml', 'status': 'failed',
            'fetch': {'sources': [{'source': source, 'status': 'changed'}]},
            'extract': {'status': 'deferred', 'sources': [
                {'source': source, 'status': 'deferred'},
                {'source': 'f' * 64, 'status': 'pending_review'},
            ]}}}}
        self.assertTrue(update_workflow_deferred(ledger))
        ledger['runs']['1']['extract']['sources'].append({'source': 'a' * 64, 'status': 'failed'})
        self.assertFalse(update_workflow_deferred(ledger))

    def test_secret_material_is_not_publishable(self):
        document = {
            'version': 1, 'updated_at': NOW.isoformat(), 'monitoring': 'ok', 'notification_failures': 0,
            'active_incidents': 0, 'check_status': 'completed', 'last_check_at': NOW.isoformat(),
            'attempted': 1, 'succeeded': 1, 'sources': [{'platform': 'sk-' + 'a' * 20, 'status': 'changed'}],
        }
        with self.assertRaises(StatusError) as caught:
            canonical_payload(document)
        self.assertEqual(caught.exception.code, 'STATUS_SECRET')

    def test_status_supports_up_to_200_sources_and_64kb_payload(self):
        self.assertEqual(MAX_SOURCES, 200)
        self.assertEqual(MAX_STATUS_BYTES, 65536)
        sources_in_ledger = [
            {
                'source': f'{index:064x}',
                'platform': f'platform-{index:03d}',
                'checked_at': NOW.isoformat(),
                'status': 'verified_unchanged',
                'scope': 'public_source',
            }
            for index in range(205)
        ]
        ledger = {
            'version': 1, 'calls': {}, 'history': {},
            'runs': {'1': {
                'completed_at': NOW.isoformat(),
                'workflow_file': 'update.yml',
                'status': 'completed',
                'fetch': {
                    'checked_at': NOW.isoformat(),
                    'attempted': 205,
                    'succeeded': 205,
                    'sources': sources_in_ledger,
                },
                'extract': {'sources': []},
            }},
        }
        problems, summary = ledger_problems(ledger, NOW.timestamp())
        self.assertEqual(problems, [])
        self.assertEqual(len(summary['sources']), 200)
        document = {
            'version': 1,
            'updated_at': NOW.isoformat(),
            'monitoring': 'ok',
            'notification_failures': 0,
            'active_incidents': 0,
            **summary,
        }
        payload = canonical_payload(document)
        self.assertGreater(len(payload.encode()), 8192)
        self.assertLessEqual(len(payload.encode()), MAX_STATUS_BYTES)

        fetched = fetch_published('example/repo', opener=lambda _req, timeout=30: Response(payload))
        self.assertEqual(len(fetched['sources']), 200)

        too_many = {**document, 'sources': summary['sources'] + [summary['sources'][0]]}
        with self.assertRaises(StatusError) as schema_err:
            canonical_payload(too_many)
        self.assertEqual(schema_err.exception.code, 'STATUS_SCHEMA')

        telemetry = (ROOT / 'site/src/components/TelemetrySweep.astro').read_text(encoding='utf-8')
        self.assertIn(f'text.length > {MAX_STATUS_BYTES}', telemetry)
        self.assertNotIn('text.length > 8192', telemetry)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.remote = self.root / 'remote.git'
        git('init', '--bare', str(self.remote), cwd=self.root)
        git('init', '-b', 'main', str(self.repo), cwd=self.root)
        git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
            'commit', '--allow-empty', '-m', 'init', cwd=self.repo)
        git('remote', 'add', 'origin', str(self.remote), cwd=self.repo)
        git('push', 'origin', 'main', cwd=self.repo)
        self.main = git('rev-parse', 'HEAD', cwd=self.repo).stdout.strip()

    def tearDown(self):
        self.temp.cleanup()

    def ledger(self):
        fresh = 'b' * 64
        return {'version': 1, 'calls': {}, 'history': {}, 'runs': {'1': {
            'completed_at': '2026-10-24T11:00:00Z', 'workflow_file': 'update.yml', 'status': 'completed',
            'fetch': {'checked_at': '2026-10-24T11:00:00Z', 'attempted': 1, 'succeeded': 1,
                      'sources': [{'platform': 'demo', 'checked_at': '2026-10-24T11:00:00Z',
                                   'status': 'changed', 'scope': 'public_source', 'source': 'd' * 64}]},
            'extract': {'sources': [{'source': fresh, 'status': 'failed'}]}}}}

    def opener(self, request, timeout=30):
        del timeout
        url = request.full_url
        if '/actions/workflows/' in url:
            workflow = 'update.yml' if 'update.yml' in url else 'discover.yml'
            body = {'workflow_runs': [{
                'event': 'schedule', 'head_branch': 'main', 'status': 'completed', 'conclusion': 'success',
                'run_attempt': 1, 'created_at': '2026-10-24T11:30:00Z',
                'path': f'.github/workflows/{workflow}',
                'repository': {'full_name': 'example/repo'}}]}
        elif 'state.json' in url:
            body = self.ledger()
        elif 'check-status.json' in url:
            show = subprocess.run(
                ['git', '--git-dir', str(self.remote), 'cat-file', 'blob',
                 'refs/heads/monitor-status:check-status.json'],
                capture_output=True, check=True)
            return Response(show.stdout)
        else:
            raise AssertionError(url)
        return Response(json.dumps(body))

    def test_refresh_publishes_without_touching_main_and_keeps_real_incidents(self):
        ok, detail, incidents, context = refresh_public_status(
            self.repo, now=NOW, repo_name='example/repo', opener=self.opener, pause=lambda _seconds: None)
        self.assertTrue(ok)
        self.assertEqual(incidents, ['extract:' + ('b' * 24)])
        self.assertEqual(context['streaks'], {'extract:' + ('b' * 24): 1})
        self.assertFalse(context['workflow_deferred'])
        self.assertIn('CHECK_MONITOR_OK', detail)
        self.assertIn('active_incidents=1', detail)
        self.assertIn('incidents=extract:' + ('b' * 24), detail)
        self.assertIn(status_raw_url('example/repo'), detail)
        self.assertEqual(git('rev-parse', 'HEAD', cwd=self.repo).stdout.strip(), self.main)
        self.assertEqual(git('status', '--porcelain', cwd=self.repo).stdout, '')
        published = subprocess.run(
            ['git', '--git-dir', str(self.remote), 'cat-file', 'blob', 'refs/heads/monitor-status:check-status.json'],
            capture_output=True, check=True).stdout
        document = json.loads(published)
        self.assertEqual(document['updated_at'], NOW.isoformat())
        self.assertEqual(document['monitoring'], 'ok')
        self.assertEqual(document['active_incidents'], 1)
        self.assertEqual(document['sources'][0]['platform'], 'demo')
        self.assertNotIn('source', document['sources'][0])

    def test_site_and_probe_share_the_published_url(self):
        url = status_raw_url('kimhero110/freetoken')
        self.assertIn(url, (ROOT / 'site/src/components/TelemetrySweep.astro').read_text(encoding='utf-8'))
        self.assertIn(url, (ROOT / 'site/src/components/SourceVerification.astro').read_text(encoding='utf-8'))
        self.assertIn(url, (ROOT / 'site/public/_headers').read_text(encoding='utf-8'))
        self.assertNotIn('witkit.zone/ops/check-status.json',
                         (ROOT / 'scripts/check_external_monitor.py').read_text(encoding='utf-8'))
        workflow = (ROOT / '.github/workflows/check-monitor.yml').read_text(encoding='utf-8')
        self.assertIn('GH_TOKEN: ${{ steps.app-token.outputs.token }}', workflow)
        self.assertIn('FEISHU_WEBHOOK_URL', workflow)
        self.assertIn('FEISHU_SECRET', workflow)
        self.assertIn('python -m scripts.check_external_monitor', workflow)
        self.assertIn('INCIDENT_ALERT_MIN_STREAK', workflow)
        self.assertIn('INCIDENT_DIGEST', workflow)
        monitor = (ROOT / 'scripts/check_external_monitor.py').read_text(encoding='utf-8')
        self.assertIn('notify_incidents', monitor)
        self.assertIn('notify_digest', monitor)


if __name__ == '__main__':
    unittest.main()
