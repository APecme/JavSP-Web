const state = { user: null, tasks: [], presets: [], downloaders: [], mediaServers: [], pathMappings: [], autoScrapeRules: [], autoScrapeSchedules: [], downloadAutoScrapeRuns: [], crawlerSources: [], disabledBuiltInCrawlers: [], activeCrawlerCodeName: '', runtime: null, activeAutoScrapeRun: null, activeAutoScrapeHistory: null, activeDownloadAutoScrapeRun: null, activeTaskDetail: null, taskDetailLogSelecting: false, taskMetadataEditing: false, pendingMetadataRefresh: null, overviewSort: { key: 'created_at', direction: 'desc' }, overviewSelectionMode: false, overviewSelectionFeedback: new Set(), activeDownloaderId: null, activeDownloads: [], activeDownloader: null, downloadSort: { key: 'added_on', direction: 'desc' }, editingPreset: null, editingUser: null, pendingDeleteTask: null, pendingConfirm: null, selectedOverviewTasks: new Set(), pathBrowser: { kind: 'directory', target: 'manual', currentPath: '/' }, formValues: {}, presetMode: null, logScroll: {}, logOpen: {}, taskOpen: {}, taskStatus: {}, googleCoverDialogTaskId: null, googleCoverDialogDismissed: false };
const $ = (selector) => document.querySelector(selector);
const FORM_SECTIONS = ['scanner', 'network', 'crawler', 'summarizer', 'translator', 'other'];
const CRAWLER_GROUPS = { normal: '普通影片', fc2: 'FC2', cid: 'CID', getchu: 'Getchu', gyutto: 'Gyutto' };
const CRAWLER_IDS = ['airav','avsox','avwiki','dl_getchu','fanza','fc2','fc2fan','fc2ppvdb','gyutto','jav321','javbus','javdb','javlib','javmenu','mgstage','njav','prestige','arzon','arzon_iv'];
const REQUIRED_MOVIE_FIELDS = [
  ['dvdid', '\u756a\u53f7'], ['cid', 'CID'], ['url', 'URL'], ['plot', '\u5267\u60c5'],
  ['cover', '\u5c01\u9762'], ['big_cover', '\u9ad8\u6e05\u5c01\u9762'], ['genre', '\u7c7b\u578b'], ['score', '\u8bc4\u5206'],
  ['title', '\u6807\u9898'], ['ori_title', '\u539f\u59cb\u6807\u9898'], ['magnet', '\u4e0b\u8f7d\u94fe\u63a5'], ['serial', '\u7cfb\u5217'],
  ['actress', '\u6f14\u5458'], ['director', '\u5bfc\u6f14'], ['duration', '\u65f6\u957f'], ['producer', '\u5236\u4f5c\u5546'],
  ['publisher', '\u53d1\u884c\u5546'], ['publish_date', '\u53d1\u884c\u65e5\u671f'], ['preview_pics', '\u5267\u7167'], ['preview_video', '\u9884\u544a\u7247'],
];
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
  ignored_id_pattern: '输入后点击加号添加；每个标签是一条正则表达式。',
  filename_extensions: '输入后点击加号添加；每个标签是一个文件扩展名。',
  ignored_folder_name_pattern: '输入后点击加号添加；每个标签是一条目录过滤正则。',
  proxy_server: '留空或输入 null 表示不使用代理。',
  proxy_free: '站点地址对象，可按 YAML 格式填写。',
  selection: '按影片类型选择爬虫列表，可直接输入 YAML 对象。',
  required_keys: '勾选影片成功抓取时必须取得的字段。',
  engine: '引擎配置可输入 null 或 YAML 对象。',
  path: '路径相关配置对象，可按 YAML 格式填写。',
  nfo: 'NFO 文件生成配置对象。',
  cover: '封面和裁剪配置对象。',
  crop: '封面裁剪配置对象。',
  extra_fanarts: '剧照下载配置对象。',
  fields: '需要翻译的字段开关。',
};
const FIELD_DESCRIPTIONS = {
  'summarizer.cover.google_search_fallback': '启用后，封面下载失败时仅使用 Google 图片搜索查找候选封面，并使用预设中的代理。',
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

function configArrayTagMarkup(value) {
  return `<span class="config-array-tag" data-array-value="${escapeHtml(value)}"><code>${escapeHtml(value)}</code><button class="config-array-remove" type="button" title="\u5220\u9664 ${escapeHtml(value)}" aria-label="\u5220\u9664 ${escapeHtml(value)}">\u00d7</button></span>`;
}

function arrayConfigMarkup(path, values) {
  const items = Array.isArray(values) ? values.map((value) => String(value).trim()).filter(Boolean) : [];
  return `<div class="config-array" data-config-path="${escapeHtml(path)}"><div class="config-array-list">${items.map(configArrayTagMarkup).join('')}</div><div class="config-array-add"><input class="config-array-input" type="text" maxlength="256" autocomplete="off" placeholder="\u8f93\u5165\u503c"><button class="icon-button config-array-add-button" type="button" title="\u6dfb\u52a0" aria-label="\u6dfb\u52a0">+</button></div></div>`;
}

function requiredKeysMarkup(values) {
  const selected = new Set(Array.isArray(values) ? values.map(String) : []);
  const fields = REQUIRED_MOVIE_FIELDS.map(([name, label]) => `<label class="required-key-option"><input type="checkbox" data-required-key value="${name}"${selected.has(name) ? ' checked' : ''}><span>${escapeHtml(label)}</span><code>${name}</code></label>`).join('');
  return `<fieldset class="required-key-list" data-config-path="crawler.required_keys">${fields}</fieldset>`;
}

function hydrateCollectionControls() {
  document.querySelectorAll('textarea.config-field-input[data-config-path]').forEach((control) => {
    let values;
    try { values = JSON.parse(control.value); } catch (_) { return; }
    if (!Array.isArray(values)) return;
    const path = control.dataset.configPath;
    control.outerHTML = path === 'crawler.required_keys' ? requiredKeysMarkup(values) : arrayConfigMarkup(path, values);
  });
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
    const paths = [];
    const walk = (value, path) => {
      if (!pathMatchesTab(path, tab.prefixes)) return;
      if (tab.section === 'scanner' && path === 'input_directory') return;
      if (tab.section === 'translator' && path === 'engine') {
        paths.push([path, value]);
      } else if (tab.section === 'crawler' && path === 'selection') {
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
      const control = sourcePath === 'crawler.selection' ? crawlerConfigMarkup(value) : (sourcePath === 'translator.engine' ? translatorEngineControl(value) : (boolean ? `<select class="config-field-input" data-config-path="${sourcePath}"><option value="true"${value ? ' selected' : ''}>是</option><option value="false"${value ? '' : ' selected'}>否</option></select>` : (complex ? `<textarea class="config-field-input" data-config-path="${sourcePath}" spellcheck="false">${escapeHtml(inputValue)}</textarea>` : `<input class="config-field-input" data-config-path="${sourcePath}" value="${escapeHtml(inputValue)}"${placeholder ? ` placeholder="${escapeHtml(placeholder)}"` : ''}>`)));
      const description = fieldDescription(sourcePath, value);
      const note = fieldNote(sourcePath, value);
      const outputDirectoryPicker = sourcePath === 'summarizer.path.output_folder_pattern'
        ? `<button class="button secondary config-directory-picker" type="button" data-select-output-directory="${sourcePath}">选择路径</button>`
        : '';
      const ruleControl = isNamingRulePath(sourcePath) ? `<div class="naming-rule-control">${control}${outputDirectoryPicker}${namingRuleHelp(sourcePath)}</div>` : control;
      const heading = `<span class="config-field-name">${escapeHtml(fieldLabel(sourcePath))} <small>(${escapeHtml(sourcePath)})</small></span>`;
      const help = `${description ? `<small class="config-description">说明：${escapeHtml(description)}</small>` : ''}${note ? `<em>备注：${escapeHtml(note)}</em>` : ''}`;
      if (sourcePath === 'network.proxy_server') {
        return `<div class="config-field proxy-test-field">${heading}${ruleControl}${help}<div class="form-actions"><button class="button secondary" type="button" id="test-preset-proxy">测试连通性</button><span id="preset-proxy-test-message" class="form-message"></span></div><div id="preset-proxy-test-result" class="proxy-test-result hidden"></div></div>`;
      }
      return `<label class="config-field">${heading}${ruleControl}${help}</label>`;
    }).join('') || '<p class="muted">此分类暂无可编辑项。</p>';
    if (tab.id === 'scanner') {
      container.insertAdjacentHTML('beforeend', `<label class="config-field web-config-field"><span class="config-field-name">多线程刮削 <small>(JavSP WEB)</small></span><input id="preset-task-concurrency" type="number" min="1" max="32" value="${Math.max(1, Math.min(32, Number(state.taskConcurrency) || 1))}"><small class="config-description">手动刮削目录内有多个影片时，同时运行的任务数量；超出的任务会保留在队列中等待。</small></label>`);
    }
  });
  hydrateCollectionControls();
}

renderPresetNavigation();

function readConfigFields() {
  const values = cloneValue(state.formValues || {});
  document.querySelectorAll('.config-field-input').forEach((control) => {
    if (!control.dataset.configPath) return;
    const [section, ...path] = control.dataset.configPath.split('.');
    setPathValue(values, `${section}.${path.join('.')}`, control.value);
  });
  document.querySelectorAll('.config-array[data-config-path]').forEach((control) => {
    const items = [...control.querySelectorAll('[data-array-value]')]
      .map((tag) => String(tag.dataset.arrayValue || '').trim())
      .filter(Boolean);
    setPathValue(values, control.dataset.configPath, items);
  });
  const requiredKeys = [...document.querySelectorAll('[data-required-key]:checked')].map((control) => control.value);
  if (document.querySelector('[data-config-path="crawler.required_keys"]')) {
    setPathValue(values, 'crawler.required_keys', requiredKeys);
  }
  const crawlerSelection = {};
  document.querySelectorAll('.crawler-config-group').forEach((group) => {
    const name = group.dataset.crawlerGroup;
    if (!name) return;
    crawlerSelection[name] = [...group.querySelectorAll('[data-crawler-value]')]
      .map((tag) => String(tag.dataset.crawlerValue || '').trim())
      .filter(Boolean);
  });
  if (Object.keys(crawlerSelection).length) setPathValue(values, 'crawler.selection', crawlerSelection);
  return Object.fromEntries(FORM_SECTIONS.map((section) => [section, values[section] || {}]));
}

function proxyConnectivityResultMarkup(result) {
  const route = result.proxy_configured ? '配置代理' : '直连出口';
  const exit = result.reachable ? `${escapeHtml(result.ip || '未知 IP')}，地区 ${escapeHtml(result.country || '未知')}` : '无法查询出口地区';
  const sites = (result.restricted_sites || []).join('、');
  let compatibility = '';
  if (sites) compatibility = result.japan_compatible ? `<p class="form-message">${escapeHtml(sites)} 的出口地区满足已知限制。</p>` : `<p class="form-error">${escapeHtml(sites)} 存在日本地区访问限制，当前${route}${result.reachable ? `为 ${escapeHtml(result.country || '未知')} 地区` : '无法确认地区'}。</p>`;
  const hint = result.clash_mihomo_hint ? `<details open><summary>Clash/Mihomo 覆写提示</summary><pre>${escapeHtml(result.clash_mihomo_hint)}</pre></details>` : '';
  const preflight = result.preflight_message ? `<pre class="proxy-test-preflight">${escapeHtml(result.preflight_message)}</pre>` : '';
  return `${preflight}<p><strong>${route}：</strong>${exit}</p>${compatibility}${hint}`;
}

function crawlerConfigMarkup(selection = {}) {
  return crawlerConfigTagsMarkup(selection);
  return Object.entries(CRAWLER_GROUPS).map(([group, label]) => {
    const selected = Array.isArray(selection[group]) ? selection[group] : [];
    const options = CRAWLER_IDS.filter((id) => !selected.includes(id)).map((id) => `<option value="${id}">${id}</option>`).join('');
    return `<div class="crawler-config-group" data-crawler-group="${group}"><h3>${label}爬虫</h3><div class="crawler-config-list">${selected.map((id, index) => `<div class="crawler-config-row"><select class="crawler-selection">${CRAWLER_IDS.map((option) => `<option value="${option}"${option === id ? ' selected' : ''}>${option}</option>`).join('')}</select><button class="button secondary crawler-move" type="button" data-direction="up"${index ? '' : ' disabled'}>上移</button><button class="button secondary crawler-move" type="button" data-direction="down"${index === selected.length - 1 ? ' disabled' : ''}>下移</button><button class="button danger crawler-remove" type="button">删除</button></div>`).join('')}</div><div class="crawler-add"><select class="crawler-add-select"><option value="">添加爬虫</option>${options}</select><button class="button secondary crawler-add-button" type="button">添加</button></div></div>`;
  }).join('');
}

function crawlerConfigTagsMarkup(selection = {}) {
  const disabled = new Set(state.disabledBuiltInCrawlers || []);
  const knownNames = [...new Set([
    ...CRAWLER_IDS,
    ...(state.crawlerSources || []).map((crawler) => String(crawler?.name || '')),
    ...Object.values(selection || {}).flatMap((names) => Array.isArray(names) ? names : []),
  ].filter((name) => /^[a-z][a-z0-9_]*$/.test(name) && !disabled.has(name)))].sort();
  const options = knownNames.map((name) => `<option value="${escapeHtml(name)}"></option>`).join('');
  return Object.entries(CRAWLER_GROUPS).map(([group, label]) => {
    const selected = Array.isArray(selection[group]) ? selection[group].map((name) => String(name).trim()).filter((name) => name && !disabled.has(name)) : [];
    const tags = selected.map((name) => `<span class="crawler-tag" data-crawler-value="${escapeHtml(name)}"><code>${escapeHtml(name)}</code><button class="crawler-tag-remove" type="button" title="\u5220\u9664 ${escapeHtml(name)}" aria-label="\u5220\u9664 ${escapeHtml(name)}">\u00d7</button></span>`).join('');
    return `<div class="crawler-config-group" data-crawler-group="${group}"><h3>${label}\u722c\u866b</h3><div class="crawler-config-list crawler-tag-list">${tags}</div><div class="crawler-add"><input class="crawler-add-input" list="crawler-name-options" maxlength="80" autocomplete="off" placeholder="\u8f93\u5165\u722c\u866b\u540d\u79f0"><button class="icon-button crawler-add-button" type="button" title="\u6dfb\u52a0\u722c\u866b" aria-label="\u6dfb\u52a0\u722c\u866b">+</button><datalist id="crawler-name-options">${options}</datalist></div></div>`;
  }).join('');
}

async function loadCrawlerNames() {
  try {
    const result = await api('/api/crawler-config/names');
    state.crawlerSources = result.crawlers || [];
    state.disabledBuiltInCrawlers = result.disabled_built_ins || [];
    if (state.presetMode === 'form') renderConfigFields();
  } catch (_) { /* Manual input remains available when the name list cannot load. */ }
}

async function loadCrawlerConfig() {
  const host = $('#crawler-config-content');
  if (!host) return;
  host.innerHTML = '<p class="muted">正在读取爬虫配置...</p>';
  try {
    const result = await api('/api/crawler-config');
    state.crawlerSources = result.crawlers || [];
    state.disabledBuiltInCrawlers = result.disabled_built_ins || [];
    host.innerHTML = crawlerCodeMarkup(state.crawlerSources);
    if (state.crawlerSources[0]) loadCrawlerSource(state.crawlerSources[0].name);
  } catch (error) { host.innerHTML = `<p class="form-error">${escapeHtml(error.message)}</p>`; }
}

function crawlerCodeMarkup(crawlers) {
  const items = Array.isArray(crawlers) ? crawlers : [];
  const selected = items[0] || null;
  const disabled = (state.disabledBuiltInCrawlers || []).map((name) => `<div class="crawler-code-list-row"><span class="crawler-code-item disabled"><strong>${escapeHtml(name)}</strong><span>已移除</span></span><button class="icon-button" type="button" data-restore-built-in-crawler="${escapeHtml(name)}" title="恢复 ${escapeHtml(name)}" aria-label="恢复 ${escapeHtml(name)}">恢复</button></div>`).join('');
  return `<section class="crawler-code-editor"><div class="crawler-code-heading"><div><h3>爬虫代码</h3><p class="muted">选择爬虫后再读取代码；内置爬虫可移除并随时恢复。</p></div><button class="button secondary" type="button" id="add-custom-crawler">添加爬虫</button></div><div class="crawler-code-layout"><div id="crawler-code-list" class="crawler-code-list">${items.map((item, index) => `<div class="crawler-code-list-row"><button type="button" class="crawler-code-item${index ? '' : ' active'}" data-crawler-code-name="${escapeHtml(item.name)}"><strong>${escapeHtml(item.name)}</strong><span>${item.kind === 'custom' ? '自定义' : '内置'}</span></button>${item.kind === 'custom' ? `<button class="icon-button crawler-code-list-delete" type="button" data-delete-custom-crawler="${escapeHtml(item.name)}" title="删除 ${escapeHtml(item.name)}" aria-label="删除 ${escapeHtml(item.name)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13m-7 4v5m4-5v5"/></svg></button>` : ''}</div>`).join('') || '<p class="muted">没有可用爬虫。</p>'}${disabled ? `<div class="crawler-code-disabled"><p class="muted">已移除的内置爬虫</p>${disabled}</div>` : ''}</div><div id="crawler-code-detail" class="crawler-code-detail">${selected ? crawlerCodeDetail(selected) : ''}</div></div></section>`;
}

function crawlerCodeDetail(crawler, source = null) {
  const editable = crawler.kind === 'custom';
  const actions = editable ? `<button class="button danger" type="button" data-delete-custom-crawler="${escapeHtml(crawler.name)}">删除</button>` : `<button class="button danger" type="button" data-disable-built-in-crawler="${escapeHtml(crawler.name)}">删除</button>`;
  if (source === null) return `<div class="crawler-code-detail-head"><strong>${escapeHtml(crawler.name)}</strong><span>${editable ? '自定义爬虫' : '内置爬虫（只读）'}</span>${actions}</div><p class="muted">正在读取爬虫代码...</p>`;
  return `<div class="crawler-code-detail-head"><strong>${escapeHtml(crawler.name)}</strong><span>${editable ? '自定义爬虫' : '内置爬虫（只读）'}</span>${actions}</div><label class="config-field"><span class="config-field-name">爬虫名称</span><input id="crawler-code-name" value="${escapeHtml(crawler.name)}"${editable ? '' : ' disabled'}></label><label class="config-field"><span class="config-field-name">Python 代码</span><textarea id="crawler-code-source" class="code-editor" spellcheck="false"${editable ? '' : ' readonly'}>${escapeHtml(source)}</textarea></label>${editable ? '<div class="form-actions"><button class="button primary" type="button" id="save-custom-crawler">保存爬虫代码</button><span id="crawler-code-message" class="form-message"></span></div>' : ''}<section class="crawler-test-panel"><div><h4>爬虫测试</h4><p class="muted">使用当前网络与代理配置，单独抓取一次。</p></div><label class="config-field"><span class="config-field-name">测试输入</span><input id="crawler-test-input" maxlength="256" placeholder="例如 DANDYA-044"></label><div class="form-actions"><button class="button secondary" type="button" data-test-crawler="${escapeHtml(crawler.name)}">测试爬虫</button><span id="crawler-test-message" class="form-message"></span></div><div id="crawler-test-result" class="crawler-test-result hidden"><details open><summary>抓取结果</summary><pre id="crawler-test-data" class="crawler-test-output"></pre></details><details id="crawler-test-output-wrap"><summary>运行输出</summary><pre id="crawler-test-output" class="crawler-test-output"></pre></details></div></section>`;
}

async function loadCrawlerSource(name) {
  const crawler = (state.crawlerSources || []).find((item) => item.name === name);
  const detail = $('#crawler-code-detail');
  if (!crawler || !detail) return;
  state.activeCrawlerCodeName = name;
  detail.innerHTML = crawlerCodeDetail(crawler);
  try {
    const source = await api(`/api/crawler-config/${encodeURIComponent(name)}`);
    if (state.activeCrawlerCodeName === name) detail.innerHTML = crawlerCodeDetail(source, source.source || '');
  } catch (error) {
    if (state.activeCrawlerCodeName === name) detail.innerHTML = `<p class="form-error">${escapeHtml(error.message)}</p>`;
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, { credentials: 'include', ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  if (response.status === 401) { location.href = '/login'; throw new Error('登录已过期'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(formatApiError(data.detail, response.status));
  return data;
}

async function uploadTaskCover(taskId, file) {
  const form = new FormData();
  form.append('file', file, file.name || 'cover.jpg');
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/cover/upload`, { method: 'POST', credentials: 'include', body: form });
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

function renderGoogleBrowser(taskId) {
  const target = $('#google-cover-candidates');
  if (!target) return;
  const path = encodeURIComponent(`api/tasks/${taskId}/cover/browser`);
  target.innerHTML = `<section class="google-captcha-panel"><strong>Google 要求完成验证码</strong><p class="muted">请直接在下方真实 Google 浏览器窗口中完成验证。</p><iframe class="google-browser-frame" src="/google-browser/vnc.html?autoconnect=true&resize=remote&path=${path}" title="Google 浏览器"></iframe></section>`;
}

function renderGoogleCoverLoading() {
  const target = $('#google-cover-candidates');
  if (!target) return;
  target.innerHTML = '<section class="google-cover-loading" role="status"><i></i><strong>正在查询全部已配置爬虫</strong></section>';
}

function googleImageSearchUrl(task) {
  const query = task?.progress?.metadata?.dvdid || task?.file_name || task?.name || '';
  return `https://www.google.com/search?tbm=isch&safe=off&filter=0&hl=zh-CN&q=${encodeURIComponent(query)}`;
}

function renderGoogleClientSearch(task) {
  const target = $('#google-cover-candidates');
  if (!target) return;
  const url = googleImageSearchUrl(task);
  target.innerHTML = `<section class="google-client-search"><div class="google-client-search-heading"><strong>在本机浏览器中选择封面</strong><button class="button secondary" type="button" data-open-google-client-search="${escapeHtml(url)}">打开 Google 图片</button></div><label class="google-cover-upload">上传已选封面<input type="file" accept="image/jpeg,image/png,image/webp" data-local-cover-upload="${escapeHtml(task.id)}"></label></section>`;
}

function openGoogleClientSearch(url) {
  const tab = window.open(url, '_blank');
  if (tab) tab.opener = null;
}

function renderGoogleCoverCandidates(taskId, candidates) {
  const target = $('#google-cover-candidates');
  if (!target) return;
  target.innerHTML = candidates.map((candidate) => `<button class="google-cover-option" type="button" data-google-cover-select="${escapeHtml(taskId)}" data-candidate-id="${escapeHtml(candidate.id)}"><img src="/api/tasks/${encodeURIComponent(taskId)}/cover/candidates/${encodeURIComponent(candidate.id)}/thumbnail" loading="lazy" alt="候选封面"><span>${escapeHtml(candidate.source || '搜索结果')}${candidate.width && candidate.height ? ` · ${candidate.width}×${candidate.height}` : ''}</span><small>${escapeHtml(candidate.title || '选择此封面')}</small></button>`).join('');
}

async function waitForCrawlerCoverCandidates(taskId) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    if (state.googleCoverDialogDismissed || state.googleCoverDialogTaskId !== taskId) return;
    try {
      const result = await api(`/api/tasks/${encodeURIComponent(taskId)}/cover/candidates`);
      if (result.status === 'succeeded') {
        renderGoogleCoverCandidates(taskId, result.candidates || []);
        return;
      }
      if (result.status === 'failed') {
        $('#google-cover-message').textContent = result.error || '爬虫未返回可下载封面';
        return;
      }
    } catch (error) {
      $('#google-cover-message').textContent = error.message;
      return;
    }
  }
  $('#google-cover-message').textContent = '爬虫封面搜索超时，请查看任务日志';
}

async function waitForCrawlerCoverSelection(taskId) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    const result = await api(`/api/tasks/${encodeURIComponent(taskId)}/cover/candidates`);
    if (result.status === 'selected') return;
    if (result.status === 'failed') throw new Error(result.error || '封面下载失败');
  }
  throw new Error('封面下载超时，请查看任务日志');
}

$('#google-cover-dialog')?.addEventListener('close', () => {
  state.googleCoverDialogDismissed = true;
});

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

function expandControlIcon(expanded) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${expanded ? 'm7 15 5-5 5 5' : 'm7 9 5 5 5-5'}"/></svg>`;
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

function hasTaskDetailLogSelection() {
  const selection = window.getSelection?.();
  const content = $('#task-detail-content');
  if (!selection || selection.isCollapsed || !selection.rangeCount || !content) return false;
  return content.contains(selection.anchorNode) && content.contains(selection.focusNode);
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
  const completed = state.tasks.filter((task) => ['succeeded', 'failed', 'cancelled'].includes(task.status) && ((task.cover_count || task.fanart_count) || (task.progress?.image_sources?.cover_urls?.length || task.progress?.image_sources?.preview_pics?.length))).slice(0, 24);
  const availableIds = new Set(completed.map((task) => task.id));
  state.selectedOverviewTasks = new Set([...state.selectedOverviewTasks].filter((id) => availableIds.has(id)));
  const selectedCount = state.selectedOverviewTasks.size;
  const toolbar = completed.length ? `<div class="overview-cover-toolbar"><label class="check-label"><input id="overview-select-all" type="checkbox"${selectedCount && selectedCount === completed.length ? ' checked' : ''}>选择全部</label><span class="muted">已选择 ${selectedCount} 项</span><button id="overview-delete-selected" class="button danger" type="button"${selectedCount ? '' : ' disabled'}>删除所选记录</button></div>` : '';
  $('#overview-tasks').innerHTML = completed.length ? `<div class="overview-cover-wall">${completed.map((task) => { const image = task.cover_count ? `<img src="/api/tasks/${encodeURIComponent(task.id)}/cover/0" loading="lazy" alt="${escapeHtml(task.name || '')}">` : artworkPlaceholder('overview-cover-placeholder', task.progress?.images?.cover_status === 'failed' ? '封面下载失败' : '封面未下载'); return `<figure class="overview-cover"><button class="overview-cover-delete" type="button" data-delete-task="${escapeHtml(task.id)}" title="删除任务记录" aria-label="删除任务记录">删除</button><button class="overview-cover-open" type="button" data-task-detail="${escapeHtml(task.id)}">${image}<figcaption>${escapeHtml(task.name || task.id)}</figcaption></button></figure>`; }).join('')}</div>` : '<div class="task-list empty">还没有已完成的任务</div>';
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
  try {
    rememberLogScroll();
    state.tasks = await api('/api/tasks');
    syncTaskExpansion(state.tasks);
    renderOverview();
    renderTasks();
    const detailOpen = $('#task-detail-dialog')?.open && state.activeTaskDetail;
    if (detailOpen && !state.taskMetadataEditing && !state.taskDetailLogSelecting && !hasTaskDetailLogSelection()) openTaskDetail(state.activeTaskDetail);
    window.requestAnimationFrame(restoreLogScroll);
  } catch (error) { console.error(error); }
  if ($('#auto-scrape-run-dialog')?.open && state.activeAutoScrapeHistory) renderAutoScrapeHistory(state.activeAutoScrapeHistory);
  window.requestAnimationFrame(() => window.scrollTo({ top: pageScroll }));
}

function compareReleaseVersions(left, right) {
  const parse = (value) => String(value || '').replace(/^v/i, '').match(/^(\d+)\.(\d+)\.(\d+)/);
  const leftParts = parse(left);
  const rightParts = parse(right);
  if (!leftParts || !rightParts) return null;
  for (let index = 1; index <= 3; index += 1) {
    const difference = Number(leftParts[index]) - Number(rightParts[index]);
    if (difference) return difference;
  }
  return 0;
}

async function checkForAppUpdate(runtime) {
  const tag = $('#app-version');
  if (!tag) return;
  const displayVersion = runtime.version || runtime.app_version || tag.textContent.replace(/^v/, '');
  const currentVersion = runtime.app_version || displayVersion;
  tag.textContent = `v${displayVersion}`;
  tag.dataset.updateStatus = 'checking';
  tag.title = '正在检查 GitHub Releases 更新';
  try {
    const response = await fetch('https://api.github.com/repos/APecme/JavSP-Web/releases/latest', { headers: { Accept: 'application/vnd.github+json' } });
    if (!response.ok) throw new Error(`GitHub 返回 ${response.status}`);
    const release = await response.json();
    const latestVersion = release.tag_name || '';
    const comparison = compareReleaseVersions(currentVersion, latestVersion);
    if (comparison !== null && comparison < 0) {
      tag.dataset.updateStatus = 'available';
      tag.textContent = `v${displayVersion} 可更新`;
      tag.title = `发现新版本 ${latestVersion}`;
    } else if (comparison !== null) {
      tag.dataset.updateStatus = 'current';
      tag.textContent = `v${displayVersion} 已是最新`;
      tag.title = `已是最新版本 ${latestVersion}`;
    } else {
      tag.dataset.updateStatus = 'unknown';
      tag.title = '当前部署版本无法与 GitHub Release 标签比较';
    }
  } catch (_) {
    tag.dataset.updateStatus = 'unknown';
    tag.title = '暂时无法检查 GitHub Releases 更新';
  }
}

function scheduleGitHubStarInvite() {
  const preferenceKey = 'javsp-web.github-star-invite-disabled';
  if (localStorage.getItem(preferenceKey) === '1') return;
  const delay = 60_000 + Math.floor(Math.random() * 60_001);
  const showInvite = () => {
    if (document.hidden) {
      window.setTimeout(showInvite, 10_000);
      return;
    }
    if (document.querySelector('.github-star-invite')) return;
    document.body.insertAdjacentHTML('beforeend', '<aside class="github-star-invite" role="status"><strong>喜欢 JavSP WEB 吗？</strong><p>欢迎前往 GitHub 点亮一颗 Star，帮助项目持续改进。</p><div class="github-star-invite-actions"><button class="button secondary" type="button" data-disable-github-star-invite>不再提示</button><a class="button primary" href="https://github.com/APecme/JavSP-Web" target="_blank" rel="noopener noreferrer">前往 GitHub</a></div></aside>');
    document.querySelector('[data-disable-github-star-invite]')?.addEventListener('click', () => {
      localStorage.setItem(preferenceKey, '1');
      document.querySelector('.github-star-invite')?.remove();
    });
  };
  window.setTimeout(showInvite, delay);
}

async function loadPathTools() {
  try {
    const runtime = await api('/api/runtime');
    state.runtime = runtime;
    checkForAppUpdate(runtime);
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

function deleteTaskRecords(ids) {
  const records = [...new Set(ids)].filter(Boolean);
  if (records.length <= 1) {
    deleteTaskInDialog(records[0]);
    return;
  }
  confirmAction({
    title: '删除重复任务记录',
    text: `确定删除这 ${records.length} 条合并的任务记录吗？只删除 JavSP WEB 记录，不删除视频、NFO、封面或剧照文件。`,
    confirmLabel: '删除记录',
    danger: true,
    run: async () => {
      for (const id of records) await api(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' });
      await loadTasks();
    },
  });
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
  if (event.target.id === 'overview-sort-key' || event.target.id === 'overview-sort-direction') {
    state.overviewSort = { key: $('#overview-sort-key').value, direction: $('#overview-sort-direction').value };
    renderOverview();
  }
});
document.addEventListener('change', async (event) => {
  const input = event.target.closest('[data-local-cover-upload]');
  const file = input?.files?.[0];
  if (!input || !file) return;
  input.disabled = true;
  $('#google-cover-message').textContent = '正在保存封面';
  try {
    await uploadTaskCover(input.dataset.localCoverUpload, file);
    $('#google-cover-dialog')?.close();
    await loadTasks();
    showToast('封面已保存');
  } catch (error) {
    input.disabled = false;
    $('#google-cover-message').textContent = error.message;
  }
});
document.addEventListener('contextmenu', (event) => {
  const card = event.target.closest('[data-overview-task]');
  if (!card) return;
  event.preventDefault();
  const menu = $('#overview-context-menu');
  const select = menu?.querySelector('[data-overview-context-select]');
  const remove = menu?.querySelector('[data-overview-context-delete]');
  const selecting = state.overviewSelectionMode;
  if (select) select.textContent = selecting ? '退出选择' : '选择';
  if (remove) {
    remove.textContent = selecting ? '删除所选记录' : '删除任务记录';
    remove.disabled = selecting && !state.selectedOverviewTasks.size;
  }
  menu.dataset.taskId = card.dataset.overviewTask;
  menu.dataset.taskIds = card.dataset.overviewTaskIds || card.dataset.overviewTask;
  menu.style.left = `${Math.min(event.clientX, window.innerWidth - 164)}px`;
  menu.style.top = `${Math.min(event.clientY, window.innerHeight - 88)}px`;
  menu.hidden = false;
});
document.addEventListener('click', (event) => {
  const menu = $('#overview-context-menu');
  const select = event.target.closest('[data-overview-context-select]');
  if (select && menu) {
    if (state.overviewSelectionMode) {
      state.overviewSelectionMode = false;
      state.selectedOverviewTasks.clear();
    } else {
      state.overviewSelectionMode = true;
      const ids = overviewTaskIds(menu.dataset.taskIds);
      ids.forEach((id) => {
        state.selectedOverviewTasks.add(id);
        state.overviewSelectionFeedback.add(id);
      });
    }
    menu.hidden = true;
    renderOverview();
    return;
  }
  const remove = event.target.closest('[data-overview-context-delete]');
  if (remove && menu?.dataset.taskIds) {
    if (state.overviewSelectionMode) {
      const selectedIds = [...state.selectedOverviewTasks];
      if (selectedIds.length) document.querySelector('#overview-delete-selected')?.click();
    } else {
      deleteTaskRecords(menu.dataset.taskIds.split(','));
    }
    menu.hidden = true;
    return;
  }
  if (menu && !event.target.closest('#overview-context-menu')) menu.hidden = true;
});
document.addEventListener('click', (event) => {
  if (event.target.closest('[data-edit-task-metadata]')) {
    state.taskMetadataEditing = true;
    if (state.activeTaskDetail) openTaskDetail(state.activeTaskDetail);
    return;
  }
  if (event.target.closest('[data-cancel-task-metadata]')) {
    state.taskMetadataEditing = false;
    if (state.activeTaskDetail) openTaskDetail(state.activeTaskDetail);
  }
});
document.addEventListener('change', (event) => {
  const checkbox = event.target.closest('[data-overview-select]');
  if (checkbox) {
    if (checkbox.checked) state.selectedOverviewTasks.add(checkbox.dataset.overviewSelect);
    else state.selectedOverviewTasks.delete(checkbox.dataset.overviewSelect);
    renderOverview();
    return;
  }
  if (event.target.id === 'overview-select-all') {
    const completed = state.tasks.filter((task) => ['succeeded', 'failed', 'cancelled'].includes(task.status) && ((task.cover_count || task.fanart_count) || (task.progress?.image_sources?.cover_urls?.length || task.progress?.image_sources?.preview_pics?.length))).slice(0, 24);
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
document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-save-task-metadata]');
  if (!button) return;
  const editor = button.closest('#task-metadata-editor');
  if (!editor) return;
  const actress = String(editor.querySelector('[name="actress"]')?.value || '').split(/[\n,，、]/).map((value) => value.trim()).filter(Boolean);
  const payload = {
    dvdid: String(editor.querySelector('[name="dvdid"]')?.value || '').trim(),
    title: String(editor.querySelector('[name="title"]')?.value || '').trim(),
    actress,
    director: String(editor.querySelector('[name="director"]')?.value || '').trim(),
    producer: String(editor.querySelector('[name="producer"]')?.value || '').trim(),
    publisher: String(editor.querySelector('[name="publisher"]')?.value || '').trim(),
    publish_date: String(editor.querySelector('[name="publish_date"]')?.value || '').trim(),
    apply_to_folder: Boolean(editor.querySelector('[name="apply_to_folder"]')?.checked),
  };
  button.disabled = true;
  try {
    await api(`/api/tasks/${encodeURIComponent(editor.dataset.taskId)}/metadata`, { method: 'PATCH', body: JSON.stringify(payload) });
    state.taskMetadataEditing = false;
    await loadTasks();
    showToast(payload.apply_to_folder ? '影片资料和文件夹 NFO 已保存' : '影片资料已保存');
    requestMetadataRefresh();
  } catch (error) {
    button.disabled = false;
    showToast(error.message, 'error');
  }
});
$('#metadata-refresh-form')?.addEventListener('submit', async (event) => {
  if (event.submitter?.id !== 'metadata-refresh-confirm') return;
  event.preventDefault();
  const button = $('#metadata-refresh-confirm');
  button.disabled = true;
  try {
    if ($('#metadata-refresh-always').checked) localStorage.setItem('javsp-web.metadata-refresh-always', '1');
    await refreshConfiguredMediaLibraries();
    $('#metadata-refresh-dialog').close();
  } catch (error) {
    $('#metadata-refresh-message').textContent = error.message;
  } finally {
    button.disabled = false;
  }
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
  const active = ['queued', 'running'].includes(task.status);
  const fileName = task.file_name || task.name || task.id;
  const titleMeta = task.title ? `<span>文件：${escapeHtml(fileName)}</span>` : '';
  const actions = '';
  const detailButton = `<button class="icon-button" type="button" data-task-detail="${escapeHtml(task.id)}" title="查看任务详情">详情</button>`;
  const stopButton = active ? `<button class="button secondary task-stop" type="button" onclick="cancelTask('${escapeHtml(task.id)}')">停止任务</button>` : '';
  const deleteButton = `<button class="task-delete" type="button" data-delete-task="${escapeHtml(task.id)}"${active ? ' disabled title="请先停止任务"' : ' title="删除任务"'}>删除</button>`;
  return `<article class="task-card task-card-collapsible" data-task-card="${escapeHtml(task.id)}"><div class="task-card-head"><div class="task-card-title"><strong>${escapeHtml(taskDisplayName(task))}</strong><div class="task-meta">${titleMeta}<span>预设：${escapeHtml(task.preset_name || task.preset_id || '默认配置')}</span><span>时间：${new Date(task.created_at).toLocaleString()}</span></div><div class="task-path">路径：${escapeHtml(task.input_directory)}</div><div class="task-image-summary">${escapeHtml(imageProgressSummary(task))}</div></div><div class="task-card-tools"><span class="badge ${task.status}">${labels[task.status] || task.status}</span>${detailButton}${stopButton}${deleteButton}<button class="task-toggle" type="button" data-task-toggle="${escapeHtml(task.id)}" aria-expanded="${expanded}" title="${expanded ? '收起任务' : '展开任务'}">${expandControlIcon(expanded)}</button></div></div><div class="task-card-body${expanded ? '' : ' hidden'}" data-task-body="${escapeHtml(task.id)}">${progressMarkup(task)}${task.error ? `<div class="form-error">${escapeHtml(task.error)}</div>` : ''}${actions}</div></article>`;
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

async function openTaskDetail(taskId) {
  const summary = state.tasks.find((item) => item.id === taskId);
  if (!summary) return;
  state.activeTaskDetail = taskId;
  const dialog = $('#task-detail-dialog');
  $('#task-detail-title').textContent = taskDisplayName(summary);
  $('#task-detail-subtitle').textContent = summary.file_name || summary.name || '';
  $('#task-detail-content').innerHTML = '<p class="muted">正在读取任务详情与日志...</p>';
  if (!dialog.open) dialog.showModal();
  let task;
  try {
    task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
  } catch (error) {
    if (state.activeTaskDetail === taskId) $('#task-detail-content').innerHTML = `<p class="form-error">${escapeHtml(error.message)}</p>`;
    return;
  }
  if (state.activeTaskDetail !== taskId || !dialog.open) return;
  const metadata = task.progress?.metadata || {};
  const rows = [['番号', metadata.dvdid], ['标题', metadata.title || taskDisplayName(task)], ['女优', Array.isArray(metadata.actress) ? metadata.actress.join('、') : metadata.actress], ['导演', metadata.director], ['制作商', metadata.producer], ['发行商', metadata.publisher], ['发行时间', metadata.publish_date], ['文件名', task.file_name || task.name], ['文件路径', task.input_directory || '-'], ['整理路径', task.progress?.output?.save_dir || '-']].map(([label, value]) => `<div class="detail-data-row"><dt>${label}</dt><dd>${escapeHtml(value || '-')}</dd></div>`).join('');
  const posterImage = task.cover_count ? `<img class="detail-poster" src="/api/tasks/${encodeURIComponent(task.id)}/cover/0" alt="${escapeHtml(taskDisplayName(task))}">` : artworkPlaceholder('detail-poster detail-poster-empty', task.progress?.images?.cover_status === 'failed' ? '封面下载失败' : '封面未下载');
  const poster = `<div class="detail-poster-wrap">${posterImage}</div>`;
  const actressInput = Array.isArray(metadata.actress) ? metadata.actress.join('\n') : (metadata.actress || '');
  const metadataEditor = state.taskMetadataEditing ? `<section id="task-metadata-editor" class="task-metadata-editor" data-task-id="${escapeHtml(task.id)}"><div class="task-metadata-editor-heading"><h3>修改影片资料</h3><button class="icon-button" type="button" data-cancel-task-metadata>取消</button></div><div class="task-metadata-fields"><label>番号<input name="dvdid" maxlength="160" value="${escapeHtml(metadata.dvdid || '')}"></label><label>标题<input name="title" maxlength="1000" value="${escapeHtml(metadata.title || '')}"></label><label>女优<textarea name="actress" rows="3" maxlength="3000">${escapeHtml(actressInput)}</textarea></label><label>导演<input name="director" maxlength="300" value="${escapeHtml(metadata.director || '')}"></label><label>制作商<input name="producer" maxlength="300" value="${escapeHtml(metadata.producer || '')}"></label><label>发行商<input name="publisher" maxlength="300" value="${escapeHtml(metadata.publisher || '')}"></label><label>发行时间<input name="publish_date" maxlength="32" placeholder="YYYY-MM-DD" value="${escapeHtml(metadata.publish_date || '')}"></label></div><label class="check-label task-metadata-folder"><input name="apply_to_folder" type="checkbox" checked>同步写入整理文件夹中的 NFO</label><div class="detail-image-actions"><button class="button primary" type="button" data-save-task-metadata>保存资料</button></div></section>` : `<section class="task-metadata-summary"><div class="task-metadata-summary-heading"><h3>影片资料</h3><button class="button secondary" type="button" data-edit-task-metadata>修改</button></div><div class="task-detail-main">${poster}<dl class="task-detail-data">${rows}</dl></div></section>`;
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
  const taskLogLines = (task.log_tail || []).join('\n');
  const taskLog = taskLogLines ? `<details class="task-detail-log" data-task-details="detail-${escapeHtml(task.id)}"><summary>查看任务日志（${task.log_tail.length} 行）</summary><div class="task-log-wrap"><pre class="task-log" data-task-log="detail-${escapeHtml(task.id)}">${escapeHtml(taskLogLines)}</pre><button class="copy-log" type="button" data-copy-task="detail-${escapeHtml(task.id)}">复制日志</button></div></details>` : '<p class="muted">当前任务尚未输出日志。</p>';
  const googleCover = !task.cover_count ? `<div class="google-cover-action"><button class="button secondary task-google-cover" type="button" data-google-cover-task="${escapeHtml(task.id)}">使用全部爬虫搜索封面</button></div>` : '';
  const restore = task.restore_available ? `<button class="button danger" type="button" data-restore-task-files="${escapeHtml(task.id)}">还原文件</button>` : '';
  $('#task-detail-title').textContent = taskDisplayName(task);
  $('#task-detail-subtitle').textContent = task.file_name || task.name || '';
  $('#task-detail-content').innerHTML = `${metadataEditor}<section class="detail-images"><div><h3>下载图片</h3>${imageCounts}</div><div class="detail-image-actions">${googleCover}${retry}${restore}</div></section>${taskLog}<section class="detail-fanarts"><h3>剧照 (${task.fanart_count || 0})</h3><div class="detail-fanart-grid">${fanarts}</div></section>`;
}

function cookiecloudPayload() {
  return {
    enabled: $('#cookiecloud-enabled').checked,
    server_url: $('#cookiecloud-server-url').value.trim(),
    uuid: $('#cookiecloud-uuid').value.trim(),
    crypto_type: $('#cookiecloud-crypto-type').value,
    password: $('#cookiecloud-password').value,
    clear_password: $('#cookiecloud-clear-password').checked,
  };
}

async function loadCookieCloud() {
  const message = $('#cookiecloud-message');
  try {
    const settings = await api('/api/cookiecloud');
    $('#cookiecloud-enabled').checked = Boolean(settings.enabled);
    $('#cookiecloud-server-url').value = settings.server_url || '';
    $('#cookiecloud-uuid').value = settings.uuid || '';
    $('#cookiecloud-crypto-type').value = settings.crypto_type || 'auto';
    $('#cookiecloud-password').value = '';
    $('#cookiecloud-clear-password').checked = false;
    message.textContent = settings.has_password ? '已保存密码' : '';
  } catch (error) { message.textContent = error.message; }
}

async function refreshConfiguredMediaLibraries() {
  if (state.user?.role !== 'admin') {
    showToast('当前账户无权刷新媒体库', 'error');
    return;
  }
  const servers = await api('/api/media-servers');
  state.mediaServers = servers;
  if (!servers.length) {
    showToast('没有已配置的媒体服务器');
    return;
  }
  const results = await Promise.allSettled(servers.map((server) => api(`/api/media-servers/${encodeURIComponent(server.id)}/sync`, { method: 'POST' })));
  const failed = results.filter((result) => result.status === 'rejected').length;
  showToast(failed ? `${servers.length - failed} 个媒体库已开始刷新，${failed} 个失败` : '媒体库扫描已启动', failed ? 'error' : 'success');
}

function requestMetadataRefresh() {
  if (localStorage.getItem('javsp-web.metadata-refresh-always') === '1') {
    refreshConfiguredMediaLibraries().catch((error) => showToast(error.message, 'error'));
    return;
  }
  const dialog = $('#metadata-refresh-dialog');
  $('#metadata-refresh-always').checked = false;
  $('#metadata-refresh-message').textContent = '';
  if (dialog && !dialog.open) dialog.showModal();
}

function overviewTaskIds(value) {
  return String(value || '').split(',').map((id) => id.trim()).filter(Boolean);
}

function toggleOverviewSelection(ids) {
  if (!ids.length) return;
  const selected = ids.every((id) => state.selectedOverviewTasks.has(id));
  ids.forEach((id) => {
    if (selected) state.selectedOverviewTasks.delete(id);
    else state.selectedOverviewTasks.add(id);
    state.overviewSelectionFeedback.add(id);
  });
}

function overviewSelectionIcon(selected = false) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"></rect>${selected ? '<path d="m8 12 2.7 2.7L16.5 9"></path>' : ''}</svg>`;
}

function renderOverview() {
  $('#metric-total').textContent = state.tasks.length;
  $('#metric-running').textContent = state.tasks.filter((task) => task.status === 'running' || task.status === 'queued').length;
  const latest = state.tasks[0];
  $('#metric-result').textContent = latest ? ({ succeeded: '成功', failed: '失败', running: '运行中', queued: '排队中' }[latest.status] || latest.status) : '-';
  const completed = state.tasks.filter((task) => ['succeeded', 'failed', 'cancelled'].includes(task.status) && ((task.cover_count || task.fanart_count) || task.has_artwork_sources));
  const groups = new Map();
  completed.forEach((task) => {
    const outputPath = String(task.progress?.output?.save_dir || '').trim();
    const identity = outputPath ? `output:${outputPath.toLowerCase()}` : `input:${String(task.input_directory || task.id).toLowerCase()}`;
    const group = groups.get(identity) || [];
    group.push(task);
    groups.set(identity, group);
  });
  const cards = [...groups.values()].map((items) => {
    const ordered = items.slice().sort((left, right) => {
      const status = Number(right.status === 'succeeded') - Number(left.status === 'succeeded');
      return status || Date.parse(right.created_at || '') - Date.parse(left.created_at || '');
    });
    return { task: ordered[0], taskCount: items.length, taskIds: items.map((item) => item.id) };
  }).sort((left, right) => {
    const key = state.overviewSort.key;
    const value = (entry) => key === 'publish_date' ? Date.parse(entry.task.progress?.metadata?.publish_date || '') || 0 : Date.parse(entry.task.created_at || '') || 0;
    const difference = value(left) - value(right);
    return state.overviewSort.direction === 'asc' ? difference : -difference;
  }).slice(0, 24);
  const visibleIds = new Set(cards.flatMap((entry) => entry.taskIds));
  state.selectedOverviewTasks = new Set([...state.selectedOverviewTasks].filter((id) => visibleIds.has(id)));
  const allSelected = visibleIds.size > 0 && [...visibleIds].every((id) => state.selectedOverviewTasks.has(id));
  const selectionTools = `<div class="overview-selection-tools"><button class="icon-button" type="button" data-overview-select-all title="${allSelected ? '取消全选' : '全选'}" aria-label="${allSelected ? '取消全选' : '全选'}">${overviewSelectionIcon(allSelected)}</button><button id="overview-delete-selected" class="icon-button overview-selection-delete" type="button" title="删除所选记录" aria-label="删除所选记录"${state.selectedOverviewTasks.size ? '' : ' disabled'}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13m-7 4v5m4-5v5"/></svg></button></div>`;
  const toolbar = `<div class="overview-cover-toolbar">${selectionTools}<label>排序<select id="overview-sort-key"><option value="created_at"${state.overviewSort.key === 'created_at' ? ' selected' : ''}>刮削时间</option><option value="publish_date"${state.overviewSort.key === 'publish_date' ? ' selected' : ''}>发行时间</option></select></label><label>顺序<select id="overview-sort-direction"><option value="desc"${state.overviewSort.direction === 'desc' ? ' selected' : ''}>由近到远</option><option value="asc"${state.overviewSort.direction === 'asc' ? ' selected' : ''}>由远到近</option></select></label></div>`;
  $('#overview-tasks').innerHTML = cards.length ? `${toolbar}<div class="overview-cover-wall">${cards.map(({ task, taskCount, taskIds }) => overviewCoverCard(task, taskCount, taskIds)).join('')}</div>` : '<div class="task-list empty">还没有已完成的任务</div>';
  if (state.overviewSelectionFeedback.size) window.setTimeout(() => state.overviewSelectionFeedback.clear(), 260);
}

function overviewCoverCard(task, taskCount = 1, taskIds = [task.id]) {
  const images = task.progress?.images || {};
  const coverReady = Number(task.cover_count) > 0;
  const total = Number(images.fanart_total) || Number(task.fanart_count) || 0;
  const fanart = Math.min(Number(task.fanart_count) || 0, total || Number(task.fanart_count) || 0);
  const coverState = coverReady ? '封面已下载' : (images.failed ? '封面下载失败' : '封面未生成');
  const artwork = coverReady
    ? `<img src="/api/tasks/${encodeURIComponent(task.id)}/cover/0" loading="lazy" alt="${escapeHtml(taskDisplayName(task))}">`
    : artworkPlaceholder('overview-cover-placeholder', images.cover_status === 'failed' ? '封面下载失败' : '封面未下载');
  const selected = taskIds.every((id) => state.selectedOverviewTasks.has(id));
  const selector = state.overviewSelectionMode ? `<button class="overview-cover-select${selected ? ' selected' : ''}" type="button" data-overview-select-ids="${escapeHtml(taskIds.join(','))}" aria-pressed="${selected}" title="${selected ? '取消选择' : '选择记录'}" aria-label="${selected ? '取消选择' : '选择记录'}">${overviewSelectionIcon(selected)}</button>` : '';
  const feedback = taskIds.some((id) => state.overviewSelectionFeedback.has(id));
  return `<article class="overview-cover-card${selected ? ' selected' : ''}${state.overviewSelectionMode ? ' selecting' : ''}${feedback ? ' selection-feedback' : ''}" data-overview-task="${escapeHtml(task.id)}" data-overview-task-ids="${escapeHtml(taskIds.join(','))}">${selector}<button class="overview-cover" type="button" data-task-detail="${escapeHtml(task.id)}">${artwork}<span>${escapeHtml(taskDisplayName(task))}</span>${taskCount > 1 ? `<small>合并 ${taskCount} 条记录</small>` : ''}</button></article>`;
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
    await loadDownloadAutoScrapeRuns();
    if ($('#auto-scrape-run-dialog')?.open && state.activeAutoScrapeRun) await refreshAutoScrapeRun();
    if ($('#auto-scrape-run-dialog')?.open && state.activeAutoScrapeHistory) renderAutoScrapeHistory(state.activeAutoScrapeHistory);
  } catch (error) {
    target.classList.add('empty');
    target.textContent = error.message;
  }
}

function renderDownloadAutoScrapeRuns() {
  const target = $('#download-auto-scrape-run-list');
  if (!target) return;
  const runs = state.downloadAutoScrapeRuns || [];
  target.classList.toggle('empty', !runs.length);
  target.innerHTML = runs.length ? runs.map((run) => `<article class="auto-scrape-history-row"><div><strong>${escapeHtml(run.download_name || run.path || '下载任务')}</strong><p class="muted">${escapeHtml(run.downloader_name || '下载器')} · ${escapeHtml(formatLocalDateTime(run.created_at) || '')}</p><p class="muted">${escapeHtml(run.path || run.download_path || '')}</p>${autoScrapeRunCountsMarkup(run)}</div><div class="auto-scrape-history-actions"><button class="icon-button" type="button" data-view-download-auto-scrape-run="${escapeHtml(run.id || '')}">查看任务日志 (${Array.isArray(run.task_ids) ? run.task_ids.length : 0})</button></div></article>`).join('') : '<div class="task-list empty">下载完成后创建的刮削任务会显示在这里。</div>';
}

async function loadDownloadAutoScrapeRuns() {
  const target = $('#download-auto-scrape-run-list');
  if (!target) return;
  try {
    state.downloadAutoScrapeRuns = await api('/api/download-auto-scrape-runs');
    renderDownloadAutoScrapeRuns();
    if ($('#auto-scrape-run-dialog')?.open && state.activeDownloadAutoScrapeRun) await refreshDownloadAutoScrapeRun();
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
  return `<article class="task-card task-card-collapsible schedule-run-task" data-task-card="${escapeHtml(logKey)}"><div class="task-card-head"><div class="task-card-title"><strong>${escapeHtml(taskDisplayName(task))}</strong><div class="task-meta"><span>预设：${escapeHtml(task.preset_name || task.preset_id || '默认配置')}</span><span>时间：${new Date(task.created_at).toLocaleString()}</span></div><div class="task-path">路径：${escapeHtml(task.input_directory)}</div><div class="task-image-summary">${escapeHtml(imageProgressSummary(task))}</div></div><div class="task-card-tools"><span class="badge ${task.status}">${labels[task.status] || task.status}</span>${stopButton}<button class="task-toggle" type="button" data-task-toggle="${escapeHtml(logKey)}" aria-expanded="${expanded}" title="${expanded ? '收起任务' : '展开任务'}">${expandControlIcon(expanded)}</button></div></div><div class="task-card-body${expanded ? '' : ' hidden'}" data-task-body="${escapeHtml(logKey)}">${progressMarkup(task)}${task.error ? `<div class="form-error">${escapeHtml(task.error)}</div>` : ''}${log}</div></article>`;
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
  const results = await Promise.all(run.task_ids.map(String).map((taskId) => api(`/api/tasks/${encodeURIComponent(taskId)}`).catch(() => null)));
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
  state.activeDownloadAutoScrapeRun = null;
  state.activeAutoScrapeHistory = null;
  state.activeAutoScrapeRun = { scheduleId, runId };
  $('#auto-scrape-run-content').innerHTML = '';
  $('#auto-scrape-run-dialog').showModal();
  await refreshAutoScrapeRun();
}

async function refreshDownloadAutoScrapeRun() {
  const runId = state.activeDownloadAutoScrapeRun;
  const dialog = $('#auto-scrape-run-dialog');
  const run = state.downloadAutoScrapeRuns.find((item) => item.id === runId);
  if (!run || !dialog?.open) return;
  const taskIds = Array.isArray(run.task_ids) ? run.task_ids.map(String) : [];
  const fetched = await Promise.all(taskIds.map((taskId) => api(`/api/tasks/${encodeURIComponent(taskId)}`).catch(() => null)));
  if (!dialog.open || state.activeDownloadAutoScrapeRun !== runId) return;
  const tasks = taskIds.map((taskId) => fetched.find((task) => String(task?.id) === taskId)).filter(Boolean);
  syncTaskExpansion(tasks);
  $('#auto-scrape-run-title').textContent = `${run.download_name || '下载任务'} - 任务日志`;
  $('#auto-scrape-run-subtitle').textContent = `${run.downloader_name || '下载器'} · ${formatLocalDateTime(run.created_at) || ''}`;
  $('#auto-scrape-run-content').innerHTML = tasks.length ? tasks.map(scheduleRunTaskMarkup).join('') : '<p class="muted">关联任务已删除，无法查看日志。</p>';
}

async function openDownloadAutoScrapeRun(runId) {
  state.activeAutoScrapeRun = null;
  state.activeAutoScrapeHistory = null;
  state.activeDownloadAutoScrapeRun = runId;
  $('#auto-scrape-run-content').innerHTML = '';
  $('#auto-scrape-run-dialog').showModal();
  await refreshDownloadAutoScrapeRun();
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
  $('#auto-scrape-run-content').innerHTML = runs.length ? `<div class="auto-scrape-history-list">${runs.map((run) => `<article class="auto-scrape-history-row"><div><strong>${escapeHtml(formatLocalDateTime(run.started_at) || run.id)}</strong><p class="muted">${escapeHtml(run.result || '正在创建任务')}</p>${autoScrapeRunCountsMarkup(run)}</div><div class="auto-scrape-history-actions">${run.task_ids?.length ? `<button class="icon-button" type="button" data-view-auto-scrape-run="${escapeHtml(schedule.id)}" data-auto-scrape-run-id="${escapeHtml(run.id)}">查看任务日志 (${run.task_ids.length})</button>` : '<span class="muted">没有可查看的任务</span>'}<button class="icon-button schedule-delete" type="button" data-delete-auto-scrape-run="${escapeHtml(schedule.id)}" data-auto-scrape-run-id="${escapeHtml(run.id)}">删除日志</button></div></article>`).join('')}</div>` : '<p class="muted">尚未运行此规则。</p>';
}

function openAutoScrapeHistory(scheduleId) {
  state.activeDownloadAutoScrapeRun = null;
  const schedule = state.autoScrapeSchedules.find((item) => item.id === scheduleId);
  if (!schedule) return;
  state.activeAutoScrapeRun = null;
  state.activeAutoScrapeHistory = scheduleId;
  renderAutoScrapeHistory(scheduleId);
  $('#auto-scrape-run-dialog').showModal();
}

$('#auto-scrape-run-dialog')?.addEventListener('close', () => { state.activeAutoScrapeRun = null; state.activeAutoScrapeHistory = null; state.activeDownloadAutoScrapeRun = null; });

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
  if (view === 'crawler-config') loadCrawlerConfig();
  if (view === 'presets') loadPresets();
  if (view === 'settings') { ensureMediaSettingsUi(); ensurePathMappingsUi(); loadUsers(); loadDownloaders(); loadMediaServers(); loadPathMappings(); loadCookieCloud(); }
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
  const testPresetProxy = event.target.closest('#test-preset-proxy');
  if (testPresetProxy) {
    const message = $('#preset-proxy-test-message');
    const result = $('#preset-proxy-test-result');
    const values = readConfigFields();
    const original = testPresetProxy.textContent;
    testPresetProxy.disabled = true;
    testPresetProxy.textContent = '正在测试';
    if (message) { message.textContent = ''; message.classList.remove('form-error'); }
    if (result) result.classList.add('hidden');
    try {
      const response = await api('/api/presets/network/proxy-test', {
        method: 'POST',
        body: JSON.stringify({
          proxy_server: values.network?.proxy_server || '',
          crawler_selection: values.crawler?.selection || state.formValues?.crawler?.selection || {},
          preset_id: state.editingPreset || 'default',
          timeout: values.network?.timeout || '',
        }),
      });
      if (message) message.textContent = response.reachable ? '连通性测试完成' : '测试完成，但未能查询出口地区';
      if (result) { result.innerHTML = proxyConnectivityResultMarkup(response); result.classList.remove('hidden'); }
    } catch (error) {
      if (message) { message.textContent = error.message; message.classList.add('form-error'); }
    } finally {
      testPresetProxy.disabled = false;
      testPresetProxy.textContent = original;
    }
    return;
  }
  const crawlerCodeItem = event.target.closest('[data-crawler-code-name]');
  if (crawlerCodeItem) {
    document.querySelectorAll('[data-crawler-code-name]').forEach((item) => item.classList.toggle('active', item === crawlerCodeItem));
    loadCrawlerSource(crawlerCodeItem.dataset.crawlerCodeName);
    return;
  }
  if (event.target.closest('#add-custom-crawler')) {
    const name = `custom_${Date.now()}`;
    const crawler = { name, kind: 'custom', source: 'from javsp.datatype import MovieInfo\n\n\ndef parse_data(movie: MovieInfo):\n    # Populate movie fields here, or raise MovieNotFoundError.\n    raise NotImplementedError("Implement this crawler")\n' };
    state.activeCrawlerCodeName = '';
    $('#crawler-code-detail').innerHTML = crawlerCodeDetail(crawler, crawler.source);
    document.querySelectorAll('[data-crawler-code-name]').forEach((item) => item.classList.remove('active'));
    return;
  }
  if (event.target.closest('#save-custom-crawler')) {
    const message = $('#crawler-code-message');
    try {
      const saved = await api('/api/crawler-config/custom', { method: 'PUT', body: JSON.stringify({ name: $('#crawler-code-name').value.trim(), source: $('#crawler-code-source').value }) });
      if (message) message.textContent = `已保存 ${saved.name}`;
      await loadCrawlerConfig();
    } catch (error) { if (message) message.textContent = error.message; }
    return;
  }
  const testCrawler = event.target.closest('[data-test-crawler]');
  if (testCrawler) {
    const input = $('#crawler-test-input');
    const message = $('#crawler-test-message');
    const result = $('#crawler-test-result');
    const data = $('#crawler-test-data');
    const output = $('#crawler-test-output');
    const outputWrap = $('#crawler-test-output-wrap');
    const inputValue = input?.value.trim() || '';
    if (!inputValue) {
      if (message) message.textContent = '请输入测试输入';
      input?.focus();
      return;
    }
    const original = testCrawler.textContent;
    testCrawler.disabled = true;
    testCrawler.textContent = '正在测试';
    if (message) { message.textContent = ''; message.classList.remove('form-error'); }
    if (result) result.classList.add('hidden');
    try {
      const response = await api('/api/crawler-config/test', { method: 'POST', body: JSON.stringify({ name: testCrawler.dataset.testCrawler, input_value: inputValue }) });
      if (message) { message.textContent = response.error ? `测试失败：${response.error}` : '测试完成'; message.classList.toggle('form-error', Boolean(response.error)); }
      if (data) data.textContent = JSON.stringify(response.data || {}, null, 2);
      if (output) output.textContent = response.output || '无额外输出';
      if (outputWrap) outputWrap.classList.toggle('hidden', !response.output);
      if (result) result.classList.remove('hidden');
    } catch (error) {
      if (message) { message.textContent = error.message; message.classList.add('form-error'); }
    } finally {
      testCrawler.disabled = false;
      testCrawler.textContent = original;
    }
    return;
  }
  const deleteCustomCrawler = event.target.closest('[data-delete-custom-crawler]');
  if (deleteCustomCrawler) {
    const name = deleteCustomCrawler.dataset.deleteCustomCrawler;
    confirmAction({ title: '删除自定义爬虫', text: `确定删除自定义爬虫“${name}”吗？已在预设中引用它的任务将无法加载该爬虫。`, confirmLabel: '删除爬虫', danger: true, run: async () => { await api(`/api/crawler-config/custom/${encodeURIComponent(name)}`, { method: 'DELETE' }); await loadCrawlerConfig(); } });
    return;
  }
  const disableBuiltInCrawler = event.target.closest('[data-disable-built-in-crawler]');
  if (disableBuiltInCrawler) {
    const name = disableBuiltInCrawler.dataset.disableBuiltInCrawler;
    confirmAction({ title: '删除内置爬虫', text: `确定从可用爬虫中移除“${name}”吗？不会删除镜像文件，可随时恢复；已有预设和新任务也不会再使用它。`, confirmLabel: '删除爬虫', danger: true, run: async () => { await api(`/api/crawler-config/built-in/${encodeURIComponent(name)}`, { method: 'DELETE' }); await loadCrawlerConfig(); await loadCrawlerNames(); } });
    return;
  }
  const restoreBuiltInCrawler = event.target.closest('[data-restore-built-in-crawler]');
  if (restoreBuiltInCrawler) {
    const name = restoreBuiltInCrawler.dataset.restoreBuiltInCrawler;
    await api(`/api/crawler-config/built-in/${encodeURIComponent(name)}/restore`, { method: 'POST' });
    await loadCrawlerConfig();
    await loadCrawlerNames();
    return;
  }
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
  const viewDownloadAutoScrapeRunButton = event.target.closest('[data-view-download-auto-scrape-run]');
  if (viewDownloadAutoScrapeRunButton) {
    openDownloadAutoScrapeRun(viewDownloadAutoScrapeRunButton.dataset.viewDownloadAutoScrapeRun).catch((error) => {
      const target = $('#auto-scrape-run-content');
      if (target) target.innerHTML = `<p class="form-error">${escapeHtml(error.message)}</p>`;
    });
    return;
  }
  const deleteAutoScrapeRunButton = event.target.closest('[data-delete-auto-scrape-run]');
  if (deleteAutoScrapeRunButton) {
    const scheduleId = deleteAutoScrapeRunButton.dataset.deleteAutoScrapeRun;
    const runId = deleteAutoScrapeRunButton.dataset.autoScrapeRunId;
    confirmAction({
      title: '删除运行日志',
      text: '仅删除这条自动刮削运行记录，不会删除关联任务、封面或媒体文件。',
      confirmLabel: '删除日志',
      danger: true,
      run: async () => {
        await api(`/api/auto-scrape-schedules/${encodeURIComponent(scheduleId)}/runs/${encodeURIComponent(runId)}`, { method: 'DELETE' });
        await loadAutoScrapeSchedules();
        if ($('#auto-scrape-run-dialog')?.open) renderAutoScrapeHistory(scheduleId);
      },
    });
    return;
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
    const message = $('#download-management-message');
    addAutoScrapeRule.disabled = true;
    api('/api/downloads/auto-scrape/path-check', { method: 'POST', body: JSON.stringify({ tags: '', category: '' }) }).then((result) => {
      if (!result.ok) { message.textContent = `路径映射检查失败：${(result.issues || []).join('；')}`; return; }
      state.autoScrapeRules = [...readAutoScrapeRules(), newAutoScrapeRule()];
      renderAutoScrapeRules(state.autoScrapeRules);
      message.textContent = result.message || '路径映射检查通过';
    }).catch((error) => { message.textContent = `路径映射检查失败：${error.message}`; }).finally(() => { addAutoScrapeRule.disabled = false; });
    return;
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
    toggle.innerHTML = expandControlIcon(!expanded);
    toggle.setAttribute('aria-expanded', String(!expanded));
    toggle.title = expanded ? '展开任务' : '收起任务';
  }
  const overviewSelect = event.target.closest('[data-overview-select-ids]');
  if (overviewSelect) {
    toggleOverviewSelection(overviewTaskIds(overviewSelect.dataset.overviewSelectIds));
    renderOverview();
    return;
  }
  const overviewSelectAll = event.target.closest('[data-overview-select-all]');
  if (overviewSelectAll) {
    const ids = [...document.querySelectorAll('[data-overview-task-ids]')].flatMap((card) => overviewTaskIds(card.dataset.overviewTaskIds));
    const allSelected = ids.length > 0 && ids.every((id) => state.selectedOverviewTasks.has(id));
    if (!allSelected) state.overviewSelectionMode = true;
    ids.forEach((id) => {
      if (allSelected) state.selectedOverviewTasks.delete(id);
      else state.selectedOverviewTasks.add(id);
      state.overviewSelectionFeedback.add(id);
    });
    renderOverview();
    return;
  }
  const detail = event.target.closest('[data-task-detail]');
  if (detail) {
    const overviewCard = detail.closest('[data-overview-task]');
    if (state.overviewSelectionMode && overviewCard) {
      toggleOverviewSelection(overviewTaskIds(overviewCard.dataset.overviewTaskIds));
      renderOverview();
      return;
    }
    openTaskDetail(detail.dataset.taskDetail);
  }
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
    const taskId = googleCover.dataset.googleCoverTask;
    const currentTask = state.tasks.find((task) => task.id === taskId);
    const dialog = $('#google-cover-dialog');
    if (!currentTask) return;
    state.googleCoverDialogTaskId = taskId;
    state.googleCoverDialogDismissed = false;
    renderGoogleCoverLoading();
    $('#google-cover-message').textContent = '';
    if (dialog && !dialog.open) dialog.showModal();
    try {
      await api(`/api/tasks/${encodeURIComponent(taskId)}/cover/search`, { method: 'POST' });
      waitForCrawlerCoverCandidates(taskId);
    } catch (error) {
      $('#google-cover-message').textContent = error.message;
    }
  }
  const openGoogleSearch = event.target.closest('[data-open-google-client-search]');
  if (openGoogleSearch) openGoogleClientSearch(openGoogleSearch.dataset.openGoogleClientSearch);
  const coverOption = event.target.closest('[data-google-cover-select]');
  if (coverOption) {
    coverOption.disabled = true;
    try {
      await api(`/api/tasks/${encodeURIComponent(coverOption.dataset.googleCoverSelect)}/cover/select`, { method: 'POST', body: JSON.stringify({ candidate_id: coverOption.dataset.candidateId }) });
      await waitForCrawlerCoverSelection(coverOption.dataset.googleCoverSelect);
      $('#google-cover-dialog')?.close();
      await loadTasks();
    } catch (error) { coverOption.disabled = false; $('#google-cover-message').textContent = error.message; }
  }
  const arrayAdd = event.target.closest('.config-array-add-button');
  if (arrayAdd) {
    const control = arrayAdd.closest('.config-array');
    const input = control?.querySelector('.config-array-input');
    const value = input?.value.trim();
    if (!control || !input || !value) return;
    const duplicate = [...control.querySelectorAll('[data-array-value]')].some((tag) => tag.dataset.arrayValue === value);
    if (duplicate) { input.setCustomValidity('\u8be5\u503c\u5df2\u6dfb\u52a0'); input.reportValidity(); return; }
    input.setCustomValidity('');
    control.querySelector('.config-array-list')?.insertAdjacentHTML('beforeend', configArrayTagMarkup(value));
    input.value = '';
    return;
  }
  const arrayRemove = event.target.closest('.config-array-remove');
  if (arrayRemove) { arrayRemove.closest('.config-array-tag')?.remove(); return; }
  const crawlerAdd = event.target.closest('.crawler-add-button');
  if (crawlerAdd) {
    const group = crawlerAdd.closest('.crawler-config-group');
    const input = group?.querySelector('.crawler-add-input');
    if (input && group) {
      const name = input.value.trim().toLowerCase();
      if (!/^[a-z][a-z0-9_]*$/.test(name)) { input.setCustomValidity('\u722c\u866b\u540d\u79f0\u53ea\u80fd\u4f7f\u7528\u5c0f\u5199\u5b57\u6bcd\u3001\u6570\u5b57\u548c\u4e0b\u5212\u7ebf\uff0c\u5e76\u4e14\u5fc5\u987b\u4ee5\u5b57\u6bcd\u5f00\u5934'); input.reportValidity(); return; }
      const duplicate = [...group.querySelectorAll('[data-crawler-value]')].some((tag) => tag.dataset.crawlerValue === name);
      if (duplicate) { input.setCustomValidity('\u8be5\u722c\u866b\u5df2\u6dfb\u52a0'); input.reportValidity(); return; }
      input.setCustomValidity('');
      const tag = document.createElement('span');
      tag.className = 'crawler-tag';
      tag.dataset.crawlerValue = name;
      tag.innerHTML = `<code>${escapeHtml(name)}</code><button class="crawler-tag-remove" type="button" title="\u5220\u9664 ${escapeHtml(name)}" aria-label="\u5220\u9664 ${escapeHtml(name)}">\u00d7</button>`;
      group.querySelector('.crawler-config-list')?.append(tag);
      input.value = '';
      return;
    }
    const select = group?.querySelector('.crawler-add-select');
    if (select?.value) { const row = document.createElement('div'); row.className = 'crawler-config-row'; row.innerHTML = `<select class="crawler-selection" data-group="${group.dataset.crawlerGroup}">${CRAWLER_IDS.map((id) => `<option value="${id}"${id === select.value ? ' selected' : ''}>${id}</option>`).join('')}</select><button class="button secondary crawler-move" type="button" data-direction="up">上移</button><button class="button secondary crawler-move" type="button" data-direction="down">下移</button><button class="button danger crawler-remove" type="button">删除</button>`; group.querySelector('.crawler-config-list').append(row); select.value = ''; }
  }
  const crawlerRemove = event.target.closest('.crawler-remove');
  if (crawlerRemove) { crawlerRemove.closest('.crawler-config-row')?.remove(); }
  const crawlerTagRemove = event.target.closest('.crawler-tag-remove');
  if (crawlerTagRemove) crawlerTagRemove.closest('.crawler-tag')?.remove();
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
$('#cookiecloud-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = $('#cookiecloud-message');
  try {
    const saved = await api('/api/cookiecloud', { method: 'PUT', body: JSON.stringify(cookiecloudPayload()) });
    $('#cookiecloud-password').value = '';
    $('#cookiecloud-clear-password').checked = false;
    message.textContent = saved.has_password ? 'CookieCloud 配置已保存' : 'CookieCloud 配置已保存；尚未设置密码';
  } catch (error) { message.textContent = error.message; }
});
$('#test-cookiecloud').addEventListener('click', async () => {
  const button = $('#test-cookiecloud');
  const message = $('#cookiecloud-message');
  const original = button.textContent;
  button.disabled = true;
  button.textContent = '正在同步';
  try {
    const result = await api('/api/cookiecloud/test', { method: 'POST', body: JSON.stringify(cookiecloudPayload()) });
    message.textContent = `同步成功：${result.domains} 个站点，${result.cookies} 条 Cookie`;
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; button.textContent = original; }
});
$('#download-management-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = $('#download-management-message');
  try {
    const payload = downloadManagementPayload();
    const saved = await api('/api/downloads/settings', { method: 'PUT', body: JSON.stringify(payload) });
    state.autoScrapeRules = normalizeAutoScrapeRules(saved);
    renderAutoScrapeRules(state.autoScrapeRules);
    message.textContent = saved.limit_apply_errors?.length ? `策略已保存；限速应用失败：${saved.limit_apply_errors.join('；')}` : `策略已保存，已立即应用到 ${saved.limit_applied_count || 0} 个已接管任务`;
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
    await Promise.all([loadTasks(), loadPresets(), loadPathTools(), loadCrawlerNames()]);
    if (savedView && document.querySelector(`[data-panel="${savedView}"]`) && (state.user.role === 'admin' || (savedView !== 'settings' && savedView !== 'auto-scrape'))) showView(savedView);
    scheduleGitHubStarInvite();
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

$('#task-detail-dialog')?.addEventListener('close', () => { state.activeTaskDetail = null; state.taskMetadataEditing = false; });

document.addEventListener('pointerdown', (event) => {
  state.taskDetailLogSelecting = Boolean(event.target.closest('#task-detail-content .task-log'));
});
document.addEventListener('pointerup', () => {
  state.taskDetailLogSelecting = false;
});
