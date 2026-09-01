# FreeToken · 免费 Token 情报局

> **用免费 Token 做工具，也提醒自己保持思考。**

[![Website](https://img.shields.io/badge/Website-freetokens.info-18181b.svg?style=flat-square)](https://freetokens.info)
[![GitHub Stars](https://img.shields.io/github/stars/kimhero110/freetoken?style=flat-square&color=18181b)](https://github.com/kimhero110/freetoken)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Platforms](https://img.shields.io/badge/Monitored_Platforms-29+-green.svg?style=flat-square)](https://freetokens.info/#products)

聚合全球主流大模型（LLM）与云平台（Google Gemini、DeepSeek、硅基流动 SiliconFlow、Groq、阿里百炼、智谱 AI、Cerebras 等）的**免费 API 额度与白嫖配额**。全天候自动化探测雷达巡检，提供透明规则、风控避坑提示与 **10 秒开箱即用代码**。

---

## 🧭 四个长期坐标

* **01 AI 引导未来 (INTELLIGENCE COMPASS)**：研究模型、思维与协作范式，在技术狂潮中保持敏锐的独立判断力与人机共生边界。
* **02 Token 就是能源 (TOKEN AS ENERGY)**：算力的流动即是价值的流动。掌握充沛且低成本的 Token，就是掌握数字工厂的能源自主权。
* **03 世界代码化 (CODIFIED REALITY)**：把研究框架、业务逻辑与工作流沉淀为代码，用自动化与接口化杠杆放大个体的生产力半径。
* **04 工具开源化 (OPEN-SOURCE TOOLS)**：拥抱开放权重、开源协议与公共基础设施，让技术的主权与自由永远留在构建者手里。

---

## ⚡ 核心功能与特性

1. **29+ 主流平台全量收录**：覆盖 Google Gemini（每日 1500 次）、硅基流动（赠送 2000 万 Tokens）、Groq（300+ T/s 极速推理）、DeepSeek、智谱 GLM、GMI Cloud（限时 20 亿）等；
2. **实时雷达监控**：秒级动态倒计时巡检，展示最新核验时间与可用状态；
3. **真实 OpenAI 兼容端点**：每个平台详情页提供其真实的官方专属 Base URL、免费模型代号与 Python / cURL / JavaScript 10 秒接入代码；
4. **工具实践直达**：原生适配 **OpenCode Interpreter**、**Cherry Studio**、**Chatbox**、**Cline**、**Cursor** 及 **One API / New API** 聚合路由；
5. **极速轻量架构**：基于 Astro 极简主义科技杂志排版，全站 WebP 艺术画资产，毫秒级秒开，全量托管于 **Cloudflare Anycast 全球边缘网络**。

---

## 🏗️ 系统架构

`
┌──────────────────────── 全天候自动化探测与内容流水线 ────────────────────────┐
│                                                                                │
│  data/platforms/*.yaml ──► scripts/fetch_sources.py ──► .cache/hashes.json     │
│   （29+ 平台与来源 URL）      （抓取来源页 + 哈希变更检测）                            │
│                                     │ 仅变更项                                   │
│                                     ▼                                           │
│                            scripts/extract.py                                   │
│                     （LLM 结构化提取 + 校验规则提炼）                             │
│                                     │                                           │
│                                     ▼                                           │
│                            scripts/generate_content.py                          │
│                     （生成公众号/小红书/SVG/Sitemap/Astro 数据）                  │
│                                     │                                           │
│                                     ▼                                           │
│                            site/ （Astro 静态编译）──► site/dist/                │
└───────────────────────────────────────────────────┬────────────────────────────┘
                                                    │ push / deploy
                      ┌─────────────────────────────▼───────────────────────────┐
                      │  全球 CDN 边缘分发                                       │
                      │   - GitHub Pages / deploy 分支                           │
                      │   - Cloudflare Pages 全球 Anycast 边缘网络 (reetokens.info) │
                      └─────────────────────────────────────────────────────────┘
`

---

## 🛠️ 如何在常用 AI 工具中接入本站资源？

本站收录的大模型平台绝大多数均**原生兼容 OpenAI 标准接口协议**。无论在何种工具或项目中使用，只需要配置以下 **3 个参数**：

| 参数名称 | 说明 | 示例 |
| :--- | :--- | :--- |
| **Base URL** | 详情页中提供的平台专属接口基础地址 | https://api.siliconflow.cn/v1 |
| **API Key** | 在平台注册并创建的密钥凭证 | sk-xxxxxx |
| **Model Name** | 平台支持的免费模型代号 | Qwen/Qwen2.5-7B-Instruct |

### 1. OpenCode / Cursor / Cline (AI 编程与终端自动化)
在客户端设置 ➔ **Custom OpenAI Provider** 中，填入对应平台的 Base URL 与 API Key，即可零成本驱动终端代码编写与自动化重构。

### 2. Cherry Studio / Chatbox / NextChat (多端对话客户端)
在设置 ➔ **自定义服务商** 中，填入对应平台的 API 地址与 Key，选择免费模型即可秒级开聊。

### 3. One API / New API (聚合网关与负载均衡)
强烈建议将本站 29 家平台的免费 Key 统一挂载至聚合网关，开启多渠道负载均衡与自动轮询，实现无上限并发调用。

---

## 💻 本地开发与构建

### 环境要求
- Node.js >= 18
- Python >= 3.10

### 1. 克隆项目
`ash
git clone https://github.com/kimhero110/freetoken.git
cd freetoken
`

### 2. 运行数据与内容流水线
`ash
# 安装 Python 依赖
pip install -r scripts/requirements.txt

# 生成最新数据、SEO 资产与 Astro 模板
python scripts/generate_content.py
`

### 3. 本地启动前端预览
`ash
cd site
npm install
npm run dev
# 打开浏览器访问 http://localhost:4321
`

### 4. 生产编译
`ash
npm run build
# 产物输出至 site/dist
`

---

## 🤝 贡献与推荐新免费源

如果你发现了新的大模型免费额度、限时赠送活动或算力平台，欢迎为社区添砖加瓦：

1. **提交 Issue**：直接使用 [推荐新免费平台 Issue 模板](https://github.com/kimhero110/freetoken/issues/new?template=submit_platform.yml) 提交；
2. **提交 Pull Request**：
   - 在 data/platforms/ 下新建 <slug>.yaml；
   - 填写平台名称、官网、pi_base_url、ree_quota 及验证来源 source_urls；
   - 运行 python scripts/generate_content.py 编译验证；
   - 发起 PR，自动化 CI 会自动进行核验与合并。

---

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 开源。
