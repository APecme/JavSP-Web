// Unified local SVG icons for every page and script.
//
// Usage in static HTML: <span data-icon="refresh"></span> (painted on DOM ready,
// data-icon-position="after" appends instead of prepends).
// Usage in scripts: window.JavspIcons.render('trash').
//
// Only the names registered below can be rendered: callers pass a name, never
// markup, and user supplied text never enters the SVG. Icons inherit
// currentColor, share one 24px viewBox and one stroke, and are aria-hidden
// because the surrounding control carries the accessible name.
(() => {
  'use strict';

  const STROKE_WIDTH = 1.8;
  const VIEW_BOX = '0 0 24 24';

  // Keep in sync with the CSS mask used by `details > summary::after`.
  const ICONS = Object.freeze({
    close: ['m7 7 10 10M17 7 7 17'],
    'chevron-up': ['m7 15 5-5 5 5'],
    'chevron-down': ['m7 9 5 5 5-5'],
    'chevron-left': ['m14 7-5 5 5 5'],
    'chevron-right': ['m10 7 5 5-5 5'],
    plus: ['M12 5v14M5 12h14'],
    trash: ['M4 7h16', 'M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2', 'M6.5 7l.9 12a2 2 0 0 0 2 1.9h5.2a2 2 0 0 0 2-1.9L17.5 7', 'M10 11v6M14 11v6'],
    pencil: ['m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15v5Z'],
    refresh: ['M3 12a9 9 0 0 1 15.3-6.4L21 8', 'M21 3v5h-5', 'M21 12a9 9 0 0 1-15.3 6.4L3 16', 'M8 16H3v5'],
    send: ['M12 19V5', 'm5 12 7-7 7 7'],
    stop: ['M9 7h6a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z'],
    menu: ['M4 7h16M4 12h16M4 17h16'],
    folder: ['M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z'],
    file: ['M6 4h7l5 5v11a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z', 'M13 4v5h5'],
    'arrow-left': ['M19 12H5', 'm11 6-6 6 6 6'],
    copy: ['M8 8V6a2 2 0 0 1 2-2h5l4 4v5a2 2 0 0 1-2 2h-2', 'M6 8h5l4 4v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2Z'],
    info: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M12 11v5', 'M12 7.6h.01'],
  });

  const hasIcon = (name) => typeof name === 'string' && Object.prototype.hasOwnProperty.call(ICONS, name);

  // Extra classes are optional styling only; anything that could break out of
  // the attribute (quotes, spaces, event handler names) is discarded.
  function sanitizeClass(value) {
    if (typeof value !== 'string') return '';
    return value.split(/[\s,]+/)
      .filter(token => /^[a-z0-9-]+$/i.test(token) && !/^on/i.test(token))
      .slice(0, 4)
      .join(' ');
  }

  function sanitizeStrokeWidth(value) {
    const width = Number(value);
    return Number.isFinite(width) && width >= 1 && width <= 3 ? Math.round(width * 100) / 100 : STROKE_WIDTH;
  }

  // Returns trusted markup for a whitelisted name, or an empty string. The
  // name is looked up in a frozen table, so no caller input reaches the markup.
  function render(name, options) {
    if (!hasIcon(name)) return '';
    const className = sanitizeClass(options && options.className);
    const strokeWidth = sanitizeStrokeWidth(options && options.strokeWidth);
    const body = ICONS[name].map(path => `<path d="${path}"/>`).join('');
    return `<svg class="javsp-icon${className ? ` ${className}` : ''}" viewBox="${VIEW_BOX}" width="1em" height="1em"`
      + ` fill="none" stroke="currentColor" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round"`
      + ` aria-hidden="true" focusable="false">${body}</svg>`;
  }

  function paint(element) {
    if (!element || !element.dataset || element.dataset.iconPainted === '1') return false;
    const markup = render(element.dataset.icon);
    if (!markup || typeof element.insertAdjacentHTML !== 'function') return false;
    element.insertAdjacentHTML(element.dataset.iconPosition === 'after' ? 'beforeend' : 'afterbegin', markup);
    element.dataset.iconPainted = '1';
    return true;
  }

  // Fills every [data-icon] slot below root. Safe to call again after content
  // is re-rendered; already painted slots are skipped.
  function refresh(root) {
    const scope = root || document;
    const slots = scope.querySelectorAll ? scope.querySelectorAll('[data-icon]') : [];
    let painted = 0;
    for (let index = 0; index < slots.length; index += 1) {
      if (paint(slots[index])) painted += 1;
    }
    return painted;
  }

  const api = Object.freeze({ render, refresh, names: () => Object.keys(ICONS) });
  window.JavspIcons = api;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => refresh(document), { once: true });
  } else {
    refresh(document);
  }
})();
