import base64, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
import yaml
from scripts import extract
from daemon.candidate_notifications import newest_candidates
from daemon.alert_store import AlertStore

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

class CandidateNotificationTests(unittest.TestCase):
    def test_only_latest_version_is_selected(self):
        now=datetime.now(timezone.utc); gh=Mock(); gh.list_candidates.return_value=['old','new']
        def response(method,path):
            age=2 if '/old.yaml' in path else 1
            data={'candidate_type':'platform_update','status':'pending_review','platform_slug':'demo','source_url':'https://example.com','captured_at':(now-timedelta(hours=age)).isoformat()}
            return {'content':base64.b64encode(yaml.safe_dump(data).encode()).decode()}
        gh._request.side_effect=response
        self.assertEqual([name for name,_ in newest_candidates(gh,'owner/repo',now.timestamp())],['new'])
    def test_notification_is_durable_and_not_resent_after_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'outbox.sqlite'; store=AlertStore(path)
            store.enqueue_candidate('candidate-a','A','summary',0)
            event,payload,attempt=store.claim(0)
            self.assertEqual(payload['candidate_id'],'candidate-a')
            store.finish(event,attempt,0,message_id='om_test')
            restarted=AlertStore(path); restarted.enqueue_candidate('candidate-a','A','summary',100)
            self.assertIsNone(restarted.claim(100))
    def test_superseded_candidate_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            store=AlertStore(Path(directory)/'outbox.sqlite')
            store.enqueue_candidate('old','Old','summary',0)
            event,payload,attempt=store.claim(0)
            store.finish(event,attempt,0,unknown=True)
            store.supersede_candidates({'new'})
            self.assertIsNone(store.claim(1000))
            store.enqueue_candidate('new','New','summary',1000)
            self.assertEqual(store.claim(1000)[1]['candidate_id'],'new')
