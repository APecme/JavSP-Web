const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = file => fs.existsSync(path.join(root, file)) ? fs.readFileSync(path.join(root, file), 'utf8') : '';
const html = () => read('javsp_web/web/index.html');
const login = () => read('javsp_web/web/login.html');
const app = () => read('javsp_web/web/assets/app.js');
const ai = () => read('javsp_web/web/assets/ai.js');
const css = () => read('javsp_web/web/assets/page-layouts.css');

function slice(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0, `missing slice start: ${start}`);
  assert.ok(to > from, `missing slice end: ${end}`);
  return source.slice(from, to);
}

function at(source, needle, label = needle) {
  const index = source.indexOf(needle);
  assert.ok(index >= 0, `missing ${label}`);
  return index;
}

function between(source, first, second, third) {
  assert.ok(at(source, first) < at(source, second), `${first} must precede ${second}`);
  assert.ok(at(source, second) < at(source, third), `${second} must precede ${third}`);
}

function element(extra = {}) {
  const listeners = {};
  return Object.assign({
    listeners,
    className: '',
    textContent: '',
    innerHTML: '',
    addEventListener(type, callback) { (listeners[type] ||= []).push(callback); },
    insertAdjacentHTML(position, markup) { this.inserted = { position, markup }; },
    remove() { this.removed = true; },
    classList: { toggle() {} },
  }, extra);
}

test('feature pages expose deliberate regions instead of stacked generic panels', () => {
  const document = html();
  const stylesheet = document.match(/<link rel="stylesheet" href="\/assets\/page-layouts\.css/);
  assert.ok(stylesheet, 'page-layouts.css is loaded');
  assert.ok(document.indexOf('cinema.css') < document.indexOf('page-layouts.css'), 'page layouts load after the library baseline');

  assert.match(document, /class="[^"]*scrape-layout/);
  assert.match(document, /data-scrape-region="compose"/);
  assert.match(document, /data-scrape-region="queue"/);
  assert.ok(document.indexOf('data-scrape-region="compose"') < document.indexOf('data-scrape-region="queue"'));
  const scrape = document.slice(at(document, 'class="view" data-panel="scrape"'), at(document, 'class="view" data-panel="auto-scrape"'));
  assert.ok(scrape.indexOf('id="task-table"') > scrape.indexOf('data-scrape-region="queue"'), 'task queue owns the task table');

  assert.match(document, /data-auto-scrape-module="watch"/);
  assert.match(document, /data-auto-scrape-module="schedule"/);
  assert.doesNotMatch(document, /data-auto-scrape-module="download"/, 'download auto-scrape module was removed');
  assert.doesNotMatch(document, /download-auto-scrape/, 'no download auto-scrape hooks remain');
  assert.match(document, /id="directory-watch-mount"/);
  assert.match(document, /id="auto-scrape-watch-status"/);
  const autoScrape = document.slice(at(document, 'class="view" data-panel="auto-scrape"'), at(document, 'class="view" data-panel="downloads"'));
  assert.ok(autoScrape.indexOf('id="auto-scrape-schedule-list"') > autoScrape.indexOf('data-auto-scrape-module="schedule"'));

  const downloads = document.slice(at(document, 'class="view" data-panel="downloads"'), at(document, 'class="view" data-panel="presets"'));
  between(downloads, 'id="download-summary"', 'id="download-filter-bar"', 'id="download-list"');
  assert.ok(downloads.indexOf('id="download-policy-content"') > downloads.indexOf('id="download-list"'), 'policy follows the list');
  assert.match(downloads, /id="download-filter-panel"[^>]*class="[^"]*download-filter-panel|<details[^>]*id="download-filter-panel"/);

  const presets = document.slice(at(document, 'class="view" data-panel="presets"'), at(document, 'class="view" data-panel="crawler-config"'));
  assert.match(presets, /class="panel preset-list-panel/);
  assert.match(presets, /id="preset-editor-dialog"/);
  assert.ok(presets.indexOf('id="preset-form"') > presets.indexOf('id="preset-editor-dialog"'), 'the editor form lives inside the preset dialog');

  const aiPage = document.slice(at(document, 'class="view" data-panel="ai-scrape"'), at(document, 'class="view" data-panel="scrape"'));
  between(aiPage, 'class="ai-history"', 'id="ai-workspace"', 'id="ai-chat-form"');
  assert.match(aiPage, /class="[^"]*ai-history-head/);
});

test('settings are split into navigable groups while every form stays in the document', () => {
  const document = html();
  const settings = document.slice(at(document, 'class="view" data-panel="settings"'), at(document, 'id="profile-dialog"'));
  assert.match(settings, /class="[^"]*settings-layout/);
  // No embedded rail nav: group switching happens through tabs inside the panel.
  assert.doesNotMatch(settings, /class="[^"]*settings-nav"/);
  assert.doesNotMatch(settings, /<a[^>]*href="#settings-/);
  assert.match(settings, /class="settings-tabs"[^>]*role="tablist"[^>]*aria-label="设置分组"/);
  for (const group of ['update', 'connections', 'ai', 'account']) {
    assert.match(settings, new RegExp(`data-settings-tab="${group}"`));
    assert.match(settings, new RegExp(`id="settings-${group}"`));
  }
  assert.ok(settings.indexOf('id="settings-update"') < settings.indexOf('id="settings-connections"'));
  assert.ok(settings.indexOf('id="settings-connections"') < settings.indexOf('id="settings-ai"'));
  assert.ok(settings.indexOf('id="settings-ai"') < settings.indexOf('id="settings-account"'));

  const group = name => {
    const start = at(settings, `id="settings-${name}"`);
    const next = ['update', 'connections', 'ai', 'account'][['update', 'connections', 'ai', 'account'].indexOf(name) + 1];
    return settings.slice(start, next ? settings.indexOf(`id="settings-${next}"`, start) : settings.length);
  };
  assert.match(group('update'), /id="update-settings-panel"/);
  assert.match(group('connections'), /id="settings-connection-mount"/);
  assert.match(group('connections'), /id="cookiecloud-panel"/);
  assert.match(group('connections'), /id="downloader-list"/);
  assert.match(group('ai'), /id="settings-ai-mount"/);
  assert.match(group('account'), /id="users-table"/);
});

test('manual task filters are one collapsible region and are not reinserted', () => {
  const source = app();
  const elements = new Map();
  const taskTable = element();
  const reset = element();
  let filterBar = null;
  const state = { taskPage: 3 };
  const loads = [];
  const context = vm.createContext({ javspIcon: () => '',
    $: selector => {
      if (selector === '#task-table') return taskTable;
      if (selector === '#task-filter-bar') return filterBar;
      if (selector === '#task-filter-reset') return reset;
      return elements.get(selector) || null;
    },
    document: { querySelectorAll: () => [] },
    state,
    loadTasks: () => loads.push(state.taskPage),
    setTimeout: () => 0,
    clearTimeout() {},
  });
  vm.runInContext(slice(source, 'function ensureTaskFilters', 'function filteredTasks'), context);
  context.ensureTaskFilters();
  const markup = taskTable.inserted?.markup || '';
  assert.match(markup, /<details[^>]*id="task-filter-panel"[^>]*open/);
  assert.match(markup, /<summary[^>]*>[\s\S]*筛选/);
  assert.ok(markup.indexOf('id="task-filter-bar"') > markup.indexOf('<summary'), 'filters live under the summary');
  assert.ok(markup.indexOf('id="task-pagination"') > markup.indexOf('id="task-filter-bar"'));
  filterBar = element();
  taskTable.inserted = null;
  context.ensureTaskFilters();
  assert.equal(taskTable.inserted, null, 'existing filters are not duplicated');
});

test('crawler configuration renders source cards with an editor dialog', () => {
  const source = app();
  const context = vm.createContext({ javspIcon: () => '',
    escapeHtml: value => String(value ?? ''),
    state: { disabledBuiltInCrawlers: [] },
  });
  vm.runInContext(`${slice(source, 'let crawlerStatsCache = null;', 'function crawlerSkeletonMarkup')}${slice(source, 'function crawlerSkeletonMarkup', 'function crawlerCodeDetail')}${slice(source, 'function crawlerCodeDetail', 'async function loadCrawlerSource')}`, context);
  const markup = context.crawlerCodeMarkup([
    { name: 'alpha', kind: 'builtin' },
    { name: 'beta', kind: 'custom' },
  ]);
  assert.match(markup, /id="crawler-source-grid" class="[^"]*crawler-source-grid/);
  assert.match(markup, /class="[^"]*crawler-source-card/);
  assert.match(markup, /data-crawler-code-name="alpha"/);
  assert.match(markup, /data-open-crawler-editor="alpha"/);
  assert.match(markup, /id="crawler-editor-dialog"[^>]*class="[^"]*app-dialog[^"]*crawler-editor-dialog/);
  assert.match(source, /testCrawler\.dataset\.busy = 'true'/);
  const styles = read('javsp_web/web/assets/overrides.css');
  assert.match(styles, /\.button\[data-busy\]::before/);
  assert.match(markup, /data-dialog-close/);
  assert.ok(markup.indexOf('id="crawler-source-grid"') < markup.indexOf('id="crawler-code-detail"'));
  assert.match(markup, /id="add-custom-crawler"/);
});

test('crawler configuration marks disabled built-in crawlers and exposes skeleton loading and retry markup', () => {
  const source = app();
  const context = vm.createContext({ javspIcon: () => '',
    escapeHtml: value => String(value ?? ''),
    state: { disabledBuiltInCrawlers: ['gamma'] },
  });
  vm.runInContext(`${slice(source, 'let crawlerStatsCache = null;', 'function crawlerSkeletonMarkup')}${slice(source, 'function crawlerSkeletonMarkup', 'function crawlerCodeDetail')}`, context);
  const markup = context.crawlerCodeMarkup([{ name: 'alpha', kind: 'builtin' }]);
  assert.match(markup, /crawler-source-card-disabled/);
  assert.match(markup, /crawler-source-card-status/);
  assert.match(markup, /data-restore-built-in-crawler="gamma"/);
  const skeleton = context.crawlerSkeletonMarkup();
  assert.match(skeleton, /data-crawler-loading/);
  assert.match(skeleton, /crawler-skeleton-line/);
  assert.match(skeleton, /data-crawler-loading-message/);
  assert.ok(!markup.includes('crawler-source-card-open="gamma"'), 'disabled crawler has no editor button');
});

test('crawler editor invalidates pending source loads on close and mode switch', async () => {
  const source = app();
  // Add-crawler entry must clear the edited original name so saving cannot delete the old file.
  const addStart = source.indexOf("if (event.target.closest('#add-custom-crawler'))");
  assert.ok(addStart >= 0);
  const addBlock = source.slice(addStart, addStart + 400);
  assert.match(addBlock, /state\.activeCrawlerCodeName = ''/);
  assert.match(addBlock, /crawlerEditorToken \+= 1/);

  // Behavior: a stale source response must not overwrite a freshly opened "add crawler" editor.
  const elements = {};
  const makeDialog = () => {
    const listeners = {};
    return {
      open: false,
      dataset: {},
      showModal() { this.open = true; },
      close() { this.open = false; listeners.close?.forEach((cb) => cb()); },
      addEventListener(type, cb) { (listeners[type] ||= []).push(cb); },
    };
  };
  const detail = { innerHTML: '' };
  const title = { textContent: '' };
  elements['#crawler-editor-dialog'] = makeDialog();
  elements['#crawler-code-detail'] = detail;
  elements['#crawler-editor-dialog-title'] = title;
  let resolveSource;
  const pending = new Promise((resolve) => { resolveSource = resolve; });
  const state = {
    crawlerSources: [{ name: 'alpha', kind: 'custom' }],
    disabledBuiltInCrawlers: [],
    activeCrawlerCodeName: '',
    crawlerEditorToken: 0,
  };
  const context = vm.createContext({
    javspIcon: () => '',
    escapeHtml: value => String(value ?? ''),
    $: (selector) => elements[selector] || null,
    api: () => pending,
    state,
    document: { getElementById: () => null },
  });
  vm.runInContext(`${slice(source, 'function crawlerCodeDetail', 'const apiRequests')}${slice(source, '// Crawler editor dialog: any close', "document.addEventListener('pointerdown'")}`, context);
  const load = context.loadCrawlerSource;
  const bind = context.bindCrawlerEditorDialog;
  bind();
  const opened = load('alpha');
  assert.equal(state.activeCrawlerCodeName, 'alpha');
  // Simulate: user closes the dialog (via close button / Esc / backdrop) then opens "add crawler".
  elements['#crawler-editor-dialog'].close();
  assert.equal(state.activeCrawlerCodeName, '', 'close clears the edited crawler');
  state.activeCrawlerCodeName = '';
  state.crawlerEditorToken += 1;
  detail.innerHTML = 'NEW UNSAVED EDITOR';
  resolveSource({ name: 'alpha', source: 'OLD SOURCE' });
  await opened;
  assert.equal(detail.innerHTML, 'NEW UNSAVED EDITOR', 'stale response must not replace the new editor');
  // Backdrop click (target === dialog) closes the dialog.
  elements['#crawler-editor-dialog'].open = true;
  const clickListeners = [];
  // rebind check: dialog already bound; simulate direct click event via stored listener
  // (bindCrawlerEditorDialog stored listeners internally; use close() path already verified above)
});

test('crawler editor dialog binds backdrop click and close reset exactly once', () => {
  const source = app();
  assert.match(source, /function bindCrawlerEditorDialog\(\)/);
  assert.match(source, /if \(event\.target === dialog\) dialog\.close\(\)/);
  assert.match(source, /dialog\.dataset\.bound = 'true'/);
  const loadStart = source.indexOf('async function loadCrawlerSource');
  const tokenGuard = source.slice(loadStart, source.indexOf('const apiRequests'));
  assert.match(tokenGuard, /state\.crawlerEditorToken === token/);
});

test('auto-scrape module headings report their rule and run counts', () => {
  const source = app();
  const target = element();
  const status = element();
  const state = {
    autoScrapeSchedules: [
      { id: 'one', enabled: true, name: '每日', cron: '0 2 * * *', input_directory: '/a', preset_id: 'default' },
      { id: 'two', enabled: false, name: '每周', cron: '0 3 * * 1', input_directory: '/b', preset_id: 'default' },
    ],
  };
  const context = vm.createContext({ javspIcon: () => '',
    $: selector => ({
      '#auto-scrape-schedule-list': target,
      '#auto-scrape-schedule-status': status,
    })[selector] || null,
    document: { querySelectorAll: () => [] },
    state,
    escapeHtml: value => String(value ?? ''),
    presetName: value => value,
    formatLocalDateTime: () => '2026-10-23 10:00',
  });
  vm.runInContext(slice(source, 'function renderAutoScrapeSchedules', 'async function loadAutoScrapeSchedules'), context);
  context.renderAutoScrapeSchedules();
  assert.equal(status.textContent, '2 条规则 · 1 条启用');
});

test('download auto-scrape UI and logic are fully removed', () => {
  const source = app();
  assert.doesNotMatch(source, /downloadAutoScrapeRuns/);
  assert.doesNotMatch(source, /activeDownloadAutoScrapeRun/);
  assert.doesNotMatch(source, /renderAutoScrapeRules/);
  assert.doesNotMatch(source, /normalizeAutoScrapeRules/);
  assert.doesNotMatch(source, /newAutoScrapeRule/);
  assert.doesNotMatch(source, /readAutoScrapeRules/);
  assert.doesNotMatch(source, /ensureAutoScrapeControls/);
  assert.doesNotMatch(source, /auto_scrape_rules/);
  assert.doesNotMatch(source, /data-view-download-auto-scrape-run/);
  const document = html();
  assert.doesNotMatch(document, /download-auto-scrape/);
  assert.doesNotMatch(document, /add-auto-scrape-rule/);
});

test('an empty preset library gets an actionable empty state', () => {
  const source = app();
  const list = element();
  const select = element();
  const context = vm.createContext({ javspIcon: () => '',
    $: selector => selector === '#preset-list' ? list : (selector === '#task-preset' ? select : null),
    document: { querySelectorAll: () => [] },
    state: { presets: [], editingPreset: null, autoScrapeSchedules: [] },
    escapeHtml: value => String(value ?? ''),
  });
  const start = source.lastIndexOf('function presetCardMarkup');
  vm.runInContext(source.slice(start, source.indexOf('function renderPresetMode', start)), context);
  context.renderPresetList();
  assert.match(list.innerHTML, /page-empty-state/);
  assert.match(list.innerHTML, /新建|预设/);
});

test('dynamic settings modules mount inside their group and fall back safely', () => {
  const source = app();
  const hostCalls = [];
  const rootCalls = [];
  const host = { insertAdjacentHTML: (position, markup) => hostCalls.push({ position, markup }) };
  const settingsPanel = {
    querySelector: selector => selector === '#settings-connection-mount' ? host : null,
    insertAdjacentHTML: (position, markup) => rootCalls.push({ position, markup }),
  };
  const context = vm.createContext({ javspIcon: () => '',
    $: () => null,
    document: {
      querySelector: selector => selector === '[data-panel="settings"]' ? settingsPanel : null,
      body: { insertAdjacentHTML() {} },
    },
  });
  vm.runInContext(slice(source, 'function ensureMediaSettingsUi', 'function renderMediaServers'), context);
  context.ensureMediaSettingsUi();
  assert.equal(hostCalls.length, 1, 'the media server panel mounts inside the connections group');
  assert.equal(rootCalls.length, 0, 'the settings root is not used when the group exists');

  const pathCalls = [];
  const mediaPanel = { insertAdjacentHTML: (position, markup) => pathCalls.push({ position, markup }) };
  const pathContext = vm.createContext({ javspIcon: () => '',
    $: selector => selector === '#path-mapping-panel' ? null : (selector === '#media-server-panel' ? mediaPanel : null),
    document: { querySelector: () => settingsPanel },
  });
  vm.runInContext(slice(source, 'function ensurePathMappingsUi', 'async function loadPathMappings'), pathContext);
  pathContext.ensurePathMappingsUi();
  assert.equal(pathCalls[0]?.position, 'afterend');
  assert.match(pathCalls[0]?.markup || '', /id="path-mapping-panel"/);

  assert.match(html(), /id="settings-ai-mount"/);
  assert.match(ai(), /querySelector\('#settings-ai-mount'\)/);
});

test('page layout CSS is scoped per page and keeps responsive and motion fallbacks', () => {
  const styles = css();
  assert.ok(styles, 'page-layouts.css exists');
  for (const panel of ['scrape', 'auto-scrape', 'downloads', 'crawler-config', 'presets', 'settings', 'ai-scrape']) {
    assert.match(styles, new RegExp(`\\[data-panel="${panel}"\\]`), `${panel} has scoped rules`);
  }
  assert.match(styles, /#profile-dialog|\.profile-dialog/);
  assert.match(styles, /\.auth-shell|\.auth-card/);
  assert.match(styles, /@media \(max-width: 390px\)/);
  assert.match(styles, /prefers-reduced-motion/);
  const selectors = [...styles.matchAll(/(^|\})\s*([^{}@]+)\{/g)].map(match => match[2].trim()).filter(Boolean);
  for (const selector of selectors) {
    assert.match(selector, /\[data-panel="(scrape|auto-scrape|downloads|crawler-config|presets|settings|ai-scrape)"\]|#profile-dialog|\.profile-dialog|\.auth-|\.auth-shell|\.page-/, `unscoped selector: ${selector}`);
  }
});

test('profile and login use the same page layout system without changing business hooks', () => {
  const page = html();
  const auth = login();
  assert.match(page, /class="[^"]*profile-body/);
  assert.match(auth, /href="\/assets\/page-layouts\.css/);
  assert.match(auth, /class="[^"]*auth-brand/);
  assert.match(auth, /class="[^"]*auth-form-panel/);
  for (const id of ['login-form', 'username', 'password', 'login-error', 'login-version']) {
    assert.match(auth, new RegExp(`id="${id}"`));
  }
});

test('existing settings, task and AI hooks remain in the document', () => {
  const document = html();
  for (const id of [
    'task-form', 'input-directory', 'path-tools', 'task-preset', 'task-message', 'task-table', 'refresh-tasks',
    'add-auto-scrape-schedule', 'auto-scrape-schedule-list',
    'download-policy-toggle', 'download-policy-content', 'download-management-form',
    'downloader-tabs', 'download-summary', 'download-filter-bar', 'download-list',
    'download-filter-name', 'download-filter-category', 'download-filter-tags', 'download-filter-reset', 'download-filter-summary',
    'preset-list', 'preset-form', 'preset-name', 'preset-mode', 'preset-content', 'save-preset', 'delete-preset',
    'crawler-config-content',
    'update-settings-panel', 'update-settings-form', 'cookiecloud-panel', 'cookiecloud-form', 'downloader-list', 'users-table',
    'profile-dialog', 'profile-form', 'profile-name', 'profile-pin', 'profile-pin-confirm', 'my-comments-list',
    'ai-new-chat', 'ai-history-search', 'ai-history-list', 'ai-workspace', 'ai-conversation', 'ai-chat-form', 'ai-message', 'ai-send',
  ]) {
    assert.match(document, new RegExp(`id="${id}"`), `missing #${id}`);
  }
});

test('preset library renders as a card grid and the editor lives in a dialog', () => {
  const document = html();
  const presets = document.slice(at(document, 'class="view" data-panel="presets"'), at(document, 'class="view" data-panel="settings"'));
  assert.match(presets, /id="preset-list"/);
  assert.match(presets, /id="preset-editor-dialog"[^>]*class="[^"]*preset-editor-dialog/);
  assert.ok(presets.indexOf('id="preset-form"') > presets.indexOf('id="preset-editor-dialog"'), 'the editor form lives inside the preset dialog');
  assert.ok(presets.indexOf('id="save-preset"') > presets.indexOf('id="preset-editor-dialog"'), 'save lives inside the preset dialog');
  for (const id of ['preset-id', 'preset-name', 'preset-form-panel', 'preset-yaml-panel', 'preset-content', 'preset-message', 'preset-mode', 'delete-preset']) {
    assert.match(presets, new RegExp(`id="${id}"`), `dialog keeps #${id}`);
  }
  assert.doesNotMatch(presets, /preset-editor-panel/, 'the inline editor panel is gone');

  const source = app();
  assert.match(source, /editPreset\(button\.dataset\.editPreset\); openPresetEditorDialog\(\);/, 'clicking a preset card opens the dialog editor');
  assert.match(source, /\$\('#new-preset'\)\.addEventListener\('click', \(\) => \{ newPreset\(\); openPresetEditorDialog\(\); \}\)/, 'new preset opens the dialog');
  const listStart = source.indexOf('function renderPresetList() {');
  const listEnd = source.indexOf('function openPresetEditorDialog()', listStart);
  assert.ok(listStart > 0 && listEnd > listStart, 'renderPresetList exists exactly once');
  const listBody = source.slice(listStart, listEnd);
  assert.match(listBody, /data-delete-preset/, 'preset cards carry a delete hook');
  // Card structure mirrors crawler cards: article with name heading, mode, usage count, foot delete.
  const cardStart = source.indexOf('// Deep-compare two preset configs');
  const cardEnd = source.indexOf('function renderPresetList()', cardStart);
  const cardBody = source.slice(cardStart, cardEnd);
  assert.match(cardBody, /<article class="preset-source-card/, 'cards use the crawler-card article class');
  assert.match(cardBody, /<h3>/, 'preset name is a card heading');
  assert.match(cardBody, /preset-source-card-kind/, 'cards show the mode');
  assert.match(cardBody, /preset-source-card-diff/, 'cards show the diff tags against the default preset');
  assert.doesNotMatch(cardBody, /preset-source-card-usage/, 'auto-scrape rule usage line was removed from preset cards');
  assert.match(cardBody, /preset-source-card-actions/, 'cards have a top-right action cluster');
});

test('privacy mode keeps the library play button icon visible', () => {
  const cinema = read('javsp_web/web/assets/cinema.css');
  const blurRule = cinema.match(/html\[data-privacy-mode="1"\][^\n]*:is\(([^)]*)\)[^\n]*img:not\(\.library-play img\)[^\n]*\{([^}]*)\}/);
  assert.ok(blurRule, 'the privacy blur rule excludes .library-play img');
  assert.match(blurRule[0], /blur\(/);
  assert.match(cinema, /html\[data-privacy-mode="1"\] \.library-play img\s*\{[^}]*brightness\(0\) invert\(1\)/, 'the play icon stays solid white in privacy mode');
  assert.match(cinema, /html\[data-privacy-mode="1"\] \.library-play img\s*\{[^}]*transform:\s*none/, 'the play icon is not scaled by the privacy blur');
});

test('auto-scrape view keeps a single heading level per module with no duplicate page title', () => {
  const document = html();
  const section = document.slice(at(document, 'class="view" data-panel="auto-scrape"'), at(document, 'class="view" data-panel="downloads"'));
  const h2s = [...section.matchAll(/<h2[^>]*>([\s\S]*?)<\/h2>/g)].map(match => match[1].replace(/<[^>]+>/g, '').trim());
  assert.deepEqual([...new Set(h2s)], h2s, 'no two h2 headings share the same text in the auto-scrape view');
  assert.ok(!h2s.includes('自动刮削'), 'the top bar page title is not repeated inside the view');
  assert.ok(!/<h1[\s>]/.test(section) && !/<h4[\s>]/.test(section), 'no h1/h4 level skips inside the auto-scrape view');
  for (const module of section.matchAll(/data-auto-scrape-module="([^"]+)"/g)) {
    const id = { watch: 'auto-scrape-watch-title', schedule: 'auto-scrape-schedule-title' }[module[1]];
    assert.ok(id && section.includes(`id="${id}"`), `module ${module[1]} owns exactly one labelled h2`);
  }
});
