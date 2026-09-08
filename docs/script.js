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

const startDemo = document.querySelector('#start-demo');
if (startDemo) {
  const demoFile = document.querySelector('#demo-file');
  const task = document.querySelector('#demo-task');
  const empty = document.querySelector('#demo-empty');
  const title = document.querySelector('#demo-title');
  const status = document.querySelector('#demo-status');
  const stage = document.querySelector('#demo-stage');
  const percent = document.querySelector('#demo-percent');
  const bar = document.querySelector('#demo-progress-bar');
  const log = document.querySelector('#demo-log');
  const timeline = [...document.querySelectorAll('.demo-timeline > div')];
  const stages = ['识别番号', '聚合元数据', '下载图片', '写入媒体库'];
  let timer;

  startDemo.addEventListener('click', () => {
    clearInterval(timer);
    const code = demoFile.value;
    task.hidden = false;
    empty.hidden = true;
    title.textContent = code;
    startDemo.disabled = true;
    startDemo.innerHTML = '正在运行 <span>···</span>';
    let progress = 0;
    const render = () => {
      const current = Math.min(3, Math.floor(progress / 25));
      bar.style.width = `${progress}%`;
      percent.textContent = `${progress}%`;
      stage.textContent = progress === 100 ? '任务已完成' : `正在${stages[current]}`;
      status.textContent = progress === 100 ? '已完成' : '运行中';
      status.classList.toggle('is-finished', progress === 100);
      timeline.forEach((item, index) => {
        item.classList.toggle('is-done', index < current || progress === 100);
        item.classList.toggle('is-active', index === current && progress < 100);
        item.querySelector('small').textContent = index < current || progress === 100 ? '已完成' : index === current ? '进行中' : '等待中';
      });
      log.innerHTML = `<span>${progress === 100 ? `${code} 的元数据已写入媒体库。` : `正在${stages[current]}：${code}`}</span><time>演示数据</time>`;
    };
    render();
    timer = setInterval(() => {
      progress = Math.min(100, progress + 5);
      render();
      if (progress === 100) {
        clearInterval(timer);
        startDemo.disabled = false;
        startDemo.innerHTML = '再次运行演示 <span>↻</span>';
      }
    }, 220);
  });
}
