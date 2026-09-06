"""Explicit ledger bootstrap; never calls a provider or replays an intent."""
import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .check_state import GitState, StateError, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "inspect", "attach-result", "abandon"])
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--key")
    parser.add_argument("--result-file", type=Path)
    parser.add_argument("--actor", help="Public GitHub login")
    parser.add_argument("--old-run-stopped", action="store_true")
    parser.add_argument("--authorize-refresh", action="store_true")
    args = parser.parse_args()
    store = GitState(args.repo)
    if args.action == "init":
        history = json.loads((args.repo / "config/check-history.json").read_text(encoding="utf-8"))
        if history.get('version') != 1 or history.get('audit_complete') is not True:
            raise StateError('HISTORY_AUDIT_REQUIRED')
        if args.authorize_refresh and (not args.old_run_stopped or not re.fullmatch('[A-Za-z0-9-]{1,39}', args.actor or '')):
            raise StateError('EXPLICIT_RESOLUTION_REQUIRED')
        def initialize(state):
            for source in history['source_versions']:
                state["history"].setdefault(source, "legacy_unconfirmed")
            state['history'].setdefault('legacy_audit', {'runs': history.get('runs', []), 'audited_at': history.get('audited_at')})
            if args.authorize_refresh:
                for group in history.get('refresh_sources', []):
                    state['history'].setdefault('refresh_group:' + group['source_id'], {
                        'actor': args.actor, 'used': None, 'allowed_legacy': group['legacy_keys'],
                        'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                        'reason': 'one_time_post_incident_revalidation'})
        store.update(initialize, initialize=True)
        print("STATE_INITIALIZED_WITH_HISTORICAL_BLOCKS")
    elif args.action == "inspect":
        _, state = store.read()
        print(json.dumps({"calls": {key: value["status"] for key, value in state["calls"].items()},
                          "history": state["history"]}))
    else:
        if not args.old_run_stopped or not re.fullmatch('[a-f0-9]{64}', args.key or '') or not re.fullmatch('[A-Za-z0-9-]{1,39}', args.actor or ''):
            raise StateError('EXPLICIT_RESOLUTION_REQUIRED')
        result = None
        if args.action == 'attach-result':
            from .extract import validate_extracted
            from .check_runner import public_result
            if not args.result_file or args.result_file.stat().st_size > 8000:
                raise StateError('RESULT_INVALID')
            result = validate_extracted(json.loads(args.result_file.read_text(encoding='utf-8')))
            if result is None:
                raise StateError('RESULT_INVALID')
            public_result(result)
        def resolve(state):
            call = state['calls'].get(args.key)
            if not call or call['status'] not in {'intent', 'uncertain', 'rejected_result'}:
                raise StateError('CALL_NOT_UNRESOLVED')
            now = datetime.now(timezone.utc).isoformat()
            call['resolution'] = {'action': args.action, 'actor': args.actor, 'at': now}
            call['status'] = 'abandoned' if result is None else 'result_saved'
            if result is not None:
                call.update(result=result, result_hash=digest(result), saved_at=now)
        store.update(resolve)
        print('CALL_RESOLVED_NO_REQUEST_SENT')


if __name__ == "__main__":
    main()
