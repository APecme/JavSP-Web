// Unified SVG icon system: whitelist, injection safety, DOM hydration and
// the accessibility/state behaviour of icon-bearing action buttons.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = file => fs.existsSync(path.join(root, file)) ? fs.readFileSync(path.join(root, file), 'utf8') : '';
const iconsSource = () => read('javsp_web/web/assets/icons.js');
const page = () => read('javsp_web/web/index.html');
const login = () => read('javsp_web/web/login.html');
const appSource = () => read('javsp_web/web/assets/app.js');
const aiSource = () => read('javsp_web/web/assets/ai.js');
const communitySource = () => read('javsp_web/web/assets/community.js');

// Minimal element model: textContent assignment removes children, exactly like
// the DOM, so an icon that survives a label update is proven to still be there.
function element(extra = {}) {
  const node = {
    children: [], disabled: false, hidden: false, _text: '', dataset: {}, attributes: {}, listeners: {},
    append(...items) { node.children.push(...items); },
    querySelector(selector) { return node.children.find(child => child.matchesSelector === selector) || null; },
    setAttribute(name, value) { node.attributes[name] = String(value); },
    addEventListener(name, listener) { node.listeners[name] = listener; },
    ...extra,
  };
  Object.defineProperty(node, 'textContent', {
    get() { return node._text; },
    set(value) { node._text = String(value); node.children = []; },
  });
  return node;
}

function contextFor(source, { hosts = [], readyState = 'complete' } = {}) {
  const inserted = [];
  for (const host of hosts) {
    Object.assign(host, {
      insertAdjacentHTML(position, markup) { inserted.push({ host, position, markup }); },
    });
  }
  const document = {
    readyState,
    listeners: {},
    addEventListener(name, listener) { document.listeners[name] = listener; },
    querySelectorAll(selector) { return selector === '[data-icon]' ? hosts : []; },
    querySelector() { return null; },
  };
  const context = vm.createContext({ document, console });
  context.window = context;
  vm.runInContext(source, context);
  return { context, document, inserted };
}

function icons() {
  assert.ok(iconsSource(), 'javsp_web/web/assets/icons.js exists');
  return contextFor(iconsSource()).context.JavspIcons;
}

test('every whitelisted icon renders one trusted 24px currentColor stroke SVG', () => {
  const api = icons();
  assert.equal(typeof api.render, 'function', 'window.JavspIcons.render(name, options)');
  const names = api.names();
  assert.ok(Array.isArray(names) && names.length >= 10, 'whitelist is populated');
  assert.deepEqual([...names].sort(), [...new Set(names)].sort(), 'names are unique');
  const widths = new Set();
  for (const name of names) {
    const markup = api.render(name);
    assert.match(markup, /^<svg\b/, `${name}: svg element`);
    assert.match(markup, /viewBox="0 0 24 24"/, `${name}: 24px viewBox`);
    assert.match(markup, /fill="none"/, `${name}: unfilled strokes`);
    assert.match(markup, /stroke="currentColor"/, `${name}: inherits currentColor`);
    assert.match(markup, /stroke-linecap="round"/, `${name}: round caps`);
    assert.match(markup, /stroke-linejoin="round"/, `${name}: round joins`);
    assert.match(markup, /aria-hidden="true"/, `${name}: decorative by default`);
    assert.match(markup, /focusable="false"/, `${name}: not in the tab order`);
    assert.match(markup, /class="javsp-icon/, `${name}: shared icon class`);
    assert.doesNotMatch(markup, /<(script|style|image|foreignObject|iframe)\b/i, `${name}: no nested embeddables`);
    assert.doesNotMatch(markup, /\son[a-z]+\s*=/i, `${name}: no inline event handlers`);
    widths.add(markup.match(/stroke-width="([\d.]+)"/)?.[1]);
  }
  assert.equal(widths.size, 1, 'all icons share one stroke width');
  assert.equal([...widths][0], '1.8', 'baseline stroke width is 1.8 (CSS may refine per control)');
});

test('unknown or hostile names never reach the SVG markup', () => {
  const api = icons();
  const hostile = [
    'nope', '', null, undefined, 0, '__proto__', 'constructor', 'toString', 'hasOwnProperty',
    'close"><script>alert(1)</script>', 'close onload=alert(1)', '<img src=x onerror=alert(1)>',
    "close' stroke-width='9", 42, {}, ['close'],
  ];
  for (const name of hostile) {
    const markup = api.render(name);
    assert.equal(markup, '', `render(${JSON.stringify(name)}) renders nothing`);
  }
  assert.equal(api.render('close').includes('script'), false);
});

test('options cannot smuggle attributes or markup into the rendered icon', () => {
  const api = icons();
  const base = api.render('close');
  assert.equal(api.render('close', undefined), base, 'no options keeps the baseline markup');
  assert.equal(api.render('close', null), base, 'null options keeps the baseline markup');
  const styled = api.render('close', { className: 'javsp-icon-lg' });
  assert.match(styled, /class="javsp-icon javsp-icon-lg"/, 'extra classes are appended');
  const hostileClass = api.render('close', { className: 'x" onload="alert(1)' });
  assert.doesNotMatch(hostileClass, /onload/i, 'hostile class names are stripped');
  assert.match(hostileClass, /class="javsp-icon[^"]*"/, 'hostile class names are filtered, not concatenated');
  const hostileWidth = api.render('close', { strokeWidth: '9" onload="x' });
  assert.match(hostileWidth, /stroke-width="1.8"/, 'non-numeric stroke widths are ignored');
  const wideWidth = api.render('close', { strokeWidth: 9 });
  assert.match(wideWidth, /stroke-width="1.8"/, 'out-of-range stroke widths are ignored');
  assert.match(api.render('close', { strokeWidth: 2.4 }), /stroke-width="2.4"/, 'in-range stroke widths apply');
});

test('hydration fills [data-icon] slots without touching labels, disabled state or accessibility text', () => {
  const whitelist = icons().names();
  assert.ok(whitelist.includes('plus'));
  const slot = element({ dataset: { icon: 'plus' } });
  const unknown = element({ dataset: { icon: 'not-an-icon' } });
  const after = element({ dataset: { icon: 'close', iconPosition: 'after' } });
  const button = element({ disabled: true, dataset: { icon: 'refresh' }, attributes: { 'aria-label': '刷新任务' } });
  const { context, inserted } = contextFor(iconsSource(), { hosts: [slot, unknown, after, button] });
  const api = context.JavspIcons;
  assert.ok(inserted.length >= 3, 'whitelisted slots receive an icon');
  for (const { markup } of inserted) assert.match(markup, /^<svg\b/);
  assert.ok(inserted.some(item => item.host === slot && item.position === 'afterbegin'), 'leading icons are prepended');
  assert.ok(inserted.some(item => item.host === after && item.position === 'beforeend'), 'trailing icons are appended');
  assert.equal(inserted.some(item => item.host === unknown), false, 'unknown slot names stay empty');
  assert.equal(button.disabled, true, 'disabled buttons stay disabled');
  assert.equal(button.attributes['aria-label'], '刷新任务', 'accessible names are untouched');
  assert.equal(slot.dataset.iconPainted, '1', 'painted slots are marked');
  // Re-running hydration after framework re-renders must not stack duplicate icons.
  assert.equal(api.refresh({ querySelectorAll: () => [slot, unknown, after, button] }), 0, 'repeat hydration is a no-op');
  assert.equal(inserted.length >= 3 && inserted.length <= 4, true, 'no duplicated icons were inserted');
});

test('hydration waits for the document when the script loads in the head', () => {
  const host = element({ dataset: { icon: 'menu' } });
  const { context, document, inserted } = contextFor(iconsSource(), { hosts: [host], readyState: 'loading' });
  assert.equal(inserted.length, 0, 'nothing is painted before the DOM exists');
  assert.equal(typeof document.listeners.DOMContentLoaded, 'function', 'DOMContentLoaded is awaited');
  document.listeners.DOMContentLoaded();
  assert.equal(inserted.length, 1, 'icons paint once the DOM is ready');
  assert.ok(context.JavspIcons.render('menu').startsWith('<svg'));
});

test('console and login load icons.js before the scripts that use it', () => {
  const html = page();
  const position = html.indexOf('/assets/icons.js');
  assert.ok(position > 0, 'index.html loads icons.js');
  for (const script of ['community.js', 'app.js', 'ai.js']) {
    const at = html.indexOf(`/assets/${script}`);
    assert.ok(at > 0, `index.html still loads ${script}`);
    assert.ok(position < at, `icons.js loads before ${script}`);
  }
  assert.match(html.slice(position - 40, position + 90), /icons\.js\?v=__ASSET_VERSION__/, 'icons.js is cache-busted like the other assets');
  assert.ok(login().includes('/assets/icons.js'), 'login.html can use the same icons');
  assert.match(login(), /icons\.js\?v=__ASSET_VERSION__/);
});

test('static pages only reference whitelisted icon names and keep labelled controls', () => {
  const whitelist = new Set(icons().names());
  const html = page();
  const used = [...html.matchAll(/data-icon="([^"]+)"/g)].map(match => match[1]);
  assert.ok(used.length >= 12, 'static controls were converted to icons');
  for (const name of used) assert.ok(whitelist.has(name), `data-icon="${name}" is whitelisted`);
  // Any control whose visible text disappears behind an icon needs a name of its own.
  for (const match of html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)) {
    const [, attributes, body] = match;
    const text = body.replace(/<svg\b[\s\S]*?<\/svg>/g, '').replace(/<[^>]+>/g, '').replace(/\s+/g, '');
    if (!text) assert.match(attributes, /aria-label="[^"]+"/, `icon-only button needs aria-label: ${match[0].slice(0, 120)}`);
  }
  // No button may remain labelled by a bare glyph.
  for (const glyph of ['×', '✕', '‹', '›', '☰', '■', '＋', '↑', '↓']) {
    assert.equal(html.includes(`>${glyph}</button>`), false, `index.html has no glyph-only "${glyph}" button`);
  }
});

test('dynamic markup builds icons through the shared whitelist instead of glyph text', () => {
  const app = appSource();
  const ai = aiSource();
  assert.match(app, /const javspIcon = \(name, options\) =>/, 'app.js has one icon helper');
  assert.match(app, /window\.JavspIcons\.render/, 'the helper delegates to the shared whitelist');
  for (const glyph of ['>×</button>', '>+</button>', "? '✎' : '×'"]) {
    assert.equal(app.includes(glyph), false, `app.js template no longer emits the glyph ${glyph}`);
  }
  const uses = [
    ...[...app.matchAll(/javspIcon\('([a-z-]+)'/g)].map(match => match[1]),
    ...[...app.matchAll(/data-icon="([a-z-]+)"/g)].map(match => match[1]),
    ...[...app.matchAll(/(?:dataset\.)?icon\s*=\s*[^;\n]*?'([a-z-]+)'/g)].map(match => match[1]),
    ...(/['"]chevron-up['"]/.test(app) ? ['chevron-up'] : []),
  ];
  for (const name of new Set(uses)) assert.ok(icons().names().includes(name), `app.js uses whitelisted icon ${name}`);
  assert.ok(uses.includes('trash') && uses.includes('close') && uses.includes('chevron-right'), 'delete/close/paging controls use icons');
  // Icon-only dynamic controls must carry their own accessible name.
  const iconOnly = [
    ...app.matchAll(/<button\b([^>]*)>\$\{javspIcon\('[a-z-]+'\)\}<\/button>/g),
    ...app.matchAll(/<button\b([^>]*)>' \+ javspIcon\('[a-z-]+'\) \+ '<\/button>/g),
  ];
  assert.ok(iconOnly.length >= 6, 'dynamic icon-only controls use the shared helper');
  for (const [, attributes] of iconOnly) {
    assert.match(attributes, /aria-label="[^"]+"/, `dynamic icon-only button needs aria-label: ${attributes.slice(0, 120)}`);
  }
  assert.equal(ai.includes("'✎' : '×'"), false, 'ai.js history buttons are not glyph labelled');
  assert.match(ai, /JavspIcons\.render\(rename \? 'pencil' : 'close'\)/, 'ai.js reuses the shared icons');
  assert.equal(ai.includes("$('#ai-send').textContent"), false, 'ai.js never overwrites the whole send button');
  assert.equal(ai.includes("$('#ai-stop').textContent"), false, 'ai.js never overwrites the whole stop button');
});

test('send and stop keep their icons while busy state changes the label and disabled flag', async () => {
  const source = aiSource();
  const start = source.indexOf('function updateBusy');
  const end = source.indexOf('function renderHistory', start);
  assert.ok(start > 0 && end > start, 'updateBusy is extractable');
  const sendIcon = element({ className: 'javsp-icon' });
  const sendLabel = element();
  const send = element();
  send.append(sendIcon, sendLabel);
  const stopIcon = element({ className: 'javsp-icon' });
  const stopLabel = element();
  const stop = element();
  stop.append(stopIcon, stopLabel);
  const workspace = element();
  const elements = new Map([['#ai-send', send], ['#ai-stop', stop], ['#ai-send-label', sendLabel], ['#ai-stop-label', stopLabel], ['#ai-workspace', workspace], ['#ai-new-chat', element()]]);
  const context = vm.createContext({
    sending: false, stopping: false, conversation: null,
    $: selector => elements.get(selector) || null,
    document: { querySelectorAll: () => [] },
    renderHistory() {},
  });
  vm.runInContext(source.slice(start, end), context);
  context.conversation = { status: 'running' };
  vm.runInContext('updateBusy()', context);
  assert.equal(send.hidden, true, '发送 hides while the answer streams');
  assert.equal(stop.hidden, false, '停止 becomes available');
  assert.equal(send.disabled, true, '发送 is disabled while busy');
  assert.equal(stop.label === undefined, true);
  assert.deepEqual(send.children, [sendIcon, sendLabel], '发送 icon survives the label update');
  assert.deepEqual(stop.children, [stopIcon, stopLabel], '停止 icon survives the label update');
  assert.equal(sendLabel.textContent, '发送', 'idle label stays short');
  assert.equal(stopLabel.textContent, '停止生成', 'stop label keeps its wording');
  context.sending = true;
  vm.runInContext('updateBusy()', context);
  assert.equal(sendLabel.textContent, '提交中…', 'submitting label is updated');
  context.sending = false;
  context.stopping = true;
  vm.runInContext('updateBusy()', context);
  assert.equal(stopLabel.textContent, '正在停止…', 'stopping label is updated');
  assert.deepEqual(stop.children, [stopIcon, stopLabel], '停止 icon still present while stopping');
  assert.equal(stop.disabled, true, '停止 is disabled while stopping');
});

test('expanding the download policy swaps the caret and keeps the button intact', () => {
  const source = appSource();
  const start = source.indexOf("const downloadPolicyToggle = $('#download-policy-toggle');");
  const end = source.indexOf('(async () => {', start);
  assert.ok(start > 0 && end > start, 'download policy toggle is extractable');
  const caret = element({ dataset: { icon: 'chevron-down', iconPainted: '1' }, matchesSelector: '[data-icon]' });
  const label = element({ matchesSelector: '[data-policy-label]' });
  label.textContent = '展开策略';
  const toggle = element();
  toggle.append(caret, label);
  const content = element({ classList: { hidden: true, toggle(name, force) { this.hidden = Boolean(force); }, contains(name) { return name === 'hidden' && this.hidden; } } });
  const saved = new Map();
  const context = vm.createContext({
    $: selector => selector === '#download-policy-toggle' ? toggle : selector === '#download-policy-content' ? content : null,
    localStorage: { getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value) },
    javspIcon: name => `<svg data-icon-name="${name}"></svg>`,
  });
  vm.runInContext(source.slice(start, end), context);
  assert.deepEqual(toggle.children, [caret, label], 'nothing rewrote the button on first paint');
  assert.equal(label.textContent, '展开策略', 'collapsed label');
  assert.equal(caret.dataset.icon, 'chevron-down', 'collapsed caret');
  toggle.listeners.click();
  assert.equal(content.classList.hidden, false, 'policy content is shown');
  assert.equal(label.textContent, '收起策略', 'expanded label');
  assert.equal(caret.dataset.icon, 'chevron-up', 'caret flips');
  assert.match(caret.innerHTML, /chevron-up/, 'caret is repainted from the whitelist');
  assert.deepEqual(toggle.children, [caret, label], 'expanding keeps both icon and label');
  assert.equal(toggle.attributes['aria-expanded'], 'true', 'expanded state is exposed');
  assert.equal(saved.get('javsp-web.download-policy-open'), '1', 'state is remembered');
});

test('CSS carries no symbol glyphs for functional controls and sizes shared icons', () => {
  const css = ['app.css', 'overrides.css', 'cinema.css', 'theme.css'].map(name => read(`javsp_web/web/assets/${name}`)).join('\n');
  assert.equal(css.includes('content: "\\2304"'), false, 'the details caret is no longer a glyph');
  assert.match(css, /\.javsp-icon\s*\{[^}]*width:/, 'shared icons declare a size');
  assert.match(css, /\.javsp-icon\s*\{[^}]*height:/, 'shared icons declare a height');
  assert.doesNotMatch(css, /content:\s*['"][×✕‹›☰■＋↑↓]/, 'no glyph pseudo-element icons remain');
});

test('every whitelisted icon is actually used by a page or script', () => {
  const api = icons();
  const sources = [page(), appSource(), aiSource(), communitySource()].join('\n');
  for (const name of api.names()) {
    const referenced = sources.includes(`data-icon="${name}"`) || sources.includes(`render('${name}'`) || sources.includes(`javspIcon('${name}'`) || sources.includes(`'${name}'`);
    assert.ok(referenced, `icon "${name}" is referenced; remove it from the whitelist if unused`);
  }
});

// The naming-rule help used to be a focusable <span> whose "?" caret came from a
// CSS pseudo-element: a functional control drawn as a glyph. It is now a real
// icon button that still owns its popover and the insert-variable actions.
function namingRuleHelpMarkup(targetPath, variables = [['num', '番号'], ['actress', '女优']]) {
  const app = appSource();
  const start = app.indexOf('function namingRuleHelp(');
  const end = app.indexOf('function translatorEngineControl(', start);
  assert.ok(start > 0 && end > start, 'namingRuleHelp is extractable');
  const { context } = contextFor(iconsSource());
  // app.js declares this helper; the slice only borrows the call site.
  vm.runInContext('var javspIcon = (name, options) => window.JavspIcons.render(name, options);', context);
  context.NAMING_RULE_VARIABLES = variables;
  context.escapeHtml = value => String(value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  vm.runInContext(app.slice(start, end), context);
  return { markup: vm.runInContext(`namingRuleHelp(${JSON.stringify(targetPath)})`, context), context };
}

test('the naming-rule help is an info icon button with a name, a popover and insert actions', () => {
  const target = 'summarizer.path.basename_pattern';
  const { markup } = namingRuleHelpMarkup(target);
  const trigger = markup.match(/<button\b([^>]*)>([\s\S]*?)<\/button>/);
  assert.ok(trigger, 'the help marker is a button element');
  const [, attributes, body] = trigger;

  // 1. the "?" glyph is gone: the marker is the whitelisted info SVG.
  assert.match(body, /<svg\b/, 'the button renders an SVG');
  assert.match(body, /class="javsp-icon/, 'the SVG comes from the shared icon set');
  assert.match(body, /aria-hidden="true"/, 'the SVG stays decorative');
  assert.equal(body.replace(/<svg\b[\s\S]*?<\/svg>/g, '').trim(), '', 'no text glyph is left in the button');
  assert.match(attributes, /class="naming-rule-help-trigger"/, 'the trigger keeps its own hook');
  assert.equal(/tabindex="0"/.test(markup), false, 'focus comes from the button, not a tabindex span');
  assert.match(attributes, /type="button"/, 'the trigger never submits the preset form');

  // 2. accessible name plus a short description for screen readers.
  assert.match(attributes, /aria-label="[^"]+"/, 'the icon-only button has an accessible name');
  assert.match(attributes, /title="[^"]+"/, 'the marker explains itself on hover');
  const described = attributes.match(/aria-describedby="([^"]+)"/);
  assert.ok(described, 'the trigger points at its usage hint');
  assert.ok(markup.includes(`id="${described[1]}"`), 'the description target exists in the same block');

  // 3. the popover survives, self-labelled for assistive technology.
  assert.match(markup, /<span class="naming-rule-popover" id="naming-rule-popover-summarizer-path-basename-pattern"/, 'the popover keeps a stable per-field id');
  assert.match(markup, /role="group" aria-label="[^"]+"/, 'the popover is a labelled group');
  assert.match(markup, /<strong>可用命名变量<\/strong>/, 'the visible heading is unchanged');
  assert.match(markup, /点击变量会插入到当前模板的光标位置/, 'the usage hint is unchanged');

  // 4. every variable is still an insert action aimed at this field.
  const inserts = [...markup.matchAll(/data-insert-naming-variable="([^"]+)" data-naming-target="([^"]+)"/g)];
  assert.deepEqual(inserts.map(match => match[1]), ['{num}', '{actress}'], 'each variable keeps its token');
  for (const [, , namingTarget] of inserts) assert.equal(namingTarget, target, 'variables target the field they belong to');
  assert.equal(markup.match(/class="naming-rule-variable"/g).length, 2, 'one button per variable');
});

test('naming-rule variable buttons still insert into the field at the caret', () => {
  const app = appSource();
  const start = app.indexOf("const variable = event.target.closest('[data-insert-naming-variable]');");
  const end = app.indexOf('const directoryPicker = event.target.closest', start);
  assert.ok(start > 0 && end > start, 'the insert branch is extractable');
  const input = {
    value: 'x{num}y', selectionStart: 6, selectionEnd: 7,
    focused: false, caret: null, event: null,
    focus() { input.focused = true; },
    setSelectionRange(from, to) { input.caret = [from, to]; },
    dispatchEvent(evt) { input.event = evt; return true; },
  };
  const variable = { dataset: { namingTarget: 'summarizer.path.basename_pattern', insertNamingVariable: '{actress}' } };
  const context = vm.createContext({
    event: { target: { closest: selector => selector === '[data-insert-naming-variable]' ? variable : null } },
    document: { querySelector: selector => selector === '[data-config-path="summarizer.path.basename_pattern"]' ? input : null },
    Event: class { constructor(type, options) { this.type = type; this.bubbles = Boolean(options && options.bubbles); } },
  });
  vm.runInContext(`(() => {${app.slice(start, end)}})()`, context);
  assert.equal(input.value, 'x{num}{actress}', 'the token replaces the selection at the caret');
  assert.deepEqual(input.caret, [15, 15], 'the caret sits after the inserted token');
  assert.equal(input.focused, true, 'the field keeps focus');
  assert.equal(input.event?.type, 'input', 'input listeners are notified so the form marks itself dirty');
});

test('naming-rule help CSS drops the "?" pseudo-element and keeps the popover on hover and focus', () => {
  const css = read('javsp_web/web/assets/app.css');
  assert.equal(css.includes('.naming-rule-help::before'), false, 'the pseudo-element marker is gone');
  assert.doesNotMatch(css, /content:\s*['"]\?['"]/, 'no "?" content glyph is left in the stylesheet');
  assert.match(css, /\.naming-rule-help\{[^}]*position:relative/, 'the wrapper stays a positioning context');
  assert.match(css, /\.naming-rule-help-trigger\{[^}]*border-radius:50%/, 'the button keeps the round help look');
  assert.match(css, /\.naming-rule-help-trigger \.javsp-icon\{[^}]*width:13px/, 'the info icon is sized inside the circle');
  assert.match(css, /\.naming-rule-help:hover \.naming-rule-popover/, 'hover still opens the popover');
  assert.match(css, /\.naming-rule-help:focus-within \.naming-rule-popover/, 'keyboard focus still opens the popover');
});
