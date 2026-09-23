// Execute the production request/version helpers without a browser or dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../javsp_web/web/assets/app.js'), 'utf8');
const versions = source.slice(source.indexOf('function normalizeVersion'), source.indexOf('async function checkForAppUpdate'));
const requests = source.slice(source.indexOf('const apiRequests'), source.indexOf('// Keep unchanged cards'));

async function verifyUpdateOverlay() {
  const markup = fs.readFileSync(path.join(__dirname, '../javsp_web/web/index.html'), 'utf8');
  assert.match(markup, /id="update-overlay"[^>]*role="alertdialog"/);
  const elements = new Map();
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, { hidden: true, dataset: {}, textContent: '', focus() {} });
    return elements.get(selector);
  };
  const classes = new Set();
  const pending = new Map();
  const callbacks = [];
  const replies = [];
  let reloads = 0;
  const context = vm.createContext({
    $: element,
    api: async () => {
      const reply = replies.shift();
      if (reply instanceof Error) throw reply;
      return reply;
    },
    document: { body: { classList: { add: name => classes.add(name), remove: name => classes.delete(name) } } },
    sessionStorage: { setItem: (key, value) => pending.set(key, value), getItem: key => pending.get(key), removeItem: key => pending.delete(key) },
    window: { setTimeout: callback => { callbacks.push(callback); return callbacks.length; }, clearTimeout() {} },
    location: { reload: () => reloads++ },
  });
  const updateFunctions = source.slice(source.indexOf('const UPDATE_OVERLAY_KEY'), source.indexOf('function scheduleGitHubStarInvite'));
  vm.runInContext(updateFunctions, context);
  context.watchUpdateJob({ id: 'first' });
  assert.equal(element('#update-overlay').hidden, false);
  assert.ok(classes.has('update-in-progress'));
  assert.equal(JSON.parse(pending.get('javsp-web.update-job')).id, 'first');
  replies.push({ job: { id: 'first', status: 'downloading', message: '正在下载应用包' } });
  await context.pollUpdateOverlay();
  assert.equal(element('#update-overlay-status').textContent, '正在下载应用包');
  replies.push(new Error('server restarting'));
  await context.pollUpdateOverlay();
  assert.match(element('#update-overlay-status').textContent, /重新连接/);
  replies.push({ job: { id: 'first', status: 'updated' } });
  await context.pollUpdateOverlay();
  assert.equal(element('#update-overlay').dataset.phase, 'updated');
  assert.equal(pending.size, 0);
  callbacks.at(-1)();
  assert.equal(reloads, 1);
  context.watchUpdateJob({ id: 'second' });
  replies.push({ job: { id: 'second', status: 'rolled_back', message: '已恢复旧版本' } });
  await context.pollUpdateOverlay();
  assert.equal(element('#update-overlay').dataset.phase, 'failed');
  assert.equal(element('#update-overlay-close').hidden, false);
  context.closeUpdateOverlay();
  assert.equal(element('#update-overlay').hidden, true);
  assert.equal(classes.has('update-in-progress'), false);
  replies.push({ status: 'scheduled', id: 'manual' }, { settings: {}, result: {}, capability: { supported: true }, job: { id: 'manual', status: 'scheduled' } });
  const manual = context.applyUpdateNow();
  assert.equal(element('#update-overlay').hidden, false, 'manual update must show feedback before the request completes');
  await manual;
  assert.equal(JSON.parse(pending.get('javsp-web.update-job')).id, 'manual');
  context.closeUpdateOverlay();
  replies.push(new Error('当前还有运行中的任务'));
  await context.applyUpdateNow();
  assert.equal(element('#update-overlay').hidden, true);
  assert.equal(element('#update-settings-message').textContent, '当前还有运行中的任务');
}

async function main() {
  let count = 0;
  let release;
  let abortTimer;
  let mode = 'pending';
  const context = vm.createContext({
    state: {}, location: {}, AbortController,
    window: { setTimeout: fn => { abortTimer = fn; return 1; }, clearTimeout: () => {} },
    formatApiError: (_, status) => `HTTP ${status}`,
    fetch: async (url, options) => {
      count++;
      if (mode === 'pending') await new Promise(resolve => { release = resolve; });
      if (mode === 'abort') return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(Object.assign(new Error(), { name: 'AbortError' }))));
      if (mode === 'cached') { assert.equal(options.headers['If-None-Match'], 'v1'); return { status: 304 }; }
      if (mode === 'error') return { status: 503, ok: false, json: async () => ({}) };
      return { status: 200, ok: true, headers: { get: () => 'v1' }, json: async () => ({ items: [{ id: 1 }], total: 1 }) };
    },
  });
  vm.runInContext(versions + '\n' + requests, context);
  assert.equal(context.normalizeVersion('vv1.1.36'), '1.1.36');
  assert.equal(context.compareReleaseVersions('vv1.1.36', 'v1.1.36'), 0);
  assert.ok(context.compareReleaseVersions('1.1.36', 'v1.1.37') < 0);
  assert.equal(context.compareReleaseVersions('bata.20260923', '1.1.36'), null);
  const first = context.api('/api/tasks?limit=50');
  const second = context.api('/api/tasks?limit=50');
  assert.equal(count, 1, 'concurrent GETs must share a request');
  release();
  assert.equal(await first, await second);
  mode = 'cached';
  assert.equal((await context.api('/api/tasks?limit=50')).items[0].id, 1);
  mode = 'error';
  await assert.rejects(context.api('/api/failed'), /503/);
  mode = 'success';
  await context.api('/api/failed');
  mode = 'abort';
  const timed = context.api('/api/slow');
  abortTimer();
  await assert.rejects(timed, /请求超时/);
  mode = 'success';
  await context.api('/api/slow');
  await verifyUpdateOverlay();
  console.log('Web client regression checks passed: version normalization, shared GET, ETag, timeout/retry, update overlay.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
