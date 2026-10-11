const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../javsp_web/web/assets/app.js'), 'utf8');
const markup = fs.readFileSync(path.join(__dirname, '../javsp_web/web/index.html'), 'utf8');
const elements = new Map();
function $(selector) {
  if (!elements.has(selector)) elements.set(selector, { value: '', checked: false, disabled: false, textContent: '',
    listeners: {}, addEventListener(event, callback) { this.listeners[event] = callback; } });
  return elements.get(selector);
}
let settings = { enabled: true, sync_interval_minutes: 12, server_url: 'https://cloud.test', uuid: 'test', has_password: true,
  sync: { last_sync_at: '2026-10-11T08:00:00Z', next_sync_at: '2026-10-11T08:12:00Z', domains: 2, cookies: 3 } };
let submitted;
const calls = [];
const context = vm.createContext({ $, formatLocalDateTime: value => value, window: { clearTimeout() {}, setTimeout() {} },
  api: async (url, options = {}) => {
    calls.push({ url, options });
    if (options.method === 'PUT') { submitted = JSON.parse(options.body); return settings; }
    if (url.endsWith('/sync')) return { ok: true, sync: settings.sync };
    if (url.endsWith('/test')) return { ok: true, domains: 2, cookies: 3 };
    return settings;
  },
});
vm.runInContext(source.slice(source.indexOf('function cookiecloudPayload'), source.indexOf('async function refreshConfiguredMediaLibraries')), context);
vm.runInContext(source.slice(source.indexOf("$('#cookiecloud-form').addEventListener"), source.indexOf("$('#download-management-form').addEventListener")), context);
(async () => {
  assert.match(markup, /id="cookiecloud-sync-interval"[^>]*min="1"[^>]*max="1440"/);
  await context.loadCookieCloud();
  assert.equal($('#cookiecloud-sync-interval').value, 12);
  assert.match($('#cookiecloud-sync-status').textContent, /最近同步.*08:00:00.*下次.*08:12:00/);
  $('#cookiecloud-sync-interval').value = '60';
  await $('#cookiecloud-form').listeners.submit({ preventDefault() {} });
  assert.equal(submitted.sync_interval_minutes, 60);
  await $('#sync-cookiecloud').listeners.click();
  assert.ok(calls.some(call => call.url === '/api/cookiecloud/sync' && call.options.method === 'POST' && !call.options.body));
  assert.match($('#cookiecloud-message').textContent, /同步完成/);
  await $('#test-cookiecloud').listeners.click();
  assert.match($('#cookiecloud-message').textContent, /测试不会保存/);
  context.renderCookieCloudStatus({ enabled: false, sync: {} });
  assert.equal($('#sync-cookiecloud').disabled, true);
  assert.match($('#cookiecloud-sync-status').textContent, /已停用/);
  context.renderCookieCloudStatus({ enabled: true, sync: { last_error: '同步失败' } });
  assert.match($('#cookiecloud-sync-status').textContent, /同步失败/);
  console.log('CookieCloud client checks passed: interval, status, saved-settings sync and connection test.');
})().catch(error => { console.error(error); process.exitCode = 1; });
