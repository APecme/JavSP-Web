(() => {
  const seed = window.JavspDemoSeed;
  document.addEventListener('click', event => {
    if (event.target.closest('#logout')) {
      event.preventDefault();
      event.stopImmediatePropagation();
      location.href = 'index.html';
    }
  }, true);
  const copy = value => JSON.parse(JSON.stringify(value));
  const now = () => new Date().toISOString();
  const id = () => crypto.randomUUID().replaceAll('-', '');
  const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
  const denied = () => json({ detail: '静态示例不执行此操作，请在自己部署的 JavSP WEB 中使用。' }, 409);
  const metadata = { dvdid: 'DEMO-001', title: '媒体库整理示例', actress: ['示例演员'], publish_date: '2026-10-10', genre: ['演示数据'], plot: '此资料只用于演示界面。' };
  const makeTask = (name, status = 'succeeded') => ({
    id: id(), name, file_name: `${name}.mkv`, input_directory: `/video/待整理/${name}.mkv`, preset_id: 'default', preset_name: '默认预设', source: 'manual',
    status, created_at: now(), finished_at: now(), cover_count: 0, fanart_count: 0, output_directory: `/video/媒体库/${name}`, error: status === 'failed' ? '资料汇总失败：所有数据源均未取得必需字段：封面' : '',
    log_tail: ['演示扫描完成', status === 'failed' ? '示例失败：封面资料缺失' : '演示整理完成'],
    log_entries: [{ group: 'result', level: status === 'failed' ? 'error' : 'success', message: status === 'failed' ? '封面资料缺失（演示）' : '整理完成（演示）' }, { group: 'notes', level: 'info', message: '此处为模拟结果，未读取文件或访问爬虫站点' }],
    progress: { stages: { concurrent: { percent: 100 }, summary: { percent: 100 }, images: { percent: status === 'failed' ? 0 : 100 } }, crawlers: { javdb: '完成' }, crawler_details: {}, metadata: { ...metadata, dvdid: name }, images: { cover_done: 0, cover_status: 'pending', fanart_done: 0, fanart_total: 0, fanart_status: 'pending' } },
  });
  const tasks = [makeTask('DEMO-001'), makeTask('DEMO-002', 'failed')];
  const presets = [{ id: 'default', name: '默认预设', mode: 'form', form_values: copy(seed.config), content: seed.config_yaml, task_concurrency: 1 }];
  let settings = copy(seed.ai);
  let skills = copy(seed.skills);
  const conversations = [];
  const schedules = [{ id: 'demo-schedule', name: '每天整理示例目录', enabled: false, cron: '0 2 * * *', input_directory: '/video/待整理', preset_id: 'default', preset_name: '默认预设', next_run_at: '', runs: [] }];
  let mappings = [{ source_path: '/downloads', target_path: '/video/待整理' }];
  let downloadSettings = { takeover_enabled: false, auto_scrape_enabled: false, auto_scrape_rules: [], ratio_limit: -1, seeding_time_limit: -1, inactive_seeding_time_limit: -1, download_limit_kib: -1, upload_limit_kib: -1 };
  const downloaders = [{ id: 'demo-downloader', name: 'qBittorrent 示例', url: 'http://qbittorrent.example:8080', username: 'demo', password_set: false }];
  const mediaServers = [{ id: 'demo-media', name: 'Emby 示例', type: 'emby', url: 'http://emby.example:8096', external_url: '', api_key_set: false, auto_scan: false, auto_scan_delay: 30, libraries: [] }];
  let cookiecloud = { enabled: false, url: '', uuid: '', has_password: false };
  const update = { current: seed.version, channel: 'bata', settings: { experience_program: true, check_enabled: false, auto_update: false, check_interval_hours: 24 }, result: {}, job: {}, capability: { supported: false, reason: '静态示例不检查或安装软件。正式部署请在此管理更新。' } };
  const crawlerNames = [...new Set(Object.values(seed.config.crawler.selection).flat())];
  const crawlerInfo = name => ({ name, kind: 'builtin', editable: false, source: '此示例展示爬虫入口，不包含可执行爬虫代码。' });
  const publicConversation = conversation => {
    if (conversation.status === 'running' && conversation.demo_started) {
      const elapsed = Date.now() - conversation.demo_started;
      const reply = conversation.turns.at(-1);
      reply.reasoning_content = '演示：先核对任务失败阶段，再区分数据源失败与整理冲突。';
      reply.phase = elapsed < 800 ? 'thinking' : 'answering';
      const answer = '这是固定的演示回复，未调用真实模型。\n\n- **1 个示例任务缺少封面**：先在爬虫配置中测试数据源。\n- **1 个示例任务已完成**：可展开详情查看日志。\n\n建议先核对失败任务的必需字段与预设。';
      reply.content = elapsed < 800 ? '' : answer.slice(0, Math.floor((elapsed - 800) / 12));
      if (reply.content.length === answer.length) { reply.status = 'completed'; conversation.status = 'completed'; }
    }
    const result = copy(conversation);
    delete result.demo_started;
    return result;
  };
  const saveCollection = (items, path, body, method) => {
    const identifier = path.split('/')[3];
    const existing = items.find(item => item.id === identifier);
    if (method === 'DELETE') { if (existing) items.splice(items.indexOf(existing), 1); return json({ ok: true }); }
    if (method === 'POST' || method === 'PUT') {
      const safe = Object.fromEntries(Object.entries(body).filter(([key]) => !/password|api_key|secret|token/i.test(key)));
      const record = existing || { id: id() };
      Object.assign(record, safe);
      if (!existing) items.push(record);
      return json(record);
    }
    return json(existing || items);
  };
  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.origin);
    const path = url.pathname;
    const method = (options.method || 'GET').toUpperCase();
    let body = {};
    try { body = JSON.parse(options.body || '{}'); } catch { return denied(); }
    if (url.origin !== location.origin || !path.startsWith('/api/')) return denied();
    if (path === '/api/auth/me') return json({ username: 'demo', role: 'admin' });
    if (path.startsWith('/api/auth/')) return denied();
    if (path === '/api/runtime') return json({ version: seed.version, app_version: seed.version, docker: true, deployment: 'docker', timezone: 'Asia/Shanghai', ai_enabled: settings.enabled });
    if (path === '/api/update') return json(update);
    if (path.startsWith('/api/update/')) return denied();
    if (path === '/api/ai/settings') {
      if (method === 'PUT') { const { api_key, clear_api_key, ...safe } = body; settings = { ...settings, ...safe, has_api_key: false }; }
      return json(settings);
    }
    if (path === '/api/ai/test' || path === '/api/ai/test-search') return json({ message: '此处为静态演示，未连接 LLM 或搜索服务。请在自己的部署中测试。', tools_supported: false });
    if (path === '/api/ai/skills/restore-defaults') { skills = copy(seed.skills); return json(skills); }
    if (path === '/api/ai/skills') {
      if (method === 'PUT') {
        const name = body.source?.match(/^name:\s*([a-z][a-z0-9_-]*)\s*$/m)?.[1];
        const description = body.source?.match(/^description:\s*(.+)$/m)?.[1];
        if (!name || !description) return json({ detail: '请填写 name 和 description' }, 400);
        skills = skills.filter(skill => skill.name !== name);
        skills.push({ name, description, source: body.source, kind: 'custom' });
      }
      return json(skills);
    }
    if (path.startsWith('/api/ai/skills/')) {
      const skill = skills.find(item => item.name === decodeURIComponent(path.split('/').at(-1)));
      if (!skill) return json({ detail: 'Skill 不存在' }, 404);
      if (method === 'DELETE') { skills.splice(skills.indexOf(skill), 1); return json({ ok: true }); }
      return json(skill);
    }
    if (path === '/api/ai/chat') {
      if (!settings.enabled) return json({ detail: '请先启用 AI 刮削' }, 400);
      let conversation = conversations.find(item => item.id === body.conversation_id);
      if (!conversation) { conversation = { id: id(), title: body.message.slice(0, 40), turns: [], actions: [], steps: [], created_at: now() }; conversations.unshift(conversation); }
      if (conversation.status === 'running') return json({ detail: '当前对话正在处理中' }, 409);
      conversation.turns.push({ id: id(), role: 'user', content: body.message }, { id: id(), role: 'assistant', content: '', status: 'running', phase: 'thinking' });
      Object.assign(conversation, { status: 'running', error: '', updated_at: now(), demo_started: Date.now() });
      return json(publicConversation(conversation), 202);
    }
    if (path === '/api/ai/conversations') return json(conversations.map(item => { const value = publicConversation(item); return { id: value.id, title: value.title, status: value.status, updated_at: value.updated_at }; }));
    if (path.startsWith('/api/ai/conversations/')) {
      if (!/^\/api\/ai\/conversations\/[^/]+(?:\/stop)?$/.test(path)) return denied();
      const conversation = conversations.find(item => item.id === path.split('/')[4]);
      if (!conversation) return json({ detail: '此演示对话已随刷新重置，请新建对话' }, 404);
      if (path.endsWith('/stop')) { conversation.status = 'stopped'; conversation.turns.at(-1).status = 'stopped'; }
      else if (method === 'PATCH') conversation.title = body.title;
      else if (method === 'DELETE') { conversations.splice(conversations.indexOf(conversation), 1); return json({ ok: true }); }
      return json(publicConversation(conversation));
    }
    if (path === '/api/tasks' && method === 'POST') {
      const task = makeTask((body.input_directory || 'DEMO-003').split(/[\\/]/).pop().replace(/\.[^.]+$/, '') || 'DEMO-003', 'queued');
      task.input_directory = body.input_directory;
      tasks.unshift(task);
      setTimeout(() => { if (task.status === 'queued') task.status = 'running'; }, 800);
      setTimeout(() => { if (task.status === 'running') task.status = 'succeeded'; }, 2500);
      return json({ scan: false, count: 1, task_id: task.id }, 202);
    }
    if (path === '/api/tasks') {
      let items = tasks.filter(task => !url.searchParams.get('status') || task.status === url.searchParams.get('status'));
      const query = url.searchParams.get('query')?.toLowerCase();
      if (query) items = items.filter(task => JSON.stringify(task).toLowerCase().includes(query));
      const offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 20);
      return json({ items: items.slice(offset, offset + limit), total: items.length, offset, limit, metrics: { total: tasks.length, latest_status: tasks[0]?.status, running: tasks.filter(task => task.status === 'running').length, succeeded: tasks.filter(task => task.status === 'succeeded').length, failed: tasks.filter(task => task.status === 'failed').length } });
    }
    if (path.startsWith('/api/tasks/')) {
      const task = tasks.find(item => item.id === path.split('/')[3]);
      if (!task) return json({ detail: '任务不存在' }, 404);
      if (path.endsWith('/cancel')) { task.status = 'cancelled'; return json(task); }
      if (method === 'DELETE') { tasks.splice(tasks.indexOf(task), 1); return json({ ok: true }); }
      if (method !== 'GET' || path.split('/').length > 4) return denied();
      return json(task);
    }
    if (path === '/api/presets/convert' || path === '/api/presets/network/proxy-test') return denied();
    if (path === '/api/presets' || /^\/api\/presets\/[^/]+$/.test(path)) {
      if (body.mode === 'yaml') return denied();
      if (method === 'POST' || method === 'PUT') body.form_values = body.form || copy(seed.config);
      return saveCollection(presets, path, body, method);
    }
    if (path === '/api/config') return json({ content: seed.config_yaml });
    if (path === '/api/path/select') return json({ path: '/video/待整理' });
    if (path === '/api/path/browse') {
      const current = url.searchParams.get('path') || '/';
      const entries = current === '/' ? [{ name: 'video', path: '/video', kind: 'directory' }] : current === '/video' ? [{ name: '待整理', path: '/video/待整理', kind: 'directory' }] : [{ name: 'DEMO-001.mkv', path: '/video/待整理/DEMO-001.mkv', kind: 'file' }];
      return json({ path: current, parent: current === '/' ? null : current.slice(0, current.lastIndexOf('/')) || '/', entries });
    }
    if (path === '/api/crawler-config/names') return json({ crawlers: crawlerNames.map(crawlerInfo), disabled_built_ins: [] });
    if (path === '/api/crawler-config') return json({ ...copy(seed.config), crawlers: crawlerNames.map(crawlerInfo), selection: seed.config.crawler.selection, media_types: seed.config.scanner.media_types });
    if (path.startsWith('/api/crawler-config/') && method !== 'GET') return denied();
    if (path.startsWith('/api/crawler-config/')) return json(crawlerInfo(path.split('/').at(-1)));
    if (path === '/api/downloads/settings') { if (method === 'PUT') downloadSettings = { ...downloadSettings, ...body }; return json(downloadSettings); }
    if (path === '/api/downloads') return json({ downloaders: downloaders.map(item => ({ ...item, connected: false, error: '静态示例未连接下载器', torrents: [] })) });
    if (path.startsWith('/api/downloads/')) return denied();
    if (path === '/api/path-mappings') { if (method === 'PUT') mappings = body.mappings; return json({ mappings }); }
    if (path === '/api/download-auto-scrape-runs') return json([]);
    if (path.startsWith('/api/auto-scrape-schedules/')) {
      if (path.endsWith('/run')) return denied();
      return saveCollection(schedules, path, body, method);
    }
    if (path === '/api/auto-scrape-schedules') return saveCollection(schedules, path, body, method);
    if (path.startsWith('/api/downloaders')) { if (path.endsWith('/test')) return denied(); return saveCollection(downloaders, path, body, method); }
    if (path.startsWith('/api/media-servers')) { if (path.endsWith('/sync') || path.endsWith('/libraries')) return denied(); return saveCollection(mediaServers, path, body, method); }
    if (path === '/api/cookiecloud/test') return denied();
    if (path === '/api/cookiecloud') { if (method === 'PUT') { const { password, ...safe } = body; cookiecloud = { ...cookiecloud, ...safe, has_password: false }; } return json(cookiecloud); }
    if (path === '/api/users' && method === 'GET') return json([{ username: 'demo', role: 'admin', created_at: now() }]);
    return denied();
  };
})();
