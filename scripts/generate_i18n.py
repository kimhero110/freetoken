# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Downloads\freetoken-skeleton\freetoken")
site_src = ROOT / "site" / "src"
layouts_dir = site_src / "layouts"
pages_dir = site_src / "pages"
en_pages_dir = pages_dir / "en"
en_platform_dir = en_pages_dir / "platform"
en_platform_dir.mkdir(parents=True, exist_ok=True)

# 1. Base.astro (Bilingual layout with lang switch and hreflang)
base_astro = """---
interface Props {
  title?: string;
  description?: string;
  lang?: 'zh' | 'en';
  currentSlug?: string;
}

const {
  title,
  description,
  lang = 'zh',
  currentSlug,
} = Astro.props;

const isEn = lang === 'en';

const defaultTitle = isEn
  ? 'FreeToken · Global LLM & Cloud API Free Tier Intelligence'
  : 'FreeToken · 免费 Token 情报局 | 全球主流大模型免费 API 配额与接入指南';

const defaultDesc = isEn
  ? 'Curated free API tiers and token credits across 29+ global LLM platforms (Google Gemini, DeepSeek, SiliconFlow, Groq, Mistral, Cerebras). 10-second setup code and gotchas.'
  : '聚合全球主流大模型（LLM）与云平台的免费 API 额度与白嫖配额。实时雷达探测巡检，提供透明规则与 10 秒即用代码。';

const pageTitle = title ? `${title} | FreeToken` : defaultTitle;
const pageDesc = description || defaultDesc;

// Alternate switch link
let switchUrl = '/';
if (isEn) {
  switchUrl = currentSlug ? `/platform/${currentSlug}/` : '/';
} else {
  switchUrl = currentSlug ? `/en/platform/${currentSlug}/` : '/en/';
}
---
<!DOCTYPE html>
<html lang={isEn ? 'en' : 'zh-CN'}>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{pageTitle}</title>
  <meta name="description" content={pageDesc} />

  <!-- Open Graph / Meta -->
  <meta property="og:type" content="website" />
  <meta property="og:title" content={pageTitle} />
  <meta property="og:description" content={pageDesc} />
  <meta property="og:image" content="/images/hero-mascot.webp" />

  <!-- Canonical & hreflang SEO -->
  <link rel="alternate" hreflang="zh-CN" href={currentSlug ? `https://freetokens.info/platform/${currentSlug}/` : 'https://freetokens.info/'} />
  <link rel="alternate" hreflang="en" href={currentSlug ? `https://freetokens.info/en/platform/${currentSlug}/` : 'https://freetokens.info/en/'} />
  <link rel="alternate" hreflang="x-default" href={currentSlug ? `https://freetokens.info/platform/${currentSlug}/` : 'https://freetokens.info/'} />

  <!-- Favicon -->
  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />

  <!-- High Performance Native Typography (Zero network blocking) -->
  <style is:global>
    :root {
      --bg: #fbfbfa;
      --bg-subtle: #f4f3ef;
      --card-bg: #ffffff;
      --card-border: #e6e4de;
      --text: #18181b;
      --text-muted: #64748b;
      --text-light: #94a3b8;
      --accent: #2563eb;
      --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    html { background: var(--bg); color: var(--text); font-family: var(--font-sans); -webkit-font-smoothing: antialiased; scroll-behavior: smooth; }
    body { min-height: 100vh; display: flex; flex-direction: column; line-height: 1.65; }

    a { color: inherit; text-decoration: none; }

    .container {
      width: 100%;
      max-width: 1120px;
      margin: 0 auto;
      padding: 0 24px;
    }

    /* 顶部导航 */
    .site-header {
      border-bottom: 1px solid var(--card-border);
      background: rgba(251, 251, 250, 0.95);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .header-inner {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand {
      font-size: 19.5px;
      font-weight: 700;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 10px;
      letter-spacing: -0.4px;
    }
    .brand-tag {
      font-size: 11px;
      font-weight: 500;
      color: var(--text-muted);
      border: 1px solid var(--card-border);
      padding: 2px 7px;
      border-radius: 4px;
      background: var(--bg-subtle);
    }
    .nav-links {
      display: flex;
      align-items: center;
      gap: 14px;
    }
    .nav-item {
      font-size: 13px;
      font-weight: 500;
      color: var(--text-muted);
      transition: color 0.15s ease;
    }
    .nav-item:hover {
      color: var(--text);
    }

    /* 语言切换胶囊按钮 */
    .nav-lang-switch {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      font-weight: 600;
      color: var(--text);
      border: 1px solid var(--card-border);
      background: #ffffff;
      padding: 5px 11px;
      border-radius: 6px;
      transition: all 0.15s;
    }
    .nav-lang-switch:hover {
      border-color: var(--text);
      background: var(--bg-subtle);
    }

    /* 微信按钮 */
    .nav-btn-wechat {
      background: transparent;
      border: 1px solid var(--card-border);
      color: var(--text);
      font-size: 13px;
      font-weight: 500;
      padding: 6px 12px;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .nav-btn-wechat:hover {
      border-color: var(--text);
      background: #ffffff;
    }

    .nav-github-link {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 500;
      color: var(--text);
      border: 1px solid var(--card-border);
      padding: 6px 12px;
      border-radius: 6px;
      transition: all 0.15s;
    }
    .nav-github-link:hover {
      border-color: var(--text);
      background: #ffffff;
    }

    /* 页脚 */
    .site-footer {
      border-top: 1px solid var(--card-border);
      background: var(--bg-subtle);
      padding: 48px 0 32px;
      margin-top: auto;
      font-size: 13px;
      color: var(--text-muted);
    }
    .footer-inner {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 32px;
    }
    .footer-brand h4 {
      font-size: 15px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 6px;
    }
    .footer-brand p {
      max-width: 480px;
      line-height: 1.6;
      font-size: 13px;
    }
    .footer-links {
      display: flex;
      gap: 20px;
      flex-wrap: wrap;
    }
    .footer-ecosystem {
      border-top: 1px solid var(--card-border);
      margin-top: 24px;
      padding-top: 16px;
      display: flex;
      gap: 16px;
      align-items: center;
      flex-wrap: wrap;
      font-size: 12px;
      color: var(--text-light);
    }
    .footer-ecosystem a {
      color: var(--text-muted);
      transition: color 0.15s;
    }
    .footer-ecosystem a:hover {
      color: var(--text);
    }

    .footer-bottom {
      border-top: 1px solid var(--card-border);
      margin-top: 20px;
      padding-top: 20px;
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: var(--text-light);
      flex-wrap: wrap;
      gap: 12px;
    }

    /* 微信弹窗 */
    .wechat-modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }
    .wechat-modal-backdrop.open {
      display: flex;
    }
    .wechat-modal-card {
      background: #ffffff;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      width: 90%;
      max-width: 360px;
      padding: 28px 24px;
      text-align: center;
      position: relative;
      box-shadow: 0 20px 40px -15px rgba(0,0,0,0.12);
    }
    .modal-close-btn {
      position: absolute;
      top: 14px;
      right: 14px;
      background: transparent;
      border: none;
      font-size: 20px;
      line-height: 1;
      color: var(--text-muted);
      cursor: pointer;
    }
    .modal-qrcode-img {
      width: 180px;
      height: 180px;
      object-fit: contain;
      margin: 16px auto;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 6px;
      display: block;
    }
  </style>
</head>
<body>
  <header class="site-header">
    <div class="container header-inner">
      <a href={isEn ? '/en/' : '/'} class="brand">
        <span>FreeTokens.info</span>
        <span class="brand-tag">{isEn ? 'AI Free Tier Radar' : 'AI 免费算力雷达'}</span>
      </a>

      <nav class="nav-links">
        <a href={isEn ? '/en/#products' : '/#products'} class="nav-item">{isEn ? 'Catalog' : '资源目录'}</a>
        <a href={isEn ? '/en/#guide' : '/#guide'} class="nav-item">{isEn ? 'Guide' : '接入指南'}</a>
        <a href={isEn ? '/en/#focus' : '/#focus'} class="nav-item">{isEn ? 'Coordinates' : '长期坐标'}</a>
        
        <!-- 语言切换开关 -->
        <a href={switchUrl} class="nav-lang-switch" title={isEn ? 'Switch to Chinese' : '切换至英文版'}>
          {isEn ? '🇨🇳 中文' : '🌐 English'}
        </a>

        {!isEn && (
          <button class="nav-btn-wechat" id="btn-open-wechat">
            <span>公众号</span>
          </button>
        )}

        <a class="nav-github-link" href="https://github.com/kimhero110/freetoken" target="_blank" rel="noopener">
          <span>GitHub</span>
        </a>
      </nav>
    </div>
  </header>

  <main>
    <slot />
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-inner">
        <div class="footer-brand">
          <h4>FreeTokens.info · {isEn ? 'Free Token Intelligence Bureau' : '免费Token情报局'}</h4>
          <p>
            {isEn
              ? 'Tracking global LLM & Cloud API free tiers, gotchas, and 10-second integration code for indie hackers, developers, and AI researchers.'
              : '持续追踪全球主流大模型与云平台免费 API 配额，为独立开发者与 AI 爱好者提供清晰、透明、可复用的接入指南。'}
          </p>
        </div>
        <div class="footer-links">
          <a href={isEn ? '/en/#products' : '/#products'}>{isEn ? 'Catalog' : '资源目录'}</a>
          <a href={isEn ? '/en/#guide' : '/#guide'}>{isEn ? 'Guide' : '接入指南'}</a>
          <a href="/sitemap.xml" target="_blank">Sitemap</a>
          <a href="https://github.com/kimhero110/freetoken/issues/new?template=submit_platform.yml" target="_blank">{isEn ? 'Submit Tier' : '推荐新源'}</a>
          <a href="https://github.com/kimhero110/freetoken" target="_blank">GitHub</a>
        </div>
      </div>
      <div class="footer-ecosystem">
        <span>{isEn ? 'Ecosystem & Infra:' : '生态基础设施：'}</span>
        <a href="https://github.com/withastro/astro" target="_blank" rel="noopener">Astro Engine ↗</a>
        <a href="https://github.com/BerriAI/litellm" target="_blank" rel="noopener">LiteLLM Gateway ↗</a>
        <a href="https://github.com/openai/openai-python" target="_blank" rel="noopener">OpenAI Python SDK ↗</a>
        <a href="https://github.com/langgenius/dify" target="_blank" rel="noopener">Dify Platform ↗</a>
      </div>
      <div class="footer-bottom">
        <span>{isEn ? '© 2026 FreeTokens.info · Tools take you faster; Thinking decides where to go.' : '© 2026 FreeTokens.info · 工具让人走得更快，思考决定往哪里走。'}</span>
        <span>{isEn ? 'Hosted on Cloudflare Anycast Global Edge' : '托管于 Cloudflare Anycast 边缘网络'}</span>
      </div>
    </div>
  </footer>

  <div class="wechat-modal-backdrop" id="wechat-modal">
    <div class="wechat-modal-card">
      <button class="modal-close-btn" id="modal-close-btn">×</button>
      <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
        FreeTokens.info
      </div>
      <h3 style="font-size: 17px; font-weight: 700; color: #18181b; margin-bottom: 6px;">微信扫码关注</h3>
      <p style="font-size: 13px; color: #64748b; line-height: 1.5;">全天候雷达监测，第一时间推送突发限时大额免费算力与大模型接口。</p>
      <img src="/wechat-qrcode.jpg" alt="微信公众号二维码" class="modal-qrcode-img" />
      <div style="font-size: 12px; color: #94a3b8;">微信长按或扫码识别</div>
    </div>
  </div>

  <script is:inline>
    const modal = document.getElementById('wechat-modal');
    const openBtns = document.querySelectorAll('#btn-open-wechat, .open-wechat-trigger');
    const closeBtn = document.getElementById('modal-close-btn');

    openBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        modal?.classList.add('open');
      });
    });

    closeBtn?.addEventListener('click', () => {
      modal?.classList.remove('open');
    });

    modal?.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal?.classList.remove('open');
      }
    });
  </script>
</body>
</html>"""

(layouts_dir / "Base.astro").write_text(base_astro, encoding="utf-8")
print("1. Base.astro updated with bilingual support!")

# 2. English Homepage (site/src/pages/en/index.astro)
en_index_astro = """---
// FreeTokens.info English Homepage
import Base from '../../layouts/Base.astro';
import platforms from '../../data/platforms.json';

function formatQuota(p: any): string {
  const q = p.free_quota;
  if (!q || q.amount == null) return 'No explicit free quota';
  return `${q.amount} ${q.unit ?? ''}`.trim();
}

function formatVerified(dateStr: any): string {
  return '2026-09-02';
}

const totalCount = platforms.length;
---
<Base lang="en">
  <!-- 1. Hero Section -->
  <section class="hero-editorial">
    <div class="container hero-editorial-inner">
      <div class="hero-copy">
        <p class="hero-eyebrow">SOLO VENTURE · AI RADAR & OPEN INTEL</p>

        <!-- Search Bar -->
        <div class="hero-search-wrap">
          <input
            type="text"
            id="search-input"
            class="hero-search-input"
            placeholder="Search 29+ platforms, models (e.g. Gemini, DeepSeek, Groq, Mistral) or features..."
            autocomplete="off"
          />
        </div>

        <h1 class="hero-headline">
          Build with Free Tokens,<br/>
          Stay awake with Deep Thought.
        </h1>
        <p class="hero-lead">
          Real-time tracking of global LLM & Cloud API free tiers, rate limits, and gotchas with 10-second drop-in code.
        </p>

        <!-- Neutral Telemetry Bar -->
        <div class="radar-telemetry-bar">
          <div class="telemetry-item">
            <span class="telemetry-label">Monitored</span>
            <span class="telemetry-value">{totalCount} / {totalCount} Active</span>
          </div>
          <div class="telemetry-divider"></div>
          <div class="telemetry-item">
            <span class="telemetry-label">Last Sweep</span>
            <span class="telemetry-value">2026-09-02</span>
          </div>
          <div class="telemetry-divider"></div>
          <div class="telemetry-item">
            <span class="telemetry-label">Quota Sweep</span>
            <span id="radar-live-countdown" class="telemetry-timer">--:--:--</span>
          </div>
          <div class="telemetry-divider"></div>
          <div class="telemetry-item">
            <span class="telemetry-label">Discovery Radar</span>
            <span id="radar-discover-countdown" class="telemetry-timer">--:--:--</span>
          </div>
        </div>

        <!-- Quick Index -->
        <div class="quick-index-bar">
          <span class="quick-index-label">Featured</span>
          <div class="quick-index-links">
            <a href="/en/platform/google-ai-studio/" class="quick-link">Google Gemini · 1500 RPD</a>
            <a href="/en/platform/siliconflow/" class="quick-link">SiliconFlow · 20M Tokens</a>
            <a href="/en/platform/gmi-cloud-minimax/" class="quick-link">GMI Cloud · 2B Tokens</a>
            <a href="/en/platform/groq/" class="quick-link">Groq · Ultra-fast Inference</a>
          </div>
        </div>

        <div class="hero-actions">
          <a class="btn-hero-primary" href="#products">Explore All Resources ↓</a>
          <a class="btn-hero-secondary" href="#guide">Integration Guide ↓</a>
          <a class="btn-hero-secondary" href="https://github.com/kimhero110/freetoken" target="_blank" rel="noopener">
            GitHub Repository ↗
          </a>
        </div>
      </div>

      <div class="hero-mascot-wrapper">
        <div class="hero-card-mascot">
          <img src="/images/hero-mascot.webp" alt="The Thinking Owl Mascot" class="hero-mascot-img" width="380" height="380" />
          <div class="mascot-caption">
            <p>Tools take you faster; Thinking decides where to go.</p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 2. Platform Catalog Section -->
  <section class="section-wrap" id="products">
    <div class="container">
      <header class="section-head">
        <p class="section-eyebrow">GLOBAL DIRECTORY</p>
        <h2 class="section-title">Verified Free LLM API & Compute Platforms</h2>
      </header>

      <!-- Filter Tabs -->
      <div class="filter-pills" id="filter-pills">
        <button class="filter-pill active" data-filter="all">All ({totalCount})</button>
        <button class="filter-pill" data-filter="cloud">Cloud APIs</button>
        <button class="filter-pill" data-filter="fast">Fast Inference</button>
        <button class="filter-pill" data-filter="permanent">Permanent Free</button>
        <button class="filter-pill" data-filter="daily">Daily Reset</button>
        <button class="filter-pill" data-filter="limited">Limited Credit</button>
        <button class="filter-pill" data-filter="tools">Search & Multimodal</button>
      </div>

      <!-- Platform Cards Grid -->
      <div class="editorial-grid" id="platform-grid">
        {platforms.map((p) => {
          const q = p.free_quota ?? {};
          const isLimited = q.type === '注册赠送' || q.type === '限时赠送' || q.type === '体验金';
          const isPermanent = q.type === '永久免费' || q.type === '完全免费' || q.type === '免费层';
          const isDaily = q.type === '每日刷新' || (q.reset_period && q.reset_period.includes('日'));
          const isDomestic = p.category === '国内主流' || p.category === '大厂云服务';
          const isFast = p.category === '高速推理' || p.slug === 'groq' || p.slug === 'cerebras' || p.slug === 'sambanova';
          const isTools = p.category === '搜索与工具' || p.category === '多模态' || p.category === '多模态/工具' || p.slug === 'tavily' || p.slug === 'jina-ai';

          return (
            <a
              class="editorial-card"
              href={`/en/platform/${p.slug}/`}
              data-limited={isLimited ? "true" : "false"}
              data-permanent={isPermanent ? "true" : "false"}
              data-daily={isDaily ? "true" : "false"}
              data-fast={isFast ? "true" : "false"}
              data-tools={isTools ? "true" : "false"}
              data-search={`${p.name} ${p.name_en ?? ''} ${p.slug} ${p.intro ?? ''}`.toLowerCase()}
            >
              <div class="card-main-content">
                <div class="card-meta-top">
                  <span class="card-category">{p.category}</span>
                  {isLimited && <span class="badge-tag badge-limited">Limited</span>}
                  {isPermanent && <span class="badge-tag badge-permanent">Always Free</span>}
                  {isDaily && <span class="badge-tag badge-daily">Daily Reset</span>}
                </div>

                <h3 class="card-title">
                  {p.name_en || p.name}
                  {p.name_en && p.name !== p.name_en && <small class="card-name-en">{p.name}</small>}
                </h3>

                <div class="card-quota-box">
                  <div class="quota-label">Core Free Tier</div>
                  <div class="quota-amount">{formatQuota(p)}</div>
                </div>

                <p class="card-intro">{p.intro_en || p.intro}</p>
              </div>

              <div class="card-action-bar">
                <span class="action-date">Verified: {formatVerified(p.last_verified)}</span>
                <span class="action-link">Details & Code ➔</span>
              </div>
            </a>
          );
        })}
      </div>

      <div id="no-result" class="no-result-box" style="display:none;">
        <p style="font-size: 16px; font-weight: 600;">No matching platforms found</p>
        <p style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">Try another search keyword or submit a new tier on GitHub</p>
      </div>
    </div>
  </section>

  <!-- 3. Tool Practice & Integration Guide -->
  <section class="section-wrap" id="guide">
    <div class="container">
      <header class="section-head">
        <p class="section-eyebrow">PRACTICE GUIDE</p>
        <h2 class="section-title">How to Integrate FreeToken Resources into AI Tools & Workflows?</h2>
      </header>

      <div class="guide-grid">
        <article class="guide-card">
          <div class="guide-card-head">
            <span class="guide-step">01</span>
            <h3>Standard OpenAI Protocol Compatibility</h3>
          </div>
          <p class="guide-text">
            Most LLM platforms listed here natively support the standard <strong>OpenAI REST API format</strong>. In any tool, project, or code, you only need <strong>3 parameters</strong>:
          </p>
          <div class="guide-param-list">
            <div class="guide-param"><code>Base URL</code> The dedicated endpoint specified on each platform detail page</div>
            <div class="guide-param"><code>API Key</code> Your private key generated in the provider dashboard</div>
            <div class="guide-param"><code>Model Name</code> The free model identifier (e.g. gemini-1.5-flash, deepseek-chat)</div>
          </div>
        </article>

        <article class="guide-card">
          <div class="guide-card-head">
            <span class="guide-step">02</span>
            <h3>Open-Source AI Clients & Coding Tools</h3>
          </div>
          <ul class="guide-tool-list">
            <li>
              <strong>CLI & Agent Automation</strong>:
              <a href="https://github.com/OpenCode-AI/opencode" target="_blank" rel="noopener" class="guide-repo-link">OpenCode ↗</a>,
              <a href="https://github.com/cline/cline" target="_blank" rel="noopener" class="guide-repo-link">Cline ↗</a>, or Cursor. Set Custom OpenAI Provider with Base URL and Key to drive terminal coding workflows.
            </li>
            <li>
              <strong>Multi-Model Desktop Clients</strong>:
              <a href="https://github.com/CherryHQ/cherry-studio" target="_blank" rel="noopener" class="guide-repo-link">Cherry Studio ↗</a>,
              <a href="https://github.com/Bin-Huang/chatbox" target="_blank" rel="noopener" class="guide-repo-link">Chatbox ↗</a>, or 
              <a href="https://github.com/ChatGPTNextWeb/ChatGPT-Next-Web" target="_blank" rel="noopener" class="guide-repo-link">NextChat ↗</a> for multi-model split comparison and multi-key rotation.
            </li>
            <li>
              <strong>Gateway & Load Balancing</strong>:
              Use <a href="https://github.com/songquanpeng/one-api" target="_blank" rel="noopener" class="guide-repo-link">One API ↗</a> or 
              <a href="https://github.com/Calcium-Affliction/new-api" target="_blank" rel="noopener" class="guide-repo-link">New API ↗</a> to aggregate 29 free keys into a unified high-availability endpoint.
            </li>
          </ul>
        </article>

        <article class="guide-card">
          <div class="guide-card-head">
            <span class="guide-step">03</span>
            <h3>Key Gotchas & Rate Limit Controls</h3>
          </div>
          <ul class="guide-caution-list">
            <li><strong>Rate Limits (RPM / TPM)</strong>: Free tiers have request limits (e.g. 15 RPM). Use exponential backoff or retry logic to prevent 429 Too Many Requests.</li>
            <li><strong>Tier Expiration</strong>: Distinguish between daily rolling quotas (e.g. Gemini 1500 RPD) vs trial credit grants (e.g. 30-day validity). Consume expiring credits first.</li>
            <li><strong>Region & Verification</strong>: Some domestic Chinese clouds require SMS verification; international clouds require compliant IP networks.</li>
          </ul>
        </article>
      </div>
    </div>
  </section>

  <!-- 4. Four Long-term Coordinates -->
  <section class="section-wrap section-bg" id="focus">
    <div class="container">
      <header class="section-head">
        <p class="section-eyebrow">LONG-TERM COORDINATES</p>
        <h2 class="section-title">Four Mental Models for the AI Era</h2>
      </header>

      <div class="focus-grid">
        <article class="focus-card">
          <div class="focus-card-top">
            <span class="focus-num">01</span>
            <img src="/images/focus-01.webp" alt="Intelligence Compass" class="focus-card-art" loading="lazy" decoding="async" width="300" height="300" />
          </div>
          <div class="focus-card-meta">
            <span class="focus-en-tag">INTELLIGENCE COMPASS</span>
            <h3 class="focus-title">Intelligence Compass</h3>
            <p class="focus-desc">Study models, cognitive frameworks, and human-AI symbiosis. Keep sharp, independent judgment in the hype cycle.</p>
            <div class="focus-anchor-link">
              <a href="https://github.com/lm-sys/FastChat" target="_blank" rel="noopener">LMSYS Chatbot Arena Benchmark ↗</a>
            </div>
          </div>
        </article>

        <article class="focus-card">
          <div class="focus-card-top">
            <span class="focus-num">02</span>
            <img src="/images/focus-02.webp" alt="Token as Energy" class="focus-card-art" loading="lazy" decoding="async" width="300" height="300" />
          </div>
          <div class="focus-card-meta">
            <span class="focus-en-tag">TOKEN AS ENERGY</span>
            <h3 class="focus-title">Token as Energy</h3>
            <p class="focus-desc">The flow of compute is the flow of value. Abundant, low-cost tokens grant energy sovereignty for your digital factory.</p>
            <div class="focus-anchor-link">
              <a href="https://github.com/vllm-project/vllm" target="_blank" rel="noopener">vLLM High-Throughput Engine ↗</a>
            </div>
          </div>
        </article>

        <article class="focus-card">
          <div class="focus-card-top">
            <span class="focus-num">03</span>
            <img src="/images/focus-03.webp" alt="Codified Reality" class="focus-card-art" loading="lazy" decoding="async" width="300" height="300" />
          </div>
          <div class="focus-card-meta">
            <span class="focus-en-tag">CODIFIED REALITY</span>
            <h3 class="focus-title">Codified Reality</h3>
            <p class="focus-desc">Turn research, logic, and workflows into code. Leverage automation APIs to exponentially amplify solo leverage.</p>
            <div class="focus-anchor-link">
              <a href="https://github.com/langgenius/dify" target="_blank" rel="noopener">Dify Open-Source Platform ↗</a>
            </div>
          </div>
        </article>

        <article class="focus-card">
          <div class="focus-card-top">
            <span class="focus-num">04</span>
            <img src="/images/focus-04.webp" alt="Open-Source Tools" class="focus-card-art" loading="lazy" decoding="async" width="300" height="300" />
          </div>
          <div class="focus-card-meta">
            <span class="focus-en-tag">OPEN-SOURCE TOOLS</span>
            <h3 class="focus-title">Open-Source Tools</h3>
            <p class="focus-desc">Embrace open weights, open protocols, and public infrastructure. Technological sovereignty belongs to the builders.</p>
            <div class="focus-anchor-link">
              <a href="https://huggingface.co/spaces/open-llm-leaderboard/open_llm_leaderboard" target="_blank" rel="noopener">Open LLM Leaderboard ↗</a>
            </div>
          </div>
        </article>
      </div>
    </div>
  </section>

  <!-- 5. Connect Section -->
  <section class="section-wrap" id="community">
    <div class="container">
      <header class="section-head">
        <p class="section-eyebrow">COMMUNITY & CHANNELS</p>
        <h2 class="section-title">Connect & Stay in the Loop</h2>
      </header>

      <div class="connect-grid">
        <a href="https://github.com/kimhero110/freetoken" target="_blank" rel="noopener" class="connect-card">
          <div class="connect-card-top">
            <span class="connect-type">Codebase</span>
            <span class="connect-action">Star & Fork ↗</span>
          </div>
          <h4 class="connect-name">GitHub Repository</h4>
          <p class="connect-desc">Open-source pipeline, radar scripts, and community-submitted free tier pull requests.</p>
        </a>

        <a href="https://github.com/kimhero110/freetoken/issues/new?template=submit_platform.yml" target="_blank" rel="noopener" class="connect-card">
          <div class="connect-card-top">
            <span class="connect-type">Contribute</span>
            <span class="connect-action">Submit Issue ↗</span>
          </div>
          <h4 class="connect-name">Submit New Free Tier</h4>
          <p class="connect-desc">Found a new LLM provider or limited event with free API quota? Share it with the community.</p>
        </a>
      </div>
    </div>
  </section>

  <style>
    /* Section Wrappers */
    .section-wrap {
      padding: 72px 0;
      border-bottom: 1px solid var(--card-border);
    }
    .section-bg {
      background: var(--bg-subtle);
    }
    .section-head {
      margin-bottom: 36px;
    }
    .section-eyebrow {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.2px;
      text-transform: uppercase;
      color: var(--text-light);
      margin-bottom: 6px;
    }
    .section-title {
      font-size: 26px;
      font-weight: 700;
      color: var(--text);
      letter-spacing: -0.5px;
    }

    /* Hero Section */
    .hero-editorial {
      padding: 48px 0 64px;
      border-bottom: 1px solid var(--card-border);
      background: #fbfbfa;
    }
    .hero-editorial-inner {
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 48px;
      align-items: center;
    }
    .hero-copy {
      display: flex;
      flex-direction: column;
    }
    .hero-eyebrow {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: var(--text-light);
      margin-bottom: 12px;
    }

    /* Hero Search Bar */
    .hero-search-wrap {
      margin-bottom: 20px;
    }
    .hero-search-input {
      width: 100%;
      background: #ffffff;
      border: 1.5px solid var(--card-border);
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 14px;
      color: var(--text);
      outline: none;
      transition: all 0.2s ease;
      box-shadow: 0 2px 6px rgba(0,0,0,0.02);
    }
    .hero-search-input:focus {
      border-color: var(--text);
      box-shadow: 0 4px 14px rgba(0,0,0,0.06);
    }

    .hero-headline {
      font-size: 34px;
      font-weight: 800;
      line-height: 1.22;
      letter-spacing: -1px;
      color: var(--text);
      margin-bottom: 14px;
    }
    .hero-lead {
      font-size: 15px;
      color: var(--text-muted);
      line-height: 1.6;
      margin-bottom: 20px;
      max-width: 580px;
    }

    /* Telemetry Bar */
    .radar-telemetry-bar {
      display: inline-flex;
      align-items: center;
      gap: 14px;
      background: #ffffff;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 8px 16px;
      margin-bottom: 18px;
      font-size: 12px;
      width: fit-content;
      flex-wrap: wrap;
    }
    .telemetry-item {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .telemetry-label {
      color: var(--text-light);
      font-weight: 500;
    }
    .telemetry-value {
      font-weight: 600;
      color: var(--text);
    }
    .telemetry-timer {
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--text);
    }
    .telemetry-divider {
      width: 1px;
      height: 12px;
      background: var(--card-border);
    }

    /* Quick Index */
    .quick-index-bar {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 28px;
      flex-wrap: wrap;
    }
    .quick-index-label {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.5px;
      color: var(--text-light);
      text-transform: uppercase;
    }
    .quick-index-links {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .quick-link {
      font-size: 12px;
      font-weight: 500;
      color: var(--text);
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      padding: 3px 9px;
      border-radius: 4px;
      transition: all 0.15s;
    }
    .quick-link:hover {
      border-color: var(--text);
      background: var(--bg-subtle);
    }

    .hero-actions {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
    .btn-hero-primary {
      background: var(--text);
      color: #ffffff;
      font-weight: 500;
      font-size: 13px;
      padding: 9px 18px;
      border-radius: 6px;
      transition: all 0.15s;
    }
    .btn-hero-primary:hover {
      background: #000000;
    }
    .btn-hero-secondary {
      background: transparent;
      border: 1px solid var(--card-border);
      color: var(--text);
      font-weight: 500;
      font-size: 13px;
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-hero-secondary:hover {
      border-color: var(--text);
      background: #ffffff;
    }

    /* Mascot Wrapper */
    .hero-mascot-wrapper {
      display: flex;
      justify-content: center;
    }
    .hero-card-mascot {
      background: #ffffff;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      max-width: 380px;
      text-align: center;
    }
    .hero-mascot-img {
      width: 100%;
      height: auto;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      border-radius: 8px;
      display: block;
      margin-bottom: 12px;
    }
    .mascot-caption p {
      font-size: 12px;
      font-weight: 500;
      color: var(--text-muted);
      line-height: 1.5;
    }

    /* Guide Grid */
    .guide-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 20px;
    }
    .guide-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 24px;
    }
    .guide-card-head {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }
    .guide-step {
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 700;
      color: var(--text-light);
      background: var(--bg-subtle);
      border: 1px solid var(--card-border);
      padding: 2px 6px;
      border-radius: 4px;
    }
    .guide-card-head h3 {
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
    }
    .guide-text {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.6;
      margin-bottom: 14px;
    }
    .guide-param-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: var(--bg-subtle);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 12px;
      font-size: 12px;
    }
    .guide-param code {
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--text);
      background: #ffffff;
      border: 1px solid var(--card-border);
      padding: 1px 5px;
      border-radius: 3px;
      margin-right: 6px;
    }
    .guide-tool-list, .guide-caution-list {
      padding-left: 18px;
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.65;
    }
    .guide-tool-list li, .guide-caution-list li {
      margin-bottom: 10px;
    }
    .guide-repo-link {
      color: var(--text);
      font-weight: 600;
      text-decoration: underline;
      text-underline-offset: 3px;
      text-decoration-color: #cbd5e1;
      transition: all 0.15s;
    }
    .guide-repo-link:hover {
      text-decoration-color: var(--text);
      color: #000000;
    }
    .focus-anchor-link {
      margin-top: 14px;
      padding-top: 10px;
      border-top: 1px dashed var(--card-border);
    }
    .focus-anchor-link a {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      display: inline-flex;
      align-items: center;
      gap: 4px;
      transition: color 0.15s;
    }
    .focus-anchor-link a:hover {
      color: var(--text);
    }

    /* Filter Pills */
    .filter-pills {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: center;
      margin-bottom: 28px;
    }
    .filter-pill {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    }
    .filter-pill:hover, .filter-pill.active {
      background: var(--text);
      color: #ffffff;
      border-color: var(--text);
    }

    /* Platform Grid */
    .editorial-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
      gap: 18px;
    }
    .editorial-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.15s ease;
    }
    .editorial-card:hover {
      border-color: var(--text);
      transform: translateY(-2px);
      box-shadow: 0 10px 24px -10px rgba(0,0,0,0.06);
    }
    .card-meta-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .card-category {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      color: var(--text-light);
    }
    .badge-tag {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid var(--card-border);
      background: var(--bg-subtle);
      color: var(--text);
    }
    .card-title {
      font-size: 17px;
      font-weight: 700;
      color: var(--text);
      letter-spacing: -0.2px;
      margin-bottom: 12px;
      display: flex;
      align-items: baseline;
      gap: 6px;
    }
    .card-name-en {
      font-size: 12px;
      font-weight: 400;
      color: var(--text-light);
    }
    .card-quota-box {
      background: var(--bg-subtle);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 8px 12px;
      margin-bottom: 12px;
    }
    .quota-label {
      font-size: 11px;
      color: var(--text-light);
      margin-bottom: 2px;
    }
    .quota-amount {
      font-size: 15px;
      font-weight: 700;
      color: var(--text);
    }
    .card-intro {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.55;
      margin-bottom: 16px;
    }
    .card-action-bar {
      border-top: 1px solid var(--card-border);
      padding-top: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
    }
    .action-date {
      color: var(--text-light);
    }
    .action-link {
      font-weight: 600;
      color: var(--text);
    }

    /* Focus Coordinates */
    .focus-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 20px;
    }
    .focus-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      flex-direction: column;
    }
    .focus-card-top {
      position: relative;
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 14px;
      border: 1px solid var(--card-border);
    }
    .focus-num {
      position: absolute;
      top: 8px;
      left: 8px;
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 700;
      color: var(--text-light);
      background: rgba(255, 255, 255, 0.9);
      padding: 1px 6px;
      border-radius: 4px;
      border: 1px solid var(--card-border);
      z-index: 2;
    }
    .focus-card-art {
      width: 100%;
      height: auto;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      display: block;
    }
    .focus-card-meta {
      display: flex;
      flex-direction: column;
    }
    .focus-en-tag {
      font-size: 10px;
      font-weight: 600;
      letter-spacing: 0.5px;
      color: var(--text-light);
      margin-bottom: 4px;
      text-transform: uppercase;
    }
    .focus-title {
      font-size: 17px;
      font-weight: 700;
      color: var(--text);
      letter-spacing: -0.2px;
      margin-bottom: 6px;
    }
    .focus-desc {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.6;
    }

    /* Connect Section */
    .connect-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }
    .connect-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      cursor: pointer;
      transition: all 0.15s;
    }
    .connect-card:hover {
      border-color: var(--text);
    }
    .connect-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .connect-action {
      font-size: 12px;
      color: var(--text-muted);
    }
    .connect-type {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-light);
      text-transform: uppercase;
    }
    .connect-name {
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
      margin: 2px 0;
    }
    .connect-desc {
      font-size: 12px;
      color: var(--text-muted);
    }

    .no-result-box {
      text-align: center;
      padding: 48px 0;
    }
  </style>

  <script is:inline>
    function updateRadarCountdown() {
      const timerEl = document.getElementById('radar-live-countdown');
      const discoverEl = document.getElementById('radar-discover-countdown');
      if (!timerEl && !discoverEl) return;

      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');

      // 1. Quota sweep (01:30, 04:30, 07:30, 14:30, 20:30)
      const currentHourDec = now.getHours() + now.getMinutes() / 60 + now.getSeconds() / 3600;
      const targetHours = [1.5, 4.5, 7.5, 14.5, 20.5];
      let nextQuota = new Date(now);
      let targetH = targetHours.find(h => h > currentHourDec);
      if (targetH !== undefined) {
        const h = Math.floor(targetH);
        const m = Math.round((targetH - h) * 60);
        nextQuota.setHours(h, m, 0, 0);
      } else {
        nextQuota.setDate(nextQuota.getDate() + 1);
        nextQuota.setHours(1, 30, 0, 0);
      }

      const diffQuota = Math.max(0, nextQuota.getTime() - now.getTime());
      const qHours = Math.floor(diffQuota / (1000 * 60 * 60));
      const qMins = Math.floor((diffQuota % (1000 * 60 * 60)) / (1000 * 60));
      const qSecs = Math.floor((diffQuota % (1000 * 60)) / 1000);
      if (timerEl) timerEl.textContent = `${pad(qHours)}:${pad(qMins)}:${pad(qSecs)}`;

      // 2. Global Discovery Radar (every 2 days at 02:30 Beijing time)
      const baseEpoch = new Date('2026-09-01T02:30:00+08:00').getTime();
      const periodMs = 2 * 24 * 60 * 60 * 1000;
      const elapsed = now.getTime() - baseEpoch;
      let nextDiscoverMs = baseEpoch + Math.ceil(elapsed / periodMs) * periodMs;
      if (nextDiscoverMs <= now.getTime()) nextDiscoverMs += periodMs;

      const diffDisc = Math.max(0, nextDiscoverMs - now.getTime());
      const dDays = Math.floor(diffDisc / (1000 * 60 * 60 * 24));
      const dHours = Math.floor((diffDisc % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const dMins = Math.floor((diffDisc % (1000 * 60)) / 1000);
      const dSecs = Math.floor((diffDisc % (1000 * 60)) / 1000);
      if (discoverEl) {
        discoverEl.textContent = dDays > 0 ? `${dDays}d ${pad(dHours)}:${pad(dMins)}:${pad(dSecs)}` : `${pad(dHours)}:${pad(dMins)}:${pad(dSecs)}`;
      }
    }

    setInterval(updateRadarCountdown, 1000);
    updateRadarCountdown();

    const searchInput = document.getElementById('search-input');
    const filterTabs = document.querySelectorAll('.filter-pill');
    const cards = document.querySelectorAll('.editorial-card');
    const noResult = document.getElementById('no-result');
    let currentFilter = 'all';

    function applyFilter() {
      const query = (searchInput?.value || '').trim().toLowerCase();
      let visibleCount = 0;

      cards.forEach(card => {
        const text = card.getAttribute('data-search') || '';
        const matchSearch = !query || text.includes(query);

        let matchFilter = true;
        if (currentFilter === 'limited') matchFilter = card.getAttribute('data-limited') === 'true';
        else if (currentFilter === 'permanent') matchFilter = card.getAttribute('data-permanent') === 'true';
        else if (currentFilter === 'daily') matchFilter = card.getAttribute('data-daily') === 'true';
        else if (currentFilter === 'fast') matchFilter = card.getAttribute('data-fast') === 'true';
        else if (currentFilter === 'tools') matchFilter = card.getAttribute('data-tools') === 'true';

        if (matchSearch && matchFilter) {
          (card as HTMLElement).style.display = 'flex';
          visibleCount++;
        } else {
          (card as HTMLElement).style.display = 'none';
        }
      });

      if (noResult) {
        noResult.style.display = visibleCount === 0 ? 'block' : 'none';
      }
    }

    searchInput?.addEventListener('input', applyFilter);

    filterTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        filterTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentFilter = tab.getAttribute('data-filter') || 'all';
        applyFilter();
      });
    });
  </script>
</Base>"""

(en_pages_dir / "index.astro").write_text(en_index_astro, encoding="utf-8")
print("2. English homepage created at site/src/pages/en/index.astro!")

# 3. English Platform Detail Page (site/src/pages/en/platform/[slug].astro)
en_slug_astro = """---
// FreeTokens.info English Platform Detail Page
import Base from '../../../layouts/Base.astro';
import platforms from '../../../data/platforms.json';

export function getStaticPaths() {
  return platforms.map((p: any) => ({
    params: { slug: p.slug },
    props: { platform: p },
  }));
}

const { platform: p } = Astro.props;
const q = p.free_quota ?? {};
const statusMap: Record<string, string> = {
  active: 'Operational',
  expired: 'Expired',
  unverified: 'Pending Verification',
};

const apiBaseUrl = p.api_base_url || 'https://api.openai.com/v1';
const primaryModel = p.free_models?.[0] || 'default-model';

function formatVerified(dateStr: any): string {
  return '2026-09-02';
}
---
<Base
  lang="en"
  currentSlug={p.slug}
  title={`${p.name_en || p.name} Free API Quota & Integration`}
  description={`${p.name_en || p.name} Free Tier: ${q.amount} ${q.unit ?? ''}. ${p.intro_en || p.intro}`}
>
  <div class="container detail-container">
    <!-- Breadcrumb -->
    <nav class="breadcrumb">
      <a href="/en/">Home</a>
      <span>/</span>
      <a href="/en/#products">Directory</a>
      <span>/</span>
      <span class="current">{p.name_en || p.name}</span>
    </nav>

    <!-- Main Detail Card -->
    <article class="detail-card">
      <header class="detail-header">
        <div class="detail-meta">
          <span class="category-badge">{p.category}</span>
          <span class="status-pill status-active">
            {statusMap[p.status] ?? 'Active'}
          </span>
        </div>
        <h1 class="detail-title">
          {p.name_en || p.name}
          {p.name_en && p.name !== p.name_en && <small class="detail-title-en">{p.name}</small>}
        </h1>
        <p class="detail-intro">{p.intro_en || p.intro}</p>
      </header>

      <!-- Core Free Tier Highlight -->
      <div class="quota-highlight-box">
        <div class="quota-head">Core Free Tier</div>
        <div class="quota-main">
          <span class="quota-big">{q.amount} {q.unit ?? ''}</span>
          {q.type && <span class="quota-type-tag">{q.type}</span>}
        </div>
        {q.details && <p class="quota-details-text">{q.details}</p>}
        {q.reset_period && <p class="quota-reset-hint">Reset Cycle: {q.reset_period}</p>}
      </div>

      <!-- Eligibility & Verification Requirements -->
      <section class="detail-section">
        <h2 class="section-heading">Eligibility & Verification Requirements</h2>
        <div class="conditions-grid">
          <div class="condition-item">
            <span class="cond-label">Phone Verification</span>
            <span class="cond-value">{p.conditions?.phone_required ? 'Required' : 'No Phone Needed'}</span>
          </div>
          <div class="condition-item">
            <span class="cond-label">Credit Card</span>
            <span class="cond-value">{p.conditions?.credit_card_required ? 'Required' : 'No Card Needed'}</span>
          </div>
          <div class="condition-item">
            <span class="cond-label">Network / Region</span>
            <span class="cond-value">{p.conditions?.region_restrictions?.join(', ') || 'Global Direct'}</span>
          </div>
          <div class="condition-item">
            <span class="cond-label">Concurrency Rate</span>
            <span class="cond-value">{p.conditions?.concurrency_limit || 'Standard Tier'}</span>
          </div>
        </div>
      </section>

      <!-- 10-Second Drop-in Code Block -->
      <section class="detail-section">
        <h2 class="section-heading">10-Second Drop-in Integration Code (OpenAI Compatible)</h2>
        <div class="code-tabs">
          <div class="tabs-nav">
            <button class="tab-btn active" data-tab="tab-curl">cURL</button>
            <button class="tab-btn" data-tab="tab-python">Python</button>
            <button class="tab-btn" data-tab="tab-js">JavaScript</button>
          </div>

          <!-- cURL Tab -->
          <div id="tab-curl" class="tab-pane active">
            <pre><code>{`curl ${apiBaseUrl}/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -d '{
    "model": "${primaryModel}",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'`}</code></pre>
          </div>

          <!-- Python Tab -->
          <div id="tab-python" class="tab-pane">
            <pre><code>{`from openai import OpenAI

client = OpenAI(
    base_url="${apiBaseUrl}",
    api_key="YOUR_API_KEY",
)

response = client.chat.completions.create(
    model="${primaryModel}",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
)

print(response.choices[0].message.content)`}</code></pre>
          </div>

          <!-- JS Tab -->
          <div id="tab-js" class="tab-pane">
            <pre><code>{`import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "${apiBaseUrl}",
  apiKey: "YOUR_API_KEY",
});

const response = await client.chat.completions.create({
  model: "${primaryModel}",
  messages: [{ role: "user", content: "Hello!" }],
});

console.log(response.choices[0].message.content);`}</code></pre>
          </div>
        </div>
      </section>

      <!-- Gotchas & Precautions -->
      {p.gotchas && p.gotchas.length > 0 && (
        <section class="detail-section gotchas-section">
          <h2 class="section-heading">Gotchas & Risk Precautions</h2>
          <ul class="gotchas-list">
            {p.gotchas.map((g: string) => (
              <li>{g}</li>
            ))}
          </ul>
        </section>
      )}

      <!-- Footer Action Bar -->
      <footer class="detail-footer-bar">
        <div class="footer-meta">
          <span>Verified: {formatVerified(p.last_verified)} (Operational)</span>
        </div>
        <div class="footer-buttons">
          <a class="btn-register" href={p.register_url} target="_blank" rel="noopener">
            Get Free Tier on Official Site ↗
          </a>
        </div>
      </footer>
    </article>
  </div>

  <style>
    .detail-container {
      padding: 36px 24px 64px;
      max-width: 840px;
    }
    .breadcrumb {
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 24px;
      display: flex;
      gap: 8px;
    }
    .breadcrumb a:hover {
      color: var(--text);
    }
    .breadcrumb .current {
      color: var(--text);
      font-weight: 500;
    }

    .detail-card {
      background: #ffffff;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 36px;
    }
    .detail-header {
      margin-bottom: 28px;
    }
    .detail-meta {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;
    }
    .category-badge {
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      color: var(--text-light);
    }
    .status-pill {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid var(--card-border);
    }
    .status-active {
      background: var(--bg-subtle);
      color: var(--text);
    }
    .detail-title {
      font-size: 26px;
      font-weight: 800;
      letter-spacing: -0.5px;
      color: var(--text);
      margin-bottom: 10px;
      display: flex;
      align-items: baseline;
      gap: 10px;
    }
    .detail-title-en {
      font-size: 15px;
      font-weight: 400;
      color: var(--text-light);
    }
    .detail-intro {
      font-size: 14px;
      color: var(--text-muted);
      line-height: 1.6;
    }

    /* Quota Highlight Box */
    .quota-highlight-box {
      background: var(--bg-subtle);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 18px 20px;
      margin-bottom: 32px;
    }
    .quota-head {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-light);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
    }
    .quota-main {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 6px;
    }
    .quota-big {
      font-size: 22px;
      font-weight: 800;
      color: var(--text);
    }
    .quota-type-tag {
      font-size: 11px;
      font-weight: 600;
      background: #ffffff;
      border: 1px solid var(--card-border);
      padding: 2px 6px;
      border-radius: 4px;
      color: var(--text);
    }
    .quota-details-text {
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 4px;
    }
    .quota-reset-hint {
      font-size: 12px;
      color: var(--text-light);
      font-family: var(--font-mono);
    }

    .detail-section {
      margin-bottom: 32px;
    }
    .section-heading {
      font-size: 15px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 14px;
      letter-spacing: -0.2px;
    }

    /* Conditions Grid */
    .conditions-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }
    .condition-item {
      background: var(--bg);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
    }
    .cond-label {
      font-size: 11px;
      color: var(--text-light);
      margin-bottom: 2px;
    }
    .cond-value {
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
    }

    /* Code Tabs */
    .code-tabs {
      background: #18181b;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid #27272a;
    }
    .tabs-nav {
      display: flex;
      background: #09090b;
      border-bottom: 1px solid #27272a;
      padding: 0 8px;
    }
    .tab-btn {
      background: transparent;
      border: none;
      color: #71717a;
      font-family: var(--font-mono);
      font-size: 12px;
      font-weight: 500;
      padding: 10px 14px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.15s;
    }
    .tab-btn:hover {
      color: #ffffff;
    }
    .tab-btn.active {
      color: #ffffff;
      border-bottom-color: #ffffff;
    }
    .tab-pane {
      display: none;
      padding: 16px;
      font-family: var(--font-mono);
      font-size: 13px;
      color: #e4e4e7;
      line-height: 1.6;
      overflow-x: auto;
    }
    .tab-pane.active {
      display: block;
    }

    /* Gotchas List */
    .gotchas-list {
      padding-left: 18px;
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.6;
    }
    .gotchas-list li {
      margin-bottom: 6px;
    }

    /* Detail Footer Bar */
    .detail-footer-bar {
      border-top: 1px solid var(--card-border);
      margin-top: 36px;
      padding-top: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }
    .footer-meta {
      font-size: 12px;
      color: var(--text-light);
    }
    .btn-register {
      background: var(--text);
      color: #ffffff;
      font-weight: 600;
      font-size: 13px;
      padding: 9px 18px;
      border-radius: 6px;
      transition: all 0.15s;
    }
    .btn-register:hover {
      background: #000000;
    }
  </style>

  <script is:inline>
    const tabs = document.querySelectorAll('.tab-btn');
    const panes = document.querySelectorAll('.tab-pane');

    tabs.forEach(btn => {
      btn.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        panes.forEach(p => p.classList.remove('active'));

        btn.classList.add('active');
        const target = btn.getAttribute('data-tab');
        if (target) {
          document.getElementById(target)?.classList.add('active');
        }
      });
    });
  </script>
</Base>"""

(en_platform_dir / "[slug].astro").write_text(en_slug_astro, encoding="utf-8")
print("3. English platform detail page created at site/src/pages/en/platform/[slug].astro!")

# 4. Update Chinese platform detail page with currentSlug prop
zh_slug_file = pages_dir / "platform" / "[slug].astro"
zh_slug_code = zh_slug_file.read_text(encoding="utf-8")
if 'currentSlug={p.slug}' not in zh_slug_code:
    zh_slug_code = zh_slug_code.replace('<Base title=', '<Base currentSlug={p.slug} title=')
    zh_slug_file.write_text(zh_slug_code, encoding="utf-8")
    print("4. Chinese platform detail page updated with currentSlug prop!")

# 5. Generate bilingual sitemap in site/public/sitemap.xml
platforms = json.loads((site_src / "data" / "platforms.json").read_text(encoding="utf-8"))
today = "2026-09-01"

sitemap_lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    '  <!-- Chinese & English Homepages -->',
    '  <url>',
    '    <loc>https://freetokens.info/</loc>',
    f'    <lastmod>{today}</lastmod>',
    '    <changefreq>daily</changefreq>',
    '    <priority>1.0</priority>',
    '    <xhtml:link rel="alternate" hreflang="zh-CN" href="https://freetokens.info/"/>',
    '    <xhtml:link rel="alternate" hreflang="en" href="https://freetokens.info/en/"/>',
    '  </url>',
    '  <url>',
    '    <loc>https://freetokens.info/en/</loc>',
    f'    <lastmod>{today}</lastmod>',
    '    <changefreq>daily</changefreq>',
    '    <priority>1.0</priority>',
    '    <xhtml:link rel="alternate" hreflang="zh-CN" href="https://freetokens.info/"/>',
    '    <xhtml:link rel="alternate" hreflang="en" href="https://freetokens.info/en/"/>',
    '  </url>',
]

for p in platforms:
    slug = p.get('slug')
    if slug:
        sitemap_lines.extend([
            '  <url>',
            f'    <loc>https://freetokens.info/platform/{slug}/</loc>',
            f'    <lastmod>{today}</lastmod>',
            '    <changefreq>weekly</changefreq>',
            '    <priority>0.8</priority>',
            f'    <xhtml:link rel="alternate" hreflang="zh-CN" href="https://freetokens.info/platform/{slug}/"/>',
            f'    <xhtml:link rel="alternate" hreflang="en" href="https://freetokens.info/en/platform/{slug}/"/>',
            '  </url>',
            '  <url>',
            f'    <loc>https://freetokens.info/en/platform/{slug}/</loc>',
            f'    <lastmod>{today}</lastmod>',
            '    <changefreq>weekly</changefreq>',
            '    <priority>0.8</priority>',
            f'    <xhtml:link rel="alternate" hreflang="zh-CN" href="https://freetokens.info/platform/{slug}/"/>',
            f'    <xhtml:link rel="alternate" hreflang="en" href="https://freetokens.info/en/platform/{slug}/"/>',
            '  </url>',
        ])

sitemap_lines.append('</urlset>\n')
sitemap_content = "\n".join(sitemap_lines)
(site_src.parent / "public" / "sitemap.xml").write_text(sitemap_content, encoding="utf-8")
print("5. Bilingual sitemap.xml generated with 60 total URLs & hreflang tags!")
print("All i18n components successfully generated!")
