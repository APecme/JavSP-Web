// Exercise the production AI settings and preset forms with a small DOM fixture.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const app = fs.readFileSync(path.join(__dirname, '../javsp_web/web/assets/app.js'), 'utf8');
const ai = fs.readFileSync(path.join(__dirname, '../javsp_web/web/assets/ai.js'), 'utf8');

function section(source, from, to) {
  const start = source.indexOf(from);
  assert.ok(start >= 0, `Missing source boundary: ${from}`);
  const end = source.indexOf(to, start);
  assert.ok(end > start, `Missing source boundary: ${to}`);
  return source.slice(start, end);
}

function attributes(markup) {
  return Object.fromEntries([...markup.matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map(([, key, value]) => [key, value ?? true]));
}

function decodeHtml(value) {
  return String(value).replaceAll('&quot;', '"').replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&amp;', '&');
}

function formControls(markup) {
  return [...markup.matchAll(/<input\b([^>]*)>|<select\b([^>]*)>([\s\S]*?)<\/select>|<textarea\b([^>]*)>([\s\S]*?)<\/textarea>/g)].flatMap(([, input, select, options, textarea, text]) => {
    const attrs = attributes(input ?? select ?? textarea);
    if (!String(attrs.class || '').split(' ').includes('config-field-input')) return [];
    const choices = options ? [...options.matchAll(/<option\b([^>]*)>/g)].map(([, attrs]) => attributes(attrs)) : [];
    return [{
      dataset: attrs['data-config-path'] ? { configPath: attrs['data-config-path'] } : {},
      type: attrs.type || (textarea !== undefined ? 'textarea' : select !== undefined ? 'select-one' : 'text'),
      checked: attrs.checked === true,
      disabled: attrs.disabled === true,
      value: decodeHtml(choices.length ? (choices.find(choice => choice.selected) || choices[0]).value : text ?? attrs.value ?? ''),
    }];
  });
}

function verifyPresets() {
  const containers = new Map();
  const elements = selector => {
    if (!containers.has(selector)) containers.set(selector, {
      innerHTML: '',
      insertAdjacentHTML(_, markup) { this.innerHTML += markup; },
    });
    return containers.get(selector);
  };
  let controls = [];
  let engineChange;
  const state = { aiEnabled: true, formValues: {} };
  const context = vm.createContext({
    state, $: elements,
    escapeHtml: value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;'),
    hydrateCollectionControls() {}, isNamingRulePath: () => false,
    document: {
      querySelectorAll: selector => selector === '.config-field-input' ? controls : [], querySelector: () => null,
      addEventListener: (_, listener) => { engineChange = listener; },
    },
  });
  vm.runInContext([
    section(app, 'const FORM_SECTIONS', 'function cloneValue'),
    section(app, 'function cloneValue', 'function normalizeMediaTypes'),
    section(app, 'function translatorEngineControl', 'function renderPresetNavigation'),
    section(app, 'function renderConfigFields', '\nrenderPresetNavigation();'),
    section(app, 'function readConfigFields', 'function proxyConnectivityResultMarkup'),
    section(app, 'function presetPayload', 'async function savePreset'),
  ].join('\n'), context);
  const changeStart = app.lastIndexOf("document.addEventListener('change',", app.indexOf("const select = event.target.closest('[data-translator-engine]')"));
  vm.runInContext(app.slice(changeStart, app.indexOf("$('#task-delete-form')", changeStart)), context);

  const engine = { name: 'openai', url: 'https://translate.example/v1/chat/completions', api_key: 'saved-secret', model: 'translation-model' };
  state.formValues = { translator: { engine: { ...engine }, fields: { title: true, plot: false }, ai_enabled: false } };
  const syncControls = () => { controls = formControls([...containers.values()].map(element => element.innerHTML).join('')); };
  const render = () => {
    context.renderConfigFields();
    const markup = elements('#preset-fields-translator').innerHTML;
    syncControls();
    return markup;
  };
  const read = () => JSON.parse(JSON.stringify(context.readConfigFields())).translator;
  let markup = render();
  assert.equal(controls.filter(control => control.dataset.configPath === 'translator.ai_enabled').length, 1);
  assert.ok(markup.indexOf('translator.ai_enabled') > markup.indexOf('translator.fields.plot'), 'AI switch follows translation fields');
  const toggle = () => controls.find(control => control.dataset.configPath === 'translator.ai_enabled');
  const switchAi = checked => {
    toggle().checked = checked;
    engineChange({ target: { closest: selector => selector === '[data-config-path="translator.ai_enabled"]' ? toggle() : null } });
    syncControls();
  };
  assert.equal(toggle().disabled, false, 'the shared AI scraping switch makes preset translation available');
  assert.equal(toggle().checked, false, 'existing presets remain off');
  switchAi(true);
  assert.ok(controls.filter(control => control.dataset.configPath?.startsWith('translator.engine.')).every(control => control.disabled), 'AI disables engine credentials');
  assert.match(elements('#preset-fields-translator').innerHTML, /data-translator-engine disabled/);
  controls.find(control => control.dataset.configPath === 'translator.engine.api_key').value = 'must-not-be-saved';
  let saved = read();
  assert.equal(saved.ai_enabled, true);
  assert.deepEqual(saved.engine, engine, 'enabling AI preserves the traditional engine and credentials');
  state.formValues.translator = saved;
  state.aiEnabled = false;
  markup = render();
  assert.equal(toggle().disabled, false, 'a saved AI choice can be cancelled while system AI is unavailable');
  assert.equal(toggle().checked, true, 'saved choice remains visible while globally unavailable');
  assert.match(markup, /AI 刮削已关闭/);
  assert.match(markup, /data-translator-engine disabled/);
  switchAi(false);
  saved = read();
  assert.equal(saved.ai_enabled, false);
  assert.deepEqual(saved.engine, engine, 'explicitly cancelling AI restores the saved engine configuration');
  assert.equal(toggle().disabled, true, 'system AI must be enabled before selecting it again');
  assert.doesNotMatch(elements('#preset-fields-translator').innerHTML, /data-translator-engine disabled/);
  state.aiEnabled = true;

  state.formValues = { translator: { engine: null, fields: { title: false, plot: false } } };
  render();
  assert.equal(toggle().checked, false, 'legacy presets without an AI field default off');
  toggle().checked = true;
  saved = read();
  assert.equal(saved.ai_enabled, true);
  assert.equal(saved.engine, null, 'AI does not replace an explicit null engine');
  assert.equal(saved.fields.title, false);
  assert.equal(saved.fields.plot, false);

  const mediaTypes = [{ id: 'normal', name: '普通影片', priority: 0, detector: 'fallback', identifier_kind: 'dvdid', fallback: true }];
  state.formValues = {
    scanner: { media_types: mediaTypes, minimum_size: '00123', skip_nfo_dir: false, filename_extensions: ['.mp4', '.strm'] },
    network: { retry: 3, proxy_server: null },
    translator: { engine: null, fields: { title: true, plot: false }, ai_enabled: false },
  };
  elements('#preset-mode').value = 'form';
  elements('#preset-name').value = '翻译预设';
  render();
  const control = path => controls.find(item => item.dataset.configPath === path);
  control('network.retry').value = '4';
  const switchEngine = value => {
    engineChange({ target: { closest: selector => selector === '[data-translator-engine]' ? { value } : null } });
    syncControls();
  };
  switchEngine('google');
  assert.equal(control('translator.fields.title').type, 'select-one', 'engine changes retain boolean selects');
  assert.equal(control('translator.fields.plot').type, 'select-one');
  assert.equal(control('translator.fields.plot').value, 'false');
  assert.equal(control('scanner.skip_nfo_dir').value, 'false');
  assert.equal(control('scanner.media_types').type, 'textarea');
  assert.deepEqual(JSON.parse(control('scanner.media_types').value), mediaTypes, 'media types remain JSON arrays, not quoted JSON strings');
  toggle().checked = true;
  const payload = JSON.parse(JSON.stringify(context.presetPayload()));
  assert.deepEqual(payload.form.translator, { engine: { name: 'google' }, fields: { title: true, plot: false }, ai_enabled: true });
  assert.deepEqual(payload.form.scanner.media_types, mediaTypes);
  assert.deepEqual(payload.form.scanner.filename_extensions, ['.mp4', '.strm']);
  assert.equal(payload.form.scanner.skip_nfo_dir, false);
  assert.equal(payload.form.network.retry, 4);
  assert.equal(payload.form.network.proxy_server, null);
  assert.equal(payload.form.scanner.minimum_size, '00123', 'numeric-looking strings keep their original meaning');

  // YAML edits still reach the server unchanged after multiple local re-renders.
  switchAi(false);
  const yamlMediaTypes = '- id: normal\n  name: 默认分类\n  priority: 0\n  detector: fallback\n  identifier_kind: dvdid\n  fallback: true\n';
  control('scanner.media_types').value = yamlMediaTypes;
  switchEngine('openai');
  assert.equal(control('scanner.media_types').type, 'textarea');
  assert.equal(control('scanner.media_types').value, yamlMediaTypes);
  control('translator.engine.api_key').value = 'false';
  control('translator.engine.model').value = '00123';
  control('translator.engine.url').value = 'https://llm.example/v1/chat/completions';
  state.formValues = context.readConfigFields();
  render();
  const yamlPayload = JSON.parse(JSON.stringify(context.presetPayload()));
  assert.equal(yamlPayload.form.scanner.media_types, yamlMediaTypes);
  assert.equal(yamlPayload.form.translator.engine.api_key, 'false', 'string credentials are not coerced');
  assert.equal(yamlPayload.form.translator.engine.model, '00123');
  assert.equal(yamlPayload.form.translator.fields.plot, false);
}

async function verifySettings() {
  const elements = new Map();
  const element = selector => {
    if (!elements.has(selector)) elements.set(selector, { value: '', checked: false, textContent: '', reportValidity: () => true, querySelectorAll: () => [] });
    return elements.get(selector);
  };
  const requests = [];
  const settings = { enabled: true, provider: 'compatible', base_url: 'https://model.example/v1', model: 'text-model', timeout: 60, search_enabled: false, has_api_key: true };
  const state = {};
  const context = vm.createContext({
    $: element, state, defaultSystemPrompt: '',
    api: async (url, options) => {
      const payload = JSON.parse(options.body);
      requests.push({ url, payload, status: element('#ai-settings-message').textContent });
      return url === '/api/ai/settings' ? { ...settings, ...payload, has_api_key: true } : { message: '连接成功' };
    },
  });
  vm.runInContext(section(ai, '  const advancedNumbers', '  const storageKey') + section(ai, '  function fillSettings', '  window.JavspAI'), context);
  context.fillSettings(settings);
  assert.equal(element('#ai-enabled').checked, true);
  assert.equal(state.aiEnabled, true);
  assert.equal(elements.has('#ai-translation-enabled'), false, 'there is no second global AI switch');
  await context.submitSettings(false);
  assert.equal('translation_enabled' in requests.at(-1).payload, false);
  assert.equal(requests.at(-1).payload.enabled, true);
  assert.equal(requests.at(-1).payload.search_enabled, false, 'AI translation does not enable online search');
  assert.equal(requests.at(-1).payload.api_key, null, 'blank key retains the existing shared credential');
  assert.equal(requests.at(-1).payload.clear_api_key, false);
  await context.submitSettings(true);
  assert.equal(requests.at(-1).status, '正在测试连接…');
  element('#ai-enabled').checked = false;
  await context.submitSettings(false);
  assert.equal('translation_enabled' in requests.at(-1).payload, false);
  assert.equal(requests.at(-1).payload.enabled, false);
  assert.equal(state.aiEnabled, false);
  context.fillSettings({ ...settings, enabled: false, translation_enabled: true });
  assert.equal(state.aiEnabled, false, 'the obsolete translation switch cannot enable AI');
  assert.equal(elements.has('#ai-translation-enabled'), false);
  assert.equal('aiTranslationEnabled' in state, false);
  assert.doesNotMatch(ai, /id="ai-translation-enabled"/);
}

async function verifyRuntimeAvailability() {
  const state = {};
  let runtime = { ai_enabled: false, ai_translation_enabled: true };
  const context = vm.createContext({
    state, $: () => null, editPreset() {},
    api: async url => url === '/api/runtime' ? runtime : [],
  });
  vm.runInContext(section(app, 'async function loadPresets', 'function presetPayload'), context);
  await context.loadPresets();
  assert.equal(state.aiEnabled, false);
  assert.equal('aiTranslationEnabled' in state, false, 'the obsolete runtime field is ignored');
  runtime = { ai_enabled: true };
  await context.loadPresets();
  assert.equal(state.aiEnabled, true);
  assert.equal('aiTranslationEnabled' in state, false);
}

async function main() {
  verifyPresets();
  await verifySettings();
  await verifyRuntimeAvailability();
  console.log('AI translation client checks passed: exclusive translation mode, disabled engine fields, explicit recovery, preset round trip and shared AI settings.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
