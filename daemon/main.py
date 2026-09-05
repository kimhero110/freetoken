# -*- coding: utf-8 -*-
"""Intake daemon entrypoint: Feishu long-connection router.

Commands → GitHub Actions (workflow_dispatch via Actions-only PAT).
All canonical data changes still flow through gated PRs; the daemon is a router.
"""

import base64
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from . import auth, cards, commands
from .config import load_config
from .feishu_client import FeishuClient, extract_message
from .gh_client import GhError, GitHubClient
from .journal import Journal
from .state import TicketStore, now_iso
from .watchdog import Watchdog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("intake")

REVIEW_WORKFLOW = "review-candidate.yml"
PLATFORM_WORKFLOW = "feishu-platform-tip.yml"
ARTICLE_WORKFLOW = "feishu-article-rewrite.yml"
SELFTEST_WORKFLOW = "feishu-self-test.yml"
FRESHNESS_KEYS = ("checked_at", "captured_at")


class Bot:
    def __init__(self, config=None):
        self.config = config or load_config()
        self.journal = Journal(self.config["journal_path"])
        self.store = TicketStore(
            confirm_ttl=self.config["confirm_ttl_seconds"],
            confirm_max_attempts=self.config["confirm_max_attempts"],
            lock_ttl=self.config["lock_ttl_seconds"],
            fresh_hours=self.config["candidate_fresh_hours"],
        )
        self.store.prime(self.journal.load_events())
        self.journal.prime_seen_events()
        self.gh = GitHubClient(self.config["github_pat"], self.config["github_repo"])
        self.feishu = FeishuClient(self.config["app_id"], self.config["app_secret"])
        self.started_at = time.time()
        self.watchdog = Watchdog(self.store, self.gh, self.feishu, self.config, self.journal)

    # ------------------------------------------------------------------ util
    def card(self, chat_id: str, card: dict, reply_to: str = "", patch_id: str = "") -> str:
        if patch_id:
            if self.feishu.patch_card(patch_id, card):
                return patch_id
        return self.feishu.send_card(chat_id, card, message_id=reply_to)

    def _dispatch_ticket(self, ticket, workflow: str, inputs: dict):
        ticket.dispatch_actor, ticket.dispatch_sha = self.gh.dispatch_identity()
        if not ticket.dispatch_actor or not re.fullmatch(r"[a-f0-9]{40}", ticket.dispatch_sha or ""):
            raise GhError("CONTRACT", "cannot bind dispatch identity")
        self.journal.append(ticket.to_event())
        self.gh.dispatch_workflow(workflow, inputs=inputs)

    def _matches_run(self, ticket, run: dict, workflow: str) -> bool:
        if (run.get("path") != f".github/workflows/{workflow}"
                or run.get("head_branch") != "main"
                or run.get("repository", {}).get("full_name") != self.config["github_repo"]):
            return False
        if workflow == "publish.yml":
            return bool(ticket.publish_sha and ticket.publish_actor
                        and run.get("event") == "push"
                        and run.get("head_sha") == ticket.publish_sha
                        and run.get("actor", {}).get("login") == ticket.publish_actor)
        title = f"intake:{ticket.ticket_id}"
        if workflow == REVIEW_WORKFLOW:
            title += f":{ticket.kind}:{ticket.arg}"
        return bool(ticket.dispatch_actor and ticket.dispatch_sha
                    and run.get("event") == "workflow_dispatch"
                    and run.get("display_title") == title
                    and run.get("actor", {}).get("login") == ticket.dispatch_actor
                    and run.get("head_sha") == ticket.dispatch_sha)

    def _unique_run(self, ticket, workflow: str) -> dict | None:
        matches = [r for r in self.gh.list_runs(workflow=workflow, limit=100)
                   if self._matches_run(ticket, r, workflow)]
        if len(matches) > 1:
            raise GhError("CONTRACT", "multiple runs match this ticket; manual review required")
        return matches[0] if matches else None

    def tracked(self, ticket, phase: str, card: dict, chat_id: str):
        ticket.phase = phase
        ticket.updated_at = time.time()
        self.journal.append(ticket.to_event())
        message_id = self.card(chat_id, card, patch_id=ticket.card_message_id)
        if message_id and message_id != ticket.card_message_id:
            ticket.card_message_id = message_id
            self.journal.append(ticket.to_event())

    # ------------------------------------------------------------- candidate
    def candidate_fresh(self, candidate_id: str) -> bool | None:
        """Light freshness probe: regex over the candidate YAML. None = unknown (allow)."""
        try:
            data = self.gh._request("GET", f"/repos/{self.config['github_repo']}/contents/data/candidates/{candidate_id}.yaml")
            raw = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
        except GhError:
            return None
        stamps = []
        for key in FRESHNESS_KEYS:
            match = re.search(rf"{key}:\s*['\"]?(\S+)", raw)
            if match:
                try:
                    stamps.append(datetime.fromisoformat(match.group(1).strip("'\"")))
                except ValueError:
                    continue
        if not stamps:
            return None
        newest = max(stamps)
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - newest
        return age.total_seconds() <= self.config["candidate_fresh_hours"] * 3600

    def candidate_name(self, candidate_id: str) -> str:
        try:
            data = self.gh._request("GET", f"/repos/{self.config['github_repo']}/contents/data/candidates/{candidate_id}.yaml")
            raw = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
            match = re.search(r"(?:name|platform_name):\s*['\"]?([^'\"\n]+)", raw)
            if match:
                return match.group(1).strip()
        except GhError:
            pass
        return candidate_id

    # -------------------------------------------------------------- handlers
    def handle(self, sender: str, chat_id: str, message_id: str, text: str):
        command = commands.parse(text)
        verb, arg = command.verb, command.arg

        if verb == "whoami":
            if auth.should_answer_whoami(sender, self.config["owner_open_id"], self.config["bootstrap"]):
                self.card(chat_id, cards.status_card([f"你的 open_id：`{sender}`"], "?", self.config["commit_sha"], "-"), reply_to=message_id)
            return
        if not auth.is_authorized(sender, self.config["owner_open_id"]):
            log.info("ignored sender %s", auth.redact_open_id(sender))
            return
        if verb == "empty":
            return
        if verb == "unknown":
            if commands.BARE_URL_RE.match(commands.normalize(text)):
                verb = "bare_url"
            else:
                self.card(chat_id, cards.help_card(), reply_to=message_id)
                return

        if verb == "help":
            self.card(chat_id, cards.help_card(), reply_to=message_id)
        elif verb == "pending":
            self.cmd_pending(chat_id, message_id)
        elif verb == "status":
            self.cmd_status(chat_id, message_id)
        elif verb == "selftest":
            ticket = self.store.new_ticket("selftest", "no-content-change", owner=sender)
            code = self.store.issue_confirm(ticket)
            self.journal.append(ticket.to_event())
            ticket.card_message_id = self.card(chat_id, cards.confirm_card(
                "联调测试：仅验证 GitHub production 审批门禁，不修改或发布网站内容", code), reply_to=message_id)
            self.journal.append(ticket.to_event())
        elif verb == "bare_url":
            ticket = self.store.new_ticket("disambig", arg, owner=sender)
            self.journal.append(ticket.to_event())
            self.card(chat_id, cards.disambiguation_card(arg), reply_to=message_id)
        elif verb == "platform" or (verb == "disambig_followup" and False):
            self.cmd_submit(chat_id, message_id, sender, "platform", arg)
        elif verb == "article":
            self.cmd_submit(chat_id, message_id, sender, "article", arg)
        elif verb in ("approve", "reject"):
            self.cmd_approve(chat_id, message_id, sender, verb, arg)
        elif verb == "confirm":
            self.cmd_confirm(chat_id, message_id, sender, arg)
        elif verb == "undo":
            self.cmd_undo(chat_id, message_id, sender)
        else:
            self.card(chat_id, cards.help_card(), reply_to=message_id)

    def cmd_pending(self, chat_id: str, message_id: str):
        try:
            candidates = self.gh.list_candidates()
        except GhError as exc:
            self.card(chat_id, cards.error_card("获取候选失败", exc.kind, "稍后重试；若持续失败查 PAT/网络"), reply_to=message_id)
            return
        items = []
        for index, cid in enumerate(sorted(candidates), start=1):
            items.append({"short": f"#p{index:03d}", "name": self.candidate_name(cid), "wait": "?"})
        self.card(chat_id, cards.pending_list_card(items), reply_to=message_id)

    def cmd_status(self, chat_id: str, message_id: str):
        try:
            runs = self.gh.list_runs(limit=5)
            lines = [
                f"{r['name']} · {r['status']}{'/' + r['conclusion'] if r.get('conclusion') else ''}"
                for r in runs if r.get("status") != "completed"
            ][:5]
        except GhError:
            lines = ["运行列表获取失败（PAT/网络）"]
        uptime = time.strftime("%H:%M", time.gmtime(time.time() - self.started_at))
        self.card(chat_id, cards.status_card(lines, "?", self.config["commit_sha"], uptime), reply_to=message_id)

    def cmd_submit(self, chat_id: str, message_id: str, sender: str, kind: str, arg: str):
        url, note = arg, ""
        if " " in arg:
            url, note = arg.split(" ", 1)
        if not commands.validate_url(url):
            self.card(chat_id, cards.error_card("链接无效", f"只接受 HTTPS 链接，收到：{url or '(空)'}", "示例：平台 https://example.com 送 10 刀"), reply_to=message_id)
            return
        workflow = PLATFORM_WORKFLOW if kind == "platform" else ARTICLE_WORKFLOW
        mode = "outline" if "参数:提纲" in note or ":提纲" in note else "rewrite"
        ticket = self.store.new_ticket(kind, url, owner=sender, note=note)
        self.journal.append(ticket.to_event())
        ticket.card_message_id = self.card(chat_id, cards.ack_card(kind, ticket.ticket_id, url), reply_to=message_id)
        self.journal.append(ticket.to_event())
        try:
            inputs = {"url": url[:300], "note": note[:200], "ticket_id": ticket.ticket_id}
            if kind == "article":
                inputs["mode"] = mode
            self._dispatch_ticket(ticket, workflow, inputs)
            ticket.phase = "dispatched"
            ticket.updated_at = time.time()
            self.journal.append(ticket.to_event())
            threading.Thread(target=self.track_run, args=(ticket, chat_id, kind), daemon=True).start()
        except GhError as exc:
            self.tracked(ticket, "failed", cards.error_card("触发失败", f"{exc.kind}: {exc}", "401=按手册轮换 PAT；422=工作流契约破坏查 CI"), chat_id)

    def track_run(self, ticket, chat_id: str, kind: str):
        """Poll the ticket's workflow run; final card depends on kind."""
        deadline = time.time() + 15 * 60
        run_id = None
        while time.time() < deadline:
            time.sleep(15)
            try:
                mine = self._unique_run(ticket, PLATFORM_WORKFLOW if kind == "platform" else ARTICLE_WORKFLOW)
                if not run_id and mine:
                    run_id = mine["id"]
                    ticket.run_ids = [run_id]
                    self.journal.append(ticket.to_event())
                if run_id:
                    run = self.gh.get_run(run_id)
                    if run.get("status") == "completed":
                        if run.get("conclusion") == "success":
                            self.on_workflow_success(ticket, chat_id, kind)
                        else:
                            self.tracked(ticket, "failed", cards.error_card(
                                "流水线失败", f"run {run_id} {run.get('conclusion')}", "常见：抓取失败/提取不合 schema/额度不足。重发或人工处理"), chat_id)
                        return
            except GhError as exc:
                log.warning("track_run poll error %s", exc)
            if run_id is None and time.time() > deadline - 60:
                break
        self.tracked(ticket, "failed", cards.error_card("跟踪超时", "15 分钟未观察到 run 完成", f"查看 Actions 页面确认 {self.gh.run_url(run_id) if run_id else ''}"), chat_id)

    def on_workflow_success(self, ticket, chat_id: str, kind: str):
        if kind == "platform":
            try:
                candidates = self.gh.list_candidates()
                match = next((c for c in candidates if ticket.ticket_id in c), None)
            except GhError:
                match = None
            if match:
                ordered = sorted(self.gh.list_candidates())
                short = self.store.short_id_for(ordered, match)
                name = self.candidate_name(match)
                self.tracked(ticket, "done", cards.candidate_card(short or "?", match, name, [], [
                    "tools 全部 unknown，verification=claimed", "批准后仅提升来源核验，不自动开探针",
                ]), chat_id)
            else:
                self.tracked(ticket, "done", cards.progress_card(kind, ticket.ticket_id, "done", "候选已入库（详情见 Actions）"), chat_id)
        else:
            pr_url = self.find_pr_url(f"auto/article-{ticket.ticket_id}")
            preview = pr_url.replace("/pull/", "/pull/") if pr_url else ""
            self.tracked(ticket, "done", cards.article_card(
                ticket.note or ticket.arg, pr_url or "(见 Actions)", preview, "见 PR"), chat_id)

    def find_pr_url(self, head_branch: str) -> str:
        try:
            pulls = self.gh._request("GET", f"/repos/{self.config['github_repo']}/pulls?state=open&per_page=20")
            for pull in pulls:
                if pull.get("head", {}).get("ref") == head_branch:
                    return pull.get("html_url", "")
        except GhError:
            pass
        return ""

    # ------------------------------------------------------------- approvals
    def cmd_approve(self, chat_id: str, message_id: str, sender: str, decision: str, arg: str):
        candidates = None
        candidate_id = arg
        if not candidate_id and message_id:
            candidate_id = ""  # reply-quote path: resolve via quoted card footer is SDK-heavy; require arg in v1
        short = commands.validate_short_id(candidate_id) if candidate_id.startswith("#") or candidate_id.isdigit() else None
        if short is not None or (candidate_id and not commands.validate_candidate_id(candidate_id)):
            try:
                candidates = sorted(self.gh.list_candidates())
            except GhError as exc:
                self.card(chat_id, cards.error_card("候选清单获取失败", exc.kind, "稍后重试"), reply_to=message_id)
                return
            resolved = self.store.resolve_short_id(candidates, short or int(candidate_id)) if (short or (candidate_id.isdigit() and len(candidate_id) <= 3)) else None
            if resolved:
                candidate_id = resolved
        if not candidate_id:
            self.card(chat_id, cards.error_card("缺少候选标识", "用法：通过 #p042 或 通过 <完整ID>", "发 待审 查看短号列表"), reply_to=message_id)
            return
        if not commands.validate_candidate_id(candidate_id):
            self.card(chat_id, cards.error_card("候选 ID 非法", candidate_id, "发 待审 查看列表"), reply_to=message_id)
            return
        active = self.store.active_approval_for(candidate_id)
        if active:
            self.card(chat_id, cards.error_card("审批进行中", f"票据 {active.ticket_id} 已在处理", "等它完成或超时后重试"), reply_to=message_id)
            return
        fresh = self.candidate_fresh(candidate_id)
        if fresh is False:
            self.card(chat_id, cards.error_card("候选已过期", f"{candidate_id} 超过 48h 新鲜窗口", "重新发 平台 <原URL> 生成新候选"), reply_to=message_id)
            return
        ticket = self.store.new_ticket("approve" if decision == "approve" else "reject", candidate_id, owner=sender)
        self.journal.append(ticket.to_event())
        code = self.store.issue_confirm(ticket)
        self.journal.append(ticket.to_event())
        ticket.card_message_id = self.card(chat_id, cards.confirm_card(candidate_id, code), reply_to=message_id)
        self.journal.append(ticket.to_event())

    def cmd_confirm(self, chat_id: str, message_id: str, sender: str, arg: str):
        code = arg
        if not commands.validate_confirm_code(code):
            self.card(chat_id, cards.error_card("确认码格式错误", "用法：确认 123456", "码在审批确认卡页脚，5 分钟内有效"), reply_to=message_id)
            return
        ticket = None
        for candidate_ticket in sorted(self.store.tickets.values(), key=lambda t: t.updated_at, reverse=True):
            if candidate_ticket.owner == sender and candidate_ticket.confirm_code and candidate_ticket.phase in ("created", "awaiting_confirm"):
                ticket = candidate_ticket
                break
        if not ticket:
            self.card(chat_id, cards.error_card("无待确认票据", "先发 通过/拒绝 <候选> 获取确认码", "发 待审 查看候选"), reply_to=message_id)
            return
        ok, why = self.store.check_confirm(ticket, commands.normalize(code))
        self.journal.append(ticket.to_event())
        if not ok:
            messages = {"LOCKED": "错误次数过多，该候选锁定 30 分钟", "EXPIRED": "确认码已过期（5 分钟），重新发 通过/拒绝", "WRONG": "确认码不正确"}
            self.card(chat_id, cards.error_card("确认失败", messages.get(why, why), "重新发起审批"), reply_to=message_id)
            return
        if ticket.kind == "selftest":
            try:
                self._dispatch_ticket(ticket, SELFTEST_WORKFLOW, {"ticket_id": ticket.ticket_id})
                self.tracked(ticket, "dispatched", cards.progress_card("联调", ticket.ticket_id, "dispatched", "无内容变更，验证实际审批门禁"), chat_id)
                threading.Thread(target=self.track_selftest, args=(ticket, chat_id), daemon=True).start()
            except GhError as exc:
                self.tracked(ticket, "failed", cards.error_card("联调触发失败", str(exc), "检查 Actions 权限及工作流版本"), chat_id)
            return
        decision = "approve" if ticket.kind == "approve" else "reject"
        ticket.phase = "awaiting_confirm"
        ticket.updated_at = time.time()
        self.journal.append(ticket.to_event())
        try:
            self._dispatch_ticket(ticket, REVIEW_WORKFLOW, {
                "ticket_id": ticket.ticket_id,
                "candidate_id": ticket.arg,
                "decision": decision,
                "approver_via": "feishu",
                "approver_id": auth.redact_open_id(sender),
            })
        except GhError as exc:
            self.tracked(ticket, "failed", cards.error_card("触发审批失败", f"{exc.kind}: {exc}", "401=轮换 PAT；422=契约破坏查 CI"), chat_id)
            return
        self.tracked(ticket, "dispatched", cards.progress_card(ticket.kind, ticket.ticket_id, "dispatched", f"候选 {ticket.arg}"), chat_id)
        threading.Thread(target=self.track_approval, args=(ticket, chat_id), daemon=True).start()

    def track_selftest(self, ticket, chat_id: str):
        run_id = self._await_gate(ticket, chat_id, SELFTEST_WORKFLOW)
        if not run_id or not self._approve_gate(ticket, chat_id, run_id, f"intake selftest {ticket.ticket_id}"):
            return
        conclusion = self._await_completion(ticket, chat_id, run_id)
        if conclusion == "success":
            self.tracked(ticket, "done", cards.progress_card("联调", ticket.ticket_id, "done", "真实 GitHub 门禁与回执链路通过；未发布网站内容"), chat_id)
        else:
            self.tracked(ticket, "failed", cards.error_card("联调未通过", str(conclusion), "检查对应 Actions 运行"), chat_id)

    def track_approval(self, ticket, chat_id: str):
        """dispatch → review run → approve its gate → merged → publish run → approve gate → done."""
        run_id = self._await_gate(ticket, chat_id, REVIEW_WORKFLOW)
        if not run_id:
            return
        if not self._approve_gate(ticket, chat_id, run_id, f"intake-bot ticket {ticket.ticket_id} ({ticket.kind})"):
            return
        conclusion = self._await_completion(ticket, chat_id, run_id)
        if conclusion != "success":
            self.tracked(ticket, "failed", cards.error_card(
                "审批 run 失败", f"conclusion={conclusion}", "常见：候选 hash 过期（重发线索）或构建失败；查看 run 链接"), chat_id)
            return
        if ticket.kind != "approve":
            self.tracked(ticket, "done", cards.progress_card(ticket.kind, ticket.ticket_id, "done", f"已拒绝并归档 {ticket.arg}"), chat_id)
            return
        # Bind publication to the exact PR merged by this run and attempt.
        try:
            review_run = self.gh.get_run(run_id)
            merge = self.gh.reviewed_merge(review_run) if self._matches_run(ticket, review_run, REVIEW_WORKFLOW) else None
        except GhError as exc:
            self.tracked(ticket, "failed", cards.error_card("无法关联发布", str(exc), "请人工检查本次审核 PR"), chat_id)
            return
        if not self._matches_run(ticket, review_run, REVIEW_WORKFLOW):
            self.tracked(ticket, "failed", cards.error_card("审批关联失效", "run 身份不匹配", "请人工检查 Actions"), chat_id)
            return
        if not merge or not re.fullmatch(r"[a-f0-9]{40}", merge.get("sha") or "") or not merge.get("actor"):
            self.tracked(ticket, "failed", cards.error_card("无法关联发布", "未找到本审批的唯一合并 PR", "请人工检查 Actions"), chat_id)
            return
        ticket.publish_sha, ticket.publish_actor = merge["sha"], merge["actor"]
        ticket.updated_at = time.time()
        self.journal.append(ticket.to_event())
        publish_run = self._find_publish_run(ticket)
        if not publish_run:
            self.tracked(ticket, "failed", cards.error_card("未找到关联发布", "等待本次合并的 publish 超时", "请人工检查 Actions；未自动批准其他发布"), chat_id)
            return
        ticket.run_ids.append(publish_run["id"])
        ticket.updated_at = time.time()
        self.journal.append(ticket.to_event())
        self.tracked(ticket, "publishing", cards.progress_card(ticket.kind, ticket.ticket_id, "publishing", f"publish run {publish_run['id']}"), chat_id)
        if not self._approve_gate(ticket, chat_id, publish_run["id"], f"intake-bot publish {ticket.ticket_id}"):
            return
        conclusion = self._await_completion(ticket, chat_id, publish_run["id"], timeout=900)
        if conclusion == "success":
            self.tracked(ticket, "done", cards.progress_card(ticket.kind, ticket.ticket_id, "done", "双节点验证通过，已上线"), chat_id)
        else:
            self.tracked(ticket, "failed", cards.error_card("发布失败", f"publish conclusion={conclusion}", "查看 run；服务器有回滚快照"), chat_id)

    def _await_gate(self, ticket, chat_id: str, workflow: str) -> int | None:
        deadline = time.time() + 10 * 60
        while time.time() < deadline:
            time.sleep(15)
            try:
                run = self._unique_run(ticket, workflow)
                if run:
                    # Identity is independent of status: waiting and fast completed runs count.
                    if run["id"] not in ticket.run_ids:
                        ticket.run_ids.append(run["id"])
                        ticket.updated_at = time.time()
                        self.journal.append(ticket.to_event())
                    return run["id"]
            except GhError as exc:
                if exc.kind == "CONTRACT":
                    self.tracked(ticket, "failed", cards.error_card("审批关联失败", str(exc), "请人工检查 Actions"), chat_id)
                    return None
                log.warning("await_gate poll %s", exc)
        self.tracked(ticket, "failed", cards.error_card("未观察到审批 run", "10 分钟超时", "查 Actions 是否排队/并发组占用"), chat_id)
        return None

    def _approve_gate(self, ticket, chat_id: str, run_id: int, comment: str) -> bool:
        deadline = time.time() + self.config["watchdog_minutes"] * 60 - 60
        while time.time() < deadline:
            time.sleep(20)
            try:
                run = self.gh.get_run(run_id)
                workflow = SELFTEST_WORKFLOW if ticket.kind == "selftest" else "publish.yml" if ticket.publish_sha else REVIEW_WORKFLOW
                if run_id not in ticket.run_ids or not self._matches_run(ticket, run, workflow):
                    self.tracked(ticket, "failed", cards.error_card("拒绝自动批准", "run 与票据不匹配", "请人工检查 Actions"), chat_id)
                    return False
                pendings = self.gh.pending_deployments(run_id)
                if pendings:
                    if len(pendings) != 1 or pendings[0].get("environment", {}).get("name") != "production":
                        self.tracked(ticket, "failed", cards.error_card("拒绝自动批准", "非预期的 Environment", "请人工检查 Actions"), chat_id)
                        return False
                    self.tracked(ticket, "awaiting_gate", cards.progress_card(ticket.kind, ticket.ticket_id, "awaiting_gate", f"run {run_id}"), chat_id)
                    environment = pendings[0]["environment"]
                    self.gh.approve_deployment(run_id, environment["id"], comment)
                    self.journal.append({"type": "gate_approved", "ticket_id": ticket.ticket_id,
                                         "run_id": run_id, "environment_id": environment["id"], "ts": now_iso()})
                    log.info("approved gate run=%s env=%s ticket=%s", run_id, environment.get("name"), ticket.ticket_id)
                    return True
                if run.get("status") == "completed":
                    return True  # gate passed some other way (no env wait)
            except GhError as exc:
                if exc.kind == "PAT_DEAD":
                    self.tracked(ticket, "failed", cards.error_card("PAT 失效", exc.__str__()[:200], "按运维手册轮换 PAT 后重发命令"), chat_id)
                    return False
                log.warning("approve_gate %s", exc)
        self.tracked(ticket, "failed", cards.error_card("门禁批准超时", f"run {run_id}", "看门狗稍后会取消该 run"), chat_id)
        return False

    def _await_completion(self, ticket, chat_id: str, run_id: int, timeout: int = 900) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(20)
            try:
                run = self.gh.get_run(run_id)
                if run.get("status") == "completed":
                    return run.get("conclusion") or "unknown"
            except GhError:
                continue
        return "timeout"

    def _find_publish_run(self, ticket) -> dict | None:
        deadline = time.time() + 10 * 60
        while time.time() < deadline:
            try:
                run = self._unique_run(ticket, "publish.yml")
                if run:
                    return run
            except GhError as exc:
                if exc.kind == "CONTRACT":
                    return None
                log.warning("find publish %s", exc)
            time.sleep(15)
        return None

    def cmd_undo(self, chat_id: str, message_id: str, sender: str):
        latest = self.store.latest_own_submission(sender)
        if not latest:
            self.card(chat_id, cards.error_card("无可撤销票据", "你没有已提交的线索", "发 平台 <url> 开始"), reply_to=message_id)
            return
        self.card(chat_id, cards.status_card(
            [f"最新票据 {latest.ticket_id}（{latest.arg}）"], "?", self.config["commit_sha"], "-"), reply_to=message_id)
        self.card(chat_id, cards.status_card(
            ["候选入库后不可直接修改：拒绝后重发。若已生成候选，发 拒绝 <短号>"], "?", "", ""), reply_to=message_id)

    # -------------------------------------------------------------- dispatch
    def on_event(self, data: P2ImMessageReceiveV1) -> None:
        extracted = extract_message(data)
        if not extracted:
            return
        sender, chat_id, message_id, text = extracted
        event_id = getattr(data, "header", None)
        event_key = getattr(event_id, "event_id", "") if event_id else ""
        if event_key and self.journal.seen_event(event_key):
            return  # Feishu redelivery dedupe
        if event_key:
            self.journal.append({"type": "feishu_event", "event_id": event_key, "ts": now_iso()})
        try:
            self.handle(sender, chat_id, message_id, text)
        except Exception:
            log.exception("command handling failed")
            try:
                self.card(chat_id, cards.error_card("内部错误", "命令处理异常（已记录日志）", "重试一次；持续失败查 docker logs"), reply_to=message_id)
            except Exception:
                pass

    def daily_digest(self):
        while True:
            now = datetime.now(timezone(timedelta(hours=8)))
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            time.sleep(max(1, (target - now).total_seconds()))
            try:
                self.send_daily_digest()
            except Exception:
                log.exception("daily digest failed")

    def send_daily_digest(self):
        pending = sorted(self.gh.list_candidates())
        runs = self.gh.list_runs(workflow="publish.yml", limit=5)
        releases = [f"{r['id']} {r.get('conclusion', r.get('status'))}" for r in runs[:3]]
        approvals = sum(
            1 for event in self.journal.load_events()
            if event.get("type") == "gate_approved"
            and event.get("ts", "") > (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        )
        return self.feishu.send_card(self.config["owner_open_id"],
                                    cards.daily_card(pending, "详见 Actions 探针 Job Summary", releases, approvals),
                                    receive_id_type="open_id")

    def run(self):
        self.watchdog.start()
        threading.Thread(target=self.daily_digest, name="digest", daemon=True).start()
        log.info("intake bot starting (bootstrap=%s commit=%s)", self.config["bootstrap"], self.config["commit_sha"])
        from lark_oapi.ws import Client as WsClient
        handler = (lark.EventDispatcherHandler.builder("", "")
                   .register_p2_im_message_receive_v1(self.on_event)
                   .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(lambda event: None)
                   .register_p2_im_chat_member_bot_added_v1(lambda event: None).build())
        # INFO connection logs include temporary WebSocket credentials.
        ws = WsClient(self.config["app_id"], self.config["app_secret"], event_handler=handler, log_level=lark.LogLevel.WARNING)
        ws.start()


def main():
    bot = Bot()
    bot.run()


if __name__ == "__main__":
    main()
