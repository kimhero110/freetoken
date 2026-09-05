# FreeToken · 免费 Token 情报局

> 用免费 Token 做工具，也提醒自己保持思考。

[![Website](https://img.shields.io/badge/Website-freetokens.info-18181b.svg?style=flat-square)](https://freetokens.info)
[![GitHub Stars](https://img.shields.io/github/stars/kimhero110/freetoken?style=flat-square&color=18181b)](https://github.com/kimhero110/freetoken)
[![License](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)

FreeToken 收录全球大模型和开发者平台的免费额度、官方入口、核验来源与接入方式。当前收录 44 个平台。自动抓取与 LLM 提取只生成候选变更，正式数据必须经过人工批准。

## 核心原则

- 不把网页或 LLM 输出直接当作可信事实。
- 未知的手机、绑卡、地区和限流条件明确显示为“未核实”。
- 只有已标记为 OpenAI 兼容的平台才生成 Chat Completions 示例。
- 每条正式平台数据必须通过 Schema 校验并包含核验来源。
- 构建产物通过独立发布工作流部署，候选数据不会触发生产发布。

## 架构

```text
data/platforms/*.yaml
        |
        v
fetch_sources.py -> extract.py -> data/candidates/*.yaml
                                      |
                                人工审核批准
                                      |
                                      v
                              正式平台 YAML
                                      |
                    compile_data.py + tests + Astro build
                                      |
                                      v
                               deploy 分支
```

## 本地开发

环境要求：Node.js 22、Python 3.11。

```bash
git clone https://github.com/kimhero110/freetoken.git
cd freetoken

python -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r scripts/requirements.lock

python -m unittest discover -s tests -v
python scripts/compile_data.py

cd site
npm ci
npm test
npm run dev
```

Windows PowerShell 激活虚拟环境时使用：

```powershell
.venv\Scripts\Activate.ps1
```

飞书入口集成测试使用真实锁定版本的 SDK 和本地 mock，不发送消息或触发 Actions。daemon 与数据脚本的 requests 版本不同，请用独立环境运行（发布工作流的 build 门禁也执行此检查）：

```bash
python -m venv .venv-daemon
.venv-daemon/bin/python -m pip install -r daemon/requirements.txt
.venv-daemon/bin/python -m unittest discover -s tests/daemon_integration -v
```

Windows 将以上 `.venv-daemon/bin/python` 替换为 `.venv-daemon\Scripts\python.exe`。

## 数据更新流程

1. `python scripts/fetch_sources.py` 检测来源变化。
2. 配置 LLM 环境变量后运行 `python scripts/extract.py`。
3. 提取结果写入 `data/candidates/`，不会修改正式数据。
4. 使用 `python scripts/review_candidates.py --list` 查看候选。
5. 核对来源和差异后，运行 `python scripts/review_candidates.py --approve <candidate-id>`。
6. 审批命令会更新正式数据并执行数据编译与站点构建；失败时回滚修改并保留候选。
7. 将审核后的改动通过 PR 合并到 `main`，发布工作流会测试并部署同一个构建产物。

首次启用发布前，仓库管理员必须在 GitHub 的 `production` Environment 中配置 required reviewers，并将允许部署的分支限制为 `main`。工作流本身也拒绝从 PR、标签或其他分支部署，并会等待 Cloudflare Pages 检查成功后才报告发布完成。`main` 分支由 repository ruleset 完整保护：禁止 force push 与分支删除，且所有变更（包括自动化数据提交）必须通过 PR 并通过 `build` 状态检查。自动化写入使用专属 GitHub App `freetoken-bot`（每次运行铸造短时效令牌，凭据仅存于 `APP_ID`/`APP_PRIVATE_KEY` Secrets），以 `auto/*` 分支 + PR 自动合并方式进入 `main`——GITHUB_TOKEN 直推已被彻底移除。

拒绝候选：

```bash
python scripts/review_candidates.py --reject <candidate-id>
```

### 能力探测与审核

仓库管理员可在 GitHub Actions 的 **Capability probe candidates** 工作流中手动选择一个固定提供商和 `raw_http`、`openai_python`、`openai_node` 客户端，也可选择 `all`。工作流每周二 `03:17 UTC` 自动运行，并在 Job Summary 报告固定十项允许列表的 Secret 覆盖率；缺少凭据的项会明确列为跳过且不生成失败候选。每个 provider/tool 组合只发送一次可能计费的 API POST，SDK 自动重试被禁用，请在启用 Secret 前确认额度和成本。

探测只写入 `data/candidates/`，不会直接修改正式平台数据。每个候选只证明并提升一个工具，不能用 HTTP 探测替代 SDK 证明。人工核对候选后，在 `main` 分支运行 **Review candidate**，填写候选文件名（不含扩展名）并选择 `approve` 或 `reject`。批准成功的 live 探测会更新正式 YAML、连同已审核来源哈希（`.cache/hashes.json`）一并重新编译并提交；推送成功后工作流自动触发 `publish.yml` 生产发布，只有双节点公网 `release-id.txt` 核验通过后才会发送飞书上线通知（审批阶段的通知只声明“发布已触发”）。拒绝候选同样会归档审核记录，并记录该来源版本已审，避免同一来源反复入队；已批准与已拒绝的候选都会带上 `github.actor` 审核记录并移入 `data/reviews/`。

能力状态含义：`claimed` 表示平台声称支持但尚无已核验证据；`documented` 表示官方文档已核验；`live` 表示一次真实 API 请求成功且协议响应有效。定时探测结果在人工批准前始终只是候选，不改变这些正式状态。

## 配置与密钥

密钥只能通过环境变量或 GitHub Secrets 提供。仓库不包含 Webhook、API Key 或 SSH 私钥的默认值。

主要变量：

- `DEEPSEEK_API_KEY`
- `SILICONFLOW_API_KEY`
- `MOONSHOT_KIMI_API_KEY`（能力探测；额度提取仍使用 `MOONSHOT_API_KEY`）
- `ALIYUN_BAILIAN_API_KEY`（能力探测；额度提取仍使用 `DASHSCOPE_API_KEY`）
- `GOOGLE_AI_STUDIO_API_KEY`
- `GROQ_API_KEY`
- `VOLCENGINE_API_KEY`
- `ZHIPU_AI_API_KEY`
- `OPENROUTER_API_KEY`
- `GMI_CLOUD_MINIMAX_API_KEY`
- `FEISHU_WEBHOOK_URL`
- `FEISHU_SECRET`

腾讯云部署还需要：

- `FREETOKEN_SSH_KEY`
- `FREETOKEN_KNOWN_HOSTS`
- `FREETOKEN_DEPLOY_HOST`
- `FREETOKEN_DEPLOY_USER`
部署账号应为受限的非 root 用户，并仅获得发布目录和受控容器重建权限。容器必须通过 Compose 重建，而不是仅重启；Docker 的目录绑定不会在普通重启时切换到新目录 inode。部署归档在 root 解压前强制限制：压缩包 ≤256MB、成员数 ≤30000、单文件 ≤64MB、解压总量 ≤1GB。每次发布通过公网核验 `release-id.txt` 与本次构建一致后才宣告成功；服务器保留最新两个回滚快照，更早的历史发布自动清理。

GitHub 的 `production` Environment 需要配置 `TENCENT_SSH_PRIVATE_KEY`、`TENCENT_KNOWN_HOSTS` 和 `TENCENT_DEPLOY_HOST`。服务器仅允许部署账号免密执行 root 拥有的 `/usr/local/sbin/deploy-freetoken`，该脚本会校验归档成员与资源上限、串行化发布并在健康检查失败时回滚。

依赖供应链由 Dependabot 每周跟踪 GitHub Actions 与 npm 依赖（`/site` 与 `/scripts/node`）；Python 依赖保持 hash 锁定并人工审核升级。

## 飞书智能入口机器人（Intake Bot）

私聊飞书自建应用即可完成线索入库、文章改写与候选审批。守护进程只做"入口路由"（身份白名单 + 命令解析 + 状态票据），重逻辑全部在 GitHub Actions 内执行，正式数据仍走 候选 → 门禁 PR → 人工决策 → 验证发布 的既有链路。

### 命令手册

| 命令 | 作用 |
|---|---|
| `平台 <url> [备注]` | 安全抓取 → LLM 提取 → Schema 校验 → 查重 → 新候选 PR（门禁自动合并）；平台已存在时生成更新候选或备注候选 |
| `文章 <url> [备注]` | 改写为本站文章**草稿 PR（永不自动合并）**，强制 `source_url` 来源标注；加 `参数:提纲` 仅生成提纲；输出截断自动降级提纲 |
| `通过 / 拒绝 <#p短号 或 完整ID>` | 触发 Review candidate 审批（先回 6 位确认码防误触；票据绑定 run，门禁由 PAT 代批并全程审计） |
| `确认 <6位码>` | 完成审批确认（5 分钟有效，错 3 次锁 30 分钟） |
| `待审` | 列出全部候选（短号 + 平台名） |
| `状态` | 运行中管线、PAT 自检、版本 commit 与运行时长 |
| `撤销` | 说明最新票据与"拒绝后重发"路径 |
| `帮助` / `谁我` | 手册卡片 / 返回自己的 open_id |
| （裸 HTTPS 链接） | 歧义卡：回复 `平台` 或 `文章` |

审批安全模型（A+）：daemon 持**仅限本仓库、仅 Actions 读写**的 fine-grained PAT（90 天过期、每周自检、提前 30 天告警）；代码内只批准"本票据自己 dispatch 的 run"；确认码防误触（不防会话劫持——由仅偏差触发的异常卡与日报"昨日自动批准"计数兜底）；权威审计身份永远是 `github.actor`，飞书身份只作标注。已声明的残余风险：服务器完全沦陷可绕过（单操作者接受）。

运行关联使用唯一 ticket_id、候选/决定、PAT 操作者、main 提交 SHA 和工作流路径；生产发布只关联该审核运行对应 PR 的合并 SHA 和合并者。等待 Environment 的 `waiting` 状态可直接被发现，非 production 门禁或多个匹配运行不会自动批准。关联所需的提交与 PR 信息读取自本公开仓库，不增加 PAT 写权限。若 dispatch 前后的 main 恰好变化，关联会保守失败，需要重新发起命令。

升级时先让新版工作流进入 main，再重建 daemon；旧票据没有新的关联字段，不会自动批准，请重新发起。日报和看门狗通知使用 OWNER_OPEN_ID 主动发送，不需要填写聊天 ID。

### 快速开始（部署后 30 分钟内完成首条命令）

1. [开放平台](https://open.feishu.cn/) 创建**企业自建应用**：添加"机器人"能力；权限勾选 `im:message`（获取与发送单聊消息）；事件订阅选择**长连接**模式，订阅 `im.message.receive_v1`；发布版本并可用范围=自己。
2. 创建 fine-grained PAT：GitHub → Settings → Developer settings → Fine-grained tokens → 仅 `kimhero110/freetoken`，权限仅 `Actions: Read and write`，有效期 90 天。
3. 服务器：`git clone` 本仓库到 `/opt/freetoken-intake`；`cp daemon/env.example /opt/freetoken-intake/.env` 并填入 `FEISHU_APP_ID/FEISHU_APP_SECRET/GITHUB_PAT/GITHUB_REPO`，`BOOTSTRAP=1` 保持开启，`chmod 600 .env`。
4. 启动：`cd /opt/freetoken-intake && GIT_COMMIT=$(git rev-parse --short HEAD) docker compose -f deploy/docker-compose.feishu-intake.yml up -d --build`。
5. 引导：飞书私聊发 `谁我` → 机器人回你的 open_id → 填入 `.env` 的 `OWNER_OPEN_ID`，去掉 `BOOTSTRAP=1` → `docker compose -f deploy/docker-compose.feishu-intake.yml up -d --force-recreate feishu-intake`。
6. 验证：发 `状态`，应在 10 秒内收到卡片（无响应=长连接未建立，查容器日志与事件订阅配置）。
7. 首条真实命令：发 `待审`（空列表卡片）→ 再发 `平台 <任一已收录平台URL>` 应返回"已在库"。
8. 记录实际 TTHW 到本节（boomerang：上线后跑 /devex-review 复测）。

### 运维手册

- **PAT 轮换**（每 90 天，状态卡会提前 30 天告警）：建新 PAT → 更新 `/opt/freetoken-intake/.env` → `docker compose -f deploy/docker-compose.feishu-intake.yml up -d --force-recreate feishu-intake` → 发 `状态` 验证。
- **升级 daemon**：`cd /opt/freetoken-intake && git pull && GIT_COMMIT=$(git rev-parse --short HEAD) docker compose -f deploy/docker-compose.feishu-intake.yml up -d --build`；`状态` 卡显示新 commit 即生效。
- **日志**：`docker logs -f freetoken-feishu-intake`；票据全生命周期在容器卷 `/data/journal.jsonl`。
- **宕机语义**：断线期间的命令不会补跑（重连卡有提示）；外部看门狗 = GitHub Actions 定时探测健康端点并发告警卡。
- **看门狗**：dispatch 后 30 分钟未获批准的 run 自动取消并告警（防止并发组被毒化）。
- **回滚**：`docker compose -f deploy/docker-compose.feishu-intake.yml down` 即完全回到无机器人现状；GitHub 侧审批流始终可独立使用（并行通道）。

### 相关密钥

- GitHub Actions Secrets：`APP_ID`/`APP_PRIVATE_KEY`（既有）、`DEEPSEEK_API_KEY`（提取/改写）
- 服务器 `/opt/freetoken-intake/.env`（0600）：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`OWNER_OPEN_ID`、`GITHUB_PAT`、`GITHUB_REPO`

## 贡献新平台

1. 使用[新平台 Issue 模板](https://github.com/kimhero110/freetoken/issues/new?template=submit_platform.yml)提交官方来源。
2. 或在 `data/candidates/` 提交候选 YAML。
3. 正式平台数据必须通过 `python -m unittest discover -s tests -v`。

## License

[MIT](LICENSE)

## 成本预算工具

主站 `/cost/` 和 `/en/cost/` 提供本地月预算估算，支持缓存、峰谷价格、明确适用的免费余额和自填汇率。价格独立维护在 `data/pricing/pricebook.json`，经代码审查更新。数据规则、验证命令及评测站后续接入见 [成本计算器 V1](docs/cost-calculator-v1.md)。

## Live integration check

Send `selftest` (or the Chinese integration-check command) to the configured bot, then reply with the confirmation code shown on its card. This dispatches `feishu-self-test.yml` and exercises the existing `production` approval gate without changing or deploying site content. An empty, absent candidates directory is treated as an empty queue only after its parent is verified readable.

Environment-file edits require container recreation; a Docker restart does not reload env_file. Validate the owner ID using the bot bootstrap command before disabling BOOTSTRAP. See [live integration record](docs/feishu-live-integration.md).
