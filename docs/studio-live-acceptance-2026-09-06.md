# WitKit Studio 上线验收（2026-09-06）

## 正式入口

- https://witkit.zone/：WitKit 品牌首页，连接 FreeToken 与 Studio。
- https://freetokens.info/：免费算力情报、平台详情与接入指南；平台详情携带报价标识进入 Studio。
- https://studio.witkit.zone/：独立工作台，提供预算、质量评测、综合分析、比较和私有报告。
- test.witkit.zone 的 GET/HEAD 保留路径以 308 跳转 Studio；其他方法返回 409，避免转发旧客户端凭据。遗留公开报告继续可读。
- witkit.zone 的旧平台/文章路径以 301 转向 freetokens.info；旧成本入口保留兼容页面。

## 已上线版本

- 实现 PR：https://github.com/kimhero110/freetoken/pull/17
- main 合并提交：3c14e344132b1ac066d98c6f1f1bc187c1412e00。
- 静态站发布：https://github.com/kimhero110/freetoken/actions/runs/34008948897 （成功）。
- 两站 release-id：20260906032600-3c14e344132b。
- Studio 应用提交：986c40500031761992218a327a9b8569116dcd44，包含于上述合并；服务 3.0，成本引擎 1.0.1。
- 活动源码为 studio/，历史快照 _websit/server-current 不作为当前部署源。

## 验收证据

- Python 主测试 142、飞书 SDK 集成 22、Studio 20、Node 20，共 204 项通过；Astro 构建 109 页。
- Studio 端到端测试使用本地模型 mock，覆盖幂等、会话隔离、分享撤销、重启不重发、综合分析复用同一次请求及无 Key 预算。
- 正式 HTTPS 页面点击预算计算：100 万输入、100 万输出、零缓存，所选报价得到 USD 1.76，明细为输入 0.44、输出 1.32、缓存 0。
- 正式 healthz 返回应用及引擎版本；两主站 release-id 相同；三个首页、平台详情、跨站入口和旧域名跳转可达。
- 本次上线验收没有执行付费模型推理。真实供应商调用仍需用户选择评测并提交自己的 Key。

## 运维与回滚

Studio 主机：wuhao-server。活动服务 witkit-studio.service，发布目录 /opt/witkit-studio/releases/986c4050，绑定 100.64.0.17:8501，数据库沿用 /opt/witkit-bench/data/reports.db。原 witkit-bench.service 已停止并保留。

Nginx Proxy Manager 的 Studio 代理为 id 5，旧 test 代理为 id 4。studio DNS A 记录原已存在，本次没有修改 DNS。新证书有效期至 2026-12-05，使用现有 acme.sh DNS 续期机制，安装后校验并重载 NPM。

迁移前私有备份位于 /opt/witkit-studio/backups/before-v3：原服务配置、SQLite 一致性快照、NPM 数据库和旧代理配置。备份与凭据不提交 Git。回滚应用时先停新版、恢复旧服务与原代理配置，执行 nginx 配置校验后重载；保留新增数据库表，不以旧快照覆盖上线后报告。

WitKit 静态主机：FreeTokenLab；活动配置 /root/verdaccio/freetoken-nginx.conf，模板 deploy/nginx-witkit-brand.conf，旧配置备份为同目录 freetoken-nginx.conf.before-studio。回滚首页时将备份内容写回活动配置，运行 docker exec freetoken-nginx nginx -t，通过后运行 docker exec freetoken-nginx nginx -s reload。

静态站已通过现有审核工作流自动发布。Studio 当前需要按 studio/README.md 经测试后执行独立服务部署；GitHub 工作流会验证 Studio，但不会自动升级该服务。报价更新也必须同步部署 Studio，不能仅发布静态站。

## 当前范围及后续工作

已实现文本 Token 线性计费、缓存、确认抵扣、显式汇率、同模型同币种比较和未知项说明。质量评测费用与业务月预算分别展示。私有报告基于浏览器会话，并非跨设备账号。

后续独立迭代：跨设备账号和报告归属、更多经核实的报价、复杂套餐/阶梯规则、实际账单对账，以及 Studio 的自动部署与回滚。现有实现不将这些能力呈现为已完成。
