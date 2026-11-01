/* Hot discovery: no external requests in the browser; independent of app.js. */
(function () {
  'use strict';
  const LABELS = { unchecked: '未检测', ok: '可达', age_gate: '年龄确认', challenge: '验证拦截',
    region_blocked: '地区限制', maintenance: '维护中', parking: '疑似停放', js_shell: '前端空壳',
    denied: '拒绝访问', rate_limited: '请求受限', http_error: 'HTTP 错误', timeout: '超时',
    dns_error: 'DNS 失败', tls_error: '证书错误', network_error: '连接失败', unsafe_redirect: '不安全跳转',
    redirect_error: '跳转失败', not_html: '非网页', too_large: '超出上限', error: '失败',
    not_loaded: '待获取', parse_error: '解析失败', cookiecloud_error: 'CookieCloud 同步失败' };
  const state = { category: 'all', sort: 'latest', films: null, connections: null,
    generation: 0, connectionGeneration: 0, loading: false, checking: false, refreshPending: false, loaded: false,
    timer: null, checkingTimer: null, failedPolls: 0, checkFailedPolls: 0 };
  const $ = id => document.getElementById(id);
  const escape = value => String(value == null ? '' : value).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const categoryLabel = category => ({ censored: '有码', uncensored: '无码', all: '全部', unknown: '码类未知' }[category] || '未知');
  function safeUrl(value) {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : ''; }
    catch { return ''; }
  }
  function time(value) {
    if (!value) return '尚无成功快照';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString();
  }
  async function api(path, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('/api/hot' + path, { credentials: 'same-origin', cache: 'no-store',
        ...options, signal: controller.signal,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
      let data;
      try { data = await response.json(); } catch { throw new Error('服务器返回无效数据，请重试'); }
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败（${response.status}）`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('请求超时，请重试；服务端任务可能仍在进行');
      throw error;
    } finally { clearTimeout(timeout); }
  }
  function message(text, error = false) {
    $('hot-message').textContent = text;
    $('hot-message').dataset.error = String(error);
  }
  function card(item) {
    const sources = item.sources || [{ source_name: item.source_name, url: item.url, rank: item.rank }];
    const facts = [
      ['演员', (item.actors || []).join(' / ')], ['片商', item.studio], ['卖家', item.seller],
      [item.date_kind || '来源日期', item.date], ['时长', item.duration],
      ['评分', item.score != null ? `${item.score}${item.score_scale ? '/' + item.score_scale : ''}` : ''],
      ['浏览', item.views], ['收藏', item.favorites], ['评论', item.comments],
    ].filter(([, value]) => value != null && value !== '');
    const url = safeUrl(item.url);
    return `<article class="hot-card"><div class="hot-card-top"><span class="hot-type">${escape(categoryLabel(item.category))}</span>${item.rank ? `<span class="hot-rank" title="来源原始名次">#${escape(item.rank)}</span>` : ''}</div><p class="hot-identifier">${escape(item.identifier)}</p><h4>${url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${escape(item.title)}</a>` : escape(item.title)}</h4><dl class="hot-facts">${facts.map(([name, value]) => `<div><dt>${escape(name)}</dt><dd>${escape(value)}</dd></div>`).join('')}</dl><div class="hot-tags">${(item.tags || []).slice(0, 8).map(tag => `<span>${escape(tag)}</span>`).join('')}</div><details class="hot-card-sources"><summary>${sources.length} 个资料来源</summary>${sources.map(source => { const href = safeUrl(source.url); return `<p>${href ? `<a href="${escape(href)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${escape(source.source_name)} ↗</a>` : escape(source.source_name)}${source.rank ? ` · 原站 #${escape(source.rank)}` : ''}<small>${escape(source.label || '')}${source.stale ? ' · 缓存过期/刷新失败' : ''}${source.fetched_at ? ' · ' + escape(time(source.fetched_at)) : ''}</small></p>`; }).join('')}</details></article>`;
  }
  function renderFilms() {
    const data = state.films;
    if (!data) return;
    const groups = data.groups || [];
    // Older demo/server responses remain readable, but never reintroduce groups.
    const items = data.items || groups.flatMap(group => group.items || []);
    const failed = groups.filter(group => !['ok', 'not_loaded'].includes(group.state));
    const warnings = failed.length ? `<details class="hot-source-warnings"><summary>${failed.length} 个来源读取异常（成功数据仍保留）</summary>${failed.map(group => `<p>${escape(group.source_name)}：${escape(group.message)}${group.state === 'age_gate' || group.state === 'cookiecloud_error' ? '；请在设置启用 CookieCloud 并同步。' : ''}</p>`).join('')}</details>` : '';
    $('hot-results').innerHTML = warnings + (items.length ? `<div class="hot-grid" aria-label="统一热片影片墙">${items.map(card).join('')}</div>` : `<div class="hot-empty">暂无可用作品。点击“刷新列表”获取；连接限制详情请打开检测窗口。</div>`);
    const running = Boolean(data.job?.running);
    $('hot-results').setAttribute('aria-busy', String(running || state.loading));
    $('hot-refresh').disabled = running || state.refreshPending;
    $('hot-refresh').textContent = running ? `获取中 ${data.job.completed}/${data.job.total}` : '刷新列表';
    if (data.notice) $('hot-notice').textContent = data.notice;
    if (running) message(`正在获取来源列表 ${data.job.completed}/${data.job.total}；可切换分类，已成功结果会逐步显示。`);
    else message(`共 ${data.total || 0} 部 · ${categoryLabel(state.category)} · ${state.sort === 'hot' ? '最热（来源名次交错）' : '最新（日期降序）'}`);
  }
  function renderConnections() {
    const data = state.connections;
    if (!data) return;
    const sources = data.sources || [];
    const job = data.job || {};
    const checked = sources.filter(s => s.result?.state !== 'unchecked').length;
    const good = sources.filter(s => s.result?.state === 'ok').length;
    $('hot-connection-count').textContent = `${sources.length} 个站点 · ${good} 个可达 · 已检测 ${checked}`;
    const button = $('hot-check');
    button.disabled = false; // Always permit reopening the result dialog; server enforces permission/cooldown.
    button.textContent = job.running ? `检测中 ${job.completed}/${job.total}` : job.retry_after > 0 ? `检测连接（${job.retry_after}s）` : '检测连接';
    button.title = data.can_check === false ? '需要管理员权限' : '检测全部30站，不受影片分类影响';
    $('hot-check-message').textContent = job.running ? `正在检测 ${job.completed}/${job.total}，部分站点可能需要等待。` :
      job.finished_at ? `最近检测完成：${time(job.finished_at)} · 直连/可选 CookieCloud；异常/限制 ${checked - good} 个。` : '尚未检测。点击“检测连接”批量检测全部站点。';
    $('hot-check-progress').hidden = !job.running;
    $('hot-check-progress').max = job.total || 30;
    $('hot-check-progress').value = job.completed || 0;
    $('hot-source-list').innerHTML = sources.map(source => {
      const r = source.result || {};
      const url = safeUrl(source.url);
      return `<article class="hot-source" data-state="${escape(r.state)}"><div class="hot-source-heading">${url ? `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${escape(source.name)} ↗</a>` : `<strong>${escape(source.name)}</strong>`}<span class="hot-state">${escape(LABELS[r.state] || '未知')}</span></div><p>${escape(r.message)}</p>${r.state === 'age_gate' || r.state === 'cookiecloud_error' ? '<p class="hot-hint">请在浏览器完成年龄确认，再通过 CookieCloud 同步该域名 Cookie。<button class="button secondary" type="button" data-hot-cookiecloud>打开设置</button></p>' : ''}${r.state === 'region_blocked' ? '<button class="button secondary" type="button" data-hot-clash>诊断 Clash 出口</button>' : ''}<small class="muted">${r.http_status ? `HTTP ${escape(r.http_status)} · ` : ''}${r.elapsed_ms != null ? `${escape(r.elapsed_ms)} ms · ` : ''}${escape(r.checked_at ? time(r.checked_at) : '未检测')}</small></article>`;
    }).join('');
  }
  function active() { return document.querySelector('[data-panel="hot"]')?.classList.contains('active'); }
  function scheduleFilms() {
    clearTimeout(state.timer);
    if (active() && state.films?.job?.running) state.timer = setTimeout(() => loadFilms(), 1800);
  }
  async function loadFilms() {
    const generation = ++state.generation;
    state.loading = true;
    $('hot-results').setAttribute('aria-busy', 'true');
    try {
      const data = await api(`/films?category=${state.category}&sort=${state.sort}`);
      if (generation !== state.generation) return;
      state.failedPolls = 0;
      state.films = data;
      renderFilms();
      scheduleFilms();
    } catch (error) {
      if (generation !== state.generation) return;
      message(error.message + '。已显示的列表保留；点击刷新重试。', true);
      // A temporary disconnect during a batch should recover, but not poll forever.
      if (state.films?.job?.running && active() && ++state.failedPolls <= 3) {
        state.timer = setTimeout(() => loadFilms(), 3000 * state.failedPolls);
      } else {
        $('hot-refresh').disabled = false;
        $('hot-refresh').textContent = '重试刷新';
      }
    } finally {
      if (generation === state.generation) {
        state.loading = false;
        $('hot-results').setAttribute('aria-busy', String(Boolean(state.films?.job?.running)));
      }
    }
  }
  async function refreshFilms() {
    if (state.refreshPending) return;
    if (state.films?.job?.running) { await loadFilms(); return; }
    state.refreshPending = true;
    $('hot-refresh').disabled = true;
    try {
      await api('/refresh', { method: 'POST', body: JSON.stringify({ category: state.category, sort: state.sort }) });
      await loadFilms();
    } catch (error) { message(error.message, true); }
    finally {
      state.refreshPending = false;
      $('hot-refresh').disabled = Boolean(state.films?.job?.running);
    }
  }
  function scheduleConnections() {
    clearTimeout(state.checkingTimer);
    if (active() && (state.connections?.job?.running || state.connections?.job?.retry_after > 0))
      state.checkingTimer = setTimeout(() => loadConnections(), 2000);
  }
  async function loadConnections() {
    const generation = ++state.connectionGeneration;
    try {
      const data = await api('/connections');
      if (generation !== state.connectionGeneration) return;
      state.connections = data;
      state.checkFailedPolls = 0;
      renderConnections();
      scheduleConnections();
    } catch (error) {
      if (generation !== state.connectionGeneration) return;
      $('hot-check-message').textContent = error.message + '；点击检测连接可重试/恢复任务状态。';
      if (active() && ++state.checkFailedPolls <= 3) state.checkingTimer = setTimeout(() => loadConnections(), 3000 * state.checkFailedPolls);
      else { $('hot-check').disabled = false; $('hot-check').textContent = '重试检测状态'; }
    }
  }
  async function checkConnections() {
    openDialog('hot-connections');
    if (state.checking) return;
    if (state.connections?.can_check === false || state.connections?.job?.running || state.connections?.job?.retry_after > 0) { await loadConnections(); return; }
    state.checking = true;
    const generation = ++state.connectionGeneration;
    clearTimeout(state.checkingTimer);
    $('hot-check').disabled = false;
    openDialog('hot-connections');
    let failure = '';
    try {
      const data = await api('/connections', { method: 'POST', body: '{}' });
      if (generation !== state.connectionGeneration) return;
      state.connections = data;
      renderConnections();
      scheduleConnections();
    } catch (error) { failure = error.message; }
    finally {
      state.checking = false;
      if (state.connections) renderConnections(); else $('hot-check').disabled = false;
      if (failure) $('hot-check-message').textContent = failure;
    }
  }
  function openDialog(id) {
    const dialog = $(id);
    if (dialog && !dialog.open) dialog.showModal();
  }
  function cookieSettings() {
    $('hot-connections')?.close();
    document.querySelector('[data-view="settings"]')?.click();
    document.querySelector('[data-settings-tab="connections"]')?.click();
    const panel = $('cookiecloud-panel');
    if (panel) { panel.open = true; panel.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
  }
  function syncControls() {
    document.querySelectorAll('[data-hot-category]').forEach(tab => {
      const selected = tab.dataset.hotCategory === state.category;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll('[data-hot-sort]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.hotSort === state.sort)));
    $('hot-results').setAttribute('aria-labelledby', 'hot-tab-' + state.category);
  }
  async function select(category, sort) {
    state.category = category;
    state.sort = sort;
    try { localStorage.setItem('javsp-web.hot-filter', JSON.stringify({ category, sort })); } catch { /* optional */ }
    syncControls();
    // Clear the previous category before awaiting: never show censored items
    // under an uncensored selected tab, including when a request fails.
    state.films = null;
    clearTimeout(state.timer);
    $('hot-results').innerHTML = '<p class="muted">正在读取此分类…</p>';
    await loadFilms();
  }
  function init() {
    const panel = $('hot-panel');
    if (!panel || panel.dataset.bound) return;
    panel.dataset.bound = '1';
    try {
      const saved = JSON.parse(localStorage.getItem('javsp-web.hot-filter'));
      if (['all', 'censored', 'uncensored'].includes(saved?.category)) state.category = saved.category;
      if (['latest', 'hot'].includes(saved?.sort)) state.sort = saved.sort;
    } catch { /* keep defaults */ }
    syncControls();
    document.querySelectorAll('[data-hot-category]').forEach(tab => {
      tab.addEventListener('click', () => select(tab.dataset.hotCategory, state.sort));
      tab.addEventListener('keydown', event => {
        const tabs = [...document.querySelectorAll('[data-hot-category]')];
        const index = tabs.indexOf(tab);
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        if (next == null) return;
        event.preventDefault();
        tabs[next].focus();
        select(tabs[next].dataset.hotCategory, state.sort);
      });
    });
    document.querySelectorAll('[data-hot-sort]').forEach(button => button.addEventListener('click', () => select(state.category, button.dataset.hotSort)));
    $('hot-refresh').addEventListener('click', refreshFilms);
    $('hot-check').addEventListener('click', checkConnections);
    $('hot-show-connections').addEventListener('click', () => { openDialog('hot-connections'); loadConnections(); });
    $('hot-connections-close').addEventListener('click', () => $('hot-connections').close());
    $('hot-connections').addEventListener('click', event => {
      if (event.target.closest('[data-hot-cookiecloud]')) cookieSettings();
      if (event.target.closest('[data-hot-clash]')) window.JavspHotClash?.open();
    });
    $('hot-connections').addEventListener('close', () => $('hot-check').focus());
    const view = document.querySelector('[data-panel="hot"]');
    async function enter() {
      if (!active()) { clearTimeout(state.timer); clearTimeout(state.checkingTimer); return; }
      await Promise.all([loadFilms(), loadConnections()]);
      state.loaded = true;
    }
    new MutationObserver(enter).observe(view, { attributes: true, attributeFilter: ['class'] });
    if (active()) enter();
  }
  window.JavspHot = { init, api, safeUrl, escape, openDialog, state, select, loadFilms, refreshFilms, loadConnections, checkConnections };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
