// Background function: runs the full four-stage DeepSeek search server-side (up to 15 min),
// so the slow v4-pro reasoning calls (30–50s each) aren't bound by the 26s sync-function cap.
// It writes progress + the final ranked list to Netlify Blobs under jobId; the browser polls
// search.mjs (action 'status') for them. Mirrors horizon_search.py / index.html's llmSearch.
//
// Triggered by search.mjs via POST {jobId, query, origin}. Returns 202 immediately; the body
// keeps running to completion. DeepSeek key stays server-side (DEEPSEEK_API_KEY).
//
// The pipeline lives in runSearch() with its data-fetch, API key and progress callback injected,
// so it can be exercised headlessly (see scratchpad test harness) without Netlify/Blobs/Turnstile.

import { getStore } from '@netlify/blobs';

// —— config (mirrors horizon_search.py configure() for the DeepSeek default) ——
const ROUTE_MODEL = 'deepseek-v4-flash';            // route on flash (pro would exhaust its output budget)
const WORK_MODEL  = 'deepseek-v4-pro';              // coarse / fine / rerank
const SHARD_THRESHOLD = 300, SHARD_SIZE = 200, FINE_SHARD = 40;   // small shards: v4-pro reasons before answering
const FINAL_TOP = 50, RERANK_IN = 80, SNIPPET = 300;
const maxOutFor = (m) => /pro/.test(m) ? 32000 : 8192;

// —— DeepSeek call (OpenAI-compatible). Throws on empty content so the halving retry can split. ——
async function deepseek(prompt, model, apiKey) {
  const r = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: 'Bearer ' + apiKey },
    body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }], max_tokens: maxOutFor(model), temperature: 0 }),
  });
  if (!r.ok) {
    const body = (await r.text()).slice(0, 200);
    const err = new Error('DeepSeek HTTP ' + r.status + ': ' + body);
    // fatal = don't let the shard-retry logic swallow it; surface a clear message to the user
    if (r.status === 402 || /insufficient balance/i.test(body)) { err.fatal = true; err.code = 'NO_CREDIT'; }
    else if (r.status === 401 || r.status === 403) { err.fatal = true; err.code = 'AUTH'; }
    throw err;
  }
  const d = await r.json();
  const ch = (d.choices || [])[0] || {};
  const txt = (ch.message && ch.message.content) || '';
  if (!txt) throw new Error('DeepSeek empty (finish=' + (ch.finish_reason || '?') + ')');
  return txt;
}

// —— tolerant parsers (mirror parse_id_array / parse_obj_array) ——
function parseIds(txt) {
  try { const a = JSON.parse(txt); if (Array.isArray(a)) return a.filter(x => typeof x === 'number').map(x => x | 0); } catch {}
  return (txt.match(/\d{5,}/g) || []).map(Number);
}
function parseObjs(txt) {
  try { const a = JSON.parse(txt); if (Array.isArray(a)) return a.filter(x => x && typeof x === 'object'); } catch {}
  const out = []; const re = /\{[^{}]*\}/g; let m;
  while ((m = re.exec(txt))) { try { out.push(JSON.parse(m[0])); } catch {} }
  return out;
}

// —— prompt templating (same SPEC.prompts the webapp & CLI use) ——
function fill(prompts, name, kw) {
  let t = prompts[name].join('\n');
  for (const k in kw) t = t.split('{{' + k + '}}').join(String(kw[k]));
  return t;
}

// —— the four-stage pipeline. Returns [{g,score,reason}]. Dependencies injected for testability. ——
export async function runSearch({ query, fetchJson, apiKey, onProgress }) {
  const progress = (step, label) => onProgress && onProgress({ state: 'running', step, label });
  const ds = (prompt, model) => deepseek(prompt, model, apiKey);

  const spec = await fetchJson('search_spec.json');
  const prompts = spec.prompts, blockDesc = spec.blockDesc || {};

  // one coarse shard; on failure split in half and retry (mirror coarseShard / _coarse_shard)
  async function coarseShard(rows, depth = 0) {
    try {
      const lines = rows.map(r => `[${r[0]}] ${r[1] || ''} — ${r[2] || ''} :: ${(r[3] || '').slice(0, SNIPPET)}`).join('\n');
      return parseIds(await ds(fill(prompts, 'coarse', { query, count: rows.length, lines }), WORK_MODEL));
    } catch (e) {
      if (e.fatal) throw e;                        // out-of-credit / auth → bubble up, don't swallow
      if (depth >= 2 || rows.length <= 120) return [];
      const mid = rows.length >> 1;
      const [a, b] = await Promise.all([coarseShard(rows.slice(0, mid), depth + 1), coarseShard(rows.slice(mid), depth + 1)]);
      return a.concat(b);
    }
  }

  // —— Stage 0: route ——
  progress(0, 'Routing to relevant domains…');
  const catalog = await fetchJson('data/proj_catalog.json');   // [gid, acr, title, snippet, block]
  const counts = {};
  for (const r of catalog) counts[r[4]] = (counts[r[4]] || 0) + 1;
  const info = Object.keys(counts).sort().map(k => `${k}: ${blockDesc[k] || k} (${counts[k]})`).join('\n');
  let routed;
  try {
    const txt = await ds(fill(prompts, 'route', { query, info }), ROUTE_MODEL);
    let picked = [];
    try { const a = JSON.parse(txt); if (Array.isArray(a)) picked = a.filter(x => counts[x]); } catch {}
    if (!picked.length) picked = Object.keys(counts).filter(k => txt.includes(k));
    routed = new Set(picked.length ? picked : Object.keys(counts));
  } catch (e) { if (e.fatal) throw e; routed = new Set(Object.keys(counts)); }

  // —— Stage 1: adaptive coarse ——
  const sub = catalog.filter(r => routed.has(r[4]));
  progress(1, `Screening ${sub.length} projects across ${routed.size} domains…`);
  let idRaw;
  if (sub.length <= SHARD_THRESHOLD) {
    idRaw = await coarseShard(sub);
  } else {
    const shards = [];
    for (let i = 0; i < sub.length; i += SHARD_SIZE) shards.push(sub.slice(i, i + SHARD_SIZE));
    progress(1, `Screening ${sub.length} projects in ${shards.length} parallel shards…`);
    idRaw = (await Promise.all(shards.map(sh => coarseShard(sh)))).flat();
  }
  const gid2row = new Map(catalog.map(r => [r[0], r]));
  const ids = [...new Set(idRaw)].filter(g => { const r = gid2row.get(g); return r && routed.has(r[4]); });
  if (!ids.length) return [];

  // —— Stage 2: fine score (fetch objectives for candidate blocks) ——
  progress(2, `Scoring ${ids.length} candidates…`);
  const cand = ids.map(g => gid2row.get(g));
  const blocks = [...new Set(cand.map(r => r[4]))];
  const objs = {};
  await Promise.all(blocks.map(async b => { objs[b] = await fetchJson(`data/objectives_${b}.json`).catch(() => ({})); }));
  const bodyOf = (rows) => rows.map(r => `[${r[0]}] ${r[2]}\nAbstract: ${(objs[r[4]] || {})[r[0]] || '(no abstract)'}`).join('\n\n');
  let scoredRaw;
  if (cand.length <= FINE_SHARD) {
    scoredRaw = parseObjs(await ds(fill(prompts, 'fine', { query, count: cand.length, body: bodyOf(cand) }), WORK_MODEL));
  } else {
    const shards = [];
    for (let i = 0; i < cand.length; i += FINE_SHARD) shards.push(cand.slice(i, i + FINE_SHARD));
    progress(2, `Scoring ${cand.length} candidates in ${shards.length} parallel shards…`);
    const res = await Promise.all(shards.map(sh =>
      ds(fill(prompts, 'fine', { query, count: sh.length, body: bodyOf(sh) }), WORK_MODEL).then(parseObjs)
        .catch(e => { if (e.fatal) throw e; return []; })));
    scoredRaw = res.flat();
  }
  const seen = new Set();
  let scored = scoredRaw
    .filter(s => s && gid2row.has(s.g) && Number.isFinite(s.score) && !seen.has(s.g) && seen.add(s.g))
    .sort((a, b) => b.score - a.score);
  if (!scored.length) return [];

  // —— Stage 3: Pro rerank ——
  if (scored.length > 1) {
    progress(3, `Final re-rank of the top ${Math.min(scored.length, RERANK_IN)}…`);
    try {
      const head = scored.slice(0, RERANK_IN);
      const body = head.map(s => { const r = gid2row.get(s.g); return `[${s.g}] ${r[2]} (prelim ${s.score})\nAbstract: ${((objs[r[4]] || {})[s.g] || '(no abstract)').slice(0, 600)}`; }).join('\n\n');
      const reSeen = new Set();
      const re = parseObjs(await ds(fill(prompts, 'rerank', { query, count: head.length, body }), WORK_MODEL))
        .filter(s => s && gid2row.has(s.g) && Number.isFinite(s.score) && !reSeen.has(s.g) && reSeen.add(s.g))
        .sort((a, b) => b.score - a.score);
      if (re.length) { const done = new Set(re.map(s => s.g)); scored = re.concat(scored.filter(s => !done.has(s.g))); }
    } catch { /* keep fine order */ }
  }

  return scored.slice(0, FINAL_TOP).map(s => ({ g: s.g, score: s.score, reason: s.reason || '' }));
}

// —— Netlify background handler: wires real Blobs + CDN fetch + env key into runSearch ——
export default async (req) => {
  let jobId;
  const store = getStore('searchjobs');
  try {
    const body = await req.json();
    jobId = body.jobId;
    const query = body.query;
    const origin = (body.origin || process.env.URL || '').replace(/\/$/, '');
    if (!jobId || !query) return new Response('bad request', { status: 400 });

    const fetchJson = (p) => fetch(`${origin}/${p}`).then(r => r.json());
    const onProgress = (rec) => store.setJSON(jobId, rec);
    const ranked = await runSearch({ query, fetchJson, apiKey: process.env.DEEPSEEK_API_KEY, onProgress });
    await store.setJSON(jobId, { state: 'done', ranked });
  } catch (e) {
    if (jobId) { try { await store.setJSON(jobId, { state: 'error', error: String(e && e.message || e).slice(0, 200), code: e && e.code || null }); } catch {} }
  }
};
