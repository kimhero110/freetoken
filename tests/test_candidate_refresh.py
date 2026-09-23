import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
import yaml
from scripts import extract

class RefreshTests(unittest.TestCase):
    def test_expired_same_source_refreshes_without_model_or_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); platforms=root/'platforms'; candidates=root/'candidates'
            platforms.mkdir(); candidates.mkdir()
            entry={'name':'Demo','source_urls':['https://example.com'],'free_quota':{'amount':1},'intro':'old'}
            (platforms/'demo.yaml').write_text(yaml.safe_dump(entry))
            text='Current official terms'; source_hash=extract.hashlib.sha256(text.encode()).hexdigest()
            proposed={'free_quota':{'amount':10,'unit':'tokens','type':'永久','conditions':[]},'intro':'new'}
            candidate=extract.build_update_candidate(entry,'demo','https://example.com',source_hash,'',proposed,{})
            candidate['captured_at']=(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()
            old=candidates/f'update-demo-{source_hash[:12]}.yaml'; old.write_text(yaml.safe_dump(candidate))
            (root/'changed.json').write_text(json.dumps([{'platform':'demo','url':'https://example.com','hash':source_hash,'text':text}]))
            with patch.object(extract,'PLATFORMS_DIR',platforms),patch.object(extract,'CANDIDATES_DIR',candidates),patch.object(sys,'argv',['extract','--input-dir',directory]),patch.dict(os.environ,{'CHECK_PAID_ENABLED':'true','CHECK_MAX_CALLS':'0','CHECK_MAX_OUTPUT_TOKENS':'0'}),patch('scripts.check_state.GitState'),patch.object(extract,'resolve_providers',return_value={}),patch.object(extract,'OpenAI') as api,patch.object(extract,'execute_llm_call') as paid:
                self.assertEqual(extract.main(),0)
                api.assert_not_called(); paid.assert_not_called()
            new=[p for p in candidates.glob('*.yaml') if p!=old]
            self.assertEqual(len(new),1)
            result=yaml.safe_load(new[0].read_text())
            self.assertEqual(result['supersedes'],old.stem)
            self.assertEqual(result['status'],'pending_review')
            self.assertNotIn('review',result)
            self.assertEqual(yaml.safe_load(old.read_text()),candidate)
