#!/usr/bin/env python3
"""Automated verification sweep for unverified / flagged platforms.

Selects platforms whose canonical entry is unverified, carries a 待核实 free
quota, is tagged for manual re-check (待人工复核 / 雷达新源), or has never been
stamped ``last_verified``. Each authorized public source is fetched, any pending
platform_update candidate for the same slug+URL is reused, and a conclusion is
classified per source:

  has_free_tier | no_free_tier | unclear

Hard boundaries:
- data/platforms/*.yaml is never modified here; last_verified is stamped only
  by human approval through review_candidates.py.
- ``unclear`` never produces a candidate: approving a null-quota candidate
  would stamp 无免费额度 onto the platform, so inconclusive sources are
  report-only.
- Paid LLM extraction is never called directly. When it is allowed (and not
  --skip-extract/--dry-run), sources that need extraction are written as a
  forced changed.json for scripts/extract.py; ``--finalize`` re-classifies
  afterwards from the candidates extract wrote.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"
CANDIDATES_DIR = ROOT / "data" / "candidates"
DEFAULT_WORK_DIR = Path(os.environ.get("RUNNER_TEMP") or (ROOT / ".cache" / "verify-run"))

if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
    from scripts.fetch_sources import fetch_text
    from scripts.source_verification import authorized_source_urls
    from scripts.extract import validate_extracted
else:
    from .fetch_sources import fetch_text
    from .source_verification import authorized_source_urls
    from .extract import validate_extracted

PENDING_MARK = "待核实"
TARGET_TAGS = ("待人工复核", "雷达新源")
CONCLUSIONS = ("has_free_tier", "no_free_tier", "unclear")

# Free-tier marketing language that should have produced a non-null extraction.
# A null extraction next to these hints means the LLM likely missed the free
# tier, so the honest answer is unclear, not no_free_tier.
FREE_TIER_HINT_RE = re.compile(
    r"free tier|free credit|free tokens|免费额度|免费试用|新用户.*赠|注册即送|trial credit| complimentary"
)

SOURCES_CACHE_NAME = "verify-sources.json"
SUMMARY_NAME = "verify-summary.json"
CHANGED_NAME = "changed.json"


def _parse_verified_date(value) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def selection_reasons(entry: dict, *, today: date | None = None, stale_days: int = 45) -> list[str]:
    """Why this platform needs automatic verification, empty when it does not.

    Radar leftover tags alone do not re-queue a platform that was verified within
    ``stale_days``; stale / missing stamps do, which automatically covers the
    previously flagged active platforms without anyone naming their slugs.
    """
    if not isinstance(entry, dict):
        return []
    if stale_days < 1:
        raise ValueError("stale_days must be >= 1")
    reasons = []
    if entry.get("status") == "unverified":
        reasons.append("status:unverified")
    quota = entry.get("free_quota")
    if isinstance(quota, dict) and (quota.get("amount") == PENDING_MARK or quota.get("type") == PENDING_MARK):
        reasons.append("free_quota:待核实")
    verified_on = _parse_verified_date(entry.get("last_verified"))
    if verified_on is None:
        reasons.append("last_verified:missing")
    else:
        age = (today or date.today()) - verified_on
        if age.days >= stale_days:
            reasons.append(f"last_verified:stale:{age.days}d")
    # Leftover radar tags only matter when the stamp is missing/stale (already
    # recorded above) or the platform is still unverified / 待核实.
    tags = entry.get("tags")
    if isinstance(tags, list) and any(tag in tags for tag in TARGET_TAGS):
        if reasons:
            reasons.extend(f"tag:{tag}" for tag in TARGET_TAGS if tag in tags)
    return reasons


def needs_verification(entry: dict, *, today: date | None = None, stale_days: int = 45) -> bool:
    return bool(selection_reasons(entry, today=today, stale_days=stale_days))


def select_verification_targets(platforms_dir, *, today: date | None = None, stale_days: int = 45) -> list[dict]:
    """Pick platforms to verify; no slug list comes from a caller."""
    targets = []
    for path in sorted(Path(platforms_dir).glob("*.yaml")):
        try:
            entry = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        reasons = selection_reasons(entry, today=today, stale_days=stale_days)
        if not reasons:
            continue
        targets.append({
            "slug": path.stem,
            "name": entry.get("name", path.stem) if isinstance(entry, dict) else path.stem,
            "reasons": reasons,
            "source_urls": authorized_source_urls(entry) if isinstance(entry, dict) else [],
        })
    return targets


def classify_verification(source_text: str | None, extracted: dict | None) -> str:
    """Classify one source observation into exactly one conclusion."""
    if not isinstance(source_text, str) or not source_text.strip():
        return "unclear"
    validated = validate_extracted(extracted)
    if validated is None:
        return "unclear"
    quota = validated["free_quota"]
    amount = quota.get("amount")
    quota_type = quota.get("type")
    if (
        isinstance(amount, (int, float))
        and not isinstance(amount, bool)
        and math.isfinite(amount)
        and amount > 0
        and quota_type in {"永久", "限时", "每日"}
    ):
        return "has_free_tier"
    if amount is None and quota.get("unit") is None and quota_type is None:
        if FREE_TIER_HINT_RE.search(source_text.casefold()):
            return "unclear"
        return "no_free_tier"
    return "unclear"


def merge_conclusions(source_conclusions: list[str]) -> str:
    """One platform conclusion across sources.

    A positive free-tier finding wins. ``no_free_tier`` only wins when every
    source agreed; mixed with ``unclear`` stays ``unclear`` so a flaky page
    cannot stamp away a possible free tier.
    """
    if not source_conclusions:
        return "unclear"
    if "has_free_tier" in source_conclusions:
        return "has_free_tier"
    if source_conclusions and all(item == "no_free_tier" for item in source_conclusions):
        return "no_free_tier"
    return "unclear"


def is_renew_keep_current(candidate: dict) -> bool:
    """Whether this pending candidate is a rejected-null-wipe renewal.

    extract.write_keep_current_candidate stamps both markers; accept either so
    finalize still recognizes a hand-edited or partially rewritten renewal.
    """
    if not isinstance(candidate, dict):
        return False
    if candidate.get("verification_conclusion") == "renew_keep_current":
        return True
    extractor = candidate.get("extractor")
    return isinstance(extractor, dict) and extractor.get("type") == "reviewed_rejection_renewal"


def renew_keep_current_payload(proposed: object) -> dict | None:
    """Accept canonical free_quota/intro shapes that validate_extracted rejects.

    Renewals copy live platform YAML, which may use string amounts such as
    ``1500 万``. Those are intentional keep-current payloads, not LLM output.
    """
    if not isinstance(proposed, dict):
        return None
    quota = proposed.get("free_quota")
    intro = proposed.get("intro")
    if not isinstance(quota, dict) or not isinstance(intro, str) or not intro.strip():
        return None
    amount = quota.get("amount")
    if amount is None or amount == "无免费额度":
        return None
    return {
        "free_quota": dict(quota),
        "intro": intro.strip(),
    }


def load_pending_extraction(candidates_dir, slug: str, url: str):
    """Latest pending platform_update candidate for this slug+URL, validated.

    Returns (path, raw_candidate, validated_extraction) or None. Ordinary
    candidates whose proposed payload fails validate_extracted cannot be
    classified. ``renew_keep_current`` renewals are accepted without the
    numeric LLM schema so string quotas like ``1500 万`` still finalize.
    """
    best = None
    for path in sorted(Path(candidates_dir).glob(f"update-{slug}-*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        if data.get("candidate_type") != "platform_update":
            continue
        if data.get("platform_slug") != slug or data.get("source_url") != url:
            continue
        if data.get("status") != "pending_review":
            continue
        if is_renew_keep_current(data):
            validated = renew_keep_current_payload(data.get("proposed"))
        else:
            validated = validate_extracted(data.get("proposed"))
        if validated is None:
            continue
        if best is None or data.get("captured_at", "") >= best[1].get("captured_at", ""):
            best = (path, data, validated)
    return best


def annotate_candidate(candidate_path: Path, conclusion: str, reasons: list[str]) -> None:
    """Attach auto-verify metadata to a candidate file.

    review_candidates only reads known keys for platform_update candidates, so
    these extra fields survive load/approve untouched; conclusions also live in
    verify-summary.json as the authoritative record.
    """
    data = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return
    data["verification_conclusion"] = conclusion
    data["verification_reasons"] = [str(reason) for reason in reasons][:10]
    candidate_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _source_record(url, fetched, text, candidates_dir, slug, extract_allowed, annotate):
    """Fetch/classify a single authorized source for one platform."""
    pending = load_pending_extraction(candidates_dir, slug, url)
    reasons = []
    candidate_stem = None
    changed_entry = None
    if pending is not None:
        candidate_path, _raw, validated = pending
        candidate_stem = candidate_path.stem
        reasons.append(f"candidate:{candidate_stem}")
        if is_renew_keep_current(_raw):
            # Preserve a real free tier after a rejected null wipe. Summary uses
            # has_free_tier so counts stay in the existing contract; the candidate
            # file keeps renew_keep_current so review still sees the renewal.
            conclusion = "has_free_tier"
            reasons.append("renew_keep_current")
            if not fetched:
                reasons.append("fetch_failed")
            if annotate:
                annotate_candidate(candidate_path, "renew_keep_current", reasons)
        else:
            conclusion = classify_verification(text, validated)
            if not fetched:
                reasons.append("fetch_failed")
            quota = validated["free_quota"]
            if conclusion == "has_free_tier":
                reasons.append("extracted_positive_quota")
            elif conclusion == "no_free_tier":
                reasons.append("null_quota_without_free_hints")
            elif (
                quota.get("amount") is None
                and quota.get("unit") is None
                and quota.get("type") is None
                and fetched
                and FREE_TIER_HINT_RE.search(text.casefold())
            ):
                reasons.append("free_tier_hints_present")
            elif conclusion == "unclear" and fetched:
                reasons.append("extraction_inconclusive")
            if annotate:
                annotate_candidate(candidate_path, conclusion, reasons)
    elif not fetched:
        conclusion = "unclear"
        reasons.append("fetch_failed")
    elif extract_allowed:
        # Paid extraction is deferred to scripts/extract.py via forced changed.json;
        # the conclusion is attached by --finalize after extract writes candidates.
        conclusion = "unclear"
        reasons.append("pending_extract")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        changed_entry = {"platform": slug, "url": url, "hash": digest, "text": text}
    else:
        conclusion = "unclear"
        reasons.append("needs_extract")
    return {
        "url": url,
        "fetched": fetched,
        "conclusion": conclusion,
        "reasons": reasons,
        "candidate": candidate_stem,
    }, changed_entry


def run_sweep(platforms_dir, candidates_dir, input_dir, output_dir, limit, *,
              fetch: bool, extract_allowed: bool, annotate: bool, mode: str,
              stale_days: int = 45, today: date | None = None) -> dict:
    targets = select_verification_targets(platforms_dir, today=today, stale_days=stale_days)[:limit]
    cache_path = Path(input_dir) / SOURCES_CACHE_NAME
    cached = {}
    if not fetch and cache_path.exists():
        try:
            for item in json.loads(cache_path.read_text(encoding="utf-8")):
                cached[(item.get("slug"), item.get("url"))] = item
        except (json.JSONDecodeError, OSError):
            cached = {}

    platforms = []
    changed_entries = []
    cache_entries = []
    for target in targets:
        slug = target["slug"]
        source_records = []
        urls = target["source_urls"]
        if not urls:
            source_records.append({
                "url": None,
                "fetched": False,
                "conclusion": "unclear",
                "reasons": ["no_authorized_sources"],
                "candidate": None,
            })
        for url in urls:
            text = None
            fetched = False
            if fetch:
                text = fetch_text(url)
                fetched = text is not None
                cache_entries.append({
                    "slug": slug, "url": url, "fetched": fetched,
                    "hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if fetched else None,
                    "text": text,
                })
            else:
                item = cached.get((slug, url))
                if item and item.get("fetched") and isinstance(item.get("text"), str):
                    text = item["text"]
                    fetched = True
            record, changed_entry = _source_record(
                url, fetched, text, candidates_dir, slug, extract_allowed, annotate
            )
            source_records.append(record)
            if changed_entry is not None:
                changed_entries.append(changed_entry)
        conclusions = [record["conclusion"] for record in source_records]
        platform_reasons = []
        for record in source_records:
            for reason in record["reasons"]:
                if reason not in platform_reasons:
                    platform_reasons.append(reason)
        platforms.append({
            "slug": slug,
            "name": target["name"],
            "target_reasons": target["reasons"],
            "conclusion": merge_conclusions(conclusions),
            "reasons": platform_reasons,
            "sources": source_records,
        })

    counts = {conclusion: sum(p["conclusion"] == conclusion for p in platforms) for conclusion in CONCLUSIONS}
    summary = {
        "version": 1,
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paid_extract_allowed": extract_allowed,
        "limit": limit,
        "stale_days": stale_days,
        "selected": len(targets),
        "counts": counts,
        "extract_needed": len(changed_entries),
        "platforms": platforms,
    }

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if fetch:
        (output_dir / SOURCES_CACHE_NAME).write_text(
            json.dumps(cache_entries, ensure_ascii=False), encoding="utf-8"
        )
    if extract_allowed and changed_entries:
        (output_dir / CHANGED_NAME).write_text(
            json.dumps(changed_entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as handle:
                handle.write("extract_needed=true\n")
    (output_dir / SUMMARY_NAME).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auto-verify unverified/flagged platforms from public sources")
    parser.add_argument("--list-only", action="store_true", help="print selected targets as JSON, no network")
    parser.add_argument("--finalize", action="store_true",
                        help="skip fetching; re-classify from cached sources and candidates after extract.py ran")
    parser.add_argument("--dry-run", action="store_true",
                        help="never queue paid extraction (default when CHECK_PAID_ENABLED != true)")
    parser.add_argument("--skip-extract", action="store_true",
                        help="classify from existing pending candidates only; never queue paid extraction")
    parser.add_argument("--limit", type=int, default=20, help="max platforms this run")
    parser.add_argument("--stale-days", type=int, default=45,
                        help="re-queue platforms whose last_verified is at least this many days old")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--platforms-dir", type=Path, default=PLATFORMS_DIR)
    parser.add_argument("--candidates-dir", type=Path, default=CANDIDATES_DIR)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.limit <= 500:
        print("limit 必须在 1..500 之间", file=sys.stderr)
        return 2

    if not 1 <= args.stale_days <= 3650:
        print("stale-days 必须在 1..3650 之间", file=sys.stderr)
        return 2

    if args.list_only:
        targets = select_verification_targets(
            args.platforms_dir, stale_days=args.stale_days
        )[:args.limit]
        print(json.dumps(targets, ensure_ascii=False, indent=2))
        return 0

    paid_enabled = os.environ.get("CHECK_PAID_ENABLED") == "true"
    if args.finalize:
        fetch, extract_allowed, annotate = False, False, True
        mode = "finalize"
    else:
        fetch = True
        extract_allowed = not (args.dry_run or args.skip_extract) and paid_enabled
        annotate = not extract_allowed
        if extract_allowed:
            mode = "collect"
        elif args.skip_extract:
            mode = "collect_skip_extract"
        else:
            mode = "collect_dry"

    summary = run_sweep(
        args.platforms_dir, args.candidates_dir, args.input_dir, args.output_dir,
        args.limit, fetch=fetch, extract_allowed=extract_allowed, annotate=annotate, mode=mode,
        stale_days=args.stale_days,
    )
    print(json.dumps({
        "mode": summary["mode"],
        "selected": summary["selected"],
        "counts": summary["counts"],
        "extract_needed": summary["extract_needed"],
        "summary": str(Path(args.output_dir) / SUMMARY_NAME),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
