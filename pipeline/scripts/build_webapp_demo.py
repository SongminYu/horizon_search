"""Generate webapp_demo.html: a self-contained interactive demo of the
EU-funding explorer, with real aggregate data embedded.

Reads /tmp/demo_agg.json + /tmp/demo_topics.json (built by the aggregation
snippet); writes webapp_demo.html.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
agg = json.load(open("/tmp/demo_agg.json"))
topics = json.load(open("/tmp/demo_topics.json"))

HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EU 能源环境资助数据库 — 交互 Demo</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
:root{--blue:#2c5d99;--blue-bg:#eaf2fb;--green:#2f6b3d;--green-bg:#e8f1ea;--orange:#b66a1f;--orange-bg:#fbf0e3;--purple:#6c3a85;--purple-bg:#f3ecf6;--red:#b03a2e;--line:#e2e2e2;--ink:#1c1c1e;--muted:#777;}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);background:#f7f8fa}
header{background:linear-gradient(135deg,#1d3f68 0%,#2c5d99 60%,#3a77c2 100%);color:#fff;padding:1.4em 2em 1.1em}
header h1{font-size:1.45em;font-weight:700;letter-spacing:.02em}
header .sub{opacity:.85;font-size:.85em;margin-top:.3em}
.kpis{display:flex;gap:1em;flex-wrap:wrap;margin-top:1em}
.kpi{background:rgba(255,255,255,.13);border:1px solid rgba(255,255,255,.25);border-radius:10px;padding:.5em 1em;min-width:120px}
.kpi .v{font-size:1.25em;font-weight:700}
.kpi .k{font-size:.72em;opacity:.85}
nav{display:flex;gap:.4em;padding:.7em 2em;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:9;flex-wrap:wrap}
nav button{border:1px solid var(--line);background:#fff;border-radius:18px;padding:.42em 1.1em;font-size:.92em;cursor:pointer;color:#444}
nav button.on{background:var(--blue);border-color:var(--blue);color:#fff;font-weight:600}
main{padding:1.4em 2em;max-width:1340px;margin:0 auto}
.view{display:none}.view.on{display:block}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1.2em}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:1em 1.2em;margin-bottom:1.2em;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.card h3{font-size:1em;margin-bottom:.6em;color:var(--blue)}
.chart{width:100%;height:380px}
.chart.tall{height:460px}
.chips{display:flex;gap:.4em;flex-wrap:wrap;margin:.4em 0 .8em}
.chip{border:1px solid var(--line);background:#fff;border-radius:14px;padding:.25em .8em;font-size:.82em;cursor:pointer;color:#444}
.chip.on{background:var(--green);border-color:var(--green);color:#fff}
input[type=text]{width:100%;padding:.6em .9em;border:1.5px solid var(--line);border-radius:10px;font-size:.95em;outline:none}
input[type=text]:focus{border-color:var(--blue)}
table{width:100%;border-collapse:collapse;font-size:.84em}
th{position:sticky;top:0;background:var(--blue);color:#fff;text-align:left;padding:.45em .6em;cursor:pointer;white-space:nowrap}
td{border-bottom:1px solid #efefef;padding:.4em .6em;vertical-align:top}
tr:hover td{background:var(--blue-bg)}
td.num,th.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.tag{display:inline-block;font-size:.76em;border-radius:8px;padding:.05em .5em;font-weight:600}
.scroll{max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:8px}
.muted{color:var(--muted);font-size:.82em}
.banner{background:var(--orange-bg);border-left:4px solid var(--orange);padding:.7em 1em;border-radius:6px;font-size:.88em;margin-bottom:1.2em}
a{color:var(--blue);text-decoration:none}
.org-head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:.5em}
.backlink{cursor:pointer;color:var(--blue);font-size:.86em}
footer{padding:2em;color:var(--muted);font-size:.8em;text-align:center}
@media (max-width:900px){.grid2{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>EU 能源·环境·气候 研究资助数据库 <span style="font-size:.6em;font-weight:400;opacity:.8">DEMO</span></h1>
  <div class="sub">Horizon 2020 + Horizon Europe + Missions + JU/JTI + LIFE + Innovation Fund ｜ 2014-2026 ｜ 数据：CORDIS / F&T Portal（已签约口径）</div>
  <div class="kpis">
    <div class="kpi"><div class="v">12</div><div class="k">数据板块</div></div>
    <div class="kpi"><div class="v">3,677</div><div class="k">Topics</div></div>
    <div class="kpi"><div class="v">7,601</div><div class="k">Projects</div></div>
    <div class="kpi"><div class="v">97,102</div><div class="k">机构×项目参与</div></div>
    <div class="kpi"><div class="v">28,802</div><div class="k">机构（去重）</div></div>
    <div class="kpi"><div class="v">€35.2B</div><div class="k">已签约 EU 资助</div></div>
  </div>
</header>
<nav>
  <button data-v="overview" class="on">总览</button>
  <button data-v="prog">板块浏览</button>
  <button data-v="search">跨板块主题检索</button>
  <button data-v="org">机构查询</button>
  <button data-v="about">完整版设计</button>
</nav>
<main>
<div class="banner">这是设计确认用的 <b>demo</b>：图表与检索背后是<b>真实数据</b>（topic 级全量索引 3,454 条 + 机构 top 120），但项目级/参与方级钻取在 demo 中只到 topic 层。完整版会把全部 11 万行装进浏览器内 DuckDB，钻到任意粒度（见"完整版设计"页）。</div>

<!-- ===== 总览 ===== -->
<section class="view on" id="v-overview">
  <div class="card"><h3>资金流向：框架期 → 板块 → Destination（已签约 EU 资助，点击节点高亮路径）</h3><div id="sankey" class="chart tall"></div></div>
  <div class="grid2">
    <div class="card"><h3>年度趋势：各板块已签约资助（按 topic 所属 call 年份）</h3><div id="area" class="chart"></div></div>
    <div class="card"><h3>两个框架期的板块体量对比（点击柱条跳到该板块）</h3><div id="progbar" class="chart"></div></div>
  </div>
</section>

<!-- ===== 板块浏览 ===== -->
<section class="view" id="v-prog">
  <div class="chips" id="progchips"></div>
  <div class="grid2">
    <div class="card"><h3 id="tm-title">Destination 结构（面积 = 已签约资助，点击筛选下表）</h3><div id="treemap" class="chart"></div></div>
    <div class="card"><h3>年度节奏（点击年份筛选下表）</h3><div id="progyear" class="chart"></div></div>
  </div>
  <div class="card">
    <div class="org-head"><h3 id="tt-title">Topics</h3><span class="backlink" id="clearfilter" style="display:none">✕ 清除筛选</span></div>
    <input type="text" id="topicfilter" placeholder="在本板块内过滤 topic（标题/编号关键词）…">
    <div class="scroll" style="margin-top:.6em"><table id="topictable"></table></div>
    <div class="muted" id="tt-note" style="margin-top:.4em"></div>
  </div>
</section>

<!-- ===== 跨板块检索 ===== -->
<section class="view" id="v-search">
  <div class="card">
    <h3>跨板块主题检索 — 一个关键词，看全部 12 个板块、2014-2026 的资助轨迹</h3>
    <input type="text" id="q" placeholder="输入关键词（英文，空格 = AND；如 hydrogen storage）…">
    <div class="chips" id="presets"></div>
  </div>
  <div class="grid2">
    <div class="card"><h3>命中资金的时间分布（按板块堆叠）</h3><div id="qchart" class="chart"></div></div>
    <div class="card"><h3>命中板块分布</h3><div id="qpie" class="chart"></div></div>
  </div>
  <div class="card"><h3 id="qcount">检索结果</h3><div class="scroll"><table id="qtable"></table></div></div>
</section>

<!-- ===== 机构 ===== -->
<section class="view" id="v-org">
  <div class="card">
    <h3>机构查询（demo 内置全库资助额 top 120；完整版可查全部 28,802 家）</h3>
    <input type="text" id="orgq" placeholder="机构名称关键词（如 FRAUNHOFER / WAGENINGEN / AIRBUS）…">
  </div>
  <div id="orgprofile" class="card" style="display:none">
    <div class="org-head"><h3 id="op-name"></h3><span class="backlink" id="op-back">← 返回列表</span></div>
    <div class="muted" id="op-meta"></div>
    <div id="orgbar" class="chart" style="height:300px"></div>
  </div>
  <div class="card" id="orglistcard"><div class="scroll"><table id="orgtable"></table></div></div>
</section>

<!-- ===== 完整版设计 ===== -->
<section class="view" id="v-about">
  <div class="card"><h3>完整版架构（纯静态，无需服务器）</h3>
  <p style="font-size:.92em;line-height:1.8">
  <b>数据层</b>：脚本把 12 个 xlsx 导出为 Parquet（topics 3,677 / projects 7,601 / participants 97,102 / organisations 28,802，合计约 11 万行、压缩后 ~15MB）。<br>
  <b>查询引擎</b>：浏览器内 <b>DuckDB-WASM</b>，页面打开时按板块懒加载 Parquet——任何花式查询都是真 SQL，毫秒级，支持任意维度组合（板块 × destination × 年份 × 类型 × 国家 × 机构类型 × 关键词）。<br>
  <b>前端</b>：本 demo 的四个功能区扩展为：① 总览（Sankey/趋势/对比）② 板块仪表盘（每板块 destination 钻取：topic → project → participants 三级下钻）③ 跨板块检索（关键词 + 结构化条件混合查询，主题资金轨迹横跨 H2020→HE）④ 机构页（任意机构的全部项目、资金时间线、合作网络图、国别/类型对比）⑤ 任意查询结果一键导出 CSV。<br>
  <b>部署</b>：单目录静态文件，<code>python -m http.server</code> 本地用，或直接丢 GitHub Pages。</p></div>
  <div class="card"><h3>确认点</h3>
  <p style="font-size:.92em;line-height:1.8">1️⃣ 视觉与交互方向（本 demo 的布局/配色/图表类型）是否 OK？<br>
  2️⃣ 四个功能区之外还想要什么（如：国家维度页？两框架期承接对比页？PPT 导图模式？）<br>
  3️⃣ 机构合作网络图（force graph）做不做（最炫但最费内存的部分）？<br>
  4️⃣ 默认口径：已签约资助（当前）vs 指示性预算切换开关？</p></div>
</section>
</main>
<footer>EU Funding Explorer · demo · 数据截至 2026-06 CORDIS 快照 · 已签约口径</footer>

<script>
const AGG = __AGG__;
const ORGS = __ORGS__;
const TOPICS = __TOPICS__;
const PROGS = ['CL5','CL6','MISS','JU','CL4','H2020-SC3','H2020-SC4','H2020-SC2','H2020-SC5','H2020-JTI'];
const PCOLOR = {'CL5':'#2c5d99','CL6':'#2f6b3d','MISS':'#6c3a85','JU':'#b66a1f','CL4':'#5a7d9a',
 'H2020-SC3':'#7fa6d9','H2020-SC4':'#9db8d9','H2020-SC2':'#7fb08a','H2020-SC5':'#a4c4ab','H2020-JTI':'#d9a45f','LIFE':'#4d8c57','INNOVFUND':'#8a5fb0'};
const fmtM = m => m>=1000 ? '€'+(m/1000).toFixed(2)+'B' : '€'+Math.round(m)+'M';

/* nav */
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('nav button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('on'));
  document.getElementById('v-'+b.dataset.v).classList.add('on');
  window.dispatchEvent(new Event('resize'));
});

/* ---------- overview ---------- */
(function(){
  const byProg={}, byDest={};
  AGG.forEach(r=>{
    byProg[r.prog]=(byProg[r.prog]||0)+r.eur_m;
    const k=r.prog+'›'+r.dest;
    byDest[k]=(byDest[k]||0)+r.eur_m;
  });
  const nodes=[{name:'Horizon 2020'},{name:'Horizon Europe'}];
  const links=[];
  PROGS.forEach(p=>{
    nodes.push({name:p,itemStyle:{color:PCOLOR[p]}});
    links.push({source:p.startsWith('H2020')?'Horizon 2020':'Horizon Europe',target:p,value:+(byProg[p]||0).toFixed(1)});
  });
  const topDest = Object.entries(byDest).filter(([k,v])=>v>150).sort((a,b)=>b[1]-a[1]).slice(0,28);
  topDest.forEach(([k,v])=>{
    const [p,d]=k.split('›'); const nm=d+' ('+p+')';
    nodes.push({name:nm,itemStyle:{color:PCOLOR[p]}});
    links.push({source:p,target:nm,value:+v.toFixed(1)});
  });
  echarts.init(document.getElementById('sankey')).setOption({
    tooltip:{trigger:'item',formatter:x=>x.dataType==='edge'?x.data.source+' → '+x.data.target+'<br><b>'+fmtM(x.data.value)+'</b>':x.name},
    series:[{type:'sankey',data:nodes,links:links,left:10,right:230,nodeWidth:14,nodeGap:7,
      emphasis:{focus:'adjacency'},lineStyle:{color:'gradient',opacity:.35},label:{fontSize:11}}]});

  const years=[...new Set(AGG.map(r=>r.year))].filter(y=>y>='2014'&&y<='2026').sort();
  const series=PROGS.map(p=>({name:p,type:'line',stack:'a',areaStyle:{opacity:.55},showSymbol:false,lineStyle:{width:1},
    color:PCOLOR[p],data:years.map(y=>+AGG.filter(r=>r.prog===p&&r.year===y).reduce((s,r)=>s+r.eur_m,0).toFixed(1))}));
  echarts.init(document.getElementById('area')).setOption({
    tooltip:{trigger:'axis',valueFormatter:v=>fmtM(v)},legend:{type:'scroll',textStyle:{fontSize:10}},
    grid:{left:60,right:20,top:40,bottom:25},xAxis:{type:'category',data:years},yAxis:{type:'value',name:'€M'},series});

  const pb=echarts.init(document.getElementById('progbar'));
  const order=[...PROGS].sort((a,b)=>byProg[b]-byProg[a]);
  pb.setOption({tooltip:{valueFormatter:v=>fmtM(v)},grid:{left:100,right:40,top:10,bottom:25},
    xAxis:{type:'value',name:'€M'},yAxis:{type:'category',data:order.reverse()},
    series:[{type:'bar',data:order.map(p=>({value:+byProg[p].toFixed(0),itemStyle:{color:PCOLOR[p]}})),label:{show:true,position:'right',formatter:x=>fmtM(x.value),fontSize:10}}]});
  pb.on('click',x=>{const p=x.name;document.querySelector('nav button[data-v=prog]').click();selectProg(p);});
})();

/* ---------- programme view ---------- */
let curProg='CL5', fDest=null, fYear=null;
const chipbox=document.getElementById('progchips');
PROGS.forEach(p=>{const c=document.createElement('span');c.className='chip'+(p===curProg?' on':'');c.textContent=p;
  c.onclick=()=>selectProg(p);chipbox.appendChild(c);});
const tmChart=echarts.init(document.getElementById('treemap'));
const pyChart=echarts.init(document.getElementById('progyear'));
function selectProg(p){curProg=p;fDest=null;fYear=null;
  [...chipbox.children].forEach(c=>c.classList.toggle('on',c.textContent===p));
  const rows=AGG.filter(r=>r.prog===p);
  const dest={};rows.forEach(r=>dest[r.dest]=(dest[r.dest]||0)+r.eur_m);
  tmChart.setOption({tooltip:{formatter:x=>x.name+'<br><b>'+fmtM(x.value)+'</b>'},
    series:[{type:'treemap',roam:false,nodeClick:false,breadcrumb:{show:false},
      label:{formatter:x=>x.name+'\n'+fmtM(x.value),fontSize:11},
      data:Object.entries(dest).map(([d,v])=>({name:d,value:+v.toFixed(1)})),
      levels:[{color:['#2c5d99','#2f6b3d','#b66a1f','#6c3a85','#b03a2e','#5a7d9a','#4d8c57','#8a5fb0','#777']}]}]},true);
  const ys=[...new Set(rows.map(r=>r.year))].sort();
  pyChart.setOption({tooltip:{valueFormatter:v=>fmtM(v)},grid:{left:60,right:20,top:20,bottom:25},
    xAxis:{type:'category',data:ys},yAxis:{type:'value',name:'€M'},
    series:[{type:'bar',color:PCOLOR[p],data:ys.map(y=>+rows.filter(r=>r.year===y).reduce((s,r)=>s+r.eur_m,0).toFixed(1))}]},true);
  renderTopics();
}
tmChart.on('click',x=>{fDest=x.name;renderTopics();});
pyChart.on('click',x=>{fYear=x.name;renderTopics();});
document.getElementById('clearfilter').onclick=()=>{fDest=null;fYear=null;document.getElementById('topicfilter').value='';renderTopics();};
document.getElementById('topicfilter').oninput=()=>renderTopics();
function renderTopics(){
  const q=document.getElementById('topicfilter').value.trim().toLowerCase();
  let rows=TOPICS.filter(t=>t.prog===curProg);
  if(fDest)rows=rows.filter(t=>t.dest===fDest);
  if(fYear)rows=rows.filter(t=>t.year===fYear);
  if(q)rows=rows.filter(t=>(t.title+' '+t.id).toLowerCase().includes(q));
  rows.sort((a,b)=>b.m-a.m);
  document.getElementById('clearfilter').style.display=(fDest||fYear)?'inline':'none';
  document.getElementById('tt-title').textContent=`Topics — ${curProg}${fDest?' › '+fDest:''}${fYear?' › '+fYear:''}`;
  const shown=rows.slice(0,250);
  document.getElementById('topictable').innerHTML=
    '<tr><th>Topic ID</th><th>标题</th><th>Dest</th><th class="num">年</th><th class="num">项目</th><th class="num">已签约</th></tr>'+
    shown.map(t=>`<tr><td><a href="https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/${t.id.toLowerCase()}" target="_blank">${t.id}</a></td><td>${t.title}</td><td>${t.dest}</td><td class="num">${t.year}</td><td class="num">${t.p}</td><td class="num">${t.m?fmtM(t.m):'—'}</td></tr>`).join('');
  document.getElementById('tt-note').textContent=`${rows.length} 个 topic（显示前 ${shown.length}；完整版点击行可下钻到项目和参与机构）`;
}
selectProg('CL5');

/* ---------- cross search ---------- */
const qChart=echarts.init(document.getElementById('qchart'));
const qPie=echarts.init(document.getElementById('qpie'));
const PRESETS=['hydrogen','battery','offshore wind','photovoltaic','carbon capture','biodiversity','soil','circular economy','climate adaptation','aviation'];
const pb2=document.getElementById('presets');
PRESETS.forEach(p=>{const c=document.createElement('span');c.className='chip';c.textContent=p;
  c.onclick=()=>{document.getElementById('q').value=p;doSearch();};pb2.appendChild(c);});
document.getElementById('q').oninput=()=>doSearch();
function doSearch(){
  const terms=document.getElementById('q').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if(!terms.length){document.getElementById('qcount').textContent='检索结果';document.getElementById('qtable').innerHTML='';qChart.clear();qPie.clear();return;}
  const hits=TOPICS.filter(t=>{const s=(t.title+' '+t.id).toLowerCase();return terms.every(x=>s.includes(x));});
  const money=hits.reduce((s,t)=>s+t.m,0);
  document.getElementById('qcount').textContent=`检索结果：${hits.length} 个 topic ｜ 已签约合计 ${fmtM(money)}（demo 只搜 topic 层；完整版同时搜项目摘要与机构）`;
  const years=[...new Set(hits.map(t=>t.year))].sort();
  const progs=[...new Set(hits.map(t=>t.prog))];
  qChart.setOption({tooltip:{trigger:'axis',valueFormatter:v=>fmtM(v||0)},legend:{textStyle:{fontSize:10}},
    grid:{left:60,right:20,top:40,bottom:25},xAxis:{type:'category',data:years},yAxis:{type:'value',name:'€M'},
    series:progs.map(p=>({name:p,type:'bar',stack:'a',color:PCOLOR[p],
      data:years.map(y=>+hits.filter(t=>t.prog===p&&t.year===y).reduce((s,t)=>s+t.m,0).toFixed(1))}))},true);
  qPie.setOption({tooltip:{formatter:x=>x.name+': '+fmtM(x.value)+' ('+x.percent+'%)'},
    series:[{type:'pie',radius:['35%','68%'],label:{fontSize:10},
      data:progs.map(p=>({name:p,value:+hits.filter(t=>t.prog===p).reduce((s,t)=>s+t.m,0).toFixed(1),itemStyle:{color:PCOLOR[p]}}))}]},true);
  hits.sort((a,b)=>b.m-a.m);
  document.getElementById('qtable').innerHTML=
    '<tr><th>板块</th><th>Topic ID</th><th>标题</th><th class="num">年</th><th class="num">已签约</th></tr>'+
    hits.slice(0,300).map(t=>`<tr><td><span class="tag" style="background:${PCOLOR[t.prog]}22;color:${PCOLOR[t.prog]}">${t.prog}</span></td><td>${t.id}</td><td>${t.title}</td><td class="num">${t.year}</td><td class="num">${t.m?fmtM(t.m):'—'}</td></tr>`).join('');
}

/* ---------- orgs ---------- */
const orgBar=echarts.init(document.getElementById('orgbar'));
document.getElementById('orgq').oninput=()=>renderOrgs();
document.getElementById('op-back').onclick=()=>{document.getElementById('orgprofile').style.display='none';document.getElementById('orglistcard').style.display='block';};
function renderOrgs(){
  const q=document.getElementById('orgq').value.trim().toLowerCase();
  const rows=ORGS.filter(o=>!q||o.name.toLowerCase().includes(q));
  document.getElementById('orgtable').innerHTML=
    '<tr><th>#</th><th>机构</th><th>国</th><th>类型</th><th class="num">项目数</th><th class="num">EU 资助合计</th><th>活跃板块</th></tr>'+
    rows.map((o,i)=>`<tr style="cursor:pointer" onclick="orgProfile(${ORGS.indexOf(o)})"><td>${i+1}</td><td><b>${o.name}</b></td><td>${o.country||''}</td><td>${o.type||''}</td><td class="num">${o.projects}</td><td class="num">${fmtM(o.total)}</td><td>${Object.keys(o.progs).map(p=>`<span class="tag" style="background:${PCOLOR[p]}22;color:${PCOLOR[p]}">${p}</span>`).join(' ')}</td></tr>`).join('');
}
function orgProfile(i){
  const o=ORGS[i];
  document.getElementById('orglistcard').style.display='none';
  const prof=document.getElementById('orgprofile');prof.style.display='block';
  document.getElementById('op-name').textContent=o.name;
  document.getElementById('op-meta').textContent=`${o.country} · ${o.type} · 跨 ${Object.keys(o.progs).length} 个板块 · ${o.projects} 个项目 · 合计 ${fmtM(o.total)}（完整版：项目清单 / 资金时间线 / 合作网络）`;
  const ps=Object.entries(o.progs).sort((a,b)=>b[1].eur-a[1].eur);
  orgBar.setOption({tooltip:{formatter:x=>x.name+'<br>'+fmtM(x.value)+' · '+o.progs[x.name].projects+' 个项目'},
    grid:{left:100,right:60,top:10,bottom:25},xAxis:{type:'value',name:'€M'},
    yAxis:{type:'category',data:ps.map(x=>x[0]).reverse()},
    series:[{type:'bar',data:ps.map(([p,v])=>({value:v.eur,itemStyle:{color:PCOLOR[p]}})).reverse(),
      label:{show:true,position:'right',formatter:x=>fmtM(x.value),fontSize:10}}]},true);
  window.dispatchEvent(new Event('resize'));
}
renderOrgs();
</script>
</body>
</html>
"""

out = (HTML
       .replace("__AGG__", json.dumps(agg["agg"], ensure_ascii=False))
       .replace("__ORGS__", json.dumps(agg["orgs"], ensure_ascii=False))
       .replace("__TOPICS__", json.dumps(topics, ensure_ascii=False)))
path = ROOT.parent / "docs" / "webapp_demo.html"
path.write_text(out)
print(f"written {path} ({path.stat().st_size//1024} KB)")
