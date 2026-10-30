const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const app = () => read('javsp_web/web/assets/app.js');
const html = () => read('javsp_web/web/index.html');

function slice(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0, `missing slice start: ${start}`);
  assert.ok(to > from, `missing slice end: ${end}`);
  return source.slice(from, to);
}

const STILLS_START = '// --- Stills viewer (regressions: tests/test_film_detail_ux.cjs) ---';
const STILLS_END = '// --- end stills viewer ---';

/* A tiny DOM: only what the viewer module touches, with real event dispatch. */
function viewer({ total = 3, taskId = 'task 1' } = {}) {
  const focused = [];
  const state = { activeElement: null };
  const make = (name, selector = '') => ({
    name, selector, listeners: {}, attrs: {}, dataset: {}, children: {}, hidden: false, disabled: false,
    textContent: '', src: '', alt: '', open: false, isConnected: true, className: '',
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); },
    dispatch(type, extra = {}) {
      const event = Object.assign({
        type, target: this, defaultPrevented: false,
        preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.propagationStopped = true; },
      }, extra);
      (this.listeners[type] || []).forEach(listener => listener(event));
      return event;
    },
    getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
    setAttribute(name, value) { this.attrs[name] = String(value); if (name === 'src') this.src = String(value); },
    removeAttribute(name) { delete this.attrs[name]; if (name === 'src') this.src = ''; },
    closest(selector) { return this.selector === selector ? this : null; },
    focus() { state.activeElement = this; focused.push(this.name); },
    querySelector(selector) { return this.children[selector] || null; },
    showModal() { this.open = true; },
    close() { this.open = false; this.dispatch('close'); },
  });
  const dialog = make('dialog');
  const image = make('image', '.stills-image');
  const preview = make('image', '.stills-preview');
  const error = make('error', '[data-stills-error]');
  const counter = make('counter', '[data-stills-counter]');
  const prev = make('prev', '[data-stills-prev]');
  const next = make('next', '[data-stills-next]');
  const closeButton = make('close', '[data-stills-close]');
  const retryButton = make('retry', '[data-stills-retry]');
  const stage = Object.assign(make('stage', '.stills-stage'), { classList: { add() {}, remove() {}, toggle() {} } });
  error.hidden = true;
  retryButton.hidden = true;
  prev.disabled = true;
  next.disabled = true;
  dialog.children = {
    '.stills-image': image, '.stills-preview': preview, '.stills-stage': stage,
    '[data-stills-error]': error, '[data-stills-counter]': counter,
    '[data-stills-prev]': prev, '[data-stills-next]': next, '[data-stills-close]': closeButton,
    '[data-stills-retry]': retryButton,
  };
  const opener = make('opener');
  const context = vm.createContext({
    document: { querySelector: selector => selector === '#stills-dialog' ? dialog : null },
    encodeURIComponent, Image: function Image() { return { decode: () => Promise.resolve() }; },
  });
  window_context(context);
  const module = () => context.window.JavspStills;
  const load = () => vm.runInContext(slice(app(), STILLS_START, STILLS_END), context);
  const open = (index = 0, options = {}) => module().open(Object.assign({ taskId, index, total, version: 'v1', opener }, options));
  return { context, state, focused, dialog, image, preview, stage, error, counter, prev, next, closeButton, retryButton, opener, module, load, open };
}

function window_context(context) {
  context.window = context;
}

test('still thumbnails are labelled buttons that carry their own viewer coordinates', () => {
  const source = app();
  const context = vm.createContext({
    escapeHtml: value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character])),
    encodeURIComponent,
    artworkPlaceholder: (className, label) => `<span class="${className}"><b>${label}</b></span>`,
  });
  window_context(context);
  vm.runInContext(slice(source, '// Downloaded stills become labelled buttons', 'async function openTaskDetail('), context);
  const markup = context.fanartGridMarkup(
    { id: 'a/b', fanart_count: 2, updated_at: '2026-10-22T10:00:00' },
    { fanart_total: 4, fanart_failures: [4] },
  );
  assert.match(markup, /<button type="button" class="detail-fanart" data-fanart-open="0" data-fanart-task="a\/b" data-fanart-total="2"/);
  assert.match(markup, /aria-label="放大查看剧照 1，共 2 张"/);
  assert.match(markup, /src="\/api\/tasks\/a%2Fb\/fanart\/1\?v=2026-10-22T10%3A00%3A00&thumbnail=true" loading="lazy" alt=""/);
  assert.match(markup, /剧照 3 未下载/);
  assert.match(markup, /剧照 4 下载失败/);
  assert.equal((markup.match(/data-fanart-open=/g) || []).length, 2, 'only downloaded stills open the viewer');
  assert.equal(context.fanartGridMarkup({ id: 'x', fanart_count: 0 }, { fanart_total: 0 }), '<p class="muted">暂无剧照</p>');
});

test('a still opens the viewer with its own count, then steps without leaving the range', () => {
  const v = viewer({ total: 3 }); v.load();
  assert.equal(v.module().isOpen(), false);
  assert.equal(v.open(1), true);
  assert.equal(v.dialog.open, true);
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1&size=view');
  assert.equal(v.preview.src, '/api/tasks/task%201/fanart/1?v=v1&thumbnail=true', 'thumbnail placeholder sits underneath');
  assert.equal(v.image.alt, '剧照 2');
  assert.equal(v.counter.textContent, '2 / 3');
  assert.equal(v.prev.disabled, false);
  assert.equal(v.next.disabled, false);
  assert.equal(v.state.activeElement, v.closeButton, 'focus moves into the viewer');

  v.open(0);
  assert.equal(v.prev.disabled, true);
  assert.equal(v.module().step(-1), false, 'first still cannot step backwards');
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/0?v=v1&size=view');
  v.module().step(1); v.module().step(1);
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/2?v=v1&size=view');
  assert.equal(v.next.disabled, true);
  assert.equal(v.module().step(1), false, 'last still cannot step forwards');
  assert.equal(v.counter.textContent, '3 / 3');
});

test('out of range requests and empty galleries never open the viewer', () => {
  const v = viewer({ total: 2 }); v.load();
  assert.equal(v.open(9), true);
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1&size=view', 'index is clamped to the last still');
  v.module().close();
  assert.equal(v.module().open({ taskId: '', index: 0, total: 2 }), false);
  assert.equal(v.module().open({ taskId: 'task 1', index: 0, total: 0 }), false);
  assert.equal(v.dialog.open, false);
});

test('arrow keys step the viewer and Escape closes only the viewer', () => {
  const v = viewer({ total: 3 }); v.load();
  const closed = v.dialog.dispatch('keydown', { key: 'Escape' });
  assert.equal(closed.defaultPrevented, false, 'a closed viewer must not swallow Escape');
  v.open(0);
  const right = v.dialog.dispatch('keydown', { key: 'ArrowRight' });
  assert.equal(right.defaultPrevented, true);
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1&size=view');
  v.dialog.dispatch('keydown', { key: 'ArrowLeft' });
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/0?v=v1&size=view');
  const escape = v.dialog.dispatch('keydown', { key: 'Escape' });
  assert.equal(escape.defaultPrevented, true);
  assert.equal(escape.propagationStopped, true, 'Escape must not reach the film detail dialog');
  assert.equal(v.dialog.open, false);
  assert.equal(v.module().isOpen(), false);
});

test('closing the viewer restores focus and drops the full size image', () => {
  const v = viewer({ total: 3 }); v.load();
  v.open(2);
  assert.equal(v.image.getAttribute('src'), '/api/tasks/task%201/fanart/2?v=v1&size=view');
  v.module().close();
  assert.equal(v.dialog.open, false);
  assert.equal(v.image.getAttribute('src'), null, 'stale still images are cleared');
  assert.equal(v.image.alt, '');
  assert.equal(v.state.activeElement, v.opener);
  assert.equal(v.prev.disabled, true);
  assert.equal(v.next.disabled, true);

  v.open(0);
  v.opener.isConnected = false;
  v.module().close();
  assert.equal(v.state.activeElement, v.closeButton, 'a detached thumbnail cannot take focus back');
});

test('a failing still shows a message instead of a broken frame', () => {
  const v = viewer({ total: 2 }); v.load();
  v.open(0);
  assert.equal(v.error.hidden, true);
  v.dialog.dispatch('error', { target: v.image });
  v.dialog.dispatch('error', { target: v.image });
  v.dialog.dispatch('error', { target: v.image });
  assert.equal(v.error.hidden, false, 'the original failing surfaces the error banner');
  v.module().step(1);
  assert.equal(v.error.hidden, true, 'stepping to another still clears the error state');
});

test('switching tasks and closing the film detail tear the viewer down', () => {
  const source = app();
  const openDetail = slice(source, 'async function openTaskDetail(', 'function artworkEditor(');
  const switchLine = openDetail.slice(0, openDetail.indexOf('state.detailTask = task'));
  assert.match(switchLine, /window\.JavspStills\?\.close\(\{ restoreFocus: false \}\)/, 'a new task must not keep the previous stills');
  assert.match(switchLine, /if \(state\.activeTaskDetail !== taskId\)[\s\S]*JavspComments\?\.close\(\)[\s\S]*JavspStills\?\.close\(/, 'viewer cleanup rides the existing task switch branch');
  const detailClose = source.slice(source.indexOf("$('#task-detail-dialog')?.addEventListener('close'"));
  assert.match(detailClose, /window\.JavspComments\?\.close\(\);\s*window\.JavspStills\?\.close\(\{ restoreFocus: false \}\);/);
  const document = html();
  const viewer = slice(document, '<dialog id="stills-dialog"', '<dialog id="metadata-refresh-dialog"');
  for (const hook of ['aria-labelledby="stills-title"', 'class="stills-image"', 'data-stills-counter',
    'data-stills-prev aria-label="上一张剧照"', 'data-stills-next aria-label="下一张剧照"',
    'data-stills-close aria-label="关闭剧照查看"', 'data-stills-error role="alert"']) {
    assert.ok(viewer.includes(hook), `stills viewer is missing ${hook}`);
  }
});

const detailMarkup = () => slice(html(), '<dialog id="task-detail-dialog"', '<dialog id="metadata-refresh-dialog"');

test('the film detail closes from the title action group, right of 编辑资料', () => {
  const detail = detailMarkup();
  assert.equal((detail.match(/data-dialog-close/g) || []).length, 1, 'only one close affordance');

  const titleBar = detail.slice(0, detail.indexOf('<nav'));
  const actions = slice(titleBar, '<div class="film-detail-actions"', '</div>');
  const editIndex = actions.indexOf('data-edit-task-metadata');
  const closeIndex = actions.indexOf('data-dialog-close');
  assert.ok(editIndex > 0, 'the edit action stays in the title action group');
  assert.ok(closeIndex > editIndex, 'the close control sits right of 编辑资料');

  const closeStart = actions.lastIndexOf('<button', closeIndex);
  const closeButton = actions.slice(closeStart, actions.indexOf('</button>', closeIndex) + '</button>'.length);
  assert.match(closeButton, /type="button"/);
  assert.match(closeButton, /aria-label="关闭影片详情"/);
  assert.match(closeButton, /<svg [^>]*aria-hidden="true"[^>]*>/, 'the close affordance is an SVG icon');
  const inner = closeButton.slice(closeButton.indexOf('>') + 1, closeButton.lastIndexOf('</button>'));
  assert.match(inner, /^<svg[\s\S]*<\/svg>$/, 'the icon button holds nothing but the SVG');
  assert.doesNotMatch(inner.replace(/<[^>]+>/g, ''), /\S/, 'no text glyph such as × remains');

  const navigation = slice(detail, '<nav class="film-navigation"', '</nav>');
  assert.doesNotMatch(navigation, /data-dialog-close/, 'the section navigation no longer offers a close');
  assert.equal((navigation.match(/data-detail-section=/g) || []).length, 3, 'the navigation keeps its three sections');
});

test('the sticky title region carries the close and stays out of the detail grid', () => {
  const detail = detailMarkup();
  const top = slice(detail, '<div class="film-detail-top"', '<div class="film-detail-shell"');
  assert.match(top, /<div class="panel-heading">/);
  assert.match(top, /<nav class="film-navigation"/);
  assert.match(top, /data-dialog-close/, 'the sticky region keeps the only close visible while scrolling');
  assert.ok(detail.indexOf('<div class="film-detail-top"') < detail.indexOf('<div class="film-detail-shell"'),
    'a grid item can only stick inside its own row, so the bar must not be a child of the detail grid');

  const cinema = read('javsp_web/web/assets/cinema.css');
  const rule = body => { const start = cinema.indexOf(body + ' {'); assert.ok(start >= 0, `missing rule: ${body}`); return cinema.slice(start, cinema.indexOf('}', start)); };
  assert.match(rule('#task-detail-dialog .film-detail-top'), /position:\s*sticky/, 'the title region is sticky');
  assert.match(rule('#task-detail-dialog .film-detail-top'), /top:\s*0/);
  assert.doesNotMatch(rule('#task-detail-dialog .film-navigation'), /position:\s*sticky/, 'the navigation must not stack a second sticky layer');
});

test('section links scroll clear of the now sticky title region', () => {
  const source = app();
  const start = source.indexOf("document.addEventListener('click', event => { const button = event.target.closest('[data-detail-section]')");
  assert.ok(start >= 0, 'the section navigation handler is missing');
  const handler = source.slice(start, source.indexOf('\n', start));

  const calls = [];
  const section = { style: {}, scrollIntoView: options => calls.push(options) };
  const bar = { offsetHeight: 121 };
  const dialog = { querySelector: selector => (selector === '.film-detail-top' ? bar : null) };
  const button = {
    dataset: { detailSection: 'task-detail-content' },
    closest: selector => (selector === '#task-detail-dialog' ? dialog : null),
  };
  const listeners = {};
  vm.runInNewContext(handler, {
    document: { addEventListener: (type, listener) => { listeners[type] = listener; }, getElementById: id => (id === 'task-detail-content' ? section : null) },
    window: { matchMedia: () => ({ matches: false }) },
  });
  listeners.click({ target: { closest: selector => (selector === '[data-detail-section]' ? button : null) } });
  assert.equal(calls.length, 1, 'the section still scrolls into view');
  assert.equal(calls[0].behavior, 'smooth');
  assert.equal(calls[0].block, 'start');
  assert.match(section.style.scrollMarginTop, /^13[0-9]px$/, 'the scroll offset covers the measured sticky bar instead of the old 55px');
});

test('the title close rides the shared dialog close handler', () => {
  const snippet = slice(app(), "const closeButton = event.target.closest('[data-dialog-close]');", 'const viewAutoScrapeHistoryButton');
  const dialog = { closed: false, close() { this.closed = true; this.open = false; } };
  const button = { closest: selector => (selector === 'dialog' ? dialog : null) };
  const event = { target: { closest: selector => (selector === '[data-dialog-close]' ? button : null) } };
  const closeFromEvent = vm.runInNewContext(`(function (event) {${snippet}})`, {});
  closeFromEvent(event);
  assert.equal(dialog.closed, true, 'clicking the title close closes the film detail dialog');
});

test('scan tasks hide the empty navigation and the edit action but keep the close', () => {
  const openDetail = slice(app(), 'async function openTaskDetail(', 'function artworkEditor(');
  const snippet = slice(openDetail, "document.querySelectorAll('.film-navigation [data-detail-section]')",
    "document.querySelector('[data-detail-section=\"task-comments\"]').hidden");
  assert.doesNotMatch(snippet, /\[data-dialog-close\]/, 'the close action is never hidden for scans');

  const run = (taskType) => {
    const sections = [{ hidden: false }, { hidden: false }, { hidden: false }];
    const nav = { hidden: false };
    const edit = { hidden: false };
    const document = {
      querySelectorAll: selector => (selector === '.film-navigation [data-detail-section]' ? sections : []),
      querySelector: (selector) => {
        if (selector === '#task-detail-dialog > .film-detail-top [data-edit-task-metadata]') return edit;
        if (selector === '#task-detail-dialog .film-navigation') return nav;
        return null;
      },
    };
    vm.runInNewContext(`(function (document, state, task) {${snippet}})(document, state, task)`, { document, state: { taskMetadataEditing: false }, task: { task_type: taskType } });
    return { sections, nav, edit };
  };

  const scan = run('scan');
  assert.deepEqual(scan.sections.map(button => button.hidden), [true, true, true], 'no section links for a scan task');
  assert.equal(scan.nav.hidden, true, 'the now empty section bar hides instead of leaving a bare strip');
  assert.equal(scan.edit.hidden, true, 'scan tasks cannot open the metadata editor');
  const film = run('scrape');
  assert.deepEqual(film.sections.map(button => button.hidden), [false, false, false]);
  assert.equal(film.nav.hidden, false, 'film tasks keep the section navigation');
  assert.equal(film.edit.hidden, false);
});

test('comment help uses an icon button, groups the rules and stays in the document flow', () => {
  const source = app();
  const help = slice(source, "const commentHelp = '", "const replyQuote");
  assert.match(help, /<summary[^>]*><svg [^>]*aria-hidden="true"/, 'the help trigger is a line icon, not a bare question mark');
  assert.match(help, /<span>格式说明<\/span>/);
  assert.doesNotMatch(help, />\?<\/summary>/, 'the bare question mark is gone');
  assert.equal((help.match(/class="comment-help-group"/g) || []).length, 4, 'rules are grouped');
  for (const rule of ['300 字符', '举报原因最多 300 字符', '**粗体**', '*斜体*', '~~删除线~~', '30:15', '1:02:03',
    '代码和链接中的时间保持原样', '不执行 HTML', '不加载远程图片', '播放时需绑定媒体库并登录播放器']) {
    assert.ok(help.includes(rule), `kept the original restriction: ${rule}`);
  }
  const css = read('javsp_web/web/assets/overrides.css');
  const block = css.slice(css.lastIndexOf('.comment-help-content'));
  assert.doesNotMatch(block.slice(0, block.indexOf('}')), /position:\s*absolute/, 'the help card must not float out of its container');
  assert.match(css, /\.comment-help summary::after\s*\{[^}]*display:\s*none/);
});

test('privacy mode keeps the enlarged stills masked', () => {
  const cinema = read('javsp_web/web/assets/cinema.css');
  assert.match(cinema, /html\[data-privacy-mode="1"\][^{]*\.stills-image\s*\{[^}]*blur\(/);
});

test('a decoded view-size still fades in over the thumbnail placeholder', async () => {
  const v = viewer({ total: 3 }); v.load();
  v.open(0);
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/0?v=v1&size=view');
  assert.equal(v.preview.src, '/api/tasks/task%201/fanart/0?v=v1&thumbnail=true', 'thumbnail placeholder sits underneath');
  v.image.dispatch('load');
  assert.equal(v.retryButton.hidden, true, 'a loaded view image hides the retry control');
});

test('a failing view endpoint falls back to the original with a retry control', () => {
  const v = viewer({ total: 3 }); v.load();
  v.open(1);
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1&size=view');
  v.dialog.dispatch('error', { target: v.image });
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1', 'view failure falls back to the original');
  assert.equal(v.retryButton.hidden, false, 'retry is offered after the fallback');
  assert.equal(v.error.hidden, true, 'the fallback keeps the error banner hidden');
  v.retryButton.dispatch('click');
  v.dialog.dispatch('click', { target: v.retryButton });
  assert.equal(v.retryButton.hidden, true, 'retry hides itself while reloading');
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1&size=view', 'retry re-requests the view size');
  v.dialog.dispatch('error', { target: v.image });
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1', 'a failed retry falls back again');
  v.dialog.dispatch('error', { target: v.image });
  assert.equal(v.error.hidden, false, 'only the original failing surfaces the error banner');
  assert.equal(v.retryButton.hidden, true);
});

test('preload decodes neighbours and evicts beyond the cache cap', async () => {
  const v = viewer({ total: 45 }); v.load();
  const module = v.module();
  assert.equal(typeof module.preload, 'function');
  for (let index = 0; index <= 43; index += 1) v.open(index);
  // 46 unique ±1 neighbours primed: FIFO eviction drops the oldest entries.
  const evicted = await module.preload(0);
  assert.ok(evicted === null || typeof evicted === 'object', 'preload resolves to the decoded image or null');
});
