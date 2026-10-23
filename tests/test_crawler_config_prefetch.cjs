const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const appSource = fs.readFileSync(path.join(root, 'javsp_web/web/assets/app.js'), 'utf8');

function slice(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0, `missing slice start: ${start}`);
  assert.ok(to > from, `missing slice end: ${end}`);
  return source.slice(from, to);
}

const START = 'async function loadCrawlerConfig(';
const END = 'function crawlerCardMarkup(';

function harness({ prefetchFails = false } = {}) {
  const writes = [];
  const host = {
    innerHTML: '',
  };
  Object.defineProperty(host, 'innerHTML', {
    get() { return this._html || ''; },
    set(value) { this._html = String(value); writes.push(String(value)); },
  });
  const calls = [];
  const context = vm.createContext({
    $: selector => (selector === '#crawler-config-content' ? host : null),
    escapeHtml: value => String(value ?? ''),
    api: target => {
      calls.push(target);
      if (prefetchFails && calls.length === 1) return Promise.reject(new Error('boom'));
      return Promise.resolve({ crawlers: [{ name: 'airav', kind: 'built_in' }], disabled_built_ins: [] });
    },
    crawlerSkeletonMarkup: () => '<div data-crawler-loading>skeleton</div>',
    crawlerCodeMarkup: crawlers => `<div class="crawler-source-grid">${crawlers.map(item => `<article class="crawler-source-card">${item.name}</article>`).join('')}</div>`,
    bindCrawlerEditorDialog: () => {},
    state: { crawlerSources: [], disabledBuiltInCrawlers: [] },
  });
  context.window = context;
  vm.runInContext(slice(appSource, START, END), context);
  return { context, calls, writes, host };
}

test('hovering the crawler nav warms the config once and the page renders without a skeleton', async () => {
  const { context, calls, writes } = harness();
  assert.equal(typeof context.prefetchCrawlerConfig, 'function', 'app.js must expose the prefetch hook');

  context.prefetchCrawlerConfig();
  context.prefetchCrawlerConfig();
  assert.equal(calls.length, 1, 'repeated hovers share one request');

  await context.loadCrawlerConfig();
  assert.deepEqual(writes.filter(value => value.includes('skeleton')), [], 'a warmed page must not flash the skeleton');
  assert.match(writes.at(-1), /crawler-source-card/);
  assert.equal(calls.length, 1, 'the cached payload is reused instead of refetching');
});

test('a cold open still shows the skeleton, and a failed prefetch falls back to a real request', async () => {
  const cold = harness();
  await cold.context.loadCrawlerConfig();
  assert.match(cold.writes[0], /skeleton/, 'cold open renders the skeleton first');
  assert.match(cold.writes.at(-1), /crawler-source-card/);

  const failed = harness({ prefetchFails: true });
  failed.context.prefetchCrawlerConfig();
  await new Promise(resolve => setImmediate(resolve));
  await failed.context.loadCrawlerConfig();
  assert.equal(failed.calls.length >= 2, true, 'a failed prefetch must retry through the live request');
  assert.match(failed.writes.at(-1), /crawler-source-card/);
});

test('the crawler nav entry wires pointerenter and focus to the prefetch', () => {
  const source = appSource;
  assert.match(source, /\$\('#crawler-config-nav'\)/);
  assert.match(source, /crawlerNav\.addEventListener\('pointerenter', prefetchCrawlerConfig, \{ once: true \}\)/);
  assert.match(source, /crawlerNav\.addEventListener\('focus', prefetchCrawlerConfig, \{ once: true \}\)/);
});
