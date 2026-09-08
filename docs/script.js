const menuToggle = document.querySelector('.menu-toggle');
const siteNav = document.querySelector('.site-nav');
menuToggle?.addEventListener('click', () => {
  const open = siteNav.classList.toggle('is-open');
  menuToggle.setAttribute('aria-expanded', String(open));
});
siteNav?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
  siteNav.classList.remove('is-open');
  menuToggle?.setAttribute('aria-expanded', 'false');
}));

document.querySelectorAll('.install-tab').forEach((tab) => tab.addEventListener('click', () => {
  document.querySelectorAll('.install-tab').forEach((item) => {
    const active = item === tab;
    item.classList.toggle('is-active', active);
    item.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('.install-content').forEach((panel) => panel.classList.toggle('is-active', panel.id === tab.dataset.target));
}));

function copyText(value) {
  const input = document.createElement('textarea');
  input.value = value;
  input.style.position = 'fixed';
  input.style.opacity = '0';
  document.body.append(input);
  input.select();
  document.execCommand('copy');
  input.remove();
  navigator.clipboard?.writeText(value).catch(() => {
    // The synchronous fallback above supports browsers without clipboard permission.
  });
}

document.querySelectorAll('.copy-button').forEach((button) => button.addEventListener('click', () => {
  copyText(button.dataset.copy);
  const original = button.textContent;
  button.textContent = '已复制';
  setTimeout(() => { button.textContent = original; }, 1600);
}));
