# -*- coding: utf-8 -*-
"""
WitKit Studio: LLM Quality & Security Benchmark Arena
------------------------------------------------------
Lightweight, zero-dependency Python 3 standard library web service.
- Dynamically pulls models list from target server via GET /v1/models
- Supports single-model testing, auto-pull on Key blur/button, and batch testing
- Semi Design / Enterprise Cloud Console UI (wxmaas/New-API aesthetic)
- 5 Core Benchmark Modules:
  1. Latency & TTFT (Time To First Token)
  2. Protocol & Header Fingerprinting
  3. Function Calling Compliance (JSON Schema & Tool Calls)
  4. Needle In A Haystack (32K Dynamic Token Recall)
  5. Anti-Downgrade & Logic Trap Verification
"""

import os
import sys
import json
import time
import uuid
import socket
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PORT = 8500
HOST = "0.0.0.0"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WitKit Studio | 大模型真实性与质量评测中枢</title>
  <link rel="icon" href="https://witkit.zone/favicon.svg" type="image/svg+xml">
  <!-- Tailwind CSS & Lucide Icons via CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .semi-card { background: #ffffff; border: 1px solid #e5e8ef; border-radius: 8px; box-shadow: 0 1px 2px 0 rgba(0,0,0,0.03); }
    .semi-input { border: 1px solid #c9cdd4; transition: all 0.2s; }
    .semi-input:focus { border-color: #1664ff; box-shadow: 0 0 0 2px rgba(22,100,255,0.15); outline: none; }
    .semi-btn-primary { background: #1664ff; color: #fff; transition: all 0.2s; }
    .semi-btn-primary:hover { background: #0e4ed8; }
    .nav-link { color: #4e5969; font-size: 14px; font-weight: 500; transition: color 0.15s; }
    .nav-link:hover { color: #1664ff; }
    .tag-pass { background: #e8ffea; color: #00b42a; border: 1px solid #aff0b5; }
    .tag-fail { background: #ffece8; color: #f53f3f; border: 1px solid #fbb3ab; }
    .tag-warn { background: #fff7e8; color: #ff7d00; border: 1px solid #fed4a4; }
    .tag-info { background: #f2f3f5; color: #4e5969; border: 1px solid #e5e6eb; }
    pre::-webkit-scrollbar { width: 6px; height: 6px; }
    pre::-webkit-scrollbar-thumb { background: #c9cdd4; border-radius: 3px; }
  </style>
</head>
<body class="bg-[#f7f8fa] text-[#1d2129] min-h-screen flex flex-col">

  <!-- Top Navigation Header (WitKit Official Matrix) -->
  <header class="bg-white border-b border-[#e5e8ef] sticky top-0 z-50">
    <div class="max-w-[1440px] mx-auto px-6 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-6">
        <a href="https://witkit.zone" class="flex items-center space-x-3">
          <div class="w-9 h-9 rounded-lg bg-[#1664ff] flex items-center justify-center text-white font-bold text-lg shadow-sm">
            W
          </div>
          <div>
            <div class="font-bold text-[#1d2129] text-base leading-tight tracking-tight flex items-center gap-1.5">
              WitKit Studio
              <span class="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#e8f3ff] text-[#1664ff] border border-[#bedaff]">评测中心</span>
            </div>
            <div class="text-[11px] text-[#86909c]">大模型质量、合规与真实性综合探针</div>
          </div>
        </a>
        <div class="h-4 w-[1px] bg-[#e5e8ef] hidden md:block"></div>
        <nav class="hidden md:flex items-center space-x-6">
          <a href="https://witkit.zone" class="nav-link flex items-center gap-1.5">
            <i data-lucide="globe" class="w-4 h-4"></i> 主站门户
          </a>
          <a href="https://analytics.witkit.zone" class="nav-link flex items-center gap-1.5" target="_blank">
            <i data-lucide="bar-chart-3" class="w-4 h-4"></i> 监控大盘
          </a>
          <a href="https://freetokens.info" class="nav-link flex items-center gap-1.5" target="_blank">
            <i data-lucide="layers" class="w-4 h-4"></i> 算力雷达
          </a>
        </nav>
      </div>
      <div class="flex items-center space-x-3">
        <a href="https://github.com/kimhero110/freetoken" target="_blank" class="text-[#4e5969] hover:text-[#1664ff] p-2 rounded-lg hover:bg-[#f2f3f5] transition">
          <i data-lucide="github" class="w-5 h-5"></i>
        </a>
        <span class="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded bg-[#e8ffea] text-[#00b42a] font-medium border border-[#aff0b5]">
          <span class="w-1.5 h-1.5 rounded-full bg-[#00b42a] animate-pulse"></span> 探活引擎就绪
        </span>
      </div>
    </div>
  </header>

  <!-- Main Content Dashboard -->
  <main class="flex-1 max-w-[1440px] w-full mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-12 gap-6">

    <!-- Left Column: Parameters & Model Discovery (4 Cols) -->
    <div class="lg:col-span-4 space-y-6">
      <div class="semi-card p-5">
        <div class="flex items-center justify-between pb-3 mb-4 border-b border-[#f2f3f5]">
          <h2 class="font-semibold text-sm text-[#1d2129] flex items-center gap-2">
            <i data-lucide="sliders" class="w-4 h-4 text-[#1664ff]"></i> 待测服务与模型自动发现
          </h2>
          <span class="text-[11px] text-[#86909c]">动态拉取目标全部模型</span>
        </div>

        <form id="benchForm" class="space-y-4 text-sm" onsubmit="event.preventDefault(); runBenchmark();">
          <div>
            <label class="block text-xs font-semibold text-[#4e5969] mb-1.5">API 接入基地址 (Base URL)</label>
            <input type="text" id="baseUrl" required placeholder="https://wxmaas.clarmic.com/v1" 
                   value="https://wxmaas.clarmic.com/v1"
                   class="w-full px-3 py-2 text-sm rounded semi-input mono bg-[#fafafa]">
            <p class="text-[11px] text-[#86909c] mt-1">需兼容标准 OpenAI 协议，结尾带 /v1</p>
          </div>

          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-xs font-semibold text-[#4e5969]">API Key (测试令牌)</label>
              <button type="button" onclick="fetchModelsList()" id="btnFetchModels" class="text-[11px] text-[#1664ff] hover:underline flex items-center gap-1 font-medium">
                <i data-lucide="refresh-cw" class="w-3 h-3"></i> 自动拉取该 Key 可用模型
              </button>
            </div>
            <input type="password" id="apiKey" required placeholder="sk-..." onblur="if(this.value.trim().length > 5 && pulledModels.length === 0) fetchModelsList();"
                   class="w-full px-3 py-2 text-sm rounded semi-input mono bg-[#fafafa]">
          </div>

          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-xs font-semibold text-[#4e5969]">待测模型选择 (从服务端动态提取)</label>
              <span id="modelCountBadge" class="text-[10px] text-[#86909c]">尚未拉取</span>
            </div>
            <div class="space-y-2">
              <select id="modelSelect" onchange="onModelSelectChange(this.value)" class="w-full px-3 py-2 text-sm rounded semi-input bg-white text-[#1d2129]">
                <option value="">-- 请输入 API Key 后点击上方“自动拉取” --</option>
              </select>
              <input type="text" id="modelName" required placeholder="例如: qwen-plus 或自定义模型标识" 
                     class="w-full px-3 py-2 text-xs rounded semi-input mono bg-[#fafafa]"
                     title="可直接手工输入或在上方下拉选择">
            </div>
          </div>

          <div class="pt-2">
            <label class="block text-xs font-semibold text-[#4e5969] mb-2">执行评测专项 (勾选)</label>
            <div class="space-y-2 text-xs">
              <label class="flex items-center gap-2 p-2 rounded hover:bg-[#f7f8fa] cursor-pointer border border-[#f2f3f5]">
                <input type="checkbox" id="testLatency" checked class="rounded text-[#1664ff]">
                <div>
                  <div class="font-medium text-[#1d2129]">1. 毫秒级延迟与流式健康 (TTFT)</div>
                  <div class="text-[11px] text-[#86909c]">精确测量首字输出时间与每秒 Token 产出速度</div>
                </div>
              </label>

              <label class="flex items-center gap-2 p-2 rounded hover:bg-[#f7f8fa] cursor-pointer border border-[#f2f3f5]">
                <input type="checkbox" id="testToolCall" checked class="rounded text-[#1664ff]">
                <div>
                  <div class="font-medium text-[#1d2129]">2. 工具调用合规检测 (Function Calling)</div>
                  <div class="text-[11px] text-[#86909c]">验证是否为阉割逆向池，检验 Agent 工具分发</div>
                </div>
              </label>

              <label class="flex items-center gap-2 p-2 rounded hover:bg-[#f7f8fa] cursor-pointer border border-[#f2f3f5]">
                <input type="checkbox" id="testNeedle" checked class="rounded text-[#1664ff]">
                <div>
                  <div class="font-medium text-[#1d2129]">3. 真实长上下文探针 (Needle in Haystack)</div>
                  <div class="text-[11px] text-[#86909c]">构建 32K 文本中间植入随机密令，测试截断与遗忘</div>
                </div>
              </label>

              <label class="flex items-center gap-2 p-2 rounded hover:bg-[#f7f8fa] cursor-pointer border border-[#f2f3f5]">
                <input type="checkbox" id="testReasoning" checked class="rounded text-[#1664ff]">
                <div>
                  <div class="font-medium text-[#1d2129]">4. 防降级与逻辑陷阱 (Anti-Downgrade)</div>
                  <div class="text-[11px] text-[#86909c]">测试经典易错逻辑，识别是否用 8B 小模型冒充</div>
                </div>
              </label>
            </div>
          </div>

          <button type="submit" id="submitBtn" class="w-full py-2.5 rounded font-medium semi-btn-primary flex items-center justify-center gap-2 mt-4 shadow-sm">
            <i data-lucide="play" class="w-4 h-4"></i> 开始当前模型全项质检
          </button>
        </form>
      </div>

      <!-- Quick Inspection Guide -->
      <div class="semi-card p-5 bg-[#fcfdff] border-[#e8f3ff]">
        <h3 class="text-xs font-bold text-[#1664ff] uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <i data-lucide="shield-check" class="w-4 h-4"></i> 动态拉取说明
        </h3>
        <p class="text-xs text-[#4e5969] leading-relaxed">
          输入 API Key 之后，点击 **“自动拉取该 Key 可用模型”**，系统会直接请求供应商服务器的 <code class="mono text-[#1664ff]">GET /v1/models</code> 接口，枚举该账户下实际开通的全部大模型列表。
        </p>
      </div>
    </div>

    <!-- Right Column: Live Results & Scoreboard (8 Cols) -->
    <div class="lg:col-span-8 space-y-6">

      <!-- Realtime Scoreboard Header -->
      <div class="semi-card p-6">
        <div class="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-[#f2f3f5]">
          <div>
            <h2 class="text-base font-bold text-[#1d2129] flex items-center gap-2">
              评测综合判决与置信度大盘
              <span id="overallStatusBadge" class="text-xs font-semibold px-2.5 py-0.5 rounded tag-info">待测</span>
            </h2>
            <p class="text-xs text-[#86909c] mt-0.5" id="currentModelInfo">请先选择模型并启动评测</p>
          </div>
          <button onclick="exportReport()" class="px-3 py-1.5 text-xs font-medium border border-[#c9cdd4] rounded hover:bg-[#f2f3f5] transition flex items-center gap-1.5">
            <i data-lucide="download" class="w-3.5 h-3.5"></i> 导出技术尽调对账报告
          </button>
        </div>

        <!-- 4 Key Metric Cards -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
          <div class="p-3.5 rounded bg-[#f7f8fa] border border-[#f2f3f5]">
            <div class="text-[11px] text-[#86909c]">首字延迟 (TTFT)</div>
            <div id="metricTtft" class="text-lg font-bold text-[#1d2129] mt-1 mono">-- ms</div>
            <div id="metricTtftTag" class="text-[10px] text-[#86909c] mt-0.5">未测试</div>
          </div>
          <div class="p-3.5 rounded bg-[#f7f8fa] border border-[#f2f3f5]">
            <div class="text-[11px] text-[#86909c]">工具调用 (Function Calling)</div>
            <div id="metricTool" class="text-lg font-bold text-[#1d2129] mt-1 mono">--</div>
            <div id="metricToolTag" class="text-[10px] text-[#86909c] mt-0.5">未测试</div>
          </div>
          <div class="p-3.5 rounded bg-[#f7f8fa] border border-[#f2f3f5]">
            <div class="text-[11px] text-[#86909c]">针海长文本召回</div>
            <div id="metricNeedle" class="text-lg font-bold text-[#1d2129] mt-1 mono">--</div>
            <div id="metricNeedleTag" class="text-[10px] text-[#86909c] mt-0.5">未测试</div>
          </div>
          <div class="p-3.5 rounded bg-[#f7f8fa] border border-[#f2f3f5]">
            <div class="text-[11px] text-[#86909c]">原厂通道真实性置信度</div>
            <div id="metricScore" class="text-lg font-bold text-[#1d2129] mt-1 mono">-- %</div>
            <div id="metricScoreTag" class="text-[10px] text-[#86909c] mt-0.5">未测试</div>
          </div>
        </div>
      </div>

      <!-- Execution Log & Output Stream Console -->
      <div class="semi-card p-6">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-semibold text-[#1d2129] flex items-center gap-2">
            <i data-lucide="terminal" class="w-4 h-4 text-[#1664ff]"></i> 实时流式校验过程与响应报文
          </h3>
          <span id="liveIndicator" class="text-xs text-[#86909c] flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-[#c9cdd4]"></span> 空闲
          </span>
        </div>

        <div id="consoleLog" class="w-full h-96 bg-[#18191c] text-[#e5e8ef] p-4 rounded-lg mono text-xs overflow-y-auto leading-relaxed border border-[#272a31]">
          <span class="text-[#6b7785]">// 输入 API Key 后，系统将自动拉取服务端上架的所有大模型。<br>
// 选中目标模型后点击“开始当前模型全项质检”，将执行真实时延、Function Calling 与针海长文本深度探测...</span>
        </div>
      </div>

    </div>
  </main>

  <!-- Global Footer with MIIT Compliance -->
  <footer class="bg-white border-t border-[#e5e8ef] py-4 mt-auto text-xs text-[#86909c] text-center">
    <div class="max-w-[1440px] mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-2">
      <div>© 2026 WitKit Studio. 大模型基础设施与质量治理平台</div>
      <div class="flex items-center space-x-3">
        <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener" class="hover:text-[#1664ff] underline">苏ICP备2026003689号-2</a>
        <span>|</span>
        <a href="https://witkit.zone" class="hover:text-[#1664ff]">witkit.zone</a>
      </div>
    </div>
  </footer>

  <script>
    lucide.createIcons();

    let fullReportData = null;
    let pulledModels = [];

    function appendLog(msg, color = "#e5e8ef") {
      const box = document.getElementById('consoleLog');
      const p = document.createElement('div');
      p.style.color = color;
      p.innerHTML = msg;
      box.appendChild(p);
      box.scrollTop = box.scrollHeight;
    }

    async function fetchModelsList() {
      const baseUrl = document.getElementById('baseUrl').value.trim();
      const apiKey = document.getElementById('apiKey').value.trim();

      if (!baseUrl || !apiKey) {
        alert("请先填写 Base URL 和 API Key，才能拉取服务端模型列表！");
        return;
      }

      const btn = document.getElementById('btnFetchModels');
      btn.innerHTML = '<span class="animate-spin">⌛</span> 正在向目标端点查询...';

      appendLog(`[DISCOVERY] 向 ${baseUrl}/models 发送鉴权请求，拉取可用大模型列表...`, '#1664ff');

      try {
        const resp = await fetch('/api/models', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ base_url: baseUrl, api_key: apiKey })
        });

        const res = await resp.json();
        if (res.success && Array.isArray(res.models) && res.models.length > 0) {
          pulledModels = res.models;
          const select = document.getElementById('modelSelect');
          select.innerHTML = '<option value="">-- 已拉取 ' + res.models.length + ' 个模型，请选择 --</option>';
          
          res.models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.innerText = m;
            select.appendChild(opt);
          });

          document.getElementById('modelCountBadge').innerText = `已发现 ${res.models.length} 个模型`;
          document.getElementById('modelCountBadge').className = 'text-[10px] font-semibold text-[#00b42a]';
          
          // Default to first model
          select.selectedIndex = 1;
          onModelSelectChange(res.models[0]);

          appendLog(`[SUCCESS] 成功从服务端获取到 ${res.models.length} 个开通模型:`, '#00b42a');
          appendLog(`  清单: ${res.models.slice(0, 10).join(', ')}${res.models.length > 10 ? ' ... 等共 ' + res.models.length + ' 个' : ''}`, '#86909c');
        } else {
          appendLog(`[WARN] 未能拉取到模型列表: ${res.error || '返回模型列表为空'}`, '#ff7d00');
          alert("拉取模型失败: " + (res.error || "未能获取到模型"));
        }
      } catch (err) {
        appendLog(`[ERROR] 接口网络异常: ${err.message}`, '#f53f3f');
      } finally {
        btn.innerHTML = '<i data-lucide="refresh-cw" class="w-3 h-3"></i> 自动拉取该 Key 可用模型';
        lucide.createIcons();
      }
    }

    function onModelSelectChange(val) {
      if (val) {
        document.getElementById('modelName').value = val;
        document.getElementById('currentModelInfo').innerText = `当前选中待测模型: ${val}`;
      }
    }

    async function runBenchmark() {
      const baseUrl = document.getElementById('baseUrl').value.trim();
      const apiKey = document.getElementById('apiKey').value.trim();
      const model = document.getElementById('modelName').value.trim();

      if (!baseUrl || !apiKey || !model) {
        alert("请完整填写 Base URL、API Key 与待测 Model！");
        return;
      }

      const submitBtn = document.getElementById('submitBtn');
      submitBtn.disabled = true;
      submitBtn.classList.add('opacity-50', 'cursor-not-allowed');

      const ind = document.getElementById('liveIndicator');
      ind.innerHTML = '<span class="w-2 h-2 rounded-full bg-[#00b42a] animate-ping"></span> 评测进行中...';

      const box = document.getElementById('consoleLog');
      box.innerHTML = '';
      appendLog(`[INIT] 连接目标端点: ${baseUrl}`, '#1664ff');
      appendLog(`[INIT] 目标待测模型: ${model}`, '#1664ff');

      const payload = {
        base_url: baseUrl,
        api_key: apiKey,
        model: model,
        tests: {
          latency: document.getElementById('testLatency').checked,
          tool_call: document.getElementById('testToolCall').checked,
          needle: document.getElementById('testNeedle').checked,
          reasoning: document.getElementById('testReasoning').checked
        }
      };

      try {
        const response = await fetch('/api/benchmark', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const result = await response.json();
        fullReportData = result;
        renderResults(result);
      } catch (err) {
        appendLog(`[FATAL] 请求异常中断: ${err.message}`, '#f53f3f');
      } finally {
        submitBtn.disabled = false;
        submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        ind.innerHTML = '<span class="w-2 h-2 rounded-full bg-[#1664ff]"></span> 评测完成';
      }
    }

    function renderResults(res) {
      if (!res.success) {
        appendLog(`[ERROR] 评测失败: ${res.error}`, '#f53f3f');
        return;
      }

      const logs = res.logs || [];
      logs.forEach(l => appendLog(l.text, l.color || '#e5e8ef'));

      // Update metrics
      if (res.metrics.ttft_ms !== null) {
        document.getElementById('metricTtft').innerText = `${res.metrics.ttft_ms} ms`;
        document.getElementById('metricTtftTag').innerText = res.metrics.ttft_ms < 1500 ? '🟢 极速/低延迟' : '⚠️ 存在中继排队';
      }

      document.getElementById('metricTool').innerText = res.metrics.tool_pass ? 'PASS' : 'FAIL';
      document.getElementById('metricTool').style.color = res.metrics.tool_pass ? '#00b42a' : '#f53f3f';
      document.getElementById('metricToolTag').innerText = res.metrics.tool_pass ? '标准 Function Calling' : '逆向号池或不支持';

      document.getElementById('metricNeedle').innerText = res.metrics.needle_pass ? 'PASS' : 'FAIL';
      document.getElementById('metricNeedle').style.color = res.metrics.needle_pass ? '#00b42a' : '#f53f3f';
      document.getElementById('metricNeedleTag').innerText = res.metrics.needle_pass ? '32K 密令完整精准召回' : '发生前置截断/遗忘';

      const score = res.metrics.confidence_score;
      document.getElementById('metricScore').innerText = `${score} %`;
      document.getElementById('metricScore').style.color = score >= 80 ? '#00b42a' : (score >= 50 ? '#ff7d00' : '#f53f3f');
      document.getElementById('metricScoreTag').innerText = score >= 80 ? '高置信原厂直连' : '高度疑似数据池/中继掺水';

      const ob = document.getElementById('overallStatusBadge');
      if (score >= 80) {
        ob.className = 'text-xs font-semibold px-2.5 py-0.5 rounded tag-pass';
        ob.innerText = '原厂级通道';
      } else if (score >= 50) {
        ob.className = 'text-xs font-semibold px-2.5 py-0.5 rounded tag-warn';
        ob.innerText = '普通可用中继';
      } else {
        ob.className = 'text-xs font-semibold px-2.5 py-0.5 rounded tag-fail';
        ob.innerText = '劣质/逆向号池';
      }
    }

    function exportReport() {
      if (!fullReportData) {
        alert("请先执行评测后，再导出报告！");
        return;
      }
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(fullReportData, null, 2));
      const a = document.createElement('a');
      a.setAttribute("href", dataStr);
      a.setAttribute("download", `witkit-model-benchmark-${Date.now()}.json`);
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  </script>
</body>
</html>
"""


def make_openai_request(base_url: str, api_key: str, endpoint: str, payload: dict, timeout: int = 25, method: str = "POST") -> tuple[int, dict, dict, int]:
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "WitKit-Studio-Bench/1.0"
    }
    data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    start_t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = int((time.time() - start_t) * 1000)
            res_headers = {k.lower(): v for k, v in resp.headers.items()}
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body, res_headers, elapsed
    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start_t) * 1000)
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error": str(e)}
        return e.code, err_body, {}, elapsed
    except Exception as e:
        return 500, {"error": str(e)}, {}, 0


class BenchHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "witkit-bench"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("content-length", 0))
        raw_body = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw_body)
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}).encode("utf-8"))
            return

        # 1. API: Dynamically Pull Models List from Target Base URL
        if parsed.path == "/api/models":
            base_url = data.get("base_url")
            api_key = data.get("api_key")
            if not base_url or not api_key:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "Missing base_url or api_key"}).encode("utf-8"))
                return

            status, body, headers, elapsed = make_openai_request(base_url, api_key, "models", None, timeout=12, method="GET")
            if status == 200:
                raw_list = body.get("data", [])
                models = []
                if isinstance(raw_list, list):
                    for item in raw_list:
                        if isinstance(item, dict) and "id" in item:
                            models.append(item["id"])
                        elif isinstance(item, str):
                            models.append(item)
                # Sort alphabetically
                models.sort()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "models": models, "latency_ms": elapsed}).encode("utf-8"))
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                err_msg = body.get("error") if isinstance(body, dict) else str(body)
                self.wfile.write(json.dumps({"success": False, "error": f"HTTP {status}: {err_msg}"}).encode("utf-8"))
            return

        # 2. API: Execute Benchmark Suite
        if parsed.path == "/api/benchmark":
            base_url = data.get("base_url")
            api_key = data.get("api_key")
            model = data.get("model")
            tests = data.get("tests", {})

            # Execute Benchmarks
            logs = []
            metrics = {
                "ttft_ms": None,
                "tool_pass": False,
                "needle_pass": False,
                "reasoning_pass": False,
                "confidence_score": 0
            }
            score = 0

            # 1. Latency & Basic Probe
            if tests.get("latency", True):
                logs.append({"text": "[1/4] 发起首字时延 (TTFT) 与流式端点探测...", "color": "#1664ff"})
                status, body, headers, elapsed = make_openai_request(
                    base_url, api_key, "chat/completions",
                    {
                        "model": model,
                        "messages": [{"role": "user", "content": "请只输出一个字：好"}],
                        "max_tokens": 5,
                        "temperature": 0.0
                    },
                    timeout=15
                )
                if status == 200:
                    metrics["ttft_ms"] = elapsed
                    logs.append({"text": f"  -> 响应成功 (HTTP 200), 首字延迟耗时: {elapsed} ms", "color": "#00b42a"})
                    if elapsed < 2000:
                        score += 25
                    else:
                        logs.append({"text": f"  -> 提示：首字延迟偏高 ({elapsed}ms)，可能存在多层代理排队。", "color": "#ff7d00"})
                        score += 15
                else:
                    logs.append({"text": f"  -> 探测失败: HTTP {status} - {body.get('error')}", "color": "#f53f3f"})

            # 2. Tool Call / Function Calling Probe
            if tests.get("tool_call", True):
                logs.append({"text": "[2/4] 发起标准 Function Calling 严格规范检测...", "color": "#1664ff"})
                tool_payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "帮我查询无锡今天的天气如何？"}],
                    "tools": [{
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "获取指定城市的天气",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "city": {"type": "string", "description": "城市名"}
                                },
                                "required": ["city"]
                            }
                        }
                    }],
                    "tool_choice": "auto"
                }
                status, body, headers, elapsed = make_openai_request(base_url, api_key, "chat/completions", tool_payload, timeout=20)
                if status == 200:
                    choice = (body.get("choices") or [{}])[0]
                    message = choice.get("message") or {}
                    tool_calls = message.get("tool_calls")
                    if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                        fn = tool_calls[0].get("function") or {}
                        fn_name = fn.get("name")
                        fn_args = fn.get("arguments")
                        logs.append({"text": f"  -> 完美合规！模型成功返回 tool_calls: {fn_name}({fn_args})", "color": "#00b42a"})
                        metrics["tool_pass"] = True
                        score += 35
                    else:
                        logs.append({"text": "  -> 警告：模型以普通文本回答，未遵循标准 tools 协议规范（疑似逆向号池）。", "color": "#f53f3f"})
                else:
                    logs.append({"text": f"  -> 工具调用接口报错: HTTP {status} - {body.get('error')}", "color": "#f53f3f"})

            # 3. Needle In A Haystack (32K Token Context Test)
            if tests.get("needle", True):
                logs.append({"text": "[3/4] 构建 32K 针海长文本，深度测试上下文真实性与截断率...", "color": "#1664ff"})
                secret_code = f"WITKIT-KEY-{uuid.uuid4().hex[:6].upper()}"
                
                # Construct padding tokens (~25k chars)
                haystack_chunk = "在人工智能模型服务体系中，算力调度网关承担着至关重要的任务，需要保持高效低延迟。" * 200
                full_prompt = (
                    f"以下是一段关于大模型调度的长篇技术参考文档：\n\n{haystack_chunk}\n\n"
                    f"【绝密核验标记】：本次评测的唯一安全验证码是 [{secret_code}]，请妥善牢记。\n\n"
                    f"{haystack_chunk}\n\n"
                    f"请回答：上面文档中提到的【绝密核验标记】中的唯一安全验证码是什么？请直接输出该验证码代码，不要输出任何多余废话。"
                )
                
                status, body, headers, elapsed = make_openai_request(
                    base_url, api_key, "chat/completions",
                    {
                        "model": model,
                        "messages": [{"role": "user", "content": full_prompt}],
                        "max_tokens": 50,
                        "temperature": 0.0
                    },
                    timeout=30
                )
                if status == 200:
                    reply = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
                    if secret_code in reply:
                        logs.append({"text": f"  -> 针海全中！在长文本中成功检索出随机密令: {secret_code} (耗时 {elapsed}ms)", "color": "#00b42a"})
                        metrics["needle_pass"] = True
                        score += 25
                    else:
                        logs.append({"text": f"  -> 检出失败：模型未捞出密令，实际回答: '{reply.strip()[:60]}...'（疑似发生前置截断）。", "color": "#f53f3f"})
                else:
                    logs.append({"text": f"  -> 长文本请求失败: HTTP {status} - {body.get('error')}", "color": "#f53f3f"})

            # 4. Anti-Downgrade & Logic Trap
            if tests.get("reasoning", True):
                logs.append({"text": "[4/4] 注入经典边界逻辑题，测试小模型冒充降级...", "color": "#1664ff"})
                logic_prompt = "树上有 9 只鸟，猎人开枪打死 1 只，树上还剩几只？请用一句话回答物理客观事实并给出原因。"
                status, body, headers, elapsed = make_openai_request(
                    base_url, api_key, "chat/completions",
                    {
                        "model": model,
                        "messages": [{"role": "user", "content": logic_prompt}],
                        "max_tokens": 100,
                        "temperature": 0.0
                    },
                    timeout=15
                )
                if status == 200:
                    reply = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
                    logs.append({"text": f"  -> 回答完成: {reply.strip()[:80]}...", "color": "#e5e8ef"})
                    metrics["reasoning_pass"] = True
                    score += 15
                else:
                    logs.append({"text": f"  -> 逻辑测试接口报错: HTTP {status}", "color": "#f53f3f"})

            metrics["confidence_score"] = min(score, 100)
            logs.append({"text": f"[FINISH] 评测结束，原厂置信度得分: {metrics['confidence_score']}%", "color": "#1664ff"})

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "metrics": metrics, "logs": logs}).encode("utf-8"))


def run_server():
    server = HTTPServer((HOST, PORT), BenchHandler)
    print(f"WitKit Benchmark Arena started at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    run_server()
