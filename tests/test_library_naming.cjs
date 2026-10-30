// The visible name of the overview view is 片库; internal overview hooks stay
// unchanged so saved views, deep links and data requests keep working.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const html = () => read('javsp_web/web/index.html');
const source = read('javsp_web/web/assets/app.js');

function element(dataset = {}) {
  const classes = new Set();
  return {
    dataset,
    classes,
    classList: {
      toggle(name, force) {
        if (force === undefined) classes.has(name) ? classes.delete(name) : classes.add(name);
        else if (force) classes.add(name);
        else classes.delete(name);
      },
      contains: name => classes.has(name),
    },
  };
}

function showViewHarness() {
  const start = source.indexOf('function showView(');
  assert.ok(start > 0, 'app.js still exposes showView');
  const sourceText = source.slice(start, source.indexOf('function ensurePathMappingsUi(', start));
  const elements = new Map();
  const text = selector => {
    if (!elements.has(selector)) elements.set(selector, { textContent: '' });
    return elements.get(selector);
  };
  const navs = ['overview', 'scrape', 'auto-scrape', 'downloads', 'settings'].map(view => element({ view }));
  const panels = ['overview', 'scrape', 'auto-scrape', 'downloads', 'settings'].map(panel => element({ panel }));
  const documentElement = { removed: [], removeAttribute(name) { this.removed.push(name); } };
  let loads = 0;
  const storage = { items: {}, setItem(key, value) { this.items[key] = value; } };
  // Stubs for the per-view loaders showView triggers; none of them are under test here.
  const noop = () => {};
  const context = vm.createContext({
    document: {
      documentElement,
      querySelectorAll: selector => (selector === '.nav-item' ? navs : panels),
    },
    $: text,
    state: { tasks: [{ id: 'old' }], tasksSignature: 'old' },
    localStorage: storage,
    window: {},
    loadTasks: () => { loads += 1; },
    ensureTaskFilters: noop, loadPresets: noop, loadCrawlerNames: noop, loadPathTools: noop,
    loadDownloadManagement: noop, loadDownloads: noop, loadCrawlerConfig: noop,
    loadAutoScrapeSchedules: noop, ensureMediaSettingsUi: noop, ensurePathMappingsUi: noop,
    loadUsers: noop, loadDownloaders: noop, loadMediaServers: noop, loadPathMappings: noop,
    loadCookieCloud: noop, loadUpdateSettings: noop,
    applySettingsGroup: noop, SETTINGS_GROUPS: ['update', 'connections', 'ai', 'account'],
    currentSettingsGroup: () => 'update',
  });
  vm.runInContext(sourceText, context);
  return { showView: context.showView, text, navs, panels, storage, documentElement, loads: () => loads };
}

test('the sidebar and header present the overview view as 片库', () => {
  const document = html();
  const nav = document.match(/<button[^>]*data-view="overview"[^>]*>([\s\S]*?)<\/button>/);
  assert.ok(nav, 'the overview navigation button keeps its data-view hook');
  assert.equal(nav[1].replace(/<[^>]*>/g, '').trim(), '片库');
  assert.equal(document.match(/<h1 id="section-title">([^<]*)<\/h1>/)?.[1], '片库');
  assert.match(document, /data-panel="overview"/, 'the overview panel hook is unchanged');
});

test('showView labels overview as 片库 and keeps the overview persistence key', () => {
  const view = showViewHarness();
  view.showView('overview');
  assert.equal(view.text('#section-title').textContent, '片库');
  assert.equal(view.text('#section-eyebrow').textContent, '片区');
  assert.equal(view.storage.items['javsp-web.active-view'], 'overview', 'saved view key and value stay compatible');
  assert.equal(view.navs.find(nav => nav.dataset.view === 'overview').classList.contains('active'), true);
  assert.equal(view.panels.find(panel => panel.dataset.panel === 'overview').classList.contains('active'), true);
  assert.equal(view.loads(), 1, 'overview still refreshes the task list');
});

test('showView keeps the other view titles untouched', () => {
  const view = showViewHarness();
  for (const [name, title] of [['scrape', '手动刮削'], ['auto-scrape', '自动刮削'], ['downloads', '下载管理'], ['settings', '系统设置']]) {
    view.showView(name);
    assert.equal(view.text('#section-title').textContent, title, name);
    assert.equal(view.storage.items['javsp-web.active-view'], name);
  }
});

test('saved overview view still restores the library panel on load', () => {
  const document = html();
  assert.match(document, /localStorage\.getItem\('javsp-web\.active-view'\)/, 'the saved view is still read');
  assert.match(document, /html\[data-initial-view="overview"\] \[data-panel="overview"\]/, 'a saved overview paints before scripts run');
  assert.match(source, /if \(savedView && document\.querySelector\(`\[data-panel="\$\{savedView\}"\]`\)/, 'the restore path is unchanged');
  assert.match(source, /else showView\('overview'\)/, 'the default view remains overview');
});

test('user-facing copy no longer calls this view 概览', () => {
  for (const name of ['javsp_web/web/index.html', 'javsp_web/web/assets/app.js', 'javsp_web/web/login.html', 'javsp_web/skills/javsp-scrape/SKILL.md', 'scripts/build_demo.py']) {
    assert.doesNotMatch(read(name), /概览/, `${name} shows the new name`);
  }
});
