const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const {webcrypto}=require('node:crypto');
function fixture(){
 const listeners={},callbacks={};const frame={contentWindow:{}};let closed=0;
 const dialog={querySelector:s=>s==='iframe'?frame:{addEventListener(){}},setAttribute(){},showModal(){},close(){closed++;},remove(){},addEventListener:(name,fn)=>callbacks[name]=fn,removeEventListener:name=>delete callbacks[name]};
 const context=vm.createContext({window:{addEventListener:(n,fn)=>listeners[n]=fn,removeEventListener:n=>delete listeners[n]},document:{getElementById:()=>null,addEventListener(){},createElement:()=>dialog,body:{append(){}}},URL,URLSearchParams,crypto:webcrypto,setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../javsp_web/web/assets/community.js'),'utf8'),context);
 const api=context.window.JavspCommunity;api.configure('https://comments.example');
 return {api,listeners,frame,callbacks,get closed(){return closed;}};
}
test('verification accepts only the matching origin, window, nonce and action',async()=>{
 const f=fixture();const verification=f.api.verify('comment');let resolved=false;verification.then(()=>resolved=true);
 const nonce=new URLSearchParams(new URL(f.frame.src).hash.slice(1)).get('nonce');
 const good={origin:'https://comments.example',source:f.frame.contentWindow,data:{type:'javsp-verification',nonce,action:'comment',token:'unit-test-proof'}};
 for(const bad of [{...good,origin:'https://attacker.example'},{...good,source:{}},{...good,data:{...good.data,nonce:'wrong'}},{...good,data:{...good.data,action:'like'}}])f.listeners.message(bad);
 await Promise.resolve();assert.equal(resolved,false);
 f.listeners.message(good);assert.equal(await verification,'unit-test-proof');assert.equal(f.closed,1);assert.equal(f.listeners.message,undefined);
});

test('adaptive requests challenge only after 428 and retry once through the real verification flow', async()=>{
 const f=fixture();let calls=0;
 const pending=f.api.withChallenge('comment',async token=>{calls++;if(calls===1){assert.equal(token,'');throw Object.assign(new Error('challenge'),{status:428});}assert.equal(token,'proof');return 'posted';});
 await new Promise(resolve=>setImmediate(resolve));
 const nonce=new URLSearchParams(new URL(f.frame.src).hash.slice(1)).get('nonce');
 f.listeners.message({origin:'https://comments.example',source:f.frame.contentWindow,data:{type:'javsp-verification',nonce,action:'comment',token:'proof'}});
 assert.equal(await pending,'posted');assert.equal(calls,2);assert.equal(f.closed,1);
 await assert.rejects(f.api.withChallenge('like',async()=>{throw Object.assign(new Error('limited'),{status:429});}),/limited/);
 assert.equal(f.closed,1);
});
test('canceling verification rejects the action and allows a later attempt',async()=>{
 const f=fixture();const first=f.api.verify('like');await assert.rejects(f.api.verify('like'),/先完成/);
 const rejection=assert.rejects(first,/取消/);f.callbacks.close();await rejection;
 const next=f.api.verify('like');const second=assert.rejects(next,/取消/);f.callbacks.close();await second;
});
