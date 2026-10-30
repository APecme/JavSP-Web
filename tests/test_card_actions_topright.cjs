const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const app = () => read('javsp_web/web/assets/app.js');
const css = () => read('javsp_web/web/assets/page-layouts.css');

function slice(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0, `missing slice start: ${start}`);
  assert.ok(to > from, `missing slice end: ${end}`);
  return source.slice(from, to);
}

test('preset cards render a top-right action cluster instead of a footer row', () => {
  const source = app();
  const body = slice(source, 'function presetCardMarkup(preset) {', 'function renderPresetList()');
  assert.match(body, /<div class="preset-source-card-actions">/, 'action cluster markup exists');
  assert.match(body, /preset-source-card-actions/, 'actions come before the card main button');
  const actionsIdx = body.indexOf('preset-source-card-actions');
  const mainIdx = body.indexOf('preset-source-card-main');
  assert.ok(actionsIdx < mainIdx, 'action cluster is rendered above the title block');
  assert.doesNotMatch(body, /preset-source-card-foot/, 'footer row removed from preset cards');
  assert.match(body, /data-delete-preset=/, 'delete button kept');
  assert.match(body, /data-edit-preset=/, 'edit button kept');
});

test('crawler cards render a top-right action cluster instead of a footer row', () => {
  const source = app();
  const body = slice(source, 'function crawlerCardMarkup(item) {', 'function crawlerSourceDeleteButton(item) {');
  assert.match(body, /<div class="crawler-source-card-actions">/, 'action cluster markup exists');
  const actionsIdx = body.indexOf('crawler-source-card-actions');
  const mainIdx = body.indexOf('crawler-source-card-main');
  assert.ok(actionsIdx < mainIdx, 'action cluster is rendered above the title block');
  assert.doesNotMatch(body, /crawler-source-card-foot/, 'footer row removed from crawler cards');
  assert.match(body, /data-open-crawler-editor=/, 'edit button kept');
});

test('both cards share the same absolutely positioned top-right action styling', () => {
  const source = css();
  assert.match(source, /\/\* Shared top-right action cluster for preset & crawler cards\. \*\//);
  const block = slice(source,
    '[data-panel="presets"] .preset-source-card-actions,\n[data-panel="crawler-config"] .crawler-source-card-actions {',
    '[data-panel="presets"] .preset-source-card-actions .icon-button,\n[data-panel="crawler-config"] .crawler-source-card-actions .icon-button {');
  assert.match(block, /position:\s*absolute;/, 'actions are absolutely positioned');
  assert.match(block, /top:\s*8px;/, 'anchored to the top');
  assert.match(block, /right:\s*8px;/, 'anchored to the right');
  assert.match(block, /z-index:\s*1;/, 'stacked above card content');
  // Cards are relative + reserve right padding so titles never overlap the actions.
  assert.match(source, /\[data-panel="presets"\] \.preset-source-card \{[^}]*position:\s*relative;/s);
  assert.match(source, /\[data-panel="crawler-config"\] \.crawler-source-card \{[^}]*position:\s*relative;/s);
  assert.match(source, /\[data-panel="presets"\] \.preset-source-card \{[^}]*padding-right:\s*76px;/s);
  assert.match(source, /\[data-panel="crawler-config"\] \.crawler-source-card \{[^}]*padding-right:\s*76px;/s);
  assert.match(source, /padding-right:\s*72px;/, 'mobile keeps reserved space for the action cluster');
  // hover + focus-visible shared rules exist.
  assert.match(source, /:focus-visible \{\s*outline:\s*2px solid var\(--accent\);/s);
});

test('icon buttons inside the action clusters have a consistent compact size', () => {
  const source = css();
  const block = slice(source,
    '[data-panel="presets"] .preset-source-card-actions .icon-button,\n[data-panel="crawler-config"] .crawler-source-card-actions .icon-button {',
    '[data-panel="presets"] .preset-source-card-actions .icon-button:hover,');
  assert.match(block, /width:\s*30px;/);
  assert.match(block, /height:\s*30px;/);
  assert.match(block, /padding:\s*0;/);
});
