/* Shared by the console, login and generated demo; no API calls required. */
(() => {
  const key = 'javsp-web.theme';
  const root = document.documentElement;
  const buttons = document.querySelectorAll('[data-theme-toggle]');
  const system = window.matchMedia?.('(prefers-color-scheme: dark)');
  const valid = theme => theme === 'light' || theme === 'dark';
  const preferred = () => {
    try { return localStorage.getItem(key); } catch { return null; }
  };
  let manual = valid(preferred());
  const systemTheme = () => system?.matches ? 'dark' : 'light';

  function apply(theme) {
    root.classList.add('theme-switching');
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    buttons.forEach(button => {
      button.setAttribute('aria-pressed', String(theme === 'dark'));
      button.title = theme === 'dark' ? '切换到明亮模式' : '切换到黑暗模式';
    });
    // Keep transitions suppressed through the first paint of the new palette.
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => root.classList.remove('theme-switching')));
  }

  function set(theme) {
    if (!valid(theme)) return;
    manual = true;
    try { localStorage.setItem(key, theme); } catch { /* Retain this page's choice even without storage. */ }
    apply(theme);
  }

  const get = () => root.dataset.theme;
  const toggle = () => set(get() === 'dark' ? 'light' : 'dark');
  window.JavspTheme = { get, set, toggle };
  buttons.forEach(button => button.addEventListener('click', toggle));
  apply(manual ? preferred() : systemTheme());

  const followSystem = () => { if (!manual) apply(systemTheme()); };
  if (system?.addEventListener) system.addEventListener('change', followSystem);
  else system?.addListener?.(followSystem);

  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    try { if (event.storageArea && event.storageArea !== window.localStorage) return; } catch { /* Storage may be disabled. */ }
    manual = valid(event.newValue);
    apply(manual ? event.newValue : systemTheme());
  });
})();
