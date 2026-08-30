# FreeToken 免费Token信息聚合

聚合各大 LLM / 云平台（OpenAI、Anthropic、Google AI、DeepSeek、硅基流动 SiliconFlow、阿里云百炼、Groq 等）的**免费 API 额度 / 免费层级**信息，定时自动检查并标记待人工核实，以静态网站形式呈现。

- 主站域名：`freetokens.info`（备用：`freetokenlab.com`）
- 仓库：https://github.com/kimhero110/freetoken

## 架构

```
┌──────────────────────── GitHub Actions（海外网络，每 6 小时）────────────────────────┐
│                                                                                    │
│  data/platforms/*.yaml ──► scripts/fetch_sources.py ──► .cache/hashes.json         │
│   （平台条目 & 来源URL）      （抓取来源页 + 哈希变更检测）                                │
│                                     │ 仅变更项                                       │
│                                     ▼                                               │
│                            scripts/extract.py                                       │
│                     （DeepSeek API 结构化提取 + SEO 文案）                             │
│                                     │                                               │
│                                     ▼                                               │
│                            scripts/build_data.py ──► site/src/data/platforms.json   │
│                                                             │                        │
│                                                             ▼                        │
│                                              site/ （Astro 构建）──► site/dist/      │
└───────────────────────────────────────────────────────┬─────────────────────────────┘
                                                        │ push
                          ┌─────────────────────────────▼───────────┐
                          │  GitHub 仓库                             │
                          │   main 分支：数据 + 代码（回写）           │
                          │   deploy 分支：纯静态构建产物（dist）      │
                          └─────────────────────────────┬───────────┘
                                                        │ cron git pull（每 10 分钟）
                          ┌─────────────────────────────▼───────────┐
                          │  腾讯云境内服务器（2C/2G/40G）             │
                          │   Nginx 托管 /var/www/freetoken           │
                          └─────────────────────────────────────────┘
```

## 快速开始

### 1. 推送本骨架到仓库

```bash
git clone https://github.com/kimhero110/freetoken.git
# 将本项目所有文件拷入仓库目录后提交推送
git add -A && git commit -m "init: 项目骨架" && git push origin main
```

### 2. 配置 GitHub

1. 仓库 **Settings → Secrets and variables → Actions → New repository secret**，添加以下 API Key 中的**至少一个**（支持多模型自动降级 Fallback）：
   - `DEEPSEEK_API_KEY`：DeepSeek 开放平台（platform.deepseek.com）API Key（CI 任务已自动对齐在每日 00:30~08:30 官方 5 折优惠波谷期运行）
   - `SILICONFLOW_API_KEY`（可选）：硅基流动 API Key
   - `MOONSHOT_API_KEY`（可选）：Kimi / Moonshot 开放平台 API Key
   - `DASHSCOPE_API_KEY`（可选）：阿里百炼 DashScope API Key
   - `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`（可选）：任何自定义 OpenAI 兼容接口
2. **Settings → Actions → General → Workflow permissions**，勾选 *Read and write permissions*（回写分支需要）
3. 在 **Actions** 页面启用 workflow，可手动触发一次验证

### 3. 首次生成 package-lock.json

workflow 使用 `npm ci`，需要先提交一次 lockfile：

```bash
cd site
npm install        # 生成 package-lock.json
git add package-lock.json && git commit -m "chore: lockfile" && git push
```

### 4. 腾讯云服务器部署（Nginx）

```bash
# 安装 Nginx 后，参考 deploy/nginx.conf.example 创建站点配置
sudo cp deploy/nginx.conf.example /etc/nginx/conf.d/freetoken.conf
# 修改 server_name 为你的已备案域名，然后重载
sudo nginx -t && sudo systemctl reload nginx

# 首次克隆 deploy 分支（需等 GitHub Actions 首次构建推送后）
sudo git clone --branch deploy --single-branch \
  https://github.com/kimhero110/freetoken.git /var/www/freetoken

# 配置定时拉取
sudo cp deploy/pull.sh /opt/freetoken/pull.sh && sudo chmod +x /opt/freetoken/pull.sh
# crontab -e 添加：
# */10 * * * * /opt/freetoken/pull.sh >> /var/log/freetoken-pull.log 2>&1
```

> 若服务器拉取私有仓库，请配置 Deploy Key 或改用 HTTPS token。

### 5. ICP 备案提醒

- 境内服务器通过 80/443 端口对外提供**域名访问**前，必须完成 ICP 备案；
- 备案完成后记得在 `site/src/layouts/Base.astro` 页脚添加备案号；
- HTTPS 证书（Let's Encrypt / certbot）建议在备案通过后配置，示例见 `deploy/nginx.conf.example` 注释段。

## 本地开发

```bash
# 数据流水线
pip install -r scripts/requirements.txt
python scripts/fetch_sources.py
python scripts/extract.py --dry-run     # 无 API Key 时可先干跑
python scripts/build_data.py

# 站点预览
cd site && npm install && npm run dev
```

## 添加新平台

在 `data/platforms/` 下新建 `<slug>.yaml`（参考现有 3 个示例），填写 `source_urls` 后提交即可，下一轮定时任务会自动抓取、提取并上线页面。

## 目录说明

```
data/platforms/      平台条目 YAML（人工维护 + AI 提取回写）
scripts/             抓取 / 提取 / 数据合并脚本（Python 3.11）
site/                Astro 静态站点源码
deploy/              服务器端 Nginx 配置示例与拉取脚本
.github/workflows/   定时更新与构建 workflow
.cache/              抓取哈希缓存（CI 回写，勿手工编辑）
```
