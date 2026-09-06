# WitKit Studio 3

活动源码目录。原 `_websit/server-current` 保留为历史服务器快照；迁移前已核对核心 Python 文件 SHA256 与线上一致。

## 能力

- Python Decimal 纯函数按量成本引擎，同模型同币种比较；缓存、抵扣、显式汇率、适用条件未知与分项解释。
- 预算无需 Key；质量/综合模式沿用15项测试，通过统一客户端记录逐请求用量，不额外调用模型来计算费用。
- 全局2个执行worker、最多4个在途任务、每个会话1个任务、每个来源每小时10次远程操作；单任务最多90次请求和20分钟调用预留窗口。现有测试也保留各自输出和时间上限。
- 同源预算API、私有会话报告、7天脱敏摘要分享、撤销、JSON下载、追加预算分析；遗留公开报告URL保持可读，但不混入私有历史。
- DNS固定连接、公网HTTPS、禁止重定向、响应大小限制；日志不写请求URL/Key。

## 运行

Python 3.11或更新，无第三方运行时依赖。生产环境不设置下面的本地测试开关。

```sh
BENCH_HOST=127.0.0.1 BENCH_PORT=8510 STUDIO_LOCAL_HTTP=1 python studio/server_bench.py
python -m unittest discover -s studio/tests -v
```

正式服务为witkit-studio.service，配置只绑定100.64.0.17:8501，原witkit-bench.service已停止并保留用于回滚。`BENCH_DB`指向原有reports.db；新增表，不修改遗留runs内容。新Cookie为HttpOnly/Secure/SameSite=Lax。若反代需要按真实用户IP限流，`STUDIO_TRUSTED_PROXIES`仅配置已验证的代理源IP，并要求它覆写X-Real-IP；否则按直接来源限制。

会话不是跨设备账号：清除Cookie会失去私有报告访问权，界面提供下载与显式分享。Key只在任务内存中存在，进程重启后的在途任务标interrupted，不自动重发；取消不会撤销已收费请求。

价格来自data/pricing/pricebook.json的同版副本。更改报价必须通过PR检查与现有审核，构建检查两份内容相同；私有自填报价不写公共库。报价的period是用户明确选择的整份用量假设，不根据当前时间猜测。套餐、每日额度、复杂阶梯、税费及真实账单对账尚不在该版本计算范围，不支持规则返回错误。

## 验收与回滚

studio/tests包含精确金额、旧加权反例、未知值、币种、缓存、并发采集、幂等任务、私有报告、分享撤销、无额外计费调用、重启语义。端到端使用本地mock，生产不得启用STUDIO_TEST_LOOPBACK。

发布前备份应用、systemd配置、SQLite一致性快照及NPM配置。新版在独立目录测试后启动独立systemd服务，再切换NPM域名代理；数据库路径不变。回滚切回旧服务路径和代理配置，保留新增数据表，不用旧备份覆盖新报告。新域名先验证HTTPS与路由，旧test域名仅在GET/HEAD页面请求上转向studio；旧客户端POST不自动跨域转发凭据。
