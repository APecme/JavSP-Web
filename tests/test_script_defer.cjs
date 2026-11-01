const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

const EXPECTED_ORDER = [
  'theme.js',
  'icons.js',
  'markdown-it.min.js',
  'comment-markdown.js',
  'community.js',
  'app.js',
  'directory-watch.js',
  'hot.js',
  'hot-clash.js',
  'navigation.js',
  'ai-markdown.js',
  'ai.js',
];

function scriptTags(html) {
  return [...html.matchAll(/<script\b([^>]*)>(?:[\s\S]*?)<\/script>/g)].map((m) => m[1]);
}

test('all business scripts are deferred and keep their original order', () => {
  const html = read('javsp_web/web/index.html');
  const deferred = [...html.matchAll(/<script defer src="\/assets\/([a-z.-]+\.js)\?v=__ASSET_VERSION__"><\/script>/g)].map((m) => m[1]);
  assert.deepEqual(deferred, EXPECTED_ORDER, 'deferred scripts must match the original order');
  // No non-defer external business scripts remain.
  const external = [...html.matchAll(/<script\b([^>]*)\bsrc="[^"]+"[^>]*><\/script>/g)].map((m) => m[1]);
  for (const attrs of external) {
    assert.match(attrs, /(?:^|\s)defer(?:\s|$)/, `external script is missing defer: <script ${attrs}>`);
  }
});

test('inline boot snippets stay synchronous and load before the deferred bundles', () => {
  const html = read('javsp_web/web/index.html');
  const tags = scriptTags(html);
  const inline = tags.filter((attrs) => !/src=/.test(attrs));
  const deferred = tags.filter((attrs) => /(?:^|\s)defer(?:\s|$)/.test(attrs));
  assert.equal(inline.length, 2, 'two inline boot snippets (theme + initial-view) stay synchronous');
  for (const attrs of inline) assert.doesNotMatch(attrs, /defer/, 'inline snippets do not need defer');
  assert.equal(deferred.length, EXPECTED_ORDER.length, 'all business scripts are deferred');
  // Deferred scripts appear after the inline snippets in document order.
  const firstDeferred = html.indexOf('<script defer');
  const lastInline = Math.max(...inline.map((attrs) => {
    const i = html.indexOf(attrs.trim() ? `<script ${attrs}>` : '<script>');
    assert.ok(i >= 0);
    return i;
  }));
  assert.ok(firstDeferred > lastInline, 'deferred scripts load after inline boot snippets');
});

test('demo.html mirrors the same defer order for its business scripts', () => {
  const html = read('docs/demo.html');
  const deferred = [...html.matchAll(/<script defer src="assets\/([a-z.-]+\.js)\?v=[0-9a-f]+"><\/script>/g)].map((m) => m[1]);
  const expected = EXPECTED_ORDER.map((name) => (name === 'app.js' ? 'demo-app.js' : name));
  assert.deepEqual(deferred, expected, 'demo.html deferred order mirrors index.html (app.js -> demo-app.js)');
});
