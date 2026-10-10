(() => {
  function inline(target, source) {
    const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^\s)]+\))/g;
    let offset = 0;
    for (const match of source.matchAll(pattern)) {
      target.append(document.createTextNode(source.slice(offset, match.index)));
      const token = match[0];
      let element;
      if (token.startsWith('`')) {
        element = document.createElement('code');
        element.textContent = token.slice(1, -1);
      } else if (token.startsWith('**')) {
        element = document.createElement('strong');
        element.textContent = token.slice(2, -2);
      } else {
        const link = token.match(/^\[([^\]]+)\]\((.+)\)$/);
        let safe = false;
        try { safe = ['https:', 'http:'].includes(new URL(link[2]).protocol); } catch {}
        element = document.createElement(safe ? 'a' : 'span');
        element.textContent = link[1];
        if (safe) {
          element.href = link[2];
          element.target = '_blank';
          element.rel = 'noopener noreferrer';
        }
      }
      target.append(element);
      offset = match.index + token.length;
    }
    target.append(document.createTextNode(source.slice(offset)));
  }

  function render(source) {
    const target = document.createElement('div');
    target.className = 'ai-markdown';
    const lines = String(source || '').replace(/\r\n/g, '\n').split('\n');
    let position = 0;
    while (position < lines.length) {
      const line = lines[position];
      if (!line.trim()) { position += 1; continue; }
      const fence = line.match(/^\s*```(.*)$/);
      if (fence) {
        const block = document.createElement('div');
        block.className = 'ai-code-block';
        const header = document.createElement('div');
        header.className = 'ai-code-heading';
        const label = document.createElement('span');
        label.textContent = fence[1].trim() || '代码';
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'icon-button';
        copy.textContent = '复制代码';
        const content = [];
        position += 1;
        while (position < lines.length && !/^\s*```/.test(lines[position])) content.push(lines[position++]);
        position += 1;
        const pre = document.createElement('pre');
        const code = document.createElement('code');
        code.textContent = content.join('\n');
        copy.addEventListener('click', async () => {
          try { await navigator.clipboard.writeText(code.textContent); copy.textContent = '已复制'; }
          catch { copy.textContent = '请选中代码复制'; }
        });
        header.append(label, copy);
        pre.append(code);
        block.append(header, pre);
        target.append(block);
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      const item = line.match(/^\s*(?:[-*+] |\d+\. )(.+)$/);
      const quote = line.match(/^>\s?(.*)$/);
      let element;
      if (heading) {
        element = document.createElement(`h${Math.min(heading[1].length + 1, 6)}`);
        inline(element, heading[2]);
      } else if (item) {
        const ordered = /^\s*\d+\./.test(line);
        element = document.createElement(ordered ? 'ol' : 'ul');
        while (position < lines.length) {
          const next = lines[position].match(ordered ? /^\s*\d+\. (.+)$/ : /^\s*[-*+] (.+)$/);
          if (!next) break;
          const child = document.createElement('li');
          inline(child, next[1]);
          element.append(child);
          position += 1;
        }
        target.append(element);
        continue;
      } else {
        element = document.createElement(quote ? 'blockquote' : 'p');
        inline(element, quote ? quote[1] : line);
      }
      target.append(element);
      position += 1;
    }
    return target;
  }
  window.JavspMarkdown = { render };
})();
