const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../javsp_web/web/assets/app.js'), 'utf8');
const moduleSource = source.slice(source.indexOf('window.JavspComments ='), source.indexOf('\nfunction formatLocalDateTime'));
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness() {
  const nodes = new Map(), events = {}, requests = [], saved = new Map();
  const node = key => {
    if (!nodes.has(key)) nodes.set(key, { value: '', textContent: '', innerHTML: '', hidden: false, disabled: false, addEventListener() {} });
    return nodes.get(key);
  };
  const section = node('section');
  section.querySelector = node;
  const form = { elements: { nickname: node('[name=nickname]'), body: node('body') }, querySelector: node, closest: selector => selector === '#task-comments form' ? form : null };
  const context = vm.createContext({
    window: {}, document: { addEventListener: (event, fn) => { events[event] = fn; } },
    $: selector => selector === '#task-comments' ? section : node(selector),
    escapeHtml: value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
    localStorage: { getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value) },
    AbortController, setTimeout, clearTimeout,
    fetch: (url, options) => new Promise((resolve, reject) => requests.push({ url, options, resolve: (data, status = 200) => resolve({ ok: status < 400, json: async () => data }), reject })),
  });
  vm.runInContext(moduleSource, context);
  const click = selector => events.click({ target: { closest: value => value === '#task-comments ' + selector ? node(selector) : null } });
  const submit = () => events.submit({ target: form, preventDefault() {} });
  return { api: context.window.JavspComments, requests, node, section, form, click, submit, saved };
}
test('same movie refresh preserves drafts; closing aborts requests and ignores stale responses', async () => {
  const h = harness(); h.api.open('ABC-001', 'https://comments.test');
  const initial = h.section.innerHTML;
  h.form.elements.body.value = 'draft'; h.api.open('ABC-001', 'https://comments.test');
  assert.equal(h.requests.length, 1); assert.equal(h.section.innerHTML, initial); assert.equal(h.form.elements.body.value, 'draft');
  h.api.open('ABC-002', 'https://comments.test');
  assert.equal(h.requests[0].options.signal.aborted, true);
  h.requests[1].resolve({ items: [{ id: 2, body: 'new movie' }] }); await tick();
  h.requests[0].resolve({ items: [{ id: 1, body: 'old movie' }] }); await tick();
  assert.match(h.node('.comments-list').innerHTML, /new movie/); assert.doesNotMatch(h.node('.comments-list').innerHTML, /old movie/);
  h.api.close(); assert.equal(h.section.hidden, true);
});
test('pagination appends escaped comments and retry keeps existing results', async () => {
  const h = harness(); h.api.open('ABC-001', 'https://comments.test');
  h.requests[0].resolve({ items: [{ id: 3, body: '<script>bad</script>', nickname: '<img>' }], next_cursor: 3 }); await tick();
  assert.match(h.node('.comments-list').innerHTML, /&lt;script>/); assert.doesNotMatch(h.node('.comments-list').innerHTML, /<img>/);
  assert.equal(h.node('[data-comment-more]').hidden, false);
  const loading = h.click('[data-comment-more]');
  assert.match(h.requests[1].url, /before=3/);
  h.requests[1].resolve({ detail: '暂时不可用' }, 503); await loading;
  assert.match(h.node('.comments-list').innerHTML, /&lt;script>/);
  const retry = h.click('[data-comment-more]');
  h.requests[2].resolve({ items: [{ id: 2, body: 'older comment' }], next_cursor: null }); await retry;
  assert.equal(h.node('.comments-status').textContent, '2 条评论'); assert.equal(h.node('[data-comment-more]').hidden, true);
});
test('posting is single-flight, preserves failures, omits login credentials and handles pending review', async () => {
  const h = harness(); h.api.open('ABC-001', 'https://comments.test');
  h.requests[0].resolve({ items: [] }); await tick();
  h.form.elements.body.value = '   '; await h.submit(); assert.equal(h.requests.length, 1);
  h.form.elements.body.value = 'hello'; h.form.elements.nickname.value = 'tester';
  const first = h.submit(); await h.submit(); assert.equal(h.requests.length, 2);
  assert.equal(h.requests[1].options.credentials, 'omit'); assert.equal(h.requests[1].options.referrerPolicy, 'no-referrer');
  h.requests[1].resolve({ detail: '请稍后重试' }, 429); await first;
  assert.equal(h.form.elements.body.value, 'hello'); assert.equal(h.node('button[type="submit"]').disabled, false);
  const second = h.submit(); h.requests[2].resolve({ comment: { status: 'pending' } }, 201); await second;
  assert.equal(h.form.elements.body.value, ''); assert.match(h.node('.comment-form-message').textContent, /审核/);
  assert.equal(h.saved.get('javsp-web.comment-nickname'), 'tester');
});
test('disabled service or unidentified movie makes no external request', () => {
  const h = harness(); h.api.open('ABC-001', ''); assert.equal(h.section.hidden, true);
  h.api.open('', 'https://comments.test'); assert.equal(h.requests.length, 0);
});
