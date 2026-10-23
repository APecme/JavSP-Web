const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const {webcrypto}=require('node:crypto');
function fixture(options={}){
 const listeners={},callbacks={};const frame={contentWindow:{}};let closed=0;const requests=[],nodes=new Map();
 const node=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',value:'',hidden:false,disabled:false,addEventListener(){}});return nodes.get(id);};
 const dialog={querySelector:s=>s==='iframe'?frame:{addEventListener(){}},setAttribute(){},showModal(){},close(){closed++;},remove(){},addEventListener:(name,fn)=>callbacks[name]=fn,removeEventListener:name=>delete callbacks[name]};
 const profile={display_name:'tester#AB12',avatar_id:'',identity_ready:true,comment_token:'T'.repeat(43),...options.profile};
 const context=vm.createContext({window:{addEventListener:(n,fn)=>listeners[n]=fn,removeEventListener:n=>delete listeners[n]},document:{getElementById:node,querySelectorAll:()=>[],addEventListener(){},createElement:()=>dialog,body:{append(){}}},URL,URLSearchParams,crypto:webcrypto,AbortSignal,AbortController,setTimeout,clearTimeout,escapeHtml:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
  api:async()=>({...profile}),fetch:async(url,init)=>{requests.push({url,init});return {ok:true,status:200,json:async()=>({...profile})};}});
 // A real browser always has a page URL; only tests that ask for one get it.
 if(options.pageOrigin)context.location={origin:options.pageOrigin,href:options.pageOrigin+'/tasks/'};
 vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../javsp_web/web/assets/community.js'),'utf8'),context);
 const api=context.window.JavspCommunity;api.configure('base'in options?options.base:'https://comments.example',options.verify);
 return {api,listeners,frame,callbacks,requests,profile,get closed(){return closed;}};
}
test('verification accepts only the matching origin, window, nonce and action',async()=>{
 const f=fixture();const verification=f.api.verify('comment');let resolved=false;verification.then(()=>resolved=true);
 const nonce=new URLSearchParams(new URL(f.frame.src).hash.slice(1)).get('nonce');
 const good={origin:'https://comments.example',source:f.frame.contentWindow,data:{type:'javsp-verification',nonce,action:'comment',token:'unit-test-proof'}};
 for(const bad of [{...good,origin:'https://attacker.example'},{...good,source:{}},{...good,data:{...good.data,nonce:'wrong'}},{...good,data:{...good.data,action:'like'}},{...good,data:{...good.data,token:42}},{...good,data:{...good.data,token:'x'.repeat(4097)}}])f.listeners.message(bad);
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

test('same-origin API base keeps data calls relative, sends site credentials and verifies on its own origin',async()=>{
 const f=fixture({base:'/api/comments',verify:'https://comments.example'});
 await f.api.init();await f.api.requireIdentity();
 assert.equal(f.requests.length,1);
 assert.equal(f.requests[0].url,'/api/comments/api/me/profile');
 assert.equal(f.requests[0].init.credentials,'same-origin');
 assert.equal(f.requests[0].init.referrerPolicy,'no-referrer');
 assert.equal(f.requests[0].init.headers['X-User-Token'],'T'.repeat(43));
 assert.match(f.requests[0].init.headers.Accept,/application\/json/);
 const verification=f.api.verify('comment');
 assert.match(f.frame.src,/^https:\/\/comments\.example\/verify#/);
 const nonce=new URLSearchParams(new URL(f.frame.src).hash.slice(1)).get('nonce');
 assert.equal(new URLSearchParams(new URL(f.frame.src).hash.slice(1)).get('action'),'comment');
 const proof={type:'javsp-verification',nonce,action:'comment',token:'same-origin-proof'};
 f.listeners.message({origin:'https://app.example',source:f.frame.contentWindow,data:proof});
 await Promise.resolve();assert.equal(f.closed,0);
 f.listeners.message({origin:'https://comments.example',source:f.frame.contentWindow,data:proof});
 assert.equal(await verification,'same-origin-proof');assert.equal(f.closed,1);
});

test('a relative API base without a verification origin refuses to start a challenge',async()=>{
 const f=fixture({base:'/api/comments'});
 await assert.rejects(f.api.verify('comment'),/验证服务未配置/);
 assert.equal(f.frame.src,undefined);
});

test('legacy single-argument configure keeps verification on the API origin',async()=>{
 const f=fixture();
 assert.doesNotThrow(()=>f.api.configure('https://comments.example/'));
 const verification=f.api.verify('like');
 assert.match(f.frame.src,/^https:\/\/comments\.example\/verify#/);
 const nonce=new URLSearchParams(new URL(f.frame.src).hash.slice(1)).get('nonce');
 f.listeners.message({origin:'https://comments.example',source:f.frame.contentWindow,data:{type:'javsp-verification',nonce,action:'like',token:'legacy-proof'}});
 assert.equal(await verification,'legacy-proof');
});

test('an absolute legacy base keeps omitting credentials so site cookies never leave the site',async()=>{
 const f=fixture({base:'https://comments.example',pageOrigin:'https://app.example'});
 await f.api.init();await f.api.requireIdentity();
 assert.equal(f.requests[0].url,'https://comments.example/api/me/profile');
 assert.equal(f.requests[0].init.credentials,'omit');
 assert.equal(f.requests[0].init.referrerPolicy,'no-referrer');
});

test('request options cannot override the credential and referrer decision',()=>{
 const f=fixture({base:'/api/comments',pageOrigin:'https://app.example'});
 const sameSite=f.api.requestInit('/api/comments/api/me/profile',{credentials:'include',referrerPolicy:'unsafe-url'});
 assert.equal(sameSite.credentials,'same-origin');assert.equal(sameSite.referrerPolicy,'no-referrer');
 assert.equal(f.api.requestInit('https://comments.example/api/me/profile',{credentials:'include'}).credentials,'omit');
 // An absolute base on the page's own origin is still the same site.
 assert.equal(f.api.requestInit('https://app.example/api/comments/x').credentials,'same-origin');
 assert.equal(f.api.requestCredentials('/api/comments/api/threads/ABC-001/comments'),'same-origin');
 assert.equal(f.api.requestCredentials('//comments.example/api/config'),'omit');
});

test('an unknown page origin never guesses same-origin for an absolute base',()=>{
 const f=fixture({base:'https://app.example/api/comments'});
 assert.equal(f.api.requestInit('https://app.example/api/comments/api/config').credentials,'omit');
});

test('reconfiguring with only a base keeps the runtime verification source while the base is unchanged',async()=>{
 const f=fixture({base:'/api/comments',verify:'https://comments.example'});
 assert.doesNotThrow(()=>f.api.configure('/api/comments/'));
 const verification=f.api.verify('comment');
 assert.match(f.frame.src,/^https:\/\/comments\.example\/verify#/);
 const nonce=new URLSearchParams(new URL(f.frame.src).hash.slice(1)).get('nonce');
 f.listeners.message({origin:'https://comments.example',source:f.frame.contentWindow,data:{type:'javsp-verification',nonce,action:'comment',token:'kept-proof'}});
 assert.equal(await verification,'kept-proof');assert.equal(f.closed,1);
});

test('switching the API base drops the previous verification origin',async()=>{
 const f=fixture({base:'/api/comments',verify:'https://comments.example'});
 assert.doesNotThrow(()=>f.api.configure('/api/other-comments'));
 await assert.rejects(f.api.verify('comment'),/验证服务未配置/);
 assert.equal(f.frame.src,undefined);
 assert.doesNotThrow(()=>f.api.configure('/api/other-comments','https://verify.example'));
 const verification=f.api.verify('comment');
 assert.match(f.frame.src,/^https:\/\/verify\.example\/verify#/);
 const nonce=new URLSearchParams(new URL(f.frame.src).hash.slice(1)).get('nonce');
 f.listeners.message({origin:'https://comments.example',source:f.frame.contentWindow,data:{type:'javsp-verification',nonce,action:'comment',token:'stale-origin'}});
 await Promise.resolve();assert.equal(f.closed,0);
 f.listeners.message({origin:'https://verify.example',source:f.frame.contentWindow,data:{type:'javsp-verification',nonce,action:'comment',token:'fresh-origin'}});
 assert.equal(await verification,'fresh-origin');
});

test('an empty base disables the service: no request, no verification',async()=>{
 const f=fixture({base:'',verify:'https://comments.example'});
 await f.api.init();
 await assert.rejects(f.api.requireIdentity(),/评论服务未启用/);
 assert.equal(f.requests.length,0);
 await assert.rejects(f.api.verify('comment'),/评论服务未启用/);
 assert.equal(f.frame.src,undefined);
});
