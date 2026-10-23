const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const html = read('javsp_web/web/index.html');
const appSource = read('javsp_web/web/assets/app.js');
const dwSource = read('javsp_web/web/assets/directory-watch.js');

// Page titles shown in the top bar, from app.js switchView.
const titleMapMatch = appSource.match(/const title = \{([^}]+)\}\[view\]/);
assert.ok(titleMapMatch, 'app.js exposes the view -> page title map');
const pageTitles = {};
for (const match of titleMapMatch[1].matchAll(/'?([\w-]+)'?\s*:\s*'([^']+)'/g)) {
  pageTitles[match[1]] = match[2];
}
assert.equal(pageTitles['auto-scrape'], '自动刮削');
assert.equal(pageTitles.downloads, '下载管理');

function viewSection(name) {
  const start = html.indexOf(`data-panel="${name}"`);
  assert.ok(start >= 0, `missing view ${name}`);
  const next = html.indexOf('class="view"', start);
  return html.slice(start, next > start ? next : html.length);
}

function headings(markup, level) {
  return [...markup.matchAll(new RegExp(`<${level}[^>]*>([\\s\\S]*?)</${level}>`, 'g'))]
    .map(match => match[1].replace(/<[^>]+>/g, '').trim());
}

test('each tab renders only the top bar page title, no duplicate page heading inside the view', () => {
  for (const [view, title] of Object.entries(pageTitles)) {
    const section = viewSection(view);
    const duplicates = headings(section, 'h2').filter(text => text === title);
    assert.deepEqual(duplicates, [], `view "${view}" repeats page title "${title}" as an h2`);
  }
});

test('every aria-labelledby reference resolves to an existing id', () => {
  const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map(match => match[1]));
  for (const match of html.matchAll(/aria-labelledby="([^"]+)"/g)) {
    for (const id of match[1].trim().split(/\s+/)) {
      assert.ok(ids.has(id), `dangling aria-labelledby="${id}"`);
    }
  }
});

test('embedded directory watch renders toolbar and rules without a nested panel or heading', () => {
  const runBindOnce = (closestResult) => {
    let hostMarkup = null;
    const host = {
      dataset: {},
      closest: () => closestResult,
    };
    Object.defineProperty(host, 'innerHTML', {
      get() { return hostMarkup; },
      set(value) { hostMarkup = value; },
    });
    const dialogStub = () => ({
      id: '', className: '', innerHTML: '',
      addEventListener() {}, querySelectorAll: () => [],
    });
    const control = () => ({ addEventListener() {}, classList: { toggle() {}, contains: () => false }, dataset: {}, textContent: '' });
    const controls = {};
    const context = vm.createContext({
      window: { setInterval: () => 0 },
      document: {
        readyState: 'complete',
        querySelector: selector => (selector === '#directory-watch-panel' ? host : (controls[selector] ||= control())),
        getElementById: () => null,
        createElement: dialogStub,
        body: { appendChild() {} },
        addEventListener() {},
      },
      console,
      MutationObserver: function () { this.observe = () => {}; },
      setInterval: () => 0,
      fetch: () => Promise.reject(new Error('offline')),
    });
    vm.runInContext(dwSource, context);
    return hostMarkup;
  };

  const embedded = runBindOnce({ dataset: { autoScrapeModule: 'watch' } });
  assert.ok(embedded, 'bindOnce rendered into the mount point');
  assert.doesNotMatch(embedded, /class="panel dw-panel"/, 'embedded module must not nest a second panel');
  assert.doesNotMatch(embedded, /<h[1-4][\s>]/, 'embedded module must not repeat the module heading');
  for (const hook of ['id="dw-add"', 'id="dw-refresh"', 'id="dw-list"', 'id="dw-message"', 'id="dw-runtime"']) {
    assert.ok(embedded.includes(hook), `embedded module keeps ${hook}`);
  }

  const standalone = runBindOnce(null);
  assert.match(standalone, /class="panel dw-panel"/, 'standalone fallback keeps its own panel');
  assert.match(standalone, /<h3[^>]*>自动刮削规则<\/h3>/, 'standalone fallback keeps its own heading');
});
