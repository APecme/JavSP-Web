const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const assets=path.join(__dirname,'../javsp_web/web/assets');
const context=vm.createContext({window:{markdownit:require(path.join(assets,'markdown-it.min.js'))}});
vm.runInContext(fs.readFileSync(path.join(assets,'comment-markdown.js'),'utf8'),context);
const render=(text,options)=>context.window.JavspCommentMarkdown.render(text,options);

test('comment Markdown supports formatting without executing HTML or unsafe links',()=>{
 const html=render('**粗体** *斜体* ~~删除~~\n\n- 列表\n\n> 引用\n\n`代码`\n\n[链接](https://example.com)\n\n<script>alert(1)</script>\n\n[x](javascript:alert%281%29)\n\n![图](https://tracker.test/x.png)');
 for(const tag of ['strong','em','s','ul','blockquote','code'])assert.match(html,new RegExp('<'+tag+'[ >]'));
 assert.match(html,/href="https:\/\/example.com"/);assert.match(html,/noopener noreferrer/);
 assert.doesNotMatch(html,/<script|<img|href="javascript:/i);assert.match(html,/&lt;script&gt;/);
});

test('time labels resolve to seconds only in plain Markdown text',()=>{
 const html=render('精彩 30:15，再看 1:02:03。\n\n`02:00` [链接 03:00](https://example.com/04:00)\n\n```\n05:00\n```');
 assert.match(html,/data-comment-time="1815"[^>]*>30:15</);
 assert.match(html,/data-comment-time="3723"[^>]*>1:02:03</);
 assert.equal((html.match(/data-comment-time=/g)||[]).length,2);
 assert.doesNotMatch(render('99:99 1:99:00 abc30:15 https://example.com/30:15 30:15.5'),/data-comment-time/);
 assert.doesNotMatch(render('30:15',{timestamps:false}),/data-comment-time/);
});

test('nested Markdown cannot forge time buttons or bypass link validation',()=>{
 const html=render('**看 *30:15*** <button data-comment-time="0">x</button> [x](jav&#x61;script:alert%281%29)');
 assert.equal((html.match(/data-comment-time="1815"/g)||[]).length,1);
 assert.doesNotMatch(html,/<button[^>]*data-comment-time="0"|href="javascript:/);
});
