#!/usr/bin/env python3
"""FreeToken 自动化内容工坊 (Content & Visual Studio)
借鉴 baoyu-skills 精髓设计：
1. 微信公众号终极排版生成器 (Inline-CSS 富文本 HTML，一键粘贴到微信后台)
2. 小红书 3:4 知识卡片流 (Style x Layout 视觉卡片系统)
3. 纯矢量自适应 SVG 架构与流程图生成器 (0成本矢量渲染)
4. 文章封面图 5 维参数生成器
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_FILE = ROOT / "site" / "src" / "data" / "platforms.json"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_platforms() -> list[dict]:
    if not PLATFORMS_FILE.exists():
        print(f"Error: {PLATFORMS_FILE} not found. Run build_data.py first.")
        return []
    return json.loads(PLATFORMS_FILE.read_text(encoding="utf-8"))


# ==========================================
# 0. 暖色极客/独立工作室风格页面模板 (ssgoo.net 风格)
# ==========================================
def render_ssgoo_base_astro() -> str:
    return """---
// 站点基础布局：暖色极客/独立工作室社群风格 (Inspired by ssgoo.net)
interface Props {
  title?: string;
  description?: string;
}
const {
  title = 'FreeToken 免费Token情报局',
  description = '聚合各大 LLM 与云平台的免费 API 额度信息，帮助你找到免费的 Token 与调用配额。',
} = Astro.props;

const pageTitle = title === 'FreeToken 免费Token情报局'
  ? title
  : `${title} - 免费Token情报局`;

const canonicalURL = new URL(Astro.url.pathname, 'https://freetokens.info').href;
---
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{pageTitle}</title>
  <meta name="description" content={description} />
  <meta name="keywords" content="免费Token, 免费大模型API, 免费LLM, Gemini免费API, DeepSeek免费API, 白嫖API, OpenAI接口免费, 免费算力, AI API Faucet" />
  <link rel="canonical" href={canonicalURL} />

  <!-- Open Graph -->
  <meta property="og:type" content="website" />
  <meta property="og:url" content={canonicalURL} />
  <meta property="og:title" content={pageTitle} />
  <meta property="og:description" content={description} />
  <meta property="og:site_name" content="FreeToken 免费Token情报局" />

  <!-- Twitter Cards -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content={pageTitle} />
  <meta name="twitter:description" content={description} />

  <link rel="icon" type="image/svg+xml" href="/favicon.svg" />

  <!-- Schema.org JSON-LD -->
  <script type="application/ld+json" set:html={JSON.stringify({
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": "FreeToken",
    "url": "https://freetokens.info/",
    "description": "全球各大 LLM 与云平台免费 API 额度情报聚合雷达",
    "inLanguage": "zh-CN",
    "potentialAction": {
      "@type": "SearchAction",
      "target": "https://freetokens.info/?q={search_term_string}",
      "query-input": "required name=search_term_string"
    }
  })} />

  <style is:global>
    :root {
      --bg: #fcfbf9;
      --bg-subtle: #f5f4ef;
      --card-bg: #ffffff;
      --card-border: #e8e6df;
      --card-border-hover: #d2cfc4;
      --text: #191816;
      --text-muted: #6b675e;
      --text-light: #9c978b;
      --primary: #191816;
      --accent-warm: #c25e00;
      --accent-green: #15803d;
      --accent-green-bg: #f0fdf4;
      --accent-green-border: #bbf7d0;
      --accent-orange-bg: #fffaf0;
      --accent-orange-border: #feebc8;
      --accent-blue-bg: #f0f7ff;
      --accent-blue-border: #cce3fe;
      --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
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

    /* 顶部导航 (Editorial Nav) */
    .site-header {
      border-bottom: 1px solid var(--card-border);
      background: rgba(252, 251, 249, 0.94);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .header-inner {
      height: 68px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand {
      font-size: 19px;
      font-weight: 700;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
      letter-spacing: -0.3px;
    }
    .brand-tag {
      font-size: 11px;
      background: var(--bg-subtle);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 2px 8px;
      border-radius: 20px;
      font-weight: 500;
    }
    .nav-links {
      display: flex;
      align-items: center;
      gap: 20px;
      font-size: 14px;
      color: var(--text-muted);
    }
    .nav-links a {
      transition: color 0.15s;
    }
    .nav-links a:hover {
      color: var(--text);
    }
    .nav-btn-wechat {
      background: var(--text);
      color: #ffffff;
      border: none;
      font-size: 13px;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .nav-btn-wechat:hover {
      background: #000000;
      transform: translateY(-1px);
    }

    /* 页脚 */
    .site-footer {
      border-top: 1px solid var(--card-border);
      background: var(--bg-subtle);
      padding: 56px 0 36px;
      margin-top: auto;
      font-size: 14px;
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
      font-size: 16px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 8px;
    }
    .footer-brand p {
      max-width: 460px;
      line-height: 1.6;
      font-size: 13px;
    }
    .footer-links {
      display: flex;
      gap: 24px;
      flex-wrap: wrap;
    }
    .footer-bottom {
      border-top: 1px solid var(--card-border);
      margin-top: 36px;
      padding-top: 24px;
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      color: var(--text-light);
      flex-wrap: wrap;
      gap: 12px;
    }

    /* 微信关注弹窗 (WeChat Modal) */
    .wechat-modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(4px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 9999;
      padding: 20px;
    }
    .wechat-modal-backdrop.open {
      display: flex;
      animation: fadeIn 0.2s ease-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: scale(0.96); }
      to { opacity: 1; transform: scale(1); }
    }
    .wechat-modal-card {
      background: #ffffff;
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 32px;
      max-width: 380px;
      width: 100%;
      text-align: center;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.12);
      position: relative;
    }
    .modal-close-btn {
      position: absolute;
      top: 16px;
      right: 16px;
      background: none;
      border: none;
      font-size: 20px;
      color: var(--text-light);
      cursor: pointer;
      padding: 4px 8px;
    }
    .modal-qrcode-img {
      width: 190px;
      height: 190px;
      border-radius: 12px;
      border: 1px solid var(--card-border);
      margin: 16px auto;
      display: block;
    }
  </style>
</head>
<body>
  <header class="site-header">
    <div class="container header-inner">
      <a class="brand" href="/">
        <span>⚡ 免费Token情报局</span>
        <span class="brand-tag">FreeTokens.info</span>
      </a>
      <div class="nav-links">
        <a href="/#products">资源目录</a>
        <a href="/#focus">四个坐标</a>
        <a href="/#community">关于与矩阵</a>
        <button class="nav-btn-wechat" id="btn-open-wechat">📱 关注公众号</button>
        <a href="https://github.com/kimhero110/freetoken" target="_blank" rel="noopener">GitHub ↗</a>
      </div>
    </div>
  </header>

  <main style="flex: 1;">
    <slot />
  </main>

  <footer class="site-footer">
    <div class="container">
      <div class="footer-inner">
        <div class="footer-brand">
          <h4>⚡ 免费Token情报局 (FreeTokens.info)</h4>
          <p>全天候自动监测全球主流大模型与云平台免费 API 额度，为独立开发者与 AI 爱好者提供清晰、透明、可复用的接入指南。</p>
        </div>
        <div class="footer-links">
          <a href="/#products">资源目录</a>
          <a href="/sitemap.xml" target="_blank">Sitemap</a>
          <a href="https://github.com/kimhero110/freetoken/issues/new?template=submit_platform.yml" target="_blank">➕ 推荐新源</a>
          <a href="https://github.com/kimhero110/freetoken" target="_blank">开源仓库</a>
        </div>
      </div>
      <div class="footer-bottom">
        <span>© 2026 免费Token情报局 · 工具让人走得更快，思考决定往哪里走。</span>
        <span>托管于 Cloudflare 全球 Anycast 边缘网络</span>
      </div>
    </div>
  </footer>

  <!-- 微信关注弹窗 -->
  <div class="wechat-modal-backdrop" id="wechat-modal">
    <div class="wechat-modal-card">
      <button class="modal-close-btn" id="modal-close-btn">×</button>
      <div style="font-size: 13px; font-weight: 700; color: #c25e00; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px;">
        ⚡ 免费Token情报局
      </div>
      <h3 style="font-size: 18px; font-weight: 700; color: #191816; margin-bottom: 6px;">微信扫码一键关注</h3>
      <p style="font-size: 13px; color: #6b675e; line-height: 1.5;">全天候雷达探测，第一时间为你推送突发限时大额免费大模型与算力羊毛！</p>
      <img src="/wechat-qrcode.jpg" alt="微信公众号二维码" class="modal-qrcode-img" />
      <div style="font-size: 12px; color: #9c978b;">👆 微信长按或扫码识别关注</div>
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


def render_ssgoo_index_astro() -> str:
    return """---
// 首页：小声工作室 (ssgoo.net) 暖色极客/独立工作室风格
import Base from '../layouts/Base.astro';
import platforms from '../data/platforms.json';

const statusText: Record<string, string> = {
  active: '有效',
  expired: '已失效',
  unverified: '待核实',
};

function formatQuota(p: any): string {
  const q = p.free_quota;
  if (!q || q.amount == null) return '暂无明确免费额度信息';
  return `${q.amount} ${q.unit ?? ''}`.trim();
}

const totalCount = platforms.length;
---
<Base>
  <!-- 1. Hero 区域 (ssgoo.net 标志性布局) -->
  <section class="hero-editorial">
    <div class="container hero-editorial-inner">
      <div class="hero-copy">
        <p class="hero-eyebrow">一人公司 · AI 免费算力雷达</p>
        <h1 class="hero-headline">
          用免费 Token 做工具，<br/>
          也提醒自己保持思考。
        </h1>
        <p class="hero-lead">
          免费Token情报局持续追踪全球各大主流大模型与云平台免费 API 额度，把分散的配额规则、避坑条件与 10 秒接入代码整理成清晰透明的实践索引。
        </p>
        <div class="hero-actions">
          <a class="btn-hero-primary" href="#products">浏览全部资源库</a>
          <button class="btn-hero-secondary open-wechat-trigger">
            关注公众号 <span aria-hidden="true">↗</span>
          </button>
        </div>
      </div>

      <div class="hero-mascot-wrapper">
        <div class="hero-card-mascot">
          <img src="/images/hero-mascot.jpg" alt="思考的科技猫头鹰插画" class="hero-mascot-img" />
          <div class="mascot-caption">
            <p>工具让人走得更快，<br/>思考决定往哪里走。</p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 2. 四个长期坐标 (Four Focus Dimensions - ssgoo.net 经典大图海报卡片) -->
  <section class="section-wrap" id="focus">
    <div class="container">
      <header class="section-head">
        <p class="section-eyebrow">四个长期坐标</p>
        <h2 class="section-title">从四个方向，建立一套长期判断系统。</h2>
      </header>

      <div class="focus-grid">
        <article class="focus-card">
          <div class="focus-card-top">
            <span class="focus-num">01</span>
            <img src="/images/focus-01.jpg" alt="AI 引导未来 智能罗盘" class="focus-card-art" />
          </div>
          <div class="focus-card-meta">
            <span class="focus-en-tag">INTELLIGENCE COMPASS</span>
            <h3 class="focus-title">AI 引导未来</h3>
            <p class="focus-desc">研究模型、思维与协作范式，在技术狂潮中保持敏锐的独立判断力与人机共生边界。</p>
          </div>
        </article>

        <article class="focus-card">
          <div class="focus-card-top">
            <span class="focus-num">02</span>
            <img src="/images/focus-02.jpg" alt="Token 就是能源 无限光子环" class="focus-card-art" />
          </div>
          <div class="focus-card-meta">
            <span class="focus-en-tag">TOKEN AS ENERGY</span>
            <h3 class="focus-title">Token 就是能源</h3>
            <p class="focus-desc">算力的流动即是价值的流动。掌握充沛且低成本的 Token，就是掌握数字工厂的能源自主权。</p>
          </div>
        </article>

        <article class="focus-card">
          <div class="focus-card-top">
            <span class="focus-num">03</span>
            <img src="/images/focus-03.jpg" alt="世界代码化 架构与阶梯" class="focus-card-art" />
          </div>
          <div class="focus-card-meta">
            <span class="focus-en-tag">CODIFIED REALITY</span>
            <h3 class="focus-title">世界代码化</h3>
            <p class="focus-desc">把研究框架、业务逻辑与工作流沉淀为代码，用自动化与接口化杠杆放大个体的生产力半径。</p>
          </div>
        </article>

        <article class="focus-card">
          <div class="focus-card-top">
            <span class="focus-num">04</span>
            <img src="/images/focus-04.jpg" alt="工具开源化 开放魔盒与钥匙" class="focus-card-art" />
          </div>
          <div class="focus-card-meta">
            <span class="focus-en-tag">OPEN-SOURCE TOOLS</span>
            <h3 class="focus-title">工具开源化</h3>
            <p class="focus-desc">拥抱开放权重、开源协议与公共基础设施，让技术的主权与自由永远留在构建者手里。</p>
          </div>
        </article>
      </div>
    </div>
  </section>

  <!-- 3. 平台资源库 (Product & Platform Grid) -->
  <section class="section-wrap section-bg" id="products">
    <div class="container">
      <header class="section-head">
        <p class="section-eyebrow">资源与实践</p>
        <h2 class="section-title">全网免费 API Token 清单与接入代码。</h2>
      </header>

      <!-- 搜索框 -->
      <div class="search-bar-wrap">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          id="search-input"
          class="search-input"
          placeholder="搜索平台名、模型（如 Gemini, GLM-4, DeepSeek, MiniMax）或特性标签..."
          autocomplete="off"
        />
      </div>

      <!-- 分类过滤 Tab -->
      <div class="filter-pills" id="filter-tabs">
        <button class="filter-pill active" data-filter="all">🌟 全部平台 ({totalCount})</button>
        <button class="filter-pill" data-filter="limited">🔥 限时大额活动</button>
        <button class="filter-pill" data-filter="permanent">💎 永久免费大厂</button>
        <button class="filter-pill" data-filter="daily">⚡ 每日刷新配额</button>
        <button class="filter-pill" data-filter="domestic">🇨🇳 国产直连</button>
        <button class="filter-pill" data-filter="tools">🛠️ Agent & 搜索</button>
        <button class="filter-pill" data-filter="multimodal">🎨 生图与语音</button>
        <button class="filter-pill" data-filter="web3">🪙 Web3 水龙头</button>
      </div>

      <!-- 平台卡片网格 (ssgoo 风格卡片) -->
      <div class="editorial-grid" id="platform-grid">
        {platforms.map((p: any) => {
          const q = p.free_quota ?? {};
          const isLimited = q.type === '限时' || (p.tags ?? []).some((t: string) => t.includes('限时') || t.includes('活动') || t.includes('专场') || t.includes('体验金') || t.includes('送'));
          const isPermanent = q.type === '永久' || (p.tags ?? []).some((t: string) => t.includes('永久'));
          const isDaily = q.type === '每日' || (p.tags ?? []).some((t: string) => t.includes('每日') || t.includes('天'));
          const isDomestic = (p.tags ?? []).some((t: string) => t.includes('国产') || t.includes('国内') || t.includes('阿里') || t.includes('百度') || t.includes('腾讯') || t.includes('智谱') || t.includes('星火'));
          const isTools = p.category === 'tools' || (p.tags ?? []).some((t: string) => t.includes('Agent') || t.includes('搜索') || t.includes('向量') || t.includes('Rerank'));
          const isMultimodal = p.category === 'multimodal' || (p.tags ?? []).some((t: string) => t.includes('图') || t.includes('语音') || t.includes('FLUX'));
          const isWeb3 = p.category === 'web3-faucet' || (p.tags ?? []).some((t: string) => t.includes('Web3') || t.includes('水龙头'));

          const searchTerms = `${p.name} ${p.name_en ?? ''} ${p.slug} ${p.intro ?? ''} ${(p.tags ?? []).join(' ')} ${formatQuota(p)}`.toLowerCase();

          return (
            <a
              class="editorial-card"
              href={`/platform/${p.slug}/`}
              data-limited={isLimited ? "true" : "false"}
              data-permanent={isPermanent ? "true" : "false"}
              data-daily={isDaily ? "true" : "false"}
              data-domestic={isDomestic ? "true" : "false"}
              data-tools={isTools ? "true" : "false"}
              data-multimodal={isMultimodal ? "true" : "false"}
              data-web3={isWeb3 ? "true" : "false"}
              data-search={searchTerms}
            >
              <div class="card-main-content">
                <div class="card-meta-top">
                  <span class="card-category">{p.category}</span>
                  {isLimited ? (
                    <span class="badge-tag badge-limited">🔥 限时福利</span>
                  ) : (
                    <span class="badge-tag badge-type">{q.type ?? '免费额度'}</span>
                  )}
                </div>

                <h3 class="card-title">
                  {p.name}
                  {p.name_en && <small class="card-name-en">{p.name_en}</small>}
                </h3>

                <div class="card-quota-box">
                  <div class="quota-label">核心免费额度</div>
                  <div class="quota-amount">{formatQuota(p)}</div>
                </div>

                <p class="card-intro">{p.intro}</p>
              </div>

              <div class="card-action-bar">
                <span class="action-date">核实：{p.last_verified}</span>
                <span class="action-link">查看详情 & 代码 ➔</span>
              </div>
            </a>
          );
        })}
      </div>

      <!-- 无搜索结果提示 -->
      <div id="no-result" class="no-result-box" style="display:none;">
        <p style="font-size: 32px; margin-bottom: 12px;">🔍</p>
        <p style="font-size: 16px; font-weight: 600;">未找到符合条件的免费平台</p>
        <p style="font-size: 13px; color: var(--text-muted); margin-top: 6px;">可尝试更换搜索词，或在 GitHub 上提交新平台推荐</p>
      </div>
    </div>
  </section>

  <!-- 4. 保持联系与矩阵 (Connect Section) -->
  <section class="section-wrap" id="community">
    <div class="container">
      <header class="section-head">
        <p class="section-eyebrow">保持联系</p>
        <h2 class="section-title">选择你习惯的入口。</h2>
      </header>

      <div class="connect-grid">
        <div class="connect-card wechat-connect-card open-wechat-trigger">
          <div class="connect-card-top">
            <span class="connect-icon">📱</span>
            <span class="connect-action">点击查看二维码 ↗</span>
          </div>
          <div>
            <span class="connect-type">微信公众号</span>
            <h3 class="connect-name">免费Token情报局</h3>
            <p class="connect-desc">突发限时免费大模型与算力羊毛推送</p>
          </div>
        </div>

        <a class="connect-card" href="https://github.com/kimhero110/freetoken" target="_blank" rel="noopener">
          <div class="connect-card-top">
            <span class="connect-icon">💻</span>
            <span class="connect-action">访问 GitHub ↗</span>
          </div>
          <div>
            <span class="connect-type">开源仓库</span>
            <h3 class="connect-name">freetoken</h3>
            <p class="connect-desc">全套自动化探测雷达与数据源开源共建</p>
          </div>
        </a>

        <a class="connect-card" href="https://github.com/kimhero110/freetoken/issues/new?template=submit_platform.yml" target="_blank" rel="noopener">
          <div class="connect-card-top">
            <span class="connect-icon">➕</span>
            <span class="connect-action">提交 Issue ↗</span>
          </div>
          <div>
            <span class="connect-type">社区共建</span>
            <h3 class="connect-name">推荐新免费源</h3>
            <p class="connect-desc">发现新免费额度？欢迎提交推荐合并入库</p>
          </div>
        </a>
      </div>
    </div>
  </section>

  <!-- 页面专属 CSS (暖色 Editorial 风格) -->
  <style>
    /* Hero Editorial */
    .hero-editorial {
      padding: 64px 0 48px;
      border-bottom: 1px solid var(--card-border);
    }
    .hero-editorial-inner {
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 48px;
      align-items: center;
    }
    @media (max-width: 860px) {
      .hero-editorial-inner { grid-template-columns: 1fr; gap: 32px; }
    }
    .hero-eyebrow {
      font-size: 13px;
      font-weight: 700;
      color: var(--accent-warm);
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 12px;
    }
    .hero-headline {
      font-size: 38px;
      font-weight: 800;
      color: var(--text);
      line-height: 1.3;
      letter-spacing: -0.5px;
      margin-bottom: 20px;
    }
    @media (max-width: 640px) {
      .hero-headline { font-size: 28px; }
    }
    .hero-lead {
      font-size: 16px;
      color: var(--text-muted);
      line-height: 1.7;
      margin-bottom: 32px;
      max-width: 520px;
    }
    .hero-actions {
      display: flex;
      gap: 16px;
      align-items: center;
      flex-wrap: wrap;
    }
    .btn-hero-primary {
      background: var(--text);
      color: #ffffff;
      font-weight: 600;
      font-size: 14px;
      padding: 12px 24px;
      border-radius: 8px;
      transition: all 0.15s;
    }
    .btn-hero-primary:hover {
      background: #000000;
      transform: translateY(-1px);
    }
    .btn-hero-secondary {
      background: transparent;
      border: 1px solid var(--card-border);
      color: var(--text);
      font-weight: 600;
      font-size: 14px;
      padding: 11px 20px;
      border-radius: 8px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .btn-hero-secondary:hover {
      border-color: var(--card-border-hover);
      background: var(--bg-subtle);
    }

    /* Hero Mascot Card (Inspired by ssgoo.net) */
    .hero-mascot-wrapper {
      display: flex;
      justify-content: center;
    }
    .hero-card-mascot {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 24px;
      padding: 20px;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.04);
      max-width: 440px;
      width: 100%;
      text-align: center;
    }
    .hero-mascot-img {
      width: 100%;
      height: auto;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      border-radius: 18px;
      border: 1px solid var(--card-border);
      margin-bottom: 16px;
      display: block;
    }
    .mascot-caption {
      font-size: 14px;
      color: var(--text-muted);
      line-height: 1.6;
      font-style: italic;
      padding: 4px 12px 6px;
    }

    /* Focus Card Image */
    .focus-img {
      width: 52px;
      height: 52px;
      border-radius: 10px;
      object-fit: cover;
      border: 1px solid var(--card-border);
    }

    /* Section Structure */
    .section-wrap {
      padding: 64px 0;
    }
    .section-bg {
      background: var(--bg-subtle);
      border-top: 1px solid var(--card-border);
      border-bottom: 1px solid var(--card-border);
    }
    .section-head {
      margin-bottom: 36px;
    }
    .section-eyebrow {
      font-size: 13px;
      font-weight: 700;
      color: var(--accent-warm);
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 6px;
    }
    .section-title {
      font-size: 26px;
      font-weight: 800;
      color: var(--text);
      letter-spacing: -0.3px;
    }

    /* Focus Grid (ssgoo.net 经典高质感海报卡片) */
    .focus-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 24px;
    }
    .focus-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 20px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.25s ease;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.02);
    }
    .focus-card:hover {
      border-color: var(--card-border-hover);
      transform: translateY(-4px);
      box-shadow: 0 16px 32px rgba(0, 0, 0, 0.06);
    }
    .focus-card-top {
      position: relative;
      margin-bottom: 20px;
      background: #faf9f6;
      border-radius: 14px;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 1px solid rgba(0, 0, 0, 0.04);
    }
    .focus-num {
      position: absolute;
      top: 12px;
      left: 14px;
      font-family: var(--font-mono);
      font-size: 13px;
      font-weight: 800;
      color: var(--text-light);
      background: rgba(255, 255, 255, 0.9);
      backdrop-filter: blur(4px);
      padding: 2px 8px;
      border-radius: 6px;
      border: 1px solid var(--card-border);
      z-index: 2;
    }
    .focus-card-art {
      width: 100%;
      height: auto;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      display: block;
      transition: transform 0.3s ease;
    }
    .focus-card:hover .focus-card-art {
      transform: scale(1.03);
    }
    .focus-card-meta {
      display: flex;
      flex-direction: column;
    }
    .focus-en-tag {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.8px;
      color: var(--accent-warm);
      margin-bottom: 4px;
      text-transform: uppercase;
    }
    .focus-title {
      font-size: 20px;
      font-weight: 800;
      color: var(--text);
      letter-spacing: -0.3px;
      margin-bottom: 8px;
    }
    .focus-desc {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.65;
    }

    /* 搜索与过滤 */
    .search-bar-wrap {
      position: relative;
      max-width: 600px;
      margin: 0 auto 24px;
    }
    .search-input {
      width: 100%;
      padding: 14px 20px 14px 44px;
      font-size: 15px;
      border-radius: 12px;
      border: 1px solid var(--card-border);
      background: var(--card-bg);
      color: var(--text);
      outline: none;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
      transition: all 0.2s;
    }
    .search-input:focus {
      border-color: var(--text);
      box-shadow: 0 0 0 3px rgba(25, 24, 22, 0.08);
    }
    .search-icon {
      position: absolute;
      left: 16px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 16px;
    }
    .filter-pills {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: center;
      margin-bottom: 36px;
    }
    .filter-pill {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s;
    }
    .filter-pill:hover, .filter-pill.active {
      background: var(--text);
      color: #ffffff;
      border-color: var(--text);
    }

    /* 平台卡片流 (Editorial Cards) */
    .editorial-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 22px;
    }
    .editorial-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: all 0.2s ease;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
    }
    .editorial-card:hover {
      border-color: var(--card-border-hover);
      transform: translateY(-3px);
      box-shadow: 0 14px 28px rgba(0, 0, 0, 0.06);
    }
    .card-meta-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .card-category {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-light);
    }
    .badge-tag {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 4px;
    }
    .badge-limited { background: #ffedd5; color: #9a3412; }
    .badge-type { background: #f1f5f9; color: #475569; }
    .card-title {
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 12px;
      display: flex;
      align-items: baseline;
      gap: 6px;
    }
    .card-name-en {
      font-size: 12px;
      color: var(--text-light);
      font-weight: 400;
    }
    .card-quota-box {
      background: var(--bg-subtle);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 10px 14px;
      margin-bottom: 14px;
    }
    .quota-label {
      font-size: 11px;
      color: var(--text-muted);
      margin-bottom: 2px;
    }
    .quota-amount {
      font-size: 16px;
      font-weight: 700;
      color: var(--accent-warm);
    }
    .card-intro {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.6;
      margin-bottom: 16px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .card-action-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-top: 1px solid var(--card-border);
      padding-top: 14px;
      margin-top: auto;
      font-size: 12px;
    }
    .action-date {
      color: var(--text-light);
    }
    .action-link {
      font-weight: 600;
      color: var(--text);
    }

    /* 社群矩阵 (Connect Grid) */
    .connect-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 20px;
    }
    .connect-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      cursor: pointer;
      transition: all 0.2s;
    }
    .connect-card:hover {
      border-color: var(--card-border-hover);
      transform: translateY(-2px);
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.04);
    }
    .connect-card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }
    .connect-icon {
      font-size: 24px;
    }
    .connect-action {
      font-size: 12px;
      font-weight: 600;
      color: var(--text);
    }
    .connect-type {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-light);
      text-transform: uppercase;
    }
    .connect-name {
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
      margin: 4px 0;
    }
    .connect-desc {
      font-size: 13px;
      color: var(--text-muted);
    }

    .no-result-box {
      text-align: center;
      padding: 60px 0;
    }
  </style>

  <script is:inline>
    const searchInput = document.getElementById('search-input');
    const filterTabs = document.querySelectorAll('.filter-pill');
    const cards = document.querySelectorAll('.editorial-card');
    const noResult = document.getElementById('no-result');
    let currentFilter = 'all';

    function applyFilter() {
      const query = (searchInput?.value || '').trim().toLowerCase();
      let visibleCount = 0;

      cards.forEach(card => {
        const searchData = card.getAttribute('data-search') || '';
        const matchesQuery = !query || searchData.includes(query);

        let matchesTab = true;
        if (currentFilter === 'limited') matchesTab = card.getAttribute('data-limited') === 'true';
        else if (currentFilter === 'permanent') matchesTab = card.getAttribute('data-permanent') === 'true';
        else if (currentFilter === 'daily') matchesTab = card.getAttribute('data-daily') === 'true';
        else if (currentFilter === 'domestic') matchesTab = card.getAttribute('data-domestic') === 'true';
        else if (currentFilter === 'tools') matchesTab = card.getAttribute('data-tools') === 'true';
        else if (currentFilter === 'multimodal') matchesTab = card.getAttribute('data-multimodal') === 'true';
        else if (currentFilter === 'web3') matchesTab = card.getAttribute('data-web3') === 'true';

        if (matchesQuery && matchesTab) {
          card.style.display = 'flex';
          visibleCount++;
        } else {
          card.style.display = 'none';
        }
      });

      if (noResult) {
        noResult.style.display = visibleCount === 0 ? 'block' : 'none';
      }
    }

    searchInput?.addEventListener('input', applyFilter);

    filterTabs.forEach(btn => {
      btn.addEventListener('click', () => {
        filterTabs.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFilter = btn.getAttribute('data-filter') || 'all';
        applyFilter();
      });
    });
  </script>
</Base>"""


def render_ssgoo_slug_astro() -> str:
    return """---
// 平台详情页：小声工作室 (ssgoo.net) 暖色高质感风格
import Base from '../../layouts/Base.astro';
import platforms from '../../data/platforms.json';

export function getStaticPaths() {
  return platforms.map((p: any) => ({
    params: { slug: p.slug },
    props: { platform: p },
  }));
}

const { platform: p } = Astro.props;
const statusText: Record<string, string> = {
  active: '有效',
  expired: '已失效',
  unverified: '待核实',
};
const q = p.free_quota ?? {};

const apiConfigMap: Record<string, { baseUrl: string; model: string; note?: string }> = {
  'deepseek': { baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  'siliconflow': { baseUrl: 'https://api.siliconflow.cn/v1', model: 'deepseek-ai/DeepSeek-V3' },
  'zhipu-ai': { baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
  'aliyun-bailian': { baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  'gmi-cloud-minimax': { baseUrl: 'https://api.gmi-serving.com/v1', model: 'MiniMaxAI/MiniMax-M3' },
  'groq': { baseUrl: 'https://api.groq.com/openai/v1', model: 'llama-3.3-70b-versatile' },
  'cerebras': { baseUrl: 'https://api.cerebras.ai/v1', model: 'llama3.1-70b' },
  'sambanova': { baseUrl: 'https://api.sambanova.ai/v1', model: 'Meta-Llama-3.1-70B-Instruct' },
  'together-ai': { baseUrl: 'https://api.together.xyz/v1', model: 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo' },
  'mistral-ai': { baseUrl: 'https://api.mistral.ai/v1', model: 'mistral-small-latest' },
  'hyperbolic': { baseUrl: 'https://api.hyperbolic.xyz/v1', model: 'deepseek-ai/DeepSeek-V3' },
  'fireworks-ai': { baseUrl: 'https://api.fireworks.ai/inference/v1', model: 'accounts/fireworks/models/llama-v3p3-70b-instruct' },
  'nebius-ai': { baseUrl: 'https://api.studio.nebius.ai/v1', model: 'meta-llama/Meta-Llama-3.1-70B-Instruct' },
  'novita-ai': { baseUrl: 'https://api.novita.ai/v3/openai', model: 'meta-llama/llama-3.1-8b-instruct' },
  'google-ai-studio': { baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai/', model: 'gemini-1.5-flash' },
  'github-models': { baseUrl: 'https://models.inference.ai.azure.com', model: 'gpt-4o' },
  'openrouter': { baseUrl: 'https://openrouter.ai/api/v1', model: 'meta-llama/llama-3.3-70b-instruct:free' },
  'cloudflare-workers-ai': { baseUrl: 'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1', model: '@cf/meta/llama-3-8b-instruct' },
  'baichuan-ai': { baseUrl: 'https://api.baichuan-ai.com/v1', model: 'Baichuan4-Air' },
  'baidu-qianfan': { baseUrl: 'https://qianfan.baidubce.com/v2', model: 'ernie-speed-128k' },
  'tencent-hunyuan': { baseUrl: 'https://api.hunyuan.cloud.tencent.com/v1', model: 'hunyuan-lite' },
  'xfyun-spark': { baseUrl: 'https://spark-api-open.xf-yun.com/v1', model: 'lite' },
  'minimax': { baseUrl: 'https://api.minimax.chat/v1', model: 'abab6.5s-chat' },
  'lingyiwanwu-01': { baseUrl: 'https://api.lingyiwanwu.com/v1', model: 'yi-lightning' },
  'jina-ai': { baseUrl: 'https://r.jina.ai', model: 'reader-v1' },
  'tavily': { baseUrl: 'https://api.tavily.com', model: 'search-v1' },
  'cohere': { baseUrl: 'https://api.cohere.com/v2', model: 'command-r-plus' },
  'pollinations': { baseUrl: 'https://pollinations.ai/p/', model: 'flux' },
  'sepolia-faucet': { baseUrl: 'https://rpc.sepolia.org', model: 'eth-sepolia' }
};

const currentConfig = apiConfigMap[p.slug] || {
  baseUrl: p.api_base_url || 'https://api.openai.com/v1',
  model: p.default_model || 'default-model'
};

const pythonCode = `# Python (使用官方 openai 库接入 ${p.name})
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_API_KEY", # 替换为你领取的免费 API Key
    base_url="${currentConfig.baseUrl}"
)

response = client.chat.completions.create(
    model="${currentConfig.model}",
    messages=[{"role": "user", "content": "你好，请用一句话介绍你自己！"}]
)

print(response.choices[0].message.content)`;

const curlCode = `# cURL 终端命令行快速测试
curl -X POST "${currentConfig.baseUrl}/chat/completions" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "${currentConfig.model}",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`;

const jsCode = `// Node.js / 浏览器 Fetch 接入
const response = await fetch("${currentConfig.baseUrl}/chat/completions", {
  method: "POST",
  headers: {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    model: "${currentConfig.model}",
    messages: [{ role: "user", content: "Hello!" }]
  })
});

const data = await response.json();
console.log(data.choices?.[0]?.message?.content || data);`;
---
<Base title={`${p.name} 免费额度`} description={p.intro}>
  <div class="detail-page-wrap">
    <div class="container">
      <div style="margin-bottom: 24px; padding-top: 32px;">
        <a href="/" class="back-link">← 返回所有免费资源清单</a>
      </div>

      <!-- 头部概览卡片 -->
      <div class="detail-editorial-card">
        <div class="detail-top-row">
          <div>
            <div class="detail-category-tag">{p.category}</div>
            <h1 class="detail-title">
              {p.name}
              {p.name_en && <small class="detail-name-en">{p.name_en}</small>}
            </h1>
            <div class="badges-row">
              <span class={`badge ${p.status}`}>{statusText[p.status] ?? p.status}</span>
              <span class="badge type">{q.type ?? '免费额度'}</span>
              {(p.tags ?? []).map((t: string) => (
                <span class="badge tag">{t}</span>
              ))}
            </div>
          </div>

          <div class="detail-action-right">
            {p.register_url && (
              <a class="btn-register-main" href={p.register_url} target="_blank" rel="nofollow noopener">
                🚀 直达领取 / 注册入口 ↗
              </a>
            )}
          </div>
        </div>

        <div class="detail-quota-callout">
          <div class="callout-label">🎁 核心免费配额：</div>
          <div class="callout-val">{q.amount != null ? `${q.amount} ${q.unit ?? ''}` : '暂无明确免费额度'}</div>
        </div>

        <p class="detail-intro">{p.intro}</p>

        <div class="detail-meta-footer">
          <span>📅 最后人工核实：{p.last_verified}</span>
          {p.last_checked && <span style="margin-left:16px;">🔄 最后自动检查：{p.last_checked}</span>}
        </div>
      </div>

      <!-- 使用条件与避坑指南 -->
      {q.conditions && q.conditions.length > 0 && (
        <div class="detail-editorial-card">
          <h2 class="card-section-title">📋 免费额度使用条件与避坑指南</h2>
          <ul class="condition-list">
            {q.conditions.map((c: string) => (
              <li>{c}</li>
            ))}
          </ul>
        </div>
      )}

      <!-- 10秒快速接入代码 -->
      <div class="detail-editorial-card">
        <h2 class="card-section-title">⚡ 10 秒快速接入代码示例</h2>
        <div class="code-box">
          <div class="code-header">
            <div class="code-tabs">
              <button class="code-tab active" data-lang="python">Python (OpenAI SDK)</button>
              <button class="code-tab" data-lang="curl">cURL 命令行</button>
              <button class="code-tab" data-lang="javascript">JavaScript (Fetch)</button>
            </div>
            <button class="copy-btn" id="copy-btn">📋 复制代码</button>
          </div>
          <pre id="code-content"><code id="code-text">{pythonCode}</code></pre>
        </div>
      </div>

      <!-- 官方直达链接 -->
      <div class="detail-editorial-card" style="margin-bottom: 64px;">
        <h2 class="card-section-title">🔗 官方相关直达链接</h2>
        <ul class="links-list">
          {p.website && <li>🌐 官方主站：<a href={p.website} target="_blank" rel="nofollow noopener">{p.website}</a></li>}
          {p.register_url && <li>🎁 免费额度/注册直达：<a href={p.register_url} target="_blank" rel="nofollow noopener">{p.register_url}</a></li>}
          {p.docs_url && <li>📖 开发者文档：<a href={p.docs_url} target="_blank" rel="nofollow noopener">{p.docs_url}</a></li>}
        </ul>
      </div>
    </div>
  </div>

  <style>
    .detail-page-wrap {
      background: var(--bg);
      min-height: calc(100vh - 180px);
    }
    .back-link {
      font-size: 14px;
      color: var(--text-muted);
      font-weight: 500;
      transition: color 0.15s;
    }
    .back-link:hover { color: var(--text); }
    .detail-editorial-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 32px;
      margin-bottom: 24px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
    }
    .detail-top-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 20px;
      margin-bottom: 20px;
    }
    .detail-category-tag {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-light);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
    }
    .detail-title {
      font-size: 28px;
      font-weight: 800;
      color: var(--text);
      display: flex;
      align-items: baseline;
      gap: 8px;
      margin-bottom: 12px;
    }
    .detail-name-en {
      font-size: 15px;
      color: var(--text-light);
      font-weight: 400;
    }
    .badges-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .badge {
      font-size: 12px;
      padding: 3px 10px;
      border-radius: 6px;
      font-weight: 600;
    }
    .badge.active { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
    .badge.type { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
    .badge.tag { background: #f4f4f5; color: #52525b; }
    .btn-register-main {
      background: var(--text);
      color: #ffffff;
      font-weight: 600;
      font-size: 14px;
      padding: 12px 24px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .btn-register-main:hover {
      background: #000000;
      transform: translateY(-1px);
    }
    .detail-quota-callout {
      background: var(--bg-subtle);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px 24px;
      margin: 20px 0;
    }
    .callout-label {
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 4px;
    }
    .callout-val {
      font-size: 22px;
      font-weight: 800;
      color: var(--accent-warm);
    }
    .detail-intro {
      font-size: 15px;
      color: var(--text);
      line-height: 1.7;
      margin-bottom: 16px;
    }
    .detail-meta-footer {
      font-size: 12px;
      color: var(--text-light);
      border-top: 1px solid var(--card-border);
      padding-top: 14px;
    }
    .card-section-title {
      font-size: 18px;
      font-weight: 700;
      color: var(--text);
      margin-bottom: 16px;
    }
    .condition-list {
      padding-left: 20px;
      line-height: 1.8;
      font-size: 14px;
      color: var(--text-muted);
    }
    .condition-list li { margin-bottom: 6px; }
    .links-list {
      list-style: none;
      line-height: 2;
      font-size: 14px;
      color: var(--text-muted);
    }
    .links-list a {
      color: var(--primary);
      text-decoration: underline;
      text-underline-offset: 3px;
    }
    .code-box {
      background: #191816;
      border: 1px solid #33312e;
      border-radius: 12px;
      overflow: hidden;
      margin-top: 12px;
    }
    .code-header {
      background: #24221f;
      padding: 10px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #33312e;
    }
    .code-tabs { display: flex; gap: 8px; }
    .code-tab {
      background: transparent;
      border: none;
      color: #9c978b;
      font-size: 12px;
      padding: 4px 10px;
      border-radius: 4px;
      cursor: pointer;
    }
    .code-tab.active { background: #33312e; color: #fdfdfc; font-weight: 600; }
    .copy-btn {
      background: #33312e;
      border: 1px solid #45423d;
      color: #e8e6df;
      padding: 4px 12px;
      border-radius: 4px;
      font-size: 12px;
      cursor: pointer;
    }
    .copy-btn:hover { background: #45423d; color: #fff; }
    pre {
      padding: 18px;
      margin: 0;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.65;
      color: #f5f4ef;
    }
  </style>

  <script is:inline define:vars={{ pythonCode, curlCode, jsCode }}>
    const tabs = document.querySelectorAll('.code-tab');
    const codeText = document.getElementById('code-text');
    const copyBtn = document.getElementById('copy-btn');

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const lang = tab.getAttribute('data-lang');
        if (lang === 'python') codeText.textContent = pythonCode;
        else if (lang === 'curl') codeText.textContent = curlCode;
        else if (lang === 'javascript') codeText.textContent = jsCode;
      });
    });

    copyBtn?.addEventListener('click', () => {
      const text = codeText?.textContent || '';
      navigator.clipboard.writeText(text).then(() => {
        const orig = copyBtn.innerText;
        copyBtn.innerText = '✅ 已复制！';
        setTimeout(() => { copyBtn.innerText = orig; }, 2000);
      });
    });
  </script>
</Base>"""


def update_frontend_files():
    (ROOT / "site" / "src" / "layouts" / "Base.astro").write_text(render_ssgoo_base_astro(), encoding="utf-8")
    (ROOT / "site" / "src" / "pages" / "index.astro").write_text(render_ssgoo_index_astro(), encoding="utf-8")
    (ROOT / "site" / "src" / "pages" / "platform" / "[slug].astro").write_text(render_ssgoo_slug_astro(), encoding="utf-8")
    print("✅ [ssgoo.net 风格 UI 模板] 成功更新 Base.astro, index.astro, [slug].astro！")


# ==========================================
# 1. 微信公众号富文本排版引擎 (WeChat HTML Engine)
# ==========================================
def generate_wechat_article(platforms: list[dict]) -> str:
    """生成带内联样式 (Inline CSS) 的微信公众号富文本 HTML，复制即可完美渲染"""
    limited_list = [p for p in platforms if (p.get("free_quota", {}).get("type") == "限时" or "限时" in str(p.get("tags", [])))]
    permanent_list = [p for p in platforms if (p.get("free_quota", {}).get("type") == "永久" or "永久" in str(p.get("tags", [])))]
    daily_list = [p for p in platforms if (p.get("free_quota", {}).get("type") == "每日" or "每日" in str(p.get("tags", [])))]

    html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; font-size: 15px; color: #2d3748; line-height: 1.75; letter-spacing: 0.5px; margin: 0 auto; max-width: 677px; padding: 10px;">

  <!-- 头部主标题区 -->
  <div style="text-align: center; margin-bottom: 24px;">
    <div style="display: inline-block; background: #e0f2fe; color: #0284c7; font-size: 12px; font-weight: 600; padding: 3px 12px; border-radius: 20px; margin-bottom: 8px;">
      ⚡ 免费Token情报局 · 独家汇总
    </div>
    <h1 style="font-size: 21px; font-weight: 800; color: #0f172a; line-height: 1.4; margin: 0 0 10px;">
      零成本跑通 AI！2026 全网 {len(platforms)} 家免费 API Token 额度白嫖清单
    </h1>
    <div style="font-size: 13px; color: #64748b;">
      📅 更新时间：{date.today().isoformat()} · 建议收藏备用
    </div>
  </div>

  <!-- 引言卡片 -->
  <div style="background: #f8fafc; border-left: 4px solid #38bdf8; border-radius: 0 8px 8px 0; padding: 14px 16px; margin-bottom: 24px;">
    <p style="margin: 0; color: #334155; font-size: 14px;">
      做 AI 应用、开发 Agent 或本地调试大模型，最烦的就是<strong>充值繁琐、绑定外卡门槛高</strong>。
      其实各大顶级大厂与 GPU 算力云提供了大量<strong>永久免费、每日刷新与限时大额体验额度</strong>！情报局为你全网地毯式整理，一键直达！
    </p>
  </div>

  <!-- 一、焦点速递：限时大额专区 -->
  <div style="margin-bottom: 30px;">
    <div style="display: flex; align-items: center; margin-bottom: 16px;">
      <span style="background: #f97316; width: 4px; height: 18px; border-radius: 2px; display: inline-block; margin-right: 8px;"></span>
      <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin: 0;">🔥 焦点速递：正在进行的限时大额羊毛</h2>
    </div>
"""

    for p in limited_list:
        q = p.get("free_quota", {})
        html += f"""
    <div style="border: 1px solid #fed7aa; background: #fffaf5; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; box-shadow: 0 2px 4px rgba(249,115,22,0.05);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-size: 16px; font-weight: 700; color: #9a3412;">{p['name']}</span>
        <span style="background: #ea580c; color: #ffffff; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px;">🔥 限时活动</span>
      </div>
      <div style="color: #c2410c; font-size: 14px; font-weight: 700; margin-bottom: 6px;">
        🎁 核心额度：{q.get('amount', '')} {q.get('unit', '')}
      </div>
      <p style="color: #475569; font-size: 13px; margin: 0 0 8px;">{p.get('intro', '')}</p>
      <div style="background: #ffffff; border: 1px dashed #fdba74; padding: 8px 12px; border-radius: 6px; font-size: 12px; color: #64748b;">
        📌 <strong>使用条件</strong>：{'；'.join(q.get('conditions', [])[:2])}
      </div>
    </div>
"""

    html += f"""
  </div>

  <!-- 二、永久免费与每日刷新大厂 -->
  <div style="margin-bottom: 30px;">
    <div style="display: flex; align-items: center; margin-bottom: 16px;">
      <span style="background: #0284c7; width: 4px; height: 18px; border-radius: 2px; display: inline-block; margin-right: 8px;"></span>
      <h2 style="font-size: 17px; font-weight: 700; color: #0f172a; margin: 0;">💎 核心推荐：永久免费 & 每日刷新大厂</h2>
    </div>
"""

    for p in (permanent_list + daily_list)[:8]:
        q = p.get("free_quota", {})
        tag_badge = '<span style="background:#e0f2fe;color:#0369a1;font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600;">' + (q.get('type') or '免费') + '</span>'
        html += f"""
    <div style="border: 1px solid #e2e8f0; background: #ffffff; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
        <span style="font-size: 15px; font-weight: 700; color: #1e293b;">{p['name']}</span>
        {tag_badge}
      </div>
      <div style="color: #0284c7; font-size: 13px; font-weight: 600; margin-bottom: 4px;">
        🎁 免费额度：{q.get('amount', '')} {q.get('unit', '')}
      </div>
      <p style="color: #64748b; font-size: 13px; margin: 0;">{p.get('intro', '')}</p>
    </div>
"""

    html += f"""
  </div>

  <!-- 网页一键代码与查看全部入口 -->
  <div style="background: #0f172a; color: #ffffff; border-radius: 12px; padding: 20px; text-align: center; margin: 30px 0;">
    <div style="font-size: 17px; font-weight: 700; margin-bottom: 6px; color: #38bdf8;">
      ⚡ 查看全网 {len(platforms)} 家平台详情 & 一键复制代码
    </div>
    <p style="font-size: 13px; color: #94a3b8; margin: 0 0 14px;">
      所有平台提供 Python (OpenAI SDK)、cURL、JavaScript 真实调用代码
    </p>
    <div style="display: inline-block; background: #38bdf8; color: #0f172a; font-weight: 700; font-size: 14px; padding: 8px 20px; border-radius: 8px;">
      🌐 访问在线雷达站：https://freetokens.info
    </div>
  </div>

  <!-- 底部公众号关注引导卡片 -->
  <div style="border: 2px dashed #4ade80; background: #f0fdf4; border-radius: 12px; padding: 20px; text-align: center; margin-top: 30px;">
    <h3 style="font-size: 16px; font-weight: 700; color: #166534; margin: 0 0 6px;">
      📱 关注【免费Token情报局】
    </h3>
    <p style="font-size: 13px; color: #15803d; margin: 0 0 14px;">
      全天候自动化雷达探测，第一时间为你推送突发限时免费大模型与算力羊毛！
    </p>
    <img src="/wechat-qrcode.jpg" style="width: 170px; height: 170px; border-radius: 8px; border: 1px solid #bbf7d0; display: block; margin: 0 auto 10px;" alt="关注公众号" />
    <div style="font-size: 12px; color: #16a34a;">👆 微信长按识别上方二维码关注</div>
  </div>

</div>"""
    return html


# ==========================================
# 2. 小红书 3:4 知识卡片流 (XHS Cards System)
# ==========================================
def generate_xhs_cards(platforms: list[dict]) -> str:
    """生成适合截图导出为小红书 3:4 比例的高清图文卡片 HTML 预览页"""
    cards_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>小红书爆款图文卡片流预览 (FreeToken Studio)</title>
  <style>
    body { background: #0f172a; margin: 0; padding: 40px; font-family: -apple-system, sans-serif; display: flex; flex-wrap: wrap; gap: 30px; justify-content: center; }
    .xhs-card {
      width: 375px;
      height: 500px;
      background: linear-gradient(145deg, #1e293b, #0f172a);
      border: 1px solid #334155;
      border-radius: 24px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5);
      padding: 28px;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      color: #f8fafc;
      position: relative;
      overflow: hidden;
    }
    .xhs-card::after {
      content: '';
      position: absolute;
      top: -50px; right: -50px;
      width: 150px; height: 150px;
      background: radial-gradient(circle, rgba(56,189,248,0.2), transparent 70%);
    }
    .card-tag { font-size: 12px; font-weight: 700; color: #38bdf8; text-transform: uppercase; letter-spacing: 1px; }
    .card-title { font-size: 24px; font-weight: 800; line-height: 1.3; margin: 10px 0; color: #ffffff; }
    .card-highlight { background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); padding: 14px; border-radius: 12px; margin: 12px 0; }
    .card-item { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06); padding: 10px 14px; border-radius: 10px; margin-bottom: 8px; font-size: 13px; }
    .card-footer { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #64748b; border-top: 1px solid #334155; padding-top: 14px; }
  </style>
</head>
<body>

  <!-- 卡片 1: 封面卡 (Cover Card) -->
  <div class="xhs-card" style="background: linear-gradient(135deg, #0284c7, #0f172a);">
    <div>
      <div class="card-tag">⚡ AI 开发者必备</div>
      <h1 class="card-title" style="font-size: 28px; margin-top: 20px;">2026 全球与国内<br><span style="color:#38bdf8;">29 家免费 API Token</span><br>白嫖全攻略！</h1>
      <p style="font-size: 14px; color: #cbd5e1; line-height: 1.6; margin-top: 16px;">
        告别昂贵 API 费用！涵盖 Google Gemini、阿里通义、智谱 GLM、GMI 20亿额度...零成本玩转大模型与 Agent！
      </p>
    </div>
    <div class="card-footer">
      <span>📱 免费Token情报局</span>
      <span>1/4</span>
    </div>
  </div>

  <!-- 卡片 2: 限时羊毛专区 (Limited Deals) -->
  <div class="xhs-card">
    <div>
      <div class="card-tag" style="color:#f97316;">🔥 正在进行的限时大额福利</div>
      <div class="card-title" style="font-size: 20px;">绝不能错过的限时免费</div>
      
      <div class="card-highlight" style="border-color: rgba(249,115,22,0.4); background: rgba(249,115,22,0.1);">
        <div style="font-weight:700; color:#fb923c;">🌟 GMI Cloud x MiniMax</div>
        <div style="font-size:12px; color:#fdba74; margin-top:2px;">送最高 20 亿 Tokens (M3/语音/音乐)</div>
        <div style="font-size:11px; color:#cbd5e1; margin-top:4px;">活动截止：2026.09.06 (GitHub登录即用)</div>
      </div>

      <div class="card-item">
        <strong style="color:#38bdf8;">Fireworks AI</strong>：注册送 $1 美元极速推理金
      </div>
      <div class="card-item">
        <strong style="color:#38bdf8;">Nebius AI Studio</strong>：欧洲超算云送 $5 算力代金券
      </div>
      <div class="card-item">
        <strong style="color:#38bdf8;">Novita AI</strong>：赠送 FLUX.1 文生图 API 免费测试金
      </div>
    </div>
    <div class="card-footer">
      <span>🌐 在线工具: freetokens.info</span>
      <span>2/4</span>
    </div>
  </div>

  <!-- 卡片 3: 永久免费大厂清单 (Permanent Tier) -->
  <div class="xhs-card">
    <div>
      <div class="card-tag" style="color:#4ade80;">💎 永久免费 & 每日刷新大厂</div>
      <div class="card-title" style="font-size: 20px;">长期稳定 · 零成本开发首选</div>

      <div class="card-item">
        <strong style="color:#4ade80;">Google AI Studio</strong><br>
        Gemini 1.5/2.0 Flash 永久免费 (1500次/天)
      </div>
      <div class="card-item">
        <strong style="color:#4ade80;">智谱 AI (GLM-4-Flash)</strong><br>
        国产直连 0 成本调用，速度极快适合 Agent
      </div>
      <div class="card-item">
        <strong style="color:#4ade80;">GitHub Models</strong><br>
        每日免费配额调用 GPT-4o、Claude 3.5
      </div>
      <div class="card-item">
        <strong style="color:#4ade80;">Groq & Cerebras</strong><br>
        全球最快芯片驱动，免费调用 Llama 3.3
      </div>
    </div>
    <div class="card-footer">
      <span>📱 免费Token情报局</span>
      <span>3/4</span>
    </div>
  </div>

  <!-- 卡片 4: 尾页与直达入口 (Action Card) -->
  <div class="xhs-card" style="text-align: center; justify-content: center; gap: 20px;">
    <div style="font-size: 40px;">⚡</div>
    <div style="font-size: 22px; font-weight: 800; color: #fff;">
      全部 29 家平台详情<br>& 10秒接入代码
    </div>
    <div style="font-size: 13px; color: #94a3b8; line-height: 1.8;">
      浏览器直达在线实时雷达站：<br>
      <strong style="color: #38bdf8; font-size: 15px;">👉 https://freetokens.info</strong><br>
      或关注微信公众号：<br>
      <strong style="color: #4ade80; font-size: 15px;">📱【免费Token情报局】</strong>
    </div>
    <div class="card-footer" style="position: absolute; bottom: 28px; left: 28px; right: 28px;">
      <span>收藏防走丢 💖</span>
      <span>4/4</span>
    </div>
  </div>

</body>
</html>"""
    return cards_html


# ==========================================
# 3. 矢量 SVG 架构图 (baoyu-diagram 引擎)
# ==========================================
def generate_svg_architecture() -> str:
    """生成纯手写自适应深浅色模式的系统架构矢量 SVG"""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 420" width="100%" height="100%">
  <defs>
    <style>
      .bg { fill: #0f172a; }
      .box { fill: #1e293b; stroke: #334155; stroke-width: 1.5; rx: 12; }
      .box-accent { fill: rgba(56, 189, 248, 0.1); stroke: #38bdf8; stroke-width: 1.5; rx: 12; }
      .box-orange { fill: rgba(249, 115, 22, 0.1); stroke: #f97316; stroke-width: 1.5; rx: 12; }
      .text-title { font-family: -apple-system, sans-serif; font-weight: 800; font-size: 16px; fill: #ffffff; }
      .text-sub { font-family: -apple-system, sans-serif; font-size: 12px; fill: #94a3b8; }
      .text-accent { font-family: -apple-system, sans-serif; font-weight: 700; font-size: 14px; fill: #38bdf8; }
      .arrow { stroke: #64748b; stroke-width: 1.5; stroke-dasharray: 4,4; marker-end: url(#arrowhead); }
    </style>
    <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
      <polygon points="0 0, 6 3, 0 6" fill="#64748b" />
    </marker>
  </defs>

  <rect width="100%" height="100%" class="bg" rx="16" />

  <!-- 标题 -->
  <text x="40" y="45" class="text-title" font-size="20">⚡ FreeToken 智能生态架构全景 (Architecture)</text>
  <text x="40" y="70" class="text-sub">全球免费 API 探测雷达 + 内容分发矩阵 + MaaS 聚合分发网关</text>

  <!-- 1. 雷达层 -->
  <g transform="translate(40, 100)">
    <rect width="210" height="270" class="box" />
    <text x="20" y="35" class="text-title">🛰️ 全网雷达层</text>
    <text x="20" y="55" class="text-sub">每 2 天自动扫描全球新源</text>
    <rect x="15" y="75" width="180" height="42" class="box-accent" />
    <text x="25" y="100" class="text-accent" font-size="12">开源生态 (Awesome Lists)</text>
    <rect x="15" y="125" width="180" height="42" class="box-accent" />
    <text x="25" y="150" class="text-accent" font-size="12">社区动态 (Reddit / V2EX)</text>
    <rect x="15" y="175" width="180" height="42" class="box-accent" />
    <text x="25" y="200" class="text-accent" font-size="12">DeepSeek AI 智能清洗入库</text>
  </g>

  <!-- 2. 内容与聚合站 -->
  <g transform="translate(295, 100)">
    <rect width="210" height="270" class="box-accent" />
    <text x="20" y="35" class="text-title" fill="#38bdf8">💻 核心门户与矩阵</text>
    <text x="20" y="55" class="text-sub">实时监控 29+ 精选平台</text>
    <rect x="15" y="75" width="180" height="50" class="box" />
    <text x="25" y="98" class="text-title" font-size="13">freetokens.info</text>
    <text x="25" y="115" class="text-sub">即时搜索 / 一键复制代码</text>
    <rect x="15" y="135" width="180" height="50" class="box-orange" />
    <text x="25" y="158" class="text-title" font-size="13" fill="#fb923c">📱 免费Token情报局</text>
    <text x="25" y="175" class="text-sub">微信公众号突发羊毛推送</text>
    <rect x="15" y="195" width="180" height="50" class="box" />
    <text x="25" y="218" class="text-title" font-size="13">📕 小红书知识卡片</text>
    <text x="25" y="235" class="text-sub">3:4 视觉图文矩阵传播</text>
  </g>

  <!-- 3. MaaS 聚合网关 -->
  <g transform="translate(550, 100)">
    <rect width="210" height="270" class="box" />
    <text x="20" y="35" class="text-title">🚀 终局 MaaS 网关</text>
    <text x="20" y="55" class="text-sub">One API / New API 分发</text>
    <rect x="15" y="75" width="180" height="42" class="box-accent" />
    <text x="25" y="100" class="text-accent" font-size="12">上游免费渠道池化</text>
    <rect x="15" y="125" width="180" height="42" class="box-accent" />
    <text x="25" y="150" class="text-accent" font-size="12">单 Key 畅调全系大模型</text>
    <rect x="15" y="175" width="180" height="42" class="box-accent" />
    <text x="25" y="200" class="text-accent" font-size="12">商业化充值与付费闭环</text>
  </g>
</svg>"""
    return svg


# ==========================================
# 4. 全自动化搜索引擎 SEO 引擎 (Sitemap & Robots)
# ==========================================
def generate_seo_assets(platforms: list[dict]):
    """自动生成完全符合 Google/Baidu/Bing 标准的 sitemap.xml 与 robots.txt"""
    public_dir = ROOT / "site" / "public"
    public_dir.mkdir(parents=True, exist_ok=True)

    # 1. robots.txt
    robots_content = "User-agent: *\nAllow: /\n\nSitemap: https://freetokens.info/sitemap.xml\nSitemap: https://freetokens.info/sitemap.xml\n"
    (public_dir / "robots.txt").write_text(robots_content, encoding="utf-8")

    # 2. sitemap.xml
    today = date.today().isoformat()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        '  <url>',
        '    <loc>https://freetokens.info/</loc>',
        f'    <lastmod>{today}</lastmod>',
        '    <changefreq>daily</changefreq>',
        '    <priority>1.0</priority>',
        '  </url>',
    ]

    for p in platforms:
        slug = p.get('slug')
        if slug:
            lines.extend([
                '  <url>',
                f'    <loc>https://freetokens.info/platform/{slug}/</loc>',
                f'    <lastmod>{today}</lastmod>',
                '    <changefreq>weekly</changefreq>',
                '    <priority>0.8</priority>',
                '  </url>',
            ])

    lines.append('</urlset>\n')
    sitemap_content = "\n".join(lines)
    (public_dir / "sitemap.xml").write_text(sitemap_content, encoding="utf-8")
    (OUTPUT_DIR / "sitemap.xml").write_text(sitemap_content, encoding="utf-8")


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("========================================")
    print("🎨 FreeToken Content Studio")
    print("========================================")

    platforms = load_platforms()
    if not platforms:
        return 1

    # 1. 导出微信公众号富文本排版 HTML
    wechat_html = generate_wechat_article(platforms)
    wechat_path = OUTPUT_DIR / "wechat_article.html"
    wechat_path.write_text(wechat_html, encoding="utf-8")
    print(f"✅ [WeChat Article HTML] -> {wechat_path}")

    # 2. 导出小红书 3:4 知识卡片流预览
    xhs_html = generate_xhs_cards(platforms)
    xhs_path = OUTPUT_DIR / "xhs_cards.html"
    xhs_path.write_text(xhs_html, encoding="utf-8")
    print(f"✅ [Xiaohongshu 3:4 Cards] -> {xhs_path}")

    # 3. 导出 SVG 架构图
    svg_content = generate_svg_architecture()
    svg_path = OUTPUT_DIR / "architecture.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    (ROOT / "site" / "public" / "architecture.svg").write_text(svg_content, encoding="utf-8")
    print(f"✅ [Adaptive Vector SVG Diagram] -> {svg_path}")

    # 4. 导出 SEO Sitemap 与 Robots.txt
    generate_seo_assets(platforms)
    print(f"✅ [SEO Sitemap.xml & Robots.txt] -> site/public/sitemap.xml")

    # 5. 更新前端页面为 ssgoo.net 暖色高质感风格
    update_frontend_files()

    print("\n🎉 All content and SEO assets generated successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

