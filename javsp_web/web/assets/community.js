window.JavspCommunity = (() => {
  let profile = null, catalog = null, base = '', selectedAvatar = '', historyCursor = null, historyItems = [], historyVersion = 0;
  let avatarPage = 0, historyLoading = false, challengeActive = false;
  const el = id => document.getElementById(id);
  const esc = value => escapeHtml(value ?? '');
  const avatarURL = id => catalog?.find(item => item.id === id)?.url || (document.body.classList.contains('demo-mode') ? `${assetRoot()}avatars/${id}.webp` : `/api/avatars/${id}`);
  const avatar = (id, name = '', className = 'user-avatar') => /^[a-f0-9]{16}$/.test(id || '')
    ? `<img class="${className}" src="${esc(avatarURL(id))}" alt="${esc(name)}" loading="lazy" referrerpolicy="no-referrer">`
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
    if (!response.ok) { const error = new Error(data.detail || '评论服务暂时不可用，请重试。'); error.status = response.status; throw error; }
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
    if (!profile?.identity_ready) {
      el('my-comments-list').innerHTML = ''; el('my-comments-count').textContent = '';
      el('my-comments-message').textContent = '先创建或登录评论身份，即可查看自己的评论。';
      el('my-comments-more').hidden = true; return;
    }
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
    } catch (error) { if (version === historyVersion) message.textContent = error.message; }
    finally { if (version === historyVersion) { historyLoading = false; el('my-comments-more').disabled = el('my-comments-refresh').disabled = false; } }
  }
  function renderAvatars() {
    const query = el('avatar-search').value.normalize('NFKC').trim().toLocaleLowerCase();
    const items = (catalog || []).filter(item => item.source === 'gfriends' && item.name.normalize('NFKC').toLocaleLowerCase().includes(query));
    const pages = Math.max(1, Math.ceil(items.length / 24));
    avatarPage = Math.min(avatarPage, pages - 1);
    el('avatar-grid').innerHTML = items.slice(avatarPage * 24, (avatarPage + 1) * 24).map(item => `<button type="button" class="avatar-option${selectedAvatar === item.id ? ' selected' : ''}" data-avatar-id="${item.id}" aria-pressed="${selectedAvatar === item.id}" title="${esc(item.name)}">${avatar(item.id, item.name, 'picker-avatar')}<span>${esc(item.name)}</span></button>`).join('') || '<p class="muted">没有找到这个名字，试试其他写法。</p>';
    el('avatar-count').textContent = `${items.length} 个头像 · 第 ${avatarPage + 1} / ${pages} 页`;
    el('avatar-prev').disabled = avatarPage === 0;
    el('avatar-next').disabled = avatarPage + 1 >= pages;
  }
  function renderPreview() {
    el('profile-avatar-preview').innerHTML = avatar(selectedAvatar, el('profile-name').value, 'profile-avatar');
    el('profile-avatar-name').textContent = catalog?.find(x => x.id === selectedAvatar)?.name || (selectedAvatar ? '当前头像' : '默认头像');
  }
  async function remember(data) {
    const changed = profile?.display_name !== data.display_name;
    profile = await api('/api/profile/community', { method: 'PUT', body: JSON.stringify({
      comment_token: data.comment_token || profile.comment_token, comment_username: data.comment_username,
      display_name: data.display_name, avatar_id: data.avatar_id,
    }) });
    if (changed) { historyVersion++; historyLoading = false; historyItems = []; historyCursor = null; el('my-comments-list').innerHTML = ''; el('my-comments-count').textContent = ''; }
    selectedAvatar = profile.avatar_id; renderAccount();
  }
  function clearPin() { el('profile-pin').value = ''; el('profile-pin-confirm').value = ''; if (el('profile-pin-new')) el('profile-pin-new').value = ''; }
  function renderMode() {
    const mode = el('identity-mode').value, creating = mode === 'create', changing = mode === 'pin';
    const confirming = creating || changing;
    el('pin-confirm-label').hidden = !confirming; el('profile-pin-confirm').required = confirming;
    el('pin-new-label').hidden = !changing; el('profile-pin-new').required = changing;
    el('pin-confirm-label').firstChild.textContent = changing ? '再次输入新 PIN' : '再次输入 PIN';
    el('profile-pin').closest('label').firstChild.textContent = changing ? '当前 PIN' : '6 位数字 PIN';
    el('profile-name').readOnly = changing;
    if (changing && profile?.identity_ready) el('profile-name').value = profile.display_name;
    el('profile-pin').autocomplete = creating ? 'new-password' : 'current-password';
    el('profile-save').textContent = creating ? '创建评论身份' : changing ? '修改 PIN' : '登录评论身份';
    // Creating takes only the name; the #TAG suffix is assigned by the service.
    if (creating) el('profile-name').value = el('profile-name').value.replace(/#[0-9A-Za-z]{4}$/, '');
  }
  function renderIdentity(edit = !profile?.identity_ready) {
    el('profile-handle').textContent = profile.identity_ready ? profile.display_name : '设置你的评论身份';
    el('profile-form').hidden = !edit; el('identity-actions').hidden = edit || !profile.identity_ready;
    el('identity-mode').querySelector('[value="pin"]').hidden = !profile.identity_ready;
    el('identity-cancel').hidden = !profile.identity_ready;
    // Logging in with the full handle keeps failed attempts isolated to this identity.
    el('profile-name').value = profile.identity_ready ? profile.display_name : (profile.comment_username || profile.display_name);
    el('identity-mode').value = profile.identity_ready ? 'login' : 'create';
    clearPin(); renderMode();
  }
  // Changing the PIN signs this identity out everywhere and returns a fresh session.
  async function changePin(pin) {
    const button = el('profile-save'), new_pin = el('profile-pin-new').value;
    if (!/^[0-9]{6}$/.test(new_pin)) { el('profile-message').textContent = '新 PIN 必须是 6 位数字。'; return; }
    if (new_pin !== el('profile-pin-confirm').value) { el('profile-message').textContent = '两次输入的新 PIN 不一致。'; return; }
    button.disabled = true;
    try {
      const turnstile_token = await verify('identity');
      await remember(await service('/api/me/pin', {method:'POST',body:JSON.stringify({pin,new_pin,turnstile_token})}));
      renderIdentity(); renderPreview();
      el('profile-message').textContent = 'PIN 已修改，其他设备上的评论身份已退出。';
    } catch (error) { el('profile-message').textContent = error.message; }
    finally { clearPin(); button.disabled = false; }
  }
  // Sign out locally even if the service session has already expired.
  async function signOut(all) {
    if (all && !confirm('让这个评论身份在所有设备上退出？之后需要重新输入用户名和 PIN 登录。')) return;
    const message = el('profile-message');
    try { await service(all ? '/api/me/logout-all' : '/api/me/logout', {method:'POST',body:'{}'}); }
    catch (error) { if (error.status !== 401) { message.textContent = error.message; return; } }
    try {
      profile = await api('/api/profile/community', {method:'DELETE'});
      historyVersion++; historyItems = []; historyCursor = null; el('my-comments-list').innerHTML = ''; el('my-comments-count').textContent = '';
      selectedAvatar = profile.avatar_id; renderAccount(); renderIdentity(); renderPreview();
      message.textContent = all ? '已在所有设备退出评论身份。' : '已退出评论身份。';
    } catch (error) { message.textContent = error.message; }
  }
  async function requireIdentity() {
    if (!profile?.identity_ready) { await open(); throw new Error('请先在个人中心创建或登录评论身份，评论草稿已保留。'); }
    try { await remember(await service('/api/me/profile')); }
    catch (error) { if (error.status === 401) { await open(); renderIdentity(true); el('identity-mode').value='login'; renderMode(); } throw error; }
  }
  async function open() {
    const dialog = el('profile-dialog');
    if (!dialog.open) dialog.showModal();
    el('profile-message').textContent = '';
    try {
      if (!profile) await init();
      selectedAvatar = profile.avatar_id;
      el('profile-login-name').textContent = profile.username;
      renderIdentity(); renderPreview();
      if (profile.identity_ready && base) {
        try { await remember(await service('/api/me/profile')); renderIdentity(); renderPreview(); }
        catch (error) { el('profile-message').textContent = error.message; if (error.status === 401) { renderIdentity(true); el('identity-mode').value='login'; renderMode(); } }
      }
      await loadHistory();
      if (profile.avatar_id && !catalog) { await loadCatalog(); renderPreview(); }
    } catch (error) { el('profile-message').textContent = error.message || '个人资料读取失败，请关闭后重试。'; }
  }
  async function loadCatalog() {
    if (catalog) return;
    const response = await fetch(assetRoot() + 'avatar-catalog.json');
    if (!response.ok) throw new Error('头像读取失败，请重试。');
    catalog = await response.json();
  }
  async function openAvatars() {
    if (!profile) return;
    selectedAvatar = profile.avatar_id; avatarPage = 0;
    el('avatar-search').value = ''; el('avatar-message').textContent = '';
    el('avatar-picker-dialog').showModal();
    try {
      await loadCatalog(); renderAvatars();
    } catch(error) { el('avatar-message').textContent = error.message; }
  }
  document.addEventListener('click', event => {
    if (event.target.closest('[data-open-profile]')) open();
    if (event.target.closest('#avatar-edit')) openAvatars();
    if (event.target.closest('#identity-switch')) renderIdentity(true);
    if (event.target.closest('#identity-logout')) signOut(false);
    if (event.target.closest('#identity-logout-all')) signOut(true);
    if (event.target.closest('#identity-cancel')) renderIdentity(false);
    const button = event.target.closest('[data-avatar-id]');
    if (button) { selectedAvatar = button.dataset.avatarId; renderAvatars(); }
    if (event.target.closest('#avatar-default')) { selectedAvatar = ''; renderAvatars(); }
    if (event.target.closest('#avatar-prev')) { avatarPage--; renderAvatars(); }
    if (event.target.closest('#avatar-next')) { avatarPage++; renderAvatars(); }
    if (event.target.closest('#my-comments-more')) loadHistory(true);
    if (event.target.closest('#my-comments-refresh')) loadHistory();
  });
  el('avatar-search')?.addEventListener('input', () => { avatarPage = 0; renderAvatars(); });
  el('identity-mode')?.addEventListener('change', () => { clearPin(); renderMode(); });
  el('profile-dialog')?.addEventListener('close', clearPin);
  el('avatar-save')?.addEventListener('click', async () => {
    const button = el('avatar-save'); button.disabled = true;
    try {
      if (profile.identity_ready) await remember(await service('/api/me/profile', {method:'POST',body:JSON.stringify({avatar_id:selectedAvatar})}));
      else profile = await api('/api/profile', {method:'PUT',body:JSON.stringify({display_name:profile.display_name,avatar_id:selectedAvatar})});
      renderAccount(); renderPreview(); el('avatar-picker-dialog').close();
      el('profile-message').textContent = '头像已更新。';
    } catch(error) { el('avatar-message').textContent = error.message; }
    finally { button.disabled = false; }
  });
  el('profile-form')?.addEventListener('submit', async event => {
    event.preventDefault();
    const button = el('profile-save'); if (button.disabled) return;
    const pin = el('profile-pin').value, mode = el('identity-mode').value;
    if (!/^[0-9]{6}$/.test(pin)) { el('profile-message').textContent = 'PIN 必须是 6 位数字。'; return; }
    if (mode === 'create' && pin !== el('profile-pin-confirm').value) { el('profile-message').textContent = '两次输入的 PIN 不一致。'; return; }
    if (mode === 'pin') return changePin(pin);
    const username = el('profile-name').value.trim(); button.disabled = true;
    try {
      const turnstile_token = await verify('identity');
      const data = await service('/api/identity', {method:'POST',body:JSON.stringify({username,pin,mode,avatar_id:profile.avatar_id,turnstile_token})});
      await remember(data); renderIdentity(); renderPreview();
      el('profile-message').textContent = mode === 'create' ? '评论身份已创建。请记住用户名和 PIN。' : '已登录，评论记录已同步。';
      await loadHistory();
    } catch (error) { el('profile-message').textContent = error.message; }
    finally { clearPin(); button.disabled = false; }
  });
  return { init, configure, headers, identity, avatar, verify, open, requireIdentity };
})();
