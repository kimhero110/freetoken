# 网站项目汇总

归档日期：2026-09-06（Asia/Shanghai）。这是版本快照和恢复参考；项目根目录仍是主站日常开发目录。归档不会启动服务，也不会覆盖线上站点。

| 目录 | 内容与来源 |
| --- | --- |
| `main-site/` | `D:\Project\freetoken` 的 Git 已跟踪工作区文件，基线 `40bf5450`，包含成本计算器及六项审查修复 |
| `local-main-site/` | `C:\Users\Administrator\freetoken` 的本地旧工作区，基线 `558b386f` |
| `server-main-deployed/` | FreeTokenLab 上 `/var/www/freetoken-public/` 的当前静态发布文件，已核对 Nginx 容器挂载；发布标识 `20260903154831-a21d9cdd1cca` |
| `server-main-source/` | FreeTokenLab 上 `/opt/freetoken-intake/` 的 Git 已跟踪工作区文件；实际提交信息见来源日志 |
| `server-current/` | wuhao-server 上 `/opt/witkit-bench/` 当前评测站 v2 源码、15 项评测实现、工具、历史 `.bak` 文件和 systemd 服务配置 |
| `antigravity/` | Antigravity 早期 `server_bench.py`、域名反代配置脚本和对应文件元数据 |
| `logs/` | 本地审查/构建/测试日志、评测服务 journal、主站机器人容器日志、服务器版本证据、相关 Antigravity 历史记录的脱敏副本 |
| `private/` | **仅本地保存，不提交 Git**：服务器原始压缩包、报告数据库、完整 Antigravity 记录及未脱敏日志 |

## 版本选择

- 评测站修改应以 `server-current/` 为基准。首页在 `bench/ui.py`，报告与方法论页面在 `bench/pages.py`，入口是 `server_bench.py`，服务配置在 `deploy/witkit-bench.service`。
- `antigravity/server_bench.py` 为旧单文件原型，不能直接覆盖当前多模块 v2。
- 主站线上快照不包含尚未合并发布的成本计算器。后续功能开发继续在项目根目录的 `site/`、`scripts/` 等目录进行。
- 归档中的原始部署脚本可能具有生产写入行为，仅保留作为历史资料；不要为浏览归档执行它们。

## 完整性与范围

`sources.json` 记录版本及来源。`manifest.json` 列出每个公开归档文件的大小和 SHA-256，执行 `python _websit/archive_inventory.py` 校验。清单不包含自身及 `private/`。

取回时已将评测站 31 个当前 Python 文件与服务器 SHA-256 对照；数据库使用 SQLite backup API 获取一致性快照并通过完整性检查。源码做了语法解析，归档过程没有运行模型评测或付费调用。

主站开发快照仅收录 Git 已跟踪的工作区文件；依赖安装目录、`.git` 内部文件、字节码和临时构建缓存不重复归档。服务器评测目录的源码及历史备份完整取回；报告数据库独立放在 `private/reports.db`。服务日志从 2026-09-03 起导出，仅涵盖服务器仍保留的记录。

公开日志移除了疑似凭据行，并对访问 IP、报告链接标识等进行了脱敏；完整原始材料仍在本地 `private/`。没有收集 SSH 私钥、服务器 `.env` 或 Nginx 证书私钥。恢复数据库或排查用户请求时应使用本地私有备份，不能将其公开提交。

Antigravity 来源任务：`bf3efad4-9f27-4be8-aa5a-bb85d75a1b06`。相关记录保留原始行号，完整记录位于本地 `private/antigravity-transcript-full.jsonl`。
