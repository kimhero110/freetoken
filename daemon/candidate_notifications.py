"""Select the newest pending version per source; never carry approvals forward."""
import base64
from datetime import datetime
import re
import yaml
from .gh_client import GhError


def newest_candidates(gh, repo, now):
    names = gh.list_candidates()
    if len(names) > 100:
        raise ValueError('CANDIDATE_SCAN_LIMIT')
    latest = {}
    for name in names:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
            raise ValueError('CANDIDATE_ID_INVALID')
        try:
            response = gh._request('GET', f'/repos/{repo}/contents/data/candidates/{name}.yaml?ref=main')
        except GhError as exc:
            if exc.status != 404:
                raise
            response = gh._request('GET', f'/repos/{repo}/contents/data/candidates/{name}.json?ref=main')
        if response.get('size', 0) > 64000:
            raise ValueError('CANDIDATE_TOO_LARGE')
        data = yaml.safe_load(base64.b64decode(response['content']).decode('utf-8'))
        if data.get('candidate_type') != 'platform_update' or data.get('status') != 'pending_review':
            continue
        captured = datetime.fromisoformat(data['captured_at'])
        if captured.tzinfo is None or captured.timestamp() > now + 60:
            raise ValueError('CANDIDATE_TIME_INVALID')
        key = (data['platform_slug'], data['source_url'])
        if key not in latest or captured.timestamp() > latest[key][0]:
            latest[key] = (captured.timestamp(), name, data)
    return [(name, data) for stamp, name, data in latest.values() if 0 <= now-stamp < 48*3600]
