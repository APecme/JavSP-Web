const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = file => fs.existsSync(path.join(root, file)) ? fs.readFileSync(path.join(root, file), 'utf8') : '';
const source = () => read('javsp_web/web/assets/theme.js');
const bootstrap = file => {
  const html = read(file);
  const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].find(match => match[1].includes('javsp-web.theme'));
  assert.ok(script, `${file}: initialize theme before styles load`);
  assert.ok(script.index < html.search(/<style\b|<link\b[^>]*rel="stylesheet"/), `${file}: theme initialized too late`);
  assert.match(html.match(/<link\b[^>]*rel="stylesheet"[^>]*>/)?.[0] || '', /theme\.css/);
  return script[1];
};

function browser({ stored = null, dark = false, blocked = false, legacy = false } = {}) {
  const values = new Map(stored === null ? [] : [['javsp-web.theme', stored]]);
  const events = {};
  const media = { matches: dark, listeners: [] };
  media[legacy ? 'addListener' : 'addEventListener'] = (...args) => media.listeners.push(args.at(-1));
  const button = {
    attributes: {}, listeners: {},
    setAttribute(name, value) { this.attributes[name] = String(value); },
    addEventListener(name, listener) { this.listeners[name] = listener; },
  };
  const document = {
    documentElement: { dataset: {}, style: {}, classList: { add() {}, remove() {} } },
    querySelectorAll: () => [button],
  };
  const storage = {
    getItem(key) { if (blocked) throw Error('Storage denied'); return values.get(key) ?? null; },
    setItem(key, value) { if (blocked) throw Error('Storage denied'); values.set(key, value); },
  };
  const context = vm.createContext({
    document, localStorage: storage, matchMedia: () => media,
    requestAnimationFrame: callback => callback(),
    addEventListener: (name, callback) => { events[name] = callback; },
  });
  context.window = context;
  const initialize = () => {
    vm.runInContext(bootstrap('javsp_web/web/index.html'), context);
    vm.runInContext(source(), context);
    assert.ok(context.JavspTheme, 'theme controller is available');
  };
  const systemChange = matches => { media.matches = matches; media.listeners.forEach(listener => listener({ matches })); };
  return { context, document, button, values, storage, events, systemChange, initialize };
}

test('login, console and generated demo initialize the same theme before their first stylesheet', () => {
  const consoleScript = bootstrap('javsp_web/web/index.html');
  assert.equal(bootstrap('javsp_web/web/login.html'), consoleScript);
  assert.equal(bootstrap('docs/demo.html'), consoleScript);
});

test('first paint follows system light or dark without a saved preference', () => {
  for (const [dark, want] of [[false, 'light'], [true, 'dark']]) {
    const b = browser({ dark }); b.initialize();
    assert.equal(b.document.documentElement.dataset.theme, want);
    assert.equal(b.document.documentElement.style.colorScheme, want);
    assert.equal(b.context.JavspTheme.get(), want);
    assert.equal(b.values.size, 0, 'system selection must not persist a manual preference');
  }
});

test('valid saved preference overrides system and survives a new page', () => {
  const b = browser({ stored: 'light', dark: true }); b.initialize();
  assert.equal(b.context.JavspTheme.get(), 'light');
  b.systemChange(false); b.systemChange(true);
  assert.equal(b.context.JavspTheme.get(), 'light');
});

test('invalid preferences and denied storage safely fall back to the system', () => {
  for (const options of [{ stored: 'invalid', dark: true }, { blocked: true, dark: true }]) {
    const b = browser(options); b.initialize();
    assert.equal(b.context.JavspTheme.get(), 'dark');
    b.systemChange(false);
    assert.equal(b.context.JavspTheme.get(), 'light');
    assert.doesNotThrow(() => b.context.JavspTheme.toggle());
    assert.equal(b.context.JavspTheme.get(), 'dark');
    b.systemChange(false);
    assert.equal(b.context.JavspTheme.get(), 'dark', 'manual choice remains effective if storage is denied');
  }
});

test('native button click switches theme, persists preference and exposes the pressed state', () => {
  const b = browser(); b.initialize();
  assert.equal(b.button.attributes['aria-pressed'], 'false');
  b.button.listeners.click();
  assert.equal(b.values.get('javsp-web.theme'), 'dark');
  assert.equal(b.document.documentElement.dataset.theme, 'dark');
  assert.equal(b.button.attributes['aria-pressed'], 'true');
  assert.equal(b.button.title, '切换到明亮模式');
  b.context.JavspTheme.toggle();
  assert.equal(b.document.documentElement.dataset.theme, 'light');
  assert.equal(b.button.attributes['aria-pressed'], 'false');
  assert.equal(b.button.title, '切换到黑暗模式');
});

test('system changes follow live until a manual selection is made, including legacy matchMedia', () => {
  for (const legacy of [false, true]) {
    const b = browser({ legacy }); b.initialize();
    b.systemChange(true);
    assert.equal(b.context.JavspTheme.get(), 'dark');
    b.context.JavspTheme.set('light'); b.systemChange(true);
    assert.equal(b.context.JavspTheme.get(), 'light');
  }
});

test('another tab changes the theme, clearing its preference resumes system following', () => {
  const b = browser(); b.initialize();
  b.events.storage({ key: 'unrelated', newValue: 'dark', storageArea: b.storage });
  assert.equal(b.context.JavspTheme.get(), 'light');
  b.events.storage({ key: 'javsp-web.theme', newValue: 'dark', storageArea: {} });
  assert.equal(b.context.JavspTheme.get(), 'light', 'sessionStorage cannot change theme');
  b.events.storage({ key: 'javsp-web.theme', newValue: 'dark', storageArea: b.storage });
  assert.equal(b.context.JavspTheme.get(), 'dark');
  assert.equal(b.button.attributes['aria-pressed'], 'true');
  b.events.storage({ key: 'javsp-web.theme', newValue: null, storageArea: b.storage });
  assert.equal(b.context.JavspTheme.get(), 'light');
  b.systemChange(true); assert.equal(b.context.JavspTheme.get(), 'dark');
  b.context.JavspTheme.set('light');
  b.events.storage({ key: null, newValue: null, storageArea: b.storage });
  assert.equal(b.context.JavspTheme.get(), 'dark');
});

test('invalid API choices do not change the current theme or stored preference', () => {
  const b = browser({ stored: 'dark' }); b.initialize();
  b.context.JavspTheme.set('sepia');
  assert.equal(b.context.JavspTheme.get(), 'dark');
  assert.equal(b.values.get('javsp-web.theme'), 'dark');
});

test('every migrated color token resolves and fixed artwork colors are explicitly marked', () => {
  const files = ['theme.css', 'app.css', 'overrides.css', 'cinema.css'];
  const styles = files.map(file => read(`javsp_web/web/assets/${file}`));
  const definitions = new Set([...styles.join('\n').matchAll(/(--[\w-]+)\s*:/g)].map(m => m[1]));
  for (const [i, css] of styles.entries()) {
    for (const match of css.matchAll(/var\((--[\w-]+)/g)) assert.ok(definitions.has(match[1]) || ['--progress', '--i', '--hue', '--tone', '--title-scale'].includes(match[1]), `${files[i]}: undefined ${match[1]}`);
  }
  assert.ok(definitions.has('--control-border'), 'interactive boundaries need their own theme token');
  for (const name of ['app.css', 'overrides.css']) {
    const css = read(`javsp_web/web/assets/${name}`).replace(/\/\*[\s\S]*?\*\//g, match => match.includes('theme: fixed') ? match : '');
    for (const rule of css.matchAll(/([^{}]*)\{([^{}]*)\}/g)) {
      for (const declaration of rule[2].split(';')) {
        if (/#[\da-f]{3,8}\b|rgba?\(|:\s*(?:white|black)\b/i.test(declaration)) assert.match(declaration, /theme: fixed/, `${name}: unclassified ${rule[1]} { ${declaration} }`);
      }
    }
  }
  const cinema = read('javsp_web/web/assets/cinema.css');
  assert.doesNotMatch(cinema, /body:has\(\.view\.active\[data-panel="overview"\]\)|html\[data-initial-view="overview"\]/);
});
