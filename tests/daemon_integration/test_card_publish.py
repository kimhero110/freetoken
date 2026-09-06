import unittest,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
from test_intake import bot
from daemon.journal import Journal
from daemon import cards
from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTrigger

class CardPublishTests(unittest.TestCase):
    def payload(self, owner='ou_owner'):
        return P2CardActionTrigger({'event':{'operator':{'open_id':owner},'action':{'value':{'action':'publish_candidate','candidate_id':'candidate-a'}},'context':{'open_message_id':'om_card','open_chat_id':'oc_chat'}}})
    def test_button_visible_before_long_body(self):
        card=cards.update_candidate_card('1','candidate-a','name',['+ new'])['card']
        button=card['elements'][0]['actions'][0]
        self.assertEqual(button['text']['content'],'直接发布')
        self.assertEqual(button['value']['candidate_id'],'candidate-a')
        self.assertNotIn('url',button)
    def test_callback_ack_deduplicates_without_blocking_on_network(self):
        b=bot()
        with tempfile.TemporaryDirectory() as d, patch('daemon.main.threading.Thread') as thread:
            b.journal=Journal(Path(d)/'journal')
            self.assertEqual(b.on_card_action(self.payload()).toast.type,'success')
            b.on_card_action(self.payload())
            thread.assert_called_once()
            b.gh.dispatch_workflow.assert_not_called()
            self.assertEqual(b.on_card_action(self.payload('stranger')).toast.type,'error')
    def test_worker_uses_real_direct_pipeline(self):
        b=bot(); b.candidate_fresh=Mock(return_value=True)
        with patch('daemon.main.threading.Thread'):
            b.process_card_publish('ou_owner','oc_chat','om_card','candidate-a')
        b.gh.dispatch_workflow.assert_called_once()

    def test_duplicate_reports_terminal_outcome(self):
        for phase, kind in [('done','success'),('failed','error')]:
            b=bot()
            ticket=b.store.new_ticket('approve','candidate-a',owner='ou_owner')
            ticket.phase=phase
            with tempfile.TemporaryDirectory() as d, patch('daemon.main.threading.Thread'):
                b.journal=Journal(Path(d)/'journal')
                b.on_card_action(self.payload())
                self.assertEqual(b.on_card_action(self.payload()).toast.type,kind)
    def test_connection_check_never_dispatches_publication(self):
        b=bot(); payload=self.payload(); payload.event.action.value={'action':'check_callback'}
        with patch('daemon.main.threading.Thread') as thread:
            self.assertEqual(b.on_card_action(payload).toast.type,'success')
            thread.assert_not_called()
        b.gh.dispatch_workflow.assert_not_called()
        payload.event.operator.open_id='stranger'
        self.assertEqual(b.on_card_action(payload).toast.type,'error')
