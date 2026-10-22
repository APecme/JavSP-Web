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
  const error = make('error', '[data-stills-error]');
  const counter = make('counter', '[data-stills-counter]');
  const prev = make('prev', '[data-stills-prev]');
  const next = make('next', '[data-stills-next]');
  const closeButton = make('close', '[data-stills-close]');
  error.hidden = true;
  prev.disabled = true;
  next.disabled = true;
  dialog.children = {
    '.stills-image': image, '[data-stills-error]': error, '[data-stills-counter]': counter,
    '[data-stills-prev]': prev, '[data-stills-next]': next, '[data-stills-close]': closeButton,
  };
  const opener = make('opener');
  const context = vm.createContext({
    document: { querySelector: selector => selector === '#stills-dialog' ? dialog : null },
    encodeURIComponent,
  });
  window_context(context);
  const module = () => context.window.JavspStills;
  const load = () => vm.runInContext(slice(app(), STILLS_START, STILLS_END), context);
  const open = (index = 0, options = {}) => module().open(Object.assign({ taskId, index, total, version: 'v1', opener }, options));
  return { context, state, focused, dialog, image, error, counter, prev, next, closeButton, opener, module, load, open };
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
  vm.runInContext(slice(source, 'function fanartGridMarkup(', 'async function openTaskDetail('), context);
  const markup = context.fanartGridMarkup(
    { id: 'a/b', fanart_count: 2, updated_at: '2026-10-22T10:00:00' },
    { fanart_total: 4, fanart_failures: [4] },
  );
  assert.match(markup, /<button type="button" class="detail-fanart" data-fanart-open="0" data-fanart-task="a\/b" data-fanart-total="2"/);
  assert.match(markup, /aria-label="放大查看剧照 1，共 2 张"/);
  assert.match(markup, /src="\/api\/tasks\/a%2Fb\/fanart\/1\?v=2026-10-22T10%3A00%3A00" loading="lazy" alt=""/);
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
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1');
  assert.equal(v.image.alt, '剧照 2');
  assert.equal(v.counter.textContent, '2 / 3');
  assert.equal(v.prev.disabled, false);
  assert.equal(v.next.disabled, false);
  assert.equal(v.state.activeElement, v.closeButton, 'focus moves into the viewer');

  v.open(0);
  assert.equal(v.prev.disabled, true);
  assert.equal(v.module().step(-1), false, 'first still cannot step backwards');
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/0?v=v1');
  v.module().step(1); v.module().step(1);
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/2?v=v1');
  assert.equal(v.next.disabled, true);
  assert.equal(v.module().step(1), false, 'last still cannot step forwards');
  assert.equal(v.counter.textContent, '3 / 3');
});

test('out of range requests and empty galleries never open the viewer', () => {
  const v = viewer({ total: 2 }); v.load();
  assert.equal(v.open(9), true);
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1', 'index is clamped to the last still');
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
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/1?v=v1');
  v.dialog.dispatch('keydown', { key: 'ArrowLeft' });
  assert.equal(v.image.src, '/api/tasks/task%201/fanart/0?v=v1');
  const escape = v.dialog.dispatch('keydown', { key: 'Escape' });
  assert.equal(escape.defaultPrevented, true);
  assert.equal(escape.propagationStopped, true, 'Escape must not reach the film detail dialog');
  assert.equal(v.dialog.open, false);
  assert.equal(v.module().isOpen(), false);
});

test('closing the viewer restores focus and drops the full size image', () => {
  const v = viewer({ total: 3 }); v.load();
  v.open(2);
  assert.equal(v.image.getAttribute('src'), '/api/tasks/task%201/fanart/2?v=v1');
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
  assert.equal(v.error.hidden, false);
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

test('the film detail keeps exactly one close control, inside the sticky navigation', () => {
  const document = html();
  const detail = slice(document, '<dialog id="task-detail-dialog"', '<dialog id="metadata-refresh-dialog"');
  assert.equal((detail.match(/data-dialog-close/g) || []).length, 1, 'only one close affordance');
  const navigation = slice(detail, '<nav class="film-navigation"', '</nav>');
  assert.match(navigation, /class="film-nav-close" data-dialog-close aria-label="关闭影片详情"/);
  assert.doesNotMatch(slice(detail, '<div class="panel-heading">', '</div>'), /data-dialog-close/, 'the title bar has no second close control');
  const openDetail = slice(app(), 'async function openTaskDetail(', 'function artworkEditor(');
  assert.doesNotMatch(openDetail, /\.film-navigation'\)\.hidden/, 'scan tasks keep the single close entry');
  assert.match(openDetail, /\.film-navigation \[data-detail-section\]'\)\.forEach\(/, 'only the section buttons hide for scans');
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
