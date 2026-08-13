const state = { user: null, tasks: [], presets: [], downloaders: [], mediaServers: [], pathMappings: [], autoScrapeRules: [], autoScrapeSchedules: [], runtime: null, activeAutoScrapeRun: null, activeAutoScrapeHistory: null, activeTaskDetail: null, activeDownloaderId: null, activeDownloads: [], activeDownloader: null, downloadSort: { key: 'added_on', direction: 'desc' }, editingPreset: null, editingUser: null, pendingDeleteTask: null, pendingConfirm: null, selectedOverviewTasks: new Set(), pathBrowser: { kind: 'directory', target: 'manual', currentPath: '/' }, formValues: {}, presetMode: null, logScroll: {}, logOpen: {}, taskOpen: {}, taskStatus: {} };
const $ = (selector) => document.querySelector(selector);
const FORM_SECTIONS = ['scanner', 'network', 'crawler', 'summarizer', 'translator', 'other'];
const CRAWLER_GROUPS = { normal: '普通影片', fc2: 'FC2', cid: 'CID', getchu: 'Getchu', gyutto: 'Gyutto' };
const CRAWLER_IDS = ['airav','avsox','avwiki','dl_getchu','fanza','fc2','fc2fan','fc2ppvdb','gyutto','jav321','javbus','javdb','javlib','javmenu','mgstage','njav','prestige','arzon','arzon_iv'];
const FORM_TABS = [
  { id: 'scanner', section: 'scanner', label: '扫描器', description: '负责识别影片文件、过滤目录和设置扫描规则。' },
  { id: 'network', section: 'network', label: '网络', description: '设置代理、重试次数和网络请求超时。' },
  { id: 'crawler', section: 'crawler', label: '爬虫', description: '选择此预设实际使用的数据来源和爬虫顺序。' },
  { id: 'folder', section: 'summarizer', prefixes: ['move_files', 'path', 'title'], label: '文件夹整理', description: '设置输出目录、文件名、路径长度和文件移动规则。' },
  { id: 'defaults', section: 'summarizer', prefixes: ['default'], label: '替代文本', description: '设置影片信息字段缺失时使用的替代文本。' },
  { id: 'images', section: 'summarizer', prefixes: ['cover', 'fanart', 'extra_fanarts'], label: '图片', description: '设置封面、横版封面、裁剪和剧照下载规则。' },
  { id: 'custom', section: 'summarizer', prefixes: ['nfo', 'censor_options_representation'], label: '自定义', description: '设置 NFO 文件名、标题模板、分类、标签和码状态文本。' },
  { id: 'translator', section: 'translator', label: '翻译器', description: '设置翻译引擎和需要翻译的字段。' },
  { id: 'other', section: 'other', label: '其他', description: '设置交互、更新检查等通用行为。' },
];
const NAMING_RULE_VARIABLES = [
  ['num', '番号'], ['title', '标题'], ['rawtitle', '原始标题'], ['actress', '女优'], ['score', '评分'],
  ['censor', '码状态'], ['serial', '系列'], ['director', '导演'], ['producer', '制作商'], ['publisher', '发行商'],
  ['date', '发行日期'], ['year', '发行年份'], ['label', '番号前缀'], ['genre', '类型'],
];
const TRANSLATOR_ENGINES = {
  google: [], bing: ['api_key'], baidu: ['app_id', 'api_key'], claude: ['api_key'], openai: ['url', 'api_key', 'model'],
};
const FIELD_LABELS = {
  'scanner.ignored_id_pattern': '番号识别忽略规则', 'scanner.input_directory': '扫描目录', 'scanner.filename_extensions': '影片文件扩展名', 'scanner.ignored_folder_name_pattern': '忽略目录规则', 'scanner.minimum_size': '最小匹配文件大小', 'scanner.skip_nfo_dir': '跳过已有 NFO 的目录', 'scanner.manual': '手动确认扫描结果',
  'network.proxy_server': '代理服务器地址', 'network.proxy_free': '免代理站点地址', 'network.proxy_free.avsox': 'Avsox 免代理地址', 'network.proxy_free.javbus': 'JavBus 免代理地址', 'network.proxy_free.javdb': 'JavDB 免代理地址', 'network.proxy_free.javlib': 'JavLib 免代理地址', 'network.retry': '网络重试次数', 'network.timeout': '网络请求超时',
  'crawler.selection.normal': '普通影片爬虫列表', 'crawler.selection.fc2': 'FC2 影片爬虫列表', 'crawler.selection.cid': 'CID 影片爬虫列表', 'crawler.selection.getchu': 'Getchu 影片爬虫列表', 'crawler.selection.gyutto': 'Gyutto 影片爬虫列表', 'crawler.required_keys': '抓取成功必需字段', 'crawler.hardworking': '深度抓取', 'crawler.respect_site_avid': '使用网站返回的番号', 'crawler.fc2fan_local_path': 'FC2Fan 本地镜像目录', 'crawler.sleep_after_scraping': '每部影片刮削后等待时间', 'crawler.use_javdb_cover': 'JavDB 封面使用策略', 'crawler.normalize_actress_name': '统一女优艺名',
  'summarizer.move_files': '移动文件到整理目录', 'summarizer.path.output_folder_pattern': '整理输出目录模板', 'summarizer.path.basename_pattern': '影片相关文件名模板', 'summarizer.path.length_maximum': '最大文件路径长度', 'summarizer.path.length_by_byte': '按字节计算路径长度', 'summarizer.path.max_actress_count': '路径中最多包含的女优数', 'summarizer.path.hard_link': '使用硬链接整理文件', 'summarizer.title.remove_trailing_actor_name': '移除标题末尾女优名', 'summarizer.default.title': '未知标题替代文本', 'summarizer.default.actress': '未知女优替代文本', 'summarizer.default.series': '未知系列替代文本', 'summarizer.default.director': '未知导演替代文本', 'summarizer.default.producer': '未知制作商替代文本', 'summarizer.default.publisher': '未知发行商替代文本', 'summarizer.nfo.basename_pattern': 'NFO 文件名', 'summarizer.nfo.title_pattern': 'NFO 影片标题模板', 'summarizer.nfo.custom_genres_fields': '自定义分类字段', 'summarizer.nfo.custom_tags_fields': '自定义标签字段', 'summarizer.censor_options_representation': '码状态显示文本', 'summarizer.cover.basename_pattern': '封面文件名', 'summarizer.cover.highres': '优先下载高清封面', 'summarizer.cover.add_label': '在封面添加水印标签', 'summarizer.cover.crop.on_id_pattern': '启用封面裁剪的番号规则', 'summarizer.cover.crop.engine': '封面裁剪识别引擎', 'summarizer.fanart.basename_pattern': '横版封面文件名', 'summarizer.extra_fanarts.enabled': '下载剧照', 'summarizer.extra_fanarts.scrap_interval': '剧照请求间隔',
  'translator.engine': '翻译引擎配置', 'translator.fields.title': '翻译标题', 'translator.fields.plot': '翻译剧情简介', 'translator.engine.name': '翻译引擎名称', 'translator.engine.app_id': '翻译服务应用 ID', 'translator.engine.api_key': '翻译服务 API 密钥', 'translator.engine.url': 'OpenAI 兼容接口地址', 'translator.engine.model': '翻译模型名称',
  'other.interactive': '终端交互模式', 'other.check_update': '检查 JavSP 更新', 'other.auto_update': '自动下载新版本',
  ignored_id_pattern: '忽略番号规则', input_directory: '输入目录', filename_extensions: '文件扩展名', ignored_folder_name_pattern: '忽略目录规则', minimum_size: '最小文件大小', skip_nfo_dir: '跳过 NFO 目录', manual: '手动确认',
  proxy_server: '代理服务器', proxy_free: '免代理站点', retry: '重试次数', timeout: '请求超时',
  selection: '爬虫选择', required_keys: '必需字段', hardworking: '深度抓取', respect_site_avid: '尊重站点番号', fc2fan_local_path: 'FC2 本地页面目录', sleep_after_scraping: '刮削后等待', use_javdb_cover: '使用 JavDB 封面', normalize_actress_name: '统一演员名称',
  move_files: '移动文件', path: '路径规则', output_folder_pattern: '输出目录模板', basename_pattern: '文件名模板', length_maximum: '路径最大长度', length_by_byte: '按字节计算长度', max_actress_count: '最多演员数量', hard_link: '使用硬链接',
  remove_trailing_actor_name: '移除标题末尾演员名', default: '缺省值', nfo: 'NFO 文件', title_pattern: '标题模板', custom_genres_fields: '自定义类型字段', custom_tags_fields: '自定义标签字段', censor_options_representation: '码状态显示文本', cover: '封面', highres: '高清封面', add_label: '添加封面标签', crop: '封面裁剪', on_id_pattern: '裁剪番号规则', fanart: '横版封面', extra_fanarts: '剧照', scrap_interval: '剧照请求间隔',
  engine: '翻译引擎', fields: '翻译字段', title: '标题', plot: '剧情简介',
  interactive: '交互模式', check_update: '检查更新', auto_update: '自动更新',
};
FIELD_LABELS['summarizer.cover.google_search_fallback'] = 'Google 搜索封面兜底';

const FIELD_NOTES = {
  input_directory: '手动刮削时会由任务路径覆盖。',
  ignored_id_pattern: '每行一个正则表达式。',
  filename_extensions: '数组可直接输入 YAML，例如 [.mkv, .mp4]。',
  ignored_folder_name_pattern: '每行一个目录过滤正则。',
  proxy_server: '留空或输入 null 表示不使用代理。',
  proxy_free: '站点地址对象，可按 YAML 格式填写。',
  selection: '按影片类型选择爬虫列表，可直接输入 YAML 对象。',
  required_keys: '数组可直接输入 YAML，例如 [cover, title]。',
  engine: '引擎配置可输入 null 或 YAML 对象。',
  path: '路径相关配置对象，可按 YAML 格式填写。',
  nfo: 'NFO 文件生成配置对象。',
  cover: '封面和裁剪配置对象。',
  crop: '封面裁剪配置对象。',
  extra_fanarts: '剧照下载配置对象。',
  fields: '需要翻译的字段开关。',
};
const FIELD_DESCRIPTIONS = {
  'summarizer.cover.google_search_fallback': '启用后，封面下载失败时使用 Google 图片搜索；如果 Google 只返回浏览器脚本页面，则自动尝试 Bing 图片结果。服务器需要能够通过预设中的代理访问搜索引擎。',
  'scanner.ignored_id_pattern': '推测番号前会忽略文件名中匹配的字符串；除非熟悉正则表达式，否则不要修改。',
  'scanner.input_directory': '要整理的影片目录。手动刮削任务会临时覆盖此值。',
  'scanner.filename_extensions': '这些扩展名的文件会被当作影片扫描。',
  'scanner.ignored_folder_name_pattern': '扫描影片文件时会忽略名称匹配规则的目录。',
  'scanner.minimum_size': '匹配番号时会忽略小于此大小的文件，格式遵循 Pydantic ByteSize。',
  'network.proxy_server': '支持 http、socks5 和 socks5h；填 null 表示禁用代理。',
  'network.proxy_free': '各站点的免代理地址；地址失效时 JavSP 会自动尝试获取新地址。',
  'network.retry': '网络问题导致抓取失败时的重试次数。',
  'network.timeout': '网络请求超时时间，使用 ISO 8601 时长，例如 PT10S。',
  'crawler.selection': '汇总数据时会按列表从前到后的顺序使用爬虫。',
  'crawler.required_keys': '爬虫至少取得这些字段时，影片才视为抓取成功。',
  'crawler.hardworking': '会尝试抓取更准确、丰富的信息，但会略微增加部分站点耗时。',
  'crawler.respect_site_avid': '启用后会使用网页上的番号，并修正番号大小写等格式。',
  'crawler.fc2fan_local_path': 'FC2Fan 已关站；如有镜像，目录内应包含类似 FC2-12345.html 的文件。',
  'crawler.sleep_after_scraping': '每刮削一部影片后的等待时长；设为 PT0S 可禁用。',
  'crawler.use_javdb_cover': '可选 fallback、yes、no；fallback 会优先使用其他站点封面以避免水印。',
  'crawler.normalize_actress_name': '启用后会尝试把同一女优的多个艺名统一为一个名称。',
  'summarizer.move_files': '启用后会移动相关文件到新目录；关闭时会在原文件同级位置保存刮削数据。',
  'summarizer.path.output_folder_pattern': '影片、封面等文件的输出目录，可使用 JavSP 命名规则变量。',
  'summarizer.path.basename_pattern': '影片、封面、NFO 等相关文件的基础名称模板。',
  'summarizer.path.length_maximum': '生成路径过长时，JavSP 会据此自动截短标题。',
  'summarizer.path.length_by_byte': '决定路径长度按字符数还是字节数计算。',
  'summarizer.path.max_actress_count': '路径变量 {actress} 中最多保留的女优人数。',
  'summarizer.path.hard_link': '硬链接可节省空间，但并非所有文件系统支持。',
  'summarizer.nfo.basename_pattern': '生成的 NFO 文件名。',
  'summarizer.nfo.title_pattern': '媒体管理工具中显示的影片标题模板。',
  'summarizer.nfo.custom_genres_fields': '要写入自定义分类的字段；空列表表示不添加。',
  'summarizer.nfo.custom_tags_fields': '要写入自定义标签的字段；空列表表示不添加。',
  'summarizer.censor_options_representation': '依次设置已知无码、已知有码和未知码状态时 {censor} 的文本。',
  'summarizer.cover.basename_pattern': '封面文件名，不包含扩展名，可使用标题等变量。',
  'summarizer.cover.highres': '高清封面约为 8 至 10 MiB，网络较慢时会降低整理速度。',
  'summarizer.cover.add_label': '在封面图上添加水印标签，例如字幕。',
  'summarizer.cover.crop.on_id_pattern': '只有番号匹配这些规则时才使用图像识别裁剪封面。',
  'summarizer.cover.crop.engine': '图像识别引擎配置；填 null 表示禁用图像裁剪。',
  'summarizer.fanart.basename_pattern': '横版封面文件名，不包含扩展名，可使用标题等变量。',
  'summarizer.extra_fanarts.enabled': '是否下载剧照。',
  'summarizer.extra_fanarts.scrap_interval': '两次剧照抓取请求之间的等待时长。',
  'translator.engine': '可选 google、bing、baidu、claude、openai；填 null 表示禁用翻译。',
  'other.interactive': '是否通过 stdin/stdout 进行交互。',
  'other.check_update': '允许时会显示新版本提示和新版功能。',
  'other.auto_update': '允许检查到新版本后自动下载。',
  manual: '是否使用交互式方式确认扫描结果。',
  minimum_size: '小于此大小的文件不会参与匹配。',
  skip_nfo_dir: '扫描时跳过已经整理好的 NFO 目录。',
  retry: '网络请求失败时的重试次数。',
  timeout: '网络请求超时时间，使用 ISO 8601 时长。',
  hardworking: '启用更完整的抓取流程，可能增加耗时。',
  respect_site_avid: '优先使用网站返回的番号。',
  sleep_after_scraping: '每部影片完成后等待的时间。',
  move_files: '是否把相关文件移动到整理后的目录。',
  output_folder_pattern: '整理后的目录命名模板。',
  basename_pattern: '影片、封面等文件名模板。',
  length_maximum: '生成路径允许的最大长度。',
  highres: '是否尽量下载高清封面。',
  add_label: '是否在封面上添加标签。',
  enabled: '是否启用此项功能。',
  interactive: '是否在终端中启用交互。',
  check_update: '是否检查 JavSP 更新。',
  auto_update: '是否自动下载新版本。',
  'translator.fields.title': '是否翻译标题字段。',
  'translator.fields.plot': '是否翻译剧情简介字段。',
};

function cloneValue(value) {
  return value && typeof value === 'object' ? JSON.parse(JSON.stringify(value)) : value;
}

function pathValue(root, path) {
  return path.split('.').reduce((value, key) => (value == null ? undefined : value[key]), root);
}

function setPathValue(root, path, value) {
  const parts = path.split('.');
  let target = root;
  parts.slice(0, -1).forEach((part) => {
    if (!target[part] || typeof target[part] !== 'object' || Array.isArray(target[part])) target[part] = {};
    target = target[part];
  });
  target[parts[parts.length - 1]] = value;
}

function fieldDescription(path, value) {
  const key = path.split('.').pop();
  const parts = path.split('.');
  while (parts.length) {
    const description = FIELD_DESCRIPTIONS[parts.join('.')];
    if (description) return description;
    parts.pop();
  }
  return FIELD_DESCRIPTIONS[key] || '';
}

function fieldNote(path, value) {
  const key = path.split('.').pop();
  return FIELD_NOTES[key] || '';
}

function fieldLabel(path) {
  const key = path.split('.').pop();
  return FIELD_LABELS[path] || FIELD_LABELS[key] || key;
}

function displayFieldValue(value) {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function isNamingRulePath(path) {
  return [
    'summarizer.path.output_folder_pattern', 'summarizer.path.basename_pattern',
    'summarizer.nfo.basename_pattern', 'summarizer.nfo.title_pattern',
    'summarizer.cover.basename_pattern', 'summarizer.fanart.basename_pattern',
  ].includes(path);
}

function namingRuleHelp(targetPath) {
  const variables = NAMING_RULE_VARIABLES.map(([name, label]) => `<button type="button" class="naming-rule-variable" data-insert-naming-variable="{${name}}" data-naming-target="${escapeHtml(targetPath)}"><code>{${name}}</code><span>${escapeHtml(label)}</span></button>`).join('');
  return `<span class="naming-rule-help" tabindex="0"><span class="naming-rule-popover"><strong>可用命名变量</strong><span class="naming-rule-variable-list">${variables}</span><small>点击变量会插入到当前模板的光标位置。</small></span></span>`;
}

function translatorEngineControl(value) {
  const engine = value && typeof value === 'object' ? value : {};
  const name = engine.name || '';
  const options = [['', '不启用翻译'], ['google', 'Google 翻译'], ['bing', '必应翻译'], ['baidu', '百度翻译'], ['claude', 'Claude'], ['openai', 'OpenAI 兼容接口']]
    .map(([key, label]) => `<option value="${key}"${name === key ? ' selected' : ''}>${label}</option>`).join('');
  const labels = { app_id: '应用 ID', api_key: 'API 密钥', url: '接口地址', model: '模型名称' };
  const placeholders = { url: 'https://api.openai.com/v1/chat/completions', model: 'gpt-4o-mini' };
  const fields = (TRANSLATOR_ENGINES[name] || []).map((key) => `<label class="translator-engine-field">${labels[key]}<input class="config-field-input" data-config-path="translator.engine.${key}" value="${escapeHtml(engine[key] || '')}"${placeholders[key] ? ` placeholder="${placeholders[key]}"` : ''}${key === 'api_key' ? ' type="password" autocomplete="off"' : ''}></label>`).join('');
  return `<div class="translator-engine-control"><select class="config-field-input" data-translator-engine>${options}</select>${fields ? `<div class="translator-engine-fields">${fields}</div>` : ''}</div>`;
}

function pathMatchesTab(path, prefixes) {
  if (!prefixes || !path) return true;
  return prefixes.some((prefix) => prefix === path || prefix.startsWith(`${path}.`) || path.startsWith(`${prefix}.`));
}

function renderPresetNavigation() {
  const tabs = $('.preset-tabs');
  const panels = $('.preset-tab-panels');
  if (!tabs || !panels) return;
  const intro = $('.preset-editor-heading .muted');
  if (intro) intro.textContent = '窗口表单按 config.yml 的配置分类组织；每项都有说明和备注。也可以直接使用完整 config.yml。';
  tabs.innerHTML = FORM_TABS.map((tab, index) => `<button class="preset-tab${index === 0 ? ' active' : ''}" type="button" data-preset-tab="${tab.id}">${tab.label}</button>`).join('');
  panels.innerHTML = FORM_TABS.map((tab, index) => `<section class="preset-tab-panel${index === 0 ? ' active' : ''}" data-preset-panel="${tab.id}"><div class="tab-intro"><strong>${tab.label}</strong><span>对应 config.yml 的 ${tab.section}${tab.prefixes ? `.${tab.prefixes.join('、')}` : ''}，${tab.description}</span></div><div id="preset-fields-${tab.id}" class="config-fields"></div></section>`).join('');
}

function renderConfigFields() {
  FORM_TABS.forEach((tab) => {
    const container = $(`#preset-fields-${tab.id}`);
    if (!container) return;
    const values = state.formValues?.[tab.section] || {};
    if (tab.id === 'crawler') {
      const selection = values.selection || {};
      container.innerHTML = `<div class="crawler-config-editor"><p class="muted">此处设置当前刮削预设使用哪些爬虫以及执行顺序。</p>${crawlerConfigMarkup(selection)}</div>`;
      return;
    }
    const paths = [];
    const walk = (value, path) => {
      if (!pathMatchesTab(path, tab.prefixes)) return;
      if (tab.section === 'scanner' && path === 'input_directory') return;
      if (tab.section === 'translator' && path === 'engine') {
        paths.push([path, value]);
      } else if (value && typeof value === 'object' && !Array.isArray(value)) {
        Object.entries(value).forEach(([key, item]) => walk(item, path ? `${path}.${key}` : key));
      } else if (path) paths.push([path, value]);
    };
    walk(values, '');
    container.innerHTML = paths.map(([path, value]) => {
      const complex = Array.isArray(value) || (value && typeof value === 'object');
      const boolean = typeof value === 'boolean';
      const sourcePath = `${tab.section}.${path}`;
      const placeholder = sourcePath === 'network.proxy_server' ? 'http://127.0.0.1:7890 或 socks5://127.0.0.1:7890' : '';
      const inputValue = value === null || value === undefined ? '' : displayFieldValue(value);
      const control = sourcePath === 'translator.engine' ? translatorEngineControl(value) : (boolean ? `<select class="config-field-input" data-config-path="${sourcePath}"><option value="true"${value ? ' selected' : ''}>是</option><option value="false"${value ? '' : ' selected'}>否</option></select>` : (complex ? `<textarea class="config-field-input" data-config-path="${sourcePath}" spellcheck="false">${escapeHtml(inputValue)}</textarea>` : `<input class="config-field-input" data-config-path="${sourcePath}" value="${escapeHtml(inputValue)}"${placeholder ? ` placeholder="${escapeHtml(placeholder)}"` : ''}>`));
      const description = fieldDescription(sourcePath, value);
      const note = fieldNote(sourcePath, value);
      const outputDirectoryPicker = sourcePath === 'summarizer.path.output_folder_pattern'
        ? `<button class="button secondary config-directory-picker" type="button" data-select-output-directory="${sourcePath}">选择路径</button>`
        : '';
      const ruleControl = isNamingRulePath(sourcePath) ? `<div class="naming-rule-control">${control}${outputDirectoryPicker}${namingRuleHelp(sourcePath)}</div>` : control;
      return `<label class="config-field"><span class="config-field-name">${escapeHtml(fieldLabel(sourcePath))} <small>(${escapeHtml(sourcePath)})</small></span>${ruleControl}${description ? `<small class="config-description">说明：${escapeHtml(description)}</small>` : ''}${note ? `<em>备注：${escapeHtml(note)}</em>` : ''}</label>`;
    }).join('') || '<p class="muted">此分类暂无可编辑项。</p>';
    if (tab.id === 'scanner') {
      container.insertAdjacentHTML('beforeend', `<label class="config-field web-config-field"><span class="config-field-name">多线程刮削 <small>(JavSP WEB)</small></span><input id="preset-task-concurrency" type="number" min="1" max="32" value="${Math.max(1, Math.min(32, Number(state.taskConcurrency) || 1))}"><small class="config-description">手动刮削目录内有多个影片时，同时运行的任务数量；超出的任务会保留在队列中等待。</small></label>`);
    }
  });
}

renderPresetNavigation();

function readConfigFields() {
  const values = cloneValue(state.formValues || {});
  document.querySelectorAll('.config-field-input').forEach((control) => {
    if (!control.dataset.configPath) return;
    const [section, ...path] = control.dataset.configPath.split('.');
    setPathValue(values, `${section}.${path.join('.')}`, control.value);
  });
  document.querySelectorAll('#preset-fields-crawler .crawler-config-group').forEach((group) => {
    setPathValue(values, `crawler.selection.${group.dataset.crawlerGroup}`, [...group.querySelectorAll('.crawler-selection')].map((item) => item.value));
  });
  return Object.fromEntries(FORM_SECTIONS.map((section) => [section, values[section] || {}]));
}

function crawlerConfigMarkup(selection = {}) {
  return Object.entries(CRAWLER_GROUPS).map(([group, label]) => {
    const selected = Array.isArray(selection[group]) ? selection[group] : [];
    const options = CRAWLER_IDS.filter((id) => !selected.includes(id)).map((id) => `<option value="${id}">${id}</option>`).join('');
    return `<div class="crawler-config-group" data-crawler-group="${group}"><h3>${label}爬虫</h3><div class="crawler-config-list">${selected.map((id, index) => `<div class="crawler-config-row"><select class="crawler-selection">${CRAWLER_IDS.map((option) => `<option value="${option}"${option === id ? ' selected' : ''}>${option}</option>`).join('')}</select><button class="button secondary crawler-move" type="button" data-direction="up"${index ? '' : ' disabled'}>上移</button><button class="button secondary crawler-move" type="button" data-direction="down"${index === selected.length - 1 ? ' disabled' : ''}>下移</button><button class="button danger crawler-remove" type="button">删除</button></div>`).join('')}</div><div class="crawler-add"><select class="crawler-add-select"><option value="">添加爬虫</option>${options}</select><button class="button secondary crawler-add-button" type="button">添加</button></div></div>`;
  }).join('');
}

async function loadCrawlerConfig() {
  const host = $('#crawler-config-content');
  if (!host) return;
  host.innerHTML = '<p class="muted">正在读取爬虫配置...</p>';
  try {
    const result = await api('/api/crawler-config');
    host.innerHTML = `<p class="muted">此页面设置全局爬虫规则。每个刮削预设使用哪些爬虫及其顺序，请在“刮削预设”的“爬虫”标签页中设置。</p>${crawlerRulesMarkup(result.rules || {}, result.available_required_keys || [])}<div class="form-actions"><button class="button primary" id="save-crawler-config" type="button">保存爬虫配置</button><span id="crawler-config-message" class="form-message"></span></div>`;
  } catch (error) { host.innerHTML = `<p class="form-error">${escapeHtml(error.message)}</p>`; }
}

async function saveCrawlerConfig() {
  const rules = {
    required_keys: [...document.querySelectorAll('#crawler-rule-required-keys input:checked')].map((item) => item.value),
    hardworking: $('#crawler-rule-hardworking').checked,
    respect_site_avid: $('#crawler-rule-respect-site-avid').checked,
    fc2fan_local_path: $('#crawler-rule-fc2fan-path').value.trim() || null,
    sleep_after_scraping: $('#crawler-rule-sleep').value.trim(),
    use_javdb_cover: $('#crawler-rule-javdb-cover').value,
    normalize_actress_name: $('#crawler-rule-normalize-actress').checked,
  };
  const message = $('#crawler-config-message');
  try { await api('/api/crawler-config', { method: 'PUT', body: JSON.stringify(rules) }); message.textContent = '爬虫配置已保存'; await loadCrawlerConfig(); } catch (error) { message.textContent = error.message; }
}

function crawlerRulesMarkup(rules, availableKeys) {
  const required = new Set(Array.isArray(rules.required_keys) ? rules.required_keys : []);
  const keys = availableKeys.length ? availableKeys : ['cover', 'title'];
  const checked = (id, fallback = true) => rules[id] === undefined ? fallback : Boolean(rules[id]);
  return `<div class="crawler-rules-editor"><label class="config-field"><span class="config-field-name">抓取成功必需字段 <small>(crawler.required_keys)</small></span><span id="crawler-rule-required-keys" class="crawler-required-keys">${keys.map((key) => `<label class="check-label"><input type="checkbox" value="${escapeHtml(key)}"${required.has(key) ? ' checked' : ''}>${escapeHtml(key)}</label>`).join('')}</span><small class="config-description">至少命中这些字段才将爬虫结果视为有效。</small></label><label class="check-label"><input id="crawler-rule-hardworking" type="checkbox"${checked('hardworking') ? ' checked' : ''}>深度抓取更多信息</label><label class="check-label"><input id="crawler-rule-respect-site-avid" type="checkbox"${checked('respect_site_avid') ? ' checked' : ''}>使用站点返回的番号</label><label class="config-field"><span class="config-field-name">FC2Fan 本地镜像目录</span><input id="crawler-rule-fc2fan-path" value="${escapeHtml(rules.fc2fan_local_path || '')}" placeholder="未设置"><small class="config-description">目录中应包含类似 FC2-12345.html 的镜像文件。</small></label><label class="config-field"><span class="config-field-name">每部影片刮削后等待时间</span><input id="crawler-rule-sleep" value="${escapeHtml(rules.sleep_after_scraping || 'PT1S')}" placeholder="PT1S"><small class="config-description">使用 ISO 8601 时长，例如 PT1S。</small></label><label class="config-field"><span class="config-field-name">JavDB 封面策略</span><select id="crawler-rule-javdb-cover"><option value="fallback"${rules.use_javdb_cover === 'fallback' ? ' selected' : ''}>fallback</option><option value="yes"${rules.use_javdb_cover === 'yes' ? ' selected' : ''}>yes</option><option value="no"${rules.use_javdb_cover === 'no' ? ' selected' : ''}>no</option></select></label><label class="check-label"><input id="crawler-rule-normalize-actress" type="checkbox"${checked('normalize_actress_name') ? ' checked' : ''}>统一女优艺名</label></div>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  if (response.status === 401) { location.href = '/login'; throw new Error('登录已过期'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(formatApiError(data.detail, response.status));
  return data;
}

function formatApiError(detail, status) {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const labels = { name: '名称', type: '类型', url: '服务地址', external_url: '外部播放地址', api_key: 'API 密钥', libraries: '管理的媒体库' };
    const messages = detail.map((item) => {
      if (!item || typeof item !== 'object') return String(item || '');
      const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== 'body').at(-1) : '';
      const label = labels[field] || field || '输入内容';
      const message = String(item.msg || '格式不正确').replace(/^Field required$/i, '不能为空').replace(/^Input should be a valid URL.*$/i, '必须是有效的网址');
      return `${label}${message.startsWith('不') || message.startsWith('必') ? '' : '：'}${message}`;
    }).filter(Boolean);
    if (messages.length) return messages.join('；');
  }
  if (detail && typeof detail === 'object') {
    const message = detail.message || detail.error || detail.detail;
    if (typeof message === 'string' && message.trim()) return message;
    try { return JSON.stringify(detail); } catch (_) { return '请求失败'; }
  }
  return status === 422 ? '请检查填写的内容' : '请求失败';
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[character]));
}

function showToast(message, tone = 'success') {
  const host = document.querySelector('dialog[open]') || document.body;
  let container = host.querySelector(':scope > #toast-container');
  if (!container) {
    document.querySelectorAll('#toast-container').forEach((item) => item.remove());
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    container.setAttribute('aria-live', 'polite');
    host.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast ${tone}`;
  toast.textContent = message;
  container.appendChild(toast);
  window.setTimeout(() => { toast.classList.add('leaving'); }, 2800);
  window.setTimeout(() => { toast.remove(); }, 3200);
}

function showView(view) {
  document.documentElement.removeAttribute('data-initial-view');
  document.querySelectorAll('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  document.querySelectorAll('.view').forEach((panel) => panel.classList.toggle('active', panel.dataset.panel === view));
  const title = { overview: '概览', scrape: '手动刮削', presets: '刮削预设', settings: '系统设置' }[view] || '概览';
  $('#section-title').textContent = title;
  $('#section-eyebrow').textContent = view === 'settings' || view === 'presets' ? '配置' : '工作区';
  if (view === 'overview') renderOverview();
  if (view === 'scrape') { renderTasks(); loadPresets(); }
  if (view === 'presets') loadPresets();
  if (view === 'crawler-config') loadCrawlerConfig();
  if (view === 'settings') loadUsers();
}

function taskCard(task) {
  const labels = { queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' };
  const lines = (task.log_tail || []).join('\n');
  const taskName = task.name || String(task.input_directory || '').split(/[\\/]/).pop();
  const log = lines ? `<div class="task-log-wrap"><pre class="task-log" data-task-log="${escapeHtml(task.id)}">${escapeHtml(lines)}</pre><button class="copy-log" type="button" data-copy-task="${escapeHtml(task.id)}">复制日志</button></div>` : '';
  const active = ['queued', 'running'].includes(task.status);
  const actions = `<div class="form-actions task-actions">${task.status === 'running' ? `<button class="button secondary" onclick="cancelTask('${escapeHtml(task.id)}')">停止任务</button>` : ''}<button class="button secondary task-delete" data-delete-task="${escapeHtml(task.id)}"${active ? ' disabled title="请先停止任务"' : ''}>删除</button></div>`;
  return `<article class="task-card"><div class="task-card-head"><div class="task-card-title"><strong>${escapeHtml(taskName)}</strong><div class="task-meta"><span>预设：${escapeHtml(task.preset_name || task.preset_id || '默认配置')}</span><span>时间：${new Date(task.created_at).toLocaleString()}</span></div></div><span class="badge ${task.status}">${labels[task.status] || task.status}</span></div><div class="task-path">路径：${escapeHtml(task.input_directory)}</div>${task.error ? `<div class="form-error">${escapeHtml(task.error)}</div>` : ''}${log}${actions}</article>`;
}

function crawlerStatusClass(status) {
  const value = String(status || '');
  if (value.startsWith('重试')) return 'retrying';
  if (value === '完成') return 'completed';
  if (value === '失败') return 'failed';
  if (value === '未找到' || value === '重复') return 'inactive';
  return 'running';
}

function crawlerTooltip(status, detail) {
  const info = detail || {};
  if (status === '完成') {
    return [
      info.dvdid && `番号：${info.dvdid}`,
      info.title && `标题：${info.title}`,
      info.url && `来源：${info.url}`,
    ].filter(Boolean).join('\n') || '爬虫已完成，未返回可展示的字段。';
  }
  if (info.reason) return `原因：${info.reason}`;
  if (status.startsWith('重试')) return `正在重试${info.attempt ? `（${info.attempt}/${info.total || '?'}）` : ''}`;
  if (status === '未找到') return '该数据源未找到匹配的影片。';
  if (status === '重复') return '该数据源返回了多个无法自动判定的结果。';
  return '正在等待该爬虫返回结果。';
}

function progressMarkup(task) {
  const progress = task.progress || { stages: {}, crawlers: {} };
  const stage = (key, label) => {
    const item = progress.stages?.[key] || { percent: 0, done: 0, total: 0 };
    const count = item.total ? `${item.done}/${item.total}` : `${item.percent}%`;
    return `<div class="progress-stage"><div class="progress-stage-head"><strong>${label}</strong><span>${count}</span></div><div class="progress-track"><i style="width:${Math.max(0, Math.min(100, item.percent || 0))}%"></i></div></div>`;
  };
  const crawlerUnits = Object.entries(progress.crawlers || {}).map(([name, status]) => `<span class="crawler-unit"><b>${escapeHtml(name)}</b><em>${escapeHtml(status)}</em></span>`).join('');
  return `<div class="scrape-progress">${stage('concurrent', '并发任务')}${crawlerUnits ? `<div class="crawler-units">${crawlerUnits}</div>` : ''}${stage('summary', '汇总数据')}${stage('images', '下载图片')}</div>`;
}

function taskCard(task) {
  const labels = { queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' };
  const lines = (task.log_tail || []).join('\n');
  const taskName = task.name || String(task.input_directory || '').split(/[\\/]/).pop();
  const rawLog = lines ? `<details class="task-raw-log" data-task-details="${escapeHtml(task.id)}"><summary>查看日志 (${task.log_tail.length} 行)</summary><div class="task-log-wrap"><pre class="task-log" data-task-log="${escapeHtml(task.id)}">${escapeHtml(lines)}</pre><button class="copy-log" type="button" data-copy-task="${escapeHtml(task.id)}">复制日志</button></div></details>` : '';
  const active = task.status === 'running';
  const actions = `<div class="form-actions task-actions">${active ? `<button class="button secondary" onclick="cancelTask('${escapeHtml(task.id)}')">停止任务</button>` : ''}<button class="button secondary task-delete" data-delete-task="${escapeHtml(task.id)}"${active ? ' disabled title="请先停止任务"' : ''}>删除</button></div>`;
  return `<article class="task-card"><div class="task-card-head"><div class="task-card-title"><strong>${escapeHtml(taskName)}</strong><div class="task-meta"><span>预设：${escapeHtml(task.preset_name || task.preset_id || '默认配置')}</span><span>时间：${new Date(task.created_at).toLocaleString()}</span></div></div><span class="badge ${task.status}">${labels[task.status] || task.status}</span></div><div class="task-path">路径：${escapeHtml(task.input_directory)}</div>${progressMarkup(task)}${task.error ? `<div class="form-error">${escapeHtml(task.error)}</div>` : ''}${rawLog}${actions}</article>`;
}

function progressMarkup(task) {
  const progress = task.progress || { stages: {}, crawlers: {} };
  const circle = (key, label) => {
    const item = progress.stages?.[key] || { percent: 0, done: 0, total: 0 };
    const percent = Math.max(0, Math.min(100, item.percent || 0));
    const count = item.total ? `${item.done}/${item.total}` : `${percent}%`;
    return `<div class="wave-progress" style="--progress:${percent}%"><div class="wave-progress-content"><b>${percent}%</b><span>${label}</span><em>${count}</em></div></div>`;
  };
  const crawlerDetails = progress.crawler_details || {};
  const crawlerUnits = Object.entries(progress.crawlers || {}).map(([name, status]) => `<span class="crawler-unit crawler-${crawlerStatusClass(status)}" tabindex="0"><b>${escapeHtml(name.replace('javsp.web.', ''))}</b><em>${escapeHtml(status)}</em><span class="crawler-tooltip" role="tooltip">${escapeHtml(crawlerTooltip(status, crawlerDetails[name]))}</span></span>`).join('');
  return `<div class="scrape-progress scrape-progress-circles">${circle('concurrent', '并发任务')}${circle('summary', '汇总数据')}${circle('images', '下载图片')}<div class="crawler-units">${crawlerUnits || '<span class="muted">等待爬虫状态</span>'}</div></div>`;
}

function progressMarkup(task) {
  const progress = task.progress || { stages: {}, crawlers: {}, metadata: {}, images: {} };
  const stageData = (key) => progress.stages?.[key] || { percent: 0, done: 0, total: 0 };
  const circle = (key, label) => {
    const item = stageData(key);
    const percent = Math.max(0, Math.min(100, Number(item.percent) || 0));
    const count = item.total ? `${item.done}/${item.total}` : `${percent}%`;
    return `<div class="wave-progress" style="--progress:${percent}%"><div class="wave-progress-content"><b>${percent}%</b><span>${label}</span><em>${count}</em></div></div>`;
  };
  const crawlerDetails = progress.crawler_details || {};
  const crawlerUnits = Object.entries(progress.crawlers || {}).map(([name, status]) => `<span class="crawler-unit crawler-${crawlerStatusClass(status)}" tabindex="0"><b>${escapeHtml(name.replace('javsp.web.', ''))}</b><em>${escapeHtml(status)}</em><span class="crawler-tooltip" role="tooltip">${escapeHtml(crawlerTooltip(status, crawlerDetails[name]))}</span></span>`).join('');
  const metadata = progress.metadata || {};
  const metadataRows = [['番号', metadata.dvdid], ['标题', metadata.title], ['女优', Array.isArray(metadata.actress) ? metadata.actress.join('、') : metadata.actress], ['导演', metadata.director], ['制作商', metadata.producer], ['发行商', metadata.publisher], ['发行时间', metadata.publish_date]].map(([label, value]) => `<div class="metadata-row"><dt>${label}</dt><dd>${escapeHtml(value || '-')}</dd></div>`).join('');
  const imageInfo = progress.images || {};
  const imageBlocks = imageCountsMarkup({ coverDone: imageInfo.cover_done, coverStatus: imageInfo.cover_status, fanartDone: imageInfo.fanart_done, fanartTotal: imageInfo.fanart_total, fanartStatus: imageInfo.fanart_status, fanartFailures: imageInfo.fanart_failures });
  return `<div class="scrape-progress stage-panels"><section class="progress-panel progress-concurrent"><div class="progress-panel-heading"><strong>并发任务</strong></div>${circle('concurrent', '并发任务')}<div class="crawler-units">${crawlerUnits || '<span class="muted">等待爬虫状态</span>'}</div></section><section class="progress-panel progress-summary"><div class="progress-panel-heading"><strong>汇总数据</strong></div>${circle('summary', '汇总数据')}<dl class="metadata-grid">${metadataRows}</dl></section><section class="progress-panel progress-images"><div class="progress-panel-heading"><strong>下载图片</strong></div>${circle('images', '下载图片')}${imageBlocks}</section></div>`;
}

function imageCountsMarkup({ coverDone = 0, coverStatus = 'pending', fanartDone = 0, fanartTotal = 0, fanartStatus = 'pending', fanartFailures = [] }) {
  const total = Math.max(0, Number(fanartTotal) || 0);
  const done = Math.min(Math.max(0, Number(fanartDone) || 0), total);
  const failures = new Set((fanartFailures || []).map((value) => Number(value)));
  const coverLabel = coverDone ? '封面已下载' : (coverStatus === 'failed' ? '封面下载失败' : (coverStatus === 'downloading' ? '正在下载封面' : '封面未下载'));
  const coverClass = coverDone ? 'done' : (coverStatus === 'failed' ? 'failed' : (coverStatus === 'downloading' ? 'downloading' : ''));
  const fanartBlocks = Array.from({ length: total }, (_, index) => {
    const current = index + 1;
    const failed = failures.has(current);
    const completed = current <= done && !failed;
    const downloading = !completed && !failed && fanartStatus === 'downloading' && current === done + 1;
    const label = completed ? `剧照 ${current} 已下载` : (failed ? `剧照 ${current} 下载失败` : (downloading ? `正在下载剧照 ${current}` : `剧照 ${current} 未下载`));
    return `<i class="image-block ${completed ? 'done' : ''}${failed ? ' failed' : ''}${downloading ? ' downloading' : ''}" title="${label}"></i>`;
  }).join('');
  const fanartLabel = total ? (fanartStatus === 'failed' ? `剧照下载失败（${done}/${total}）` : `剧照 ${done}/${total}`) : '暂无剧照';
  return `<div class="image-counts"><span class="image-kind">封面</span><i class="image-block ${coverClass}" title="${coverLabel}"></i><em class="image-state ${coverClass}">${coverLabel}</em><span class="image-kind">剧照</span>${fanartBlocks || '<em class="muted">暂无剧照</em>'}<em class="image-state ${fanartStatus === 'failed' ? 'failed' : ''}">${fanartLabel}</em></div>`;
}

function rememberLogScroll() {
  document.querySelectorAll('[data-task-log]').forEach((log) => { state.logScroll[log.dataset.taskLog] = log.scrollTop; });
  document.querySelectorAll('[data-task-details]').forEach((details) => { state.logOpen[details.dataset.taskDetails] = details.open; });
}

function restoreLogScroll() {
  document.querySelectorAll('[data-task-log]').forEach((log) => { log.scrollTop = state.logScroll[log.dataset.taskLog] || 0; });
  document.querySelectorAll('[data-task-details]').forEach((details) => { details.open = Boolean(state.logOpen[details.dataset.taskDetails]); });
}

function renderTasks() {
  rememberLogScroll();
  $('#task-table').innerHTML = state.tasks.length ? state.tasks.map(taskCard).join('') : '<div class="task-list empty">还没有任务记录</div>';
  window.requestAnimationFrame(restoreLogScroll);
}

function renderOverview() {
  $('#metric-total').textContent = state.tasks.length;
  $('#metric-running').textContent = state.tasks.filter((task) => task.status === 'running' || task.status === 'queued').length;
  const latest = state.tasks[0];
  $('#metric-result').textContent = latest ? ({ succeeded: '成功', failed: '失败', running: '运行中', queued: '排队中' }[latest.status] || latest.status) : '-';
  $('#overview-tasks').innerHTML = state.tasks.length ? state.tasks.slice(0, 5).map(taskCard).join('') : '<div class="task-list empty">还没有任务记录</div>';
}

function overviewTaskCard(task) {
  const failed = task.status === 'failed' || task.status === 'cancelled';
  const count = failed ? 6 : Math.min(task.cover_count || 0, 12);
  const covers = count ? Array.from({ length: count }, (_, index) => failed ? '<span class="cover-tile cover-failed">失败</span>' : `<img class="cover-tile" src="/api/tasks/${encodeURIComponent(task.id)}/cover/${index}" loading="lazy" alt="">`).join('') : '<span class="cover-empty">暂无封面</span>';
  return `<article class="overview-task-card"><div class="overview-task-head"><div><strong>${escapeHtml(task.name || task.id)}</strong><div class="task-meta"><span>${escapeHtml(task.preset_name || '默认配置')}</span><span>${new Date(task.created_at).toLocaleString()}</span></div></div><span class="badge ${task.status}">${task.status === 'succeeded' ? '已完成' : (failed ? '失败' : (task.status === 'running' ? '运行中' : '排队中'))}</span></div><div class="cover-wall ${failed ? 'failure' : ''}">${covers}</div></article>`;
}

function renderOverview() {
  $('#metric-total').textContent = state.tasks.length;
  $('#metric-running').textContent = state.tasks.filter((task) => task.status === 'running' || task.status === 'queued').length;
  const latest = state.tasks[0];
  $('#metric-result').textContent = latest ? ({ succeeded: '成功', failed: '失败', running: '运行中', queued: '排队中' }[latest.status] || latest.status) : '-';
  $('#overview-tasks').innerHTML = state.tasks.length ? state.tasks.slice(0, 5).map(overviewTaskCard).join('') : '<div class="task-list empty">还没有任务记录</div>';
}

function renderOverview() {
  $('#metric-total').textContent = state.tasks.length;
  $('#metric-running').textContent = state.tasks.filter((task) => task.status === 'running' || task.status === 'queued').length;
  const latest = state.tasks[0];
  $('#metric-result').textContent = latest ? ({ succeeded: '成功', failed: '失败', running: '运行中', queued: '排队中' }[latest.status] || latest.status) : '-';
  const completed = state.tasks.filter((task) => task.status === 'succeeded' && task.cover_count > 0).slice(0, 24);
  const availableIds = new Set(completed.map((task) => task.id));
  state.selectedOverviewTasks = new Set([...state.selectedOverviewTasks].filter((id) => availableIds.has(id)));
  const selectedCount = state.selectedOverviewTasks.size;
  const toolbar = completed.length ? `<div class="overview-cover-toolbar"><label class="check-label"><input id="overview-select-all" type="checkbox"${selectedCount && selectedCount === completed.length ? ' checked' : ''}>选择全部</label><span class="muted">已选择 ${selectedCount} 项</span><button id="overview-delete-selected" class="button danger" type="button"${selectedCount ? '' : ' disabled'}>删除所选记录</button></div>` : '';
  $('#overview-tasks').innerHTML = completed.length ? `<div class="overview-cover-wall">${completed.map((task) => `<figure class="overview-cover"><button class="overview-cover-delete" type="button" data-delete-task="${escapeHtml(task.id)}" title="删除任务记录">删除</button><img src="/api/tasks/${encodeURIComponent(task.id)}/cover/0" loading="lazy" alt="${escapeHtml(task.name || '')}"><figcaption>${escapeHtml(task.name || task.id)}</figcaption></figure>`).join('')}</div>` : '<div class="task-list empty">还没有已完成的封面</div>';
  if (completed.length) {
    $('#overview-tasks').insertAdjacentHTML('afterbegin', toolbar);
    $('#overview-tasks').querySelectorAll('.overview-cover').forEach((card) => {
      const task = completed.find((item) => card.querySelector(`img[src*="/api/tasks/${encodeURIComponent(item.id)}/cover/"]`));
      if (!task) return;
      const selected = state.selectedOverviewTasks.has(task.id);
      card.classList.toggle('selected', selected);
      card.insertAdjacentHTML('afterbegin', `<label class="overview-cover-select"><input type="checkbox" data-overview-select="${escapeHtml(task.id)}"${selected ? ' checked' : ''} aria-label="选择封面"></label>`);
    });
  }
}

async function loadTasks() {
  const pageScroll = window.scrollY;
  try { rememberLogScroll(); state.tasks = await api('/api/tasks'); syncTaskExpansion(state.tasks); renderOverview(); renderTasks(); if ($('#task-detail-dialog')?.open && state.activeTaskDetail) openTaskDetail(state.activeTaskDetail); window.requestAnimationFrame(restoreLogScroll); } catch (error) { console.error(error); }
  if ($('#auto-scrape-run-dialog')?.open && state.activeAutoScrapeHistory) renderAutoScrapeHistory(state.activeAutoScrapeHistory);
  window.requestAnimationFrame(() => window.scrollTo({ top: pageScroll }));
}

async function loadPathTools() {
  try {
    const runtime = await api('/api/runtime');
    state.runtime = runtime;
    if ($('#app-version') && runtime.version) $('#app-version').textContent = `v${runtime.version}`;
    const tools = $('#path-tools');
    tools.classList.remove('hidden');
    const nativeButtons = tools.querySelectorAll('.native-path-button');
    nativeButtons.forEach((button) => button.classList.toggle('hidden', runtime.docker));
    $('#docker-path-browser')?.classList.toggle('hidden', !runtime.docker);
    $('#docker-schedule-path-browser')?.classList.toggle('hidden', !runtime.docker);
    $('.native-schedule-path-button')?.classList.toggle('hidden', Boolean(runtime.docker));
  } catch (error) {
    console.error(error);
  }
}

async function selectNativePath(kind) {
  try {
    const selected = await api('/api/path/select', { method: 'POST', body: JSON.stringify({ kind }) });
    if (selected.path) $('#input-directory').value = selected.path;
  } catch (error) {
    $('#task-message').textContent = error.message;
  }
}

function setPathTarget(path) {
  const target = state.pathBrowser.target === 'schedule'
    ? $('#auto-scrape-schedule-directory')
    : (state.pathBrowser.target === 'preset-output-directory'
      ? document.querySelector('[data-config-path="summarizer.path.output_folder_pattern"]')
      : $('#input-directory'));
  if (target) target.value = path;
}

function renderDockerPathBrowser(data) {
  const current = $('#path-browser-current');
  const list = $('#path-browser-list');
  const up = $('#path-browser-up');
  const choose = $('#path-browser-choose');
  if (!current || !list || !up || !choose) return;
  state.pathBrowser.currentPath = data.path;
  current.textContent = data.path;
  up.disabled = !data.parent;
  up.dataset.parentPath = data.parent || '';
  choose.classList.toggle('hidden', !['directory', 'any'].includes(state.pathBrowser.kind));
  const entries = data.entries || [];
  list.innerHTML = entries.length ? entries.map((item) => {
    const canSelect = state.pathBrowser.kind === 'any' || state.pathBrowser.kind === item.kind;
    const selectLabel = item.kind === 'directory' ? '选此文件夹' : '选此文件';
    const enter = item.kind === 'directory' ? `<button class="button secondary path-browser-enter" type="button" data-path-browser-enter="${escapeHtml(item.path)}" data-path-browser-kind="directory">进入</button>` : '';
    return `<div class="path-browser-row"><span class="path-browser-entry-icon">${item.kind === 'directory' ? '文件夹' : '视频'}</span><span class="path-browser-entry-name">${escapeHtml(item.name)}</span><div class="path-browser-row-actions">${enter}${canSelect ? `<button class="button secondary path-browser-select" type="button" data-path-browser-select="${escapeHtml(item.path)}">${selectLabel}</button>` : ''}</div></div>`;
  }).join('') : '<p class="muted path-browser-empty">此文件夹中没有可用的子目录或视频文件。</p>';
}

async function loadDockerPathBrowser(path = state.pathBrowser.currentPath) {
  const message = $('#path-browser-message');
  if (message) message.textContent = '';
  try {
    const data = await api(`/api/path/browse?path=${encodeURIComponent(path)}`);
    renderDockerPathBrowser(data);
  } catch (error) {
    if (message) message.textContent = error.message;
  }
}

async function openDockerPathBrowser(kind, target) {
  state.pathBrowser = { kind, target, currentPath: '/' };
  $('#path-browser-title').textContent = kind === 'directory' ? '选择容器文件夹' : (kind === 'file' ? '选择容器视频文件' : '选择容器路径');
  $('#path-browser-subtitle').textContent = kind === 'directory' ? '进入文件夹后可选择当前目录，或继续浏览下一级。' : (kind === 'file' ? '进入文件夹后选择一个视频文件。' : '可选择文件夹，也可进入文件夹选择视频文件。');
  $('#path-browser-dialog').showModal();
  await loadDockerPathBrowser('/');
}

function confirmAction({ title, text, confirmLabel = '确认', danger = false, run }) {
  state.pendingConfirm = { run };
  $('#action-confirm-title').textContent = title;
  $('#action-confirm-text').textContent = text;
  $('#action-confirm-message').textContent = '';
  const button = $('#action-confirm-button');
  button.textContent = confirmLabel;
  button.className = `button ${danger ? 'danger' : 'primary'}`;
  $('#action-confirm-dialog').showModal();
}

function cancelTask(id) {
  const task = state.tasks.find((item) => item.id === id);
  confirmAction({
    title: '停止任务',
    text: `确定停止任务“${task?.name || id}”吗？`,
    confirmLabel: '停止任务',
    danger: true,
    run: async () => { await api(`/api/tasks/${id}/cancel`, { method: 'POST' }); await loadTasks(); },
  });
}

function deleteTask(id) {
  deleteTaskInDialog(id);
}

async function deleteTaskInDialog(id) {
  const task = state.tasks.find((item) => item.id === id);
  state.pendingDeleteTask = id;
  $('#task-delete-text').textContent = `确定删除任务“${task?.name || id}”的刮削记录和日志吗？只删除 JavSP WEB 记录，不删除视频、NFO、封面或剧照文件。`;
  $('#task-delete-message').textContent = '';
  $('#task-delete-dialog').showModal();
}

async function copyTaskLog(button) {
  const log = button.closest('.task-log-wrap')?.querySelector('.task-log');
  if (!log) return;
  try {
    await navigator.clipboard.writeText(log.textContent || '');
  } catch {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(log);
    selection.removeAllRanges();
    selection.addRange(range);
    document.execCommand('copy');
    selection.removeAllRanges();
  }
  const original = button.textContent;
  button.textContent = '已复制';
  window.setTimeout(() => { button.textContent = original; }, 1200);
}

function renderPresetList() {
  $('#preset-list').innerHTML = state.presets.map((preset) => `<button class="preset-item ${state.editingPreset === preset.id ? 'active' : ''}" data-preset="${preset.id}"><strong>${escapeHtml(preset.name)}</strong><span>${preset.id === 'default' || preset.mode === 'form' ? '窗口表单' : 'config.yml'}${preset.id === 'default' ? ' · 内置' : ''}</span></button>`).join('');
  document.querySelectorAll('[data-preset]').forEach((button) => button.addEventListener('click', () => editPreset(button.dataset.preset)));
  $('#task-preset').innerHTML = state.presets.map((preset) => `<option value="${preset.id}">${escapeHtml(preset.name)}</option>`).join('');
}

async function deletePresetFromList(id) {
  try {
    await api(`/api/presets/${id}`, { method: 'DELETE' });
    if (state.editingPreset === id) state.editingPreset = null;
    await loadPresets();
  } catch (error) { $('#preset-message').textContent = error.message; }
}

function renderPresetList() {
  $('#preset-list').innerHTML = state.presets.map((preset) => `<div class="preset-list-row"><button class="preset-item ${state.editingPreset === preset.id ? 'active' : ''}" data-preset="${preset.id}"><strong>${escapeHtml(preset.name)}</strong><span>${preset.id === 'default' || preset.mode === 'form' ? '窗口表单' : 'config.yml'}${preset.id === 'default' ? ' · 内置' : ''}</span></button>${preset.id === 'default' ? '' : `<button class="icon-button preset-delete" type="button" data-delete-preset="${preset.id}">删除</button>`}</div>`).join('');
  document.querySelectorAll('[data-preset]').forEach((button) => button.addEventListener('click', () => editPreset(button.dataset.preset)));
  document.querySelectorAll('[data-delete-preset]').forEach((button) => button.addEventListener('click', (event) => { event.stopPropagation(); deletePresetFromList(button.dataset.deletePreset); }));
  $('#task-preset').innerHTML = state.presets.map((preset) => `<option value="${preset.id}">${escapeHtml(preset.name)}</option>`).join('');
}

function renderPresetMode() {
  const yamlMode = state.presetMode === 'yaml';
  $('#preset-form-panel').classList.toggle('hidden', yamlMode);
  $('#preset-yaml-panel').classList.toggle('hidden', !yamlMode);
  if (!yamlMode) renderConfigFields();
}

async function setPresetMode() {
  const nextMode = $('#preset-mode').value;
  if (state.presetMode === nextMode) { renderPresetMode(); return; }
  const previousMode = state.presetMode;
  try {
    if (previousMode === 'form') {
      state.formValues = readConfigFields();
      const converted = await api('/api/presets/convert', { method: 'POST', body: JSON.stringify({ mode: 'form', form: state.formValues }) });
      $('#preset-content').value = converted.content;
    } else if (previousMode === 'yaml') {
      const converted = await api('/api/presets/convert', { method: 'POST', body: JSON.stringify({ mode: 'yaml', content: $('#preset-content').value }) });
      state.formValues = converted.form;
    }
    state.presetMode = nextMode;
    renderPresetMode();
  } catch (error) {
    $('#preset-mode').value = previousMode || 'form';
    $('#preset-message').textContent = error.message;
  }
}

function setPresetTab(section) {
  document.querySelectorAll('[data-preset-tab]').forEach((button) => button.classList.toggle('active', button.dataset.presetTab === section));
  document.querySelectorAll('[data-preset-panel]').forEach((panel) => panel.classList.toggle('active', panel.dataset.presetPanel === section));
}

function editPreset(id) {
  const preset = state.presets.find((item) => item.id === id);
  if (!preset) return;
  state.editingPreset = id;
  $('#preset-editor-title').textContent = id === 'default' ? '编辑默认预设' : '编辑预设';
  $('#preset-id').value = id;
  $('#preset-name').value = preset.name;
  state.taskConcurrency = preset.task_concurrency || 1;
  const initialMode = id === 'default' ? 'form' : preset.mode;
  $('#preset-mode').value = initialMode;
  $('#preset-content').value = preset.content || '';
  state.formValues = cloneValue(preset.form_values || {});
  state.presetMode = initialMode;
  renderConfigFields();
  setPresetTab('scanner');
  renderPresetMode();
  $('#delete-preset').disabled = id === 'default';
  renderPresetList();
}

function newPreset() {
  state.editingPreset = null;
  const defaultPreset = state.presets.find((item) => item.id === 'default');
  state.formValues = cloneValue(defaultPreset?.form_values || {});
  state.taskConcurrency = defaultPreset?.task_concurrency || 1;
  state.presetMode = 'form';
  $('#preset-editor-title').textContent = '新建预设';
  $('#preset-form').reset();
  $('#preset-id').value = '';
  renderConfigFields();
  setPresetTab('scanner');
  $('#preset-mode').value = 'form';
  renderPresetMode();
  $('#delete-preset').disabled = true;
  renderPresetList();
}

async function loadPresets() {
  try {
    state.presets = await api('/api/presets');
    if ($('#auto-scrape-rule-list')) renderAutoScrapeRules(state.autoScrapeRules);
    if (!state.editingPreset || !state.presets.some((item) => item.id === state.editingPreset)) editPreset(state.presets[0]?.id);
    else renderPresetList();
  } catch (error) { $('#preset-message').textContent = error.message; }
}

function presetPayload() {
  const mode = $('#preset-mode').value;
  return {
    name: $('#preset-name').value.trim(),
    mode,
    content: mode === 'yaml' ? $('#preset-content').value : '',
    form: mode === 'form' ? readConfigFields() : {},
    task_concurrency: Math.max(1, Math.min(32, Number($('#preset-task-concurrency')?.value) || state.taskConcurrency || 1))
  };
}

async function savePreset() {
  const message = $('#preset-message');
  try {
    const payload = presetPayload();
    if (!payload.name) throw new Error('请输入预设名称');
    const path = state.editingPreset ? `/api/presets/${state.editingPreset}` : '/api/presets';
    const saved = await api(path, { method: state.editingPreset ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    state.editingPreset = saved.id;
    message.textContent = '预设已保存';
    showToast(`预设“${saved.name}”已保存`, 'success');
    await loadPresets();
  } catch (error) { message.textContent = error.message; showToast(error.message, 'error'); }
}

$('#delete-preset').addEventListener('click', () => {
  if (!state.editingPreset || state.editingPreset === 'default') return;
  const presetId = state.editingPreset;
  const presetName = $('#preset-name').value || presetId;
  confirmAction({
    title: '删除刮削预设',
    text: `确定删除预设“${presetName}”吗？`,
    confirmLabel: '确认删除',
    danger: true,
    run: async () => {
      await api(`/api/presets/${presetId}`, { method: 'DELETE' });
      state.editingPreset = null;
      await loadPresets();
    },
  });
});

async function loadUsers() {
  try {
    const users = await api('/api/users');
    $('#users-table').innerHTML = users.map((user) => `<div class="user-row"><strong>${escapeHtml(user.username)}</strong><span class="role">${user.role === 'admin' ? '管理员' : '操作员'}</span><span class="role">${new Date(user.created_at).toLocaleDateString()}</span><span><button class="icon-button edit-user" data-username="${escapeHtml(user.username)}" data-role="${user.role}">编辑</button> <button class="icon-button delete-user" data-username="${escapeHtml(user.username)}">删除</button></span></div>`).join('');
    document.querySelectorAll('.edit-user').forEach((button) => button.addEventListener('click', () => editUser(button.dataset.username, button.dataset.role)));
    document.querySelectorAll('.delete-user').forEach((button) => button.addEventListener('click', () => removeUser(button.dataset.username)));
  } catch (error) { $('#users-table').innerHTML = `<p class="form-error">${error.message}</p>`; }
}

function editUser(username, role) {
  state.editingUser = username;
  $('#user-dialog-title').textContent = '编辑用户';
  $('#user-name').value = username;
  $('#user-role').value = role;
  $('#user-password').value = '';
  $('#user-password-confirm').value = '';
  $('#user-message').textContent = '';
  $('#user-dialog').showModal();
}

function removeUser(username) {
  confirmAction({
    title: '删除用户',
    text: `确定删除用户“${username}”吗？`,
    confirmLabel: '确认删除',
    danger: true,
    run: async () => { await api(`/api/users/${encodeURIComponent(username)}`, { method: 'DELETE' }); await loadUsers(); },
  });
}

$('#task-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = $('#task-message');
  try {
    const result = await api('/api/tasks', { method: 'POST', body: JSON.stringify({ input_directory: $('#input-directory').value, preset_id: $('#task-preset').value }) });
    message.textContent = result.count > 1 ? `已创建 ${result.count} 个影片任务` : `任务 ${result.tasks?.[0]?.id || ''} 已启动`;
    $('#input-directory').value = '';
    await loadTasks();
  } catch (error) { message.textContent = error.message; }
});

$('#refresh-tasks').addEventListener('click', loadTasks);
document.addEventListener('click', (event) => { const button = event.target.closest('.copy-log'); if (button) copyTaskLog(button); });
document.addEventListener('click', (event) => { const button = event.target.closest('[data-delete-task]'); if (button && !button.disabled) { event.stopPropagation(); deleteTaskInDialog(button.dataset.deleteTask); } });
document.addEventListener('change', (event) => {
  const checkbox = event.target.closest('[data-overview-select]');
  if (checkbox) {
    if (checkbox.checked) state.selectedOverviewTasks.add(checkbox.dataset.overviewSelect);
    else state.selectedOverviewTasks.delete(checkbox.dataset.overviewSelect);
    renderOverview();
    return;
  }
  if (event.target.id === 'overview-select-all') {
    const completed = state.tasks.filter((task) => task.status === 'succeeded' && task.cover_count > 0).slice(0, 24);
    if (event.target.checked) completed.forEach((task) => state.selectedOverviewTasks.add(task.id));
    else state.selectedOverviewTasks.clear();
    renderOverview();
  }
});
document.addEventListener('click', async (event) => {
  const button = event.target.closest('#overview-delete-selected');
  if (!button || button.disabled || !state.selectedOverviewTasks.size) return;
  const ids = [...state.selectedOverviewTasks];
  confirmAction({
    title: '删除刮削记录',
    text: `确定删除选中的 ${ids.length} 条刮削记录吗？只删除 JavSP WEB 中的任务记录和封面墙展示，不删除视频、NFO、封面或剧照文件。`,
    confirmLabel: '删除记录',
    danger: true,
    run: async () => {
      for (const id of ids) await api(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
      ids.forEach((id) => state.selectedOverviewTasks.delete(id));
      await loadTasks();
      showToast(`已删除 ${ids.length} 条刮削记录`);
    },
  });
});
document.addEventListener('click', async (event) => {
  const variable = event.target.closest('[data-insert-naming-variable]');
  if (variable) {
    const target = document.querySelector(`[data-config-path="${variable.dataset.namingTarget}"]`);
    if (!target) return;
    const token = variable.dataset.insertNamingVariable;
    const start = Number.isInteger(target.selectionStart) ? target.selectionStart : target.value.length;
    const end = Number.isInteger(target.selectionEnd) ? target.selectionEnd : start;
    target.value = `${target.value.slice(0, start)}${token}${target.value.slice(end)}`;
    target.focus();
    target.setSelectionRange(start + token.length, start + token.length);
    target.dispatchEvent(new Event('input', { bubbles: true }));
    return;
  }
  const directoryPicker = event.target.closest('[data-select-output-directory]');
  if (!directoryPicker) return;
  const target = document.querySelector(`[data-config-path="${directoryPicker.dataset.selectOutputDirectory}"]`);
  if (!target) return;
  if (state.runtime?.docker) {
    await openDockerPathBrowser('directory', 'preset-output-directory');
    return;
  }
  try {
    const selected = await api('/api/path/select', { method: 'POST', body: JSON.stringify({ kind: 'directory' }) });
    if (selected.path) target.value = selected.path;
  } catch (error) {
    const message = $('#preset-message');
    if (message) message.textContent = error.message;
  }
});
document.addEventListener('change', (event) => {
  const select = event.target.closest('[data-translator-engine]');
  if (!select) return;
  state.formValues = readConfigFields();
  state.formValues.translator ||= {};
  state.formValues.translator.engine = select.value ? { name: select.value } : null;
  renderConfigFields();
});
$('#task-delete-form').addEventListener('submit', async (event) => {
  if (event.submitter?.id !== 'task-delete-confirm') return;
  event.preventDefault();
  try {
    await api(`/api/tasks/${state.pendingDeleteTask}`, { method: 'DELETE' });
    $('#task-delete-dialog').close();
    state.pendingDeleteTask = null;
    await loadTasks();
  } catch (error) { $('#task-delete-message').textContent = error.message; }
});
$('#action-confirm-form').addEventListener('submit', async (event) => {
  if (event.submitter?.id !== 'action-confirm-button') return;
  event.preventDefault();
  const pending = state.pendingConfirm;
  if (!pending) return;
  const button = $('#action-confirm-button');
  button.disabled = true;
  try {
    await pending.run();
    state.pendingConfirm = null;
    $('#action-confirm-dialog').close();
  } catch (error) {
    $('#action-confirm-message').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
document.querySelectorAll('.native-path-button').forEach((button) => button.addEventListener('click', () => selectNativePath(button.dataset.pathKind)));
$('#docker-path-browser')?.addEventListener('click', () => openDockerPathBrowser('any', 'manual'));
$('#docker-schedule-path-browser')?.addEventListener('click', () => openDockerPathBrowser('directory', 'schedule'));
$('#path-browser-up')?.addEventListener('click', () => {
  const parent = $('#path-browser-up').dataset.parentPath;
  if (parent) loadDockerPathBrowser(parent);
});
$('#path-browser-list')?.addEventListener('click', (event) => {
  const select = event.target.closest('[data-path-browser-select]');
  if (select) {
    setPathTarget(select.dataset.pathBrowserSelect);
    $('#path-browser-dialog').close();
    return;
  }
  const entry = event.target.closest('[data-path-browser-enter]');
  if (!entry) return;
  if (entry.dataset.pathBrowserKind === 'directory') loadDockerPathBrowser(entry.dataset.pathBrowserEnter);
  else if (state.pathBrowser.kind !== 'directory') {
    setPathTarget(entry.dataset.pathBrowserEnter);
    $('#path-browser-dialog').close();
  }
});
$('#path-browser-choose')?.addEventListener('click', (event) => {
  event.preventDefault();
  if (['directory', 'any'].includes(state.pathBrowser.kind)) setPathTarget(state.pathBrowser.currentPath);
  $('#path-browser-dialog').close();
});
$('#preset-mode').addEventListener('change', setPresetMode);
document.querySelectorAll('[data-preset-tab]').forEach((button) => button.addEventListener('click', () => setPresetTab(button.dataset.presetTab)));
$('#new-preset').addEventListener('click', newPreset);
$('#save-preset').addEventListener('click', savePreset);
$('#add-user').addEventListener('click', () => { state.editingUser = null; $('#user-dialog-title').textContent = '添加用户'; $('#user-form').reset(); $('#user-message').textContent = ''; $('#user-dialog').showModal(); });
$('#user-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = $('#user-message');
  const password = $('#user-password').value;
  const passwordConfirm = $('#user-password-confirm').value;
  if (password !== passwordConfirm || (!state.editingUser && !password)) { message.textContent = password ? '两次输入的新密码不一致' : '新用户必须设置密码'; return; }
  const payload = { username: $('#user-name').value.trim(), password: password || null, password_confirm: passwordConfirm || null, role: $('#user-role').value };
  try {
    if (state.editingUser) await api(`/api/users/${encodeURIComponent(state.editingUser)}`, { method: 'PUT', body: JSON.stringify(payload) });
    else await api('/api/users', { method: 'POST', body: JSON.stringify(payload) });
    $('#user-dialog').close();
    await loadUsers();
  } catch (error) { message.textContent = error.message; }
});

$('#logout').addEventListener('click', async () => { await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }); location.href = '/login'; });
document.querySelectorAll('.nav-item').forEach((button) => {
  button.title = button.textContent.trim();
  button.addEventListener('click', () => showView(button.dataset.view));
});
document.querySelectorAll('[data-go]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.go)));

function taskDisplayName(task) {
  return task.title || task.file_name || task.name || task.id;
}

function imageProgressSummary(task) {
  const images = task.progress?.images || {};
  const cover = Number(task.cover_count) > 0 ? '封面已下载' : (images.failed ? '封面失败' : '封面等待中');
  const total = Number(images.fanart_total) || Number(task.fanart_count) || 0;
  const done = Math.min(Number(task.fanart_count) || 0, total || Number(task.fanart_count) || 0);
  return total ? `${cover} · 剧照 ${done}/${total}` : cover;
}

function syncTaskExpansion(tasks) {
  state.taskOpen ||= {};
  state.taskStatus ||= {};
  (tasks || []).forEach((task) => {
    const key = String(task.id);
    const previous = state.taskStatus[key];
    if (task.status === 'running' && previous !== 'running') {
      state.taskOpen[key] = true;
      state.taskOpen[`schedule-${key}`] = true;
    } else if (previous === 'running' && task.status !== 'running') {
      state.taskOpen[key] = false;
      state.taskOpen[`schedule-${key}`] = false;
    }
    state.taskStatus[key] = task.status;
  });
}

function taskCard(task) {
  const labels = { queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' };
  const expanded = state.taskOpen?.[task.id] ?? task.status === 'running';
  const lines = (task.log_tail || []).join('\n');
  const rawLog = lines ? `<details class="task-raw-log" data-task-details="${escapeHtml(task.id)}"><summary>查看日志 (${task.log_tail.length} 行)</summary><div class="task-log-wrap"><pre class="task-log" data-task-log="${escapeHtml(task.id)}">${escapeHtml(lines)}</pre><button class="copy-log" type="button" data-copy-task="${escapeHtml(task.id)}">复制日志</button></div></details>` : '';
  const active = ['queued', 'running'].includes(task.status);
  const fileName = task.file_name || task.name || task.id;
  const titleMeta = task.title ? `<span>文件：${escapeHtml(fileName)}</span>` : '';
  const actions = '';
  const detailButton = `<button class="icon-button" type="button" data-task-detail="${escapeHtml(task.id)}" title="查看任务详情">详情</button>`;
  const stopButton = active ? `<button class="button secondary task-stop" type="button" onclick="cancelTask('${escapeHtml(task.id)}')">停止任务</button>` : '';
  const deleteButton = `<button class="task-delete" type="button" data-delete-task="${escapeHtml(task.id)}"${active ? ' disabled title="请先停止任务"' : ' title="删除任务"'}>删除</button>`;
  return `<article class="task-card task-card-collapsible" data-task-card="${escapeHtml(task.id)}"><div class="task-card-head"><div class="task-card-title"><strong>${escapeHtml(taskDisplayName(task))}</strong><div class="task-meta">${titleMeta}<span>预设：${escapeHtml(task.preset_name || task.preset_id || '默认配置')}</span><span>时间：${new Date(task.created_at).toLocaleString()}</span></div><div class="task-path">路径：${escapeHtml(task.input_directory)}</div><div class="task-image-summary">${escapeHtml(imageProgressSummary(task))}</div></div><div class="task-card-tools"><span class="badge ${task.status}">${labels[task.status] || task.status}</span>${detailButton}${stopButton}${deleteButton}<button class="task-toggle" type="button" data-task-toggle="${escapeHtml(task.id)}" aria-expanded="${expanded}" title="${expanded ? '收起任务' : '展开任务'}">${expanded ? '-' : '+'}</button></div></div><div class="task-card-body${expanded ? '' : ' hidden'}" data-task-body="${escapeHtml(task.id)}">${progressMarkup(task)}${task.error ? `<div class="form-error">${escapeHtml(task.error)}</div>` : ''}${rawLog}${actions}</div></article>`;
}

function rememberTaskCards() {
  state.taskOpen ||= {};
  document.querySelectorAll('[data-task-card]').forEach((card) => {
    const id = card.dataset.taskCard;
    state.taskOpen[id] = !card.querySelector('[data-task-body]')?.classList.contains('hidden');
  });
}

function ensureTaskFilters() {
  if ($('#task-filter-bar')) return;
  const taskTable = $('#task-table');
  if (!taskTable) return;
  taskTable.insertAdjacentHTML('beforebegin', `<div id="task-filter-bar" class="task-filter-bar" aria-label="任务筛选"><select id="task-filter-field"><option value="all">全部信息</option><option value="path">路径</option><option value="title">标题</option><option value="dvdid">番号</option><option value="actress">女优</option></select><input id="task-filter-query" type="search" placeholder="搜索路径、标题、番号或女优"><select id="task-filter-status"><option value="">全部状态</option><option value="queued">排队中</option><option value="running">运行中</option><option value="succeeded">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option></select><label>大小 MB<input id="task-filter-size-min" type="number" min="0" placeholder="最小"></label><span>至</span><label><input id="task-filter-size-max" type="number" min="0" placeholder="最大"></label><label>时间<input id="task-filter-date-from" type="date"></label><span>至</span><label><input id="task-filter-date-to" type="date"></label><button id="task-filter-reset" class="button secondary" type="button">重置</button></div><p id="task-filter-summary" class="muted"></p>`);
  $('#task-filter-field')?.remove();
  document.querySelectorAll('#task-filter-bar input, #task-filter-bar select').forEach((control) => control.addEventListener('input', renderTasks));
  $('#task-filter-reset').addEventListener('click', () => {
    document.querySelectorAll('#task-filter-bar input').forEach((control) => { control.value = ''; });
    $('#task-filter-status').value = '';
    renderTasks();
  });
}

function filteredTasks() {
  const query = ($('#task-filter-query')?.value || '').trim().toLocaleLowerCase();
  const field = $('#task-filter-field')?.value || 'all';
  const status = $('#task-filter-status')?.value || '';
  const minSize = Number($('#task-filter-size-min')?.value);
  const maxSize = Number($('#task-filter-size-max')?.value);
  const from = $('#task-filter-date-from')?.value;
  const to = $('#task-filter-date-to')?.value;
  return state.tasks.filter((task) => {
    if (task.source && task.source !== 'manual' && !task.image_retry_started_at) return false;
    const metadata = task.progress?.metadata || {};
    const values = {
      path: task.input_directory || '', title: task.title || metadata.title || '', dvdid: metadata.dvdid || '',
      actress: Array.isArray(metadata.actress) ? metadata.actress.join(' ') : (metadata.actress || '')
    };
    const searchable = field === 'all' ? Object.values(values).join(' ') : values[field];
    if (query && !String(searchable || '').toLocaleLowerCase().includes(query)) return false;
    if (status && task.status !== status) return false;
    const sizeMb = (Number(task.size_bytes) || 0) / (1024 * 1024);
    if (Number.isFinite(minSize) && $('#task-filter-size-min').value !== '' && sizeMb < minSize) return false;
    if (Number.isFinite(maxSize) && $('#task-filter-size-max').value !== '' && sizeMb > maxSize) return false;
    const created = new Date(task.created_at);
    if (from && created < new Date(`${from}T00:00:00`)) return false;
    if (to && created > new Date(`${to}T23:59:59.999`)) return false;
    return true;
  });
}

function renderTasks() {
  ensureTaskFilters();
  rememberLogScroll();
  rememberTaskCards();
  const tasks = filteredTasks();
  $('#task-table').innerHTML = tasks.length ? tasks.map(taskCard).join('') : '<div class="task-list empty">没有符合当前筛选条件的任务</div>';
  const manualTaskCount = state.tasks.filter((task) => !task.source || task.source === 'manual' || task.image_retry_started_at).length;
  $('#task-filter-summary').textContent = `显示 ${tasks.length} / ${manualTaskCount} 个手动任务`;
  restoreLogScroll();
}

function openTaskDetail(taskId) {
  const task = state.tasks.find((item) => item.id === taskId);
  if (!task) return;
  state.activeTaskDetail = taskId;
  const metadata = task.progress?.metadata || {};
  const rows = [['番号', metadata.dvdid], ['标题', metadata.title || taskDisplayName(task)], ['女优', Array.isArray(metadata.actress) ? metadata.actress.join('、') : metadata.actress], ['导演', metadata.director], ['制作商', metadata.producer], ['发行商', metadata.publisher], ['发行时间', metadata.publish_date], ['文件名', task.file_name || task.name]].map(([label, value]) => `<div class="detail-data-row"><dt>${label}</dt><dd>${escapeHtml(value || '-')}</dd></div>`).join('');
  const posterImage = task.cover_count ? `<img class="detail-poster" src="/api/tasks/${encodeURIComponent(task.id)}/cover/0" alt="${escapeHtml(taskDisplayName(task))}">` : artworkPlaceholder('detail-poster detail-poster-empty', task.progress?.images?.cover_status === 'failed' ? '封面下载失败' : '封面未下载');
  const poster = `<div class="detail-poster-wrap">${posterImage}<div id="task-media-overlay" class="task-media-overlay"></div></div>`;
  const imageInfo = task.progress?.images || {};
  const expectedFanart = Math.max(Number(imageInfo.fanart_total) || 0, Number(task.fanart_count) || 0);
  const fanartFailures = imageInfo.fanart_failures || [];
  const fanarts = expectedFanart
    ? Array.from({ length: Math.min(expectedFanart, 24) }, (_, index) => {
      if (index < Number(task.fanart_count || 0)) return `<img src="/api/tasks/${encodeURIComponent(task.id)}/fanart/${index}" loading="lazy" alt="剧照 ${index + 1}">`;
      const failed = fanartFailures.includes(index + 1);
      return artworkPlaceholder('detail-fanart-empty', failed ? `剧照 ${index + 1} 下载失败` : `剧照 ${index + 1} 未下载`);
    }).join('')
    : '<p class="muted">暂无剧照</p>';
  const imageCounts = imageCountsMarkup({ coverDone: task.cover_count, coverStatus: imageInfo.cover_status, fanartDone: task.fanart_count, fanartTotal: expectedFanart, fanartStatus: imageInfo.fanart_status, fanartFailures });
  const retry = task.image_retry_available ? `<button class="button secondary" type="button" data-retry-task-images="${escapeHtml(task.id)}">重新下载封面与剧照</button>` : (task.image_retry_running ? '<button class="button secondary" type="button" disabled>正在重新下载封面与剧照</button>' : '');
  const googleStatus = task.google_cover_search_running ? '正在使用 Google 搜索封面' : (task.google_cover_search_status === 'failed' ? `Google 搜索失败：${task.google_cover_search_error || '未找到可用封面'}` : '');
  const googleCover = !task.cover_count ? `<div class="google-cover-action"><button class="button secondary task-google-cover" type="button" data-google-cover-task="${escapeHtml(task.id)}"${task.google_cover_search_running ? ' disabled' : ''}>${task.google_cover_search_running ? '正在搜索封面' : (task.google_cover_search_status === 'failed' ? '重试 Google 搜索封面' : '使用 Google 搜索封面')}</button>${googleStatus ? `<p class="image-state${task.google_cover_search_status === 'failed' ? ' failed' : ''}">${escapeHtml(googleStatus)}</p>` : ''}</div>` : '';
  const restore = task.restore_available ? `<button class="button danger" type="button" data-restore-task-files="${escapeHtml(task.id)}">还原文件</button>` : '';
  $('#task-detail-title').textContent = taskDisplayName(task);
  $('#task-detail-subtitle').textContent = task.file_name || task.name || '';
  $('#task-detail-content').innerHTML = `<div class="task-detail-main">${poster}<dl class="task-detail-data">${rows}</dl></div><section class="detail-images"><div><h3>下载图片</h3>${imageCounts}</div><div class="detail-image-actions">${googleCover}${retry}${restore}</div></section><section class="detail-fanarts"><h3>剧照 (${task.fanart_count || 0})</h3><div class="detail-fanart-grid">${fanarts}</div></section>`;
  if (!$('#task-detail-dialog').open) $('#task-detail-dialog').showModal();
  api(`/api/tasks/${encodeURIComponent(task.id)}/media-links`).then((result) => {
    const target = $('#task-media-overlay');
    if (!target) return;
    const playable = (result.links || []).filter((link) => link.unique_match && link.play_url);
    const searchable = (result.links || []).filter((link) => link.search_url);
    target.innerHTML = playable.length
      ? playable.map((link) => `<a class="media-play-button" href="${escapeHtml(link.play_url)}" target="_blank" rel="noopener" title="在 ${escapeHtml(link.name)} 中播放">播放</a>`).join('')
      : searchable.map((link) => `<a class="media-play-button media-search-button" href="${escapeHtml(link.search_url)}" target="_blank" rel="noopener" title="在 ${escapeHtml(link.name)} 中搜索">搜索</a>`).join('');
  }).catch(() => {});
  $('#task-detail-content').insertAdjacentHTML('beforeend', '<section id="task-media-links" class="task-media-links"><h3>媒体库播放</h3><p class="muted">正在查找匹配的媒体条目…</p></section>');
  api(`/api/tasks/${encodeURIComponent(task.id)}/media-links`).then((result) => {
    const target = $('#task-media-links');
    if (!target) return;
    const links = result.links || [];
    target.innerHTML = links.length ? `<h3>媒体库播放</h3><div class="media-link-list">${links.map((link) => link.unique_match && link.play_url ? `<a class="button secondary" href="${escapeHtml(link.play_url)}" target="_blank" rel="noopener">在 ${escapeHtml(link.name)} 中播放</a>` : (link.search_url ? `<a class="button secondary" href="${escapeHtml(link.search_url)}" target="_blank" rel="noopener">在 ${escapeHtml(link.name)} 中打开媒体库</a>` : `<span class="muted">${escapeHtml(link.name)}：${escapeHtml(link.error || '未找到匹配条目')}</span>`)).join('')}</div>` : '<h3>媒体库播放</h3><p class="muted">尚未配置媒体服务器。</p>';
  }).catch(() => { const target = $('#task-media-links'); if (target) target.innerHTML = '<h3>媒体库播放</h3><p class="muted">暂时无法读取媒体服务器。</p>'; });
}

function renderOverview() {
  $('#metric-total').textContent = state.tasks.length;
  $('#metric-running').textContent = state.tasks.filter((task) => task.status === 'running' || task.status === 'queued').length;
  const latest = state.tasks[0];
  $('#metric-result').textContent = latest ? ({ succeeded: '成功', failed: '失败', running: '运行中', queued: '排队中' }[latest.status] || latest.status) : '-';
  const completed = state.tasks.filter((task) => ['succeeded', 'failed'].includes(task.status) && ((task.cover_count || task.fanart_count) || (task.progress?.image_sources?.cover_urls?.length || task.progress?.image_sources?.preview_pics?.length))).slice(0, 24);
  $('#overview-tasks').innerHTML = completed.length ? `<div class="overview-cover-wall">${completed.map(overviewCoverCard).join('')}</div>` : '<div class="task-list empty">还没有已完成的任务</div>';
}

function overviewCoverCard(task) {
  const images = task.progress?.images || {};
  const coverReady = Number(task.cover_count) > 0;
  const total = Number(images.fanart_total) || Number(task.fanart_count) || 0;
  const fanart = Math.min(Number(task.fanart_count) || 0, total || Number(task.fanart_count) || 0);
  const coverState = coverReady ? '封面已下载' : (images.failed ? '封面下载失败' : '封面未生成');
  const artwork = coverReady
    ? `<img src="/api/tasks/${encodeURIComponent(task.id)}/cover/0" loading="lazy" alt="${escapeHtml(taskDisplayName(task))}">`
    : artworkPlaceholder('overview-cover-placeholder', images.cover_status === 'failed' ? '封面下载失败' : '封面未下载');
  return `<article class="overview-cover-card"><button class="overview-cover" type="button" data-task-detail="${escapeHtml(task.id)}">${artwork}<span>${escapeHtml(taskDisplayName(task))}</span></button></article>`;
}

function artworkPlaceholder(className, label) {
  return `<span class="${className}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5z"/><path d="m6.5 17 3.2-3.2 2.4 2.4 2-2 3.4 3.4M8.5 8.5h.01"/></svg><b>${escapeHtml(label)}</b></span>`;
}

function formatBytes(value) {
  const number = Number(value) || 0;
  if (!number) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const unit = Math.min(Math.floor(Math.log(number) / Math.log(1024)), units.length - 1);
  return `${(number / (1024 ** unit)).toFixed(unit ? 1 : 0)} ${units[unit]}`;
}

function formatDownloadDate(timestamp) {
  const value = Number(timestamp) || 0;
  return value > 0 ? new Date(value * 1000).toLocaleString() : '未完成';
}

function formatEta(seconds) {
  const value = Number(seconds) || 0;
  if (value <= 0 || value >= 8640000) return '∞';
  const units = [[86400, '天'], [3600, '时'], [60, '分']];
  const parts = [];
  let remaining = value;
  units.forEach(([unit, suffix]) => {
    const amount = Math.floor(remaining / unit);
    if (amount && parts.length < 2) parts.push(`${amount}${suffix}`);
    remaining %= unit;
  });
  return parts.length ? parts.join(' ') : `${remaining}秒`;
}

function populateDownloadFilters(downloads) {
  [['#download-filter-category', 'category', '全部分类'], ['#download-filter-tags', 'tags', '全部标签']].forEach(([selector, key, allLabel]) => {
    const select = $(selector);
    if (!select) return;
    const selected = select.value;
    const values = [...new Set(downloads.flatMap((item) => String(item[key] || '').split(',').map((value) => value.trim()).filter(Boolean)))].sort((left, right) => left.localeCompare(right));
    select.innerHTML = `<option value="">${allLabel}</option>${values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('')}`;
    select.value = values.includes(selected) ? selected : '';
  });
}

function filteredDownloads(downloads) {
  const name = ($('#download-filter-name')?.value || '').trim().toLocaleLowerCase();
  const tags = $('#download-filter-tags')?.value || '';
  const category = $('#download-filter-category')?.value || '';
  const sortBy = state.downloadSort?.key || 'added_on';
  const direction = state.downloadSort?.direction === 'asc' ? 1 : -1;
  return downloads.filter((item) => {
    if (name && !String(item.name || '').toLocaleLowerCase().includes(name)) return false;
    if (tags && !String(item.tags || '').split(',').map((value) => value.trim()).includes(tags)) return false;
    return !category || item.category === category;
  }).sort((left, right) => {
    const a = ['name', 'tags', 'state', 'category'].includes(sortBy) ? String(left[sortBy] || '').localeCompare(String(right[sortBy] || '')) : (Number(left[sortBy]) || 0) - (Number(right[sortBy]) || 0);
    return a * direction;
  });
}

function renderDownloadSummary(downloads) {
  const target = $('#download-summary');
  if (!target) return;
  const downloadSpeed = downloads.reduce((total, item) => total + (Number(item.download_speed) || 0), 0);
  const uploadSpeed = downloads.reduce((total, item) => total + (Number(item.upload_speed) || 0), 0);
  target.innerHTML = `<span>任务 ${downloads.length}</span><span>下载 ${formatBytes(downloadSpeed)}/s</span><span>上传 ${formatBytes(uploadSpeed)}/s</span>`;
}

function renderDownloadRows(downloads, active) {
  const target = $('#download-list');
  const filtered = filteredDownloads(downloads);
  const summary = $('#download-filter-summary');
  if (summary) summary.textContent = `显示 ${filtered.length} / ${downloads.length} 个已接管任务`;
  target.classList.remove('empty');
  const columns = [['name', '名称'], ['size', '选定大小'], ['progress', '进度'], ['state', '状态'], ['seeds', '种子'], ['peers', '用户'], ['download_speed', '下载速度'], ['upload_speed', '上传速度'], ['eta', '剩余时间'], ['ratio', '比率'], ['popularity', '流行度'], ['category', '分类'], ['tags', '标签'], ['added_on', '添加于'], ['completed_on', '完成于']];
  const sortMark = (key) => state.downloadSort?.key === key ? `<span class="download-sort-mark">${state.downloadSort.direction === 'asc' ? '↑' : '↓'}</span>` : '';
  const head = columns.map(([key, label]) => `<th><button class="download-column-sort" type="button" data-download-sort="${key}">${label}${sortMark(key)}</button></th>`).join('');
  const rows = filtered.map((item) => `<tr><td class="download-name-cell" title="${escapeHtml(item.name)}"><span class="download-state-dot ${escapeHtml(String(item.state || '').toLowerCase())}"></span>${escapeHtml(item.name)}</td><td>${formatBytes(item.size)}</td><td><div class="download-progress-cell"><b>${item.progress}%</b><i><em style="width:${Math.max(0, Math.min(100, item.progress))}%"></em></i></div></td><td>${escapeHtml(item.state || '未知')}</td><td>${Number(item.seeds) || 0}</td><td>${Number(item.peers) || 0}</td><td>${formatBytes(item.download_speed)}/s</td><td>${formatBytes(item.upload_speed)}/s</td><td>${escapeHtml(formatEta(item.eta))}</td><td>${Number(item.ratio || 0).toFixed(2)}</td><td>${Number(item.popularity || 0).toFixed(2)}</td><td>${escapeHtml(item.category || '')}</td><td>${escapeHtml(item.tags || '')}</td><td>${escapeHtml(formatDownloadDate(item.added_on))}</td><td>${escapeHtml(formatDownloadDate(item.completed_on))}</td><td><button class="download-row-remove" type="button" data-remove-download="${escapeHtml(item.hash)}" data-downloader-id="${escapeHtml(active.id)}" title="删除种子但保留文件">删除</button></td></tr>`).join('');
  target.innerHTML = `<div class="download-table-wrap"><table class="download-table"><thead><tr>${head}<th aria-label="操作"></th></tr></thead><tbody>${rows || '<tr><td class="download-table-empty" colspan="16">没有符合当前筛选条件的已接管下载任务</td></tr>'}</tbody></table></div>`;
}

function ensureDownloadFilters() {
  const filters = document.querySelectorAll('#download-filter-bar input, #download-filter-bar select');
  filters.forEach((control) => {
    if (control.dataset.bound) return;
    control.dataset.bound = 'true';
    control.addEventListener('input', () => renderDownloadRows(state.activeDownloads || [], state.activeDownloader || {}));
    control.addEventListener('change', () => renderDownloadRows(state.activeDownloads || [], state.activeDownloader || {}));
  });
  $('#download-filter-reset')?.addEventListener('click', () => {
    document.querySelectorAll('#download-filter-bar input').forEach((control) => { control.value = ''; });
    $('#download-filter-category').value = '';
    $('#download-filter-tags').value = '';
    state.downloadSort = { key: 'added_on', direction: 'desc' };
    renderDownloadRows(state.activeDownloads || [], state.activeDownloader || {});
  }, { once: true });
}

async function loadDownloads() {
  const target = $('#download-list');
  if (!target) return;
  const clearDownloadPresentation = () => {
    state.activeDownloads = [];
    state.activeDownloader = null;
    if ($('#download-summary')) $('#download-summary').innerHTML = '';
    if ($('#download-filter-summary')) $('#download-filter-summary').textContent = '';
  };
  try {
    const result = await api('/api/downloads');
    const downloaders = result.downloaders || [];
    renderDownloaderTabs(downloaders);
    if (!downloaders.length) {
      clearDownloadPresentation();
      target.classList.add('empty');
      target.textContent = '尚未添加下载器';
      return;
    }
    if (!state.activeDownloaderId || !downloaders.some((downloader) => downloader.id === state.activeDownloaderId)) state.activeDownloaderId = downloaders[0].id;
    const active = downloaders.find((downloader) => downloader.id === state.activeDownloaderId) || downloaders[0];
    renderDownloaderTabs(downloaders);
    if (active.error) {
      clearDownloadPresentation();
      target.classList.add('empty');
      target.textContent = `${active.name}：${active.error}`;
      return;
    }
    if (!result.takeover_enabled) {
      clearDownloadPresentation();
      target.classList.add('empty');
      target.textContent = '尚未启用下载任务接管';
      return;
    }
    const downloads = (active.items || []).filter((item) => item.managed);
    state.activeDownloads = downloads;
    state.activeDownloader = active;
    ensureDownloadFilters();
    populateDownloadFilters(downloads);
    renderDownloadSummary(downloads);
    renderDownloadRows(downloads, active);
  } catch (error) {
    target.classList.add('empty');
    target.textContent = error.message;
  }
}

function renderDownloaderTabs(downloaders) {
  const tabs = $('#downloader-tabs');
  if (!tabs) return;
  tabs.innerHTML = downloaders.map((downloader) => `<button class="downloader-tab ${downloader.id === state.activeDownloaderId ? 'active' : ''}" type="button" data-download-tab="${escapeHtml(downloader.id)}" role="tab">${escapeHtml(downloader.name)}</button>`).join('');
}

function downloaderPayload() {
  return {
    name: $('#downloader-name').value.trim(),
    url: $('#downloader-url').value.trim(),
    username: $('#downloader-username').value.trim(),
    password: $('#downloader-password').value,
  };
}

function ensureAutoScrapeControls() {
  const form = $('#download-management-form');
  if (!form || $('#auto-scrape-rule-list')) return;
  form.querySelector('.form-actions')?.insertAdjacentHTML('beforebegin', '<section class="download-auto-scrape"><div class="download-auto-scrape-heading"><div><strong>下载完成后自动刮削</strong><p>按列表顺序匹配，命中首条启用规则后执行对应预设。</p></div><button class="button secondary" id="add-auto-scrape-rule" type="button">添加规则</button></div><div id="auto-scrape-rule-list" class="auto-scrape-rule-list"></div></section>');
}

function newAutoScrapeRule() {
  return { id: `rule-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, enabled: true, tags: '', category: '', preset_id: 'default' };
}

function normalizeAutoScrapeRules(settings) {
  if (Array.isArray(settings.auto_scrape_rules) && settings.auto_scrape_rules.length) {
    return settings.auto_scrape_rules.map((rule) => ({
      id: rule.id || newAutoScrapeRule().id,
      enabled: rule.enabled !== false,
      tags: rule.tags || '',
      category: rule.category || '',
      preset_id: rule.preset_id || 'default',
    }));
  }
  if (settings.auto_scrape_enabled) {
    return [{ id: 'legacy-default', enabled: true, tags: settings.auto_scrape_tags || '', category: settings.auto_scrape_category || '', preset_id: settings.auto_scrape_preset_id || 'default' }];
  }
  return [];
}

function autoScrapePresetOptions(selectedId) {
  return state.presets.map((preset) => `<option value="${escapeHtml(preset.id)}"${preset.id === selectedId ? ' selected' : ''}>${escapeHtml(preset.name)}</option>`).join('');
}

function renderAutoScrapeRules(rules = []) {
  const target = $('#auto-scrape-rule-list');
  if (!target) return;
  target.innerHTML = rules.length ? rules.map((rule, index) => `<article class="auto-scrape-rule" data-auto-scrape-rule="${escapeHtml(rule.id)}"><div class="auto-scrape-rule-title"><strong>规则 ${index + 1}</strong><label class="check-label"><input data-auto-rule-enabled type="checkbox"${rule.enabled ? ' checked' : ''}>启用</label></div><div class="download-auto-scrape-fields"><label>命中标签<input data-auto-rule-tags value="${escapeHtml(rule.tags || '')}" placeholder="多个标签用逗号分隔；留空匹配全部"></label><label>命中分类<input data-auto-rule-category value="${escapeHtml(rule.category || '')}" placeholder="留空匹配全部分类"></label><label>刮削预设<select data-auto-rule-preset>${autoScrapePresetOptions(rule.preset_id || 'default')}</select></label></div><button class="icon-button auto-scrape-rule-remove" type="button" data-remove-auto-scrape-rule="${escapeHtml(rule.id)}" title="删除此自动刮削规则">删除</button></article>`).join('') : '<p class="muted auto-scrape-empty">尚未添加自动刮削规则。下载完成后不会自动创建刮削任务。</p>';
}

function readAutoScrapeRules() {
  return Array.from(document.querySelectorAll('[data-auto-scrape-rule]')).map((row) => ({
    id: row.dataset.autoScrapeRule,
    enabled: row.querySelector('[data-auto-rule-enabled]').checked,
    tags: row.querySelector('[data-auto-rule-tags]').value.trim(),
    category: row.querySelector('[data-auto-rule-category]').value.trim(),
    preset_id: row.querySelector('[data-auto-rule-preset]').value || 'default',
  }));
}

function downloadManagementPayload() {
  ensureAutoScrapeControls();
  const auto_scrape_rules = readAutoScrapeRules();
  return {
    takeover_enabled: $('#download-takeover-enabled').checked,
    takeover_tags: $('#download-takeover-tags').value.trim(),
    takeover_category: $('#download-takeover-category').value.trim(),
    download_limit_kib: Number($('#download-download-limit').value),
    upload_limit_kib: Number($('#download-upload-limit').value),
    ratio_limit: Number($('#download-ratio-limit').value),
    seeding_time_limit: Number($('#download-seeding-time-limit').value),
    inactive_seeding_time_limit: Number($('#download-inactive-seeding-time-limit').value),
    auto_remove: $('#download-auto-remove').checked,
    auto_scrape_rules,
  };
}

async function loadDownloadManagement() {
  try {
    ensureAutoScrapeControls();
    const settings = await api('/api/downloads/settings');
    $('#download-takeover-enabled').checked = Boolean(settings.takeover_enabled);
    $('#download-takeover-tags').value = settings.takeover_tags || '';
    $('#download-takeover-category').value = settings.takeover_category || '';
    $('#download-download-limit').value = settings.download_limit_kib ?? -1;
    $('#download-upload-limit').value = settings.upload_limit_kib ?? -1;
    $('#download-ratio-limit').value = settings.ratio_limit ?? -1;
    $('#download-seeding-time-limit').value = settings.seeding_time_limit ?? -1;
    $('#download-inactive-seeding-time-limit').value = settings.inactive_seeding_time_limit ?? -1;
    $('#download-auto-remove').checked = Boolean(settings.auto_remove);
    state.autoScrapeRules = normalizeAutoScrapeRules(settings);
    renderAutoScrapeRules(state.autoScrapeRules);
  } catch (error) { $('#download-management-message').textContent = error.message; }
}

function editDownloader(downloader) {
  const form = $('#downloader-form');
  if (!form) return;
  $('#downloader-dialog-title').textContent = downloader?.id ? '编辑下载器' : '添加下载器';
  $('#downloader-id').value = downloader?.id || '';
  $('#downloader-name').value = downloader?.name || '';
  $('#downloader-url').value = downloader?.url || '';
  $('#downloader-username').value = downloader?.username || '';
  $('#downloader-password').value = '';
  $('#downloader-password').placeholder = downloader?.password_set ? '留空则保留已保存的密码' : '请输入 qBittorrent 密码';
  $('#delete-downloader').classList.toggle('hidden', !downloader?.id);
  $('#downloader-message').textContent = '';
  $('#downloader-dialog').showModal();
}

function renderDownloaderList() {
  const target = $('#downloader-list');
  if (!target) return;
  target.innerHTML = state.downloaders.length ? state.downloaders.map((downloader) => `<button class="downloader-item" type="button" data-downloader-edit="${escapeHtml(downloader.id)}"><strong>${escapeHtml(downloader.name)}</strong><span>${escapeHtml(downloader.url)}</span></button>`).join('') : '<div class="task-list empty">还没有下载器</div>';
}

async function loadDownloaders(selectId = null) {
  try {
    state.downloaders = await api('/api/downloaders');
    renderDownloaderList();
  } catch (error) { console.error(error); }
}

function presetName(presetId) {
  return state.presets.find((preset) => preset.id === presetId)?.name || presetId || '默认配置';
}

function renderAutoScrapeSchedules() {
  const target = $('#auto-scrape-schedule-list');
  if (!target) return;
  const schedules = state.autoScrapeSchedules;
  target.classList.toggle('empty', !schedules.length);
  target.innerHTML = schedules.length ? schedules.map((schedule) => `<article class="auto-scrape-schedule-row"><div class="auto-scrape-schedule-main"><div class="auto-scrape-schedule-title"><strong>${escapeHtml(schedule.name)}</strong><span class="badge ${schedule.enabled ? 'running' : ''}">${schedule.enabled ? '已启用' : '已停用'}</span></div><dl><div><dt>Cron</dt><dd><code>${escapeHtml(schedule.cron)}</code></dd></div><div><dt>文件夹</dt><dd>${escapeHtml(schedule.input_directory)}</dd></div><div><dt>预设</dt><dd>${escapeHtml(presetName(schedule.preset_id))}</dd></div><div><dt>下次执行</dt><dd>${escapeHtml(schedule.next_run_at ? schedule.next_run_at.replace('T', ' ') : '无法计算')}</dd></div></dl><p class="muted">最近结果：${escapeHtml(schedule.last_result || '尚未执行')}</p></div><div class="auto-scrape-schedule-actions"><button class="icon-button" type="button" data-edit-auto-scrape-schedule="${escapeHtml(schedule.id)}">编辑</button><button class="icon-button schedule-delete" type="button" data-delete-auto-scrape-schedule="${escapeHtml(schedule.id)}">删除</button></div></article>`).join('') : '<div class="task-list empty">还没有定时自动刮削规则</div>';
}

async function loadAutoScrapeSchedules() {
  const target = $('#auto-scrape-schedule-list');
  if (!target) return;
  try {
    state.autoScrapeSchedules = await api('/api/auto-scrape-schedules');
    renderAutoScrapeSchedules();
    renderAutoScrapeRunButtons();
    if ($('#auto-scrape-run-dialog')?.open && state.activeAutoScrapeRun) await refreshAutoScrapeRun();
    if ($('#auto-scrape-run-dialog')?.open && state.activeAutoScrapeHistory) renderAutoScrapeHistory(state.activeAutoScrapeHistory);
  } catch (error) {
    target.classList.add('empty');
    target.textContent = error.message;
  }
}

function renderAutoScrapeRunButtons() {
  const rows = Array.from(document.querySelectorAll('.auto-scrape-schedule-row'));
  state.autoScrapeSchedules.forEach((schedule, index) => {
    if (!rows[index]) return;
    const actionArea = rows[index].querySelector('.auto-scrape-schedule-actions');
    if (!actionArea) return;
    actionArea.insertAdjacentHTML('afterbegin', `<button class="button secondary schedule-run-now" type="button" data-run-auto-scrape-schedule="${escapeHtml(schedule.id)}">立即运行</button>`);
    const runCount = Array.isArray(schedule.runs) ? schedule.runs.length : 0;
    if (runCount) actionArea.insertAdjacentHTML('afterbegin', `<button class="icon-button" type="button" data-view-auto-scrape-history="${escapeHtml(schedule.id)}">运行记录 (${runCount})</button>`);
  });
}

function scheduleRunTaskMarkup(task) {
  const labels = { queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' };
  const logKey = `schedule-${task.id}`;
  const expanded = state.taskOpen?.[logKey] ?? task.status === 'running';
  const lines = (task.log_tail || []).join('\n');
  const log = lines ? `<details class="task-raw-log" data-task-details="${escapeHtml(logKey)}"><summary>查看日志 (${task.log_tail.length} 行)</summary><div class="task-log-wrap"><pre class="task-log" data-task-log="${escapeHtml(logKey)}">${escapeHtml(lines)}</pre><button class="copy-log" type="button" data-copy-task="${escapeHtml(logKey)}">复制日志</button></div></details>` : '<p class="muted">任务尚未输出日志。</p>';
  const stopButton = task.status === 'running' ? `<button class="button secondary task-stop" type="button" onclick="cancelTask('${escapeHtml(task.id)}')">中止任务</button>` : '';
  return `<article class="task-card task-card-collapsible schedule-run-task" data-task-card="${escapeHtml(logKey)}"><div class="task-card-head"><div class="task-card-title"><strong>${escapeHtml(taskDisplayName(task))}</strong><div class="task-meta"><span>预设：${escapeHtml(task.preset_name || task.preset_id || '默认配置')}</span><span>时间：${new Date(task.created_at).toLocaleString()}</span></div><div class="task-path">路径：${escapeHtml(task.input_directory)}</div><div class="task-image-summary">${escapeHtml(imageProgressSummary(task))}</div></div><div class="task-card-tools"><span class="badge ${task.status}">${labels[task.status] || task.status}</span>${stopButton}<button class="task-toggle" type="button" data-task-toggle="${escapeHtml(logKey)}" aria-expanded="${expanded}" title="${expanded ? '收起任务' : '展开任务'}">${expanded ? '-' : '+'}</button></div></div><div class="task-card-body${expanded ? '' : ' hidden'}" data-task-body="${escapeHtml(logKey)}">${progressMarkup(task)}${task.error ? `<div class="form-error">${escapeHtml(task.error)}</div>` : ''}${log}</div></article>`;
}

async function refreshAutoScrapeRun() {
  const active = state.activeAutoScrapeRun;
  const dialog = $('#auto-scrape-run-dialog');
  if (!active || !dialog?.open) return;
  const schedule = state.autoScrapeSchedules.find((item) => item.id === active.scheduleId);
  const run = schedule?.runs?.find((item) => item.id === active.runId);
  if (!schedule || !run) return;
  const dialogScroll = dialog.scrollTop;
  const pageScroll = window.scrollY;
  rememberLogScroll();
  rememberTaskCards();
  $('#auto-scrape-run-title').textContent = `${schedule.name} - 任务日志`;
  $('#auto-scrape-run-subtitle').textContent = `${run.started_at ? run.started_at.replace('T', ' ') : ''} · ${run.result || '正在读取任务'}`;
  const results = await Promise.all(run.task_ids.map((taskId) => api(`/api/tasks/${encodeURIComponent(taskId)}`).catch(() => null)));
  if (!dialog.open || state.activeAutoScrapeRun?.runId !== active.runId) return;
  const taskById = new Map(results.filter(Boolean).map((task) => [String(task.id), task]));
  const tasks = run.task_ids.map(String).map((taskId) => taskById.get(taskId)).filter(Boolean).sort((left, right) => {
    const byCreatedAt = Date.parse(left.created_at || '') - Date.parse(right.created_at || '');
    return Number.isFinite(byCreatedAt) && byCreatedAt !== 0 ? byCreatedAt : String(left.id).localeCompare(String(right.id));
  });
  syncTaskExpansion(tasks);
  $('#auto-scrape-run-content').innerHTML = tasks.length ? tasks.map(scheduleRunTaskMarkup).join('') : '<p class="muted">相关任务已被删除，无法查看日志。</p>';
  restoreLogScroll();
  window.requestAnimationFrame(() => {
    dialog.scrollTop = dialogScroll;
    window.scrollTo({ top: pageScroll });
  });
}

async function openAutoScrapeRun(scheduleId, runId) {
  state.activeAutoScrapeHistory = null;
  state.activeAutoScrapeRun = { scheduleId, runId };
  $('#auto-scrape-run-content').innerHTML = '<p class="muted">正在读取任务日志…</p>';
  $('#auto-scrape-run-dialog').showModal();
  await refreshAutoScrapeRun();
}

function autoScrapeRunCounts(run) {
  const taskIds = Array.isArray(run.task_ids) ? run.task_ids.map(String) : [];
  const taskById = new Map(state.tasks.map((task) => [String(task.id), task]));
  const counts = { total: taskIds.length, succeeded: 0, failed: 0, running: 0, queued: 0 };
  taskIds.forEach((taskId) => {
    const status = taskById.get(taskId)?.status;
    if (status === 'succeeded') counts.succeeded += 1;
    else if (status === 'failed' || status === 'cancelled') counts.failed += 1;
    else if (status === 'running') counts.running += 1;
    else if (status === 'queued') counts.queued += 1;
  });
  return counts;
}

function autoScrapeRunCountsMarkup(run) {
  const counts = autoScrapeRunCounts(run);
  if (!counts.total) return '<span class="muted">没有创建任务</span>';
  return `<div class="auto-scrape-run-counts" aria-label="任务统计"><span class="run-total">已创建 ${counts.total} 个任务</span><span class="run-success">已完成 ${counts.succeeded}</span><span class="run-failed">失败 ${counts.failed}</span><span class="run-running">运行中 ${counts.running}</span><span class="run-queued">排队中 ${counts.queued}</span></div>`;
}

function renderAutoScrapeHistory(scheduleId) {
  const schedule = state.autoScrapeSchedules.find((item) => item.id === scheduleId);
  if (!schedule) return;
  const runs = Array.isArray(schedule.runs) ? schedule.runs.slice().sort((left, right) => Date.parse(right.started_at || '') - Date.parse(left.started_at || '')) : [];
  $('#auto-scrape-run-title').textContent = `${schedule.name} - 全部运行记录`;
  $('#auto-scrape-run-subtitle').textContent = `已保存 ${runs.length} 次定时或立即运行记录`;
  $('#auto-scrape-run-content').innerHTML = runs.length ? `<div class="auto-scrape-history-list">${runs.map((run) => `<article class="auto-scrape-history-row"><div><strong>${escapeHtml(formatLocalDateTime(run.started_at) || run.id)}</strong><p class="muted">${escapeHtml(run.result || '正在创建任务')}</p>${autoScrapeRunCountsMarkup(run)}</div>${run.task_ids?.length ? `<button class="icon-button" type="button" data-view-auto-scrape-run="${escapeHtml(schedule.id)}" data-auto-scrape-run-id="${escapeHtml(run.id)}">查看任务日志 (${run.task_ids.length})</button>` : '<span class="muted">没有可查看的任务</span>'}</article>`).join('')}</div>` : '<p class="muted">尚未运行此规则。</p>';
}

function openAutoScrapeHistory(scheduleId) {
  const schedule = state.autoScrapeSchedules.find((item) => item.id === scheduleId);
  if (!schedule) return;
  state.activeAutoScrapeRun = null;
  state.activeAutoScrapeHistory = scheduleId;
  renderAutoScrapeHistory(scheduleId);
  $('#auto-scrape-run-dialog').showModal();
}

$('#auto-scrape-run-dialog')?.addEventListener('close', () => { state.activeAutoScrapeRun = null; state.activeAutoScrapeHistory = null; });

function renderAutoScrapeSchedulePresets(selectedId = 'default') {
  const select = $('#auto-scrape-schedule-preset');
  if (!select) return;
  select.innerHTML = state.presets.map((preset) => `<option value="${escapeHtml(preset.id)}"${preset.id === selectedId ? ' selected' : ''}>${escapeHtml(preset.name)}</option>`).join('');
}

function editAutoScrapeSchedule(schedule = null) {
  $('#auto-scrape-schedule-dialog-title').textContent = schedule ? '编辑定时规则' : '添加定时规则';
  $('#auto-scrape-schedule-id').value = schedule?.id || '';
  $('#auto-scrape-schedule-name').value = schedule?.name || '';
  $('#auto-scrape-schedule-cron').value = schedule?.cron || '0 2 * * *';
  $('#auto-scrape-schedule-directory').value = schedule?.input_directory || '';
  $('#auto-scrape-schedule-enabled').checked = schedule?.enabled !== false;
  $('#auto-scrape-schedule-message').textContent = '';
  renderAutoScrapeSchedulePresets(schedule?.preset_id || 'default');
  $('#delete-auto-scrape-schedule').classList.toggle('hidden', !schedule);
  $('.native-schedule-path-button').classList.toggle('hidden', Boolean(state.runtime?.docker));
  $('#docker-schedule-path-browser')?.classList.toggle('hidden', !state.runtime?.docker);
  $('#auto-scrape-schedule-dialog').showModal();
}

function autoScrapeSchedulePayload() {
  return {
    name: $('#auto-scrape-schedule-name').value.trim(),
    enabled: $('#auto-scrape-schedule-enabled').checked,
    cron: $('#auto-scrape-schedule-cron').value.trim(),
    input_directory: $('#auto-scrape-schedule-directory').value.trim(),
    preset_id: $('#auto-scrape-schedule-preset').value || 'default',
  };
}

function showView(view) {
  document.documentElement.removeAttribute('data-initial-view');
  document.querySelectorAll('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
  document.querySelectorAll('.view').forEach((panel) => panel.classList.toggle('active', panel.dataset.panel === view));
  const title = { overview: '概览', scrape: '手动刮削', 'auto-scrape': '自动刮削', downloads: '下载管理', 'crawler-config': '爬虫配置', presets: '刮削预设', settings: '系统设置' }[view] || '概览';
  $('#section-title').textContent = title;
  $('#section-eyebrow').textContent = view === 'settings' || view === 'presets' || view === 'crawler-config' ? '配置' : '工作区';
  if (view === 'overview') renderOverview();
  if (view === 'scrape') { renderTasks(); loadPresets(); }
  if (view === 'auto-scrape') { loadPresets(); loadAutoScrapeSchedules(); }
  if (view === 'downloads') { loadDownloadManagement(); loadDownloads(); }
  if (view === 'presets') loadPresets();
  if (view === 'settings') { ensureMediaSettingsUi(); ensurePathMappingsUi(); loadUsers(); loadDownloaders(); loadMediaServers(); loadPathMappings(); }
  localStorage.setItem('javsp-web.active-view', view);
}

function ensurePathMappingsUi() {
  const settingsPanel = document.querySelector('[data-panel="settings"]');
  if (!settingsPanel || $('#path-mapping-panel')) return;
  const anchor = $('#media-server-panel');
  const markup = '<div id="path-mapping-panel" class="panel narrow"><div class="panel-heading"><div><h2>路径映射</h2><p class="muted">将 qBittorrent 的保存路径转换为 JavSP WEB 当前环境可访问的路径，用于下载完成后自动刮削。</p></div><button class="button secondary" id="add-path-mapping" type="button">添加映射</button></div><form id="path-mappings-form" class="stack"><div id="path-mapping-list" class="path-mapping-list"></div><div class="form-actions"><button class="button primary" type="submit">保存路径映射</button><span id="path-mapping-message" class="muted"></span></div></form></div>';
  if (anchor) anchor.insertAdjacentHTML('afterend', markup); else settingsPanel.insertAdjacentHTML('afterbegin', markup);
}

function renderPathMappings() {
  const target = $('#path-mapping-list');
  if (!target) return;
  target.innerHTML = state.pathMappings.length ? state.pathMappings.map((mapping) => `<div class="path-mapping-row" data-path-mapping="${escapeHtml(mapping.id || '')}"><label>qB 保存路径<input data-path-source value="${escapeHtml(mapping.source_path || '')}" placeholder="例如：/downloads"></label><label>JavSP WEB 路径<input data-path-target value="${escapeHtml(mapping.target_path || '')}" placeholder="例如：/video"></label><button class="icon-button" type="button" data-remove-path-mapping title="移除映射">删除</button></div>`).join('') : '<p class="muted">还没有路径映射。容器部署时通常需要添加 qB 下载目录到容器挂载目录的映射。</p>';
}

async function loadPathMappings() {
  ensurePathMappingsUi();
  try { state.pathMappings = (await api('/api/path-mappings')).mappings || []; renderPathMappings(); } catch (error) { $('#path-mapping-message').textContent = error.message; }
}

function ensureMediaSettingsUi() {
  const settingsPanel = document.querySelector('[data-panel="settings"]');
  if (!settingsPanel) return;
  if (!$('#media-server-panel')) {
    settingsPanel.insertAdjacentHTML('afterbegin', '<div id="media-server-panel" class="panel narrow"><div class="panel-heading"><div><h2>媒体服务器</h2><p class="muted">连接 Emby 或 Jellyfin，可手动同步媒体库，并在刮削完成后自动扫描。</p></div><button class="button primary" id="add-media-server" type="button">添加媒体服务器</button></div><div id="media-server-list" class="media-server-list"></div></div>');
  }
  if (!$('#media-server-dialog')) {
    document.body.insertAdjacentHTML('beforeend', '<dialog id="media-server-dialog" class="app-dialog"><form method="dialog" id="media-server-form" class="dialog-form"><div class="dialog-heading"><h2 id="media-server-dialog-title">添加媒体服务器</h2><button class="dialog-close" type="button" data-dialog-close>关闭</button></div><input id="media-server-id" type="hidden"><div class="dialog-content"><label>名称<input id="media-server-name" maxlength="80" required></label><label>类型<select id="media-server-type"><option value="emby">Emby</option><option value="jellyfin">Jellyfin</option></select></label><label>服务地址<input id="media-server-url" type="url" placeholder="http://127.0.0.1:8096" required></label><label>外部播放地址<input id="media-server-external-url" type="url" placeholder="https://media.example.com"></label><label>API 密钥<input id="media-server-api-key" type="password" autocomplete="new-password" placeholder="留空则保留已保存密钥"></label><label class="check-label"><input id="media-server-auto-scan" type="checkbox">刮削任务完成后自动扫描媒体库</label></div><span id="media-server-message" class="form-error dialog-message"></span><div class="dialog-actions"><button class="button secondary" id="sync-media-server" type="button">同步媒体库</button><button class="button danger" id="delete-media-server" type="button">删除</button><button class="button secondary" type="button" data-dialog-close>取消</button><button class="button primary" value="default">保存</button></div></form></dialog>');
  }
  const mediaContent = $('#media-server-dialog')?.querySelector('.dialog-content');
  if (mediaContent && !$('#probe-media-server')) mediaContent.insertAdjacentHTML('beforeend', '<button class="button secondary" id="probe-media-server" type="button">验证并读取媒体库</button><fieldset class="media-library-fieldset"><legend>管理的媒体库</legend><div id="media-server-libraries" class="media-library-options"><span class="muted">验证连接后选择要管理的媒体库</span></div></fieldset><label>自动扫描延迟（秒）<input id="media-server-auto-scan-delay" type="number" min="0" max="86400" step="1" value="0"></label>');
}

function renderMediaServers() {
  const target = $('#media-server-list');
  if (!target) return;
  target.innerHTML = state.mediaServers.length ? state.mediaServers.map((server) => `<article class="media-server-row"><div><strong>${escapeHtml(server.name)}</strong><span>${server.type === 'jellyfin' ? 'Jellyfin' : 'Emby'} · ${escapeHtml(server.url)}</span><span>${server.api_key_set ? 'API 密钥已配置' : '未配置 API 密钥'}${server.auto_scan ? ' · 完成后自动扫描' : ''}</span></div><div class="media-server-actions"><button class="icon-button" type="button" data-edit-media-server="${escapeHtml(server.id)}">编辑</button><button class="icon-button" type="button" data-sync-media-server="${escapeHtml(server.id)}">同步媒体库</button></div></article>`).join('') : '<div class="task-list empty">还没有媒体服务器</div>';
}

async function loadMediaServers() {
  ensureMediaSettingsUi();
  try { state.mediaServers = await api('/api/media-servers'); renderMediaServers(); } catch (error) { const target = $('#media-server-list'); if (target) target.innerHTML = `<p class="form-error">${escapeHtml(error.message)}</p>`; }
}

function editMediaServer(server) {
  ensureMediaSettingsUi();
  server = server || {};
  $('#media-server-dialog-title').textContent = server.id ? '编辑媒体服务器' : '添加媒体服务器';
  $('#media-server-id').value = server.id || '';
  $('#media-server-name').value = server.name || 'Emby';
  $('#media-server-type').value = server.type || 'emby';
  $('#media-server-url').value = server.url || '';
  $('#media-server-external-url').value = server.external_url || '';
  $('#media-server-api-key').value = '';
  $('#media-server-auto-scan').checked = Boolean(server.auto_scan);
  $('#media-server-auto-scan-delay').value = server.auto_scan_delay || 0;
  renderMediaLibraryOptions(server.available_libraries || [], server.libraries || []);
  $('#media-server-message').textContent = '';
  $('#delete-media-server').hidden = !server.id;
  $('#sync-media-server').hidden = !server.id;
  $('#media-server-dialog').showModal();
  if (server.id) probeMediaLibraries(false);
}

document.addEventListener('change', (event) => {
  if (event.target.id !== 'media-server-type' || $('#media-server-id')?.value) return;
  $('#media-server-name').value = event.target.value === 'jellyfin' ? 'Jellyfin' : 'Emby';
});

function mediaServerPayload() {
  return { server_id: $('#media-server-id').value || null, name: $('#media-server-name').value.trim(), type: $('#media-server-type').value, url: $('#media-server-url').value.trim(), external_url: $('#media-server-external-url').value.trim(), api_key: $('#media-server-api-key').value, auto_scan: $('#media-server-auto-scan').checked, auto_scan_delay: Number($('#media-server-auto-scan-delay').value) || 0, libraries: selectedMediaLibraryIds() };
}

function selectedMediaLibraryIds() {
  const inputs = Array.from(document.querySelectorAll('#media-server-libraries [data-media-library]'));
  if (inputs.length) return inputs.filter((input) => input.checked).map((input) => input.value);
  try { return JSON.parse($('#media-server-libraries')?.dataset.selectedLibraries || '[]'); } catch (_) { return []; }
}

function renderMediaLibraryOptions(libraries, selected = []) {
  const target = $('#media-server-libraries');
  if (!target) return;
  const selectedIds = new Set(selected);
  target.dataset.selectedLibraries = JSON.stringify([...selectedIds]);
  target.innerHTML = libraries.length
    ? libraries.map((library) => `<label class="media-library-option"><input type="checkbox" data-media-library value="${escapeHtml(library.id)}"${selectedIds.has(library.id) ? ' checked' : ''}><span>${escapeHtml(library.name)}</span></label>`).join('')
    : '<span class="muted">验证连接后选择要管理的媒体库</span>';
}

async function probeMediaLibraries(showMessage = true) {
  const button = $('#probe-media-server');
  const message = $('#media-server-message');
  const original = button?.textContent || '验证并读取媒体库';
  const payload = mediaServerPayload();
  if (!payload.name || !payload.url) {
    if (showMessage && message) message.textContent = !payload.name ? '请填写媒体服务器名称' : '请填写服务地址';
    return;
  }
  if (button) { button.disabled = true; button.textContent = '正在验证…'; }
  if (showMessage && message) message.textContent = '正在连接媒体服务器并读取媒体库…';
  try {
    const result = await api('/api/media-servers/libraries', { method: 'POST', body: JSON.stringify(payload) });
    renderMediaLibraryOptions(result.libraries || [], selectedMediaLibraryIds());
    if (showMessage && message) message.textContent = `连接成功，读取到 ${(result.libraries || []).length} 个媒体库`;
  } catch (error) {
    if (showMessage && message) message.textContent = error.message;
  } finally {
    if (button) { button.disabled = false; button.textContent = original; }
  }
}

document.addEventListener('click', async (event) => {
  if (event.target.closest('#save-crawler-config')) { await saveCrawlerConfig(); return; }
  const closeButton = event.target.closest('[data-dialog-close]');
  if (closeButton) {
    closeButton.closest('dialog')?.close();
    return;
  }
  const viewAutoScrapeHistoryButton = event.target.closest('[data-view-auto-scrape-history]');
  if (viewAutoScrapeHistoryButton) openAutoScrapeHistory(viewAutoScrapeHistoryButton.dataset.viewAutoScrapeHistory);
  const runAutoScrapeScheduleButton = event.target.closest('[data-run-auto-scrape-schedule]');
  if (runAutoScrapeScheduleButton) {
    const scheduleId = runAutoScrapeScheduleButton.dataset.runAutoScrapeSchedule;
    const original = runAutoScrapeScheduleButton.textContent;
    runAutoScrapeScheduleButton.disabled = true;
    runAutoScrapeScheduleButton.textContent = '正在创建任务';
    api(`/api/auto-scrape-schedules/${encodeURIComponent(scheduleId)}/run`, { method: 'POST' }).then(async (result) => {
      await Promise.all([loadAutoScrapeSchedules(), loadTasks()]);
      return result;
    }).catch((error) => {
      runAutoScrapeScheduleButton.disabled = false;
      runAutoScrapeScheduleButton.textContent = error.message;
      window.setTimeout(() => { runAutoScrapeScheduleButton.textContent = original; }, 2200);
    });
  }
  const viewAutoScrapeRunButton = event.target.closest('[data-view-auto-scrape-run]');
  if (viewAutoScrapeRunButton) {
    openAutoScrapeRun(viewAutoScrapeRunButton.dataset.viewAutoScrapeRun, viewAutoScrapeRunButton.dataset.autoScrapeRunId).catch((error) => {
      const target = $('#auto-scrape-run-content');
      if (target) target.innerHTML = `<p class="form-error">${escapeHtml(error.message)}</p>`;
    });
  }
  const editAutoScrapeScheduleButton = event.target.closest('[data-edit-auto-scrape-schedule]');
  if (editAutoScrapeScheduleButton) {
    editAutoScrapeSchedule(state.autoScrapeSchedules.find((schedule) => schedule.id === editAutoScrapeScheduleButton.dataset.editAutoScrapeSchedule));
  }
  const deleteAutoScrapeScheduleButton = event.target.closest('[data-delete-auto-scrape-schedule]');
  if (deleteAutoScrapeScheduleButton) {
    const id = deleteAutoScrapeScheduleButton.dataset.deleteAutoScrapeSchedule;
    const schedule = state.autoScrapeSchedules.find((item) => item.id === id);
    confirmAction({
      title: '删除定时规则',
      text: `确定删除定时自动刮削规则“${schedule?.name || id}”吗？`,
      confirmLabel: '确认删除',
      danger: true,
      run: async () => {
        await api(`/api/auto-scrape-schedules/${encodeURIComponent(id)}`, { method: 'DELETE' });
        await loadAutoScrapeSchedules();
      },
    });
  }
  const addAutoScrapeRule = event.target.closest('#add-auto-scrape-rule');
  if (addAutoScrapeRule) {
    state.autoScrapeRules = [...readAutoScrapeRules(), newAutoScrapeRule()];
    renderAutoScrapeRules(state.autoScrapeRules);
  }
  const removeAutoScrapeRule = event.target.closest('[data-remove-auto-scrape-rule]');
  if (removeAutoScrapeRule) {
    state.autoScrapeRules = readAutoScrapeRules().filter((rule) => rule.id !== removeAutoScrapeRule.dataset.removeAutoScrapeRule);
    renderAutoScrapeRules(state.autoScrapeRules);
  }
  const addPathMapping = event.target.closest('#add-path-mapping');
  if (addPathMapping) {
    state.pathMappings.push({ id: `new-${Date.now()}`, source_path: '', target_path: '' });
    renderPathMappings();
  }
  const removePathMapping = event.target.closest('[data-remove-path-mapping]');
  if (removePathMapping) {
    const row = removePathMapping.closest('[data-path-mapping]');
    state.pathMappings = state.pathMappings.filter((mapping) => mapping.id !== row?.dataset.pathMapping);
    renderPathMappings();
  }
  const addMedia = event.target.closest('#add-media-server');
  if (addMedia) editMediaServer(null);
  const probeMedia = event.target.closest('#probe-media-server');
  if (probeMedia) {
    event.preventDefault();
    probeMediaLibraries(true);
    return;
  }
  const editMedia = event.target.closest('[data-edit-media-server]');
  if (editMedia) editMediaServer(state.mediaServers.find((server) => server.id === editMedia.dataset.editMediaServer));
  const syncMedia = event.target.closest('[data-sync-media-server]');
  if (syncMedia) {
    syncMedia.disabled = true;
    api(`/api/media-servers/${encodeURIComponent(syncMedia.dataset.syncMediaServer)}/sync`, { method: 'POST' }).then((result) => { syncMedia.textContent = result.message || '已同步'; setTimeout(() => { syncMedia.textContent = '同步媒体库'; syncMedia.disabled = false; }, 1600); }).catch((error) => { syncMedia.textContent = error.message; setTimeout(() => { syncMedia.textContent = '同步媒体库'; syncMedia.disabled = false; }, 2200); });
  }
  const toggle = event.target.closest('[data-task-toggle]');
  if (toggle) {
    const body = document.querySelector(`[data-task-body="${toggle.dataset.taskToggle}"]`);
    if (!body) return;
    const expanded = body.classList.toggle('hidden');
    state.taskOpen ||= {};
    state.taskOpen[toggle.dataset.taskToggle] = !expanded;
    toggle.textContent = expanded ? '+' : '-';
    toggle.setAttribute('aria-expanded', String(!expanded));
    toggle.title = expanded ? '展开任务' : '收起任务';
  }
  const detail = event.target.closest('[data-task-detail]');
  if (detail) openTaskDetail(detail.dataset.taskDetail);
  const retryImages = event.target.closest('[data-retry-task-images]');
  if (retryImages) {
    retryImages.disabled = true;
    retryImages.textContent = '正在重新下载封面与剧照';
    api(`/api/tasks/${encodeURIComponent(retryImages.dataset.retryTaskImages)}/images/retry`, { method: 'POST' }).then(async () => {
      state.taskOpen ||= {};
      state.taskOpen[retryImages.dataset.retryTaskImages] = true;
      await loadTasks();
      $('#task-detail-dialog')?.close();
      showView('scrape');
      showToast('已开始重新下载封面与剧照，正在显示任务日志');
    }).catch((error) => {
      retryImages.disabled = false;
      retryImages.textContent = error.message;
    });
  }
  const googleCover = event.target.closest('[data-google-cover-task]');
  if (googleCover) {
    googleCover.disabled = true;
    googleCover.textContent = '正在搜索封面';
    const taskId = googleCover.dataset.googleCoverTask;
    api(`/api/tasks/${encodeURIComponent(taskId)}/cover/google-search`, { method: 'POST' }).then(async () => {
      let result;
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        result = await api(`/api/tasks/${encodeURIComponent(taskId)}/cover/google-candidates`);
        if (!result.status || !['queued', 'running'].includes(result.status)) break;
      }
      const candidates = result?.candidates || [];
      const dialog = $('#google-cover-dialog');
      $('#google-cover-message').textContent = candidates.length ? '' : (result?.error || '未找到可用图片');
      $('#google-cover-candidates').innerHTML = candidates.map((candidate) => `<button class="google-cover-option" type="button" data-google-cover-select="${escapeHtml(taskId)}" data-candidate-id="${escapeHtml(candidate.id)}"><img src="${escapeHtml(candidate.thumbnail_url || candidate.image_url)}" loading="lazy" alt="候选封面"><span>选择此封面</span></button>`).join('');
      if (candidates.length && dialog && !dialog.open) dialog.showModal();
      await loadTasks();
    }).catch((error) => {
      googleCover.disabled = false;
      googleCover.textContent = error.message;
    });
  }
  const coverOption = event.target.closest('[data-google-cover-select]');
  if (coverOption) {
    coverOption.disabled = true;
    try {
      await api(`/api/tasks/${encodeURIComponent(coverOption.dataset.googleCoverSelect)}/cover/google-select`, { method: 'POST', body: JSON.stringify({ candidate_id: coverOption.dataset.candidateId }) });
      $('#google-cover-dialog')?.close();
      await loadTasks();
    } catch (error) { coverOption.disabled = false; $('#google-cover-message').textContent = error.message; }
  }
  const crawlerAdd = event.target.closest('.crawler-add-button');
  if (crawlerAdd) {
    const group = crawlerAdd.closest('.crawler-config-group');
    const select = group?.querySelector('.crawler-add-select');
    if (select?.value) { const row = document.createElement('div'); row.className = 'crawler-config-row'; row.innerHTML = `<select class="crawler-selection" data-group="${group.dataset.crawlerGroup}">${CRAWLER_IDS.map((id) => `<option value="${id}"${id === select.value ? ' selected' : ''}>${id}</option>`).join('')}</select><button class="button secondary crawler-move" type="button" data-direction="up">上移</button><button class="button secondary crawler-move" type="button" data-direction="down">下移</button><button class="button danger crawler-remove" type="button">删除</button>`; group.querySelector('.crawler-config-list').append(row); select.value = ''; }
  }
  const crawlerRemove = event.target.closest('.crawler-remove');
  if (crawlerRemove) { crawlerRemove.closest('.crawler-config-row')?.remove(); }
  const crawlerMove = event.target.closest('.crawler-move');
  if (crawlerMove) { const row = crawlerMove.closest('.crawler-config-row'); const list = row?.parentElement; if (row && list) { const sibling = crawlerMove.dataset.direction === 'up' ? row.previousElementSibling : row.nextElementSibling; if (sibling) crawlerMove.dataset.direction === 'up' ? list.insertBefore(row, sibling) : list.insertBefore(sibling, row); } }
  const restoreFiles = event.target.closest('[data-restore-task-files]');
  if (restoreFiles) {
    const task = state.tasks.find((item) => item.id === restoreFiles.dataset.restoreTaskFiles);
    confirmAction({
      title: '还原原始文件',
      text: `将把“${taskDisplayName(task || {})}”移回原始位置，并删除本次刮削生成的 NFO、封面与剧照。此操作不可撤销。`,
      confirmLabel: '确认还原',
      danger: true,
      run: async () => {
        await api(`/api/tasks/${encodeURIComponent(restoreFiles.dataset.restoreTaskFiles)}/restore`, { method: 'POST' });
        $('#task-detail-dialog')?.close();
        await loadTasks();
        showToast('已还原原始文件并移除刮削产物');
      },
    });
  }
  const downloadTab = event.target.closest('[data-download-tab]');
  if (downloadTab) {
    state.activeDownloaderId = downloadTab.dataset.downloadTab;
    loadDownloads();
  }
  const downloadSort = event.target.closest('[data-download-sort]');
  if (downloadSort) {
    const key = downloadSort.dataset.downloadSort;
    state.downloadSort = state.downloadSort?.key === key ? { key, direction: state.downloadSort.direction === 'asc' ? 'desc' : 'asc' } : { key, direction: ['name', 'tags', 'state', 'category'].includes(key) ? 'asc' : 'desc' };
    renderDownloadRows(state.activeDownloads || [], state.activeDownloader || {});
  }
  const downloaderEdit = event.target.closest('[data-downloader-edit]');
  if (downloaderEdit) editDownloader(state.downloaders.find((downloader) => downloader.id === downloaderEdit.dataset.downloaderEdit));
  const removeDownload = event.target.closest('[data-remove-download]');
  if (removeDownload) {
    const { downloaderId, removeDownload: torrentHash } = removeDownload.dataset;
    confirmAction({
      title: '删除下载任务',
      text: '确定删除该 qBittorrent 种子记录并保留文件吗？',
      confirmLabel: '确认删除',
      danger: true,
      run: async () => {
        await api(`/api/downloads/${encodeURIComponent(downloaderId)}/${encodeURIComponent(torrentHash)}`, { method: 'DELETE' });
        await loadDownloads();
      },
    });
  }
});

$('#refresh-downloads').addEventListener('click', loadDownloads);
$('#download-management-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = $('#download-management-message');
  try {
    const payload = downloadManagementPayload();
    const saved = await api('/api/downloads/settings', { method: 'PUT', body: JSON.stringify(payload) });
    state.autoScrapeRules = normalizeAutoScrapeRules(saved);
    renderAutoScrapeRules(state.autoScrapeRules);
    message.textContent = '全局接管与做种策略已保存';
    await loadDownloads();
  } catch (error) { message.textContent = error.message; }
});
$('#add-downloader').addEventListener('click', () => editDownloader(null));
$('#add-auto-scrape-schedule').addEventListener('click', async () => {
  await loadPresets();
  editAutoScrapeSchedule();
});
['#close-auto-scrape-schedule', '#cancel-auto-scrape-schedule'].forEach((selector) => {
  $(selector)?.addEventListener('click', () => $('#auto-scrape-schedule-dialog').close());
});
$('.native-schedule-path-button').addEventListener('click', async () => {
  const message = $('#auto-scrape-schedule-message');
  try {
    const selected = await api('/api/path/select', { method: 'POST', body: JSON.stringify({ kind: 'directory' }) });
    if (selected.path) $('#auto-scrape-schedule-directory').value = selected.path;
  } catch (error) { message.textContent = error.message; }
});
$('#auto-scrape-schedule-form').addEventListener('submit', async (event) => {
  if (event.submitter?.value !== 'default') return;
  event.preventDefault();
  const id = $('#auto-scrape-schedule-id').value;
  const message = $('#auto-scrape-schedule-message');
  try {
    const saved = await api(id ? `/api/auto-scrape-schedules/${encodeURIComponent(id)}` : '/api/auto-scrape-schedules', { method: id ? 'PUT' : 'POST', body: JSON.stringify(autoScrapeSchedulePayload()) });
    state.autoScrapeSchedules = id ? state.autoScrapeSchedules.map((schedule) => schedule.id === id ? saved : schedule) : [...state.autoScrapeSchedules, saved];
    renderAutoScrapeSchedules();
    renderAutoScrapeRunButtons();
    $('#auto-scrape-schedule-dialog').close();
  } catch (error) { message.textContent = error.message; }
});
$('#delete-auto-scrape-schedule').addEventListener('click', () => {
  const id = $('#auto-scrape-schedule-id').value;
  if (!id) return;
  const schedule = state.autoScrapeSchedules.find((item) => item.id === id);
  $('#auto-scrape-schedule-dialog').close();
  confirmAction({
    title: '删除定时规则',
    text: `确定删除定时自动刮削规则“${schedule?.name || id}”吗？`,
    confirmLabel: '确认删除',
    danger: true,
    run: async () => {
      await api(`/api/auto-scrape-schedules/${encodeURIComponent(id)}`, { method: 'DELETE' });
      await loadAutoScrapeSchedules();
    },
  });
});
$('#downloader-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = $('#downloader-message');
  const downloaderId = $('#downloader-id').value;
  try {
    const result = await api(downloaderId ? `/api/downloaders/${encodeURIComponent(downloaderId)}` : '/api/downloaders', { method: downloaderId ? 'PUT' : 'POST', body: JSON.stringify(downloaderPayload()) });
    message.textContent = '下载器已保存';
    await loadDownloaders(result.id);
    $('#downloader-dialog').close();
  } catch (error) { message.textContent = error.message; }
});
$('#test-downloader').addEventListener('click', async () => {
  const message = $('#downloader-message');
  const downloaderId = $('#downloader-id').value;
  try {
    const result = await api(downloaderId ? `/api/downloaders/${encodeURIComponent(downloaderId)}/test` : '/api/downloaders/test', { method: 'POST', body: JSON.stringify(downloaderPayload()) });
    message.textContent = `连接成功，qBittorrent ${result.version}`;
  } catch (error) { message.textContent = error.message; }
});
$('#delete-downloader').addEventListener('click', () => {
  const downloaderId = $('#downloader-id').value;
  if (!downloaderId) return;
  confirmAction({
    title: '删除下载器',
    text: '确定删除该下载器连接吗？',
    confirmLabel: '确认删除',
    danger: true,
    run: async () => {
      await api(`/api/downloaders/${encodeURIComponent(downloaderId)}`, { method: 'DELETE' });
      $('#downloader-dialog').close();
      await loadDownloaders();
    },
  });
});

ensureMediaSettingsUi();

document.addEventListener('submit', async (event) => {
  if (event.target.id === 'path-mappings-form') {
    event.preventDefault();
    const message = $('#path-mapping-message');
    const mappings = Array.from(document.querySelectorAll('[data-path-mapping]')).map((row) => ({ source_path: row.querySelector('[data-path-source]').value.trim(), target_path: row.querySelector('[data-path-target]').value.trim() }));
    if (mappings.some((mapping) => !mapping.source_path || !mapping.target_path)) { message.textContent = '请完整填写每条路径映射'; return; }
    try {
      state.pathMappings = (await api('/api/path-mappings', { method: 'PUT', body: JSON.stringify({ mappings }) })).mappings || [];
      renderPathMappings();
      message.textContent = '路径映射已保存';
    } catch (error) { message.textContent = error.message; }
    return;
  }
  if (event.target.id !== 'media-server-form') return;
  event.preventDefault();
  const id = $('#media-server-id').value;
  const message = $('#media-server-message');
  try {
    const result = await api(id ? `/api/media-servers/${encodeURIComponent(id)}` : '/api/media-servers', { method: id ? 'PUT' : 'POST', body: JSON.stringify(mediaServerPayload()) });
    state.mediaServers = id ? state.mediaServers.map((server) => server.id === id ? result : server) : [...state.mediaServers, result];
    renderMediaServers();
    $('#media-server-dialog').close();
  } catch (error) { message.textContent = error.message; }
});

document.addEventListener('click', (event) => {
  const syncButton = event.target.closest('#media-server-dialog #sync-media-server');
  if (!syncButton) return;
  const id = $('#media-server-id').value;
  if (!id) return;
  const message = $('#media-server-message');
  const original = syncButton.textContent;
  syncButton.disabled = true;
  syncButton.textContent = '正在同步…';
  api(`/api/media-servers/${encodeURIComponent(id)}/sync`, { method: 'POST' }).then((result) => { message.textContent = result.message || '媒体库扫描已启动'; }).catch((error) => { message.textContent = error.message; }).finally(() => { syncButton.disabled = false; syncButton.textContent = original; });
});

document.addEventListener('click', (event) => {
  const deleteButton = event.target.closest('#media-server-dialog #delete-media-server');
  if (!deleteButton) return;
  const id = $('#media-server-id').value;
  if (!id) return;
  const server = state.mediaServers.find((item) => item.id === id);
  $('#media-server-dialog').close();
  confirmAction({ title: '删除媒体服务器', text: `确定删除媒体服务器“${server?.name || id}”吗？`, confirmLabel: '确认删除', danger: true, run: async () => { await api(`/api/media-servers/${encodeURIComponent(id)}`, { method: 'DELETE' }); await loadMediaServers(); } });
});

function setSidebarCollapsed(collapsed) {
  const shell = document.querySelector('.app-shell');
  const toggle = $('#sidebar-toggle');
  if (!shell || !toggle) return;
  shell.classList.toggle('sidebar-collapsed', collapsed);
  toggle.title = collapsed ? '展开侧边栏' : '收起侧边栏';
  toggle.setAttribute('aria-label', toggle.title);
  toggle.querySelector('span').textContent = collapsed ? '>' : '<';
  localStorage.setItem('javsp-web.sidebar-collapsed', collapsed ? '1' : '0');
}

const sidebarToggle = $('#sidebar-toggle');
if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => setSidebarCollapsed(!document.querySelector('.app-shell').classList.contains('sidebar-collapsed')));
  setSidebarCollapsed(localStorage.getItem('javsp-web.sidebar-collapsed') === '1');
}

const downloadPolicyToggle = $('#download-policy-toggle');
const downloadPolicyContent = $('#download-policy-content');
if (downloadPolicyToggle && downloadPolicyContent) {
  const setDownloadPolicyExpanded = (expanded) => {
    downloadPolicyContent.classList.toggle('hidden', !expanded);
    downloadPolicyToggle.textContent = expanded ? '收起策略' : '展开策略';
    downloadPolicyToggle.setAttribute('aria-expanded', String(expanded));
    localStorage.setItem('javsp-web.download-policy-open', expanded ? '1' : '0');
  };
  setDownloadPolicyExpanded(localStorage.getItem('javsp-web.download-policy-open') === '1');
  downloadPolicyToggle.addEventListener('click', () => setDownloadPolicyExpanded(downloadPolicyContent.classList.contains('hidden')));
}

(async () => {
  try {
    const savedView = localStorage.getItem('javsp-web.active-view');
    if (savedView && document.querySelector(`[data-panel="${savedView}"]`)) showView(savedView);
    state.user = await api('/api/auth/me');
    $('#current-user').textContent = state.user.username;
    if (state.user.role !== 'admin') { $('#settings-nav').remove(); $('#auto-scrape-nav').remove(); $('#crawler-config-nav').remove(); }
    await Promise.all([loadTasks(), loadPresets(), loadPathTools()]);
    if (savedView && document.querySelector(`[data-panel="${savedView}"]`) && (state.user.role === 'admin' || (savedView !== 'settings' && savedView !== 'auto-scrape'))) showView(savedView);
  } catch (error) { return; }
  setInterval(() => {
    loadTasks();
    if (document.querySelector('[data-panel="downloads"]')?.classList.contains('active')) loadDownloads();
    if (document.querySelector('[data-panel="auto-scrape"]')?.classList.contains('active')) loadAutoScrapeSchedules();
  }, 5000);
})();

function formatLocalDateTime(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : '';
}

$('#task-detail-dialog')?.addEventListener('close', () => { state.activeTaskDetail = null; });
