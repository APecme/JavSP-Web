const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const appSource = () => read('javsp_web/web/assets/app.js');

function slice(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0, `missing slice start: ${start}`);
  assert.ok(to > from, `missing slice end: ${end}`);
  return source.slice(from, to);
}

const MARKUP_START = '// Downloaded stills become labelled buttons';
const MARKUP_END = 'async function openTaskDetail(';

// The grid module only needs these collaborators, so stub them like test_film_detail_ux.cjs does.
function loadGridModule(context) {
  const source = appSource();
  vm.runInContext(slice(source, MARKUP_START, MARKUP_END), context);
  return context;
}

function markupContext() {
  const context = vm.createContext({
    escapeHtml: value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character])),
    encodeURIComponent,
    artworkPlaceholder: (className, label) => `<span class="${className}"><b>${label}</b></span>`,
  });
  context.window = context;
  return context;
}

const STILL_BUTTON = /<button type="button" class="detail-fanart" data-fanart-open="(\d+)"/g;

test('only the first small batch of stills carries src; the rest stay as accessible placeholders', () => {
  const context = loadGridModule(markupContext());
  const markup = context.fanartGridMarkup(
    { id: 'a/b', fanart_count: 10, updated_at: 'v1' },
    { fanart_total: 10 },
  );
  const buttons = [...markup.matchAll(STILL_BUTTON)].map(match => Number(match[1]));
  assert.deepEqual(buttons, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 'every downloaded still stays a labelled button');

  // Request budget: at most the eager batch may point at real artwork URLs.
  const sources = (markup.match(/<img src="[^"]+"/g) || []);
  assert.ok(sources.length > 0, 'the eager batch loads immediately');
  assert.ok(sources.length <= 4, `expected at most 4 eager requests, got ${sources.length}`);
  assert.ok(sources[0].includes('/api/tasks/a%2Fb/fanart/0?v=v1'), 'still 0 keeps its src for the backdrop and viewer');

  // Deferred stills: coordinates kept, real URL parked in data-fanart-src, accessible loading state.
  for (const index of [4, 5, 6, 7, 8, 9]) {
    const at = markup.indexOf(`data-fanart-open="${index}"`);
    assert.ok(at >= 0, `missing deferred still ${index}`);
    const end = markup.indexOf('</button>', at);
    const chunk = markup.slice(at, end);
    assert.match(chunk, new RegExp(`data-fanart-src="/api/tasks/a%2Fb/fanart/${index}\\?v=v1&thumbnail=true"`), `still ${index} parks its thumbnail URL`);
    assert.match(chunk, /data-fanart-total="10" data-fanart-version="v1"/);
    assert.match(chunk, /role="status"[^>]*aria-label="剧照 \d+ 加载中"/, `still ${index} exposes a loading status`);
    assert.doesNotMatch(chunk, /<img[^>]*\ssrc=/, `still ${index} must not request its image yet`);
  }
});

test('small galleries keep the old eager behaviour and missing/failed slots keep their placeholder', () => {
  const context = loadGridModule(markupContext());
  const small = context.fanartGridMarkup(
    { id: 'a/b', fanart_count: 2, updated_at: '2026-10-22T10:00:00' },
    { fanart_total: 4, fanart_failures: [4] },
  );
  assert.match(small, /src="\/api\/tasks\/a%2Fb\/fanart\/1\?v=2026-10-22T10%3A00%3A00&thumbnail=true" loading="lazy" alt=""/);
  assert.match(small, /剧照 3 未下载/);
  assert.match(small, /剧照 4 下载失败/);
  assert.equal(context.fanartGridMarkup({ id: 'x', fanart_count: 0 }, { fanart_total: 0 }), '<p class="muted">暂无剧照</p>');
});

test('strip images request thumbnails while the stills viewer keeps the full-size URL', () => {
  const context = loadGridModule(markupContext());
  const markup = context.fanartGridMarkup(
    { id: 'a/b', fanart_count: 6, updated_at: 'v1' },
    { fanart_total: 6 },
  );
  // Every URL the strip actually requests (eager src + parked data-fanart-src) is a thumbnail.
  const requested = [...markup.matchAll(/(?:<img src="|data-fanart-src=")([^"]+)"/g)].map(match => match[1]);
  assert.ok(requested.length >= 6, 'each downloaded still exposes one requestable URL');
  for (const url of requested) {
    assert.ok(url.includes('&thumbnail=true'), `strip URL must request the thumbnail: ${url}`);
    assert.ok(url.startsWith('/api/tasks/a%2Fb/fanart/'), `thumbnail keeps the fanart route: ${url}`);
  }

  // The viewer builds its own URLs from data attributes.
  const stills = slice(appSource(), 'window.JavspStills = (() => {', '// --- end stills viewer ---');
  const urlLine = stills.split('\n').find(line => line.includes('Key(') && line.includes('setAttribute'));
  assert.ok(urlLine, 'viewer assigns its fanart URL');
  assert.match(stills, /&size=view`;/, 'viewer requests the view-size render');
  assert.match(stills, /&thumbnail=true`;/, 'viewer keeps the server thumbnail as placeholder');
  // The full-size original stays available as the error fallback.
  assert.match(stills, /fullKey[\s\S]*?\/fanart\/\$\{index\}\?v=\$\{encodeURIComponent\(version\)\}`;/, 'original fanart URL kept as fallback');
  // ±1 neighbour preloading warms the decode cache.
  assert.match(stills, /preloadAround/, 'viewer preloads neighbours');
  assert.match(stills, /new Image\(\)/, 'preloading goes through Image');
  assert.match(stills, /\.decode\?\.\(\)/, 'preloads wait for decode()');
});

/* ---- DOM stubs with real src assignment and real event dispatch ---- */

function makeImage() {
  return {
    attrs: {}, listeners: {},
    setAttribute(name, value) { this.attrs[name] = String(value); },
    getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
    removeAttribute(name) { delete this.attrs[name]; },
    addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); },
    dispatch(type, extra = {}) {
      (this.listeners[type] || []).forEach(listener => listener(Object.assign({ target: this }, extra)));
    },
  };
}

function makeButton(index, url, { top = 0, left = 0 } = {}) {
  const image = makeImage();
  const deferred = index >= 4;
  if (!deferred) image.attrs.src = url;
  const button = {
    index, image,
    dataset: { fanartOpen: String(index), fanartTask: 't', fanartTotal: '10', fanartVersion: 'v1' },
    attrs: { 'aria-label': `放大查看剧照 ${index + 1}` },
    innerHTML: deferred
      ? `<img alt=""><span class="detail-fanart-loading" role="status">剧照 ${index + 1} 加载中</span>`
      : `<img src="${url}" alt="">`,
    placeholder: { removed: false, remove() { this.removed = true; } },
    rect: { top, left },
    getBoundingClientRect() { return this.rect; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; },
    removeAttribute(name) {
      delete this.attrs[name];
      if (name === 'data-fanart-src') delete this.dataset.fanartSrc;
      if (name === 'data-fanart-open') delete this.dataset.fanartOpen;
    },
    querySelector(selector) {
      if (selector === 'img') return this.image;
      if (selector === '.detail-fanart-loading') return (deferred && !this.placeholder.removed) ? this.placeholder : null;
      return null;
    },
  };
  if (deferred) button.dataset.fanartSrc = url;
  return button;
}

function makeGrid(buttons) {
  return {
    querySelectorAll(selector) {
      assert.equal(selector, '[data-fanart-src]');
      return buttons.filter(button => button.dataset.fanartSrc !== undefined);
    },
  };
}

function ioContext() {
  const instances = [];
  const context = markupContext();
  context.IntersectionObserver = class {
    constructor(callback, options) { this.callback = callback; this.options = options; this.observed = []; this.unobserved = []; this.disconnected = false; instances.push(this); }
    observe(target) { this.observed.push(target); }
    unobserve(target) { this.unobserved.push(target); }
    disconnect() { this.disconnected = true; }
    approach(target) { this.callback([{ isIntersecting: true, target }], this); }
    skip(target) { this.callback([{ isIntersecting: false, target }], this); }
  };
  return { context, instances };
}

test('hydrateFanartGrid wires an IntersectionObserver that assigns src only near the viewport', () => {
  const { context, instances } = ioContext();
  loadGridModule(context);
  assert.equal(typeof context.hydrateFanartGrid, 'function', 'app.js must expose the progressive loader');

  const buttons = Array.from({ length: 10 }, (_, index) => makeButton(index, `/fanart/${index}?v=v1`));
  const grid = makeGrid(buttons);
  const scroller = { tag: 'dialog' };
  context.hydrateFanartGrid(grid, scroller);

  assert.equal(instances.length, 1);
  const observer = instances[0];
  assert.equal(observer.observed.length, 6, 'only the 6 deferred stills are observed');
  assert.deepEqual(observer.observed.map(button => button.index), [4, 5, 6, 7, 8, 9]);
  assert.equal(observer.options.root, grid, 'the strip itself is the scroll root that clips deferred stills');
  assert.equal(observer.options.rootMargin, '0px 900px', 'the strip prefetches ahead horizontally');
  assert.ok(buttons.slice(0, 4).every(button => button.image.attrs.src === `/fanart/${button.index}?v=v1`));
  assert.ok(buttons.slice(4).every(button => button.image.attrs.src === undefined), 'deferred stills must not request yet');

  // A non-intersecting entry must do nothing.
  observer.skip(buttons[5]);
  assert.equal(buttons[5].image.attrs.src, undefined);

  // Approaching the viewport assigns the parked URL exactly once and clears the placeholder.
  observer.approach(buttons[5]);
  assert.equal(buttons[5].image.attrs.src, '/fanart/5?v=v1');
  assert.equal(buttons[5].dataset.fanartSrc, undefined, 'the parked URL is consumed');
  assert.equal(buttons[5].placeholder.removed, true);
  assert.ok(observer.unobserved.includes(buttons[5]));
  assert.equal(buttons[6].image.attrs.src, undefined, 'other deferred stills still wait');
  assert.equal(observer.disconnected, false, 'a partially loaded grid keeps observing');
});

test('re-rendering the grid disconnects the previous observer before wiring a new one', () => {
  const { context, instances } = ioContext();
  loadGridModule(context);
  const first = makeGrid([makeButton(4, '/fanart/4')]);
  const second = makeGrid([makeButton(4, '/fanart/4'), makeButton(5, '/fanart/5')]);
  context.hydrateFanartGrid(first, {});
  context.hydrateFanartGrid(second, {});
  assert.equal(instances.length, 2);
  assert.equal(instances[0].disconnected, true, 'the stale observer must disconnect');
  assert.equal(instances[1].disconnected, false);
});

test('a still that fails to load swaps to the failure placeholder and stops opening the viewer', () => {
  const { context, instances } = ioContext();
  loadGridModule(context);
  const button = makeButton(5, '/fanart/5?v=v1');
  context.hydrateFanartGrid(makeGrid([button]), {});
  instances[0].approach(button);
  assert.equal(button.image.attrs.src, '/fanart/5?v=v1');
  button.image.dispatch('error');
  assert.match(button.innerHTML, /detail-fanart-empty/, 'failure keeps the existing placeholder style');
  assert.match(button.innerHTML, /剧照 6 加载失败/);
  assert.equal(button.dataset.fanartOpen, undefined, 'a failed still no longer opens the viewer');
});

test('without IntersectionObserver the fallback hydrates ahead horizontally while scrolling', () => {
  const context = markupContext();
  loadGridModule(context);

  const buttons = Array.from({ length: 10 }, (_, index) => makeButton(index, `/fanart/${index}?v=v1`, { left: index * 180 }));
  const grid = makeGrid(buttons);
  grid.listeners = {};
  grid.getBoundingClientRect = () => ({ left: 0, right: 900 });
  grid.addEventListener = (type, listener) => { (grid.listeners[type] ||= []).push(listener); };
  grid.removeEventListener = (type, listener) => { grid.listeners[type] = (grid.listeners[type] || []).filter(item => item !== listener); };
  context.hydrateFanartGrid(grid, {});
  assert.equal(buttons.slice(4).every(button => button.image.attrs.src === undefined), true, 'fallback also defers initially');

  const onScroll = (grid.listeners.scroll || [])[0];
  assert.equal(typeof onScroll, 'function', 'fallback listens for scroll on the horizontally scrolling strip');
  onScroll();
  const loaded = buttons.filter(button => button.image.attrs.src !== undefined).length;
  assert.ok(loaded > 4, `the first scroll must prefetch past the eager batch (loaded ${loaded})`);
  assert.ok(loaded <= 8, `one scroll may not restore the whole grid (loaded ${loaded})`);

  // Scrolling further hydrates the remaining batches, never everything at once.
  for (let step = 0; step < 5 && buttons.some(button => button.image.attrs.src === undefined); step += 1) onScroll();
  assert.equal(buttons.every(button => button.image.attrs.src !== undefined), true, 'continued scrolling eventually loads everything');
});

test('openTaskDetail hydrates the freshly rendered grid inside the dialog', () => {
  const detail = slice(appSource(), 'async function openTaskDetail(', 'function artworkEditor(');
  assert.match(detail, /hydrateFanartGrid\(\$\('#task-detail-content'\)\.querySelector\('\.detail-fanart-grid'\), dialog\)/, 'detail render must start progressive loading against the dialog viewport');
});
