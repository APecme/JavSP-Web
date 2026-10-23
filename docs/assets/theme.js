/* Shared by the console, login and generated demo; no API calls required.
   Owns: light/dark mode and the user-defined accent palette. */
(() => {
  const key = 'javsp-web.theme';
  const accentKey = 'javsp-web.accent';
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

  /* --- Accent palette: preset swatches + free color, persisted per user. --- */
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
  const toHex = value => clamp(Math.round(value), 0, 255).toString(16).padStart(2, '0');
  const rgbToHex = (r, g, b) => `#${toHex(r)}${toHex(g)}${toHex(b)}`;
  const hexToRgb = hex => {
    const value = String(hex || '').replace('#', '');
    if (!/^[0-9a-fA-F]{6}$/.test(value)) return null;
    return [parseInt(value.slice(0, 2), 16), parseInt(value.slice(2, 4), 16), parseInt(value.slice(4, 6), 16)];
  };
  const mix = (hex, otherHex, weight) => {
    const a = hexToRgb(hex); const b = hexToRgb(otherHex);
    if (!a || !b) return hex;
    const w = clamp(weight, 0, 1);
    return rgbToHex(
      a[0] + (b[0] - a[0]) * w,
      a[1] + (b[1] - a[1]) * w,
      a[2] + (b[2] - a[2]) * w,
    );
  };
  const isDark = () => root.dataset.theme === 'dark';

  function applyAccent(hex) {
    const value = /^#[0-9a-fA-F]{6}$/.test(hex || '') ? hex.toLowerCase() : null;
    root.style.removeProperty('--accent');
    root.style.removeProperty('--accent-hover');
    root.style.removeProperty('--accent-border');
    root.style.removeProperty('--accent-soft');
    root.style.removeProperty('--accent-border-soft');
    root.style.removeProperty('--accent-surface');
    root.style.removeProperty('--accent-border-pale');
    root.style.removeProperty('--accent-ink');
    root.style.removeProperty('--accent-text');
    root.style.removeProperty('--focus-ring');
    root.style.removeProperty('--focus-ring-strong');
    root.style.removeProperty('--focus-ring-library');
    root.style.removeProperty('--focus-ring-accent');
    if (!value) return;
    const hover = mix(value, '#000000', 0.16);
    const soft = isDark() ? mix(value, '#0b1220', 0.78) : mix(value, '#ffffff', 0.9);
    const surface = isDark() ? mix(value, '#0b1220', 0.64) : mix(value, '#ffffff', 0.78);
    const pale = isDark() ? mix(value, '#0b1220', 0.7) : mix(value, '#ffffff', 0.82);
    const borderSoft = mix(value, isDark() ? '#0b1220' : '#ffffff', 0.45);
    const ring = `${value}44`;
    root.style.setProperty('--accent', value);
    root.style.setProperty('--accent-hover', hover);
    root.style.setProperty('--accent-border', mix(value, '#ffffff', 0.35));
    root.style.setProperty('--accent-soft', soft);
    root.style.setProperty('--accent-border-soft', borderSoft);
    root.style.setProperty('--accent-surface', surface);
    root.style.setProperty('--accent-border-pale', pale);
    root.style.setProperty('--accent-ink', value);
    root.style.setProperty('--accent-text', value);
    root.style.setProperty('--focus-ring', ring);
    root.style.setProperty('--focus-ring-strong', ring);
    root.style.setProperty('--focus-ring-library', ring);
    root.style.setProperty('--focus-ring-accent', mix(value, '#ffffff', 0.35));
  }

  const readAccent = () => {
    try { return localStorage.getItem(accentKey); } catch { return null; }
  };
  const writeAccent = value => {
    try { localStorage.setItem(accentKey, value); } catch { /* Keep the choice for this page only. */ }
  };

  const PALETTE_PRESETS = ['#175cd3', '#7c3aed', '#db2777', '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0d9488', '#0284c7', '#4b5563'];
  const DEFAULT_ACCENTS = { light: '#175cd3', dark: '#2563eb' };

  function currentAccent() {
    const stored = readAccent();
    if (stored) return stored;
    const styles = getComputedStyle(root);
    return (styles.getPropertyValue('--accent') || '').trim() || DEFAULT_ACCENTS[isDark() ? 'dark' : 'light'];
  }

  /* Re-derive soft tints when only the theme changed underneath a custom accent. */
  const baseApply = apply;
  apply = theme => { baseApply(theme); if (readAccent()) applyAccent(readAccent()); };

  function buildPaletteUI() {
    const triggers = document.querySelectorAll('[data-accent-toggle]');
    if (!triggers.length) return;
    const popover = document.createElement('div');
    popover.className = 'palette-popover';
    popover.hidden = true;
    popover.setAttribute('role', 'dialog');
    popover.setAttribute('aria-label', '自定义主题色');
    const title = document.createElement('p');
    title.className = 'palette-popover-title';
    title.textContent = '主题色';
    const swatches = document.createElement('div');
    swatches.className = 'palette-swatches';
    const presetButtons = PALETTE_PRESETS.map(color => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'palette-swatch';
      button.style.setProperty('--swatch', color);
      button.dataset.color = color;
      button.title = color;
      button.setAttribute('aria-label', `使用主题色 ${color}`);
      swatches.appendChild(button);
      return button;
    });
    const customLabel = document.createElement('label');
    customLabel.className = 'palette-custom';
    const customText = document.createElement('span');
    customText.textContent = '自定义颜色';
    const customInput = document.createElement('input');
    customInput.type = 'color';
    customInput.setAttribute('aria-label', '自定义主题色');
    customLabel.append(customText, customInput);
    popover.append(title, swatches, customLabel);
    document.body.appendChild(popover);

    let open = false;
    const syncSelection = () => {
      const current = currentAccent().toLowerCase();
      presetButtons.forEach(button => {
        const active = button.dataset.color.toLowerCase() === current;
        button.classList.toggle('active', active);
        button.setAttribute('aria-pressed', String(active));
      });
      customInput.value = /^#[0-9a-fA-F]{6}$/.test(current) ? current : '#175cd3';
    };
    const position = trigger => {
      const rect = trigger.getBoundingClientRect();
      popover.style.top = `${rect.bottom + window.scrollY + 8}px`;
      popover.style.left = `${Math.max(8, rect.left + window.scrollX - 232 + rect.width)}px`;
    };
    const setOpen = next => {
      open = next;
      popover.hidden = !open;
      if (open) syncSelection();
      triggers.forEach(trigger => trigger.setAttribute('aria-expanded', String(open)));
    };

    const choose = value => {
      const normalized = value ? value.toLowerCase() : '';
      if (normalized) writeAccent(normalized); else { try { localStorage.removeItem(accentKey); } catch { /* ignore */ } }
      applyAccent(normalized || undefined);
      syncSelection();
    };
    swatches.addEventListener('click', event => {
      const button = event.target.closest?.('.palette-swatch');
      if (button) choose(button.dataset.color);
    });
    customInput.addEventListener('input', () => choose(customInput.value));
    customInput.addEventListener('click', event => event.stopPropagation());

    triggers.forEach(trigger => {
      trigger.addEventListener('click', event => {
        event.stopPropagation();
        if (open) setOpen(false);
        else { position(trigger); setOpen(true); }
      });
    });
    document.addEventListener('click', event => {
      if (open && !popover.contains(event.target)) setOpen(false);
    });
    document.addEventListener('keydown', event => {
      if (open && event.key === 'Escape') setOpen(false);
    });
    window.addEventListener('resize', () => { if (open) setOpen(false); });
    window.addEventListener('storage', event => {
      if (event.key === accentKey || event.key === null) {
        const value = readAccent();
        applyAccent(value || undefined);
        if (open) syncSelection();
      }
    });
  }

  applyAccent(readAccent() || undefined);
  buildPaletteUI();
  if (typeof window.JavspTheme === 'object') {
    window.JavspTheme.getAccent = currentAccent;
    window.JavspTheme.setAccent = value => {
      if (value) writeAccent(value.toLowerCase());
      else { try { localStorage.removeItem(accentKey); } catch { /* ignore */ } }
      applyAccent(value || undefined);
    };
  }
})();
