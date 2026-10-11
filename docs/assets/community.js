window.JavspCommunity = (() => {
  let profile = null, catalog = null, base = '', selectedAvatar = '', historyCursor = null, historyItems = [], historyVersion = 0;
  let avatarPage = 0, historyLoading = false, challengeActive = false;
  const el = id => document.getElementById(id);
  const esc = value => escapeHtml(value ?? '');
  const avatar = (id, name = '', className = 'user-avatar') => /^[a-f0-9]{16}$/.test(id || '')
    ? `<img class="${className}" src="${assetRoot()}avatars/${id}.webp" alt="${esc(name)}" loading="lazy">`
    : `<span class="${className} avatar-fallback" aria-hidden="true">${esc((name || '匿').slice(0, 1))}</span>`;
  // The same assets are also used by the project site's subdirectory demo.
  const assetRoot = () => new URL('avatars/', document.querySelector('script[src*="community.js"]').src).href.replace(/avatars\/$/, '');
  const headers = () => profile?.comment_token ? { 'X-User-Token': profile.comment_token } : {};
  const identity = () => ({ nickname: profile?.display_name || '', avatar_id: profile?.avatar_id || '' });
  async function init() {
    profile = await api('/api/profile');
    renderAccount();
  }
  function configure(url) { base = String(url || '').replace(/\/+$/, ''); }
  function renderAccount() {
    if (!profile) return;
    el('current-user').textContent = profile.display_name;
    el('current-avatar').innerHTML = avatar(profile.avatar_id, profile.display_name);
    document.querySelectorAll('[data-comment-avatar]').forEach(node => { node.innerHTML = avatar(profile.avatar_id, profile.display_name); });
    document.querySelectorAll('[data-comment-author]').forEach(node => { node.textContent = profile.display_name; });
  }
  async function service(path, options = {}) {
    if (!base) throw new Error('评论服务未启用。');
    const response = await fetch(base + path, { ...options, credentials: 'omit', referrerPolicy: 'no-referrer', signal: AbortSignal.timeout(15000), headers: { Accept: 'application/json', ...headers(), ...(options.body ? { 'Content-Type': 'application/json' } : {}) } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || '评论服务暂时不可用，请重试。');
    return data;
  }
  function verify(action) {
    if (challengeActive) return Promise.reject(new Error('请先完成已打开的验证。'));
    if (!base) return Promise.reject(new Error('评论服务未启用。'));
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    const hex = [...bytes].map(x => x.toString(16).padStart(2, '0')).join('');
    const nonce = `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
    const dialog = document.createElement('dialog');
    dialog.className = 'verification-dialog';
    dialog.setAttribute('aria-label', '安全验证');
    dialog.innerHTML = '<div class="comments-heading"><h3>安全验证</h3><button type="button" class="icon-button" data-verify-cancel>取消验证</button></div><iframe title="Cloudflare 人机验证" referrerpolicy="no-referrer"></iframe><p class="muted">请按提示完成验证。无法加载时，可取消后重试。</p>';
    const frame = dialog.querySelector('iframe');
    frame.src = `${base}/verify#${new URLSearchParams({ action, nonce })}`;
    document.body.append(dialog);
    dialog.showModal();
    challengeActive = true;
    return new Promise((resolve, reject) => {
      const cleanup = () => { clearTimeout(timeout); window.removeEventListener('message', receive); dialog.removeEventListener('close', cancel); challengeActive = false; dialog.close(); dialog.remove(); };
      const cancel = () => { cleanup(); reject(new Error('验证已取消，可以重新提交。')); };
      const receive = event => {
        if (event.origin !== new URL(base).origin || event.source !== frame.contentWindow || event.data?.type !== 'javsp-verification' || event.data.nonce !== nonce || event.data.action !== action || typeof event.data.token !== 'string') return;
        cleanup(); resolve(event.data.token);
      };
      const timeout = setTimeout(() => { cleanup(); reject(new Error('验证超时，请重试。')); }, 180000);
      dialog.addEventListener('close', cancel);
      dialog.querySelector('[data-verify-cancel]').addEventListener('click', () => dialog.close());
      window.addEventListener('message', receive);
    });
  }

  async function loadHistory(more = false) {
    if (historyLoading) return;
    historyLoading = true;
    const version = ++historyVersion;
    const message = el('my-comments-message');
    message.textContent = '正在读取评论…';
    el('my-comments-more').disabled = el('my-comments-refresh').disabled = true;
    try {
      const data = await service('/api/me/comments' + (more && historyCursor ? '?before=' + historyCursor : ''));
      if (version !== historyVersion) return;
      historyItems = more ? [...historyItems, ...data.items] : data.items;
      historyCursor = data.next_cursor;
      const labels = { pending: '待审核', published: '已发布', hidden: '已隐藏' };
      el('my-comments-list').innerHTML = historyItems.length ? historyItems.map(item => `<article class="comment-item"><div class="comment-item-head"><strong>${esc(item.identifier)}</strong><span class="badge">${labels[item.status] || ''}</span><time>${esc(new Date(item.created_at * 1000).toLocaleString())}</time></div><p>${esc(item.body)}</p><small class="muted">${item.likes || 0} 人点赞</small></article>`).join('') : '<p class="empty-profile">还没有评论。打开影片详情，留下你的第一条评论吧。</p>';
      el('my-comments-count').textContent = `已发布 ${data.stats.published} · 待审核 ${data.stats.pending} · 已隐藏 ${data.stats.hidden}`;
      el('my-comments-more').hidden = !historyCursor;
      message.textContent = '';
    } catch (_) { if (version === historyVersion) message.textContent = base ? '暂时无法读取评论，请检查网络后重试。' : '评论服务未启用。'; }
    finally { historyLoading = false; el('my-comments-more').disabled = el('my-comments-refresh').disabled = false; }
  }
  function renderAvatars() {
    const query = el('avatar-search').value.normalize('NFKC').trim().toLocaleLowerCase();
    const items = (catalog || []).filter(item => item.name.normalize('NFKC').toLocaleLowerCase().includes(query));
    const pages = Math.max(1, Math.ceil(items.length / 24));
    avatarPage = Math.min(avatarPage, pages - 1);
    el('avatar-grid').innerHTML = items.slice(avatarPage * 24, (avatarPage + 1) * 24).map(item => `<button type="button" class="avatar-option${selectedAvatar === item.id ? ' selected' : ''}" data-avatar-id="${item.id}" aria-pressed="${selectedAvatar === item.id}" title="${esc(item.name)}">${avatar(item.id, item.name, 'picker-avatar')}<span>${esc(item.name)}</span></button>`).join('') || '<p class="muted">没有找到这个名字，试试其他写法。</p>';
    el('avatar-count').textContent = `${items.length} 个头像 · 第 ${avatarPage + 1} / ${pages} 页`;
    el('avatar-prev').disabled = avatarPage === 0;
    el('avatar-next').disabled = avatarPage + 1 >= pages;
  }
  function renderPreview() {
    el('profile-avatar-preview').innerHTML = avatar(selectedAvatar, el('profile-name').value, 'profile-avatar');
    el('profile-avatar-name').textContent = catalog?.find(x => x.id === selectedAvatar)?.name || '默认头像';
  }
  async function open() {
    const dialog = el('profile-dialog');
    if (!dialog.open) dialog.showModal();
    el('profile-message').textContent = '';
    try {
      if (!profile) await init();
      selectedAvatar = profile.avatar_id;
      el('profile-name').value = profile.display_name;
      el('profile-login-name').textContent = profile.username;
      renderPreview();
      loadHistory();
      if (!catalog) {
        const response = await fetch(assetRoot() + 'avatar-catalog.json');
        if (!response.ok) throw new Error();
        catalog = await response.json();
      }
      renderPreview(); renderAvatars();
    } catch (_) { el('profile-message').textContent = '个人资料读取失败，请关闭后重试。'; }
  }
  document.addEventListener('click', event => {
    if (event.target.closest('[data-open-profile]')) open();
    const button = event.target.closest('[data-avatar-id]');
    if (button) { selectedAvatar = button.dataset.avatarId; renderPreview(); renderAvatars(); }
    if (event.target.closest('#avatar-default')) { selectedAvatar = ''; renderPreview(); renderAvatars(); }
    if (event.target.closest('#avatar-prev')) { avatarPage--; renderAvatars(); }
    if (event.target.closest('#avatar-next')) { avatarPage++; renderAvatars(); }
    if (event.target.closest('#my-comments-more')) loadHistory(true);
    if (event.target.closest('#my-comments-refresh')) loadHistory();
  });
  el('avatar-search')?.addEventListener('input', () => { avatarPage = 0; renderAvatars(); });
  el('profile-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const button = el('profile-save'); button.disabled = true;
    try {
      profile = await api('/api/profile', { method: 'PUT', body: JSON.stringify({ display_name: el('profile-name').value.trim(), avatar_id: selectedAvatar }) });
      renderAccount(); renderPreview(); el('profile-message').textContent = '已保存。之后发送的评论会使用新的用户名和头像。';
    } catch (error) { el('profile-message').textContent = error.message; }
    finally { button.disabled = false; }
  });
  return { init, configure, headers, identity, avatar, verify, open };
})();
