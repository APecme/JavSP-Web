// Sidebar navigation: desktop collapse (240px / 72px) and phone drawer (56px rail + overlay).
// Small, standalone owner of the sidebar toggle. app.js keeps handling views; this file only
// owns navigation chrome, ARIA state and the legacy "javsp-web.sidebar-collapsed" preference.
(function (global) {
  'use strict';

  const MOBILE_QUERY = '(max-width: 800px)';
  const COLLAPSE_KEY = 'javsp-web.sidebar-collapsed';
  const COLLAPSED_CLASS = 'sidebar-collapsed';
  const DRAWER_CLASS = 'sidebar-drawer-open';
  const LOCK_CLASS = 'nav-drawer-open';

  function createNavigation(env) {
    const doc = env.document;
    const win = env.window;
    const shell = doc.querySelector('.app-shell');
    const sidebar = doc.getElementById('sidebar');
    const toggle = doc.getElementById('sidebar-toggle');
    const backdrop = doc.getElementById('sidebar-backdrop');
    const nav = doc.getElementById('sidebar-nav');
    const heading = doc.getElementById('section-title');

    let storage = env.storage;
    if (!storage) {
      try { storage = win.localStorage; } catch (error) { storage = null; }
    }
    const media = typeof win.matchMedia === 'function' ? win.matchMedia(MOBILE_QUERY) : null;
    const Observer = win.MutationObserver || global.MutationObserver;

    let collapsed = readCollapsed();
    let drawerOpen = false;
    let observer = null;
    let initialized = false;

    function isMobile() {
      return Boolean(media && media.matches);
    }

    function readCollapsed() {
      try {
        return storage ? storage.getItem(COLLAPSE_KEY) === '1' : false;
      } catch (error) {
        return false;
      }
    }

    function writeCollapsed() {
      try { if (storage) storage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0'); } catch (error) { /* storage may be blocked */ }
    }

    function activeItem() {
      const items = doc.querySelectorAll('.nav-item');
      for (const item of items) {
        if (item.classList.contains('active') && !item.hidden && !item.disabled) return item;
      }
      return null;
    }

    function apply() {
      shell.classList.toggle(COLLAPSED_CLASS, collapsed);
      sidebar.classList.toggle(DRAWER_CLASS, drawerOpen);
      doc.documentElement.classList.toggle(LOCK_CLASS, drawerOpen);
      if (backdrop) backdrop.hidden = !drawerOpen;
    }

    function syncToggle() {
      const mobile = isMobile();
      const expanded = mobile ? drawerOpen : !collapsed;
      const label = mobile
        ? (drawerOpen ? '关闭导航菜单' : '打开导航菜单')
        : (collapsed ? '展开侧边栏' : '收起侧边栏');
      toggle.setAttribute('aria-expanded', String(expanded));
      toggle.setAttribute('aria-label', label);
      toggle.setAttribute('title', label);
    }

    function syncCurrent() {
      for (const item of doc.querySelectorAll('.nav-item')) {
        if (item.classList.contains('active')) item.setAttribute('aria-current', 'page');
        else item.removeAttribute('aria-current');
      }
    }

    function focusElement(element) {
      if (!element || typeof element.focus !== 'function') return;
      try { element.focus({ preventScroll: true }); } catch (error) { element.focus(); }
    }

    function focusHeading() {
      if (!heading) return;
      if (!heading.hasAttribute('tabindex')) heading.setAttribute('tabindex', '-1');
      focusElement(heading);
    }

    function openDrawer() {
      if (!isMobile() || drawerOpen) return;
      drawerOpen = true;
      apply();
      syncToggle();
      focusElement(activeItem() || toggle);
    }

    function closeDrawer({ restoreFocus = true } = {}) {
      if (!drawerOpen) return;
      drawerOpen = false;
      apply();
      syncToggle();
      if (restoreFocus) focusElement(toggle);
    }

    function setCollapsed(next, { persist = true } = {}) {
      collapsed = Boolean(next);
      apply();
      syncToggle();
      if (persist) writeCollapsed();
    }

    function toggleNavigation() {
      if (isMobile()) {
        if (drawerOpen) closeDrawer();
        else openDrawer();
        return;
      }
      setCollapsed(!collapsed);
    }

    function onToggleClick() {
      toggleNavigation();
    }

    function onNavClick(event) {
      const target = event.target;
      const item = target && typeof target.closest === 'function' ? target.closest('.nav-item') : null;
      if (!item || !isMobile()) return;
      if (!drawerOpen) return;
      closeDrawer({ restoreFocus: false });
      focusHeading();
    }

    function focusables() {
      if (typeof sidebar.querySelectorAll !== 'function') return [];
      return [...sidebar.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
        .filter(element => !element.disabled && !element.hidden);
    }

    function onKeydown(event) {
      const key = event.key;
      if (key === 'Escape' && drawerOpen) {
        if (doc.querySelector('dialog[open]')) return;
        if (typeof event.preventDefault === 'function') event.preventDefault();
        closeDrawer();
        return;
      }
      if (key !== 'Tab' || !drawerOpen || !isMobile()) return;
      const list = focusables();
      if (!list.length) return;
      const first = list[0];
      const last = list[list.length - 1];
      const current = doc.activeElement;
      if (event.shiftKey && (current === first || !list.includes(current))) {
        if (typeof event.preventDefault === 'function') event.preventDefault();
        focusElement(last);
      } else if (!event.shiftKey && current === last) {
        if (typeof event.preventDefault === 'function') event.preventDefault();
        focusElement(first);
      }
    }

    function onBackdropClick() {
      closeDrawer();
    }

    function onViewportChange() {
      if (!isMobile() && drawerOpen) {
        drawerOpen = false;
        apply();
      }
      syncToggle();
    }

    function bind() {
      toggle.addEventListener('click', onToggleClick);
      if (backdrop) backdrop.addEventListener('click', onBackdropClick);
      if (nav) nav.addEventListener('click', onNavClick);
      doc.addEventListener('keydown', onKeydown);
      if (media && typeof media.addEventListener === 'function') media.addEventListener('change', onViewportChange);
      else if (media && typeof media.addListener === 'function') media.addListener(onViewportChange);
    }

    function nameItems() {
      for (const item of doc.querySelectorAll('.nav-item')) {
        const label = item.querySelector('.nav-item-label');
        const text = label && label.textContent ? label.textContent.trim() : '';
        if (text && !item.getAttribute('title')) item.setAttribute('title', text);
        if (text && !item.getAttribute('aria-label')) item.setAttribute('aria-label', text);
      }
    }

    function init() {
      // The login page has no sidebar: never touch it.
      if (!shell || !sidebar || !toggle) return false;
      if (initialized) return true;
      initialized = true;
      apply();
      syncToggle();
      nameItems();
      syncCurrent();
      if (Observer && nav) {
        observer = new Observer(syncCurrent);
        observer.observe(nav, { attributes: true, attributeFilter: ['class'], childList: true, subtree: true });
      }
      bind();
      return true;
    }

    return {
      init, isMobile, isCollapsed: () => collapsed, isDrawerOpen: () => drawerOpen,
      setCollapsed, openDrawer, closeDrawer, toggle: toggleNavigation, syncCurrent,
    };
  }

  if (typeof global !== 'undefined') global.JavspNavigation = { create: createNavigation };

  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    const start = () => {
      if (!window.JavspNavigation || !window.JavspNavigation.init) window.JavspNavigation = createNavigation({ document, window });
      window.JavspNavigation.init();
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
  }
})(typeof window !== 'undefined' ? window : globalThis);
