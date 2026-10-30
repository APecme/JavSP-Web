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

function harness(presets) {
  const context = vm.createContext({
    $: () => null,
    escapeHtml: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'),
    javspIcon: () => '',
    state: { presets },
  });
  const fns = slice(appSource, '// Deep-compare two preset configs', 'function renderPresetList(');
  // Top-level function declarations attach to the context, but the const FIELD_LABELS
  // lookup resolves lexically: concatenate the labels object into the same script.
  const fieldLabels = slice(appSource, 'const FIELD_LABELS = {', '\nconst FIELD_NOTES =');
  vm.runInContext(`${fieldLabels}\n${fns}`, context);
  return context;
}

const base = { id: 'default', name: '默认预设', form_values: {
  scanner: { input_directory: '/in', minimum_size: 300 },
  crawler: { hardworking: true },
  summarizer: { move_files: true, cover: { highres: false } },
} };

test('presetDiffPaths skips metadata/empty and compares deeply', () => {
  const context = harness([base]);
  const diffs = context.presetDiffPaths({
    id: 'mine', name: '我的预设', mode: 'form', task_concurrency: 4,
    scanner: { input_directory: '/other', minimum_size: 300 },
    crawler: { hardworking: true },
    summarizer: { move_files: false, cover: { highres: false } },
  }, base.form_values);
  assert.deepEqual([...diffs].sort(), ['scanner.input_directory', 'summarizer.move_files']);
});

test('preset diff tags: Chinese labels, 与默认一致, +N overflow, default hidden', () => {
  const custom = { id: 'p1', name: 'P1', form_values: {
    scanner: { input_directory: '/x' },
    crawler: { hardworking: false },
    summarizer: { move_files: true, cover: { highres: true, add_label: true } },
    network: { retry: 5 },
    translator: { fields: { title: true, plot: true } },
  } };
  const context = harness([base, custom]);
  let markup = context.presetDiffTagsMarkup(custom);
  assert.match(markup, /preset-source-card-diff/);
  assert.match(markup, /扫描目录/);
  assert.match(markup, /最小匹配文件大小/, 'missing subtree key counts as a diff');
  assert.match(markup, /深度抓取/);
  assert.match(markup, /优先下载高清封面/);
  assert.match(markup, /在封面添加水印标签/);
  assert.match(markup, />network</, 'whole-subtree additions fall back to the raw key');
  assert.match(markup, /\+1/, '7 diffs shows 6 tags plus +1');
  assert.equal((markup.match(/preset-diff-tag/g) || []).length, 7, 'six labels plus the +N chip');

  // no diffs -> 与默认一致
  const same = { id: 'p2', name: 'P2', form_values: JSON.parse(JSON.stringify(base.form_values)) };
  assert.deepEqual([...context.presetDiffPaths(same.form_values, base.form_values)], []);
  markup = context.presetDiffTagsMarkup(same);
  assert.match(markup, /与默认一致/);

  // default preset itself shows nothing
  assert.equal(context.presetDiffTagsMarkup(base), '');
  // missing default base: no crash, no tags (nothing to compare against)
  const contextOrphan = harness([{ id: 'p3', name: 'P3', form_values: { scanner: { input_directory: '/y' } } }]);
  const orphan = { id: 'p3', name: 'P3', form_values: { scanner: { input_directory: '/y' } } };
  assert.equal(contextOrphan.presetDiffTagsMarkup(orphan), '');
});

test('preset card drops the auto-scrape usage line and carries diff tags', () => {
  const context = harness([base, { id: 'p1', name: 'P1', form_values: { scanner: { input_directory: '/x' } } }]);
  const card = context.presetCardMarkup(context.state.presets[1]);
  assert.match(card, /preset-source-card-diff/);
  assert.doesNotMatch(card, /条自动刮削规则使用/, 'usage line removed from preset cards');
});
