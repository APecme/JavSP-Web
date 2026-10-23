/* 目录监控面板：独立于 app.js 的状态，只依赖公开的管理员 API。
   挂载点 <div id="directory-watch-panel"> 由 index.html 提供，
   其余标记与交互都在这里生成，避免改动既有自动化页逻辑。 */
(function () {
  'use strict';

  const ENDPOINT = '/api/directory-watch/rules';
  const STATE_LABELS = {
    ok: '运行中',
    error: '需要处理',
    offline: '目录离线',
    disabled: '已暂停',
    initializing: '准备中',
  };
  const POLL = 15000;
  const state = { rules: [], limits: null, scheduler: null, presets: [], presetsLoaded: false, loaded: false, loading: false, editing: null, busy: false };

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (character) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[character]));
  }

  async function api(path, options) {
    const request = Object.assign({ credentials: 'same-origin', headers: {} }, options || {});
    if (request.body) request.headers['Content-Type'] = 'application/json';
    const response = await fetch(path, request);
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (error) { data = {}; }
    if (!response.ok) {
      const detail = data && (data.detail || data.error);
      throw new Error(typeof detail === 'string' && detail ? detail : `请求失败（${response.status}）`);
    }
    return data;
  }

  function formatTime(value) {
    if (!value) return '尚未扫描';
    return String(value).replace('T', ' ').replace(/(\+|Z)[\d:]*$/, '').slice(0, 16);
  }

  function presetName(id) {
    const preset = (state.presets || []).find((item) => item.id === id);
    return preset ? (preset.name || preset.id) : id;
  }

  function badge(stateName) {
    const label = STATE_LABELS[stateName] || stateName || '运行中';
    return `<span class="dw-badge" data-state="${escapeHtml(stateName || 'ok')}">${escapeHtml(label)}</span>`;
  }

  function rowMarkup(rule) {
    const status = rule.status || {};
    const scheduled = rule.trigger === 'schedule';
    const facts = [
      ['预设', presetName(rule.preset_id)],
      ...(scheduled ? [['触发方式', '定时全量扫描'], ['Cron', rule.cron], ['下次运行', formatTime(rule.next_run_at)]]
        : [['触发方式', '目录轮询'], ['扫描间隔', `${rule.poll_seconds} 秒`], ['稳定等待', `${rule.stable_seconds} 秒`]]),
      ['最近扫描', formatTime(status.last_scan_at)],
      ['已提交', `${status.submitted_total || 0} 个任务`],
      ['已记录', `${status.committed || 0} 个文件`],
    ];
    const pending = status.pending ? `<span class="dw-pending">${status.pending} 个文件等待稳定</span>` : '';
    return `<article class="dw-row" data-dw-rule="${escapeHtml(rule.id)}" data-state="${escapeHtml(status.state || 'ok')}">
      <div class="dw-row-main">
        <div class="dw-row-title"><strong>${escapeHtml(rule.name)}</strong>${badge(status.state)}
          <span class="dw-flag">${scheduled ? '定时全量' : (rule.include_existing ? '处理已有文件' : '仅新增或变化')}</span>
          <span class="dw-flag">${scheduled || rule.recursive ? '含子目录' : '仅当前目录'}</span>
          ${pending}
        </div>
        <p class="dw-path" title="${escapeHtml(rule.path)}">${escapeHtml(rule.path)}</p>
        <dl class="dw-facts">${facts.map(([name, value]) => `<div><dt>${escapeHtml(name)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl>
        <p class="dw-message" role="status">${escapeHtml(status.message || '')}</p>
      </div>
      <div class="dw-row-actions">
        <button class="button secondary" type="button" data-dw-scan="${escapeHtml(rule.id)}">${scheduled ? '立即运行' : '立即扫描'}</button>
        <button class="button secondary" type="button" data-dw-toggle="${escapeHtml(rule.id)}">${rule.enabled ? '暂停' : '启用'}</button>
        <button class="button secondary" type="button" data-dw-edit="${escapeHtml(rule.id)}">编辑</button>
        ${scheduled ? `<button class="button secondary" type="button" data-dw-history="${escapeHtml(rule.id)}">运行记录 (${(rule.history?.runs || []).length})</button>`
          : `<button class="button secondary" type="button" data-dw-reset="${escapeHtml(rule.id)}">重置观察状态</button>`}
        <button class="button danger" type="button" data-dw-delete="${escapeHtml(rule.id)}">删除</button>
      </div>
    </article>`;
  }

  function render() {
    const summary = document.getElementById('auto-scrape-watch-status');
    if (summary) summary.textContent = `${state.rules.length} 条规则 · ${state.rules.filter(rule => rule.enabled).length} 条启用`;
    const list = $('#dw-list');
    if (!list) return;
    const rules = state.rules || [];
    list.classList.toggle('empty', rules.length === 0);
    if (!rules.length) {
      list.innerHTML = '<p class="dw-empty">尚未添加自动刮削规则。可选择目录监控新增文件，或定时全量扫描。</p>';
    } else {
      list.innerHTML = rules.map(rowMarkup).join('');
    }
    const scheduler = state.scheduler || {};
    const hint = $('#dw-runtime');
    if (hint) {
      hint.textContent = scheduler.demo
        ? '示例模式：不访问真实目录。'
        : (scheduler.thread_running ? '统一调度正在运行：监控模式按间隔轮询，定时模式按 Cron 全量扫描。' : '统一调度尚未运行，仍可使用手动触发。');
      hint.dataset.running = scheduler.demo ? 'demo' : (scheduler.thread_running ? '1' : '0');
    }
  }

  function setMessage(text, tone) {
    const node = $('#dw-message');
    if (!node) return;
    node.textContent = text || '';
    node.dataset.tone = tone || '';
  }

  async function load(options) {
    if (state.loading) return;
    if (!state.loaded) {
      const list = $('#dw-list');
      if (list) list.textContent = '正在读取监控规则';
    }
    state.loading = true;
    try {
      const data = await api(ENDPOINT);
      state.rules = data.rules || [];
      state.limits = data.limits || state.limits;
      state.scheduler = data.scheduler || {};
      state.loaded = true;
      syncLimits();
      if (!state.presetsLoaded) await loadPresets();
      render();
      if (!(options && options.silent)) setMessage('');
    } catch (error) {
      setMessage(error.message || '读取监控规则失败', 'error');
      const list = $('#dw-list');
      if (list && !state.loaded) list.textContent = '无法读取监控规则';
    } finally {
      state.loading = false;
    }
  }

  function syncLimits() {
    const limits = state.limits;
    if (!limits) return;
    const bind = (id, key) => {
      const input = $(`#${id}`);
      const limit = limits[key];
      if (!input || !limit) return;
      input.min = limit.min;
      input.max = limit.max;
      if (!input.value) input.value = limit.default;
    };
    bind('dw-poll', 'poll_seconds');
    bind('dw-stable', 'stable_seconds');
    bind('dw-max', 'max_tasks_per_scan');
  }

  async function loadPresets() {
    try {
      const presets = await api('/api/presets');
      state.presets = Array.isArray(presets) ? presets : [];
      state.presetsLoaded = true;
    } catch (error) {
      state.presets = [];
      return;
    }
    const select = $('#dw-preset');
    if (!select) return;
    select.innerHTML = state.presets.map((preset) => (
      `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.name || preset.id)}</option>`
    )).join('');
  }

  function fillPresetSelect(selected) {
    const select = $('#dw-preset');
    if (!select) return;
    if (selected && !state.presets.some((preset) => preset.id === selected)) {
      // A rule whose preset was deleted must not silently switch to another one.
      select.insertAdjacentHTML('afterbegin',
        `<option value="${escapeHtml(selected)}">${escapeHtml(selected)}（预设已删除）</option>`);
    }
    if (selected) select.value = selected;
  }

  function syncTrigger() {
    const scheduled = $('#dw-trigger-schedule').checked;
    $('#dw-watch-fields').hidden = scheduled;
    $('#dw-schedule-fields').hidden = !scheduled;
    $('#dw-cron').required = scheduled;
    $('#dw-cron').disabled = !scheduled;
    $('#dw-watch-fields').querySelectorAll('input, textarea').forEach(input => { input.disabled = scheduled; });
  }

  function openDialog(rule) {
    state.editing = rule || null;
    const form = $('#dw-form');
    if (!form) return;
    $('#dw-dialog-title').textContent = rule ? '编辑自动刮削规则' : '添加自动刮削规则';
    $('#dw-trigger-watch').checked = rule?.trigger !== 'schedule';
    $('#dw-trigger-schedule').checked = rule?.trigger === 'schedule';
    $('#dw-cron').value = rule?.cron || '0 2 * * *';
    syncTrigger();
    $('#dw-name').value = rule ? rule.name || '' : '';
    $('#dw-path').value = rule ? rule.path || '' : '';
    $('#dw-enabled').checked = rule ? rule.enabled !== false : true;
    $('#dw-recursive').checked = rule ? rule.recursive !== false : true;
    $('#dw-include-existing').checked = Boolean(rule && rule.include_existing);
    $('#dw-poll').value = rule ? rule.poll_seconds : (state.limits ? state.limits.poll_seconds.default : 30);
    $('#dw-stable').value = rule ? rule.stable_seconds : (state.limits ? state.limits.stable_seconds.default : 60);
    $('#dw-max').value = rule ? rule.max_tasks_per_scan : (state.limits ? state.limits.max_tasks_per_scan.default : 20);
    $('#dw-exclude').value = rule ? (rule.exclude || []).join('\n') : '';
    $('#dw-form-message').textContent = '';
    $('#dw-delete').classList.toggle('hidden', !rule);
    $('#dw-delete').dataset.dwDelete = rule ? rule.id : '';
    $('#dw-delete').dataset.confirm = '';
    $('#dw-delete').textContent = '删除';
    fillPresetSelect(rule ? rule.preset_id : (state.presets[0] || {}).id);
    if (!state.presetsLoaded) loadPresets().then(() => fillPresetSelect(rule ? rule.preset_id : ''));
    $('#dw-dialog').showModal();
  }

  function payload() {
    const poll = Number($('#dw-poll').value || 0);
    const stable = Number($('#dw-stable').value || 0);
    const max = Number($('#dw-max').value || 0);
    const exclude = $('#dw-exclude').value.split('\n').map((line) => line.trim()).filter(Boolean);
    return {
      name: $('#dw-name').value.trim(),
      trigger: $('#dw-trigger-schedule').checked ? 'schedule' : 'watch',
      cron: $('#dw-trigger-schedule').checked ? $('#dw-cron').value.trim() : '',
      path: $('#dw-path').value.trim(),
      preset_id: $('#dw-preset').value || 'default',
      enabled: $('#dw-enabled').checked,
      recursive: $('#dw-recursive').checked,
      include_existing: $('#dw-include-existing').checked,
      poll_seconds: poll,
      stable_seconds: stable,
      max_tasks_per_scan: max,
      exclude,
    };
  }

  async function save(event) {
    event.preventDefault();
    if (state.busy) return;
    const message = $('#dw-form-message');
    message.textContent = '';
    state.busy = true;
    try {
      const body = JSON.stringify(payload());
      const editing = state.editing;
      if (editing) await api(`${ENDPOINT}/${encodeURIComponent(editing.id)}`, { method: 'PUT', body });
      else await api(ENDPOINT, { method: 'POST', body });
      $('#dw-dialog').close();
      setMessage('规则已保存；定时模式按 Cron 全量运行，监控模式按观察基线检查变化');
      await load({ silent: true });
    } catch (error) {
      message.textContent = error.message || '保存失败';
    } finally {
      state.busy = false;
    }
  }

  async function ruleAction(ruleId, action, confirmText) {
    if (state.busy) return;
    state.busy = true;
    setMessage(confirmText || '正在处理…');
    try {
      if (action === 'scan') {
        const result = await api(`${ENDPOINT}/${encodeURIComponent(ruleId)}/scan`, { method: 'POST' });
        setMessage(result.message || '扫描完成');
      } else if (action === 'pause' || action === 'resume') {
        await api(`${ENDPOINT}/${encodeURIComponent(ruleId)}/${action}`, { method: 'POST' });
        setMessage(action === 'pause' ? '规则已暂停，不再提交新文件' : '规则已启用');
      } else if (action === 'delete') {
        await api(`${ENDPOINT}/${encodeURIComponent(ruleId)}`, { method: 'DELETE' });
        setMessage('规则已删除');
        state.rules = state.rules.filter((rule) => rule.id !== ruleId);
      } else if (action === 'reset') {
        await api(`${ENDPOINT}/${encodeURIComponent(ruleId)}/reset`, { method: 'POST' });
        setMessage('观察状态已重置：当前文件重新记为基线，不会重复提交');
      }
      await load({ silent: true });
    } catch (error) {
      setMessage(error.message || '操作失败', 'error');
    } finally {
      state.busy = false;
    }
  }

  function findRule(ruleId) {
    return (state.rules || []).find((rule) => rule.id === ruleId);
  }

  function handleClick(event) {
    const history = event.target.closest('[data-dw-history]');
    if (history) {
      window.JavspAutomationHistory?.open(history.dataset.dwHistory).catch(error => setMessage(error.message, 'error'));
      return;
    }
    const scan = event.target.closest('[data-dw-scan]');
    if (scan) { ruleAction(scan.dataset.dwScan, 'scan'); return; }
    const toggle = event.target.closest('[data-dw-toggle]');
    if (toggle) {
      const rule = findRule(toggle.dataset.dwToggle);
      if (rule) ruleAction(rule.id, rule.enabled ? 'pause' : 'resume');
      return;
    }
    const edit = event.target.closest('[data-dw-edit]');
    if (edit) { openDialog(findRule(edit.dataset.dwEdit)); return; }
    const reset = event.target.closest('[data-dw-reset]');
    if (reset) {
      if (reset.dataset.confirm === '1') {
        reset.dataset.confirm = '';
        reset.textContent = '重置观察状态';
        ruleAction(reset.dataset.dwReset, 'reset');
      } else {
        reset.dataset.confirm = '1';
        reset.textContent = '再次点击确认重置';
        setTimeout(() => {
          if (reset.dataset.confirm === '1') {
            reset.dataset.confirm = '';
            reset.textContent = '重置观察状态';
          }
        }, 6000);
      }
      return;
    }
    const remove = event.target.closest('[data-dw-delete]');
    if (remove) {
      if (remove.dataset.confirm !== '1') {
        remove.dataset.confirm = '1';
        remove.textContent = '再次点击确认删除';
        setTimeout(() => {
          if (remove.dataset.confirm === '1') {
            remove.dataset.confirm = '';
            remove.textContent = '删除';
          }
        }, 6000);
        return;
      }
      remove.dataset.confirm = '';
      remove.textContent = '删除';
      const ruleId = remove.dataset.dwDelete || remove.dataset.dwRule;
      if (ruleId && $('#dw-dialog').open) $('#dw-dialog').close();
      if (ruleId) ruleAction(ruleId, 'delete');
    }
  }

  function bindOnce() {
    const host = $('#directory-watch-panel');
    if (!host || host.dataset.dwBound === '1') return;
    host.dataset.dwBound = '1';
    // Embedded in the auto-scrape watch module the surrounding panel + h2 already
    // label this content, so only the toolbar and rules are rendered. A standalone
    // mount (no watch module ancestor) keeps its own panel and h3 heading.
    const embedded = typeof host.closest === 'function'
      && Boolean(host.closest('[data-auto-scrape-module="watch"]'));
    const heading = embedded ? '' : `
      <div class="panel-heading">
        <div>
          <h3>自动刮削规则</h3>
          <p class="muted">每条规则只选择一种触发方式：监控新增（轮询与稳定等待），或按 Cron 定时全量扫描。</p>
        </div>
      </div>`;
    host.innerHTML = `<div class="${embedded ? 'dw-embed' : 'panel dw-panel'}">${heading}
      <div class="dw-toolbar">
        <div class="dw-heading-actions">
          <button class="button primary" type="button" id="dw-add">添加规则</button>
          <button class="button secondary" type="button" id="dw-refresh">刷新</button>
        </div>
      </div>
      <div id="dw-list" class="dw-list empty">正在读取监控规则</div>
      <p id="dw-message" class="dw-message" role="status" aria-live="polite"></p>
      <p id="dw-runtime" class="dw-runtime">正在读取调度状态</p>
    </div>`;

    const dialog = document.createElement('dialog');
    dialog.id = 'dw-dialog';
    dialog.className = 'app-dialog dw-dialog';
    dialog.innerHTML = `<form method="dialog" id="dw-form" class="dialog-form">
      <div class="dialog-heading"><h2 id="dw-dialog-title">添加目录监控规则</h2>
        <button class="dialog-close" type="button" data-dw-close aria-label="关闭">关闭</button></div>
      <div class="dialog-content">
        <label>规则名称<input id="dw-name" maxlength="80" placeholder="例如：下载完成目录"></label>
        <fieldset class="dw-trigger"><legend>触发方式（单选）</legend>
          <label class="check-label"><input type="radio" name="dw-trigger" id="dw-trigger-watch" value="watch" checked>监控新增</label>
          <label class="check-label"><input type="radio" name="dw-trigger" id="dw-trigger-schedule" value="schedule">定时全量</label>
        </fieldset>
        <div id="dw-schedule-fields" hidden><label>Cron 时间<input id="dw-cron" placeholder="0 2 * * *" disabled></label>
          <small class="muted">标准五段 Cron，使用服务端配置时区。每次触发全量扫描目录，不使用监控成功台账。</small></div>
        <label>刮削目录<input id="dw-path" maxlength="2048" required placeholder="例如：/media/downloads"></label>
        <div class="dw-path-tools">
          <button class="button secondary" type="button" id="dw-pick">选择文件夹</button>
          <small class="muted">请填写已挂载到容器内的绝对路径；Docker 环境请直接填写容器路径。</small>
        </div>
        <label>刮削预设<select id="dw-preset"></select></label>
        <div id="dw-watch-fields"><div class="dw-grid">
          <label>扫描间隔（秒）<input id="dw-poll" type="number" step="1" min="5" max="3600" value="30"></label>
          <label>稳定等待（秒）<input id="dw-stable" type="number" step="1" min="0" max="86400" value="60"></label>
          <label>单次最多提交<input id="dw-max" type="number" step="1" min="1" max="100" value="20"></label>
        </div>
        <small class="muted">扫描间隔为轮询周期；稳定等待内文件大小或修改时间仍在变化时不会提交，避免处理还在写入的文件。</small>
        <label class="check-label"><input id="dw-recursive" type="checkbox" checked>包含子目录</label>
        <label class="check-label"><input id="dw-include-existing" type="checkbox">首次扫描也处理目录中已有的文件</label>
        <small class="muted">不勾选时，保存规则那一刻已存在的文件只记为基线，仅提交之后新增或变化的文件。</small>
        <label>排除规则<textarea id="dw-exclude" rows="3" placeholder="每行一条，例如：&#10;sample&#10;*.nfo&#10;@eaDir"></textarea></label>
        <small class="muted">按文件名或相对路径匹配；输出目录、临时下载文件与隐藏目录始终会被跳过。</small>
        </div><label class="check-label"><input id="dw-enabled" type="checkbox" checked>启用此规则</label>
      </div>
      <span id="dw-form-message" class="form-error dialog-message" role="alert"></span>
      <div class="dialog-actions">
        <button class="button danger hidden" id="dw-delete" type="button">删除</button>
        <button class="button secondary" type="button" data-dw-close>取消</button>
        <button class="button primary" type="submit">保存规则</button>
      </div>
    </form>`;
    document.body.appendChild(dialog);

    $('#dw-add').addEventListener('click', () => openDialog(null));
    $('#dw-refresh').addEventListener('click', () => load());
    $('#dw-form').addEventListener('submit', save);
    $('#dw-trigger-watch').addEventListener('change', syncTrigger);
    $('#dw-trigger-schedule').addEventListener('change', syncTrigger);
    $('#dw-pick').addEventListener('click', async () => {
      const message = $('#dw-form-message');
      message.textContent = '';
      try {
        const picked = await api('/api/path/select', { method: 'POST', body: JSON.stringify({ kind: 'directory' }) });
        if (picked && picked.path) $('#dw-path').value = picked.path;
      } catch (error) {
        message.textContent = error.message || '无法打开系统选择窗口';
      }
    });
    dialog.querySelectorAll('[data-dw-close]').forEach((button) => (
      button.addEventListener('click', () => dialog.close())
    ));
    $('#dw-delete').addEventListener('click', () => {
      const button = $('#dw-delete');
      const ruleId = button.dataset.dwDelete;
      if (!ruleId) return;
      if (button.dataset.confirm !== '1') {
        button.dataset.confirm = '1';
        button.textContent = '再次点击确认删除';
        return;
      }
      button.dataset.confirm = '';
      button.textContent = '删除';
      dialog.close();
      ruleAction(ruleId, 'delete');
    });
    $('#dw-list').addEventListener('click', handleClick);
    dialog.addEventListener('close', () => { state.editing = null; });
  }

  function viewActive() {
    const view = document.querySelector('[data-panel="auto-scrape"]');
    return Boolean(view && view.classList.contains('active'));
  }

  function watchView() {
    const view = document.querySelector('[data-panel="auto-scrape"]');
    if (!view || view.dataset.dwWatched === '1') return;
    view.dataset.dwWatched = '1';
    const observer = new MutationObserver(() => {
      if (viewActive()) load({ silent: state.loaded });
    });
    observer.observe(view, { attributes: true, attributeFilter: ['class'] });
  }

  function init() {
    if (!$('#directory-watch-panel')) return;
    bindOnce();
    watchView();
    if (viewActive()) load();
    window.setInterval(() => {
      const dialog = $('#dw-dialog');
      if (!viewActive() || (dialog && dialog.open) || state.busy) return;
      load({ silent: true });
    }, POLL);
  }

  window.JavspDirectoryWatch = { load, init, state };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
