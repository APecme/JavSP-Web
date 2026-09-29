const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../javsp_web/web/assets/app.js'), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));

function client() {
  const nodes = new Map();
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, { value: '', textContent: '', hidden: true, disabled: false });
    return nodes.get(selector);
  };
  const requests = [];
  const context = vm.createContext({
    state: {}, $: node,
    api: async (url, options) => { requests.push({ url, body: JSON.parse(options.body) }); return { scan: true, tasks: [{ id: 'scan-id' }] }; },
    loadTasks: async () => {},
    escapeHtml: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;'),
    taskDisplayName: task => task.name,
  });
  vm.runInContext(section('function clearManualFileSelection()', 'function setPathTarget('), context);
  vm.runInContext(section('async function submitManualTask(', "$('#task-form').addEventListener('submit', submitManualTask);"), context);
  vm.runInContext(section('function scanTaskCard(', 'function taskCard('), context);
  const finalCardStart = source.lastIndexOf('function taskCard(task) {');
  vm.runInContext(source.slice(finalCardStart, source.indexOf('function rememberTaskCards(', finalCardStart)), context);
  node('#task-preset').value = 'default';
  return { context, node, requests };
}
const event = { preventDefault() {} };

async function main() {
  {
    const { context, node, requests } = client();
    node('#input-directory').value = 'X:/mounted-folder';
    await context.submitManualTask(event);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].body.input_directory, 'X:/mounted-folder');
    assert.equal(requests[0].body.input_files, undefined);
    assert.equal(node('#input-directory').value, '');
    assert.match(node('#task-message').textContent, /后台扫描/);
    assert.equal(node('#task-form button[type="submit"]').disabled, false);
  }
  {
    const { context, node, requests } = client();
    context.setManualFileSelection(['X:/ABC-123-CD1.mp4', 'X:/ABC-123-CD2.mp4', 'X:/ABC-123-CD1.mp4']);
    assert.equal(node('#task-selection-message').hidden, false);
    await context.submitManualTask(event);
    assert.equal(requests.length, 1, 'one request must preserve a single batch');
    assert.deepEqual(requests[0].body.input_files, ['X:/ABC-123-CD1.mp4', 'X:/ABC-123-CD2.mp4']);
    assert.equal(context.state.manualInputFiles.length, 0);
    assert.equal(node('#task-selection-message').hidden, true);
  }
  {
    const { context, node, requests } = client();
    context.setManualFileSelection(['X:/old.mp4']);
    context.clearManualFileSelection();
    node('#input-directory').value = 'X:/another-folder';
    await context.submitManualTask(event);
    assert.equal(requests[0].body.input_files, undefined);
  }
  {
    const { context, node } = client();
    let count = 0, release;
    context.api = () => { count++; return new Promise(resolve => { release = resolve; }); };
    context.setManualFileSelection(['X:/old.mp4']);
    const pending = context.submitManualTask(event);
    await context.submitManualTask(event);
    assert.equal(count, 1, 'repeated clicks must not create duplicate scans');
    assert.equal(node('#task-form button[type="submit"]').disabled, true);
    context.setManualFileSelection(['X:/new.mp4']);
    release({ scan: true, tasks: [{ id: 'scan-id' }] });
    await pending;
    assert.equal(node('#input-directory').value, 'X:/new.mp4');
    assert.equal(context.state.manualInputFiles[0], 'X:/new.mp4');
  }
  {
    const { context, node } = client();
    context.setManualFileSelection(['X:/retry.mp4']);
    context.api = async () => { throw new Error('offline'); };
    await context.submitManualTask(event);
    assert.equal(node('#input-directory').value, 'X:/retry.mp4');
    assert.equal(context.state.manualInputFiles.length, 1);
    assert.equal(context.state.manualTaskSubmitting, false);
    assert.equal(node('#task-form button[type="submit"]').disabled, false);
    assert.equal(node('#task-message').textContent, 'offline');
  }
  {
    const { context, node } = client();
    context.api = async (url, options) => {
      assert.equal(url, '/api/path/select-multi');
      assert.deepEqual(JSON.parse(options.body), { kind: 'file' });
      return { paths: ['X:/one.mp4', 'X:/two.mp4'] };
    };
    await context.selectNativePath('files');
    assert.equal(context.state.manualInputFiles.length, 2);
    assert.equal(node('#input-directory').value, 'X:/one.mp4');
    const markup = context.taskCard({ id: 'scan', task_type: 'scan', name: '<unsafe>', status: 'running', input_directory: 'X:/mount', scan: { discovered_files: 4, created_tasks: 0, message: 'still scanning' } });
    assert.match(markup, /扫描中/);
    assert.match(markup, /停止扫描/);
    assert.match(markup, /发现 4 个文件/);
    assert.ok(!markup.includes('<unsafe>'));
    assert.ok(!markup.includes('<img'));
  }
  console.log('Scan client checks passed: directory, single batch, edited paths, duplicate clicks, retry, native multiselect and progress rendering.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
