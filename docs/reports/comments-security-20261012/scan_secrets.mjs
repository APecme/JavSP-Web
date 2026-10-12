import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'../../..');
const vars=Object.fromEntries(readFileSync(resolve(root,'comments-service/worker/.dev.vars'),'utf8').split(/\r?\n/).filter(x=>x.includes('=')).map(x=>[x.slice(0,x.indexOf('=')),x.slice(x.indexOf('=')+1).replace(/^["']|["']$/g,'')]));
const known=Object.entries(vars).filter(([k,v])=>k!=='TURNSTILE_SITE_KEY'&&v.length>=20);
const patterns=[['github-token',/\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b/],['openai-token',/\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b/],['private-key',/-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----/]];
const textFile=p=>/(?:\.(?:py|js|mjs|cjs|json|toml|yaml|yml|md|txt|html|ps1|sh|env|conf|ini|sql)|\.env[^/]*|Dockerfile|\.gitignore)$/.test(p);
const output=[];
for(const dir of [root,resolve(root,'comments-service')]) {
  const git=args=>execFileSync('git',['-C',dir,...args],{maxBuffer:256*1024*1024});
  const tracked=git(['ls-files','-z']).toString().split('\0').filter(Boolean).filter(textFile);
  const matches=[];
  const check=(data,location)=>{
    const content=data.toString('utf8');
    for(const [type,value] of known)if(content.includes(value))matches.push({location,type:'known-'+type});
    for(const [type,re] of patterns)if(re.test(content))matches.push({location,type});
  };
  for(const path of tracked){try{check(readFileSync(resolve(dir,path)),path);}catch{}}
  const objects=git(['rev-list','--objects','--all']).toString().trim().split('\n').map(line=>[line.slice(0,40),line.slice(41)]).filter(([,p])=>textFile(p));
  const batch=execFileSync('git',['-C',dir,'cat-file','--batch'],{input:objects.map(([id])=>id).join('\n')+'\n',maxBuffer:256*1024*1024});
  let offset=0,blobs=0;
  for(const [id,path] of objects){
    const end=batch.indexOf(10,offset),header=batch.subarray(offset,end).toString().split(' '),size=Number(header[2]);
    offset=end+1;
    if(header[1]==='blob'){check(batch.subarray(offset,offset+size),`${id.slice(0,12)}:${path}`);blobs++;}
    offset+=size+1;
  }
  output.push({repository:dir,tracked_text_files:tracked.length,history_text_blobs:blobs,matches});
}
console.log(JSON.stringify(output,null,2));
