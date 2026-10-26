import unittest, tempfile, hashlib
from pathlib import Path
from unittest.mock import patch
import requests, yaml
from scripts.check_state import digest
from scripts.source_verification import public_observation
from scripts.fetch_sources import fetch_text

class SourceVerificationTests(unittest.TestCase):
    def classify(self, decision='approved', quota=None, text='terms'):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'data/reviews').mkdir(parents=True)
            record={'candidate_type':'platform_update','platform_slug':'demo','source_url':'https://example.com',
                    'source_hash':hashlib.sha256(b'terms').hexdigest(),
                    'proposed':{'free_quota':{'amount':10}},'review':{'decision':decision,'reviewed_at':'2026-09-06'}}
            (root/'data/reviews/demo.yaml').write_text(yaml.safe_dump(record),encoding='utf-8')
            return public_observation('demo','https://example.com',text,{'free_quota':quota or {'amount':10}},root,'2026-09-06T00:00:00+00:00')
    def test_approved_matching_source_is_automatically_verified(self):
        self.assertEqual(self.classify()['status'],'verified_unchanged')
    def test_rejection_is_never_verification(self):
        self.assertEqual(self.classify('rejected')['status'],'reviewed_rejected')
    def test_canonical_drift_does_not_pass(self):
        self.assertEqual(self.classify(quota={'amount':20})['status'],'baseline_mismatch')
    def test_changed_source_needs_review(self):
        self.assertEqual(self.classify(text='new terms')['status'],'changed')
    def test_failure_does_not_assert_expired_or_verified(self):
        self.assertEqual(self.classify(text=None)['status'],'fetch_failed')
    def test_timeout_retry_is_bounded_and_recovers(self):
        with patch('scripts.fetch_sources.get_public_text',side_effect=[requests.Timeout(),'<p>terms</p>']) as get, patch('scripts.fetch_sources.time.sleep'):
            self.assertEqual(fetch_text('https://example.com'),'terms')
            self.assertEqual(get.call_count,2)
        with patch('scripts.fetch_sources.get_public_text',side_effect=requests.Timeout()) as get, patch('scripts.fetch_sources.time.sleep'):
            self.assertIsNone(fetch_text('https://example.com'))
            self.assertEqual(get.call_count,3)
    def test_policy_rejection_is_not_retried(self):
        with patch('scripts.fetch_sources.get_public_text',side_effect=ValueError('blocked')) as get:
            self.assertIsNone(fetch_text('https://example.com'))
            get.assert_called_once()
    def test_empty_page_is_not_success(self):
        with patch('scripts.fetch_sources.get_public_text',return_value='<script>empty</script>'):
            self.assertIsNone(fetch_text('https://example.com'))
    def test_observation_source_id_matches_check_state_digest(self):
        obs = self.classify()
        self.assertEqual(obs['source'], digest(['demo', 'https://example.com']))
    def test_approved_null_amount_matches_explicit_no_free_quota_platform(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'data/reviews').mkdir(parents=True)
            record = {
                'candidate_type': 'platform_update',
                'platform_slug': 'demo',
                'source_url': 'https://example.com',
                'source_hash': hashlib.sha256(b'no free tier').hexdigest(),
                'proposed': {'free_quota': {'amount': None, 'unit': None, 'type': None, 'conditions': []}},
                'review': {'decision': 'approved', 'reviewed_at': '2026-10-25'},
            }
            (root / 'data/reviews/demo-approved.yaml').write_text(yaml.safe_dump(record), encoding='utf-8')
            updated_platform = {'free_quota': {'amount': '无免费额度', 'unit': None, 'type': '无免费层', 'conditions': []}}
            stale_platform = {'free_quota': {'amount': '5', 'unit': 'USD', 'type': '一次性', 'conditions': []}}
            ok_obs = public_observation('demo', 'https://example.com', 'no free tier', updated_platform, root, '2026-10-25T00:00:00+00:00')
            drift_obs = public_observation('demo', 'https://example.com', 'no free tier', stale_platform, root, '2026-10-25T00:00:00+00:00')
            self.assertEqual(ok_obs['status'], 'verified_unchanged')
            self.assertEqual(drift_obs['status'], 'baseline_mismatch')
