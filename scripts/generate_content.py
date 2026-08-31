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
      🌐 访问在线雷达站：https://witkit.zone
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
      <span>🌐 在线工具: witkit.zone</span>
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
      <strong style="color: #38bdf8; font-size: 15px;">👉 https://witkit.zone</strong><br>
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
    <text x="25" y="98" class="text-title" font-size="13">witkit.zone</text>
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

    print("\n🎉 All content assets generated into output/ directory successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

