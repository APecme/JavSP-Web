(() => {
  const now = () => new Date().toISOString();
  const tasks = [
    {
      id: 'demo-complete-001',
      name: 'SSIS-247',
      file_name: 'SSIS-247.mkv',
      input_directory: '/video/Movies/SSIS-247.mkv',
      preset_id: 'demo',
      preset_name: '默认预设',
      source: 'manual',
      status: 'succeeded',
      created_at: now(),
      cover_count: 0,
      fanart_count: 0,
      log_tail: ['正在识别番号：SSIS-247', '元数据汇总完成', '示例任务已完成'],
      log_entries: [
        { group: 'result', level: 'success', message: '任务完成' },
        { group: 'process', level: 'success', message: '扫描完成 · 1 部影片' },
        { group: 'process', level: 'success', message: 'SSIS-247 · JavSP WEB 示例影片' },
        { group: 'sources', level: 'success', message: 'javdb · 已取得资料' },
        { group: 'sources', level: 'success', message: 'javbus · 已取得资料' },
        { group: 'sources', level: 'warning', message: 'airav · 失败', detail: '站点拒绝访问（403），请检查代理出口及该域名的 CookieCloud 登录状态' },
        { group: 'notes', level: 'info', message: '静态示例使用演示数据，不会下载真实图片' },
      ],
      progress: {
        stages: { concurrent: { percent: 100 }, summary: { percent: 100 }, images: { percent: 100 } },
        crawlers: { javdb: '完成', javbus: '完成' },
        crawler_details: {},
        metadata: { dvdid: 'SSIS-247', title: 'JavSP WEB 示例影片', actress: ['演示演员'], publish_date: '2026-09-08' },
        images: { cover_done: 0, cover_status: 'pending', fanart_done: 0, fanart_total: 0, fanart_status: 'pending' },
      },
    },
  ];
  tasks[0].log_tail = tasks[0].log_entries.map(entry => entry.message + (entry.detail ? `：${entry.detail}` : ''));

  const json = (data, status = 200) => new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
  const endpoint = (input) => new URL(typeof input === 'string' ? input : input.url, location.origin).pathname;

  window.fetch = async (input, options = {}) => {
    const path = endpoint(input);
    if (!path.startsWith('/api/')) return json({ tag_name: 'v1.1.34' });
    if (path === '/api/auth/me') return json({ username: 'demo', role: 'admin' });
    if (path === '/api/tasks' && (!options.method || options.method === 'GET')) return json(tasks);
    if (path.startsWith('/api/tasks/') && (!options.method || options.method === 'GET')) {
      return json(tasks.find((task) => task.id === path.split('/')[3]) || tasks[0]);
    }
    if (path === '/api/tasks' && options.method === 'POST') {
      const payload = JSON.parse(options.body || '{}');
      const inputPath = payload.input_directory || '/video/Movies/NEW-001.mkv';
      const name = inputPath.split(/[\\/]/).pop().replace(/\.[^.]+$/, '') || 'NEW-001';
      tasks.unshift({
        ...tasks[0], id: `demo-${Date.now()}`, name, file_name: `${name}.mkv`, input_directory: inputPath,
        status: 'queued', created_at: now(), log_entries: null, log_tail: [`已创建演示任务：${name}`, '等待本机 JavSP 服务执行'],
        progress: { ...tasks[0].progress, stages: { concurrent: { percent: 0 }, summary: { percent: 0 }, images: { percent: 0 } } },
      });
      return json(tasks.slice(0, 1));
    }
    if (path === '/api/presets') return json([{ id: 'demo', name: '默认预设', mode: 'yaml', content: '# 示例站点使用演示配置', form_values: {}, task_concurrency: 1 }]);
    if (path === '/api/runtime') return json({ version: '1.1.34', app_version: '1.1.34', docker: true });
    if (path === '/api/crawler-config/names') return json({ crawlers: [], disabled_built_ins: [] });
    if (path === '/api/path/select') return json({ path: '/video/Movies' });
    if (path === '/api/downloaders') return json([]);
    if (path === '/api/media-servers') return json([]);
    if (path === '/api/path-mappings') return json({ mappings: [] });
    if (path === '/api/users') return json([{ username: 'demo', role: 'admin', created_at: now() }]);
    if (path === '/api/auto-scrape-schedules') return json([]);
    if (path === '/api/downloads/settings') return json({ takeover_enabled: false, rules: [] });
    if (path === '/api/downloads') return json({ downloaders: [] });
    if (path === '/api/cookiecloud') return json({ enabled: false, has_password: false });
    return json({ ok: true });
  };
})();
