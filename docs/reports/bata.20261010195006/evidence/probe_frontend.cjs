// Execute production functions in a fake DOM; no browser/backend/network access.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, 'source/javsp_web/web/assets/app.js'), 'utf8');
const section = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
async function main() {
  const tag = { textContent: '', title: '', dataset: {} };
  const versionContext = vm.createContext({
    $: () => tag,
    api: async () => ({ result: { current: 'bata.20261010195006', target: 'bata.20261010195006', available: false, checked_at: '2026-10-11', channel: 'bata' } }),
  });
  vm.runInContext(section('function normalizeVersion', 'const UPDATE_OVERLAY_KEY'), versionContext);
  await versionContext.checkForAppUpdate({ version: 'bata.20261010195006', app_version: '1.1.38' });
  assert.equal(tag.dataset.updateStatus, 'unknown');
  console.log('CONFIRMED known-current beta update status renders unknown:', JSON.stringify(tag));

  const listeners = [];
  const controls = [{ value: 'filter', dataset: {}, addEventListener() {} }];
  const category = { value: 'A' }, tags = { value: 'B' };
  const reset = { addEventListener(name, handler, options) { listeners.push({handler, options}); } };
  const downloadContext = vm.createContext({
    state: { activeDownloads: [], activeDownloader: {} },
    document: { querySelectorAll: () => controls },
    $: selector => selector.endsWith('reset') ? reset : selector.endsWith('category') ? category : tags,
    renderDownloadRows: () => {},
  });
  vm.runInContext(section('function ensureDownloadFilters', 'async function loadDownloads'), downloadContext);
  for (let n = 0; n < 12; n++) downloadContext.ensureDownloadFilters();
  assert.equal(listeners.length, 12);
  console.log('CONFIRMED 12 successful download polls register', listeners.length, 'distinct reset handlers; all use once=true');

  const declarations = [...source.matchAll(/^(?:async )?function\s+(\w+)\s*\(/gm)].reduce((result, match) => {
    (result[match[1]] ??= []).push(source.slice(0, match.index).split('\n').length);
    return result;
  }, {});
  console.log('Duplicate top-level production function declarations:', JSON.stringify(Object.fromEntries(Object.entries(declarations).filter(([, lines]) => lines.length > 1))));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
