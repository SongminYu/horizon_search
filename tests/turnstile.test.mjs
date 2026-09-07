import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const page = readFileSync(new URL('../webapp/index.html', import.meta.url), 'utf8');
const errorStart = page.indexOf('function verificationError(');
const cancelStart = page.search(/^let _tsCancel\s*=/m);
assert.ok(errorStart >= 0, 'verification helpers must be present');
const verification = page.slice(cancelStart >= 0 ? Math.min(errorStart, cancelStart) : errorStart,
  page.indexOf('async function loadSpec()', errorStart));
const hosted = page.slice(page.indexOf('function sleep('), page.indexOf('// ---- About & settings'));
const errorHTML = page.slice(page.indexOf('function searchErrorHTML('), page.indexOf('function renderDash('));
const escapeHTML = page.match(/^const esc=.*$/m)[0];

class Clock {
  now = 0;
  nextId = 0;
  timers = new Map();
  setTimeout = (callback, delay = 0) => {
    const id = ++this.nextId;
    this.timers.set(id, { callback, at: this.now + delay });
    return id;
  };
  clearTimeout = id => this.timers.delete(id);
  advance(ms) {
    const until = this.now + ms;
    for (let runs = 0; ; runs++) {
      assert.ok(runs < 10000, 'timers should not loop forever');
      const next = [...this.timers].filter(([, t]) => t.at <= until)
        .sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
      if (!next) break;
      this.now = next[1].at;
      this.timers.delete(next[0]);
      next[1].callback();
    }
    this.now = until;
  }
}

function harness({ script = true, renderError, executeError, onRender, onExecute, response } = {}) {
  const clock = new Clock();
  const widgets = [], removed = [], executed = [], requests = [];
  const container = { id: 'ts-widget' };
  const api = {
    render(element, options) {
      assert.equal(element, container, 'render into the visible search container');
      if (renderError) throw renderError;
      const widget = { id: `widget-${widgets.length}`, options };
      widgets.push(widget);
      onRender?.(widget);
      return widget.id;
    },
    execute(id) {
      executed.push(id);
      if (executeError) throw executeError;
      onExecute?.(widgets.find(widget => widget.id === id));
    },
    remove(id) { removed.push(id); },
  };
  const context = vm.createContext({
    TURNSTILE_SITEKEY: 'test-site-key',
    DOMException,
    document: { getElementById: id => id === 'ts-widget' ? container : null },
    Date: class extends Date { static now() { return clock.now; } },
    setTimeout: clock.setTimeout,
    clearTimeout: clock.clearTimeout,
    fetch: async (...args) => {
      requests.push(args);
      if (response) return response;
      throw new Error('Unexpected network request');
    },
    G: { gid2idx: {} },
  });
  context.window = context;
  if (script) context.turnstile = api;
  vm.runInContext(verification + '\n' + hosted + '\n' + escapeHTML + '\n' + errorHTML, context);
  return { clock, widgets, removed, executed, requests, api, context,
    token: signal => context.getTurnstileToken(signal),
    search: signal => context.hostedSearch('energy modelling', () => {}, signal) };
}

function watch(promise) {
  const result = { state: 'pending' };
  promise.then(value => Object.assign(result, { state: 'resolved', value }),
    error => Object.assign(result, { state: 'rejected', error }));
  return result;
}
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
const isVerificationError = error => /^VERIFICATION_/.test(error.code);
const isAbort = error => error.name === 'AbortError';
function assertClean(h, expectedRemoved = h.widgets.map(widget => widget.id)) {
  assert.deepEqual(h.removed, expectedRemoved);
  assert.equal(h.clock.timers.size, 0, 'no verification timers should survive settlement');
}

test('success returns the token, allows interaction, and releases the widget and timer', async () => {
  const h = harness();
  const controller = new AbortController();
  const result = h.token(controller.signal);
  assert.equal(h.widgets.length, 1);
  const { id, options } = h.widgets[0];
  assert.equal(options.execution, 'execute');
  assert.equal(options.appearance, 'interaction-only');
  assert.equal(options.retry, 'never');
  assert.equal(options.size, 'normal');
  assert.deepEqual(h.executed, [id]);
  options.callback('valid-token');
  assert.equal(await result, 'valid-token');
  controller.abort();
  assertClean(h);
});

test('a Cloudflare error rejects immediately and keeps its diagnostic code', async () => {
  const h = harness();
  const result = h.token();
  const rejected = assert.rejects(result, error => isVerificationError(error)
    && error.verificationCode === '110200');
  h.widgets[0].options['error-callback']('110200');
  await rejected;
  assertClean(h);
});

for (const event of ['timeout-callback', 'expired-callback', 'unsupported-callback']) {
  test(`${event} rejects promptly and cleans up`, async () => {
    const h = harness();
    const result = h.token();
    const rejected = assert.rejects(result, isVerificationError);
    h.widgets[0].options[event]();
    await rejected;
    assertClean(h);
  });
}

test('a challenge that never responds fails within the overall deadline', async () => {
  const h = harness();
  const result = h.token();
  const state = watch(result);
  const rejected = assert.rejects(result, isVerificationError);
  h.clock.advance(59999);
  await flush();
  assert.equal(state.state, 'pending');
  h.clock.advance(1);
  await rejected;
  assertClean(h);
});

test('old callbacks and the old deadline cannot settle a later search', async () => {
  const h = harness();
  const first = h.token();
  const old = h.widgets[0].options;
  h.clock.advance(15000);
  old.callback('first-token');
  assert.equal(await first, 'first-token');

  const next = h.token();
  const state = watch(next);
  old.callback('stale-token');
  old['error-callback']('110200');
  old['timeout-callback']();
  old['expired-callback']();
  h.clock.advance(45000);
  await flush();
  assert.equal(state.state, 'pending');
  h.widgets[1].options.callback('next-token');
  assert.equal(await next, 'next-token');
  assertClean(h);
});

test('starting a second verification cancels the first without corrupting the second', async () => {
  const h = harness();
  const first = h.token();
  const rejected = assert.rejects(first, isAbort);
  const second = h.token();
  await rejected;
  h.widgets[0].options.callback('stale-token');
  h.widgets[1].options.callback('current-token');
  assert.equal(await second, 'current-token');
  assertClean(h);
});

test('aborting a pending challenge releases all resources', async () => {
  const h = harness();
  const controller = new AbortController();
  const result = h.token(controller.signal);
  const rejected = assert.rejects(result, isAbort);
  controller.abort();
  await rejected;
  h.widgets[0].options.callback('late-token');
  assertClean(h);
});

test('an already aborted request does not create a widget', async () => {
  const h = harness();
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(h.token(controller.signal), isAbort);
  assert.equal(h.widgets.length, 0);
  assertClean(h);
});

test('an already aborted request cannot cancel another active verification', async () => {
  const h = harness();
  const active = h.token();
  const state = watch(active);
  const cancelled = new AbortController();
  cancelled.abort();
  await assert.rejects(h.token(cancelled.signal), isAbort);
  await flush();
  assert.equal(state.state, 'pending');
  assert.equal(h.widgets.length, 1);
  assert.equal(h.removed.length, 0);
  h.widgets[0].options.callback('active-token');
  assert.equal(await active, 'active-token');
  assertClean(h);
});

test('a blocked script fails after ten seconds without leaving polling timers', async () => {
  const h = harness({ script: false });
  const result = h.token();
  const rejected = assert.rejects(result, isVerificationError);
  h.clock.advance(10000);
  await rejected;
  assert.equal(h.widgets.length, 0);
  assertClean(h);
});

test('a script that loads late can still complete verification', async () => {
  const h = harness({ script: false });
  const result = h.token();
  h.clock.advance(5000);
  assert.equal(h.widgets.length, 0);
  h.context.turnstile = h.api;
  h.clock.advance(100);
  assert.equal(h.widgets.length, 1);
  h.widgets[0].options.callback('late-script-token');
  assert.equal(await result, 'late-script-token');
  assertClean(h);
});

test('abort also stops waiting for a script that has not loaded', async () => {
  const h = harness({ script: false });
  const controller = new AbortController();
  const result = h.token(controller.signal);
  const rejected = assert.rejects(result, isAbort);
  h.clock.advance(1000);
  controller.abort();
  await rejected;
  h.context.turnstile = h.api;
  h.clock.advance(10000);
  assert.equal(h.widgets.length, 0);
  assertClean(h);
});

for (const operation of ['render', 'execute']) {
  test(`a synchronous ${operation} exception rejects and releases resources`, async () => {
    const h = harness({ [`${operation}Error`]: new Error(`${operation} failed`) });
    await assert.rejects(h.token(), isVerificationError);
    assertClean(h);
  });
}

test('a synchronous render callback still removes the returned widget exactly once', async () => {
  const h = harness({ onRender: widget => widget.options.callback('sync-token') });
  assert.equal(await h.token(), 'sync-token');
  assert.equal(h.executed.length, 0);
  assertClean(h);
});

test('hosted search never submits a job after verification fails', async () => {
  const h = harness();
  const result = h.search();
  const rejected = assert.rejects(result, isVerificationError);
  h.widgets[0].options['error-callback']('110200');
  await rejected;
  assert.equal(h.requests.length, 0);
  assertClean(h);
});

test('a server-rejected token remains a verification error rather than a quota error', async () => {
  const h = harness({ response: { ok: false, status: 403, text: async () => 'Verification failed' } });
  const result = h.search();
  const rejected = assert.rejects(result, isVerificationError);
  h.widgets[0].options.callback('rejected-token');
  await rejected;
  assert.equal(h.requests.length, 1);
  assert.equal(JSON.parse(h.requests[0][1].body).action, 'start');
  assertClean(h);
});

test('hosted search passes abort to verification and never submits a cancelled job', async () => {
  const h = harness();
  const controller = new AbortController();
  const result = h.search(controller.signal);
  const rejected = assert.rejects(result, isAbort);
  controller.abort();
  await rejected;
  assert.equal(h.requests.length, 0);
  assertClean(h);
});

test('an abort between token delivery and submission cannot start a hosted job', async () => {
  const h = harness();
  const controller = new AbortController();
  const result = h.search(controller.signal);
  const rejected = assert.rejects(result, isAbort);
  h.widgets[0].options.callback('valid-token');
  controller.abort();
  await rejected;
  assert.equal(h.requests.length, 0);
  assertClean(h);
});

test('verification errors show a dedicated retry action and escape diagnostic details', () => {
  const h = harness();
  const html = h.context.searchErrorHTML({ code: 'VERIFICATION_FAILED',
    message: '<script>untrusted message</script>', verificationCode: '<error-code>' });
  assert.match(html, /Security verification couldn't finish/);
  assert.match(html, /onclick="retryVerification\(\)"/);
  assert.match(html, /The shared search has not started/);
  assert.match(html, /Verification code:/);
  assert.doesNotMatch(html, /<script>|<error-code>|daily-limit|rate-limit/);
});

test('NO_CREDIT keeps its existing credit explanation and alternatives', () => {
  const html = harness().context.searchErrorHTML({ code: 'NO_CREDIT', message: 'balance exhausted' });
  assert.match(html, /The shared search is out of credit right now/);
  assert.match(html, /shared DeepSeek key that's temporarily depleted/);
  assert.match(html, /Use your own API key/);
  assert.match(html, /Browse &amp; filter projects/);
  assert.match(html, /Run it yourself/);
  assert.doesNotMatch(html, /Retry verification|Security verification couldn't finish/);
});

test('other search errors do not offer verification retry or guess a quota diagnosis', () => {
  const html = harness().context.searchErrorHTML(new Error('upstream unavailable'));
  assert.match(html, /Search couldn't finish/);
  assert.match(html, /upstream unavailable/);
  assert.doesNotMatch(html, /Retry verification|Security verification couldn't finish|daily-limit|rate-limit/);
});
