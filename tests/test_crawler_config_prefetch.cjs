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
      if (prefetchFails && target === '/api/crawler-config' && calls.filter(name => name === target).length === 1) return Promise.reject(new Error('boom'));
      if (target === '/api/crawler-config/stats') return Promise.resolve({ crawlers: [] });
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
  assert.equal(calls.length, 2, 'the hover warms the config and the usage stats in one shared flight');
  assert.equal(calls[0], '/api/crawler-config');
  assert.equal(calls[1], '/api/crawler-config/stats');

  await context.loadCrawlerConfig();
  assert.deepEqual(writes.filter(value => value.includes('skeleton')), [], 'a warmed page must not flash the skeleton');
  assert.match(writes.at(-1), /crawler-source-card/);
  assert.equal(calls.length, 2, 'the cached payload is reused instead of refetching');
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
  assert.equal(failed.calls.filter(target => target === '/api/crawler-config').length, 2, 'a failed prefetch must retry the config through the live request');
  assert.equal(failed.calls.filter(target => target === '/api/crawler-config/stats').length, 1, 'the failed config prefetch is not retried; stats degrade silently to gray dots');
  assert.match(failed.writes.at(-1), /crawler-source-card/);
});

test('the crawler nav entry wires pointerenter and focus to the prefetch', () => {
  const source = appSource;
  assert.match(source, /\$\('#crawler-config-nav'\)/);
  assert.match(source, /crawlerNav\.addEventListener\('pointerenter', prefetchCrawlerConfig, \{ once: true \}\)/);
  assert.match(source, /crawlerNav\.addEventListener\('focus', prefetchCrawlerConfig, \{ once: true \}\)/);
});

test('crawler cards show health dots, usage stats and site/rule tags', () => {
  const source = appSource;
  const START_MARKUP = 'function crawlerStatsFor(';
  const END_MARKUP = 'function crawlerSkeletonMarkup';
  const context = vm.createContext({
    $: () => null,
    escapeHtml: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'),
    javspIcon: name => `<svg data-icon="${name}"></svg>`,
    state: { crawlerSources: [], disabledBuiltInCrawlers: [] },
  });
  vm.runInContext(slice(source, START_MARKUP, END_MARKUP), context);

  context.applyCrawlerStats({ crawlers: [
    { name: 'airav', success_rate: 0.93, success_count: 120, failure_count: 8, last_failure_at: '2026-09-01', last_success_at: '2026-10-01' },
    { name: 'javbus', success_rate: 0.75, success_count: 30, failure_count: 10 },
    { name: 'dead', success_rate: 0.2, success_count: 2, failure_count: 8 },
  ] });

  const healthy = context.crawlerStatsMarkup({ name: 'airav' });
  assert.match(healthy, /crawler-health-dot crawler-health-ok/);
  assert.match(healthy, /近 30 天成功率 93%，成功 120 \/ 失败 8/);
  assert.match(healthy, /成功 120 · 失败 8/);
  assert.match(healthy, /最近失败 2026-09-01</);
  assert.doesNotMatch(healthy, /刮削 \d+ 次/, 'usage line no longer shows scrape/task counts');

  const warn = context.crawlerStatsMarkup({ name: 'javbus' });
  assert.match(warn, /crawler-health-warn/);
  assert.match(warn, /成功率 75%/);

  const danger = context.crawlerStatsMarkup({ name: 'dead' });
  assert.match(danger, /crawler-health-danger/);

  const unknown = context.crawlerStatsMarkup({ name: 'never-heard' });
  assert.match(unknown, /crawler-health-unknown/);
  assert.doesNotMatch(unknown, /刮削 \d+ 次/);

  const tags = context.crawlerSiteTagsMarkup({ name: 'airav', sites: [{ domain: 'airav.io' }, 'javbus.com'], rules: [{ name: '按番号精确匹配番号番号番号番号番号番号番号' }] });
  assert.match(tags, /crawler-site-tag/);
  assert.match(tags, /airav\.io/);
  assert.match(tags, /javbus\.com/);
  assert.match(tags, /title="按番号精确匹配番号番号番号番号番号番号番号"/);
  assert.match(tags, />按番号精确匹配番号番号番号番号番号番号番号</, 'long rule names render in full');
  assert.doesNotMatch(context.crawlerSiteTagsMarkup({ name: 'x' }), /crawler-site-tag/, 'no tags when there are no sites or rules');

  const card = context.crawlerCardMarkup({ name: 'airav', kind: 'built_in', sites: ['airav.io'] });
  assert.match(card, /data-crawler-code-name="airav"/);
  assert.match(card, /data-open-crawler-editor="airav"/);
  assert.match(card, /title="编辑与测试 airav"/);
  assert.match(card, /aria-label="编辑与测试 airav"/);
  assert.match(card, /data-icon="pencil"/);
  assert.doesNotMatch(card, /内置/, 'kind label is removed from crawler cards');
});

test('applyCrawlerStats injects site and rule tags into already-rendered cards', () => {
  const source = appSource;
  const context = vm.createContext({
    $: () => null,
    escapeHtml: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'),
    javspIcon: name => `<svg data-icon="${name}"></svg>`,
    state: {
      crawlerSources: [{ name: 'airav', kind: 'built_in' }, { name: 'javbus', kind: 'built_in' }],
      disabledBuiltInCrawlers: [],
    },
  });
  vm.runInContext(slice(source, 'function crawlerStatsFor(', 'function crawlerSkeletonMarkup'), context);

  // Cards already rendered from /api/crawler-config, which carries no sites/rules.
  const makeCard = name => ({
    name,
    html: `<article class="crawler-source-card" data-crawler-code-name="${name}"><div class="crawler-source-card-stats"><span class="crawler-health-dot crawler-health-unknown"></span></div></article>`,
    getAttribute(attr) { return attr === 'data-crawler-code-name' ? this.name : null; },
    querySelector(sel) { return sel === '.crawler-source-card-stats' ? { outerHTML: '' } : null; },
    replacements: [],
    insertAdjacentHTML(position, markup) { this.inserted = { position, markup }; },
  });
  const cardA = makeCard('airav');
  const cardB = makeCard('javbus');
  cardA.querySelector = sel => (sel === '.crawler-source-card-stats' ? { set outerHTML(value) { cardA.replacements.push(value); } } : null);
  cardB.querySelector = sel => (sel === '.crawler-source-card-stats' ? { set outerHTML(value) { cardB.replacements.push(value); } } : null);
  const grid = { querySelectorAll: () => [cardA, cardB] };
  context.$ = selector => (selector === '#crawler-source-grid' ? grid : null);

  // Stats arrive: airav has sites+rules, javbus has none.
  context.applyCrawlerStats({ crawlers: {
    airav: { sites: ['airav.io', 'www.airav.io', 'airav.io'], rules: [{ id: 'r1', name: '每日监控' }, { id: 'r2', name: '每日监控' }], success: 12, failure: 1, success_rate: 0.9231, last_failure_at: '2026-09-20', last_success_at: '2026-10-20' },
    javbus: { sites: [], rules: [], success: 0, failure: 0 },
  } });

  const aMarkup = cardA.replacements.at(-1);
  assert.match(aMarkup, /crawler-health-dot crawler-health-ok/, 'health tone refreshes');
  assert.match(aMarkup, /title="近 30 天成功率 92%，成功 12 \/ 失败 1"/, 'health dot title carries real counts');
  assert.match(aMarkup, /成功 12 · 失败 1/, 'usage line shows success/failure counts only');
  assert.match(aMarkup, /最近失败 2026-09-20</, 'failure time formatted without T');
  const siteTags = [...aMarkup.matchAll(/crawler-site-tag" title="([^"]+)"/g)].map(m => m[1]);
  assert.deepEqual(siteTags, ['airav.io', 'www.airav.io', '每日监控'], 'sites and rules are deduped and kept, max 5 each');

  const bMarkup = cardB.replacements.at(-1);
  assert.doesNotMatch(bMarkup, /crawler-site-tag/, 'no empty tag container for a crawler without data');
  assert.match(bMarkup, /crawler-health-dot/, 'health dot still renders');

  // Stats endpoint fails after cards exist: degrade silently, never wipe cards.
  context.applyCrawlerStats(null);
  const bAfter = cardB.replacements.at(-1);
  assert.doesNotMatch(bAfter, /crawler-site-tag/, 'failed stats keep cards tag-free');
  assert.match(bAfter, /暂无成功率数据/, 'failed stats degrade to the gray unknown dot');
});

test('site and rule tags are capped at five each and render long names in full', () => {
  const source = appSource;
  const context = vm.createContext({
    $: () => null,
    escapeHtml: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'),
    javspIcon: () => '',
    state: { crawlerSources: [], disabledBuiltInCrawlers: [] },
  });
  vm.runInContext(slice(source, 'function crawlerSiteTagsMarkup', 'function crawlerCardMarkup'), context);
  const longName = '这是一个非常非常非常非常非常长的规则名称用来测试省略';
  const markup = context.crawlerSiteTagsMarkup({
    sites: ['a.com', 'b.com', 'c.com', 'd.com', 'e.com', 'f.com', 'g.com'],
    rules: [{ name: longName }, '短规则'],
  });
  const titles = [...markup.matchAll(/title="([^"]+)"/g)].map(m => m[1]);
  assert.equal(titles.filter(t => /\.com$/.test(t)).length, 5, 'at most five site tags');
  assert.equal(titles.filter(t => !/\.com$/.test(t)).length, 2, 'at most five rule tags');
  assert.ok(titles.includes(longName), 'full name stays in title');
  assert.ok(markup.includes(longName), 'long names render in full inside the tag');
});
