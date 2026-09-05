# FreeToken 代码审查

审查日期：2026-09-05。版本：`558b386f19efe7971457983ce2359bf4e0b925fb`。

修复状态：下文保留原始审查证据；F1–F6 已随本次变更修复，生产部署状态以发布流水线为准。回归测试包含真实 SDK 消息解析、精确运行关联、waiting 状态、平台参数契约、更新候选生成到批准归档以及主动通知接收者。运行方式见 README，具体用例位于 `tests/daemon_integration/test_intake.py`、`tests/test_platform_tip.py` 和 `tests/test_workflow_contracts.py`。旧 `review_repro.py` 针对原始版本，修复后请使用回归测试验证。

原始审查发现飞书入口、平台提交和自动审批存在阻断问题；下文为原始证据，当前修复已通过回归测试。

## 范围与方法

用户授权审查公开仓库。本次下载源码、检查本地代码与工作流、运行已有测试，并使用本地 mock 复现；未登录生产系统、调用真实模型、发送飞书消息或触发 GitHub 审批与部署。未核实线上 Environment、PAT 权限、服务器配置和免费额度事实。

这个机器人相当于“线索接待员兼发布审批员”：接收飞书命令，触发 Actions，让 LLM 生成候选，最终用 PAT 批准 production 门禁。最重要的边界是操作者确认的候选必须与随后批准的运行严格对应。

方法参考本地 aig-agent-redteam 技能及其关联项目 [tencent/AI-Infra-Guard](https://github.com/tencent/AI-Infra-Guard)。本次未使用 AIG 漏洞数据库、指纹数据或攻击样本，不声称任何规则命中。模型对话攻击不在范围内：发送 payload 0、数据集样本 0、变异样本 0、手工对话 payload 0、算子 0、动态对话场景 0；30 条覆盖要求不适用，本报告不提供模型注入抵抗力结论。

## 发现

### F1 · P1：读取错误的 SDK 身份字段，所有正常文本消息被丢弃

位置：`daemon/feishu_client.py:72`。

锁定版本 lark-oapi 1.7.3 的 EventSender 只有 `sender_id`，open_id 位于 `sender.sender_id.open_id`。代码访问 `sender.open_id`，随后由 `except AttributeError` 返回 None，导致 `Bot.on_event` 在命令解析前退出，连引导命令“谁我”也不可用。

证据：使用实际安装的 SDK 创建合法 `P2ImMessageReceiveV1`，正确路径读取 `ou_owner`，同一对象交给 `extract_message` 返回 `None`。对照 [SDK 源码](https://raw.githubusercontent.com/larksuite/oapi-sdk-python/v1.7.3/lark_oapi/api/im/v1/model/event_sender.py)。

修复：读取嵌套 sender_id，并对缺失身份单独处理。复测必须用真实 SDK 反序列化事件，验证 owner、陌生人和 bootstrap 三条消息路径，不能只测试 auth 函数。

### F2 · P1：审批仅按时间选择运行，可能批准其他候选或无关发布

位置：`daemon/main.py:370`，以及 `daemon/main.py:420`。

`_await_gate` 将时间窗口内第一个 queued/in_progress 运行直接写入票据；没有候选 ID、唯一 dispatch 标识、actor 或 ref 的关联校验。`_approve_gate` 随后直接批准该运行的首个 environment。`_find_publish_run` 同样选票据创建后任意 push 运行，未核对已审核 PR 的 merge SHA。因此在并发提交或人工触发其他运行时，确认候选 A 可能变成批准 B，或放行无关发布。F1 当前阻断正常入口，但修复入口后这个独立缺陷仍然存在。

证据：本地 mock 返回只有无关运行 999 的列表，`_await_gate` 返回 999，并把它绑定到候选 A 的票据。没有发送真实批准请求。

修复：将唯一 ticket_id 传给审核工作流并纳入可核验 run-name，严格校验 workflow/ref/event/actor 与关联标识；将发布绑定到审核 PR 的 merge SHA，并校验 environment。找不到唯一匹配时停止批准。复测同时放入 A、B 两个运行并调换顺序，确保绝不选择 B。

### F3 · P1：平台提交总是携带工作流未声明的 mode 输入

位置：`daemon/main.py:186–188`；对照 `.github/workflows/feishu-platform-tip.yml:5–18`。

`cmd_submit` 对平台和文章都传入 mode，但平台工作流只接受 url、note、ticket_id。GitHub dispatch 的输入契约不匹配，平台命令会在触发阶段失败，候选提取无法开始。这在修复 F1 后仍会阻断平台入口。

证据：调用真实 cmd_submit 方法并 mock GitHub 客户端，比较捕获的 inputs 与 YAML 声明，额外字段恰为 `['mode']`。未向 GitHub 发送请求，因此未实测线上 422 响应。

修复：只为文章工作流传入 mode，或有意扩充平台输入契约。增加同时检查调用方和 YAML 的契约测试；现有测试只检查 YAML 中字段存在，捕捉不到多传参数。

### F4 · P1：待批准的 waiting 运行被门禁发现逻辑排除

位置：`daemon/main.py:370`。

`_await_gate` 只接受 queued/in_progress。审核工作流唯一 job 在执行前就进入 production Environment 门禁，第一次轮询时运行可能已经处于 waiting；此后持续被忽略，十分钟后超时，永远不会调用 `_approve_gate`。GitHub API 明确定义了 waiting 状态，参见 [运行状态文档](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository)。

证据：本地 mock 返回时间有效、status=waiting 的运行，加速时钟至超时，结果为 None。

修复：在 F2 的唯一关联校验基础上接纳 waiting/requested/pending 等合法非终态，并查询 pending_deployments；不要依赖捕捉瞬时 queued 状态。复测第一次查询已经 waiting 的运行。

### F5 · P2：已有平台的更新候选缺字段，审核器必定拒绝

位置：`scripts/platform_tip.py:165–172`；对照 `scripts/review_candidates.py:175–202`。

提交已有平台的授权来源时，生成器标记 candidate_type=platform_update，但只写平台 ID、来源、备注和时间。审核器要求 source_hash、proposed、current 等数据，生成器全部未提供。因此该路径显示入库成功后，批准一定失败，无法完成 README 承诺的更新流程。

证据：mock 安全抓取和已有平台匹配，调用实际 main 生成 YAML，再交给 `_apply_update_candidate`，得到 `ValueError: 更新候选来源哈希无效`，且尚未进入网络请求或正式数据写入。

修复：复用既有更新候选生成逻辑，保存来源哈希、当前数据快照和提取后的 proposed；纯备注使用明确的非更新类型及对应审核路径。增加“生成候选→审核”的贯通测试。

### F6 · P2：主动发卡把 chat_id 当作 message_id，日报无法投递

位置：`daemon/feishu_client.py:36–40`；日报调用为 `daemon/main.py:473`。

没有 reply_to 时，send_card 仍调用 reply API，并将 chat_id 填入 message_id。SDK 的实际路径为 `/open-apis/im/v1/messages/:message_id/reply`，聊天 ID 不是消息 ID。日报更使用固定占位值 oc_owner，而不是已保存的 owner 会话。这使主动通知和日报无法正确投递，API 失败只被记录日志并返回空串。

证据：检查锁定 SDK 的 ReplyMessageRequestBuilder，确认其 URI 和 paths 参数；调用链明确传入 oc_owner。本次未调用真实飞书 API，未观测线上错误码。

修复：回复走 reply，主动发送走 CreateMessageRequest 并设置 receive_id_type；保存真实 owner chat_id，或使用 owner open_id 作为接收者。复测请求类型、接收者字段以及发送失败后的处理。

## 验证与正面证据

| 检查 | 结果 | 含义及边界 |
|---|---|---|
| Python 单元测试 | 137 项通过 | 使用仓库 hash 锁定脚本依赖；日志见 review-tests.log |
| Node 单元测试 | 13 项通过 | Markdown 协议过滤、HTML 转义和代码生成保护通过 |
| Astro 构建 | 成功 | 本地 Python 3.12、Node 24，与 CI Python 3.11、Node 22 不同；未验证 CI 环境 |
| 无关运行关联 | 本地复现失败边界 | 返回运行 999；见 review_repro.py |
| waiting 运行发现 | 本地复现失败边界 | 超时返回 None |
| SDK 事件提取 | 实际 SDK 对象复现 | owner 消息被丢弃 |
| 平台输入契约 | 本地确认不匹配 | 多传 mode，线上响应未测试 |
| 候选生成与审核 | 本地复现不兼容 | 缺来源哈希 |
| 主动发卡 | 静态调用链及 SDK 校验 | API 投递未执行 |
| 真实模型注入、线上权限、发布 | skipped | 不在本次本地仓库审查范围内 |

已有安全测试提供了有效正面证据：`tests/test_safe_http.py` 用 mock 私网 DNS、重定向与受认证请求验证阻断逻辑；`site/tests/markdown.test.mjs` 验证 javascript 及实体混淆协议被拦截、原始 HTML 被转义；`tests/test_candidates.py` 验证审核失败回滚与候选保留。这些测试均通过，建议保留为回归门禁。它们不覆盖本报告发现的 SDK 接入和跨工作流关联。

复现脚本通过 AST 提取原始方法并注入本地 mock，未改写待测方法。运行时需要将 `.review-deps` 加入 PYTHONPATH。实际 SDK 对象另以 lark-oapi 1.7.3 本地验证。未读取真实凭据，证据中的 ou_owner、oc_1、999 均为假数据。没有修改业务源码或提交远程变更。
