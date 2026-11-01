/* Explicitly-confirmed administrator diagnostics; never store secrets/YAML. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  let job = null, timer = null, posting = false, exporting = false, generation = 0;
  const esc = value => window.JavspHot.escape(value);
  const api = (...args) => window.JavspHot.api(...args);
  function message(text) { $('hot-clash-message').textContent = text; }
  function render() {
    if (!job) return;
    message(`${job.message || '尚未开始'}${job.running ? ` · ${job.completed}/${job.total}` : ''}`);
    $('hot-clash-message').dataset.error = String(job.restore_state === 'failed');
    $('hot-clash-start').disabled = posting || Boolean(job.running);
    $('hot-clash-cancel').disabled = !job.running;
    $('hot-clash-export').disabled = job.running || job.restore_state !== 'restored';
    $('hot-clash-results').innerHTML = (job.results || []).map(row => {
      const good = !row.error && row.exit?.ip && (row.sites || []).some(s => s.state === 'ok');
      return `<article class="hot-clash-row"><label class="check-label"><input type="checkbox" data-hot-node value="${esc(row.name)}" ${good ? '' : 'disabled'}>${esc(row.name)}</label><p>${esc(row.exit?.ip || '出口未知')} · ${esc(row.exit?.country || '地区未知')}</p><p>${esc(row.error || row.exit?.error || '')}</p><ul>${(row.sites || []).map(s => `<li>${esc(s.source_id)}：${esc(s.message)}${s.state === 'age_gate' ? '；请使用 CookieCloud 同步年龄确认后的 Cookie' : ''}</li>`).join('')}</ul></article>`;
    }).join('');
  }
  function schedule() {
    clearTimeout(timer);
    if (job?.running && $('hot-clash-dialog').open) timer = setTimeout(load, 2000);
  }
  async function load() {
    if (posting) return;
    const request = ++generation;
    try { const data = await api('/clash'); if (request !== generation) return; job = data; render(); schedule(); }
    catch (error) { message(error.message + '。控制器可能仍处于测试状态，请刷新任务状态或取消；必要时手动恢复。'); }
  }
  async function open() {
    window.JavspHot.openDialog('hot-clash-dialog');
    if (!$('hot-clash-sites').options.length) {
      try {
        const connections = await api('/connections');
        $('hot-clash-sites').innerHTML = (connections.sources || []).map(s => `<option value="${esc(s.id)}" ${s.result?.state === 'region_blocked' ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
      } catch (error) { message(error.message); }
    }
    await load();
  }
  async function start(event) {
    event.preventDefault();
    if (posting || job?.running) return;
    const ids = [...$('hot-clash-sites').selectedOptions].map(o => o.value);
    if (ids.length < 1 || ids.length > 3) { message('请选择1–3个测试站点'); return; }
    if (!$('hot-clash-confirm').checked) { message('必须确认临时切换影响'); return; }
    posting = true;
    ++generation;
    clearTimeout(timer);
    $('hot-clash-start').disabled = true;
    try {
      job = await api('/clash', { method: 'POST', body: JSON.stringify({
        controller_url: $('hot-clash-controller').value.trim(), secret: $('hot-clash-secret').value,
        proxy_url: $('hot-clash-proxy').value.trim(), source_ids: ids, confirm_switch: true,
      }) });
      $('hot-clash-secret').value = '';
      $('hot-clash-confirm').checked = false;
      render(); schedule();
      if (!$('hot-clash-dialog').open && job.running) await cancel();
    } catch (error) { message(error.message + '。如果请求已发出，请刷新状态确认是否仍在测试。'); }
    finally { posting = false; $('hot-clash-start').disabled = Boolean(job?.running); }
  }
  async function cancel() {
    const request = ++generation;
    try { const data = await api('/clash/cancel', { method: 'POST', body: '{}' }); if (request !== generation) return; job = data; render(); schedule(); }
    catch (error) { message(error.message + '；请检查面板并手动恢复原模式与 GLOBAL 节点。'); }
  }
  async function download() {
    if (exporting || !job || job.running || job.restore_state !== 'restored') return;
    const selected = [...document.querySelectorAll('[data-hot-node]:checked')].map(node => node.value);
    const file = $('hot-clash-yaml').files[0];
    if (!selected.length || !file) { message('请选择通过测试的节点并上传原始完整 YAML'); return; }
    if (file.size > 1_000_000) { message('YAML 不得超过1MB'); return; }
    exporting = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('/api/hot/clash/export', { method: 'POST', credentials: 'same-origin',
        cache: 'no-store', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ original_yaml: await file.text(), selected_nodes: selected, job_id: job.id }) });
      if (!response.ok) { const error = await response.json(); throw new Error(error.detail || '导出失败'); }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = 'javsp-clash.yaml';
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      $('hot-clash-yaml').value = '';
      message('已下载完整配置；包含原配置密钥，请先备份并在 Clash 校验后手动覆盖。未自动改写或安装。');
    } catch (error) { message(error.name === 'AbortError' ? '导出超时，请重试' : error.message); }
    finally { clearTimeout(timeout); exporting = false; }
  }
  function init() {
    if (!$('hot-clash-dialog')) return;
    $('hot-clash-form').addEventListener('submit', start);
    $('hot-clash-cancel').addEventListener('click', cancel);
    $('hot-clash-status').addEventListener('click', load);
    $('hot-clash-export').addEventListener('click', download);
    $('hot-clash-close').addEventListener('click', () => $('hot-clash-dialog').close());
    $('hot-clash-dialog').addEventListener('close', () => {
      clearTimeout(timer); $('hot-clash-secret').value = ''; $('hot-clash-confirm').checked = false;
      // Closing is an explicit cancellation request, followed by server restore.
      if (job?.running) cancel();
    });
  }
  window.JavspHotClash = { open, load };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
