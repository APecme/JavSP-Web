// Execute the production request/version helpers without a browser or dependencies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../javsp_web/web/assets/app.js'), 'utf8');
const versions = source.slice(source.indexOf('function normalizeVersion'), source.indexOf('async function checkForAppUpdate'));
const requests = source.slice(source.indexOf('const apiRequests'), source.indexOf('// Keep unchanged cards'));

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
  console.log('Web client regression checks passed: version normalization, shared GET, ETag, failure cleanup, timeout/retry.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
