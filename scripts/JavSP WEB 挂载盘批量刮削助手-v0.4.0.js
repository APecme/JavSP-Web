// ==UserScript==
// @name         JavSP WEB 挂载盘批量刮削助手
// @namespace    https://github.com/APecme/JavSP-Web
// @version      0.4.1
// @description  登录页一键登录；批量选择挂载盘视频并统一提交后台扫描；按确认的任务列表清理手动任务记录。
// @match        http://127.0.0.1:8090/*
// @match        http://localhost:8090/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

/* ============================================================================
 *   JavSP WEB 挂载盘批量刮削助手
 * ============================================================================
 *
 *  1. 功能与使用
 *  将本脚本安装到 Tampermonkey，打开本机 JavSP WEB 后可批量选择视频。
 *  整个文件列表一次提交到后台扫描，保留分 P 分组和预设并发限制。
 *  提交成功不代表影片已经刮削完成，请在任务页查看进度。
 *  目录扫描的修复由 PR #14 配套后端提供；请一起升级服务端。
 *  本脚本的面板和一键登录为可选功能，Web 页面也提供原生多选入口。
 *
 *  2. 兼容与限制
 *  需要支持 input_files 和 HTTP 202 扫描任务的 JavSP WEB 服务端。
 *  本机多选依赖 tkinter 交互式桌面；Docker 请使用网页路径浏览器。
 *  默认只匹配 localhost:8090 和 127.0.0.1:8090，其他地址请修改 @match。
 *  队列仅保存在当前页面，刷新页面后未提交的文件列表会丢失。
 *  点击停止会请求取消当前扫描；已经生成的影片任务需在任务页停止。
 *
 *  3. 任务清理
 *  先读取所选状态的手动任务，确认数量后按明确 ID 清理。
 *  操作前再次检查任务来源和状态，运行中任务先取消，再删除记录。
 *  列表加载失败时停止，不依赖页面上的旧卡片或隐藏弹窗。
 *
 *  4. 登录配置
 *  可在脚本内配置 LOGIN_USER / LOGIN_PASS，分享脚本前请清除个人账号信息。
 *
 *  5. 致谢
 *  --------------------------------------------------------------------------
 *  感谢 JavSP WEB 作者 APecme 提供这个好用的刮削工具：
 *  https://github.com/APecme/JavSP-Web
 *
 *  6. 本脚本作者
 *  --------------------------------------------------------------------------
 *  usePattern
 *  https://github.com/usePattern/JavSP-Web
 * ========================================================================== */

(function () {
  'use strict';

  /* ====================== 可配置项 ====================== */
  const LOGIN_USER = 'admin';      // 登录用户名
  const LOGIN_PASS = 'admin';      // 登录密码
  /* ===================================================== */

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const $ = (sel) => document.querySelector(sel);

  /* ---------------- 登录页：一键登录 ---------------- */
  if (/\/login(\/|$)/.test(location.pathname)) {
    (function loginPage() {
      const u = $('#username'), p = $('#password'), form = $('#login-form');
      if (!u || !p || !form) { setTimeout(loginPage, 200); return; }
      u.value = LOGIN_USER;
      p.value = LOGIN_PASS;
      const btn = document.createElement('button');
      btn.className = 'button primary';
      btn.type = 'button';
      btn.textContent = `一键登录（${LOGIN_USER}）`;
      btn.style.cssText = 'margin-top:10px;width:100%;';
      btn.onclick = () => {
        $('#username').value = LOGIN_USER;
        $('#password').value = LOGIN_PASS;
        form.querySelector('button[type="submit"]').click();
      };
      form.appendChild(btn);
    })();
    return; // 登录页不加载批量面板
  }

  let files = [];
  let running = false;
  let stopRequested = false;
  let picking = false;
  let multiSupported = null;
  let deleting = false;
  let activeScanId = null;

  const STATUS_LABEL = {
    pending: '待处理', submitting: '提交中', done: '已提交', error: '失败', picking: '选择中'
  };

  /* ---------------- 样式 ---------------- */
  const css = `
  #jcb-panel { position: fixed; top: 76px; right: 16px; width: 420px; max-height: 80vh;
    display: flex; flex-direction: column; z-index: 99999;
    background: rgba(255,255,255,0.97); color:#222;
    border: 1px solid #d0d7de; border-radius: 10px; box-shadow: 0 8px 28px rgba(0,0,0,.18);
    font: 13px/1.5 -apple-system,"Segoe UI",Roboto,"Microsoft YaHei",sans-serif; }
  #jcb-panel.jcb-collapsed .jcb-body { display:none; }
  #jcb-panel .jcb-head { display:flex; align-items:center; gap:8px; padding:8px 10px; border-bottom:1px solid #e5e7eb; font-weight:600; }
  #jcb-panel .jcb-head .jcb-title { flex:1; }
  #jcb-panel .jcb-body { padding:8px 10px; overflow:auto; }
  #jcb-panel .jcb-section { padding:6px 0 8px; border-bottom:1px dashed #e5e7eb; margin-bottom:6px; }
  #jcb-panel .jcb-section:last-child { border-bottom:none; margin-bottom:0; }
  #jcb-panel .jcb-sub { font-weight:600; margin-bottom:4px; }
  #jcb-panel .jcb-toolbar { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:6px; }
  #jcb-panel button.jcb-btn { cursor:pointer; border:1px solid #0969da; background:#0969da; color:#fff; border-radius:6px; padding:4px 10px; font-size:12px; }
  #jcb-panel button.jcb-btn.secondary { background:#fff; color:#0969da; }
  #jcb-panel button.jcb-btn.danger { background:#fff; color:#cf222e; border-color:#cf222e; }
  #jcb-panel button.jcb-btn:disabled { opacity:.5; cursor:not-allowed; }
  #jcb-panel label { display:inline-flex; align-items:center; gap:6px; }
  #jcb-panel input { padding:3px 5px; }
  #jcb-panel .jcb-status { margin:4px 0; padding:6px 8px; background:#f6f8fa; border-radius:6px; min-height:18px; }
  #jcb-panel ul.jcb-list { list-style:none; margin:0; padding:0; max-height:220px; overflow:auto; }
  #jcb-panel ul.jcb-list li { display:flex; align-items:center; gap:6px; padding:3px 2px; border-bottom:1px dashed #eee; }
  #jcb-panel ul.jcb-list li .jcb-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  #jcb-panel ul.jcb-list li .jcb-badge { flex:none; font-size:11px; padding:1px 6px; border-radius:10px; }
  .jcb-badge.pending{background:#eaeef2;color:#57606a;} .jcb-badge.submitting{background:#ddf4ff;color:#0969da;}
  .jcb-badge.done{background:#dafbe1;color:#1a7f37;} .jcb-badge.error{background:#ffebe9;color:#cf222e;}
  #jcb-panel .jcb-cnt { font-size:12px; color:#57606a; }
  #jcb-panel .jcb-del-opts { display:flex; flex-wrap:wrap; gap:8px; margin:4px 0; font-size:12px; }
  `;
  const styleEl = document.createElement('style');
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  /* ---------------- 面板 DOM ---------------- */
  const panel = document.createElement('div');
  panel.id = 'jcb-panel';
  panel.innerHTML = `
    <div class="jcb-head">
      <span class="jcb-title">挂载盘批量手动刮削</span>
      <span class="jcb-cnt"></span>
      <button class="jcb-btn secondary" data-act="toggle" title="折叠/展开">—</button>
    </div>
    <div class="jcb-body">
      <div class="jcb-section">
        <div class="jcb-sub">① 收集挂载盘视频文件</div>
        <div class="jcb-toolbar">
          <button class="jcb-btn" data-act="pick">＋ 选择挂载盘文件</button>
        </div>
        <div class="jcb-status">尚未添加文件。点「＋ 选择挂载盘文件」。</div>
        <ul class="jcb-list"></ul>
        <div class="jcb-toolbar" style="margin-top:6px">
          <button class="jcb-btn" data-act="start">▶ 添加到任务队列</button>
          <button class="jcb-btn secondary" data-act="stop">■ 停止</button>
          <button class="jcb-btn secondary" data-act="clear-done">清除已提交</button>
          <button class="jcb-btn danger" data-act="clear-all">清空列表</button>
        </div>
      </div>
      <div class="jcb-section">
        <div class="jcb-sub">② 按状态清理手动任务记录</div>
        <div class="jcb-del-opts">
          <label><input type="checkbox" data-del="succeeded"> 已完成</label>
          <label><input type="checkbox" data-del="failed"> 失败</label>
          <label><input type="checkbox" data-del="cancelled"> 已取消</label>
          <label><input type="checkbox" data-del="queued"> 排队中</label>
          <label><input type="checkbox" data-del="running"> 运行中</label>
          <label><input type="checkbox" data-del="all"> 全部</label>
        </div>
        <button class="jcb-btn danger" data-act="delete-tasks">删除所选状态的任务</button>
      </div>
    </div>`;
  document.body.appendChild(panel);

  const statusEl = panel.querySelector('.jcb-status');
  const listEl = panel.querySelector('.jcb-list');
  const cntEl = panel.querySelector('.jcb-cnt');

  function setStatus(msg) { statusEl.textContent = msg; console.log('[JavSP批量]', msg); }

  function render() {
    const busy = running || picking || deleting;
    panel.querySelectorAll('[data-act="pick"], [data-act="start"], [data-act="clear-done"], [data-act="clear-all"], [data-act="delete-tasks"]').forEach(button => { button.disabled = busy; });
    listEl.innerHTML = '';
    files.forEach((f, idx) => {
      const li = document.createElement('li');
      li.title = f.path + (f.detail ? '\n' + f.detail : '');
      const name = document.createElement('span');
      name.className = 'jcb-name';
      name.textContent = `${idx + 1}. ${f.name}`;
      const badge = document.createElement('span');
      badge.className = 'jcb-badge ' + f.status;
      badge.textContent = STATUS_LABEL[f.status] || f.status;
      const del = document.createElement('button');
      del.className = 'jcb-btn danger'; del.style.padding = '0 6px'; del.textContent = '✕';
      del.title = '移除';
      del.disabled = busy;
      del.onclick = () => { if (!running && !picking && !deleting) { files.splice(idx, 1); render(); } };
      li.append(name, badge, del);
      listEl.appendChild(li);
    });
    cntEl.textContent = `共 ${files.length} 个`;
  }

  function addPath(p) {
    p = String(p);
    if (!files.some((f) => f.path === p)) {
      files.push({ path: p, name: p.split(/[\\/]/).pop(), status: 'pending', detail: '' });
      return true;
    }
    return false;
  }

  /* ---------------- 通用 fetch ---------------- */
  async function jfetch(url, options = {}) {
    const resp = await fetch(url, Object.assign({ credentials: 'include' }, options, {
      headers: Object.assign({ 'Content-Type': 'application/json' }, options.headers || {})
    }));
    if (resp.status === 401) { location.href = '/login'; throw new Error('登录已过期'); }
    return resp;
  }

  /* ---------------- 把按钮插到原生按钮右侧 ---------------- */
  function injectToolbarButton() {
    const tools = $('#path-tools');
    if (!tools || tools.querySelector('#jcb-pick-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'jcb-pick-btn';
    btn.className = 'button primary';
    btn.type = 'button';
    btn.textContent = '选择挂载盘文件';
    btn.addEventListener('click', pickFiles);
    tools.appendChild(btn);
  }

  /* ---------------- 选择文件：优先多选接口，缺失则回退单选循环 ---------------- */
  async function pickFiles() {
    if (picking || running || deleting) return;
    picking = true;
    render();
    panel.classList.remove('jcb-collapsed');

    if (multiSupported !== false) {
      try {
        setStatus('正在打开系统多选文件框（可 Ctrl/Shift 多选视频文件）…');
        const resp = await jfetch('/api/path/select-multi', {
          method: 'POST', body: JSON.stringify({ kind: 'file' })
        });
        if (resp.status === 404) {
          multiSupported = false;
        } else {
          if (!resp.ok) {
            const t = await resp.json().catch(() => ({}));
            throw new Error(t.detail || ('HTTP ' + resp.status));
          }
          multiSupported = true;
          const data = await resp.json();
          let added = 0;
          (data.paths || []).forEach((p) => { if (addPath(p)) added++; });
          picking = false;
          render();
          setStatus(`多选接口：新增 ${added} 个，列表共 ${files.length} 个。`);
          return;
        }
      } catch (e) {
        picking = false;
        render();
        setStatus('无法选择文件：' + e.message);
        return;
      }
    }

    setStatus('未检测到多选接口，使用单选循环：在系统弹窗里逐个选择视频文件，选完点「取消」结束。');
    let added = 0;
    while (picking) {
      let data;
      try {
        const resp = await jfetch('/api/path/select', {
          method: 'POST', body: JSON.stringify({ kind: 'file' })
        });
        if (!resp.ok) {
          const t = await resp.json().catch(() => ({}));
          throw new Error(t.detail || ('HTTP ' + resp.status));
        }
        data = await resp.json();
      } catch (e) {
        setStatus('打开选择框出错：' + e.message);
        break;
      }
      if (!data || !data.path) break;
      if (addPath(data.path)) added++;
      render();
    }
    picking = false;
    render();
    setStatus(`选择结束，本次新增 ${added} 个，列表共 ${files.length} 个。`);
  }

  /* ---------------- 批量提交与按明确 ID 清理任务 ---------------- */
  async function requestJson(url, options = {}) {
    const response = await jfetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || ('HTTP ' + response.status));
    return data;
  }

  async function requireBatchSupport() {
    const schema = await requestJson('/openapi.json');
    if (!schema.components?.schemas?.TaskBody?.properties?.input_files ||
        !schema.paths?.['/api/tasks']?.post?.responses?.['202']) {
      throw new Error('请先升级到支持后台扫描和批量文件列表的 JavSP WEB 版本。');
    }
  }

  async function stopBatch() {
    stopRequested = true;
    picking = false;
    if (!activeScanId) { setStatus('已停止后续操作；正在提交的请求返回后会停止扫描。'); return; }
    const id = activeScanId;
    try {
      await requestJson('/api/tasks/' + encodeURIComponent(id) + '/cancel', { method: 'POST' });
      if (activeScanId === id) activeScanId = null;
      setStatus('已请求停止扫描；已经生成的影片任务可在任务页单独停止。');
    } catch (error) {
      setStatus('停止扫描失败：' + error.message + '。请在任务页检查扫描及影片任务。');
    }
  }

  async function runBatch() {
    if (running || picking || deleting) return;
    const preset = $('#task-preset');
    if (!preset?.value) { setStatus('请先选择刮削预设。'); return; }
    const snapshot = files.filter(file => file.status !== 'done');
    if (!snapshot.length) { setStatus('没有待提交文件。'); return; }
    const presetId = preset.value;
    running = true;
    stopRequested = false;
    activeScanId = null;
    render();
    try {
      await requireBatchSupport();
      if (stopRequested) { setStatus('已停止提交。'); return; }
      snapshot.forEach(file => { file.status = 'submitting'; file.detail = ''; });
      render();
      const data = await requestJson('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({ input_directory: snapshot[0].path, preset_id: presetId,
                               input_files: snapshot.map(file => file.path) })
      });
      if (!data.scan || !data.tasks?.[0]?.id) throw new Error('任务响应异常，请先检查任务页，避免重复提交。');
      activeScanId = data.tasks[0].id;
      snapshot.forEach(file => { file.status = 'done'; file.detail = '已提交扫描任务 ' + activeScanId; });
      setStatus('已提交 ' + snapshot.length + ' 个文件，扫描和刮削进度请在任务页查看。');
      if (stopRequested) await stopBatch();
    } catch (error) {
      snapshot.forEach(file => { if (file.status !== 'done') { file.status = 'error'; file.detail = error.message; } });
      setStatus('批量提交失败：' + error.message);
    } finally {
      running = false;
      render();
    }
  }

  function isManualTask(task) {
    return task && (!task.source || task.source === 'manual');
  }

  async function collectDeleteTargets(statuses) {
    const targets = new Map();
    let offset = 0;
    while (!stopRequested) {
      const data = await requestJson('/api/tasks?view=manual&limit=500&offset=' + offset);
      if (!Array.isArray(data.items) || data.offset !== offset || !Number.isInteger(data.total)) {
        throw new Error('任务列表发生变化或读取失败，请重新操作。');
      }
      for (const task of data.items) {
        if (task.id && isManualTask(task) && statuses.includes(task.status)) targets.set(task.id, task);
      }
      offset += data.items.length;
      if (offset >= data.total) break;
      if (!data.items.length) throw new Error('任务列表不完整，已停止清理。');
    }
    return [...targets.values()];
  }

  async function deleteTarget(target) {
    const url = '/api/tasks/' + encodeURIComponent(target.id);
    let current = await requestJson(url);
    if (current.id !== target.id || !isManualTask(current) || current.status !== target.status) return false;
    if (['queued', 'running'].includes(current.status)) {
      await requestJson(url + '/cancel', { method: 'POST' });
      for (let attempt = 0; attempt < 10; attempt++) {
        if (stopRequested) return false;
        current = await requestJson(url);
        if (!['queued', 'running'].includes(current.status)) break;
        await sleep(300);
      }
      if (current.id !== target.id || !isManualTask(current) || current.status !== 'cancelled') return false;
    }
    if (stopRequested) return false;
    await requestJson(url, { method: 'DELETE' });
    return true;
  }

  async function batchDelete() {
    if (running || picking || deleting) { setStatus('请先完成当前操作。'); return; }
    const picked = [...panel.querySelectorAll('input[data-del]:checked')].map(input => input.dataset.del);
    const allowed = ['succeeded', 'failed', 'cancelled', 'queued', 'running'];
    const statuses = picked.includes('all') ? allowed : picked.filter(value => allowed.includes(value));
    if (!statuses.length) { setStatus('请先勾选要清理的任务状态。'); return; }
    deleting = true;
    stopRequested = false;
    render();
    let removed = 0, skipped = 0;
    try {
      setStatus('正在读取符合所选状态的手动任务记录…');
      const targets = await collectDeleteTargets(statuses);
      if (stopRequested) { setStatus('已停止清理。'); return; }
      if (!targets.length) { setStatus('没有符合条件的手动任务。'); return; }
      if (!confirm('将清理 ' + targets.length + ' 条手动任务记录，运行中和排队中的任务会先停止；不删除视频文件。继续？')) return;
      for (const target of targets) {
        if (stopRequested) break;
        if (await deleteTarget(target)) removed++; else skipped++;
      }
      setStatus((stopRequested ? '已停止清理' : '清理完成') + '：删除 ' + removed + ' 条，状态变化等原因跳过 ' + skipped + ' 条。');
    } catch (error) {
      setStatus('清理已中止，已删除 ' + removed + ' 条：' + error.message);
    } finally {
      deleting = false;
      render();
    }
  }

  /* ---------------- 面板事件 ---------------- */
  panel.addEventListener('click', (e) => {
    const act = e.target && e.target.dataset && e.target.dataset.act;
    if (!act) return;
    if (act === 'toggle') panel.classList.toggle('jcb-collapsed');
    else if (act === 'pick') pickFiles();
    else if (act === 'start') runBatch();
    else if (act === 'stop') { if (deleting) { stopRequested = true; setStatus('正在停止清理…'); } else stopBatch(); }
    else if (act === 'delete-tasks') batchDelete();
    else if (act === 'clear-done') { if (!running && !picking && !deleting) { files = files.filter((f) => f.status !== 'done'); render(); } }
    else if (act === 'clear-all') { if (!running && !picking && !deleting) { files = []; render(); setStatus('列表已清空。'); } }
  });

  panel.querySelector('input[data-del="all"]').addEventListener('change', (e) => {
    panel.querySelectorAll('input[data-del]').forEach((c) => {
      if (c.dataset.del !== 'all') c.disabled = e.target.checked;
    });
  });

  /* ---------------- 等待页面就绪 ---------------- */
  (function waitReady() {
    if ($('#path-tools') && $('#task-form') && $('#task-message')) {
      injectToolbarButton();
      render();
    } else {
      setTimeout(waitReady, 300);
    }
  })();
})();
//（注：内容由AI生成）
