import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
import yaml
from scripts import extract

class RefreshTests(unittest.TestCase):
    def test_unchanged_hash_after_24h_does_not_clone_dated_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            platforms = root / 'platforms'
            candidates = root / 'candidates'
            platforms.mkdir()
            candidates.mkdir()
            entry = {'name': 'Demo', 'source_urls': ['https://example.com'], 'free_quota': {'amount': 1}, 'intro': 'old'}
            (platforms / 'demo.yaml').write_text(yaml.safe_dump(entry))
            text = 'Current official terms'
            source_hash = extract.hashlib.sha256(text.encode()).hexdigest()
            proposed = {'free_quota': {'amount': 10, 'unit': 'tokens', 'type': '永久', 'conditions': []}, 'intro': 'new'}
            candidate = extract.build_update_candidate(entry, 'demo', 'https://example.com', source_hash, '', proposed, {})
            candidate['captured_at'] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            old = candidates / f'update-demo-{source_hash[:12]}.yaml'
            old.write_text(yaml.safe_dump(candidate))
            (root / 'changed.json').write_text(json.dumps([{'platform': 'demo', 'url': 'https://example.com', 'hash': source_hash, 'text': text}]))
            with patch.object(extract, 'PLATFORMS_DIR', platforms), \
                 patch.object(extract, 'CANDIDATES_DIR', candidates), \
                 patch.object(sys, 'argv', ['extract', '--input-dir', directory]), \
                 patch.dict(os.environ, {'CHECK_PAID_ENABLED': 'true', 'CHECK_MAX_CALLS': '0', 'CHECK_MAX_OUTPUT_TOKENS': '0'}), \
                 patch('scripts.check_state.GitState'), \
                 patch.object(extract, 'resolve_providers', return_value={}), \
                 patch.object(extract, 'OpenAI') as api, \
                 patch.object(extract, 'execute_llm_call') as paid:
                self.assertEqual(extract.main(), 0)
                api.assert_not_called()
                paid.assert_not_called()
            remaining = list(candidates.glob('*.yaml'))
            self.assertEqual(remaining, [old])
            self.assertEqual(yaml.safe_load(old.read_text()), candidate)
            summary = json.loads((root / 'extract-summary.json').read_text())
            self.assertEqual(summary['sources'][0]['status'], 'pending_review')
            self.assertEqual(summary['sources'][0]['superseded_by'], old.stem)

    def test_same_source_hash_rebases_and_unlinks_old_when_platform_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            platforms = root / 'platforms'
            candidates = root / 'candidates'
            platforms.mkdir()
            candidates.mkdir()
            old_entry = {'name': 'Demo', 'source_urls': ['https://example.com'], 'free_quota': {'amount': 1}, 'intro': 'old'}
            text = 'Current official terms'
            source_hash = extract.hashlib.sha256(text.encode()).hexdigest()
            proposed = {'free_quota': {'amount': 10, 'unit': 'tokens', 'type': '永久', 'conditions': []}, 'intro': 'new'}
            candidate = extract.build_update_candidate(old_entry, 'demo', 'https://example.com', source_hash, '', proposed, {})
            candidate['captured_at'] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
            old = candidates / f'update-demo-{source_hash[:12]}.yaml'
            old.write_text(yaml.safe_dump(candidate))
            updated_entry = {**old_entry, 'last_verified': '2026-10-25'}
            (platforms / 'demo.yaml').write_text(yaml.safe_dump(updated_entry))
            (root / 'changed.json').write_text(json.dumps([{'platform': 'demo', 'url': 'https://example.com', 'hash': source_hash, 'text': text}]))
            with patch.object(extract, 'PLATFORMS_DIR', platforms), \
                 patch.object(extract, 'CANDIDATES_DIR', candidates), \
                 patch.object(sys, 'argv', ['extract', '--input-dir', directory]), \
                 patch.dict(os.environ, {'CHECK_PAID_ENABLED': 'true', 'CHECK_MAX_CALLS': '0', 'CHECK_MAX_OUTPUT_TOKENS': '0'}), \
                 patch('scripts.check_state.GitState'), \
                 patch.object(extract, 'resolve_providers', return_value={}), \
                 patch.object(extract, 'OpenAI') as api, \
                 patch.object(extract, 'execute_llm_call') as paid:
                self.assertEqual(extract.main(), 0)
                api.assert_not_called()
                paid.assert_not_called()
            self.assertFalse(old.exists())
            remaining = list(candidates.glob('*.yaml'))
            self.assertEqual(len(remaining), 1)
            result = yaml.safe_load(remaining[0].read_text())
            self.assertEqual(result['supersedes'], old.stem)
            self.assertEqual(result['status'], 'pending_review')
            self.assertNotIn('review', result)
