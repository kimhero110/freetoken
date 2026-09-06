"""Always-run finalizer: publishing partial output does not erase failures."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .check_state import GitState


def main():
    folder = Path(os.environ['RUNNER_TEMP'])
    result = {"version": 1, "completed_at": datetime.now(timezone.utc).isoformat(),
              "workflow": os.environ.get('GITHUB_WORKFLOW', ''), "stages": {}}
    result['workflow_file'] = os.environ.get('GITHUB_WORKFLOW_REF', '').split('@')[0].rsplit('/', 1)[-1]
    for stage in ('fetch', 'extract', 'publish'):
        result['stages'][stage] = os.environ.get(stage.upper() + '_OUTCOME', 'missing')
        path = folder / (stage + '-summary.json')
        if path.exists():
            result[stage] = json.loads(path.read_text(encoding='utf-8'))
    failed = any(outcome != 'success' for outcome in result['stages'].values())
    result['status'] = 'failed' if failed else 'completed'
    if not failed and result.get('extract', {}).get('status') == 'dry_run':
        result['status'] = 'dry_run'
    run = os.environ.get('GITHUB_RUN_ID', 'local') + '-' + os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    try:
        GitState(Path(__file__).resolve().parents[1]).update(lambda state: state['runs'].update({run: result}))
    except Exception:
        result['state_error'] = 'STATE_SUMMARY_SAVE_FAILED'
        # A dry run is permitted before bootstrap. Real check results require persistence.
        failed = failed or result['status'] != 'dry_run'
    (folder / 'run-summary.json').write_text(json.dumps(result), encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as output:
            output.write('## Check result\n\n```json\n' + json.dumps(result, indent=2) + '\n```\n')
    print(json.dumps(result))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
