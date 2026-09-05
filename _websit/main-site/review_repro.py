"""Offline review reproductions; no GitHub, Feishu, or LLM requests."""
import ast
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from daemon.state import TicketStore

ROOT = Path(__file__).resolve().parent

def method(path, class_name, method_name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    parent = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name) if class_name else tree
    node = next(n for n in parent.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[method_name]

ns = dict(time=time, datetime=datetime, timezone=timezone, GhError=RuntimeError, log=Mock(), cards=Mock())
await_gate = method("daemon/main.py", "Bot", "_await_gate", ns)
store = TicketStore()
ticket = store.new_ticket("approve", "candidate-a")
unrelated = dict(id=999, status="in_progress", run_started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), display_title="unrelated candidate B")
bot = SimpleNamespace(gh=Mock(), journal=Mock(), tracked=Mock())
bot.gh.list_runs.return_value = [unrelated]
with patch.object(time, "sleep"):
    print("unrelated_review_run_selected:", await_gate(bot, ticket, "chat", "review-candidate.yml"))

bot.gh.list_runs.return_value = [dict(unrelated, status="waiting")]
start = time.time()
with patch.object(time, "sleep"), patch.object(time, "time", side_effect=[start, start, start + 601]):
    print("waiting_review_run_selected:", await_gate(bot, ticket, "chat", "review-candidate.yml"))

from daemon import commands
ns.update(commands=commands, PLATFORM_WORKFLOW="feishu-platform-tip.yml", ARTICLE_WORKFLOW="feishu-article-rewrite.yml", threading=Mock())
submit = method("daemon/main.py", "Bot", "cmd_submit", ns)
bot.store, bot.card, bot.track_run = store, Mock(return_value="om_1"), Mock()
submit(bot, "oc_1", "om_1", "ou_owner", "platform", "https://example.com")
import yaml
workflow = yaml.load((ROOT / ".github/workflows/feishu-platform-tip.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
sent = bot.gh.dispatch_workflow.call_args.kwargs["inputs"]
declared = workflow["on"]["workflow_dispatch"]["inputs"]
print("undeclared_platform_inputs:", sorted(set(sent) - set(declared)))

extract = method("daemon/feishu_client.py", None, "extract_message", {"P2ImMessageReceiveV1": object})
event = SimpleNamespace(event=SimpleNamespace(sender=SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_owner")), message=SimpleNamespace(message_type="text", content=json.dumps({"text": "帮助"}), chat_id="oc_1", message_id="om_1")))
print("valid_event_extracted:", extract(event))

from scripts import platform_tip, review_candidates
import tempfile
with tempfile.TemporaryDirectory() as directory:
    candidates = Path(directory)
    official = "https://example.com/docs"
    with patch.object(platform_tip, "CANDIDATES_DIR", candidates), patch.object(platform_tip, "get_public_text", return_value="<p>" + "public text " * 30 + "</p>"), patch.object(platform_tip, "find_match", return_value=("demo", {"source_urls": [official]}, True)), patch("sys.argv", ["platform_tip.py", "--url", official, "--ticket-id", "pl-demo"]):
        platform_tip.main()
    candidate = yaml.safe_load(next(candidates.glob("*.yaml")).read_text(encoding="utf-8"))
    try:
        review_candidates._apply_update_candidate(candidate)
    except ValueError as error:
        print("generated_update_approval_error:", str(error))
