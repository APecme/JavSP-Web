const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../javsp_web/web/assets/hot-clash.js'),'utf8');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function setup(){
 const nodes={};for(const id of ['dialog','message','start','cancel','export','results','sites','controller','secret','proxy','confirm','form','status','close','yaml']) nodes['hot-clash-'+id]={dataset:{},events:{},value:'',checked:false,disabled:false,innerHTML:'',options:[],selectedOptions:[{value:'avbase'}],files:[],open:true,addEventListener(name,fn){this.events[name]=fn},close(){this.open=false;this.events.close?.()}};
 const calls=[],timers=new Map();let n=0;let handler=()=>({running:false,results:[],restore_state:'not_needed'});
 const context=vm.createContext({window:{JavspHot:{escape:v=>String(v??'').replaceAll('<','&lt;'),openDialog:id=>{nodes[id].open=true},api:async(p,opts={})=>{calls.push({p,opts});return handler(p,opts)}}},document:{readyState:'complete',getElementById:id=>nodes[id],querySelectorAll:()=>[]},setTimeout:(fn,ms)=>{timers.set(++n,{fn,ms});return n},clearTimeout:id=>timers.delete(id),AbortController,console});
 vm.runInContext(source,context);return{nodes,calls,timers,api:context.window.JavspHotClash,handler:fn=>{handler=fn}};
}
test('opening is read-only and never mutates Clash',async()=>{
 const h=setup();h.handler(p=>p==='/connections'?{sources:[{id:'avbase',name:'AvBase',result:{}}]}:{running:false,results:[]});await h.api.open();assert.ok(h.calls.every(c=>!c.opts.method));assert.match(h.nodes['hot-clash-sites'].innerHTML,/avbase/);
});
test('checkbox is required before any diagnostic POST',async()=>{
 const h=setup();await h.nodes['hot-clash-form'].events.submit({preventDefault(){}});assert.equal(h.calls.length,0);assert.match(h.nodes['hot-clash-message'].textContent,/必须确认/);
});
test('confirmed start sends secret once and clears it and the checkbox',async()=>{
 const h=setup();h.nodes['hot-clash-confirm'].checked=true;h.nodes['hot-clash-secret'].value='private';h.nodes['hot-clash-controller'].value='http://localhost:9090';h.nodes['hot-clash-proxy'].value='http://localhost:7890';h.handler(()=>({running:true,results:[],completed:0,total:2,restore_state:'pending'}));await h.nodes['hot-clash-form'].events.submit({preventDefault(){}});assert.equal(h.calls.length,1);assert.equal(JSON.parse(h.calls[0].opts.body).secret,'private');assert.equal(h.nodes['hot-clash-secret'].value,'');assert.equal(h.nodes['hot-clash-confirm'].checked,false);assert.equal(h.nodes['hot-clash-start'].disabled,true);
});
test('closing a running diagnostic requests cancel and restore',async()=>{
 const h=setup();h.handler(p=>p==='/connections'?{sources:[]}:{running:true,results:[],restore_state:'pending'});await h.api.open();h.nodes['hot-clash-dialog'].close();await tick();assert.ok(h.calls.some(c=>c.p==='/clash/cancel'&&c.opts.method==='POST'));
});
test('restore failure disables YAML export and shows a warning',async()=>{
 const h=setup();h.handler(p=>p==='/connections'?{sources:[]}:{running:false,results:[],restore_state:'failed',message:'警告：请手动恢复'});await h.api.open();assert.equal(h.nodes['hot-clash-export'].disabled,true);assert.match(h.nodes['hot-clash-message'].textContent,/手动恢复/);
});
