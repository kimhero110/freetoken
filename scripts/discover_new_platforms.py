# -*- coding: utf-8 -*-
"""
FreeToken Automated Global Resource Discovery Radar (Safe Print v2.2)
--------------------------------------------------------------------
- Full domain & slug deduplication against 40 platforms
- Deep heuristic scoring for Free API / Token / LLM developer offerings
- Safe console printing on Windows GBK environment
"""

import hashlib
import os
import sys
import re
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import yaml

try:
    from .safe_http import get_public_text, pinned_public_https_request
except ImportError:
    from safe_http import get_public_text, pinned_public_https_request

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_DIR = ROOT / "data" / "platforms"
PLATFORMS_DIR.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 FreeTokenRadar/2.2"
)

# Candidate targets to sweep.
#
# The pool used to be twenty, seven of which were already in the master DB,
# so a sweep probed thirteen sites -- all of them inference platforms of one
# familiar kind. Widened here along the axes a free tier actually appears on:
# serverless inference, gateways and routers, the Chinese vendors, the big
# clouds' free layers, and the single-purpose APIs (speech, embedding,
# images, search) that hand out credits the same way.
#
# Being here is not a claim that a site is any good, or even that it exists;
# it is a claim that it is worth asking. Ones that refuse this runner are
# recorded as unreachable rather than dropped -- a blocked door is a fact
# about them, and it belongs in the ledger where it can be looked up.
TARGET_SEEDS = [
    # Serverless inference / GPU clouds
    "https://deepinfra.com",
    "https://chutes.ai",
    "https://fireworks.ai",
    "https://together.ai",
    "https://replicate.com",
    "https://anyscale.com",
    "https://baseten.co",
    "https://modal.com",
    "https://runpod.io",
    "https://lepton.ai",
    "https://fal.ai",
    "https://koyeb.com",
    "https://inferless.com",
    "https://beam.cloud",
    "https://friendli.ai",
    "https://nscale.com",
    "https://parasail.io",
    "https://avian.io",
    "https://targon.com",
    "https://atlascloud.ai",
    "https://ncompass.tech",
    "https://nineteen.ai",
    "https://venice.ai",
    "https://crusoe.ai",
    "https://vast.ai",
    "https://salad.com",
    "https://tensordock.com",
    "https://lambdalabs.com",
    "https://kluster.ai",
    "https://predibase.com",
    "https://openpipe.ai",
    "https://featherless.ai",
    "https://groq.com",
    "https://cerebras.ai",
    # Gateways, routers and aggregators
    "https://aimlapi.com",
    "https://unify.ai",
    "https://eden.ai",
    "https://portkey.ai",
    "https://helicone.ai",
    "https://requesty.ai",
    "https://glama.ai",
    "https://apipie.ai",
    "https://shuttleai.com",
    "https://llm7.io",
    "https://clarifai.com",
    "https://monsterapi.ai",
    "https://segmind.com",
    # Model labs with their own API
    "https://deepseek.com",
    "https://upstage.ai",
    "https://writer.com",
    "https://reka.ai",
    "https://arcee.ai",
    "https://liquid.ai",
    "https://allenai.org",
    "https://qwen.ai",
    "https://z.ai",
    "https://llama.com",
    # Chinese vendors and clouds
    "https://siliconflow.cn",
    "https://ppinfra.com",
    "https://lanyun.net",
    "https://suanli.cn",
    "https://bigmodel.cn",
    "https://chatglm.cn",
    "https://modelbest.cn",
    "https://sensetime.com",
    "https://tiangong.cn",
    "https://xverse.cn",
    "https://baai.ac.cn",
    "https://360.cn",
    "https://ctyun.cn",
    "https://jiutian.10086.cn",
    "https://hailuoai.com",
    "https://doubao.com",
    "https://yuanbao.tencent.com",
    "https://kimi.com",
    # Hyperscalers with a free layer worth watching
    "https://cloud.google.com",
    "https://ai.azure.com",
    "https://databricks.com",
    "https://snowflake.com",
    "https://vercel.com",
    "https://nvidia.com",
    # Speech, embedding, image and video APIs that hand out credits
    "https://nomic.ai",
    "https://mixedbread.com",
    "https://voyageai.com",
    "https://deepgram.com",
    "https://assemblyai.com",
    "https://elevenlabs.io",
    "https://fish.audio",
    "https://gladia.io",
    "https://speechmatics.com",
    "https://resemble.ai",
    "https://play.ht",
    "https://stability.ai",
    "https://ideogram.ai",
    "https://recraft.ai",
    "https://leonardo.ai",
    "https://getimg.ai",
    "https://runwayml.com",
    "https://civitai.com",
    # Search and retrieval APIs, the other half of an agent's bill
    "https://exa.ai",
    "https://serper.dev",
    "https://firecrawl.dev",
    "https://linkup.so",
    "https://you.com",
    "https://brave.com",
    "https://perplexity.ai",
    # Agent platforms that resell tokens
    "https://dify.ai",
    "https://coze.com",
    "https://langflow.org",
    "https://poe.com",
]


def sanitize_str(s: str) -> str:
    """Strip characters that cannot be encoded in GBK."""
    if not s:
        return ""
    # Keep standard ascii and basic chinese
    return re.sub(r'[^\x20-\x7E\u4e00-\u9fa5]', ' ', s).strip()


def get_existing_domains() -> set[str]:
    domains = set()
    for yf in PLATFORMS_DIR.glob("*.yaml"):
        domains.add(yf.stem.lower())
        try:
            data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
            for key in ("website", "register_url", "docs_url", "api_base_url"):
                if url := data.get(key):
                    if host := urlparse(url).netloc.lower():
                        domains.add(host)
                        domains.add(re.sub(r"^www\.", "", host))
                        domains.add(host.split(".")[0])
        except Exception:
            pass
    return domains


# A landing page is not the whole site, and for most of these it is the least
# informative part of it: doubao, chatglm and modelbest all scrape to nothing
# at the root. Pricing and docs are where a free tier is written down.
PAGES = ("", "/pricing", "/docs")

# The strongest single signal there is, and one request wide. A host that
# answers 401 at /v1/models speaks the OpenAI API, whatever its front page
# happens to render in a browser.
OPENAI_SHAPES = (
    "https://api.{host}/v1/models",
    "https://{host}/api/v1/models",
    "https://{host}/v1/models",
)
KEYWORDS = ["free tier", "free api", "api key", "free credits", "developer",
            "pricing", "trial", "tokens", "免费", "额度", "体验金"]
MATCH = 3
API_BONUS = 3
WORKERS = 8


def score_text(text: str) -> int:
    lower = text.lower()
    return sum(1 for word in KEYWORDS if word in lower)


def read_page(url: str) -> dict | None:
    body = get_public_text(url, headers={"User-Agent": UA}, timeout=5)
    soup = BeautifulSoup(body, "html.parser")
    title = (soup.title.string if soup.title else "").strip()
    for tag in soup(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return {"title": sanitize_str(title)[:50], "text": text[:2000],
            "score": score_text(text), "url": url}


def extract_page_data(url: str) -> dict | None:
    """Read the front page, the pricing page and the docs; keep the best."""
    best, title = None, ""
    for path in PAGES:
        try:
            page = read_page(url.rstrip("/") + path)
        except Exception:
            continue
        title = title or page["title"]
        if best is None or page["score"] > best["score"]:
            best = dict(page, page=page["url"], url=url)
    if best is not None:
        # The name belongs to the site, so it comes from whichever page had
        # one first -- usually the front page, whatever scored highest.
        best["title"] = title or best["title"]
    return best


def bare_host(url: str) -> str:
    return re.sub(r"^www\.", "", urlparse(url).netloc.lower())


def api_signature(url: str) -> dict | None:
    """Ask the host whether it speaks the OpenAI API. A 401 is a yes."""
    host = bare_host(url)
    if not host:
        return None
    for shape in OPENAI_SHAPES:
        endpoint = shape.format(host=host)
        try:
            answer = pinned_public_https_request(
                endpoint, connect_timeout=6, read_timeout=6,
                headers={"User-Agent": UA},
                allowed_content_types=("application/json",))
        except Exception:
            continue
        if answer.status == 401:
            return {"endpoint": endpoint, "evidence": "HTTP 401 需要鉴权"}
        head = answer.body[:400]
        if answer.status == 200 and (b'"data"' in head or b'"object"' in head):
            return {"endpoint": endpoint, "evidence": "HTTP 200 返回模型列表"}
    return None


def probe_target(url: str) -> dict:
    """Everything one seed has to say, gathered in one place."""
    page = None
    try:
        page = extract_page_data(url)
    except Exception:
        page = None
    try:
        api = api_signature(url)
    except Exception:
        api = None
    return {"url": url, "page": page, "api": api}


def record(targets):
    """Write down what the sweep actually saw, one line per seed.

    Until now the radar reported only a count, so four seed URLs that have
    been refusing datacentre traffic for weeks looked exactly like a quiet
    week with nothing new on the internet.
    """
    folder = os.environ.get('RUNNER_TEMP')
    if not folder:
        return
    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "attempted": len(targets),
        "succeeded": sum(1 for t in targets if t["status"] != "probe_failed"),
        "sources": targets,
    }
    Path(folder, "fetch-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False), encoding="utf-8")


def seed_id(url):
    # Keyed on the seed URL, not on the page: a target that has been blocked
    # for a month keeps the same id, so it can be recognised as the same one.
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


# Emitted per sweep. The pool is deliberately wide now; handing the review
# queue forty drafts in one morning is how a queue stops being read. The rest
# keep for the next sweep -- they are re-found, because nothing was written.
CANDIDATE_LIMIT = 12


def draft(url, slug, host, data, api):
    """The candidate file, written from whatever the sweep actually learned."""
    title = (data or {}).get("title") or slug.title()
    text = (data or {}).get("text") or ""
    score = (data or {}).get("score", 0)
    api_base = api["endpoint"][: -len("/models")] if api else f"{url.rstrip('/')}/v1"
    tags = ["雷达新源", "待人工复核"]
    found_by = [f"页面匹配得分 {score}/11"]
    if api:
        tags.append("OpenAI 兼容")
        found_by.append(f"{api['endpoint']} {api['evidence']}")
    evidence = [{"url": url, "checked_at": str(date.today())}]
    if data and data.get("page") and data["page"] != url:
        evidence.append({"url": data["page"], "checked_at": str(date.today())})
    if api:
        evidence.append({"url": api["endpoint"], "checked_at": str(date.today())})
    platform = {
        "schema_version": 2,
        "slug": slug,
        "name": title,
        "name_en": slug.title(),
        "category": "海外探索" if not any(c in text for c in ["免费", "元", "人民币"]) else "国内主流",
        # 雷达只证明了这个站存在、而且像个 API 平台。"有免费额度"是下一步
        # 要人去查的事，不该在这里先替它说出来。
        "intro": f"{title}：雷达捕获的候选源，免费额度与可用模型待人工核实。",
        "intro_en": f"{slug.title()}: discovered by radar; free tier and models unverified.",
        "website": url,
        "doc_url": f"{url.rstrip('/')}/docs",
        "api_base_url": api_base,
        "free_models": [],
        "free_quota": {
            "type": "待核实",
            "amount": "待核实",
            "unit": "Tokens",
            "reset_period": "待核实",
            "details": "雷达线索：" + "；".join(found_by) + "。免费额度需人工核实。",
        },
        "verification": "邮箱/GitHub",
        "status": "unverified",
        "last_verified": None,
        "tags": tags,
        "gotchas": ["由雷达自动捕获，请人工复核免费层 RPM 限制与模型调用范围。"],
        "gotchas_en": ["Discovered by radar. Manual verification required."],
        "registration": {"url": url},
        "requirements": {
            "phone": "unknown", "card": "unknown", "region": "unknown",
            "regions": [], "rpm": None, "tpm": None,
        },
        "capabilities": {
            "operations": [],
            "tools": {
                "curl": "unknown", "openai_python": "unknown",
                "openai_node": "unknown", "cursor": "unknown",
                "openclaw": "unknown", "cherry_studio": "unknown",
            },
        },
        "evidence": evidence,
    }
    return {"candidate_type": "new_platform", "status": "pending_review",
            "platform_slug": slug, "score": score, "proposed": platform}


def run_discovery():
    print("=" * 60)
    print("[RADAR] Starting Global Free Token & API Discovery Sweep...")
    print("=" * 60)

    existing = get_existing_domains()
    print(f"[INFO] Existing indexed entities & domains: {len(existing)}")

    targets = list(dict.fromkeys(TARGET_SEEDS))
    print(f"[INFO] Probing candidate target pool ({len(targets)} candidates)...\n")

    fresh = []
    already_indexed = 0
    seen = []
    for url in targets:
        host = urlparse(url).netloc.lower()
        clean_host = re.sub(r"^www\.", "", host)
        slug_base = clean_host.split(".")[0]
        if host in existing or clean_host in existing or slug_base in existing:
            already_indexed += 1
            seen.append({"source": seed_id(url), "url": url, "status": "indexed",
                         "platform": slug_base})
            print(f"  [INDEXED] {url:<30} -> Already in master DB")
            continue
        fresh.append((url, host, slug_base))

    print(f"\n[INFO] Probing {len(fresh)} unindexed targets with {WORKERS} workers...\n")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(probe_target, [url for url, _, _ in fresh]))

    failed = 0
    qualified = []
    for (url, host, slug_base), found in zip(fresh, results):
        data, api = found["page"], found["api"]
        print(f"  [PROBING] {url:<30} ... ", end="")
        if not data and not api:
            failed += 1
            seen.append({"source": seed_id(url), "url": url, "status": "probe_failed",
                         "platform": slug_base, "error": "SEED_UNREACHABLE"})
            print("Failed (Offline / Blocked)")
            continue
        score = (data or {}).get("score", 0)
        if api or score >= MATCH:
            note = f"API {api['evidence']}" if api else f"Match {score}/11"
            print(f"FOUND! {note} | {(data or {}).get('title', '')[:25]}")
            qualified.append({"url": url, "host": host, "slug": slug_base,
                              "title": (data or {}).get("title", ""), "score": score,
                              "data": data, "api": api})
            seen.append({"source": seed_id(url), "url": url, "platform": slug_base,
                         "status": "discovered", "score": score,
                         "openai_compatible": bool(api)})
        else:
            print(f"Low relevance ({score}/11)")
            seen.append({"source": seed_id(url), "url": url, "platform": slug_base,
                         "status": "low_relevance", "score": score})

    # An endpoint that answers is worth more than a landing page that reads
    # well, but not infinitely more: a site scoring 2 with an endpoint should
    # not push out one scoring 6 without. Worth about three keywords.
    qualified.sort(key=lambda item: item["score"] + (API_BONUS if item["api"] else 0),
                   reverse=True)
    written, held = [], []
    candidates_dir = ROOT / "data" / "candidates"
    for item in qualified:
        path = candidates_dir / f"{item['slug']}.yaml"
        if path.exists():
            continue
        if len(written) >= CANDIDATE_LIMIT:
            held.append(item)
            continue
        candidates_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            yaml.dump(draft(item["url"], item["slug"], item["host"], item["data"], item["api"]),
                      handle, allow_unicode=True, sort_keys=False)
        written.append(item)
        print(f"    -> [DRAFT] data/candidates/{item['slug']}.yaml")

    record(seen)

    print("\n" + "=" * 60)
    print("[RADAR SUMMARY] Radar Sweep Finished!")
    print(f"  - Verified Existing Platforms: {already_indexed}")
    print(f"  - Fresh Scanned Targets:       {len(fresh)}")
    print(f"  - Unreachable Seeds:           {failed}")
    print(f"  - Discovered High-Match Tiers: {len(qualified)}")
    print(f"  - Drafted This Sweep:          {len(written)}")
    print("=" * 60)
    for item in seen:
        if item["status"] == "probe_failed":
            print(f"  [UNREACHABLE] {item['url']}")

    if written:
        print("\n[CANDIDATE DISCOVERY REPORT]")
        print(f"{'SLUG':<16} | {'SCORE':<6} | {'API':<4} | {'CANDIDATE URL':<30} | TITLE")
        print("-" * 82)
        for item in written:
            api = "yes" if item["api"] else "-"
            print(f"{item['slug']:<16} | {item['score']:<6} | {api:<4} | "
                  f"{item['url'][:30]:<30} | {item['title'][:20]}")
        print("-" * 82)
        print("\n提示：运行 `python scripts/review_candidates.py` 即可在终端逐条决策。")
    else:
        print("[REPORT] No new candidates; this does not imply all targets were verified.")
    if held:
        print(f"[REPORT] {len(held)} 个命中排在本轮名额之外，下一轮再交："
              + "、".join(item["slug"] for item in held[:10]))

    # A seed that will not answer is a fact about that seed, not a broken
    # sweep. Four of thirteen have been refusing this runner for weeks, and
    # returning 1 for them turned every single scheduled run red -- which is
    # why nobody noticed anything at all for ten days. The sweep has failed
    # only when it could not reach a single thing it tried.
    if fresh and failed == len(fresh):
        print("[FAIL] Every probed target was unreachable; the sweep itself did not run.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_discovery())

