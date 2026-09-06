# 定时核验修复：实施记录与上线手册

日期：2026-09-06。范围：现有检查、候选发布、通知及页面日期。本轮工作在本地进行；没有推送、部署、改远端变量、启动收费调用或发送通知。

## 已实现的代码

- `scripts/check_state.py`：专用状态分支、版本检查、Git fast-forward 并发写入、确认丢失协调。复用 CI 现有 App 权限，不扩权机器人 PAT。
- `scripts/check_runner.py`：一次自动收费尝试、跨运行复用结果、持久运行预算、同来源版本防换供应商重试、结果未知停止。
- `scripts/extract.py`：默认干跑、预算与时段检查、SDK 禁用重试、输入快照验证、逐来源处理。
- `scripts/fetch_sources.py`：临时目录中的抓取快照及覆盖摘要，部分失败仍保留成功来源；不提前推进审核基线。
- `scripts/publish_candidates.py`：干净工作树，只提交新候选；稳定分支、已存在 PR 协调、关闭后不重开，无候选正常退出。
- `scripts/check_summary.py`：保存分阶段结果，不以候选发布成功覆盖上游失败。
- `daemon/check_monitor.py`、`daemon/alert_store.py`：独立监控线程、事务 outbox、有限通知重试、计划窗口、来源与调用故障分离。
- 页面：删除固定核验日期，区别人工审核与自动抓取，状态缺失或过期显示未知。
- `scripts/check_heartbeat.py` 和 Nginx 示例：供独立监控读取的心跳探测及只读状态路径，尚未部署。

## 尚未完成的生产门槛

1. **历史审计**：当前 `.cache/changed.json` 已为空，不能证明过去没有收费调用。核对失败运行 33995065730、33986529634、34003281818 的可信产物、候选 PR 与供应商记录；无法确定的来源版本保留阻塞记录。`config/check-history.json` 的 audit_complete 当前为 false，初始化会拒绝继续。
2. **独立告警接入**：确定机器人服务器以外的执行位置及独立通知接收通道，安装心跳检查；实际验证停机、发送失败及恢复。现有主监控默认关闭。
3. **费用配置和真实验证**：确定模型、输出上限与调用数上限，先单来源受控验证，再恢复计划运行。真实测试必须有明确预算，不能拿无限重试联调。
4. **观察期**：至少覆盖一个完整调度周期和最后一次启动宽限；没有观察结果不能宣称修复已上线或告警闭环已完成。

这些是上线门槛，不应通过改成 true、跳过测试或清空状态绕过。

## 部署步骤

### A. 候选与账本

先合并经过检查的代码。新 update 工作流只有 `CHECK_PAID_ENABLED=true` 且 `CHECK_READINESS_CONFIRMED=true` 才允许新增调用；两个仓库变量默认缺失，所以默认干跑。旧的费用窗口忽略开关被代码拒绝，fallback/load_balance 也不会重发收费请求。

历史审计完成后，在受审的 `config/check-history.json` 中设置 audit_complete，source_versions 填入无法确认的来源版本摘要。摘要算法为 `check_state.digest([platform_slug, source_url, source_hash])`，不得填提示词或原始响应。所有未知历史版本必须列出；不允许为了初始化而填空数组。

用已有仓库写凭据，在可信 main 工作树运行：

```sh
python -m scripts.check_admin init
python -m scripts.check_admin inspect
```

该操作创建/更新 `automation-state`，只存 JSON，不含可执行工作流，不合并进 main。此文档未执行这些命令。状态分支是公开的且 Git 历史长期存在，只有适合长期公开的数据才能写入。

配置 `CHECK_MAX_CALLS`（1–100 的明确整数）、`CHECK_MAX_OUTPUT_TOKENS`（1–4096）后仍先保持收费开关关闭。运行编号相同的 rerun 不重置预算；每个来源版本只允许一个自动尝试。范围较大的允许值不是建议预算，应按受控验证需求取最小必要值。

### B. 主监控

在现有机器人部署配置中增加：

```text
CHECK_MONITOR_ENABLED=true
CHECK_MONITOR_SINCE=<本次启用的 UTC ISO 时间，必须带时区>
CHECK_ALERT_DB=/data/check-alerts.sqlite3
CHECK_STATUS_PATH=/data/check-public/status.json
```

沿用现有 /data 持久卷；先备份，确认容器用户可写。保持现有 GitHub PAT 权限不变，监控只读 Actions 与公开状态分支。SQLite 损坏不自动重建，启动失败或健康状态过期需要外部监控报告。

将 `/data/check-public` 单独只读挂载给现有 Nginx，参考 `deploy/check-status.nginx.conf.example`。不要暴露整个 /data、数据库或日志，不修改不可变发布目录。执行 Nginx 配置校验后再加载；从两个站点验证 JSON 可读及浏览器跨域。

### C. 独立监控

在主机器人服务器以外，用现有监控设施每 5 分钟运行：

```sh
python -m scripts.check_heartbeat
```

退出码非零代表 HTTP 故障、监控降级、通知故障或心跳超过 15 分钟未更新。独立设施必须配置自己的通知通道、失败去重和恢复通知；这个脚本本身不发消息。未找到或配置好独立设施，就保持生产验收未通过。GitHub 与飞书同时不可用时，不承诺飞书通知仍实时到达。

## 故障处置

| 错误/状态 | 行为与处理 |
|---|---|
| STATE_NOT_INITIALIZED / HISTORY_AUDIT_REQUIRED | 不收费；完成历史审计及初始化 |
| STATE_CONTENTION / GIT_OPERATION_FAILED | 不绕过账本；恢复 Git 后先核对远端状态 |
| CALL_UNCERTAIN / UNCERTAIN | 不自动重发；确认旧运行停止，找到可信结果或明确放弃 |
| RESULT_EXPIRED / SOURCE_ALREADY_ATTEMPTED | 保留收费事实，停止自动调用；需要另行审查刷新方案 |
| PROVIDER_OR_BUDGET_NOT_CONFIGURED | 修复配置；不要新增未知费用备用供应商 |
| deferred | 等待下一允许时段，下一计划运行重新评估；监控保留阻塞提示 |
| CANDIDATE_PUBLISH_FAILED | 重试发布步骤，或重跑流程复用已保存结果；不要删账本 |
| PR closed | 保持停止，不自动重开 |
| notification exhausted | 修复通道后发新的审计事件；不重跑提取 |
| monitoring unknown | 检查 GitHub 可达性、数据库和主监控；由独立心跳处理主机失联 |

不确定调用可使用两个明确的、不会发送模型请求的处置命令：

```sh
python -m scripts.check_admin attach-result --key <64位调用键> --result-file <已验证的结构化JSON> --actor <GitHub用户名> --old-run-stopped
python -m scripts.check_admin abandon --key <64位调用键> --actor <GitHub用户名> --old-run-stopped
```

只有确认旧运行停止后才能使用上述标志；命令会保留处置记录并阻止迟到写入。abandon 不清除去重事实，也不会授权新的收费请求。当前没有提供自动付费重试按钮；如确需重新付费，应单独审查一次性授权实现，不能手工删记录。

## 回滚

优先关闭 CHECK_PAID_ENABLED，保留账本、通知数据库和只读监控。不要回滚到旧提取脚本后恢复收费调度。数据库迁移或回滚前备份；状态版本无法读取时停止并告警，不能清空数据。默认不清理收费墓碑；账本达到大小上限会停止写入，需要维护处理。

## 当前实现与原计划的保守差异

- 未实现自动重新授权付费尝试：无法确定的调用保留人工处理，不因租约过期接管。
- 计划运行归属目前依据 GitHub 创建时间及 180 分钟窗口；超过该窗口的延迟不能可靠还原原时隙，不宣称精确归因。需要生产观察后决定是否补充逐 cron 身份记录。
- 未增加永久维护静默开关：上线前监控从明确启用时间开始；启用后暂停会显示阻塞，不永久吞掉告警。
- 公共状态容量达到上限会失败关闭；没有自动删除 Git 历史或去重墓碑。

以上限制不应用“所有问题已解决”概括；它们必须在生产签收时明确核对。

## 本地验证结果

- Python 完整回归：167 项通过，其中包含新增调用去重、Git 并发/确认丢失、候选发布隔离、通知重启与有限重试测试。
- 原飞书机器人真实 SDK 集成测试：22 项通过（消息发送被测试替身接管，没有实际外发）。
- 前端测试：23 项通过，覆盖状态过期、缺失、异常与干跑表达。
- Astro 静态构建：成功，生成 109 个页面。
- git diff --check：通过。

本地测试发现并修复了 SQLite 连接未及时关闭、空预算环境变量阻断干跑、已保存结果被费用时段阻断、旧失败通知在恢复后继续重试等问题。最后补充同名外部 PR 的仓库归属过滤。

尚未执行：生产历史迁移、独立通道通知实测、真实收费调用、生产部署及完整调度观察期。没有将这些项目计入通过数量。


## 2026-09-06 恢复补充

已发布主修复 f3c62495，健康接口已获明确批准并开放。进一步审计 13 次历史失败运行：8 次完成了合计 32 次提取但未发布，另 5 次未调用模型；没有可恢复的 Actions artifact。15 个可识别旧版本指纹保留阻塞记录，最早两次缺少版本指纹的丢失事实也记录在账本中，不能声称旧结果已恢复。

初始化不再要求找回已丢失文件，而是导入已审计的旧调用事实。管理员可通过 `check_admin init --authorize-refresh --actor <GitHub用户名> --old-run-stopped` 授权一次当前来源重新核验；授权仅一小时有效、每来源只能消耗一次，并与收费 intent 原子保存。重复执行初始化不能重置已用授权。正常运行仍不能重放未决调用。

已按 [DeepSeek 当前价格页](https://api-docs.deepseek.com/quick_start/pricing/) 修正时段：周一至周五 UTC 01:00–04:00、06:00–10:00 为高峰，其他时段（包括周末）为优惠时段。更新提取模型为 deepseek-v4-flash，关闭 thinking，SDK 不重试；模型列表预检通过后才允许建立收费 intent。恢复验收限制每运行最多 4 次请求，每次最多 1024 输出 token，页面输入仍限制为 8000 字符。

新增 check-monitor.yml：GitHub 独立主机每 5 分钟检查业务服务器心跳，复用现有发布通知 webhook，不复制机器人凭据到其他服务器。异常和恢复事件写入持久账本，最多 4 次发送尝试；联调事件与真实事件隔离。此方案能在业务服务器停机时发送告警，但不承诺 GitHub 和飞书同时失效时仍能通过飞书通知。
