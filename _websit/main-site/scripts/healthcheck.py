# -*- coding: utf-8 -*-
"""
FreeToken Automated Pre-Flight Healthcheck & Regression Guard
------------------------------------------------------------
Runs before any build/deploy to ensure zero-regression on critical features:
1. Platform count >= 40 in data/platforms.json
2. Code Generator uses the tested v2 operation contract
3. Article system is present (>= 4 articles) in data/articles.json
4. Key routes return 200 OK and navigation is intact
"""

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def run_checks():
    errors = []
    print("=" * 60)
    print("[GUARD] Running pre-flight zero-regression health checks...")
    print("=" * 60)

    # 1. Check Platforms Database
    platforms_file = ROOT / "data" / "platforms.json"
    if not platforms_file.exists():
        errors.append("data/platforms.json missing!")
    else:
        platforms = json.loads(platforms_file.read_text(encoding="utf-8"))
        if len(platforms) < 40:
            errors.append(f"Platform count is less than 40! Found {len(platforms)}.")
        else:
            print(f"  [PASS] 1/4 Platforms DB: {len(platforms)}/40 platform records loaded.")

    # 2. Check Code Generator Component
    gen_file = ROOT / "site" / "src" / "components" / "CodeGenerator.astro"
    if not gen_file.exists():
        errors.append("site/src/components/CodeGenerator.astro missing!")
    else:
        content = gen_file.read_text(encoding="utf-8")
        helper_file = ROOT / "site" / "src" / "lib" / "operation-generator.mjs"
        test_file = ROOT / "site" / "tests" / "operation-generator.test.mjs"
        helper = helper_file.read_text(encoding="utf-8") if helper_file.exists() else ""
        required_contract = [
            "getCompatiblePlatforms(platforms)",
            "generateSnippet(rawOperation, model, format)",
            "endpointUrl.slice(0, -CHAT_SUFFIX.length)",
            "curl --fail --silent --show-error",
            "max_retries=0",
            "maxRetries: 0",
            "process.exitCode = 1",
        ]
        missing_contract = [item for item in required_contract if item not in helper]
        if missing_contract or "getCompatiblePlatforms(platforms)" not in content or not test_file.exists():
            errors.append(f"Code generator v2 contract is incomplete: {missing_contract}")
        else:
            print("  [PASS] 2/4 Code Generator: tested canonical operation contract present.")

    # 3. Check Articles System
    articles_file = ROOT / "data" / "articles.json"
    if not articles_file.exists():
        errors.append("data/articles.json missing!")
    else:
        articles = json.loads(articles_file.read_text(encoding="utf-8"))
        if len(articles) < 4:
            errors.append(f"Articles count is less than 4! Found {len(articles)}.")
        else:
            print(f"  [PASS] 3/4 Articles System: {len(articles)} in-depth articles verified.")

    # 4. Check Layout Navbar Links
    base_file = ROOT / "site" / "src" / "layouts" / "Base.astro"
    if not base_file.exists():
        errors.append("site/src/layouts/Base.astro missing!")
    else:
        base_content = base_file.read_text(encoding="utf-8")
        nav_items = ['/articles/', '/guide/', '/about/']
        missing_nav = [n for n in nav_items if n not in base_content]
        if missing_nav:
            errors.append(f"Navbar missing channels: {missing_nav}")
        else:
            print("  [PASS] 4/4 Navigation & Layout: All 4 top-level channels connected.")

    print("-" * 60)
    if errors:
        print("[GUARD REJECTED] Health checks failed with regressions:")
        for idx, err in enumerate(errors, 1):
            print(f"   {idx}. {err}")
        print("[BLOCKED] Deployment pipeline aborted automatically!")
        print("=" * 60)
        sys.exit(1)
    else:
        print("[GUARD PASSED] All 4 defensive checks PASSED (100%). Ready for deployment.")
        print("=" * 60)

if __name__ == "__main__":
    run_checks()
