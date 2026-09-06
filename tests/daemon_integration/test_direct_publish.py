import unittest
from unittest.mock import Mock, patch
from test_intake import bot, event
from daemon.feishu_client import extract_message

class DirectPublishTests(unittest.TestCase):
    def test_owner_direct_dispatches_once_without_code(self):
        b=bot(); b.candidate_fresh=Mock(return_value=True)
        with patch('daemon.main.threading.Thread'):
            b.handle(*extract_message(event(text='直接发布 candidate-a')))
            b.handle(*extract_message(event(text='直接发布 candidate-a')))
        b.gh.dispatch_workflow.assert_called_once()
        t=next(iter(b.store.tickets.values()))
        self.assertEqual(t.kind,'approve')
        self.assertEqual(t.note,'explicit_direct_publish')
        self.assertFalse(t.confirm_code)
        self.assertEqual(b.gh.dispatch_workflow.call_args.kwargs['inputs']['decision'],'approve')

    def test_stranger_expired_unknown_and_missing_id_cannot_publish(self):
        for sender, arg, fresh in [('ou_stranger','candidate-a',True),('ou_owner','candidate-a',False),('ou_owner','candidate-a',None),('ou_owner','',True),('ou_owner','#p001',True)]:
            b=bot(); b.candidate_fresh=Mock(return_value=fresh)
            b.handle(*extract_message(event(sender,text='直接发布 '+arg)))
            b.gh.dispatch_workflow.assert_not_called()

    def test_ordinary_approval_still_requires_confirmation(self):
        b=bot(); b.candidate_fresh=Mock(return_value=True)
        b.handle(*extract_message(event(text='通过 candidate-a')))
        b.gh.dispatch_workflow.assert_not_called()
        self.assertTrue(next(iter(b.store.tickets.values())).confirm_code)
