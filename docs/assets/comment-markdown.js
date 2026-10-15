// Markdown-it 14.1.0: HTML disabled; time controls are generated from validated text tokens.
window.JavspCommentMarkdown = (() => {
  const parser = window.markdownit({ html: false, breaks: true, linkify: false, maxNesting: 20 });
  const escape = parser.utils.escapeHtml;
  parser.validateLink = value => /^https?:\/\//i.test(value.trim());
  const openLink = parser.renderer.rules.link_open || ((tokens, index, options, env, renderer) => renderer.renderToken(tokens, index, options));
  parser.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
    tokens[index].attrSet('target', '_blank');
    tokens[index].attrSet('rel', 'noopener noreferrer nofollow ugc');
    return openLink(tokens, index, options, env, renderer);
  };
  // Do not contact external image hosts just to display a public comment.
  parser.renderer.rules.image = (tokens, index) => escape(tokens[index].content);
  parser.core.ruler.after('inline', 'comment_times', state => {
    if (state.env.timestamps === false) return;
    for (const block of state.tokens) {
      if (block.type !== 'inline') continue;
      const children = [];
      let linkDepth = 0;
      for (const token of block.children) {
        if (token.type === 'link_open') linkDepth++;
        if (token.type !== 'text' || linkDepth) children.push(token);
        else {
          const pattern = /(?<![A-Za-z0-9_:/])((?:\d{1,3}:)?\d{1,3}:\d{2})(?![A-Za-z0-9_:]|\.\d)/g;
          let offset = 0;
          for (const match of token.content.matchAll(pattern)) {
            const parts = match[0].split(':').map(Number);
            if (parts.at(-1) >= 60 || (parts.length === 3 && parts[1] >= 60)) continue;
            const seconds = parts.reduce((sum, part) => sum * 60 + part, 0);
            if (seconds > 604800) continue;
            const prefix = new state.Token('text', '', 0);
            prefix.content = token.content.slice(offset, match.index);
            children.push(prefix);
            const time = new state.Token('comment_time', 'button', 0);
            time.content = match[0];
            time.meta = { seconds };
            children.push(time);
            offset = match.index + match[0].length;
          }
          const tail = new state.Token('text', '', 0);
          tail.content = token.content.slice(offset);
          children.push(tail);
        }
        if (token.type === 'link_close') linkDepth--;
      }
      block.children = children;
    }
  });
  parser.renderer.rules.comment_time = (tokens, index) => {
    const token = tokens[index], label = escape(token.content);
    return `<button type="button" class="comment-timestamp" data-comment-time="${token.meta.seconds}" title="从 ${label} 开始播放">${label}</button>`;
  };
  return { render: (source, options = {}) => parser.render(String(source || ''), options) };
})();
