"""Main console page (single-file UI)."""

PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WitKit Studio | 大模型真实性与质量评测中枢</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
body{font-family:system-ui,-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.light-pass{background:#16a34a}.light-warn{background:#d97706}.light-fail{background:#dc2626}.light-info{background:#6b7280}
.badge{padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;color:#fff}
.badge-pass{background:#16a34a}.badge-warn{background:#d97706}.badge-fail{background:#dc2626}.badge-info{background:#6b7280}
#progressBox pre{max-height:220px;overflow:auto}
details pre{max-height:260px;overflow:auto}
input,select{outline:none}
</style>
</head>
<body class="bg-slate-100 text-slate-800">
<div class="max-w-5xl mx-auto px-4 py-8">

<header class="mb-8">
  <div class="flex items-center justify-between flex-wrap gap-3">
    <div>
      <h1 class="text-2xl font-bold">WitKit Studio 评测中心 <span class="text-xs font-normal text-slate-400 align-middle">v2</span></h1>
      <p class="text-sm text-slate-500 mt-1">大模型质量、合规与真实性综合探针 · 15 项测试 · 5 维评分</p>
    </div>
    <div class="text-sm flex gap-4">
      <a href="/criteria" class="text-blue-600 hover:underline">判定标准与方法论</a>
      <a href="https://witkit.zone" class="text-slate-500 hover:underline">主站</a>
      <a href="https://analytics.witkit.zone" class="text-slate-500 hover:underline">监控</a>
    </div>
  </div>
</header>

<section class="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
  <h2 class="font-semibold mb-4">待测服务与模型</h2>
  <div class="grid md:grid-cols-2 gap-4">
    <div>
      <label class="text-xs text-slate-500">API 接入基地址（兼容 OpenAI 协议，结尾带 /v1）</label>
      <input id="baseUrl" class="w-full mt-1 px-3 py-2 rounded-lg border border-slate-300 focus:border-blue-500" placeholder="https://api.example.com/v1">
    </div>
    <div>
      <label class="text-xs text-slate-500">API Key（仅用于本次测试，不存储）</label>
      <input id="apiKey" type="password" class="w-full mt-1 px-3 py-2 rounded-lg border border-slate-300 focus:border-blue-500" placeholder="sk-...">
    </div>
  </div>
  <div class="grid md:grid-cols-2 gap-4 mt-4">
    <div>
      <label class="text-xs text-slate-500">待测模型</label>
      <div class="flex gap-2 mt-1">
        <select id="model" class="flex-1 px-3 py-2 rounded-lg border border-slate-300 bg-white"><option value="">-- 先拉取模型列表 --</option></select>
        <button id="pullBtn" class="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm hover:bg-slate-700">自动拉取</button>
      </div>
      <input id="modelManual" class="w-full mt-2 px-3 py-2 rounded-lg border border-slate-300 text-sm" placeholder="或手动输入模型名">
    </div>
    <div class="flex items-end gap-2">
      <button id="quickBtn" class="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-500">快速体检（7 项·约3分钟）</button>
      <button id="deepBtn" class="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-700">深度全检（15 项·约12分钟）</button>
    </div>
  </div>
  <div id="pullMsg" class="text-xs text-slate-500 mt-2"></div>
</section>

<section class="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
  <div class="flex items-center justify-between mb-3">
    <h2 class="font-semibold">评测专项</h2>
    <label class="text-sm text-slate-500"><input type="checkbox" id="selectAll" checked class="mr-1 align-middle">全选</label>
  </div>
  <div id="testList" class="grid md:grid-cols-2 gap-x-6 gap-y-2 text-sm"></div>
</section>

<section id="progressSection" class="bg-white rounded-2xl border border-slate-200 p-6 mb-6 hidden" >
  <div class="flex items-center justify-between">
    <h2 class="font-semibold">实时进度</h2>
    <span id="elapsed" class="text-sm text-slate-500"></span>
  </div>
  <div id="progressBox" class="mt-3 text-sm"><pre class="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs leading-5">准备中...</pre></div>
</section>

<section id="resultSection" class="hidden">
  <div class="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
    <div class="flex items-start justify-between flex-wrap gap-4">
      <div>
        <div class="text-xs text-slate-500">综合评分</div>
        <div id="compScore" class="text-5xl font-bold">-</div>
        <div id="compGrade" class="mt-1"></div>
      </div>
      <div id="radarBox" class="w-72"></div>
    </div>
    <ul id="verdictList" class="mt-4 space-y-2 text-sm"></ul>
    <div class="mt-5 pt-4 border-t border-slate-100 flex items-center gap-3 text-sm">
      <span class="text-slate-500">分享报告：</span>
      <a id="reportLink" href="#" target="_blank" class="text-blue-600 hover:underline break-all"></a>
      <button id="copyLink" class="px-3 py-1 rounded-lg border border-slate-300 text-xs hover:bg-slate-50">复制</button>
    </div>
  </div>
  <div id="dimCards" class="grid md:grid-cols-2 gap-4 mb-6"></div>
  <div id="detailCards"></div>
</section>

<section class="bg-white rounded-2xl border border-slate-200 p-6 mb-6">
  <h2 class="font-semibold mb-3">历史评测</h2>
  <div id="historyBox" class="text-sm text-slate-500">加载中...</div>
</section>

<footer class="text-xs text-slate-400 leading-6 pb-10">
  © 2026 WitKit Studio · 判定规则全部公开于 <a class="text-blue-500" href="/criteria">/criteria</a> · 结果为规则化自动判定，仅代表测试时点接入点表现 · 不存储 API Key<br>
  <a href="https://beian.miit.gov.cn/" class="text-slate-400 hover:underline">苏ICP备2026003689号-2</a> · witkit.zone
</footer>
</div>

<script>
const DIM_NAMES={authenticity:"真实性",capability:"能力",performance:"性能",stability:"稳定性",compliance:"合规"};
const LIGHT_TXT={pass:"通过",warn:"可疑",fail:"未通过",info:"参考"};
let META=[],timer=null;

async function loadMeta(){
  const r=await fetch("/api/meta");const j=await r.json();
  META=j.tests;renderTests();
}
function renderTests(){
  const box=document.getElementById("testList");
  const byDim={};
  META.forEach(t=>{(byDim[t.dim]=byDim[t.dim]||[]).push(t)});
  box.innerHTML=Object.entries(byDim).map(([dim,ts])=>(
    '<div class="md:col-span-2 font-medium text-slate-600 mt-1">'+DIM_NAMES[dim]+'（'+ts.length+' 项）</div>'+
    ts.map(t=>'<label class="flex items-start gap-2 py-1"><input type="checkbox" class="testCb mt-1" value="'+t.tid+'" checked>'+
      '<span><span class="font-medium">'+t.name_zh+'</span>'+
      '<span class="text-xs text-slate-400 ml-1">~'+t.est_s+'s'+(t.fast?' · 快速项':'')+'</span>'+
      '<div class="text-xs text-slate-500">'+t.desc_zh+'</div></span></label>').join('')
  )).join('');
  document.getElementById("selectAll").onchange=e=>{document.querySelectorAll(".testCb").forEach(c=>c.checked=e.target.checked)};
}
function selectedTests(){return [...document.querySelectorAll(".testCb:checked")].map(c=>c.value)}
function setMode(fastOnly){
  document.querySelectorAll(".testCb").forEach(c=>{const m=META.find(t=>t.tid===c.value);c.checked=fastOnly?m.fast:true});
  document.getElementById("selectAll").checked=!fastOnly;
}

document.getElementById("pullBtn").onclick=async()=>{
  const base=document.getElementById("baseUrl").value.trim(),key=document.getElementById("apiKey").value.trim();
  const msg=document.getElementById("pullMsg");
  if(!base||!key){msg.textContent="请先填写基地址与 API Key";return}
  msg.textContent="拉取中...";
  try{
    const r=await fetch("/api/models",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({base_url:base,api_key:key})});
    const j=await r.json();
    if(!j.success){msg.textContent="拉取失败："+(j.error||r.status);return}
    const sel=document.getElementById("model");
    sel.innerHTML=(j.models||[]).map(m=>'<option value="'+m+'">'+m+'</option>').join("")||'<option value="">（空列表，请手动输入）</option>';
    msg.textContent="已拉取 "+(j.models||[]).length+" 个模型";
  }catch(e){msg.textContent="拉取异常："+e}
};
function currentModel(){return document.getElementById("modelManual").value.trim()||document.getElementById("model").value}
document.getElementById("quickBtn").onclick=()=>{setMode(true);startRun()};
document.getElementById("deepBtn").onclick=()=>{setMode(false);startRun()};
document.getElementById("copyLink").onclick=()=>{const a=document.getElementById("reportLink");navigator.clipboard.writeText(a.href);};

async function loadHistory(){
  const r=await fetch("/api/history");const j=await r.json();
  const box=document.getElementById("historyBox");
  if(!j.length){box.textContent="暂无记录";return}
  box.innerHTML='<table class="w-full text-sm"><tr class="text-left text-slate-400"><th>时间</th><th>接入点</th><th>模型</th><th>评分</th><th></th></tr>'+
    j.map(h=>'<tr class="border-t border-slate-100"><td class="py-1.5">'+h.created+'</td><td>'+h.host+'</td><td>'+h.model+'</td>'+
    '<td><b>'+h.composite+'</b> <span class="text-xs text-slate-400">'+h.grade+'</span></td>'+
    '<td><a class="text-blue-600" href="/report/'+h.id+'" target="_blank">报告</a></td></tr>').join("")+'</table>';
}

function radarSvg(dims){
  const size=280,cx=size/2,cy=size/2,R=size/2-46,n=dims.length;
  const pt=(i,f)=>{const a=-Math.PI/2+2*Math.PI*i/n;return[cx+R*f*Math.cos(a),cy+R*f*Math.sin(a)]};
  let s='<svg viewBox="0 0 '+size+' '+size+'" width="100%">';
  [0.25,0.5,0.75,1].forEach(f=>{s+='<polygon fill="none" stroke="#e5e7eb" points="'+dims.map((_,i)=>pt(i,f).map(v=>v.toFixed(1)).join(",")).join(" ")+'"/>'});
  dims.forEach((_,i)=>{const[x,y]=pt(i,1);s+='<line x1="'+cx+'" y1="'+cy+'" x2="'+x+'" y2="'+y+'" stroke="#e5e7eb"/>'});
  const poly=dims.map((d,i)=>pt(i,Math.max(.03,Math.min(1,(d.score||0)/100))).map(v=>v.toFixed(1)).join(",")).join(" ");
  const bad=dims.some(d=>d.light==="fail"),warn=dims.some(d=>d.light==="warn"),color=bad?"#dc2626":warn?"#d97706":"#2563eb";
  s+='<polygon points="'+poly+'" fill="'+color+'" fill-opacity="0.25" stroke="'+color+'" stroke-width="2"/>';
  dims.forEach((d,i)=>{const[x,y]=pt(i,1.28);const anc=Math.cos(-Math.PI/2+2*Math.PI*i/n)>0.3?"start":Math.cos(-Math.PI/2+2*Math.PI*i/n)<-0.3?"end":"middle";
    s+='<text x="'+x+'" y="'+(y+4)+'" text-anchor="'+anc+'" font-size="13" fill="#374151">'+d.name+(d.score!=null?" "+d.score:"")+'</text>'});
  return s+'</svg>';
}

async function startRun(){
  const base=document.getElementById("baseUrl").value.trim(),key=document.getElementById("apiKey").value.trim(),model=currentModel();
  if(!base||!key||!model){alert("请填写基地址、API Key 与模型");return}
  const tests=selectedTests();
  if(!tests.length){alert("请至少选择一项测试");return}
  document.getElementById("progressSection").classList.remove("hidden");
  document.getElementById("resultSection").classList.add("hidden");
  const pre=document.querySelector("#progressBox pre");pre.textContent="";
  const t0=Date.now();
  timer=setInterval(()=>{document.getElementById("elapsed").textContent=((Date.now()-t0)/1000).toFixed(0)+"s"},500);
  try{
    const resp=await fetch("/api/benchmark",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({base_url:base,api_key:key,model:model,tests:tests})});
    const reader=resp.body.getReader(),dec=new TextDecoder();let buf="";
    while(true){
      const{done,value}=await reader.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split("\n");buf=lines.pop();
      for(const line of lines){if(line.trim())handleEvent(JSON.parse(line))}
    }
  }catch(e){pre.textContent+=("\n[连接中断] "+e)}
  clearInterval(timer);
  loadHistory();
}

function handleEvent(ev){
  const pre=document.querySelector("#progressBox pre");
  if(ev.type==="start"){pre.textContent+="▶ 共 "+ev.tests.length+" 项开始\n"}
  else if(ev.type==="progress"){pre.textContent+="· "+ev.name_zh+" ...\n";pre.scrollTop=pre.scrollHeight}
  else if(ev.type==="test"){
    const r=ev.result;
    pre.textContent+="  "+(r.light==="pass"?"✅":r.light==="warn"?"⚠️":r.light==="fail"?"❌":"ℹ️")+" "+r.name_zh+" — "+r.summary_zh+" ("+r.elapsed_s+"s)\n";
    pre.scrollTop=pre.scrollHeight;
  }
  else if(ev.type==="done"){renderResult(ev.run)}
}

function renderResult(run){
  const sec=document.getElementById("resultSection");sec.classList.remove("hidden");
  const comp=run.composite;
  const bad=comp.verdict.some(v=>v[1]==="fail");
  document.getElementById("compScore").textContent=comp.composite;
  document.getElementById("compScore").style.color=comp.composite>=75?"#16a34a":comp.composite>=60?"#d97706":"#dc2626";
  document.getElementById("compGrade").innerHTML='<span class="badge badge-'+(bad?"fail":comp.composite>=60?"pass":"warn")+'">'+comp.grade+'</span>';
  const dims=Object.entries(comp.dims).map(([k,d])=>({name:d.name_zh,score:d.score,light:d.light}));
  document.getElementById("radarBox").innerHTML=radarSvg(dims);
  document.getElementById("verdictList").innerHTML=comp.verdict.map(([k,l,t])=>
    '<li><span class="dot light-'+l+'"></span>'+t+'</li>').join("");
  if(run.report_id){
    const url=location.origin+"/report/"+run.report_id;
    const a=document.getElementById("reportLink");a.href=url;a.textContent=url;
  }
  const dimCards=document.getElementById("dimCards");
  dimCards.innerHTML=Object.entries(comp.dims).map(([k,d])=>{
    const tests=(run.tests||{});const items=Object.entries(tests).filter(([tid,t])=>t.dim===k);
    return '<div class="bg-white rounded-2xl border border-slate-200 p-5"><div class="flex items-center justify-between">'+
    '<h3 class="font-semibold">'+d.name_zh+'<span class="text-xs text-slate-400 ml-2">权重 '+Math.round(d.weight*100)+'%</span></h3>'+
    '<span class="badge badge-'+d.light+'">'+(d.score==null?"-":d.score+" 分")+'</span></div>'+
    '<div class="mt-3 space-y-2 text-sm">'+items.map(([tid,t])=>
      '<div class="flex items-start gap-2"><span class="dot light-'+t.light+'" style="margin-top:6px"></span>'+
      '<div><b>'+t.name_zh+'</b> <span class="text-xs text-slate-400">'+LIGHT_TXT[t.light]+'</span>'+
      '<div class="text-xs text-slate-600">'+t.summary_zh+'</div></div></div>').join("")+'</div></div>';
  }).join("");
  const details=document.getElementById("detailCards");
  details.innerHTML='<div class="bg-white rounded-2xl border border-slate-200 p-6"><details><summary class="cursor-pointer text-sm text-slate-500">原始数据（JSON）</summary>'+
  '<pre class="mt-3 bg-slate-50 border rounded-lg p-3 text-xs overflow-auto">'+JSON.stringify(run,null,1).replace(/</g,"&lt;")+'</pre></details></div>';
  sec.scrollIntoView({behavior:"smooth"});
}

loadMeta();loadHistory();
</script>
</body>
</html>
"""
