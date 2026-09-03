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

## 数据更新流程

1. `python scripts/fetch_sources.py` 检测来源变化。
2. 配置 LLM 环境变量后运行 `python scripts/extract.py`。
3. 提取结果写入 `data/candidates/`，不会修改正式数据。
4. 使用 `python scripts/review_candidates.py --list` 查看候选。
5. 核对来源和差异后，运行 `python scripts/review_candidates.py --approve <candidate-id>`。
6. 审批命令会更新正式数据并执行数据编译与站点构建；失败时回滚修改并保留候选。
7. 将审核后的改动通过 PR 合并到 `main`，发布工作流会测试并部署同一个构建产物。

首次启用发布前，仓库管理员必须在 GitHub 的 `production` Environment 中配置 required reviewers，并将允许部署的分支限制为 `main`。工作流本身也拒绝从 PR、标签或其他分支部署，并会等待 Cloudflare Pages 检查成功后才报告发布完成。

拒绝候选：

```bash
python scripts/review_candidates.py --reject <candidate-id>
```

### 能力探测与审核

仓库管理员可在 GitHub Actions 的 **Capability probe candidates** 工作流中手动选择一个固定提供商和 `raw_http`、`openai_python`、`openai_node` 客户端，也可选择 `all`。工作流每周二 `03:17 UTC` 自动运行，并在 Job Summary 报告固定十项允许列表的 Secret 覆盖率；缺少凭据的项会明确列为跳过且不生成失败候选。每个 provider/tool 组合只发送一次可能计费的 API POST，SDK 自动重试被禁用，请在启用 Secret 前确认额度和成本。

探测只写入 `data/candidates/`，不会直接修改正式平台数据。每个候选只证明并提升一个工具，不能用 HTTP 探测替代 SDK 证明。人工核对候选后，在 `main` 分支运行 **Review candidate**，填写候选文件名（不含扩展名）并选择 `approve` 或 `reject`。批准成功的 live 探测会更新正式 YAML、重新编译并构建；Git 推送成功后，工作流才在单独的 Secret-bearing 步骤发送飞书通知。拒绝或已批准的候选都会带上 `github.actor` 审核记录并移入 `data/reviews/`。

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
部署账号应为受限的非 root 用户，并仅获得发布目录和受控容器重建权限。容器必须通过 Compose 重建，而不是仅重启；Docker 的目录绑定不会在普通重启时切换到新目录 inode。每次发布会读取 `release-id.txt`，确认容器实际提供的是本次构建后才删除回滚副本。

GitHub 的 `production` Environment 需要配置 `TENCENT_SSH_PRIVATE_KEY`、`TENCENT_KNOWN_HOSTS` 和 `TENCENT_DEPLOY_HOST`。服务器仅允许部署账号免密执行 root 拥有的 `/usr/local/sbin/deploy-freetoken`，该脚本会校验归档成员、串行化发布并在健康检查失败时回滚。

## 贡献新平台

1. 使用[新平台 Issue 模板](https://github.com/kimhero110/freetoken/issues/new?template=submit_platform.yml)提交官方来源。
2. 或在 `data/candidates/` 提交候选 YAML。
3. 正式平台数据必须通过 `python -m unittest discover -s tests -v`。

## License

[MIT](LICENSE)
