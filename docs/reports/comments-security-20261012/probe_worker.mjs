import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import worker from '../../../comments-service/worker/src/index.js';

// All writes and challenge responses are isolated synthetic data.
const db = new DatabaseSync(':memory:');
db.exec(readFileSync(new URL('../../../comments-service/worker/schema.sql', import.meta.url), 'utf8'));
const hash = s => createHash('sha256').update(s).digest('hex');
const token = 'synthetic-session-'.repeat(4);
db.prepare('INSERT INTO identities VALUES (?,?,?,?,?,?)').run('audit-user', 'audit', 'unused', '0001', '', 0);
db.prepare('INSERT INTO identity_sessions VALUES (?,?,?)').run(hash(token), 'audit-user', Math.floor(Date.now()/1000)+3600);
let queries = 0;
const prepare = sql => {
  let values = [];
  return {
    bind(...args) { values = args; return this; },
    async first() { queries++; return db.prepare(sql).get(...values) || null; },
    async all() { queries++; return {results: db.prepare(sql).all(...values)}; },
    async run() { queries++; return {meta: {changes: db.prepare(sql).run(...values).changes}}; },
  };
};
const env = { DB: {prepare, async batch(items) {const out=[];for(const item of items)out.push(await item.run());return out;}},
  ADMIN_TOKEN: 'a'.repeat(48), IP_HASH_SECRET: 'b'.repeat(48), IDENTITY_SECRET: 'c'.repeat(48),
  TURNSTILE_SITE_KEY: 'synthetic', TURNSTILE_SECRET_KEY: 'synthetic', CORS_ORIGINS: '*' };
globalThis.fetch = async (url, opts) => {
  if (url !== 'https://challenges.cloudflare.com/turnstile/v0/siteverify') throw Error('Unexpected network');
  return Response.json({success:true, hostname:'comments.rtioo.com', action:opts.body.get('response')});
};
const call = (path, method='GET', payload, ip='192.0.2.1', authenticated=true) => worker.fetch(new Request('https://audit.invalid'+path, {
  method, headers: {'CF-Connecting-IP':ip, ...(authenticated?{'X-User-Token':token}:{}), 'Content-Type':'application/json'},
  body: payload === undefined ? undefined : JSON.stringify(payload),
}), env);
const result = {};
const writes = [];
for(let i=0;i<12;i++) writes.push((await call('/api/threads/AUDIT-123/comments','POST',{body:'Synthetic comment',turnstile_token:'comment'},`192.0.2.${i+1}`)).status);
result.same_identity_across_12_ips = {statuses:writes, count:db.prepare('SELECT COUNT(*) n FROM comments').get().n};
queries=0;
const reads=[];
for(let i=0;i<150;i++) reads.push((await call('/api/threads/AUDIT-123/comments','GET',undefined,'198.51.100.1',false)).status);
result.anonymous_reads = {requests:reads.length, all_200:reads.every(x=>x===200), database_queries:queries,
  rate_entries:db.prepare("SELECT COUNT(*) n FROM rate_limits WHERE action NOT IN ('comment','verification')").get().n};
db.exec('DELETE FROM rate_limits');
const attempts=[];
for(let i=0;i<30;i++) attempts.push((await call('/api/identity','POST',{username:'victim',pin:'111111',mode:'login',turnstile_token:'identity'},`203.0.113.${i+1}`,false)).status);
result.name_lockout={wrong_attempts:attempts.filter(x=>x===401).length,
  following_create_status:(await call('/api/identity','POST',{username:'victim',pin:'222222',mode:'create',turnstile_token:'identity'},'203.0.113.100',false)).status};
db.exec('DELETE FROM rate_limits');
const auth = async ip => (await call('/api/identity','POST',{username:'shared',pin:'123456',mode:'create',turnstile_token:'identity'},ip,false)).json();
const a=await auth('192.0.2.100'), b=await auth('192.0.2.101');
result.duplicate_registration={same_identity:a.display_name===b.display_name, distinct_active_sessions:a.comment_token!==b.comment_token,
  session_count:db.prepare("SELECT COUNT(*) n FROM identity_sessions s JOIN identities i ON i.id=s.identity_id WHERE i.username='shared'").get().n};
const ins=db.prepare('INSERT INTO reports(comment_id,identity,reason,created_at) VALUES (1,?,?,0)');
for(let i=0;i<1500;i++) ins.run('synthetic-ip-'+i,'\u62a5'.repeat(300));
const req=new Request('https://audit.invalid/api/admin/comments?status=reported',{headers:{Authorization:'Bearer '+env.ADMIN_TOKEN}});
const response=await worker.fetch(req,env), raw=await response.text();
result.unbounded_report_expansion={status:response.status, bytes:Buffer.byteLength(raw), proxy_limit:1048576,
  reports:JSON.parse(raw).items[0].reports.length};
console.log(JSON.stringify(result,null,2));
