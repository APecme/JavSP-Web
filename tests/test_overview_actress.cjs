const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../javsp_web/web/assets/app.js'),'utf8');

test('actress range is sent to the server so counts and pagination cover the full catalog',()=>{
 const context=vm.createContext({state:{overviewGroupBy:'actress',actressScope:'all',overviewPageSize:24,overviewPage:1,overviewGroupPage:2,overviewGroupQuery:'Alice'},
  OVERVIEW_GROUP_PAGE_SIZE:12,URLSearchParams,document:{querySelector:()=>({dataset:{panel:'overview'}})}});
 vm.runInContext(source.slice(source.indexOf('function taskPageRequest'),source.indexOf('async function loadTasks')),context);
 const url=context.taskPageRequest();
 assert.match(url,/actress_scope=all/);assert.match(url,/offset=12/);assert.match(url,/query=Alice/);
});

test('full catalog pages render only server results and zero-film actresses can be opened',()=>{
 const nodes=new Map(), node=s=>{if(!nodes.has(s))nodes.set(s,{innerHTML:'',scrollIntoView(){}});return nodes.get(s);};
 let loads=0;
 const context=vm.createContext({window:{},state:{overviewGroups:{by:'actress',groups:[{key:'Alice',name:'Alice',count:0,avatar_id:'0123456789abcdef',covers:[]}],all:{count:0,covers:[]},total:200,limit:12},actressScope:'all',overviewGroupPage:1,selectedOverviewTasks:new Set()},
  $:node,escapeHtml:s=>String(s??''),javspIcon:()=>'',overviewGroupType:()=>['actress','女优','ACTRESS'],patchChildren:(el,html)=>{el.innerHTML=html;},libraryCard:g=>`<button>${g.name}</button>`,loadTasks:()=>{loads++;},renderOverview:()=>{}});
 vm.runInContext(source.slice(source.indexOf('function renderOverviewGroups'),source.indexOf('function libraryCard')),context);
 vm.runInContext(source.slice(source.indexOf('function openOverviewGroup'),source.indexOf('function closeOverviewGroup')),context);
 context.renderOverviewGroups();
 assert.match(node('#overview-tasks').innerHTML,/Alice/);
 assert.match(node('#overview-tasks').innerHTML,/200 个分类/);
 assert.equal((node('#overview-tasks').innerHTML.match(/<button>Alice/g)||[]).length,1);
 context.openOverviewGroup('Alice');
 assert.equal(context.state.overviewGroup.key,'Alice');assert.equal(loads,1);
});
