"""Publish only new candidate files from a clean main worktree, idempotently."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

from scripts.check_runner import public_result


class PublishError(RuntimeError):
    pass


def semantic(value):
    if isinstance(value, dict):
        return {key: semantic(item) for key, item in value.items() if key not in {'captured_at', 'checked_at', 'last_verified'}}
    if isinstance(value, list):
        return [semantic(item) for item in value]
    return value


def command(repo, *args, check=True):
    result = subprocess.run(args, cwd=repo, text=True, encoding="utf-8", capture_output=True, timeout=90)
    if check and result.returncode:
        raise PublishError("PUBLISH_COMMAND_FAILED")
    return result


def publish(repo):
    repo = Path(repo).resolve()
    # Never include unrelated tracked edits, deletions or untracked caches.
    names = command(repo, "git", "ls-files", "--others", "--exclude-standard", "--", "data/candidates").stdout.splitlines()
    files = {}
    for name in names:
        if not re.fullmatch(r"data/candidates/[a-z0-9][a-z0-9-]*\.yaml", name):
            raise PublishError("CANDIDATE_PATH_INVALID")
        path = repo / name
        if path.is_symlink() or path.stat().st_size > 64_000:
            raise PublishError("CANDIDATE_INVALID")
        raw = path.read_text(encoding="utf-8")
        candidate = yaml.safe_load(raw)
        if not isinstance(candidate, dict) or candidate.get("candidate_type") not in {"new_platform", "platform_update"} or candidate.get("status") != "pending_review":
            raise PublishError("CANDIDATE_INVALID")
        public_result(candidate)
        files[name] = raw
    if not files:
        return {"status": "empty"}
    # Captured timestamps are stabilized by extraction; entire bytes are bound here.
    manifest = hashlib.sha256(json.dumps({name: semantic(yaml.safe_load(raw)) for name, raw in files.items()}, sort_keys=True).encode()).hexdigest()
    branch = f"auto/check-{manifest[:24]}"
    expected_repo = os.environ.get('GITHUB_REPOSITORY')
    if not expected_repo:
        expected_repo = json.loads(command(repo, 'gh', 'repo', 'view', '--json', 'nameWithOwner').stdout)['nameWithOwner']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', expected_repo):
        raise PublishError('REPOSITORY_INVALID')
    expected_owner, expected_name = expected_repo.split('/')
    def find_pr():
        pulls = json.loads(command(repo, "gh", "pr", "list", "--state", "all", "--base", "main", "--head", branch,
                                   "--json", "number,state,headRefName,headRepository,headRepositoryOwner", "--limit", "100").stdout)
        # A fork can use the same branch name. Never merge or reconcile that PR.
        pulls = [p for p in pulls if (p.get('headRepositoryOwner') or {}).get('login', '').lower() == expected_owner.lower()
                 and (p.get('headRepository') or {}).get('name') == expected_name and p.get('headRefName') == branch]
        if len(pulls) > 1:
            raise PublishError("PR_AMBIGUOUS")
        return pulls[0] if pulls else None
    pr = find_pr()
    if pr and pr["state"] != "OPEN":
        return {"status": "merged" if pr["state"] == "MERGED" else "closed", "pr": pr["number"]}
    command(repo, "git", "fetch", "--no-tags", "origin", "main")
    remote = command(repo, "git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}").stdout.split()
    with tempfile.TemporaryDirectory(prefix="candidate-publish-") as directory:
        work = Path(directory) / "tree"
        if remote:
            command(repo, "git", "fetch", "--no-tags", "origin", remote[0])
        command(repo, "git", "worktree", "add", "--detach", str(work), remote[0] if remote else "origin/main")
        try:
            if remote:
                for name, raw in files.items():
                    target = work / name
                    if not target.is_file() or semantic(yaml.safe_load(target.read_text(encoding="utf-8"))) != semantic(yaml.safe_load(raw)):
                        raise PublishError("REMOTE_CANDIDATE_CONFLICT")
            else:
                for name, raw in files.items():
                    target = work / name
                    if target.exists() and semantic(yaml.safe_load(target.read_text(encoding="utf-8"))) != semantic(yaml.safe_load(raw)):
                        raise PublishError("MAIN_CANDIDATE_CONFLICT")
                    if target.exists():
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(raw, encoding="utf-8")
                command(work, "git", "add", "--", *files)
                if command(work, "git", "diff", "--cached", "--quiet", check=False).returncode == 0:
                    return {"status": "already_present"}
                command(work, "git", "-c", "user.name=freetoken-bot[bot]", "-c",
                        "user.email=freetoken-bot[bot]@users.noreply.github.com", "commit", "-m", "chore(data): publish review candidates")
                # A lost push acknowledgement is reconciled on the next invocation.
                command(work, "git", "push", "origin", f"HEAD:refs/heads/{branch}")
            if not pr:
                body = Path(directory) / "body.md"
                body.write_text("Automated candidates only. Canonical data still requires human review.\n", encoding="utf-8")
                result = command(repo, "gh", "pr", "create", "--base", "main", "--head", branch,
                                 "--title", "chore(data): publish review candidates", "--body-file", str(body), check=False)
                pr = find_pr()
                if not pr:
                    raise PublishError("PR_CREATE_UNCONFIRMED")
            command(repo, "gh", "pr", "merge", "--auto", "--merge", "--delete-branch", str(pr["number"]))
            return {"status": "pr_created", "pr": pr["number"], "manifest": manifest}
        finally:
            command(repo, "git", "worktree", "remove", "--force", str(work))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = publish(args.repo)
    except Exception:
        result = {"status": "failed", "error": "CANDIDATE_PUBLISH_FAILED"}
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(result), encoding="utf-8")
    print(json.dumps(result))
    return int(result["status"] in {"failed", "closed"})


if __name__ == "__main__":
    raise SystemExit(main())
