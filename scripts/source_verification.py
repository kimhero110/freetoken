"""Evidence classification; a successful fetch is not proof of a free account."""
import hashlib
from pathlib import Path
import yaml


def reviewed_status(root, slug, url, source_hash, platform):
    records = []
    for path in (Path(root) / 'data/reviews').glob('*.yaml'):
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('candidate_type') != 'platform_update':
            continue
        if data.get('platform_slug') != slug or data.get('source_url') != url:
            continue
        review = data.get('review', {})
        if review.get('decision') in {'approved', 'rejected'}:
            records.append(data)
    latest = max(records, key=lambda d: d['review'].get('reviewed_at', ''), default=None)
    if latest is None or latest.get('source_hash') != source_hash:
        return 'changed'
    if latest['review']['decision'] == 'rejected':
        return 'reviewed_rejected'
    proposed = latest.get('proposed', {})
    quota = proposed.get('free_quota')
    if not isinstance(quota, dict) or not quota or any(platform.get('free_quota', {}).get(k) != v for k, v in quota.items()):
        return 'baseline_mismatch'
    return 'verified_unchanged'


def public_observation(slug, url, text, platform, root, checked_at):
    source_hash = hashlib.sha256(text.encode('utf-8')).hexdigest() if text is not None else None
    return {'source': hashlib.sha256((slug + url).encode()).hexdigest(),
            'platform': slug, 'url': url, 'checked_at': checked_at,
            'source_hash': source_hash,
            'status': reviewed_status(root, slug, url, source_hash, platform) if text is not None else 'fetch_failed',
            'scope': 'public_source'}
