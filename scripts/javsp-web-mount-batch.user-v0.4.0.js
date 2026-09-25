// ==UserScript==
// @name         JavSP WEB 挂载盘批量刮削助手
// @namespace    https://github.com/APecme/JavSP-Web
// @version      0.4.0
// @description  登录页一键登录；批量选择挂载盘视频文件逐个刮削；按状态驱动 UI 批量删除任务（自动点停止/删除确认框）。
// @match        http://127.0.0.1:8090/*
// @match        http://localhost:8090/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

/* ============================================================================
 *   JavSP WEB 挂载盘批量刮削助手
 * ============================================================================
 *
 *  1. 功能与解决的问题
 *  --------------------------------------------------------------------------
 *  本脚本是给 JavSP WEB（https://github.com/APecme/JavSP-Web）写的油猴辅助，
 *  解决「直接刮削 CloudDrive2 等挂载盘文件夹会请求失败、但单个文件可以成功」
 *  的问题：把挂载盘里的视频文件批量收集成队列，逐个填入并点「启动 JavSP」，
 *  等启动信息（#task-message）更新后再提交下一个。另附带两个便利功能：
 *    - 登录页一键登录（用户名/密码在脚本顶部配置）；
 *    - 按状态批量删除任务（自动停止运行中任务、自动点删除确认框、自动翻页）。
 *
 *  2. 如何使用（安装到 Tampermonkey）
 *  --------------------------------------------------------------------------
 *  1) 浏览器安装 Tampermonkey 扩展；
 *  2) 点 Tampermonkey 图标 →「添加新脚本」；
 *  3) 把本文件全部内容粘贴进去，Ctrl+S 保存；
 *  4) 打开 http://127.0.0.1:8090/ 即可：登录页出现「一键登录」按钮，控制台
 *     右上角出现「挂载盘批量刮削」面板。
 *  5) 常用配置在脚本顶部「可配置项」：
 *       LOGIN_USER / LOGIN_PASS   登录账号密码
 *       DEFAULT_GAP_SEC           每个任务提交后的间隔秒数
 *
 *  3. 支持的 JavSP WEB 版本
 *  --------------------------------------------------------------------------
 *  基于 JavSP WEB main 分支、版本 1.1.37 实测可用（不限于此版本）。
 *  只要以下 DOM/接口不变即可使用：
 *    - #input-directory、#task-preset、#task-message、#task-form
 *    - POST /api/path/select（系统单选文件对话框）
 *    - 可选增强：POST /api/path/select-multi（一次多选，后端新增后脚本自动启用）
 *    - #task-filter-status、button.task-delete、#task-delete-confirm、
 *      #action-confirm-dialog、#task-pagination 下的 [data-task-page]
 *  若原作者后续直接内置了批量选择/批量删除功能，本脚本可废弃。
 *
 *  4. 不足之处
 *  --------------------------------------------------------------------------
 *  - 批量选择依赖后端弹出的系统文件框（tkinter）。若 JavSP 以后台服务/计划任务
 *    方式启动、没有交互式桌面，系统弹窗可能不显示，此时「选择挂载盘文件」会
 *    一直等待；需要后端改成网页内目录浏览来多选。
 *  - 未打后端多选接口补丁时，批量选择是「循环弹单选框、选完点取消结束」；
 *    加一个 /api/path/select-multi（askopenfilenames）即可一次 Ctrl/Shift 多选。
 *  - 队列只保存在当前页面内存，刷新/重启浏览器后队列丢失。
 *  - 批量删除需在「任务」页执行；运行中任务会先停止再删除。
 *  - 仅适配 127.0.0.1:8090 / localhost:8090，端口或地址变了请改 @match。
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
  const DEFAULT_GAP_SEC = 1;       // 添加到队列间隔(秒)的默认值
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

  const STATUS_LABEL = {
    pending: '待处理', submitting: '提交中', done: '成功', error: '失败', picking: '选择中'
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
  #jcb-panel .jcb-gap-label { flex:1 1 180px; min-width:180px; margin-left:16px; }
  #jcb-panel input.jcb-gap { flex:1; width:auto; min-width:70px; }
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
          <label class="jcb-gap-label">添加到队列间隔(秒) <input class="jcb-gap" data-act="gap" type="number" min="0" step="0.5" value="${DEFAULT_GAP_SEC}"></label>
        </div>
        <div class="jcb-status">尚未添加文件。点「＋ 选择挂载盘文件」。</div>
        <ul class="jcb-list"></ul>
        <div class="jcb-toolbar" style="margin-top:6px">
          <button class="jcb-btn" data-act="start">▶ 添加到任务队列</button>
          <button class="jcb-btn secondary" data-act="stop">■ 停止</button>
          <button class="jcb-btn secondary" data-act="clear-done">清除成功</button>
          <button class="jcb-btn danger" data-act="clear-all">清空列表</button>
        </div>
      </div>
      <div class="jcb-section">
        <div class="jcb-sub">② 批量删除任务（请到"任务"页操作）</div>
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
  const gapInput = panel.querySelector('input[data-act="gap"]');

  function setStatus(msg) { statusEl.textContent = msg; console.log('[JavSP批量]', msg); }

  function render() {
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
      del.onclick = () => { files.splice(idx, 1); render(); };
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

  function waitFor(cond, timeoutMs = 5000, stepMs = 150) {
    const start = Date.now();
    return new Promise((resolve) => {
      const t = setInterval(() => {
        if (cond()) { clearInterval(t); resolve(true); }
        else if (Date.now() - start > timeoutMs) { clearInterval(t); resolve(false); }
      }, stepMs);
    });
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
    if (picking || running) return;
    picking = true;
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
          render();
          picking = false;
          setStatus(`多选接口：新增 ${added} 个，列表共 ${files.length} 个。`);
          return;
        }
      } catch (e) {
        setStatus('多选接口调用异常，回退到单选循环：' + e.message);
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
    setStatus(`选择结束，本次新增 ${added} 个，列表共 ${files.length} 个。`);
  }

  /* ---------------- 等待 #task-message 出现新文本 ---------------- */
  function waitForMessage(timeoutMs = 95000) {
    const msg = $('#task-message');
    const start = Date.now();
    return new Promise((resolve) => {
      const t = setInterval(() => {
        const v = (msg && msg.textContent || '').trim();
        if (v) { clearInterval(t); resolve(v); }
        else if (Date.now() - start > timeoutMs) { clearInterval(t); resolve('(等待启动信息超时)'); }
      }, 300);
    });
  }

  async function scrapeOne(f) {
    const input = $('#input-directory');
    const btn = $('#task-form button[type="submit"]');
    const msg = $('#task-message');
    if (!input || !btn || !msg) throw new Error('页面元素缺失');

    f.status = 'submitting'; f.detail = ''; render();
    input.value = f.path;
    await sleep(120);
    msg.textContent = '';
    btn.click();

    const text = await waitForMessage();
    f.detail = text;
    f.status = /已启动|已创建/.test(text) ? 'done' : 'error';
    render();
  }

  async function runBatch() {
    if (running) return;
    const preset = $('#task-preset');
    if (!preset || !preset.value) {
      setStatus('请先在页面上选择一个「刮削预设」。');
      panel.classList.remove('jcb-collapsed');
      return;
    }
    if (!files.length) { setStatus('队列为空，请先选择挂载盘文件。'); return; }

    running = true; stopRequested = false;
    const gapSec = Math.max(0, parseFloat(gapInput.value) || 0);
    let done = 0, fail = 0;
    for (let i = 0; i < files.length; i++) {
      if (stopRequested) { setStatus('已手动停止。'); break; }
      const f = files[i];
      if (f.status === 'done') continue;
      setStatus(`正在处理第 ${i + 1}/${files.length} 个：${f.name}`);
      try {
        await scrapeOne(f);
        if (f.status === 'done') done++; else fail++;
      } catch (e) {
        f.status = 'error'; f.detail = e.message; render(); fail++;
      }
      if (gapSec > 0 && i < files.length - 1) await sleep(gapSec * 1000);
    }
    running = false;
    setStatus(`添加结束：成功 ${done}，失败 ${fail}。`);
  }

  /* ---------------- 批量删除任务：驱动 UI ---------------- */
  function openDialogEl() {
    const d1 = $('#task-delete-dialog');
    if (d1 && d1.open) return d1;
    const d2 = $('#action-confirm-dialog');
    if (d2 && d2.open) return d2;
    return null;
  }

  async function confirmOpenDialog() {
    const d1 = $('#task-delete-dialog');
    if (d1 && d1.open) { $('#task-delete-confirm').click(); return; }
    const d2 = $('#action-confirm-dialog');
    if (d2 && d2.open) { $('#action-confirm-button').click(); return; }
  }

  async function processStatus(statusValue) {
    const sel = $('#task-filter-status');
    if (!sel) { setStatus('未找到任务筛选条，请先切到"任务"页再点删除。'); return; }
    sel.value = statusValue;
    sel.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(1000);

    for (let round = 0; round < 2000; round++) {
      if (stopRequested) break;

      // 1) 先停掉运行中/排队中（它们的删除按钮是禁用的）
      const stopBtn = document.querySelector('button.task-stop, button[onclick^="cancelTask("]');
      const delBtn = document.querySelector('button.task-delete:not(:disabled)');
      const target = stopBtn || delBtn;

      if (!target) {
        // 当前页删完，尝试下一页
        const next = [...document.querySelectorAll('#task-pagination [data-task-page]')]
          .filter((b) => !b.disabled)
          .sort((a, b) => Number(b.dataset.taskPage) - Number(a.dataset.taskPage))[0];
        if (next) { setStatus('翻到下一页继续…'); next.click(); await sleep(1000); continue; }
        break;
      }

      setStatus(stopBtn ? '停止运行中任务…' : '删除任务…');
      target.click();

      const opened = await waitFor(() => !!openDialogEl(), 4000);
      if (!opened) { setStatus('确认框未弹出，跳过。'); await sleep(400); continue; }
      await sleep(250);
      confirmOpenDialog();

      // 等对话框关闭
      const closed = await waitFor(() => !openDialogEl(), 8000);
      if (!closed) {
        // 关不掉（可能后端报错），点取消关掉这个对话框继续
        const d = openDialogEl();
        const cancelBtn = d && d.querySelector('[data-dialog-close]');
        if (cancelBtn) cancelBtn.click();
        await sleep(400);
      }
      await sleep(700); // 等 loadTasks 重新渲染
    }
  }

  async function batchDelete() {
    if (running) { setStatus('批量刮削进行中，先停止。'); return; }
    const picked = [...panel.querySelectorAll('input[data-del]:checked')].map((c) => c.dataset.del);
    if (!picked.length) { setStatus('请先勾选要删除的任务状态。'); return; }
    if (!confirm('将按所选状态逐个删除任务（自动点停止/删除确认框）。确认继续？')) return;

    stopRequested = false;
    const statuses = picked.includes('all') ? [''] : picked;
    for (const sv of statuses) {
      if (stopRequested) break;
      setStatus(`处理状态：${sv || '全部'} …`);
      await processStatus(sv);
    }
    setStatus('批量删除流程结束。');
  }

  /* ---------------- 面板事件 ---------------- */
  panel.addEventListener('click', (e) => {
    const act = e.target && e.target.dataset && e.target.dataset.act;
    if (!act) return;
    if (act === 'toggle') panel.classList.toggle('jcb-collapsed');
    else if (act === 'pick') pickFiles();
    else if (act === 'start') runBatch();
    else if (act === 'stop') { stopRequested = true; setStatus('正在停止…'); }
    else if (act === 'delete-tasks') batchDelete();
    else if (act === 'clear-done') { files = files.filter((f) => f.status !== 'done'); render(); }
    else if (act === 'clear-all') { if (!running) { files = []; render(); setStatus('列表已清空。'); } }
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
