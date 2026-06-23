// Sync entry point for the hosted search. Two POST actions:
//   {action:"start",  turnstile, query}  → verify Turnstile + per-IP daily cap → mint jobId,
//                                           kick off search-background, return {jobId}
//   {action:"status", jobId}             → read the job's progress/result from Netlify Blobs
//
// The heavy DeepSeek pipeline runs in search-background.mjs (15-min budget); this function stays
// fast (well under the 26s sync cap). Env: DEEPSEEK_API_KEY (used by the bg fn), TURNSTILE_SECRET.

import { getStore } from '@netlify/blobs';

const CAP_PER_DAY = 40;            // searches per IP per day
const MAX_BODY = 200_000;

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json' } });
const text = (msg, status) => new Response(msg, { status, headers: { 'content-type': 'text/plain' } });

const b64url = (bytes) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

async function verifyTurnstile(secret, token, ip) {
  const body = new URLSearchParams({ secret, response: token || '' });
  if (ip) body.set('remoteip', ip);
  const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body });
  const d = await r.json().catch(() => ({}));
  return !!d.success;
}

export default async (req, context) => {
  if (req.method !== 'POST') return text('POST only', 405);
  const raw = await req.text();
  if (raw.length > MAX_BODY) return text('Request too large', 413);
  let body; try { body = JSON.parse(raw); } catch { return text('Bad JSON', 400); }

  const store = getStore('searchjobs');

  // ---- status: read progress/result by jobId (jobId is an unguessable capability token) ----
  if (body.action === 'status') {
    if (!body.jobId) return text('Missing jobId', 400);
    const rec = await store.get(body.jobId, { type: 'json' }).catch(() => null);
    if (!rec) return json({ state: 'pending' });
    return json(rec);
  }

  // ---- start: Turnstile + per-IP cap → mint job → fire background fn ----
  if (body.action === 'start') {
    const TURNSTILE_SECRET = process.env.TURNSTILE_SECRET, DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY;
    if (!TURNSTILE_SECRET || !DEEPSEEK_API_KEY) return text('Server not configured', 500);
    const ip = context?.ip || req.headers.get('x-nf-client-connection-ip') || req.headers.get('x-forwarded-for') || 'unknown';
    if (!(await verifyTurnstile(TURNSTILE_SECRET, body.turnstile, ip))) return text('Verification failed', 403);

    try {
      const rl = getStore('ratelimit');
      const day = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const key = `d${day}_${ip}`;
      const n = Number((await rl.get(key)) || 0);
      if (n >= CAP_PER_DAY) return text('Daily search limit reached. Please try again tomorrow.', 429);
      await rl.set(key, String(n + 1));
    } catch { /* rate-limit store best-effort; Turnstile still gates */ }

    const query = typeof body.query === 'string' ? body.query.slice(0, 4000).trim() : '';
    if (!query) return text('Missing query', 400);

    const jobId = b64url(crypto.getRandomValues(new Uint8Array(18)));
    await store.setJSON(jobId, { state: 'pending', step: -1, label: 'Starting…' });

    const origin = (process.env.URL || new URL(req.url).origin).replace(/\/$/, '');
    // fire-and-forget: background fn returns 202 immediately, then runs to completion
    try {
      await fetch(`${origin}/.netlify/functions/search-background`, {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ jobId, query, origin }),
      });
    } catch (e) {
      await store.setJSON(jobId, { state: 'error', error: 'Could not start search' });
      return text('Could not start search', 502);
    }
    return json({ jobId });
  }

  return text('Unknown action', 400);
};
