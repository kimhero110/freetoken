"""Keep transport acknowledgements separate from publication outcomes."""
import json
import logging
import time
from lark_oapi.core.json import JSON

log = logging.getLogger('callback-dispatcher')

class CallbackDispatcher:
    def __init__(self, delegate):
        self.delegate = delegate

    def _do_without_validation(self, payload):
        # Called only by the authenticated SDK WebSocket transport.
        started = time.monotonic()
        callback = False
        try:
            envelope = json.loads(payload)
            callback = envelope.get('header', {}).get('event_type') == 'card.action.trigger'
            result = self.delegate._do_without_validation(payload)
            # Validate serialization here rather than allowing SDK to turn it into HTTP 500.
            if callback:
                result = json.loads(JSON.marshal(result)) if result is not None else {}
                if not isinstance(result, dict):
                    raise ValueError('CALLBACK_RESPONSE_TYPE')
            return result
        except Exception as exc:
            log.error('EVENT_DISPATCH_FAILED callback=%s kind=%s', callback, type(exc).__name__)
            # Failure toast is not an approval or a successful publication receipt.
            if callback:
                return {'toast': {'type': 'error', 'content': '按钮处理失败，任务未确认，请查看机器人状态。'}}
            raise
        finally:
            if callback:
                log.info('CARD_CALLBACK_RESPONSE elapsed_ms=%d', round((time.monotonic()-started)*1000))
