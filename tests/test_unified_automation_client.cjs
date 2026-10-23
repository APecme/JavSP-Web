const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'javsp_web/web/assets/directory-watch.js'), 'utf8');
function setup() {
  const nodes = {};
  const node = id => nodes[id] ||= { value: '', checked: false, disabled: false, hidden: false,
    dataset: {}, classList: { toggle() {} }, querySelectorAll: () => [], showModal() { this.open = true; } };
  const window = {};
  const context = vm.createContext({ window, document: { readyState: 'loading',
    addEventListener() {}, querySelector: selector => node(selector) }, console });
  const exposed = source.replace('window.JavspDirectoryWatch = { load, init, state };',
    'window.JavspDirectoryWatch = { load, init, state, payload, syncTrigger, rowMarkup, openDialog };');
  vm.runInContext(exposed, context);
  return { api: window.JavspDirectoryWatch, node, window };
}
test('one radio choice drives payload and disables inactive controls', () => {
  const { api, node } = setup();
  const watchControl = { disabled: false };
  node('#dw-watch-fields').querySelectorAll = () => [watchControl];
  node('#dw-trigger-schedule').checked = true;
  node('#dw-cron').value = ' 0 2 * * * ';
  node('#dw-poll').value = '30'; node('#dw-stable').value = '60'; node('#dw-max').value = '20';
  api.syncTrigger();
  assert.equal(api.payload().trigger, 'schedule');
  assert.equal(api.payload().cron, '0 2 * * *');
  assert.equal(node('#dw-watch-fields').hidden, true);
  assert.equal(watchControl.disabled, true);
  assert.equal(node('#dw-cron').required, true);
  node('#dw-trigger-schedule').checked = false;
  api.syncTrigger();
  assert.equal(api.payload().trigger, 'watch');
  assert.equal(api.payload().cron, '', 'watch never submits a leftover cron');
  assert.equal(watchControl.disabled, false);
  assert.equal(node('#dw-cron').disabled, true);
});
test('edit schedule then new rule resets trigger and identity', () => {
  const { api, node } = setup();
  api.state.presetsLoaded = true;
  api.state.presets = [{ id: 'default', name: 'default' }];
  api.openDialog({ id: 'old', trigger: 'schedule', cron: '0 3 * * *', preset_id: 'default' });
  assert.equal(node('#dw-trigger-schedule').checked, true);
  assert.equal(api.state.editing.id, 'old');
  api.openDialog(null);
  assert.equal(api.state.editing, null);
  assert.equal(node('#dw-trigger-schedule').checked, false);
  assert.equal(node('#dw-trigger-watch').checked, true);
  assert.equal(api.payload().cron, '');
});
test('cards expose correct mode facts and keep history without watch reset for cron', () => {
  const { api } = setup();
  const rule = { id: 'one', name: '<script>', trigger: 'schedule', cron: '0 2 * * *',
    path: '/movies', history: { runs: [{ id: 'old' }] }, status: {} };
  const html = api.rowMarkup(rule);
  assert.match(html, /定时全量扫描/);
  assert.match(html, /0 2 \* \* \*/);
  assert.match(html, /运行记录 \(1\)/);
  assert.match(html, /立即运行/);
  assert.doesNotMatch(html, /data-dw-reset/);
  assert.doesNotMatch(html, /扫描间隔/);
  assert.match(html, /&lt;script&gt;/);
  const watch = api.rowMarkup({ ...rule, trigger: 'watch', poll_seconds: 30, stable_seconds: 60 });
  assert.match(watch, /目录轮询/);
  assert.match(watch, /扫描间隔/);
  assert.match(watch, /data-dw-reset/);
  assert.doesNotMatch(watch, /data-dw-history/);
});
test('document has one visible directory rule module; old hooks are compatibility-only', () => {
  const html = fs.readFileSync(path.join(root, 'javsp_web/web/index.html'), 'utf8');
  assert.match(html, /data-auto-scrape-module="schedule" hidden aria-hidden="true"/);
  assert.match(source, /name="dw-trigger" id="dw-trigger-watch"/);
  assert.match(source, /name="dw-trigger" id="dw-trigger-schedule"/);
  assert.match(source, /统一调度正在运行/);
});
