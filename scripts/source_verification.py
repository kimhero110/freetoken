"""Evidence classification; a successful fetch is not proof of a free account."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse
import yaml

NO_FREE_QUOTA_AMOUNT = '无免费额度'
_API_PATH_RE = re.compile(
    r'(^|/)(?:api/)?v\d+/(?:models|chat/completions|completions|embeddings|audio|images|moderations|rerank|responses)(?:/|$)'
)
_GH_NON_DOC_RE = re.compile(r'^/[^/]+/[^/]+/(?:actions|runs|commit|commits|pull|issues)(?:/|$)')


def source_observation_id(slug: str, url: str) -> str:
    return hashlib.sha256(
        json.dumps([slug, url], sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    ).hexdigest()


def _is_document_evidence_url(url: str, entry: dict) -> bool:
    if not isinstance(url, str):
        return False
    candidate = url.strip()
    if not candidate.startswith('https://'):
        return False
    parsed = urlparse(candidate)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not host:
        return False
    lower_path = (parsed.path or '').lower().rstrip('/')
    if host == 'api.github.com':
        return False
    if host in {'github.com', 'www.github.com'} and _GH_NON_DOC_RE.search(lower_path):
        return False

    doc_whitelist = {
        u.strip().rstrip('/')
        for u in (entry.get('website'), entry.get('doc_url'))
        if isinstance(u, str) and u.strip()
    }
    norm_candidate = candidate.rstrip('/')
    api_prefixes = []
    api_base = entry.get('api_base_url')
    if isinstance(api_base, str) and api_base.strip():
        api_prefixes.append(api_base.strip().rstrip('/'))
    for op in ((entry.get('capabilities') or {}).get('operations') or []):
        if isinstance(op, dict) and isinstance(op.get('endpoint_url'), str) and op['endpoint_url'].strip():
            api_prefixes.append(op['endpoint_url'].strip().rstrip('/'))
    for prefix in api_prefixes:
        if prefix and prefix not in doc_whitelist:
            if norm_candidate == prefix or norm_candidate.startswith(prefix + '/'):
                return False

    if lower_path in {'/v1', '/api/v1', '/v2', '/api/v2', '/graphql'}:
        return False
    if _API_PATH_RE.search(lower_path):
        return False
    if host.startswith('api.') and not any(
        token in lower_path for token in ('/doc', '/pricing', '/guide', '/reference', '/help')
    ):
        return False
    return True


def authorized_source_urls(entry: dict) -> list[str]:
    """Return authorized public documentation/pricing URLs for a platform entry.

    Explicit ``source_urls`` take precedence; when absent or empty, fall back to
    ``evidence[].url`` after filtering out API endpoints and CI/workflow URLs.
    """
    if not isinstance(entry, dict):
        return []
    raw_sources = entry.get('source_urls')
    if isinstance(raw_sources, list):
        explicit: list[str] = []
        for item in raw_sources:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned.startswith('https://') and cleaned not in explicit:
                    explicit.append(cleaned)
        if explicit:
            return explicit

    fallback: list[str] = []
    for item in entry.get('evidence') or []:
        if not isinstance(item, dict):
            continue
        raw_url = item.get('url')
        if isinstance(raw_url, str):
            cleaned = raw_url.strip()
            if cleaned not in fallback and _is_document_evidence_url(cleaned, entry):
                fallback.append(cleaned)
    return fallback


def _quota_matches_platform(quota: dict, platform: dict) -> bool:
    current = platform.get('free_quota')
    if not isinstance(current, dict):
        return False
    if quota.get('amount') is None:
        if current.get('amount') != NO_FREE_QUOTA_AMOUNT or current.get('unit') is not None:
            return False
        return all(
            current.get(k) == v
            for k, v in quota.items()
            if k not in {'amount', 'unit'} and v is not None
        )
    return all(current.get(k) == v for k, v in quota.items() if v is not None)


def latest_review(root, slug, url):
    """Return the latest decided platform-update review for a source."""
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
    return max(records, key=lambda d: d['review'].get('reviewed_at', ''), default=None)


def reviewed_status(root, slug, url, source_hash, platform):
    latest = latest_review(root, slug, url)
    if latest is None or latest.get('source_hash') != source_hash:
        return 'changed'
    if latest['review']['decision'] == 'rejected':
        return 'reviewed_rejected'
    proposed = latest.get('proposed', {})
    quota = proposed.get('free_quota')
    if not isinstance(quota, dict) or not quota or not _quota_matches_platform(quota, platform):
        return 'baseline_mismatch'
    return 'verified_unchanged'


def public_observation(slug, url, text, platform, root, checked_at):
    source_hash = hashlib.sha256(text.encode('utf-8')).hexdigest() if text is not None else None
    return {'source': source_observation_id(slug, url),
            'platform': slug, 'url': url, 'checked_at': checked_at,
            'source_hash': source_hash,
            'status': reviewed_status(root, slug, url, source_hash, platform) if text is not None else 'fetch_failed',
            'scope': 'public_source'}
