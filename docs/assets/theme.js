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

  /* --- Accent palettes: three independent color groups （主导航 / 主色 / 副色）.
     Each group derives only its own soft/border/hover/text tokens; body text,
     headings and card surfaces stay neutral (defined in theme.css), so changing
     a color never reduces contrast anywhere else. --- */
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

  const relativeLuminance = hex => {
    const rgb = hexToRgb(hex);
    if (!rgb) return 0;
    const channel = v => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2]);
  };

  const contrastText = hex => (relativeLuminance(hex) > 0.35 ? '#101828' : '#ffffff');

  /* Per-group token derivations. Base neutrals come from the current theme so
     soft washes stay subtle; no text/body tokens are touched. */
  const GROUPS = {
    nav: {
      label: '主导航色',
      storageKey: 'javsp-web.nav-accent',
      defaults: { light: '#175cd3', dark: '#3b82f6' },
      presets: ['#175cd3', '#7c3aed', '#db2777', '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0d9488', '#0284c7', '#4b5563'],
      cssVar: '--nav-accent',
      tokens(value) {
        const dark = isDark();
        return {
          '--nav-accent': value,
          '--nav-accent-soft': mix(value, dark ? '#111113' : '#101828', dark ? 0.72 : 0.82),
          '--nav-accent-border': mix(value, dark ? '#111113' : '#101828', dark ? 0.45 : 0.6),
          '--nav-accent-text': mix(value, '#ffffff', dark ? 0.3 : 0.45),
          '--nav-accent-ink': mix(value, '#ffffff', dark ? 0.55 : 0.68),
          '--on-nav-accent': contrastText(value),
        };
      },
    },
    accent: {
      label: '主色',
      storageKey: 'javsp-web.accent',
      defaults: { light: '#175cd3', dark: '#2563eb' },
      presets: ['#175cd3', '#7c3aed', '#db2777', '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0d9488', '#0284c7', '#4b5563'],
      cssVar: '--accent',
      tokens(value) {
        const dark = isDark();
        const base = dark ? '#0b0d14' : '#f5f7fb';
        return {
          '--accent': value,
          '--accent-hover': mix(value, '#000000', 0.16),
          '--accent-border': mix(value, '#ffffff', 0.35),
          '--accent-soft': mix(value, base, dark ? 0.78 : 0.9),
          '--accent-border-soft': mix(value, base, 0.45),
          '--accent-surface': mix(value, base, dark ? 0.64 : 0.78),
          '--accent-border-pale': mix(value, base, dark ? 0.7 : 0.82),
          '--accent-ink': dark ? mix(value, '#ffffff', 0.25) : mix(value, '#000000', 0.28),
          '--accent-text': dark ? mix(value, '#ffffff', 0.3) : value,
          '--on-accent': contrastText(value),
          '--focus-ring': `${value}44`,
          '--focus-ring-strong': `${value}44`,
          '--focus-ring-library': `${value}44`,
          '--focus-ring-accent': mix(value, '#ffffff', 0.35),
        };
      },
    },
    'accent-2': {
      label: '副色',
      storageKey: 'javsp-web.accent-2',
      defaults: { light: '#9b4dca', dark: '#a855f7' },
      presets: ['#7c3aed', '#9b4dca', '#c026d3', '#db2777', '#e11d48', '#ea580c', '#65a30d', '#0d9488', '#0369a1', '#64748b'],
      cssVar: '--accent-2',
      tokens(value) {
        const dark = isDark();
        const base = dark ? '#0b0d14' : '#f5f7fb';
        return {
          '--accent-2': value,
          '--accent-2-hover': mix(value, '#000000', 0.16),
          '--accent-2-border': mix(value, '#ffffff', 0.35),
          '--accent-2-soft': mix(value, base, dark ? 0.78 : 0.9),
          '--accent-2-border-soft': mix(value, base, 0.45),
          '--accent-2-surface': mix(value, base, dark ? 0.64 : 0.78),
          '--accent-2-border-pale': mix(value, base, dark ? 0.7 : 0.82),
          '--accent-2-ink': dark ? mix(value, '#ffffff', 0.25) : mix(value, '#000000', 0.28),
          '--accent-2-text': dark ? mix(value, '#ffffff', 0.3) : value,
          '--on-accent-2': contrastText(value),
        };
      },
    },
  };
  const GROUP_ORDER = ['nav', 'accent', 'accent-2'];

  const readGroup = group => {
    try { return localStorage.getItem(group.storageKey); } catch { return null; }
  };
  const writeGroup = (group, value) => {
    try { if (value) localStorage.setItem(group.storageKey, value); else localStorage.removeItem(group.storageKey); } catch { /* keep for this page only */ }
  };

  function applyGroup(group, hex) {
    const value = /^#[0-9a-fA-F]{6}$/.test(hex || '') ? hex.toLowerCase() : null;
    Object.keys(group.tokens(value || '#000000')).forEach(name => root.style.removeProperty(name));
    if (!value) return;
    const palette = group.tokens(value);
    Object.entries(palette).forEach(([name, color]) => root.style.setProperty(name, color));
  }

  const applyAllGroups = () => { for (const key of GROUP_ORDER) { const group = GROUPS[key]; applyGroup(group, readGroup(group)); } };

  function currentGroupColor(group) {
    const stored = readGroup(group);
    if (stored) return stored;
    const styles = getComputedStyle(root);
    return (styles.getPropertyValue(group.cssVar) || '').trim() || group.defaults[isDark() ? 'dark' : 'light'];
  }

  /* Re-derive soft tints when the theme flips underneath custom colors. */
  const baseApply = apply;
  apply = theme => { baseApply(theme); applyAllGroups(); };

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
    popover.appendChild(title);

    const controls = {};
    for (const key of GROUP_ORDER) {
      const group = GROUPS[key];
      const section = document.createElement('div');
      section.className = 'palette-group';
      const label = document.createElement('p');
      label.className = 'palette-group-label';
      label.textContent = group.label;
      const swatches = document.createElement('div');
      swatches.className = 'palette-swatches';
      const presetButtons = group.presets.map(color => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'palette-swatch';
        button.style.setProperty('--swatch', color);
        button.dataset.color = color;
        button.title = color;
        button.setAttribute('aria-label', `使用${group.label} ${color}`);
        swatches.appendChild(button);
        return button;
      });
      const customLabel = document.createElement('label');
      customLabel.className = 'palette-custom';
      const customText = document.createElement('span');
      customText.textContent = '自定义';
      const customInput = document.createElement('input');
      customInput.type = 'color';
      customInput.setAttribute('aria-label', `自定义${group.label}`);
      customLabel.append(customText, customInput);
      section.append(label, swatches, customLabel);
      popover.appendChild(section);
      controls[key] = { group, presetButtons, customInput };
    }

    const resetRow = document.createElement('div');
    resetRow.className = 'palette-reset-row';
    const resetButton = document.createElement('button');
    resetButton.type = 'button';
    resetButton.className = 'button secondary palette-reset';
    resetButton.textContent = '恢复默认';
    resetButton.setAttribute('aria-label', '恢复默认主题色');
    resetRow.appendChild(resetButton);
    popover.appendChild(resetRow);
    document.body.appendChild(popover);

    let open = false;
    const syncSelection = () => {
      for (const key of GROUP_ORDER) {
        const { group, presetButtons, customInput } = controls[key];
        const current = currentGroupColor(group).toLowerCase();
        presetButtons.forEach(button => {
          const active = button.dataset.color.toLowerCase() === current;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', String(active));
        });
        customInput.value = /^#[0-9a-fA-F]{6}$/.test(current) ? current : '#175cd3';
      }
    };
    const position = trigger => {
      const rect = trigger.getBoundingClientRect();
      popover.style.top = `${rect.bottom + window.scrollY + 8}px`;
      popover.style.left = `${Math.max(8, rect.left + window.scrollX - 260 + rect.width)}px`;
    };
    const setOpen = next => {
      open = next;
      popover.hidden = !open;
      if (open) syncSelection();
      triggers.forEach(trigger => trigger.setAttribute('aria-expanded', String(open)));
    };

    const choose = (key, value) => {
      const group = GROUPS[key];
      const normalized = value ? value.toLowerCase() : '';
      writeGroup(group, normalized);
      applyGroup(group, normalized || undefined);
      syncSelection();
    };
    popover.addEventListener('click', event => {
      const swatch = event.target.closest?.('.palette-swatch');
      if (swatch) {
        const section = swatch.closest('.palette-group');
        const key = GROUP_ORDER.find(k => controls[k].presetButtons.includes(swatch));
        if (key) choose(key, swatch.dataset.color);
        return;
      }
      if (event.target.closest?.('.palette-reset')) {
        for (const key of GROUP_ORDER) choose(key, null);
      }
    });
    popover.addEventListener('input', event => {
      const input = event.target.closest?.('input[type="color"]');
      if (!input) return;
      const key = GROUP_ORDER.find(k => controls[k].customInput === input);
      if (key) choose(key, input.value);
    });
    popover.addEventListener('click', event => {
      if (event.target.closest?.('input[type="color"]')) event.stopPropagation();
    });

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
      if (GROUP_ORDER.some(key => event.key === GROUPS[key].storageKey) || event.key === null) {
        applyAllGroups();
        if (open) syncSelection();
      }
    });
  }

  applyAllGroups();
  buildPaletteUI();
  if (typeof window.JavspTheme === 'object') {
    window.JavspTheme.getAccent = () => currentGroupColor(GROUPS.accent);
    window.JavspTheme.setAccent = value => {
      writeGroup(GROUPS.accent, value ? value.toLowerCase() : null);
      applyGroup(GROUPS.accent, value || undefined);
    };
    window.JavspTheme.getGroupColor = key => currentGroupColor(GROUPS[key]);
    window.JavspTheme.setGroupColor = (key, value) => {
      const group = GROUPS[key];
      if (!group) return;
      writeGroup(group, value ? value.toLowerCase() : null);
      applyGroup(group, value || undefined);
    };
    window.JavspTheme.resetColors = () => { for (const key of GROUP_ORDER) { writeGroup(GROUPS[key], null); applyGroup(GROUPS[key], undefined); } };
  }

})();
