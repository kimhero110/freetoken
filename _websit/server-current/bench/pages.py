"""Server-rendered pages: share report (/report/{id}) and criteria (/criteria)."""

import html

from . import baselines as B
from .registry import all_meta
from .radar import radar_svg

LIGHT_COLORS = {"pass": "#16a34a", "warn": "#d97706", "fail": "#dc2626", "info": "#6b7280"}
LIGHT_TEXT = {"pass": "通过", "warn": "可疑", "fail": "未通过", "info": "参考"}
DIM_NAMES = dict((k, zh) for k, zh, _ in B.DIMENSIONS)

_CSS = """
*{box-sizing:border-box} body{font-family:system-ui,-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
margin:0;background:#f6f7f9;color:#1f2937}
.wrap{max-width:900px;margin:0 auto;padding:24px 16px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:20px 22px;margin-bottom:16px}
h1{font-size:22px;margin:0 0 4px} .muted{color:#6b7280;font-size:13px}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;color:#fff}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:8px 6px;border-bottom:1px solid #f0f1f3;text-align:left;vertical-align:top}
.score{font-size:40px;font-weight:700}
.grid{display:flex;gap:18px;flex-wrap:wrap;align-items:center}
ul{margin:8px 0 0;padding-left:20px} li{margin:4px 0}
footer{font-size:12px;color:#9ca3af;padding:12px 0 30px;line-height:1.7}
a{color:#2563eb;text-decoration:none}
details summary{cursor:pointer;font-size:13px;color:#374151}
pre{background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:10px;font-size:12px;overflow:auto;white-space:pre-wrap;word-break:break-all}
"""


def _badge(light):
    return '<span class="badge" style="background:%s">%s</span>' % (LIGHT_COLORS.get(light, "#6b7280"), LIGHT_TEXT.get(light, light))


def _dot(light):
    return '<span class="dot" style="background:%s"></span>' % LIGHT_COLORS.get(light, "#6b7280")


def report_page(run):
    comp = run.get("composite", {})
    tests = run.get("tests", {})
    dim_scores = []
    for key, zh, _ in B.DIMENSIONS:
        d = comp.get("dims", {}).get(key, {})
        dim_scores.append((zh, d.get("score"), d.get("light", "info")))
    radar = radar_svg(dim_scores)

    verdict_items = "".join(
        "<li>%s%s</li>" % (_dot(l), html.escape(txt))
        for _, l, txt in comp.get("verdict", []))

    test_rows = []
    for meta in all_meta():
        t = tests.get(meta["tid"])
        if not t:
            continue
        test_rows.append(
            "<tr><td style='width:110px'>%s %s</td>"
            "<td><b>%s</b><div class='muted'>%s</div></td>"
            "<td style='width:90px'>%s</td></tr>" % (
                _dot(t.get("light")), html.escape(meta["dim"] and DIM_NAMES.get(meta["dim"], "")),
                html.escape(t.get("name_zh", "")), html.escape(t.get("summary_zh", "")),
                _badge(t.get("light"))))
    test_table = "<table><tr><th>维度</th><th>结果与摘要</th><th>判定</th></tr>%s</table>" % "".join(test_rows)

    usage = run.get("usage", {})
    return """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WitKit 评测报告 · %s</title><style>%s</style></head><body><div class="wrap">
<div class="card"><h1>WitKit Studio 评测报告</h1>
<div class="muted">模型 <b>%s</b> · 接入点 <b>%s</b> · %s · 耗时 %ss · 采样 %s 次请求 / %s tokens</div></div>

<div class="card"><div class="grid">
<div><div class="muted">综合评分</div><div class="score" style="color:%s">%s</div>
<div>%s</div></div><div>%s</div></div>
<ul>%s</ul></div>

<div class="card"><h3 style="margin:0 0 10px">分项明细</h3>%s</div>

<div class="card"><details><summary>原始数据（JSON）</summary><pre>%s</pre></details></div>

<footer>判定标准与基线版本：%s（见 <a href="/criteria">/criteria</a>）。基线为预置参考数据，非实时官方采样；
结果仅代表测试时点该接入点的表现。本报告不含 API Key。</footer>
</div></body></html>""" % (
        html.escape(str(run.get("model", ""))), _CSS,
        html.escape(str(run.get("model", ""))), html.escape(str(run.get("host", ""))),
        html.escape(str(run.get("created", ""))), run.get("elapsed_s", "-"),
        usage.get("requests", "-"), (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)),
        LIGHT_COLORS.get("fail" if any(d[2] == "fail" for d in dim_scores) else "warn" if any(d[2] == "warn" for d in dim_scores) else "pass", "#2563eb"),
        comp.get("composite", "-"), html.escape(str(comp.get("grade", ""))),
        radar, verdict_items, test_table,
        html.escape(__import__("json").dumps(comp, ensure_ascii=False)[:4000]),
        html.escape(run.get("baseline_version", B.BASELINE_VERSION)),
    )


def criteria_page():
    rows = []
    for m in all_meta():
        rows.append("<tr><td>%s</td><td><b>%s</b><div class='muted'>%s</div></td><td>%s</td><td style='text-align:right'>~%ss</td></tr>" % (
            html.escape(DIM_NAMES.get(m["dim"], m["dim"])),
            html.escape(m["name_zh"]), html.escape(m["desc_zh"]),
            html.escape(m["thresholds_zh"]), m["est_s"]))
    weights = "".join("<li>%s：权重 %d%%</li>" % (zh, int(w * 100)) for _, zh, w in B.DIMENSIONS)
    return """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WitKit 判定标准</title><style>%s</style></head><body><div class="wrap">
<div class="card"><h1>判定标准与方法论</h1>
<div class="muted">基线版本 %s · 全部判定为规则化阈值，无人工主观打分</div></div>
<div class="card"><h3>维度与权重</h3><ul>%s</ul>
<p class="muted">维度分 = 该维度下各测试得分均值（通过=100，可疑=60，未通过=10，参考项不计分）；
综合分 = 维度加权平均。</p></div>
<div class="card"><h3>测试项与阈值</h3>
<table><tr><th>维度</th><th>测试项</th><th>判定规则</th><th>预计耗时</th></tr>%s</table></div>
<div class="card"><h3>客观性声明</h3><ul>
<li>所有结论由规则引擎依据上表阈值自动生成，附原始证据。</li>
<li>基线数据为预置参考数据（版本化），非实时官方采样；官方网络表现受地域影响，延迟类结论仅供参考。</li>
<li>并发压测固定 8 路小请求，规模克制，避免对供应商造成滥用。</li>
<li>测试结果仅代表测试时点该接入点的表现，不构成对供应商的整体评价。</li>
<li>报告与历史记录不存储 API Key。</li></ul></div>
<footer>WitKit Studio · <a href="/">返回评测中心</a></footer>
</div></body></html>""" % (_CSS, B.BASELINE_VERSION, weights, "".join(rows))
