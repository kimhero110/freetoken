import json,unittest,tempfile,threading
from pathlib import Path
from unittest.mock import Mock
import lark_oapi as lark
from daemon.callback_dispatcher import CallbackDispatcher
from daemon.journal import Journal
from test_intake import bot,event

class DispatcherTests(unittest.TestCase):
    def test_real_sdk_routes_and_serializes_card_response(self):
        from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
        handler=lark.EventDispatcherHandler.builder('','').register_p2_card_action_trigger(lambda event:P2CardActionTriggerResponse({'toast':{'type':'success','content':'ok'}})).build()
        payload=json.dumps({'schema':'2.0','header':{'event_type':'card.action.trigger'},'event':{}}).encode()
        self.assertEqual(CallbackDispatcher(handler)._do_without_validation(payload)['toast']['type'],'success')
    def test_sdk_callback_failure_returns_failure_toast_not_transport_500(self):
        handler=Mock(); handler._do_without_validation.side_effect=ValueError('private details')
        payload=b'{"header":{"event_type":"card.action.trigger"}}'
        result=CallbackDispatcher(handler)._do_without_validation(payload)
        self.assertEqual(result['toast']['type'],'error')
        self.assertNotIn('private details',json.dumps(result))
    def test_slow_message_does_not_block_receiver(self):
        b=bot(); entered=threading.Event(); release=threading.Event(); returned=threading.Event()
        b.handle=lambda *args:(entered.set(),release.wait(5))
        with tempfile.TemporaryDirectory() as directory:
            b.journal=Journal(Path(directory)/'journal')
            try:
                def receive():
                    b.on_event(event())
                    returned.set()
                receiver=threading.Thread(target=receive)
                receiver.start()
                self.assertTrue(entered.wait(1))
                self.assertTrue(returned.wait(.3), 'slow command blocked the WebSocket receiver')
            finally:
                release.set()
                receiver.join(2)

    def test_non_card_failure_is_not_silently_acknowledged(self):
        handler=Mock(); handler._do_without_validation.side_effect=ValueError('failure')
        with self.assertRaises(ValueError):
            CallbackDispatcher(handler)._do_without_validation(b'{"header":{"event_type":"im.message.receive_v1"}}')
