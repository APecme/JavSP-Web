(() => {
  let conversation = null;
  let pollTimer = null;
  let sending = false;
  let loaded = false;
  let history = [];
  let viewRevision = 0;
  let stopping = false;
  let historyRevision = 0;
  const drafts = new Map();
  const actionNames = { create_task: '创建刮削任务', save_crawler: '保存爬虫代码', change_preset: '修改刮削预设', create_preset: '创建刮削预设', create_schedule: '创建自动刮削规则', update_metadata: '保存影片资料' };
  const toolNames = { ...actionNames, read_skill: '读取 Skill', list_crawlers: '查看爬虫', get_crawler: '读取爬虫代码', test_crawler: '测试爬虫', list_presets: '查看预设', get_preset: '读取预设', list_tasks: '查找任务', get_task: '读取任务', list_schedules: '查看自动刮削规则' };
  const statusNames = { pending: '待确认', executing: '执行中', completed: '已完成', rejected: '已取消', failed: '失败', unknown: '结果待核实' };
  toolNames.ai_lookup = 'AI 搜索影片资料';
  const storageKey = () => `javsp-web.ai-conversation.${state.user?.username || ''}`;

  function fitLayout() {
    const layout = document.querySelector('[data-panel="ai-scrape"].active .ai-layout');
    if (layout) layout.style.height = `${Math.max(300, (window.visualViewport?.height || window.innerHeight) - layout.getBoundingClientRect().top - 24)}px`;
  }
  window.addEventListener('resize', fitLayout);
  window.visualViewport?.addEventListener('resize', fitLayout);

  function textElement(tag, text, className = '') {
    const element = document.createElement(tag);
    element.textContent = text;
    element.className = className;
    return element;
  }

  function detail(title, value) {
    const element = document.createElement('details');
    element.append(textElement('summary', title), textElement('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2), 'ai-code'));
    return element;
  }

  function reconcile(target, nodes) {
    nodes.forEach((node, index) => {
      if (target.childNodes[index] !== node) target.insertBefore(node, target.childNodes[index] || null);
    });
    while (target.childNodes.length > nodes.length) target.lastChild.remove();
  }

  function updateBusy() {
    const busy = sending || conversation?.status === 'running';
    $('#ai-send').disabled = busy;
    $('#ai-new-chat').disabled = sending;
    $('#ai-send').hidden = conversation?.status === 'running';
    $('#ai-send').textContent = sending ? '提交中…' : '发送 ↑';
    $('#ai-stop').hidden = conversation?.status !== 'running';
    $('#ai-stop').disabled = stopping || sending;
    $('#ai-stop').textContent = stopping ? '正在停止…' : '停止生成 ■';
    $('#ai-workspace')?.setAttribute('aria-busy', String(busy));
    document.querySelectorAll('.ai-action button').forEach(button => { button.disabled = busy; });
    renderHistory();
  }

  function renderHistory() {
    const query = $('#ai-history-search').value.trim().toLocaleLowerCase();
    const items = history.filter(item => item.title.toLocaleLowerCase().includes(query));
    const target = $('#ai-history-list');
    const existing = new Map([...target.children].map(row => [row.dataset.id, row]));
    const rows = items.map(item => {
      const signature = JSON.stringify([item.title, item.status, item.id === conversation?.id, sending]);
      if (existing.get(item.id)?.dataset.signature === signature) return existing.get(item.id);
      const row = document.createElement('div');
      row.dataset.id = item.id;
      row.dataset.signature = signature;
      row.className = `ai-history-item${item.id === conversation?.id ? ' selected' : ''}`;
      const select = textElement('button', item.title, 'ai-history-select');
      select.type = 'button';
      select.title = item.title;
      select.setAttribute('aria-current', String(item.id === conversation?.id));
      select.disabled = sending;
      if (item.status === 'running') select.append(textElement('small', ' · 处理中'));
      select.addEventListener('click', () => openConversation(item.id));
      row.append(select);
      for (const rename of [true, false]) {
        const button = textElement('button', rename ? '✎' : '×', 'icon-button');
        button.type = 'button';
        button.title = rename ? '重命名对话' : '删除对话';
        button.setAttribute('aria-label', `${button.title}：${item.title}`);
        button.disabled = sending || item.status === 'running';
        button.addEventListener('click', () => manageConversation(item, rename));
        row.append(button);
      }
      return row;
    });
    reconcile(target, rows);
    if (!items.length) $('#ai-history-list').append(textElement('p', query ? '没有匹配的对话' : '还没有历史对话', 'muted'));
  }

  async function loadHistory() {
    const revision = ++historyRevision;
    try {
      const result = await api('/api/ai/conversations');
      if (revision !== historyRevision) return;
      history = result;
      renderHistory();
      $('#ai-history-status').textContent = '';
    } catch (error) { $('#ai-history-status').textContent = error.message; }
  }

  function saveDraft() { drafts.set(conversation?.id || '', $('#ai-message').value); }

  function restoreDraft() {
    $('#ai-message').value = drafts.get(conversation?.id || '') || '';
    $('#ai-message').dispatchEvent(new Event('input'));
  }

  async function openConversation(identifier) {
    if (sending) return;
    saveDraft();
    const revision = ++viewRevision;
    window.clearTimeout(pollTimer);
    try {
      const result = await api(`/api/ai/conversations/${identifier}`);
      if (revision !== viewRevision) return;
      conversation = result;
      stopping = false;
      localStorage.setItem(storageKey(), identifier);
      restoreDraft();
      document.querySelector('.ai-layout').classList.remove('history-open');
      $('#ai-toggle-history').setAttribute('aria-expanded', 'false');
      render();
      document.querySelector('.ai-scroll').scrollTop = document.querySelector('.ai-scroll').scrollHeight;
    } catch (error) {
      if (revision !== viewRevision) return;
      $('#ai-status').textContent = error.message;
      if (conversation?.status === 'running') pollTimer = window.setTimeout(poll, 1000);
    }
  }

  async function manageConversation(item, rename) {
    if (sending) return;
    const title = rename ? window.prompt('对话名称', item.title) : null;
    if (rename && (title === null || !title.trim())) return;
    if (!rename && !window.confirm(`删除对话「${item.title}」？聊天记录和待确认操作将被删除，已执行的任务不受影响。`)) return;
    const revision = viewRevision;
    try {
      const result = await api(`/api/ai/conversations/${item.id}`, { method: rename ? 'PATCH' : 'DELETE', ...(rename ? { body: JSON.stringify({ title: title.trim() }) } : {}) });
      if (!rename) drafts.delete(item.id);
      if (revision === viewRevision && conversation?.id === item.id) {
        if (rename) { conversation = result; render(); }
        else newConversation();
      }
      await loadHistory();
    } catch (error) { $('#ai-history-status').textContent = error.message; }
  }

  function actionCard(action) {
    const card = document.createElement('article');
    card.className = 'ai-action';
    card.append(textElement('h3', `${actionNames[action.tool] || action.tool} · ${statusNames[action.status] || action.status}`));
    if (action.tool === 'save_crawler') card.append(textElement('p', '代码保存后，可由爬虫测试和刮削任务执行。请先检查代码。', 'muted'));
    const preview = detail('查看操作内容', action.arguments);
    preview.dataset.detailKey = `action-${action.id}`;
    preview.open = action.status === 'pending';
    card.append(preview);
    if (action.result) card.append(detail('执行结果', action.result));
    if (action.error) card.append(textElement('p', action.error, 'form-error'));
    if (action.status === 'pending') {
      const buttons = document.createElement('div');
      buttons.className = 'form-actions';
      for (const approve of [true, false]) {
        const button = textElement('button', approve ? '确认执行' : '取消', `button ${approve ? 'primary' : 'secondary'}`);
        button.type = 'button';
        button.addEventListener('click', () => decide(action.id, approve));
        buttons.append(button);
      }
      card.append(buttons);
    }
    return card;
  }

  function render() {
    fitLayout();
    const scroll = document.querySelector('.ai-scroll');
    const follow = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 80;
    const target = $('#ai-conversation');
    const details = new Map([...target.querySelectorAll('details[data-detail-key]')].map(element => [element.dataset.detailKey, element.open]));
    const previousScroll = scroll.scrollTop;
    const existing = new Map([...target.children].map(row => [row.dataset.id, row]));
    const rows = [];
    $('#ai-chat-title').textContent = conversation?.title || 'AI 刮削助手';
    if (!conversation?.turns.length) {
      const welcome = document.createElement('div');
      welcome.className = 'ai-empty';
      welcome.append(textElement('h2', '今天想刮削哪些影片？'), textElement('p', '告诉我番号、文件路径，或粘贴网页资料。', 'muted'));
      const suggestions = document.createElement('div');
      suggestions.className = 'ai-suggestions';
      for (const prompt of ['查看最近失败的刮削任务，分析原因', '列出可用爬虫和刮削预设', '帮我制作一个新的爬虫']) {
        const button = textElement('button', prompt, 'button secondary');
        button.type = 'button';
        button.addEventListener('click', () => { $('#ai-message').value = prompt; $('#ai-message').focus(); });
        suggestions.append(button);
      }
      welcome.append(suggestions);
      target.replaceChildren(welcome);
    }
    const turns = conversation?.turns || [];
    const lastAssistant = turns.findLast(turn => turn.role === 'assistant');
    for (const turn of turns) {
      const turnSteps = (conversation.steps || []).filter(step => step.turn_id === turn.id || (!step.turn_id && turn === lastAssistant));
      const turnActions = (conversation.actions || []).filter(action => action.turn_id === turn.id || (!action.turn_id && turn === lastAssistant));
      const signature = JSON.stringify([turn, turnSteps, turnActions, conversation.status === 'running']);
      if (existing.get(turn.id)?.dataset.signature === signature) {
        rows.push(existing.get(turn.id));
        continue;
      }
      const row = document.createElement('article');
      row.dataset.id = turn.id;
      row.dataset.signature = signature;
      row.className = `ai-turn ai-turn-${turn.role}`;
      if (turn.role === 'user') row.append(textElement('div', turn.content, 'ai-turn-text'));
      else {
        row.append(textElement('strong', 'JavSP', 'ai-assistant-label'));
        const running = turn.status === 'running' && conversation.status === 'running';
        if (turn.reasoning_content) {
          const thinking = document.createElement('details');
          thinking.className = 'ai-thinking';
          thinking.dataset.detailKey = `thinking-${turn.id}`;
          thinking.append(textElement('summary', running && turn.phase === 'thinking' ? '正在思考…' : '查看思考内容'));
          thinking.append(window.JavspMarkdown.render(turn.reasoning_content));
          row.append(thinking);
        }
        const steps = turnSteps;
        if (steps.length) {
          const tools = document.createElement('details');
          tools.className = 'ai-tool-progress';
          tools.dataset.detailKey = `tools-${turn.id}`;
          tools.append(textElement('summary', `${steps.some(step => step.status === 'executing') ? '正在使用工具' : '工具记录'} · ${steps.length}`));
          for (const step of steps) {
            const entry = detail(`${toolNames[step.tool] || step.tool} · ${statusNames[step.status] || step.status}`, step.result);
            entry.dataset.detailKey = `step-${step.id || steps.indexOf(step)}`;
            tools.append(entry);
          }
          row.append(tools);
        }
        if (turn.content) row.append(window.JavspMarkdown.render(turn.content));
        if (running && (turn.phase !== 'thinking' || !turn.reasoning_content)) row.append(textElement('div', ({ thinking: '正在思考…', answering: '正在回复…', tools: '正在调用工具…' })[turn.phase] || '正在处理…', 'ai-stream-status'));
        if (turn.status === 'stopped') row.append(textElement('small', '已停止生成', 'muted'));
        if (turn.status === 'failed') row.append(textElement('small', '本次回复中断，已保留收到的内容', 'muted'));
        for (const action of turnActions) row.append(actionCard(action));
        if (turn.content && !running) {
          const copy = textElement('button', '复制回复', 'icon-button ai-copy-reply');
          copy.type = 'button';
          copy.addEventListener('click', async () => {
            try { await navigator.clipboard.writeText(turn.content); copy.textContent = '已复制'; }
            catch { copy.textContent = '请选中文本复制'; }
          });
          row.append(copy);
        }
      }
      rows.push(row);
    }
    if (turns.length) reconcile(target, rows);
    for (const element of target.querySelectorAll('details[data-detail-key]')) {
      if (details.has(element.dataset.detailKey)) element.open = details.get(element.dataset.detailKey);
    }
    const running = conversation?.status === 'running';
    $('#ai-status').className = conversation?.error ? 'form-error' : 'muted';
    $('#ai-status').textContent = conversation?.error || (running && turns.at(-1)?.role !== 'assistant' ? '正在连接模型…' : '');
    if (!running) stopping = false;
    if (conversation) {
      const summary = { id: conversation.id, title: conversation.title || '新对话', status: conversation.status };
      const index = history.findIndex(item => item.id === conversation.id);
      if (index < 0) history.unshift(summary); else history[index] = summary;
    }
    updateBusy();
    window.clearTimeout(pollTimer);
    if (running) pollTimer = window.setTimeout(poll, 500);
    scroll.scrollTop = follow ? scroll.scrollHeight : previousScroll;
  }

  async function poll() {
    if (!conversation) return;
    const identifier = conversation.id;
    const revision = viewRevision;
    try {
      const result = await api(`/api/ai/conversations/${identifier}`);
      if (revision !== viewRevision || identifier !== conversation?.id) return;
      conversation = result;
      render();
    } catch (error) {
      if (revision !== viewRevision || identifier !== conversation?.id) return;
      $('#ai-status').textContent = `${error.message}；正在重连，后台操作可能仍在进行。`;
      pollTimer = window.setTimeout(poll, 5000);
    }
  }

  async function decide(actionId, approve) {
    if (sending) return;
    sending = true;
    viewRevision += 1;
    window.clearTimeout(pollTimer);
    updateBusy();
    try {
      conversation = await api(`/api/ai/conversations/${conversation.id}/actions/${actionId}`, { method: 'POST', body: JSON.stringify({ approve }) });
      render();
    } catch (error) {
      await poll();
      $('#ai-status').textContent = error.message;
    } finally {
      sending = false;
      updateBusy();
    }
  }

  $('#ai-chat-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (sending || conversation?.status === 'running') return;
    const message = $('#ai-message').value.trim();
    if (!message) return;
    sending = true;
    viewRevision += 1;
    window.clearTimeout(pollTimer);
    updateBusy();
    $('#ai-status').textContent = '正在提交…';
    try {
      conversation = await api('/api/ai/chat', { method: 'POST', body: JSON.stringify({ message, conversation_id: conversation?.id || null }) });
      localStorage.setItem(storageKey(), conversation.id);
      $('#ai-message').value = '';
      drafts.delete('');
      drafts.delete(conversation.id);
      $('#ai-message').dispatchEvent(new Event('input'));
      render();
      document.querySelector('.ai-scroll').scrollTop = document.querySelector('.ai-scroll').scrollHeight;
      loadHistory();
    } catch (error) {
      $('#ai-status').textContent = error.message;
    } finally {
      sending = false;
      updateBusy();
    }
  });
  $('#ai-message').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      $('#ai-chat-form').requestSubmit();
    }
  });
  $('#ai-message').addEventListener('input', event => {
    event.target.style.height = 'auto';
    event.target.style.height = `${Math.min(event.target.scrollHeight, 200)}px`;
  });

  function newConversation() {
    if (sending) return;
    saveDraft();
    viewRevision += 1;
    stopping = false;
    window.clearTimeout(pollTimer);
    conversation = null;
    localStorage.removeItem(storageKey());
    restoreDraft();
    document.querySelector('.ai-layout').classList.remove('history-open');
    $('#ai-toggle-history').setAttribute('aria-expanded', 'false');
    render();
    $('#ai-message').focus();
  }
  $('#ai-new-chat').addEventListener('click', newConversation);
  $('#ai-history-search').addEventListener('input', renderHistory);
  $('#ai-toggle-history').addEventListener('click', () => {
    const open = document.querySelector('.ai-layout').classList.toggle('history-open');
    $('#ai-toggle-history').setAttribute('aria-expanded', String(open));
  });
  $('#ai-stop').addEventListener('click', async () => {
    const identifier = conversation?.id;
    const revision = viewRevision;
    if (!identifier) return;
    stopping = true;
    updateBusy();
    try { await api(`/api/ai/conversations/${identifier}/stop`, { method: 'POST' }); }
    catch (error) {
      if (revision !== viewRevision) return;
      stopping = false;
      $('#ai-status').textContent = error.message;
      updateBusy();
    }
  });

  function settingsForm() {
    if ($('#ai-settings-form')) return;
    const panel = document.createElement('div');
    panel.className = 'panel narrow';
    panel.innerHTML = `<div class="panel-heading"><div><h2>AI 接入</h2><p class="muted">配置 AI 刮削助手使用的 LLM，需要支持工具调用的模型。</p></div></div>
      <form id="ai-settings-form" class="stack">
        <label class="check-label"><input id="ai-enabled" type="checkbox">启用 AI 刮削</label>
        <label>LLM 提供商<select id="ai-provider"><option value="compatible">OpenAI 兼容服务</option><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="ollama">Ollama</option><option value="anthropic">Anthropic</option></select></label>
        <label>LLM URL<input id="ai-base-url" type="url" maxlength="2048" placeholder="https://api.example.com/v1"></label>
        <small class="muted">填写服务端可访问的 API 基础地址，通常以 /v1 结尾。</small>
        <label>模型名称<input id="ai-model" maxlength="200" placeholder="填写服务商提供的模型 ID"></label>
        <label>API KEY<input id="ai-key" type="password" autocomplete="new-password" maxlength="4096" placeholder="留空保留已保存的密钥"></label>
        <label class="check-label"><input id="ai-clear-key" type="checkbox">清除已保存的 API KEY</label>
        <label>请求超时（秒）<input id="ai-timeout" type="number" min="10" max="120" value="60" required></label>
        <div class="form-actions"><button class="button secondary" id="ai-test" type="button">测试连接</button><button class="button primary" type="submit">保存 AI 配置</button></div>
        <p id="ai-settings-message" class="muted" role="status"></p>
      </form>
      <section class="ai-skill-manager"><div class="panel-heading"><div><h3>项目 Skills</h3><p class="muted">管理 AI 可按需读取的技能指令；添加或删除不会赋予额外工具权限。</p></div><button class="button secondary" id="ai-add-skill" type="button">添加 Skill</button></div>
        <div id="ai-skills-list"></div>
        <div class="form-actions"><button class="button secondary" id="ai-restore-skills" type="button">恢复内置 Skills</button></div>
        <form id="ai-skill-form" class="stack" hidden><label>SKILL.md<textarea id="ai-skill-source" class="code-editor" rows="12" maxlength="32000" spellcheck="false" required></textarea></label><div class="form-actions"><button class="button primary" type="submit">保存 Skill</button><button class="button secondary" id="ai-cancel-skill" type="button">取消</button></div></form>
        <p id="ai-skills-message" role="status" class="muted"></p>
      </section>`;
    document.querySelector('[data-panel="settings"]').prepend(panel);
    $('#ai-settings-form').addEventListener('submit', async event => {
      event.preventDefault();
      await submitSettings(false);
    });
    $('#ai-test').addEventListener('click', () => submitSettings(true));
    $('#ai-add-skill').addEventListener('click', () => {
      $('#ai-skill-source').value = '---\nname: my-skill\ndescription: 描述这个技能的用途和触发场景\n---\n\n# 技能说明\n\n填写 AI 应遵循的处理方式。\n';
      $('#ai-skill-form').hidden = false;
      $('#ai-skill-source').focus();
    });
    $('#ai-cancel-skill').addEventListener('click', () => { $('#ai-skill-form').hidden = true; });
    $('#ai-skill-form').addEventListener('submit', async event => {
      event.preventDefault();
      const button = event.target.querySelector('button[type="submit"]');
      button.disabled = true;
      try {
        await api('/api/ai/skills', { method: 'PUT', body: JSON.stringify({ source: $('#ai-skill-source').value }) });
        $('#ai-skill-form').hidden = true;
        await loadSkills();
        $('#ai-skills-message').textContent = 'Skill 已保存，后续 AI 请求可使用。';
      } catch (error) { $('#ai-skills-message').textContent = error.message; }
      finally { button.disabled = false; }
    });
    $('#ai-restore-skills').addEventListener('click', async () => {
      try { await api('/api/ai/skills/restore-defaults', { method: 'POST' }); await loadSkills(); }
      catch (error) { $('#ai-skills-message').textContent = error.message; }
    });
    $('#ai-provider').addEventListener('change', () => {
      const defaults = { openai: 'https://api.openai.com/v1', deepseek: 'https://api.deepseek.com/v1', ollama: 'http://127.0.0.1:11434/v1', anthropic: 'https://api.anthropic.com/v1' };
      if (!$('#ai-base-url').value || Object.values(defaults).includes($('#ai-base-url').value)) $('#ai-base-url').value = defaults[$('#ai-provider').value] || '';
    });
  }

  async function loadSkills() {
    const skills = await api('/api/ai/skills');
    $('#ai-skills-list').replaceChildren(...skills.map(skill => {
      const row = document.createElement('article');
      row.className = 'ai-skill-row';
      const description = document.createElement('div');
      description.append(textElement('strong', skill.name), textElement('p', skill.description, 'muted'));
      row.append(description);
      for (const edit of [true, false]) {
        const button = textElement('button', edit ? '编辑' : '删除', 'icon-button');
        button.type = 'button';
        button.addEventListener('click', async () => {
          try {
            if (edit) {
              const result = await api(`/api/ai/skills/${encodeURIComponent(skill.name)}`);
              $('#ai-skill-source').value = result.source;
              $('#ai-skill-form').hidden = false;
              $('#ai-skill-source').focus();
            } else if (window.confirm(`删除 Skill「${skill.name}」？`)) {
              await api(`/api/ai/skills/${encodeURIComponent(skill.name)}`, { method: 'DELETE' });
              await loadSkills();
            }
          } catch (error) { $('#ai-skills-message').textContent = error.message; }
        });
        row.append(button);
      }
      return row;
    }));
  }

  function fillSettings(settings) {
    $('#ai-enabled').checked = settings.enabled;
    $('#ai-provider').value = settings.provider;
    $('#ai-base-url').value = settings.base_url;
    $('#ai-model').value = settings.model;
    $('#ai-timeout').value = settings.timeout;
    $('#ai-key').value = '';
    $('#ai-clear-key').checked = false;
    $('#ai-settings-message').textContent = settings.has_api_key ? '已保存 API KEY，留空即可保留。' : '尚未保存 API KEY。';
  }

  async function submitSettings(test) {
    const form = $('#ai-settings-form');
    if (!form.reportValidity()) return;
    const payload = { enabled: $('#ai-enabled').checked, provider: $('#ai-provider').value, base_url: $('#ai-base-url').value.trim(), model: $('#ai-model').value.trim(), api_key: $('#ai-key').value || null, clear_api_key: $('#ai-clear-key').checked, timeout: Number($('#ai-timeout').value) };
    const message = $('#ai-settings-message');
    form.querySelectorAll('button').forEach(button => { button.disabled = true; });
    message.textContent = test ? '正在连接 LLM 并验证工具调用…' : '正在保存…';
    try {
      const result = await api(test ? '/api/ai/test' : '/api/ai/settings', { method: test ? 'POST' : 'PUT', body: JSON.stringify(payload), timeoutMs: (payload.timeout + 15) * 1000 });
      if (!test) { fillSettings(result); state.aiEnabled = result.enabled; }
      message.textContent = test ? result.message : 'AI 配置已保存';
    } catch (error) {
      message.textContent = error.message;
    } finally {
      form.querySelectorAll('button').forEach(button => { button.disabled = false; });
    }
  }

  window.JavspAI = {
    async loadSettings() {
      if (state.user?.role !== 'admin') return;
      settingsForm();
      try { fillSettings(await api('/api/ai/settings')); await loadSkills(); } catch (error) { $('#ai-settings-message').textContent = error.message; }
    },
    async load() {
      if (state.user?.role !== 'admin') return;
      window.scrollTo(0, 0);
      fitLayout();
      try {
        const settings = await api('/api/ai/settings');
        $('#ai-connection-status').textContent = settings.enabled ? `${settings.provider} · ${settings.model}` : '尚未启用 AI 刮削，请先到系统设置配置 LLM。';
        if (!loaded) {
          const saved = localStorage.getItem(storageKey());
          if (saved) {
            try { conversation = await api(`/api/ai/conversations/${encodeURIComponent(saved)}`); }
            catch (error) { localStorage.removeItem(storageKey()); $('#ai-status').textContent = error.message; }
          }
          loaded = true;
        }
        render();
        await loadHistory();
      } catch (error) { $('#ai-status').textContent = error.message; }
    },
  };
  if (document.querySelector('[data-panel="ai-scrape"].active')) window.JavspAI.load();
  if (document.querySelector('[data-panel="settings"].active')) window.JavspAI.loadSettings();
})();
