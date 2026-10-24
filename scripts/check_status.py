"""Publish the public check summary from GitHub Actions.

The intake daemon used to rewrite /data/check-public/status.json every five
minutes. That process was removed on 2026-09-23, and nginx on witkit.zone is
still serving the frozen file. This module is the replacement publisher: it
reads workflow runs and the public automation ledger, then fast-forwards
check-status.json on the monitor-status branch.
"""
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .check_heartbeat import explain, healthy

BRANCH = 'monitor-status'
STATUS_FILE = 'check-status.json'
STALE_SOURCE = 3 * 86400
MONITOR_SINCE = datetime(2026, 9, 6, tzinfo=timezone.utc)
WORKFLOWS = ('update.yml', 'discover.yml')
SOURCE_KEYS = ('platform', 'checked_at', 'status', 'scope')
DOCUMENT_KEYS = {
    'version', 'updated_at', 'monitoring', 'notification_failures', 'active_incidents',
    'check_status', 'last_check_at', 'attempted', 'succeeded', 'sources',
}
GOOD_SOURCE = {
    'fetched', 'candidate_ready', 'pending_review', 'deferred', 'reviewed_version',
    'verified_unchanged', 'reviewed_rejected', 'changed', 'baseline_mismatch',
}


class StatusError(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def default_repo():
    repo = os.environ.get('GITHUB_REPOSITORY', 'kimhero110/freetoken').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise StatusError('REPO_INVALID')
    return repo


def status_api_url(repo_name):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo_name):
        raise StatusError('REPO_INVALID')
    return f'https://api.github.com/repos/{repo_name}/contents/{STATUS_FILE}?ref={BRANCH}'


def status_raw_url(repo_name):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo_name):
        raise StatusError('REPO_INVALID')
    return f'https://raw.githubusercontent.com/{repo_name}/{BRANCH}/{STATUS_FILE}'


def stamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return parsed.timestamp()


def expected_slots(workflow, start, now):
    day = datetime.fromtimestamp(start, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    while day.timestamp() <= now:
        # discover.yml is `30 18 */2 * *`: day-of-month 1, 3, 5, ... at 18:30 UTC.
        hours = (17, 20, 23) if workflow == 'update.yml' else ((18,) if day.day % 2 == 1 else ())
        for hour in hours:
            slot = day.replace(hour=hour, minute=30).timestamp()
            if start <= slot <= now:
                yield slot
        day += timedelta(days=1)


def missing_slots(workflow, runs, start, now):
    scheduled = [run for run in runs if run.get('event') == 'schedule' and run.get('head_branch') == 'main']
    return [slot for slot in expected_slots(workflow, start, now - 10800)
            if not any(slot <= stamp(run['created_at']) < slot + 10800 for run in scheduled)]


def _git(repo, *args, data=None, env=None, check=True):
    result = subprocess.run(
        ['git', *args], cwd=repo, input=data, text=True, encoding='utf-8',
        capture_output=True, timeout=60, env=env)
    if check and result.returncode:
        raise StatusError('GIT_OPERATION_FAILED')
    return result


def _read_http(url, token, accept, limit, opener):
    headers = {
        'Accept': accept,
        'User-Agent': 'FreeToken-External-Monitor/1',
        'Cache-Control': 'no-cache',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = Request(url, headers=headers)
    open_fn = opener or urlopen
    try:
        response = open_fn(request, timeout=30)
    except HTTPError as exc:
        return exc.code, b''
    except StatusError:
        raise
    except Exception:
        raise StatusError('GITHUB_UNAVAILABLE') from None
    with response:
        status = getattr(response, 'status', None) or response.getcode()
        raw = response.read(limit + 1)
    return status, raw


def github_json(url, *, token='', accept='application/vnd.github+json', limit=2_000_000, opener=None, attempts=3):
    for attempt in range(attempts):
        try:
            status, raw = _read_http(url, token or None, accept, limit, opener)
        except StatusError as exc:
            if exc.code != 'GITHUB_UNAVAILABLE' or attempt + 1 == attempts:
                raise
            time.sleep(1)
            continue
        if status in (401, 403) and token:
            status, raw = _read_http(url, None, accept, limit, opener)
        if status == 404:
            raise StatusError('STATUS_NOT_PUBLISHED')
        if status == 200:
            if len(raw) > limit:
                raise StatusError('RESPONSE_TOO_LARGE')
            try:
                return json.loads(raw)
            except ValueError:
                raise StatusError('GITHUB_INVALID') from None
        if attempt + 1 < attempts:
            time.sleep(1)
    raise StatusError('GITHUB_UNAVAILABLE')


def _trusted_runs(workflow, runs, repo_name, start):
    if not isinstance(runs, list) or len(runs) > 100:
        raise StatusError('RUN_LIST_INVALID')
    trusted = []
    for run in runs:
        if not isinstance(run, dict) or run.get('head_branch') != 'main':
            continue
        if run.get('path') != f'.github/workflows/{workflow}':
            continue
        if (run.get('repository') or {}).get('full_name') != repo_name:
            continue
        try:
            stamp(run['created_at'])
        except (KeyError, TypeError, ValueError):
            continue
        trusted.append(run)
    if len(runs) >= 100 and trusted and min(stamp(run['created_at']) for run in trusted) > start:
        raise StatusError('RUN_HISTORY_TRUNCATED')
    return trusted


def workflow_problems(workflow, runs, repo_name, start, now):
    trusted = _trusted_runs(workflow, runs, repo_name, start)
    problems = []
    completed = [run for run in trusted if stamp(run['created_at']) >= start and run.get('status') == 'completed']
    latest = max(completed, key=lambda run: (stamp(run['created_at']), run.get('run_attempt') or 1), default=None)
    if latest and latest.get('conclusion') != 'success':
        problems.append(f'workflow:{workflow}:execution')
    overdue = False
    for run in trusted:
        if run.get('status') != 'in_progress' or stamp(run['created_at']) < start:
            continue
        started = run.get('run_started_at') or run['created_at']
        try:
            elapsed = now - stamp(started)
        except (TypeError, ValueError):
            continue
        if elapsed > 2400:
            overdue = True
    if overdue:
        problems.append(f'workflow:{workflow}:running')
    missing = missing_slots(workflow, trusted, start, now)
    last_scheduled = max((stamp(run['created_at']) for run in trusted if run.get('event') == 'schedule'), default=0)
    if missing and max(missing) > last_scheduled:
        problems.append(f'workflow:{workflow}:schedule')
    return problems


def _public_source(item):
    if not isinstance(item, dict):
        return None
    published = {}
    for key in SOURCE_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value and len(value) <= 80 and not any(char in value for char in '\n\r'):
            published[key] = value
    if 'platform' not in published:
        return None
    return published


def ledger_problems(ledger, now):
    if not isinstance(ledger, dict) or ledger.get('version') != 1:
        raise StatusError('LEDGER_SCHEMA')
    if not all(isinstance(ledger.get(key), dict) for key in ('runs', 'calls', 'history')):
        raise StatusError('LEDGER_SCHEMA')
    problems = []
    for key, call in ledger['calls'].items():
        if not re.fullmatch(r'[a-f0-9]{64}', key) or not isinstance(call, dict):
            raise StatusError('CALL_ID_INVALID')
        status = call.get('status')
        unresolved = status in {'uncertain', 'rejected_result'}
        if status == 'intent':
            unresolved = now - stamp(call['created_at']) > 1800
        if unresolved:
            problems.append('call:' + key[:24])
    summaries = [run for run in ledger['runs'].values()
                 if isinstance(run, dict) and run.get('completed_at') and run.get('workflow_file') == 'update.yml']
    observations = {}
    for summary in sorted(summaries, key=lambda run: stamp(run['completed_at'])):
        seen = stamp(summary['completed_at'])
        for stage in ('fetch', 'extract'):
            for item in (summary.get(stage) or {}).get('sources') or []:
                if not isinstance(item, dict) or not re.fullmatch(r'[a-f0-9]{64}', item.get('source', '')):
                    raise StatusError('SOURCE_ID_INVALID')
                observations[(stage, item['source'])] = (item, seen)
    for (stage, source), (item, seen) in observations.items():
        status = item.get('status')
        stale = now - seen > STALE_SOURCE
        if not stale and status in {'failed', 'fetch_failed'}:
            problems.append(f'{stage}:{source[:24]}')
    latest = max(summaries, key=lambda run: stamp(run['completed_at']), default={})
    if latest.get('status') == 'dry_run':
        problems.append('checks:paused')
    fetch = latest.get('fetch') if isinstance(latest.get('fetch'), dict) else {}
    sources = []
    for item in fetch.get('sources') or []:
        published = _public_source(item)
        if published:
            sources.append(published)
    status = latest.get('status')
    summary = {
        'last_check_at': fetch.get('checked_at') if isinstance(fetch.get('checked_at'), str) else '',
        'attempted': fetch.get('attempted') if isinstance(fetch.get('attempted'), int) else -1,
        'succeeded': fetch.get('succeeded') if isinstance(fetch.get('succeeded'), int) else -1,
        'check_status': status if status in {'completed', 'failed', 'dry_run'} else 'unknown',
        'sources': sources[:40],
    }
    return problems, summary


def _unknown_document(now):
    updated = now.astimezone(timezone.utc).isoformat()
    return {
        'version': 1,
        'updated_at': updated,
        'monitoring': 'unknown',
        'notification_failures': 0,
        'active_incidents': 0,
        'check_status': 'unknown',
        'last_check_at': updated,
        'attempted': 0,
        'succeeded': 0,
        'sources': [],
    }


def _summary_displayable(summary):
    try:
        stamp(summary['last_check_at'])
    except (KeyError, TypeError, ValueError):
        return False
    attempted, succeeded = summary['attempted'], summary['succeeded']
    return (isinstance(attempted, int) and isinstance(succeeded, int)
            and 0 <= succeeded <= attempted <= 10000)


def build_status(repo_name, now, *, token='', opener=None):
    """Return (document, active incident ids). Query failures publish monitoring=unknown."""
    if now.tzinfo is None:
        raise StatusError('TIMEZONE_REQUIRED')
    unknown = _unknown_document(now)
    try:
        start = max(MONITOR_SINCE.timestamp(), now.timestamp() - 7 * 86400)
        problems = []
        for workflow in WORKFLOWS:
            url = f'https://api.github.com/repos/{repo_name}/actions/workflows/{workflow}/runs?per_page=100'
            payload = github_json(url, token=token, opener=opener)
            runs = payload.get('workflow_runs') if isinstance(payload, dict) else None
            problems.extend(workflow_problems(workflow, runs, repo_name, start, now.timestamp()))
        ledger_url = f'https://api.github.com/repos/{repo_name}/contents/state.json?ref=automation-state'
        ledger = github_json(ledger_url, token=token, accept='application/vnd.github.raw+json',
                             limit=8_000_000, opener=opener)
        ledger_ids, summary = ledger_problems(ledger, now.timestamp())
        problems.extend(ledger_ids)
        if not _summary_displayable(summary):
            return unknown, []
        document = _unknown_document(now)
        document.update(summary)
        document['monitoring'] = 'ok'
        document['notification_failures'] = 0
        document['active_incidents'] = len(problems)
        canonical_payload(document)
        return document, problems
    except (StatusError, ValueError, KeyError, TypeError):
        return unknown, []


def _reject_secrets(text):
    if re.search(r'(?i)(bearer\s|sk-[a-z0-9]{12,}|-----BEGIN|api[_-]?key\s*[:=])', text):
        raise StatusError('STATUS_SECRET')
    for name, value in os.environ.items():
        if len(value) < 8:
            continue
        if any(word in name for word in ('SECRET', 'TOKEN', 'API_KEY', 'PASSWORD', 'PRIVATE')) and value in text:
            raise StatusError('STATUS_SECRET')


def canonical_payload(document):
    if not isinstance(document, dict) or set(document) != DOCUMENT_KEYS or document.get('version') != 1:
        raise StatusError('STATUS_SCHEMA')
    if document.get('monitoring') not in {'ok', 'unknown'}:
        raise StatusError('STATUS_SCHEMA')
    if document.get('check_status') not in {'completed', 'failed', 'dry_run', 'unknown'}:
        raise StatusError('STATUS_SCHEMA')
    if document.get('notification_failures') != 0:
        raise StatusError('STATUS_SCHEMA')
    incidents = document.get('active_incidents')
    if not isinstance(incidents, int) or not 0 <= incidents <= 10000:
        raise StatusError('STATUS_SCHEMA')
    try:
        stamp(document.get('updated_at'))
        stamp(document.get('last_check_at'))
    except (TypeError, ValueError):
        raise StatusError('STATUS_SCHEMA') from None
    attempted, succeeded = document.get('attempted'), document.get('succeeded')
    if not isinstance(attempted, int) or not isinstance(succeeded, int) or not 0 <= succeeded <= attempted <= 10000:
        raise StatusError('STATUS_SCHEMA')
    sources = document.get('sources')
    if not isinstance(sources, list) or len(sources) > 40:
        raise StatusError('STATUS_SCHEMA')
    for item in sources:
        if not isinstance(item, dict) or not item or set(item) - set(SOURCE_KEYS) or 'platform' not in item:
            raise StatusError('STATUS_SCHEMA')
        for value in item.values():
            if not isinstance(value, str) or not value or len(value) > 80 or any(char in value for char in '\n\r'):
                raise StatusError('STATUS_SCHEMA')
    text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    if len(text.encode()) > 8192:
        raise StatusError('STATUS_TOO_LARGE')
    _reject_secrets(text)
    return text


def _remote_head(repo, remote):
    result = _git(repo, 'ls-remote', '--heads', remote, f'refs/heads/{BRANCH}')
    parts = result.stdout.split()
    if not parts:
        return None
    head = parts[0]
    _git(repo, 'fetch', '--no-tags', remote, head)
    return head


def _remote_payload(repo, head):
    result = subprocess.run(
        ['git', 'cat-file', 'blob', f'{head}:{STATUS_FILE}'], cwd=repo,
        capture_output=True, timeout=60)
    if result.returncode:
        return None
    return result.stdout.decode('utf-8')


def _commit_file(repo, head, payload):
    with tempfile.TemporaryDirectory(prefix='status-index-') as temp:
        env = dict(os.environ)
        env.update({
            'GIT_INDEX_FILE': str(Path(temp) / 'index'),
            'GIT_AUTHOR_NAME': 'freetoken-bot[bot]',
            'GIT_COMMITTER_NAME': 'freetoken-bot[bot]',
            'GIT_AUTHOR_EMAIL': 'freetoken-bot[bot]@users.noreply.github.com',
            'GIT_COMMITTER_EMAIL': 'freetoken-bot[bot]@users.noreply.github.com',
        })
        _git(repo, 'read-tree', '--empty', env=env)
        blob = _git(repo, 'hash-object', '-w', '--stdin', data=payload, env=env).stdout.strip()
        _git(repo, 'update-index', '--add', '--cacheinfo', f'100644,{blob},{STATUS_FILE}', env=env)
        tree = _git(repo, 'write-tree', env=env).stdout.strip()
        parents = ['-p', head] if head else []
        return _git(repo, 'commit-tree', tree, *parents, data='Publish check status\n', env=env).stdout.strip()


def _try_push(repo, remote, commit):
    if _git(repo, 'push', remote, f'{commit}:refs/heads/{BRANCH}', check=False).returncode == 0:
        return True
    try:
        head = _remote_head(repo, remote)
    except StatusError:
        return False
    if not head:
        return False
    return _git(repo, 'merge-base', '--is-ancestor', commit, head, check=False).returncode == 0


def push_status(repo, document, remote='origin'):
    payload = canonical_payload(document)
    for _ in range(3):
        head = _remote_head(repo, remote)
        if head and _remote_payload(repo, head) == payload:
            return
        commit = _commit_file(repo, head, payload)
        if _try_push(repo, remote, commit):
            return
        head = _remote_head(repo, remote)
        if head and _remote_payload(repo, head) == payload:
            return
    raise StatusError('STATUS_PUSH_REJECTED')


def fetch_published(repo_name, *, token='', opener=None):
    return github_json(status_api_url(repo_name), token=token,
                       accept='application/vnd.github.raw+json', limit=8192, opener=opener)


def refresh_public_status(repo, *, now=None, repo_name=None, opener=None, remote='origin', pause=time.sleep):
    repo_name = repo_name or default_repo()
    now = now or datetime.now(timezone.utc)
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''
    incidents = []
    try:
        document, incidents = build_status(repo_name, now, token=token, opener=opener)
        push_status(Path(repo), document, remote=remote)
        published = None
        for attempt in range(3):
            try:
                candidate = fetch_published(repo_name, token=token, opener=opener)
            except StatusError:
                candidate = None
            if isinstance(candidate, dict) and candidate.get('updated_at') == document['updated_at']:
                published = candidate
                break
            if attempt < 2:
                pause(1)
        if published is None:
            raise StatusError('STATUS_NOT_VISIBLE')
        line = explain(published, now) + ' url=' + status_raw_url(repo_name)
        if incidents:
            line += ' incidents=' + ','.join(str(item) for item in incidents[:5])
        return healthy(published, now), line, list(incidents)
    except StatusError as exc:
        return False, 'CHECK_MONITOR_UNAVAILABLE reason=' + exc.code, list(incidents)
