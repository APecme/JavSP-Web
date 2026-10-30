// Sidebar navigation behaviour (desktop collapse / phone drawer) without a browser.
// The visual widths are verified in a real browser; these tests cover state, storage
// compatibility, focus, ARIA and the DOM contract that app.js depends on.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const NAVIGATION = path.join(root, 'javsp_web/web/assets/navigation.js');
const MOBILE_QUERY = '(max-width: 800px)';

function slice(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0, `missing slice start: ${start}`);
  assert.ok(to > from, `missing slice end: ${end}`);
  return source.slice(from, to);
}

/* --- minimal DOM: only the APIs navigation.js is allowed to use. --- */
function buildDom({ mobile = false, stored = null, views = ['overview', 'scrape', 'ai-scrape', 'auto-scrape', 'downloads', 'crawler-config', 'presets', 'settings'] } = {}) {
  const storage = new Map();
  if (stored !== null) storage.set('javsp-web.sidebar-collapsed', stored);
  const focusLog = [];
  const observers = [];
  const documentListeners = {};

  const makeClassList = (element) => {
    const set = new Set();
    const changed = () => { if (element.onClassChange) element.onClassChange(); };
    return {
      add(...names) { names.forEach(name => set.add(name)); changed(); },
      remove(...names) { names.forEach(name => set.delete(name)); changed(); },
      contains(name) { return set.has(name); },
      toggle(name, force) {
        const want = force === undefined ? !set.has(name) : Boolean(force);
        if (want) set.add(name); else set.delete(name);
        changed();
        return want;
      },
      values() { return [...set]; },
    };
  };

  const element = (name, attrs = {}) => {
    const node = {
      name, listeners: {}, children: {}, attrs: { ...attrs }, hidden: false, textContent: '',
      addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); },
      removeEventListener(type, listener) { this.listeners[type] = (this.listeners[type] || []).filter(fn => fn !== listener); },
      fire(type, extra = {}) {
        const event = {
          type, target: this, defaultPrevented: false, propagationStopped: false, key: '',
          preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.propagationStopped = true; },
          ...extra,
        };
        for (const listener of [...(this.listeners[type] || [])]) listener(event);
        return event;
      },
      getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
      setAttribute(name, value) { this.attrs[name] = String(value); },
      removeAttribute(name) { delete this.attrs[name]; },
      hasAttribute(name) { return name in this.attrs; },
      focus() { document.activeElement = this; focusLog.push(this.name); },
      querySelector(selector) { return this.children[selector] || null; },
      querySelectorAll(selector) { return this.lists?.[selector] || this.lists?.all || []; },
    };
    node.classList = makeClassList(node);
    return node;
  };

  const document = {
    activeElement: null, listeners: {}, documentElement: element('html'), dialogOpen: false,
    getElementById(id) { return this.ids?.[id] || null; },
    querySelector(selector) {
      if (selector === '.app-shell') return this.shell || null;
      if (selector === 'dialog[open]') return this.dialogOpen ? element('dialog') : null;
      return null;
    },
    querySelectorAll(selector) { return selector === '.nav-item' ? this.items || [] : []; },
    addEventListener(type, listener) { (documentListeners[type] ||= []).push(listener); },
    removeEventListener(type, listener) { documentListeners[type] = (documentListeners[type] || []).filter(fn => fn !== listener); },
    fire(type, extra = {}) {
      const event = {
        type, target: this, defaultPrevented: false, key: '',
        preventDefault() { this.defaultPrevented = true; }, stopPropagation() {},
        ...extra,
      };
      for (const listener of [...(documentListeners[type] || [])]) listener(event);
      return event;
    },
  };

  const shell = element('shell');
  const sidebar = element('sidebar');
  const toggle = element('sidebar-toggle');
  const backdrop = element('sidebar-backdrop');
  const nav = element('sidebar-nav');
  const heading = element('section-title');
  backdrop.hidden = true;

  const items = views.map((view, index) => {
    const item = element(`item:${view}`);
    item.dataset = { view };
    if (index === 0) item.classList.add('active');
    const label = element(`label:${view}`);
    label.textContent = view;
    item.children['.nav-item-label'] = label;
    item.closest = selector => (selector === '.nav-item' ? item : null);
    return item;
  });
  nav.lists = { all: [toggle, ...items] };
  sidebar.lists = { all: [toggle, ...items] };
  document.ids = { sidebar, 'sidebar-toggle': toggle, 'sidebar-backdrop': backdrop, 'sidebar-nav': nav, 'section-title': heading };
  document.shell = shell;
  document.items = items;

  const handlers = [];
  const media = {
    media: MOBILE_QUERY, matches: mobile,
    addEventListener(type, listener) { if (type === 'change') handlers.push(listener); },
    removeEventListener(type, listener) { const at = handlers.indexOf(listener); if (at >= 0) handlers.splice(at, 1); },
  };
  const window = {
    matchMedia(query) { assert.equal(query, MOBILE_QUERY); return media; },
    localStorage: {
      getItem(key) { return storage.has(key) ? storage.get(key) : null; },
      setItem(key, value) { storage.set(key, String(value)); },
    },
    MutationObserver: class { constructor(callback) { this.callback = callback; observers.push(this); } observe() {} disconnect() {} },
  };

  const context = vm.createContext({ window, document, console });
  vm.runInContext(fs.readFileSync(NAVIGATION, 'utf8'), context);
  assert.ok(context.window.JavspNavigation, 'navigation.js must expose window.JavspNavigation');
  context.window.JavspNavigation.init();

  return {
    window, document, shell, sidebar, toggle, backdrop, nav, heading, items, media, storage, focusLog, observers,
    flush() { observers.forEach(observer => observer.callback([{ type: 'attributes' }], observer)); },
    setMobile(next) { media.matches = next; handlers.forEach(handler => handler({ matches: next, media: MOBILE_QUERY })); },
  };
}

test('desktop restores collapse from the legacy storage key without rewriting it', () => {
  for (const [stored, collapsed] of [['1', true], ['0', false], [null, false]]) {
    const dom = buildDom({ stored });
    assert.equal(dom.shell.classList.contains('sidebar-collapsed'), collapsed, `stored=${stored}`);
    assert.equal(dom.toggle.getAttribute('aria-expanded'), String(!collapsed));
    assert.equal(dom.toggle.getAttribute('aria-label'), collapsed ? '展开侧边栏' : '收起侧边栏');
    assert.equal(dom.toggle.getAttribute('title'), collapsed ? '展开侧边栏' : '收起侧边栏');
    assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), false);
    assert.equal(dom.backdrop.hidden, true);
    assert.equal(dom.storage.get('javsp-web.sidebar-collapsed') ?? null, stored, 'init must not rewrite the stored preference');
  }
});

test('desktop toggle persists collapse and never touches the mobile drawer', () => {
  const dom = buildDom();
  dom.toggle.fire('click');
  assert.equal(dom.shell.classList.contains('sidebar-collapsed'), true);
  assert.equal(dom.storage.get('javsp-web.sidebar-collapsed'), '1');
  assert.equal(dom.toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), false);
  assert.equal(dom.backdrop.hidden, true);

  dom.toggle.fire('click');
  assert.equal(dom.shell.classList.contains('sidebar-collapsed'), false);
  assert.equal(dom.storage.get('javsp-web.sidebar-collapsed'), '0');
  assert.equal(dom.toggle.getAttribute('aria-expanded'), 'true');
});

test('phone toggle opens a drawer with a backdrop, expanded state and focus on the current view', () => {
  const dom = buildDom({ mobile: true });
  assert.equal(dom.toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(dom.toggle.getAttribute('aria-label'), '打开导航菜单');

  dom.toggle.fire('click');
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), true);
  assert.equal(dom.backdrop.hidden, false);
  assert.equal(dom.toggle.getAttribute('aria-expanded'), 'true');
  assert.equal(dom.toggle.getAttribute('aria-label'), '关闭导航菜单');
  assert.equal(dom.focusLog.at(-1), 'item:overview', 'focus moves into the drawer');
  assert.equal(dom.storage.has('javsp-web.sidebar-collapsed'), false, 'drawer state is not persisted');
});

test('a hidden or disabled active option does not steal drawer focus', () => {
  const dom = buildDom({ mobile: true });
  dom.items[0].hidden = true;
  dom.toggle.fire('click');
  assert.equal(dom.focusLog.at(-1), 'sidebar-toggle');

  const disabled = buildDom({ mobile: true });
  disabled.items[0].disabled = true;
  disabled.toggle.fire('click');
  assert.equal(disabled.focusLog.at(-1), 'sidebar-toggle');
});

test('choosing a phone option closes the drawer and moves focus to the view heading', () => {
  const dom = buildDom({ mobile: true });
  dom.toggle.fire('click');
  dom.nav.fire('click', { target: dom.items[3] });
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), false);
  assert.equal(dom.backdrop.hidden, true);
  assert.equal(dom.toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(dom.focusLog.at(-1), 'section-title');
  assert.equal(dom.heading.getAttribute('tabindex'), '-1');
});

test('desktop option selection keeps the sidebar mode untouched', () => {
  const dom = buildDom();
  dom.nav.fire('click', { target: dom.items[2] });
  assert.equal(dom.shell.classList.contains('sidebar-collapsed'), false);
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), false);
  assert.equal(dom.backdrop.hidden, true);
});

test('Escape and the backdrop close the drawer and restore focus to the toggle', () => {
  const dom = buildDom({ mobile: true });
  dom.toggle.fire('click');
  const escape = dom.document.fire('keydown', { key: 'Escape' });
  assert.equal(escape.defaultPrevented, true);
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), false);
  assert.equal(dom.focusLog.at(-1), 'sidebar-toggle');
  assert.equal(dom.backdrop.hidden, true);

  dom.toggle.fire('click');
  dom.backdrop.fire('click');
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), false);
  assert.equal(dom.focusLog.at(-1), 'sidebar-toggle');

  const closed = dom.document.fire('keydown', { key: 'Escape' });
  assert.equal(closed.defaultPrevented, false, 'Escape outside the drawer must be left alone');
});

test('Escape leaves a native dialog to close itself', () => {
  const dom = buildDom({ mobile: true });
  dom.toggle.fire('click');
  dom.document.dialogOpen = true;
  const escape = dom.document.fire('keydown', { key: 'Escape' });
  assert.equal(escape.defaultPrevented, false);
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), true);
});

test('Tab is trapped inside the open drawer', () => {
  const dom = buildDom({ mobile: true });
  dom.toggle.fire('click');
  dom.document.activeElement = dom.items.at(-1);
  const forward = dom.document.fire('keydown', { key: 'Tab' });
  assert.equal(forward.defaultPrevented, true);
  assert.equal(dom.focusLog.at(-1), 'sidebar-toggle');

  dom.document.activeElement = dom.toggle;
  const backward = dom.document.fire('keydown', { key: 'Tab', shiftKey: true });
  assert.equal(backward.defaultPrevented, true);
  assert.equal(dom.focusLog.at(-1), 'item:settings');
});

test('desktop collapse and phone drawer stay independent across the breakpoint', () => {
  const dom = buildDom({ stored: '1' });
  assert.equal(dom.shell.classList.contains('sidebar-collapsed'), true);

  dom.setMobile(true);
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), false);
  assert.equal(dom.toggle.getAttribute('aria-expanded'), 'false');
  dom.toggle.fire('click');
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), true);
  assert.equal(dom.storage.get('javsp-web.sidebar-collapsed'), '1', 'opening the drawer must not clear the desktop preference');

  dom.setMobile(false);
  assert.equal(dom.sidebar.classList.contains('sidebar-drawer-open'), false, 'leaving phone width closes the drawer');
  assert.equal(dom.shell.classList.contains('sidebar-collapsed'), true, 'desktop preference survives');
  assert.equal(dom.toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(dom.storage.get('javsp-web.sidebar-collapsed'), '1');
});

test('aria-current follows the active view, including changes made by app.js', () => {
  const dom = buildDom();
  assert.equal(dom.items[0].getAttribute('aria-current'), 'page');
  for (const item of dom.items.slice(1)) assert.equal(item.getAttribute('aria-current'), null);

  dom.items[0].classList.remove('active');
  dom.items[4].classList.add('active');
  dom.flush();
  assert.equal(dom.items[0].getAttribute('aria-current'), null);
  assert.equal(dom.items[4].getAttribute('aria-current'), 'page');
});

test('label fallbacks give every option a name and title', () => {
  const dom = buildDom();
  // app.js sets titles today; navigation.js must still name the rail icons without it.
  for (const item of dom.items) assert.equal(item.getAttribute('title'), item.dataset.view);
});

test('collapsed rails use real SVG icons, not ::first-letter fake glyphs', () => {
  const css = read('javsp_web/web/assets/navigation.css');
  assert.doesNotMatch(css, /first-letter/, 'no ::first-letter pseudo-icon rules anywhere');
  // Collapsed rails must still hide the text label accessibly instead of styling letters.
  for (const scope of ['.app-shell.sidebar-collapsed .nav-item-label', '.sidebar .nav-item-label']) {
    const at = css.indexOf(scope);
    assert.ok(at >= 0, `missing ${scope}`);
    const block = css.slice(at, css.indexOf('}', at));
    assert.match(block, /clip-path:\s*inset\(50%\)/, `${scope} keeps the screen-reader-only label`);
  }
  // Three-tier width contract stays put.
  assert.match(css, /grid-template-columns:\s*240px minmax\(0, 1fr\)/, 'desktop 240px');
  assert.match(css, /\.app-shell\.sidebar-collapsed \{\s*grid-template-columns:\s*72px/, 'desktop collapsed 72px');
  assert.match(css, /grid-template-columns:\s*56px minmax\(0, 1fr\)/, 'phone 56px');
});

test('the console keeps the navigation DOM contract and drops the old toggle owner', () => {
  const html = read('javsp_web/web/index.html');
  const aside = slice(html, '<aside class="sidebar"', '</aside>');
  const topbar = slice(html, '<header class="topbar"', '</header>');
  assert.match(aside, /<nav class="nav" id="sidebar-nav"/);
  assert.doesNotMatch(topbar, /<nav|nav-item|data-view=/);
  assert.match(html, /id="sidebar-backdrop"/);
  assert.match(html, /<script defer src="\/assets\/navigation\.js\?v=__ASSET_VERSION__"><\/script>/);
  assert.match(html, /<link rel="stylesheet" href="\/assets\/navigation\.css\?v=__ASSET_VERSION__">/);

  const views = ['hot', 'overview', 'download-script', 'ai-scrape', 'scrape', 'auto-scrape', 'downloads', 'crawler-config', 'presets', 'settings'];
  for (const view of views) assert.match(aside, new RegExp(`data-view="${view}"`), view);
  for (const id of ['ai-scrape-nav', 'auto-scrape-nav', 'crawler-config-nav', 'settings-nav']) {
    assert.match(aside, new RegExp(`id="${id}"`), id);
  }
  // Grouping: 片区 → 工作区 → 配置, each announced by a nav-label. 片区 = 热片/片库; 工作区 = 下片/AI 刮削/手动刮削/自动刮削/下载管理.
  const labels = [...aside.matchAll(/<p class="nav-label">([^<]+)<\/p>/g)].map(m => m[1]);
  assert.deepEqual(labels, ['片区', '工作区', '配置'], 'sidebar group labels');
  const hotPos = aside.indexOf('data-view="hot"');
  const overviewPos = aside.indexOf('data-view="overview"');
  const aiPos = aside.indexOf('data-view="ai-scrape"');
  const scrapePos = aside.indexOf('data-view="scrape"');
  const downloadsPos = aside.indexOf('data-view="downloads"');
  const crawlerPos = aside.indexOf('data-view="crawler-config"');
  const presetsPos = aside.indexOf('data-view="presets"');
  const settingsPos = aside.indexOf('data-view="settings"');
  assert.ok(overviewPos < aiPos && aiPos < scrapePos, 'AI 刮削 sits before 手动刮削 inside 工作区');
  assert.ok(downloadsPos < crawlerPos && crawlerPos < presetsPos && presetsPos < settingsPos, '配置 group order');
  assert.ok(hotPos < overviewPos, '热片 before 片库 inside 片区');
  const downloadPos = aside.indexOf('data-view="download-script"');
  assert.ok(overviewPos < downloadPos && downloadPos < aiPos, '下片 first inside 工作区, after 片区 group');
  const buttons = [...aside.matchAll(/<button class="nav-item[^"]*"[^>]*data-view="([^"]+)"[^>]*>([\s\S]*?)<\/button>/g)];
  assert.equal(buttons.length, views.length);
  assert.deepEqual(buttons.map(([, view]) => view), views, 'nav item order: 热片/片库 (片区), then 下片/工作区, then 配置');
  for (const [, view, body] of buttons) {
    assert.match(body, /<svg class="nav-item-icon"[^>]*aria-hidden="true"[^>]*>/, `${view}: decorative icon`);
    assert.match(body, /<span class="nav-item-label">[^<]+<\/span>/, `${view}: visible label`);
  }
  assert.match(aside, /data-view="overview"[^>]*aria-current="page"/);

  const login = read('javsp_web/web/login.html');
  assert.doesNotMatch(login, /navigation\.(css|js)|sidebar|nav-item/);

  const app = read('javsp_web/web/assets/app.js');
  assert.doesNotMatch(app, /setSidebarCollapsed|javsp-web\.sidebar-collapsed|#sidebar-toggle/, 'navigation.js is the single owner of the sidebar toggle');
});

test('a page without a sidebar is left alone', () => {
  const context = vm.createContext({
    window: { matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }), localStorage: { getItem: () => null, setItem() {} } },
    document: { querySelector: () => null, getElementById: () => null, querySelectorAll: () => [], addEventListener() {} },
    console,
  });
  vm.runInContext(fs.readFileSync(NAVIGATION, 'utf8'), context);
  assert.doesNotThrow(() => context.window.JavspNavigation.init());
});
