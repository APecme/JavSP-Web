const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const code = fs.readFileSync(path.join(root, 'javsp_web/web/assets/hot.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return { promise, resolve }; };
function harness() {
  class Node {
    constructor() { this.dataset = {}; this.attrs = {}; this.textContent = ''; this.innerHTML = ''; this.disabled = false; this.events = {}; this.tabIndex = 0; }
    setAttribute(k, v) { this.attrs[k] = v; }
    addEventListener(k, v) { this.events[k] = v; }
    showModal() { this.open = true; }
    close() { this.open = false; }
    focus() { this.focused = true; }
  }
  const ids = {};
  for (const id of ['hot-panel', 'hot-message', 'hot-results', 'hot-refresh', 'hot-check', 'hot-notice', 'hot-connection-count', 'hot-check-message', 'hot-check-progress', 'hot-source-list', 'hot-connections', 'hot-show-connections', 'hot-connections-close', 'hot-age-close', 'hot-age-form', 'hot-age-dialog', 'hot-age-confirm', 'hot-age-message', 'hot-age-submit', 'hot-age-site']) ids[id] = new Node();
  const tabs = ['all', 'censored', 'uncensored'].map(category => Object.assign(new Node(), { dataset: { hotCategory: category } }));
  const sorts = ['latest', 'hot'].map(sort => Object.assign(new Node(), { dataset: { hotSort: sort } }));
  const timers = new Map(); let timerId = 0;
  const calls = []; let handler = () => ({ groups: [], total: 0, job: { running: false } });
  const view = new Node(); let visible = false;
  view.classList = { contains: () => visible };
  let mutation;
  const storage = {};
  const context = vm.createContext({
    window: {}, URL, AbortController, Date, console,
    localStorage: { getItem: k => storage[k] || null, setItem: (k, v) => { storage[k] = v; } },
    document: { readyState: 'complete', getElementById: id => ids[id], querySelector: () => view,
      querySelectorAll: selector => selector === '[data-hot-category]' ? tabs : sorts },
    MutationObserver: class { constructor(fn) { mutation = fn; } observe() {} },
    setTimeout: (fn, delay) => { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout: id => timers.delete(id),
    fetch: async (url, options) => { calls.push({ url, options }); const result = await handler(url, options); if (result instanceof Error) throw result; return { ok: result._status ? result._status < 400 : true, status: result._status || 200, json: async () => result }; },
  });
  vm.runInContext(code, context);
  return { api: context.window.JavspHot, ids, tabs, sorts, calls, timers, storage,
    handle: fn => { handler = fn; }, enter: async () => { visible = true; await mutation(); }, leave: async () => { visible = false; await mutation(); } };
}
const data = (category = 'all', sort = 'latest', extra = {}) => ({ category, sort, total: 1, job: { running: false }, groups: [{ source_name: 'Source', source_id: 's', category: category === 'all' ? 'censored' : category, label: 'Real source rank', state: 'ok', url: 'https://example.invalid/', items: [{ title: 'A release', identifier: 'DEMO-1', source_name: 'Source', category, rank: sort === 'hot' ? 1 : null, url: 'https://example.invalid/item' }] }], ...extra });

test('no outbound action on initialization; tabs and sort use separate API filters', async () => {
  const h = harness();
  assert.equal(h.calls.length, 0);
  h.handle(() => data('uncensored', 'hot'));
  await h.api.select('uncensored', 'hot');
  assert.equal(h.calls[0].url, '/api/hot/films?category=uncensored&sort=hot');
  assert.equal(h.tabs[2].attrs['aria-selected'], 'true');
  assert.equal(h.tabs[0].tabIndex, -1);
  assert.equal(h.sorts[1].attrs['aria-pressed'], 'true');
  assert.equal(h.ids['hot-results'].attrs['aria-labelledby'], 'hot-tab-uncensored');
  assert.match(h.ids['hot-results'].innerHTML, /#1/);
  assert.equal(h.calls[0].options.credentials, 'same-origin');
  assert.match(h.storage['javsp-web.hot-filter'], /uncensored/);
});

test('rapid filter changes discard late responses and never keep wrong-category cards', async () => {
  const h = harness(); const first = deferred(); const second = deferred();
  let count = 0;
  h.handle(() => ++count === 1 ? first.promise : second.promise);
  const a = h.api.select('censored', 'latest');
  const b = h.api.select('uncensored', 'hot');
  assert.doesNotMatch(h.ids['hot-results'].innerHTML, /A release/);
  second.resolve(data('uncensored', 'hot'));
  await b;
  first.resolve(data('censored', 'latest'));
  await a;
  assert.equal(h.api.state.films.category, 'uncensored');
  assert.equal(h.api.state.sort, 'hot');
  assert.equal(h.ids['hot-results'].attrs['aria-busy'], 'false');
});

test('remote title HTML is escaped and unsafe links cannot execute', async () => {
  const h = harness(); const d = data();
  d.groups[0].items[0].title = '<img src=x onerror=evil()> & "';
  d.groups[0].items[0].url = 'javascript:evil()';
  d.groups[0].url = 'https://user:secret@example.invalid';
  h.handle(() => d);
  await h.api.loadFilms();
  const html = h.ids['hot-results'].innerHTML;
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<img|javascript:|user:secret/);
});

test('refresh posts only selected enums and reports server batch progress', async () => {
  const h = harness(); h.api.state.category = 'uncensored'; h.api.state.sort = 'hot';
  h.handle(url => url.endsWith('/refresh') ? {} : data('uncensored', 'hot', { job: { running: true, completed: 1, total: 3 } }));
  await h.api.refreshFilms();
  const post = h.calls.find(c => c.options.method === 'POST');
  assert.equal(post.url, '/api/hot/refresh');
  assert.deepEqual(JSON.parse(post.options.body), { category: 'uncensored', sort: 'hot' });
  assert.equal(h.ids['hot-refresh'].disabled, true);
  assert.match(h.ids['hot-message'].textContent, /1\/3/);
});

test('connection check is independent of category and shows all statuses', async () => {
  const h = harness(); h.api.state.category = 'uncensored';
  h.handle(() => ({ can_check: true, job: { running: true, completed: 2, total: 30, retry_after: 60 }, sources: [
    { name: 'One', url: 'https://example.invalid', result: { state: 'ok', message: 'Reachable', http_status: 200, elapsed_ms: 50 } },
    { name: '<Two>', url: 'javascript:evil()', result: { state: 'region_blocked', message: 'Limited' } },
  ] }));
  await h.api.checkConnections();
  assert.equal(h.calls[0].url, '/api/hot/connections');
  assert.deepEqual(JSON.parse(h.calls[0].options.body), {});
  assert.equal(h.ids['hot-connections'].open, true);
  assert.equal(h.ids['hot-check-progress'].value, 2);
  assert.equal(h.ids['hot-check'].disabled, false);
  assert.match(h.ids['hot-source-list'].innerHTML, /地区限制/);
  assert.match(h.ids['hot-source-list'].innerHTML, /&lt;Two&gt;/);
  assert.doesNotMatch(h.ids['hot-source-list'].innerHTML, /javascript:/);
});

test('connection post error survives finally and duplicate clicks use one request', async () => {
  const h = harness(); const d = deferred();
  h.api.state.connections = { can_check: true, sources: [], job: {} };
  h.handle(() => d.promise);
  const first = h.api.checkConnections();
  await h.api.checkConnections();
  assert.equal(h.calls.length, 1);
  d.resolve({ _status: 403, detail: '需要管理员权限' });
  await first;
  assert.match(h.ids['hot-check-message'].textContent, /管理员/);
  assert.equal(h.ids['hot-check'].disabled, false);
});

test('operator can open connection result dialog but cannot dispatch batch detection', async () => {
  const h = harness();
  h.handle(() => ({ can_check: false, sources: [], job: {} }));
  await h.api.loadConnections();
  assert.equal(h.ids['hot-check'].disabled, false);
  assert.match(h.ids['hot-check'].title, /管理员/);
});

test('tab keyboard navigation uses roving focus and selection', async () => {
  const h = harness(); h.handle(() => data('uncensored'));
  let prevented = false;
  h.tabs[0].events.keydown({ key: 'End', preventDefault: () => { prevented = true; } });
  await tick();
  assert.equal(prevented, true);
  assert.equal(h.tabs[2].focused, true);
  assert.equal(h.api.state.category, 'uncensored');
});

test('leaving hot page stops poll timers; returning resumes job state', async () => {
  const h = harness();
  h.handle(url => url.includes('/connections') ? { can_check: true, sources: [], job: { running: true } } : data('all', 'latest', { job: { running: true, completed: 0, total: 4 } }));
  await h.enter();
  assert.ok([...h.timers.values()].some(t => t.delay === 1800));
  assert.ok([...h.timers.values()].some(t => t.delay === 2000));
  await h.leave();
  assert.equal(h.timers.size, 0);
  await h.enter();
  assert.equal(h.calls.length, 4);
});

test('network error leaves prior cards intact and offers retry', async () => {
  const h = harness(); h.handle(() => data());
  await h.api.loadFilms();
  const cards = h.ids['hot-results'].innerHTML;
  h.handle(() => new Error('暂时断开'));
  await h.api.loadFilms();
  assert.equal(h.ids['hot-results'].innerHTML, cards);
  assert.match(h.ids['hot-message'].textContent, /暂时断开/);
  assert.equal(h.ids['hot-refresh'].disabled, false);
});

test('new assets and markup are shipped in demo and production', () => {
  for (const asset of ['hot.css', 'hot.js']) {
    assert.equal(fs.readFileSync(path.join(root, 'docs/assets', asset), 'utf8'), fs.readFileSync(path.join(root, 'javsp_web/web/assets', asset), 'utf8'));
    for (const file of ['javsp_web/web/index.html', 'docs/demo.html']) assert.match(fs.readFileSync(path.join(root, file), 'utf8'), new RegExp(asset.replace('.', '\\.')));
  }
  const html = fs.readFileSync(path.join(root, 'javsp_web/web/index.html'), 'utf8');
  assert.match(html, /id="hot-check"/);
  assert.equal([...html.matchAll(/data-hot-category="/g)].length, 3);
  assert.equal([...html.matchAll(/data-hot-sort="/g)].length, 2);
});


test('late initial connection GET cannot replace a new running detection batch', async () => {
  const h = harness(); const old = deferred();
  h.handle((url, options) => options.method === 'POST'
    ? { can_check: true, sources: [], job: { running: true, completed: 1, total: 30 } }
    : old.promise);
  const loading = h.api.loadConnections();
  await h.api.checkConnections();
  old.resolve({ can_check: true, sources: [], job: { running: false } });
  await loading;
  assert.equal(h.api.state.connections.job.running, true);
  assert.equal(h.ids['hot-check'].disabled, false);
  assert.match(h.ids['hot-check-message'].textContent, /1\/30/);
});


test('unified wall has one grid, richer fields, sources and no site sections', async () => {
  const h = harness(); const d = data();
  d.items = [{ ...d.groups[0].items[0], actors: ['Actor'], studio: 'Studio', tags: ['Tag'], views: 42,
    sources: [{ source_name: 'A', url: 'https://example.invalid/a', rank: 2 }, { source_name: 'B', url: 'https://example.invalid/b', rank: 1 }] }];
  h.handle(() => d); await h.api.loadFilms();
  const html = h.ids['hot-results'].innerHTML;
  assert.equal([...html.matchAll(/class="hot-grid"/g)].length, 1);
  assert.doesNotMatch(html, /class="hot-group"/);
  for (const value of ['Actor','Studio','Tag','42','2 个资料来源']) assert.ok(html.includes(value));
});

test('age gate provides CookieCloud hint and modal remains reopenable during detection', async () => {
  const h = harness();
  h.handle(() => ({ can_check: true, sources: [{name:'Site',url:'https://example.invalid/',result:{state:'age_gate',message:'confirm age'}}], job:{running:true,completed:1,total:30} }));
  await h.api.loadConnections();
  assert.match(h.ids['hot-source-list'].innerHTML,/CookieCloud/);
  await h.api.checkConnections();
  assert.equal(h.ids['hot-connections'].open,true);
  assert.equal(h.calls.filter(c=>c.options.method==='POST').length,0);
});


test('age declaration requires explicit checkbox and posts only the fixed source id', async () => {
  const h = harness();
  h.api.state.connections = { can_check:true, sources:[{id:'giga',name:'GIGA',age:{supported:true}}] };
  h.api.openAge('giga');
  assert.equal(h.ids['hot-age-dialog'].open,true);
  assert.equal(h.ids['hot-age-confirm'].checked,false);
  await h.api.submitAge({preventDefault(){}});
  assert.equal(h.calls.length,0);
  h.ids['hot-age-confirm'].checked=true;
  h.handle(url => url.endsWith('/age/giga') ? {running:true} : {can_check:true,sources:[],job:{}});
  await h.api.submitAge({preventDefault(){}});
  const call=h.calls.find(c=>c.options.method==='POST');
  assert.equal(call.url,'/api/hot/age/giga');
  assert.deepEqual(JSON.parse(call.options.body),{confirmed:true});
  assert.equal(h.ids['hot-age-dialog'].open,true);
  assert.equal(h.ids['hot-age-confirm'].checked,false);
});

test('running age confirmation keeps connection polling and CookieCloud fallback', async () => {
  const h=harness();
  h.handle(url => url.includes('/connections') ? {can_check:true,sources:[{id:'giga',name:'GIGA',url:'https://www.giga-web.jp/',age:{supported:true,running:true},result:{state:'age_gate',message:'confirm'}}],job:{running:false,retry_after:0}} : data());
  await h.enter();
  assert.match(h.ids['hot-source-list'].innerHTML,/年龄确认中/);
  assert.match(h.ids['hot-source-list'].innerHTML,/CookieCloud 备用同步/);
  assert.ok([...h.timers.values()].some(t=>t.delay===2000));
});


test('age progress stays visible until completion and renders failure then success', async () => {
  const h=harness();
  h.api.state.ageSource='giga';h.api.state.ageSeenRun=true;
  h.handle(()=>({sources:[{id:'giga',name:'GIGA',age:{running:true,phase:'submitting',message:'正在提交…'},result:{state:'age_gate'}}],job:{}}));
  await h.api.loadConnections();assert.match(h.ids['hot-age-message'].textContent,/正在提交/);assert.equal(h.ids['hot-age-submit'].disabled,true);
  h.handle(()=>({sources:[{id:'giga',name:'GIGA',age:{running:false,phase:'finished',success:false,message:'原站仍要求确认'},result:{state:'age_gate'}}],job:{}}));
  await h.api.loadConnections();assert.match(h.ids['hot-age-message'].textContent,/原站仍要求/);assert.equal(h.ids['hot-age-message'].dataset.error,'true');
  h.handle(()=>({sources:[{id:'giga',name:'GIGA',age:{running:false,phase:'finished',success:true,message:'确认已通过'},result:{state:'ok'}}],job:{}}));
  await h.api.loadConnections();assert.match(h.ids['hot-age-message'].textContent,/确认已通过/);assert.equal(h.ids['hot-age-message'].dataset.error,'false');
});

test('script-rendered HTML is counted connected; timeout offers server-specific retry', async()=>{
 const h=harness();h.handle(()=>({can_check:true,network:{label:'默认预设代理'},job:{finished_at:'2026-11-02T00:00:00Z'},sources:[
  {id:'avsox',name:'AVSOX',result:{state:'js_shell',message:'HTTP 已连通'}},
  {id:'dmm',name:'DMM',result:{state:'timeout',message:'服务端超时'}}]}));
 await h.api.loadConnections();assert.match(h.ids['hot-connection-count'].textContent,/1 个已连通/);assert.match(h.ids['hot-source-list'].innerHTML,/需脚本渲染/);assert.match(h.ids['hot-source-list'].innerHTML,/重测此站/);assert.match(h.ids['hot-check-message'].textContent,/默认预设代理/);
});


test('covers use only registered same-origin URLs with lazy loading and escaped alt', async()=>{
 const h=harness();const d=data();d.items=[{...d.groups[0].items[0],identifier:'ABC-123',cover:'/api/hot/covers/'+'a'.repeat(64)+'.jpg'}];h.handle(()=>d);await h.api.loadFilms();
 const html=h.ids['hot-results'].innerHTML;assert.match(html,/class="hot-cover-image"/);assert.match(html,/loading="lazy"/);assert.match(html,/decoding="async"/);assert.match(html,/ABC-123 封面/);
 assert.equal(h.api.coverUrl('https://evil.invalid/cover.jpg'),'');assert.equal(h.api.coverUrl('javascript:alert(1)'),'');
 d.items[0].cover='https://remote.invalid/image.jpg';await h.api.loadFilms();assert.doesNotMatch(h.ids['hot-results'].innerHTML,/<img/);assert.match(h.ids['hot-results'].innerHTML,/暂无封面/);
});

test('cover failure and subsequent load toggle accessible placeholder and retry',()=>{
 const h=harness();const placeholder={textContent:''};const retry={hidden:true};const wrap={dataset:{},querySelector:selector=>selector.includes('placeholder')?placeholder:retry};
 const image={matches:()=>true,closest:()=>wrap};h.api.coverFailed({target:image});assert.equal(wrap.dataset.coverState,'error');assert.equal(retry.hidden,false);assert.equal(placeholder.textContent,'封面加载失败');
 h.api.coverLoaded({target:image});assert.equal(wrap.dataset.coverState,'loaded');assert.equal(retry.hidden,true);assert.equal(placeholder.textContent,'');
});
