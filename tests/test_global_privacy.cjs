const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const root=path.resolve(__dirname,'..');const read=name=>fs.readFileSync(path.join(root,name),'utf8');
test('one privacy switch lives in shared topbar, not in library toolbar',()=>{
 for(const file of ['javsp_web/web/index.html','docs/demo.html']){
  const html=read(file);assert.equal([...html.matchAll(/id="privacy-mode"/g)].length,1);
  const header=html.slice(html.indexOf('<header class="topbar">'),html.indexOf('</header>'));
  assert.match(header,/id="privacy-mode"/);assert.match(header,/aria-label="全站隐私模式"/);
  const library=html.slice(html.indexOf('<section class="view active" data-panel="overview"'),html.indexOf('data-panel="ai-scrape"'));
  assert.doesNotMatch(library,/id="privacy-mode"/);
 }
});
test('shared privacy state restores, updates ARIA and persists under existing key',()=>{
 const code=read('javsp_web/web/assets/app.js');const snippet=code.slice(code.indexOf("const privacyMode = $('#privacy-mode');"),code.indexOf('// --- Stills viewer'));
 const control={checked:false,attrs:{},setAttribute(k,v){this.attrs[k]=v},addEventListener(name,fn){this.change=fn}};
 const document={documentElement:{dataset:{privacyMode:'1'},offsetHeight:100}};const storage={};const state={privacyMode:true};
 vm.runInNewContext(snippet,{$:()=>control,state,document,localStorage:{setItem:(k,v)=>{storage[k]=v}}});
 assert.equal(control.checked,true);assert.equal(control.attrs['aria-checked'],'true');
 control.checked=false;control.change();assert.equal(document.documentElement.dataset.privacyMode,'0');assert.equal(storage['javsp-web.privacy-mode'],'0');
 control.checked=true;control.change();assert.equal(document.documentElement.dataset.privacyMode,'1');assert.equal(control.attrs['aria-checked'],'true');
 assert.match(read('javsp_web/web/assets/hot.css'),/html\[data-privacy-mode="1"\] \.hot-cover-image/);
 assert.match(read('javsp_web/web/assets/cinema.css'),/html\[data-privacy-mode="1"\].*\.stills-image/);
});
