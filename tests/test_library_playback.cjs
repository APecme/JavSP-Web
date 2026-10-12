const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../javsp_web/web/assets/app.js'), 'utf8');
const functions = source.slice(source.indexOf('function playButton'), source.indexOf('function artworkPlaceholder'));

async function main() {
  let destination, closed = false, message, request;
  const player = { opener: {}, location: { replace: url => { destination = url; } }, close: () => { closed = true; } };
  const button = { dataset: { playTask: 'task/1' }, disabled: false };
  const context = vm.createContext({
    window: { open: () => player },
    api: async url => { request = url; return { links: [{ url: 'https://player.test/web/#/details?id=1' }] }; },
    showToast: error => { message = error; }, escapeHtml: value => value,
  });
  vm.runInContext(functions, context);
  await context.playTask(button);
  assert.equal(request, '/api/tasks/task%2F1/playback');
  assert.equal(destination, 'https://player.test/web/#/details?id=1');
  assert.equal(player.opener, null);
  assert.equal(button.disabled, false);
  context.api = async () => { throw new Error('未找到影片'); };
  await context.playTask(button);
  assert.equal(closed, true);
  assert.equal(message, '未找到影片');
  assert.equal(button.disabled, false);
  let options = { innerHTML: '' }, shown = false, inserted = false;
  const dialog = { querySelector: () => options, showModal: () => { shown = true; } };
  context.$ = () => inserted ? dialog : null;
  context.document = { body: { insertAdjacentHTML: () => { inserted = true; } } };
  context.api = async () => ({ links: [
    { name: 'Jellyfin', url: 'https://one.test/web/' },
    { name: 'Emby', url: 'https://two.test/web/' },
    { name: 'Invalid', url: 'javascript:invalid' },
  ] });
  closed = false;
  await context.playTask(button);
  assert.equal(closed, true);
  assert.equal(shown, true);
  assert.match(options.innerHTML, /https:\/\/one.test\/web\//);
  assert.match(options.innerHTML, /https:\/\/two.test\/web\//);
  assert.match(options.innerHTML, /rel="noopener noreferrer"/);
  assert.doesNotMatch(options.innerHTML, /javascript:/);
  context.window.open = () => null;
  shown = false;
  context.api = async () => ({ links: [{ name: 'Jellyfin', url: 'https://one.test/web/' }] });
  await context.playTask(button);
  assert.equal(shown, true);
  assert.equal(button.disabled, false);
  console.log('Library playback regression checks passed.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
