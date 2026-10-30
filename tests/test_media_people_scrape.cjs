const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../javsp_web/web/assets/app.js'), 'utf8');

const SERVER = { id: 'srv-1', name: 'Emby', type: 'emby', url: 'http://127.0.0.1:8096', api_key_set: true, auto_scan: false };

function sliceCode(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  assert.ok(from >= 0, `missing slice start: ${start}`);
  assert.ok(to > from, `missing slice end: ${end}`);
  return source.slice(from, to);
}

// Minimal DOM stub: the media-server-list captures innerHTML; each [data-people-scrape="id"]
// host records its own innerHTML so card re-renders are observable.
function makeDom() {
  const hosts = new Map();
  const document = {
    querySelector(selector) {
      const hostMatch = selector.match(/^\[data-people-scrape="(.+)"\]$/);
      if (hostMatch) {
        if (!hosts.has(hostMatch[1])) hosts.set(hostMatch[1], {
          innerHTML: '',
          scrollTop: 0,
          scrollHeight: 0,
          classList: { contains: () => false },
        });
        return hosts.get(hostMatch[1]);
      }
      return null;
    },
    createElement() {
      return {
        set innerHTML(value) { this._html = value; },
        get innerHTML() { return this._html || ''; },
        get firstElementChild() {
          const html = this._html || '';
          const m = html.match(/^<div class="people-scrape"[^>]*>([\s\S]*)<\/div>$/);
          if (!m) throw new Error('stub: unexpected card markup ' + html.slice(0, 80));
          return {
            _html: m[1],
            replaceWith() { for (const host of hosts.values()) host.innerHTML = this._html; },
          };
        },
      };
    },
  };
  return { hosts, document };
}

function makeHarness({ getResponse, putResponse, runResponse }) {
  const dom = makeDom();
  const calls = [];
  const timers = [];
  const context = vm.createContext({
    $: () => null,
    document: dom.document,
    state: { mediaServers: [SERVER] },
    escapeHtml: value => String(value ?? ''),
    javspIcon: () => '',
    api: async (url, options = {}) => {
      calls.push({ url, options: { ...options, body: options.body } });
      if (options.method === 'POST') {
        const value = typeof runResponse === 'function' ? runResponse() : runResponse;
        if (value instanceof Error) throw value;
        return value || { started: true };
      }
      if (options.method === 'PUT') {
        if (putResponse instanceof Error) throw putResponse;
        return putResponse;
      }
      const value = typeof getResponse === 'function' ? getResponse() : getResponse;
      if (value instanceof Error) throw value;
      return value;
    },
    clearTimeout() {},
    setTimeout(callback, delay) { timers.push({ callback, delay }); return timers.length; },
    window: {},
  });
  vm.runInContext(sliceCode('const peopleScrape = { state: {}, timer: null };', 'async function loadMediaServers()'), context);
  const cardHtml = () => {
    const entry = context.window.__peopleScrapeEntry(SERVER.id);
    if (entry && typeof entry.html === 'string') return entry.html;
    const host = dom.hosts.get(SERVER.id);
    return (host && host.innerHTML) || '';
  };
  return { ...dom, calls, timers, context, cardHtml };
}

test('a ready people-scrape card renders toggle, run button, stats and a collapsed log', async () => {
  const harness = makeHarness({
    getResponse: { enabled: true, running: false, last_run_at: '2026-10-20T10:00:00+08:00', stats: { created: 1, updated: 2, skipped: 3, failed: 0 }, log: ['line-1', 'line-2'] },
  });
  await harness.context.loadPeopleScrape(SERVER);
  const html = harness.cardHtml();
  assert.match(html, /data-people-scrape-toggle="srv-1" checked/);
  assert.match(html, /立即刮削演员/);
  assert.match(html, /新增 1 · 更新 2 · 跳过 3 · 失败 0/);
  assert.match(html, /data-people-scrape-log="srv-1"/);
  assert.match(html, /class="people-scrape-log hidden"/);
  assert.match(html, /<div>line-1<\/div><div>line-2<\/div>/);
  assert.ok(harness.calls.some(call => call.url === '/api/media-servers/srv-1/people-scrape' && !call.options.method));
});

test('a 404 people-scrape endpoint degrades to a hint and keeps the existing buttons', async () => {
  const harness = makeHarness({ getResponse: new Error('404: not found') });
  await harness.context.loadPeopleScrape(SERVER);
  const html = harness.cardHtml();
  assert.match(html, /暂不支持演员刮削/);
  assert.doesNotMatch(html, /data-people-scrape-toggle/);
  // Full card markup still carries the original edit/sync buttons.
  const region = sliceCode('function renderMediaServers() {', 'async function loadMediaServers()');
  assert.match(region, /data-edit-media-server/);
  assert.match(region, /data-sync-media-server/);
  assert.match(region, /\$\{peopleScrapeCard\(server\)\}/);
});

test('a non-404 error shows the failure message instead of crashing', async () => {
  const harness = makeHarness({ getResponse: new Error('500: boom') });
  await harness.context.loadPeopleScrape(SERVER);
  assert.match(harness.cardHtml(), /演员刮削状态获取失败.*500: boom/);
});

test('toggling the checkbox PUTs the new enabled state and re-renders', async () => {
  const harness = makeHarness({
    getResponse: { enabled: false, running: false, stats: null, log: [] },
    putResponse: { enabled: true, running: false, stats: null, log: [] },
  });
  await harness.context.loadPeopleScrape(SERVER);
  const input = { checked: true };
  await harness.context.togglePeopleScrape(SERVER, input);
  const put = harness.calls.find(call => call.options.method === 'PUT');
  assert.equal(put.url, '/api/media-servers/srv-1/people-scrape');
  assert.deepEqual(JSON.parse(put.options.body), { enabled: true });
  assert.match(harness.cardHtml(), /data-people-scrape-toggle="srv-1" checked/);
});

test('a failed toggle reverts the checkbox', async () => {
  const harness = makeHarness({
    getResponse: { enabled: false, running: false, stats: null, log: [] },
    putResponse: new Error('400: bad request'),
  });
  await harness.context.loadPeopleScrape(SERVER);
  const input = { checked: true };
  await harness.context.togglePeopleScrape(SERVER, input);
  assert.equal(input.checked, false);
});

test('run enters the running state, posts, and polls until completion stats arrive', async () => {
  let running = true;
  const harness = makeHarness({
    getResponse: () => ({ enabled: true, running, stats: running ? null : { created: 4, updated: 1, skipped: 2, failed: 1 }, log: ['done'] }),
    runResponse: () => ({ started: true }),
  });
  await harness.context.loadPeopleScrape(SERVER);
  assert.match(harness.cardHtml(), /刮削中…/, 'a running state from the initial GET renders the running button');
  await harness.context.runPeopleScrape(SERVER);
  assert.ok(harness.calls.some(call => call.url.endsWith('/people-scrape/run') && call.options.method === 'POST'));
  // The POST resolves → the client refreshes the status (still running → schedules a poll).
  await harness.context.loadPeopleScrape(SERVER);
  const lastTimer = harness.timers[harness.timers.length - 1];
  assert.ok(lastTimer, 'a poll is scheduled while the backend reports running');
  // The poll then observes completion and the stats render.
  running = false;
  await lastTimer.callback();
  assert.doesNotMatch(harness.cardHtml(), /刮削中…/);
  assert.match(harness.cardHtml(), /新增 4 · 更新 1 · 跳过 2 · 失败 1/);
});

test('the log area keeps at most the last 50 lines', async () => {
  const longLog = Array.from({ length: 60 }, (_, i) => `log-${i}`);
  const harness = makeHarness({ getResponse: { enabled: true, running: false, stats: null, log: longLog } });
  await harness.context.loadPeopleScrape(SERVER);
  assert.match(harness.cardHtml(), /<div>log-10<\/div>/);
  assert.doesNotMatch(harness.cardHtml(), /<div>log-0<\/div>/);
});

test('people-scrape styles live in overrides.css with scoped, non-overflowing rules', () => {
  const css = fs.readFileSync(path.join(__dirname, '../javsp_web/web/assets/overrides.css'), 'utf8');
  assert.match(css, /\.people-scrape \{/);
  assert.match(css, /\.people-scrape-log \{/);
  assert.match(css, /font-family: ui-monospace/);
  assert.match(css, /@media \(max-width: 560px\)/);
});

test('the delegated click handler wires toggle, run and log controls', () => {
  const start = source.indexOf("const peopleToggle = event.target.closest('[data-people-scrape-toggle]');");
  assert.ok(start > 0, 'delegated people-scrape handler exists');
  const region = source.slice(start, start + 1400);
  assert.match(region, /togglePeopleScrape\(server, peopleToggle\)/);
  assert.match(region, /runPeopleScrape\(server\)/);
  assert.match(region, /logOpen: !entry\.logOpen/);
});
