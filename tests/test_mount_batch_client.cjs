const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../scripts/javsp-web-mount-batch.user-v0.4.0.js'), 'utf8');
const alias = fs.readFileSync(path.join(__dirname, '../scripts/JavSP WEB 挂载盘批量刮削助手-v0.4.0.js'), 'utf8');
assert.equal(source, alias, 'both distributed script names must contain the same fixes');

function client(handler) {
  const requests = [], messages = [], confirmations = [];
  const schema = { components: { schemas: { TaskBody: { properties: { input_files: {} } } } },
    paths: { '/api/tasks': { post: { responses: { '202': {} } } } } };
  let listener;
  const context = vm.createContext({
    files: [], running: false, picking: false, deleting: false, stopRequested: false, activeScanId: null,
    $: () => ({ value: 'default' }), render() {}, sleep: async () => {}, encodeURIComponent,
    setStatus: message => messages.push(message),
    confirm: message => { confirmations.push(message); return true; },
    panel: { addEventListener: (name, callback) => { listener = callback; },
      querySelectorAll: () => [{ dataset: { del: 'failed' } }] },
    jfetch: async (url, options = {}) => {
      requests.push({ url, method: options.method || 'GET', body: options.body && JSON.parse(options.body) });
      const result = url === '/openapi.json' ? schema : await handler(url, options, context);
      return { ok: true, json: async () => result };
    },
  });
  const start = source.indexOf('  async function requestJson(');
  const end = source.indexOf('  panel.querySelector(', source.indexOf('  /* ---------------- 面板事件', start));
  vm.runInContext(source.slice(start, end), context);
  const click = action => listener({ target: { dataset: { act: action } } });
  return { context, requests, messages, confirmations, click, schema };
}

async function main() {
  {
    const { context, requests, click } = client(async () => ({ scan: true, tasks: [{ id: 'scan' }] }));
    context.files = ['A-CD1.mp4', 'A-CD2.mp4', 'B.mp4'].map(path => ({ path, status: 'pending' }));
    await context.runBatch();
    const submissions = requests.filter(request => request.method === 'POST');
    assert.equal(submissions.length, 1);
    assert.deepEqual(submissions[0].body.input_files, ['A-CD1.mp4', 'A-CD2.mp4', 'B.mp4']);
    assert.equal(submissions[0].body.preset_id, 'default');
    assert.ok(context.files.every(file => file.status === 'done'));
    click('clear-done');
    assert.equal(context.files.length, 0);
  }
  {
    let release;
    const { context, requests, click } = client(() => new Promise(resolve => { release = resolve; }));
    context.files = [{ path: 'old.mp4', status: 'done' }, { path: 'A.mp4' }, { path: 'B.mp4' }];
    const promise = context.runBatch();
    while (!release) await Promise.resolve();
    click('clear-done');
    click('clear-all');
    await context.runBatch();
    assert.equal(context.files.length, 3, 'queue cannot mutate while submitting');
    assert.equal(requests.filter(request => request.method === 'POST').length, 1);
    release({ scan: true, tasks: [{ id: 'scan' }] });
    await promise;
    assert.ok(context.files.every(file => file.status === 'done'));
  }
  {
    let release;
    const { context, requests } = client((url) => url === '/api/tasks'
      ? new Promise(resolve => { release = resolve; }) : {});
    context.files = [{ path: 'A.mp4' }];
    const promise = context.runBatch();
    while (!release) await Promise.resolve();
    await context.stopBatch();
    release({ scan: true, tasks: [{ id: 'scan' }] });
    await promise;
    assert.ok(requests.some(request => request.url === '/api/tasks/scan/cancel'));
  }
  {
    const { context, requests, schema } = client(async () => { throw Error('must not submit'); });
    delete schema.components.schemas.TaskBody.properties.input_files;
    context.files = [{ path: 'A.mp4' }];
    await context.runBatch();
    assert.equal(requests.filter(request => request.method === 'POST').length, 0, 'old servers must fail closed');
    assert.equal(context.running, false);
    assert.equal(context.files[0].status, 'error');
  }
  {
    const { context } = client(async () => { throw Error('offline'); });
    context.files = [{ path: 'A.mp4' }];
    await context.runBatch();
    assert.equal(context.files[0].path, 'A.mp4');
    assert.equal(context.files[0].status, 'error');
    assert.equal(context.running, false);
  }
  {
    const { context, requests } = client(async url => {
      if (url.startsWith('/api/tasks?')) return { offset: 0, total: 3, items: [
        { id: 'failed', source: 'manual', status: 'failed' },
        { id: 'succeeded', source: 'manual', status: 'succeeded' },
        { id: 'hidden-schedule', source: 'schedule', status: 'running' },
      ] };
      if (url === '/api/tasks/failed') return { id: 'failed', source: 'manual', status: 'failed' };
      throw Error('unintended target: ' + url);
    });
    await context.batchDelete();
    assert.deepEqual(requests.filter(request => request.method === 'DELETE').map(request => request.url), ['/api/tasks/failed']);
    assert.ok(!requests.some(request => request.url.endsWith('/cancel')));
  }
  for (const status of ['queued', 'running']) {
    let cancelled = false;
    const { context, requests } = client(async (url) => {
      if (url.endsWith('/cancel')) { cancelled = true; return {}; }
      return { id: 'one', source: 'manual', status: cancelled ? 'cancelled' : status };
    });
    assert.equal(await context.deleteTarget({ id: 'one', status }), true);
    assert.deepEqual(requests.map(request => request.method), ['GET', 'POST', 'GET', 'DELETE']);
  }
  {
    const { context, requests } = client(async () => ({ id: 'one', source: 'manual', status: 'succeeded' }));
    assert.equal(await context.deleteTarget({ id: 'one', status: 'failed' }), false);
    assert.deepEqual(requests.map(request => request.method), ['GET']);
  }
  {
    const { context, requests, confirmations } = client(async () => { throw Error('list unavailable'); });
    await context.batchDelete();
    assert.equal(confirmations.length, 0);
    assert.equal(requests.filter(request => request.method !== 'GET').length, 0);
    assert.equal(context.deleting, false);
  }
  {
    const { context, requests } = client(async () => ({ offset: 0, total: 1, items: [{ id: 'one', status: 'failed' }] }));
    context.confirm = () => false;
    await context.batchDelete();
    assert.equal(requests.filter(request => request.method !== 'GET').length, 0);
  }
  {
    const { context } = client(async url => {
      const offset = Number(new URL('http://test' + url).searchParams.get('offset'));
      return { offset, total: 2, items: [{ id: String(offset), source: 'manual', status: 'failed' }] };
    });
    assert.deepEqual(Array.from(await context.collectDeleteTargets(['failed']), task => task.id), ['0', '1']);
  }
  console.log('PR #14 helper checks passed: batch manifests, queue locking, cancellation, legacy server rejection, targeted cleanup, pagination and aliases.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
