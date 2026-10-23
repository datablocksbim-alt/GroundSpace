// Real browser click-through smoke test for Ground Space UI flows.
// npm install --no-save playwright && npx playwright install chromium
// node tools/test_gs015_browser.mjs
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const playwrightModule=process.env.GROUND_SPACE_PLAYWRIGHT_MODULE;
const {chromium}=await import(playwrightModule?pathToFileURL(playwrightModule).href:'playwright');

const ROOT = resolve(import.meta.dirname, '..');
const registered = [{model:'qwen2.5-coder:3b',available:true,label:'Qwen',role:'proposal-only'}];
const discovered = ['granite4:3b','codex'];
const projects = [];
const groups = [];
const tasks = [];
const collaborations = [];
const chatgptStatus={connected:false,login_state:"not_started",auth_mode:null,plan_type:null};
const modelProfiles={};
const agentConfigs={};
const conversations = {};
const codex = {default_mode:'manual',project_modes:{},jobs:[]};
const state = {csrf:'functional-test-token'};
tasks.push({task_id:'GS-PENDING-DIRECT',status:'queued',requested_worker:'qwen-proposal',
  payload:{conversation_id:'direct-pending',model:'qwen2.5-coder:3b',project_id:null},
  required_permissions:['read','propose'],approval:{status:'pending'}});
conversations['direct-pending']=[{role:'user',agent:'qwen',content:'Pending owner review',
  timestamp:new Date().toISOString(),task_id:'GS-PENDING-DIRECT',project_id:null}];
// Migration-free navigation fixture: stored group IDs, messages and approvals must survive.
projects.push({id:'project-existing',name:'Existing Ground Space',
  path:'D:\\000_AI Project\\Existing Ground Space'});
groups.push({id:'group-existing',name:'Existing team chat',project_id:'project-existing',
  models:['qwen2.5-coder:3b'],approval_modes:{'qwen2.5-coder:3b':'manual'},
  conversation_id:'room-existing'});
groups.push({id:'group-unassigned',name:'Older general chat',project_id:null,
  models:['qwen2.5-coder:3b'],approval_modes:{'qwen2.5-coder:3b':'approve_for_me'},
  conversation_id:'room-unassigned'});
conversations['room-existing']=[{role:'assistant',agent:'group',content:'Preserved project reply',
  timestamp:new Date().toISOString()}];
conversations['room-unassigned']=[{role:'assistant',agent:'group',content:'Preserved legacy reply',
  timestamp:new Date().toISOString()}];
const json = (res,status,value) => {
  res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});
  res.end(JSON.stringify(value));
};
const reqBody = async req => {
  let body='';
  for await (const chunk of req)body+=chunk;
  return JSON.parse(body||'{}');
};
const bootstrap = () => ({
  csrf_token:state.csrf,
  agents:[{agent_id:'administrator',active:true,role:'Read only',permissions:['read']}],
  tasks:tasks.map(t=>({...t,approval:{...t.approval}})),
  conversations,
  models:{
    registered:registered.map(x=>({...x})),
    discovered:[...discovered],
    presets:[{id:'fast',label:'Fast'}, {id:'balanced',label:'Balanced'}],
  },
  workspaces:{
    projects:projects.map(p=>({...p})),
    groups:groups.map(g=>({...g})),
    allowed_project_roots:['D:\\000_AI Project'],
  },
  codex:{scope:'single_owner_pilot',per_user_accounts:false,cli_installed:true,
    registered:registered.some(x=>x.model==='codex'),write_enabled:true,max_permission:'workspace_write_if_owner_approved',
    default_mode:codex.default_mode,project_modes:{...codex.project_modes},jobs:[...codex.jobs].reverse()},
  collaborations:collaborations.map(x=>({...x})),
  model_profiles:{provider:'codex_cli',supported_efforts:['low','medium','high'],
    other_cloud_providers_connected:false,profiles:{...modelProfiles}},
  agent_configs:{schema_version:1,profiles:Object.fromEntries(registered.map(x=>[x.model,
    agentConfigs[x.model]||(x.model==='codex'?
      {model_id:'',level:'',access:['read','review','workspace_write'],approval:'manual'}:
      {model_id:x.model,level:'balanced',access:['chat','read','propose','review'],approval:'auto_read_only'})])),
    providers:[{id:'ollama',connected:true},{id:'openai_codex_cli',connected:true},
      {id:'anthropic',connected:false},{id:'grok',connected:false}]},
  chatgpt_connection:{scope:'single_owner_codex_cli',enabled:true,login_state:chatgptStatus.login_state},
  security:{deployment:'owner_private',public_ready:false,multi_user_accounts:false},
  paid_api_usage_aud:0,
});
const server=createServer(async(req,res)=>{
  try{
    const url=new URL(req.url, 'http://localhost');
    const path=url.pathname;
    if(req.method==='GET'&&['/','/app.css','/app.js'].includes(path)){
      const file = path==='/'?'index.html':path.slice(1);
      const data=await readFile(resolve(ROOT,'web/public',file));
      res.writeHead(200,{'Content-Type':file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});
      res.end(data);
      return;
    }
    if(req.method==='GET'&&path==='/api/bootstrap')return json(res,200,bootstrap());
    if(req.method==='GET'&&path==='/api/auth/chatgpt/status')
      return json(res,200,{scope:'single_owner_codex_cli',enabled:true,...chatgptStatus});
    if(req.method==='GET'&&path==='/api/projects/browse'){
      const chosen=url.searchParams.get('path');
      if(!chosen)return json(res,200,{
        current:null,is_root_list:true,folders:[{name:'ASUS project root',path:'D:\\000_AI Project'}]
      });
      return json(res,200,{
        current:chosen,is_root_list:false,parent:null,
        folders:[{name:'Demo',path:'D:\\000_AI Project\\Demo'}]
      });
    }
    if(req.method==='POST'){
      assert.equal(req.headers['x-ground-space-csrf'],state.csrf,'CSRF token missing');
      const body=await reqBody(req);
      if(path==='/api/agents/configure'){
        const ids=registered.map(x=>x.model);
        if(!ids.includes(body.agent_id))return json(res,400,{error:'Agent not registered'});
        if(!Array.isArray(body.access)||!body.access.length)return json(res,400,{error:'Access is required'});
        const connected=body.agent_id==='codex';
        if(!connected&&!ids.includes(body.model_id))return json(res,400,{error:'Model not registered'});
        if(!connected&&body.access.includes('workspace_write'))return json(res,400,{error:'No local filesystem permissions'});
        agentConfigs[body.agent_id]={model_id:body.model_id,level:body.level,
          access:body.access,approval:body.approval};
        return json(res,200,agentConfigs[body.agent_id]);
      }
      if(path==='/api/model-profiles/set'){
        if(body.provider!=='codex')return json(res,400,{error:'Provider not connected'});
        if(!['','low','medium','high'].includes(body.reasoning_effort))return json(res,400,{error:'Invalid effort'});
        if(!/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(body.model_id||'')&&body.model_id!=='')
          return json(res,400,{error:'Invalid model identifier'});
        const key=body.group_id?'codex:group:'+body.group_id:'codex:direct';
        modelProfiles[key]={model_id:body.model_id,reasoning_effort:body.reasoning_effort};
        return json(res,200,modelProfiles[key]);
      }
      if(path==='/api/auth/chatgpt/device/start'){
        chatgptStatus.login_state='pending';
        return json(res,200,{verification_url:'https://auth.openai.com/codex/device',
          user_code:'ABCD-1234',login_id:'mock-login'});
      }
      if(path==='/api/collaboration/start'){
        const group=groups.find(g=>g.id===body.group_id);
        if(!group||!group.project_id)return json(res,400,{error:'Project required'});
        const task={task_id:'GS-FLOW-'+(tasks.length+1),status:'completed',
          payload:{model:'qwen2.5-coder:3b',group_id:group.id},result:{answer:'Propose a small test module'},
          approval:{status:'approved'}};
        tasks.push(task);
        const flow={id:'FLOW-'+(collaborations.length+1),group_id:group.id,project_id:group.project_id,
          goal:body.goal,state:'proposal_pending',proposal_task_id:task.task_id};
        collaborations.push(flow);
        conversations[group.conversation_id]||=[];
        conversations[group.conversation_id].push({role:'user',agent:'group',content:'@Qwen proposal: '+body.goal,
          task_ids:[task.task_id],timestamp:new Date().toISOString()});
        return json(res,201,flow);
      }
      if(path==='/api/collaboration/advance'){
        const flow=collaborations.find(f=>f.id===body.flow_id);
        if(!flow)return json(res,400,{error:'Unknown collaboration'});
        if(flow.state==='proposal_pending'){
          const group=groups.find(g=>g.id===flow.group_id);
          const item={id:'CODEX-'+(codex.jobs.length+1),project_id:flow.project_id,
            project_name:'Demo',prompt:flow.goal,status:'pending_approval',
            scope:'workspace_write',mode_at_submission:'manual',answer:'',error:'',
            ...(modelProfiles['codex:group:'+group.id]||{})};
          codex.jobs.push(item);
          flow.codex_job_id=item.id;flow.state='codex_pending';
          conversations[group.conversation_id].push({role:'note',agent:'group',content:'Co-work: Codex implementation',
            codex_job_ids:[item.id],timestamp:new Date().toISOString()});
        }
        return json(res,200,flow);
      }
      if(path==='/api/codex/policy'){
        if(!['manual','auto_read_only','disabled'].includes(body.mode))return json(res,400,{error:'Invalid approval mode'});
        if(body.project_id)codex.project_modes[body.project_id]=body.mode;
        else codex.default_mode=body.mode;
        return json(res,200,bootstrap().codex);
      }
      if(path==='/api/codex/submit'){
        const mode=codex.project_modes[body.project_id]||codex.default_mode;
        if(mode==='disabled')return json(res,400,{error:'Codex disabled'});
        const job={id:'CODEX-'+(codex.jobs.length+1),project_id:body.project_id,project_name:'Demo',
          prompt:body.prompt,mode_at_submission:mode,status:mode==='manual'?'pending_approval':'running',
          scope:'read_only',answer:'',error:''};
        codex.jobs.push(job);return json(res,201,job);
      }
      if(path==='/api/codex/approve'||path==='/api/codex/reject'){
        const job=codex.jobs.find(x=>x.id===body.job_id);
        if(!job||job.status!=='pending_approval')return json(res,400,{error:'Not pending'});
        job.status=path.endsWith('/approve')?'running':'rejected';return json(res,200,job);
      }
      if(path==='/api/projects/add'){
        if(!String(body.path).startsWith('D:\\000_AI Project\\')||String(body.path).includes('Forbidden'))
          return json(res,400,{error:'Project folder must be inside an allowed project root'});
        const item={id:'project-'+(projects.length+1),name:body.name||'Demo',path:body.path};
        projects.push(item);return json(res,201,item);
      }
      if(path==='/api/projects/remove'){
        const index=projects.findIndex(x=>x.id===body.project_id);
        if(index<0||body.confirm_name!==projects[index].name)
          return json(res,400,{error:'Project confirmation mismatch'});
        const item=projects[index];
        const linked=groups.filter(x=>x.project_id===item.id);
        const result={removed:item.id,name:item.name,unassigned_chats:linked.length,folder_deleted:false};
        projects.splice(index,1);
        for(const group of linked)group.project_id=null;
        return json(res,200,result);
      }

      if(path==='/api/models/add'){
        const i=discovered.indexOf(body.model);
        if(i<0)return json(res,400,{error:'Model must already be installed in local Ollama'});
        discovered.splice(i,1);
        registered.push({model:body.model,available:true,label:body.model,
          provider:body.model==='codex'?'openai_codex_cli':'ollama',
          role:body.model==='codex'?'workspace coding agent':'proposal-only'});
        return json(res,201,bootstrap().models);
      }
      if(path==='/api/groups/create'){
        if(!body.name||!body.models?.length)return json(res,400,{error:'Choose between 1 and 6 local AI models'});
        const group={id:'group-'+(groups.length+1),name:body.name,models:body.models,
          approval_modes:body.approval_modes||{},project_id:body.project_id,
          conversation_id:'room-'+(groups.length+1)};
        groups.push(group);return json(res,201,group);
      }
      if(path==='/api/groups/update'){
        const group=groups.find(g=>g.id===body.group_id);
        if(!group)return json(res,404,{error:'Group missing'});
        group.models=body.models;group.approval_modes=body.approval_modes||{};
        group.project_id=body.project_id;
        return json(res,200,group);
      }
      if(path==='/api/groups/send'){
        const group=groups.find(g=>g.id===body.group_id);
        if(body.prompt.startsWith('@Codex') && group.models.includes('codex')){
          const item={id:'CODEX-'+(codex.jobs.length+1),project_id:group.project_id,
            group_id:group.id,conversation_id:group.conversation_id,project_name:'Demo',
            prompt:body.prompt,mode_at_submission:'manual',status:'pending_approval',
            scope:'workspace_write',answer:'',error:'',
            ...(modelProfiles['codex:group:'+group.id]||{})};
          codex.jobs.push(item);
          const entry={role:'user',agent:'group',content:body.prompt,
            timestamp:new Date().toISOString(),codex_job_ids:[item.id],task_ids:[]};
          conversations[group.conversation_id]||=[];
          conversations[group.conversation_id].push(entry);
          return json(res,201,{group,task_ids:[],codex_job_ids:[item.id],conversation_id:group.conversation_id});
        }
        const model=group.models[0];
        const mode=group.approval_modes[model]||'approve_for_me';
        if(mode==='disabled')return json(res,400,{error:'Bot disabled'});
        const task={task_id:'GS-MOCK-'+(tasks.length+1),status:'queued',
          payload:{group_id:group.id,model,speaker:'Coordinator'},required_permissions:['read','propose'],
          approval:{status:mode==='manual'?'pending':'approved'}};
        tasks.push(task);
        const entry={role:'user',agent:'group',content:body.prompt,
          timestamp:new Date().toISOString(),task_ids:[task.task_id]};
        conversations[group.conversation_id]||=[];
        conversations[group.conversation_id].push(entry);
        return json(res,201,{group,task_ids:[task.task_id],conversation_id:group.conversation_id});
      }
      if(path==='/api/groups/approve'||path==='/api/groups/reject'){
        const task=tasks.find(t=>t.task_id===body.task_id&&t.payload.group_id===body.group_id);
        if(!task||task.approval.status!=='pending')return json(res,400,{error:'Pending task not found'});
        task.approval.status=path.endsWith('/approve')?'approved':'rejected';
        return json(res,200,task);
      }
      if(path==='/api/tasks/approve'||path==='/api/tasks/reject'){
        const task=tasks.find(t=>t.task_id===body.task_id&&!t.payload.group_id);
        if(!task||task.approval.status!=='pending')return json(res,400,{error:'Pending direct task not found'});
        task.approval.status=path.endsWith('/approve')?'approved':'rejected';
        return json(res,200,task);
      }
      if(path==='/api/chat'){
        const id=body.conversation_id||'chat';
        if(body.agent==='codex'){
          const item={id:'CODEX-'+(codex.jobs.length+1),project_id:body.project_id,
            conversation_id:id,project_name:'Demo',prompt:body.prompt,scope:'workspace_write',
            mode_at_submission:'manual',status:'pending_approval',answer:'',error:''};
          codex.jobs.push(item);
          conversations[id]||=[];
          const entry={role:'user',agent:'codex',content:body.prompt,
            timestamp:new Date().toISOString(),codex_job_ids:[item.id]};
          conversations[id].push(entry);
          return json(res,201,{entry,codex_job:item,conversation_id:id});
        }
        conversations[id]||=[];
        const entry={role:'note',agent:body.agent,kind:'goal',content:'Check mobile',timestamp:new Date().toISOString()};
        conversations[id].push(entry);return json(res,201,{entry,conversation_id:id});
      }
      return json(res,404,{error:'Unknown mock API endpoint: '+path});
    }
    json(res,404,{error:'Not found'});
  }catch(err){json(res,500,{error:String(err)});}
});

let browser;
try{
  await new Promise(ok=>server.listen(0,'127.0.0.1',ok));
  const url='http://127.0.0.1:'+server.address().port;
  const executablePath=process.env.GROUND_SPACE_CHROMIUM_EXECUTABLE||undefined;
  browser=await chromium.launch({headless:true,...(executablePath?{executablePath}:{})});
  for(const viewport of [{width:390,height:844,mobile:true},{width:1280,height:800,mobile:false}]){
    const label=viewport.mobile?'mobile':'desktop';
    registered.splice(0,registered.length,{model:'qwen2.5-coder:3b',available:true,label:'Qwen',role:'proposal-only',provider:'ollama'});
    discovered.splice(0,discovered.length,'granite4:3b','codex');
    tasks.find(task=>task.task_id==='GS-PENDING-DIRECT').approval.status='pending';
    const context=await browser.newContext({viewport:{width:viewport.width,height:viewport.height},isMobile:viewport.mobile,hasTouch:viewport.mobile});
    const page=await context.newPage();
    const exceptions=[];
    page.on('pageerror',error=>exceptions.push(error.message));
    const requests=[];
    page.on('response',response=>{if(response.status()>=400)requests.push(response.status()+' '+response.url());});
    await page.goto(url,{waitUntil:'domcontentloaded'});
    try{
      await page.waitForFunction(()=>document.querySelector('#systemState')?.textContent==='Local systems ready',null,{timeout:6000});
    }catch(error){
      console.error('STARTUP DIAG',label,{exceptions,requests,system:await page.locator('#systemState').textContent(),page:await page.title()});
      throw error;
    }
    assert.equal(exceptions.length,0,label+' startup errors: '+exceptions.join(', '));

    // Compact per-field buttons, Save and reload, and unified built-in cards.
    await page.locator('.nav-button[data-view="agents"]').click();
    const localAgent=page.locator('.agent-config-card[data-agent-item="qwen2.5-coder:3b"]');
    assert.equal(await localAgent.locator('[data-agent-menu]').count(),4);
    assert.equal(await localAgent.locator('details').count(),0,'no whole-card dropdown');
    const tinySave=localAgent.locator('.save-agent-config');
    assert.equal(await tinySave.isDisabled(),true);
    assert.equal(await tinySave.getAttribute('aria-label'),
      'Save configuration for qwen2.5-coder:3b');
    assert.equal((await tinySave.textContent()).trim(),'✓');
    const originalLevel=await localAgent.locator('[data-agent-field="level"]').inputValue();
    const nextLevel=originalLevel==='detailed'?'fast':'detailed';
    await localAgent.locator('[data-agent-menu="level"]').click();
    assert.equal(await localAgent.locator('[data-agent-pane="level"]').isVisible(),true);
    assert.equal(await localAgent.locator('[data-agent-pane="model_id"]').isVisible(),false);
    await localAgent.locator('[data-agent-field="level"]').selectOption(nextLevel);
    assert.equal(await localAgent.locator('[data-agent-pane="level"]').isVisible(),false,
      'Single-choice Level menu should close automatically');
    assert.equal(await localAgent.locator('.save-agent-config').isEnabled(),true);
    if(viewport.mobile){
      const controls=await localAgent.locator('.agent-small-actions button').evaluateAll(buttons=>
        buttons.map(el=>{const b=el.getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,height:b.height};}));
      const cardRight=await localAgent.evaluate(el=>el.getBoundingClientRect().right);
      assert.ok(controls.every(c=>c.right<=cardRight+1),'Buttons must not overflow mobile card');
      assert.ok(controls.every(c=>c.height>=32&&c.height<=42),'Compact buttons keep usable touch targets');
    }
    // Returning to the current saved value cancels the pending Save.
    await localAgent.locator('[data-agent-menu="level"]').click();
    await localAgent.locator('[data-agent-field="level"]').selectOption(originalLevel);
    assert.equal(await tinySave.isDisabled(),true,'no changes means no Save');
    await localAgent.locator('[data-agent-menu="level"]').click();
    await localAgent.locator('[data-agent-field="level"]').selectOption(nextLevel);
    assert.equal(await tinySave.isEnabled(),true);
    await localAgent.locator('[data-agent-menu="access"]').click();
    assert.equal(await localAgent.locator('[data-agent-pane="level"]').isVisible(),false);
    assert.equal(await localAgent.locator('[data-agent-pane="access"]').isVisible(),true);
    assert.equal(await localAgent.locator('input[data-agent-access]').count(),4);
    await tinySave.click();
    await page.waitForFunction(level=>document.querySelector('.agent-config-card[data-agent-item="qwen2.5-coder:3b"] .agent-summary-value')?.textContent.includes(level), nextLevel);
    const refreshedSave=page.locator('.agent-config-card[data-agent-item="qwen2.5-coder:3b"] .save-agent-config');
    assert.equal(await refreshedSave.isDisabled(),true,'successful Save returns to disabled state');
    await page.locator('.agent-config-card[data-agent-item="qwen2.5-coder:3b"] .agent-config-feedback').getByText('Saved').waitFor({state:'visible'});
    assert.equal(agentConfigs['qwen2.5-coder:3b'].level,nextLevel);
    // Built-in agents use matching compact rows, not the former technical grid.
    assert.equal(await page.locator('#agentGrid.agent-grid').count(),0);
    const builtIn=page.locator('#agentGrid .builtin-agent-card[data-builtin-agent="administrator"]');
    assert.equal(await builtIn.count(),1);
    await builtIn.locator('[data-builtin-menu="access"]').click();
    assert.equal(await builtIn.locator('[data-builtin-pane="access"]').isVisible(),true);
    assert.match(await builtIn.locator('[data-builtin-pane="access"]').innerText(),/Managed by Ground Space/);
    await page.reload({waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('#registeredModels .agent-config-card'));
    await page.locator('.nav-button[data-view="agents"]').click();
    const afterReload=page.locator('.agent-config-card[data-agent-item="qwen2.5-coder:3b"]');
    await afterReload.locator('[data-agent-menu="level"]').click();
    assert.equal(await afterReload.locator('[data-agent-field="level"]').inputValue(),nextLevel);
    await page.locator('.nav-button[data-view="chat"]').click();


    // Regression: GS-026 originally reapplied a desktop two-column grid after
    // the mobile breakpoint. This silently reduced iPhone chat to ~55% width.
    const geometry = await page.evaluate(() => {
      const width = window.innerWidth;
      const rect = selector => {
        const r = document.querySelector(selector).getBoundingClientRect();
        return {width:r.width,left:r.left,right:r.right};
      };
      return {width,
        chat:rect('.chat-layout'),conversation:rect('.conversation'),
        head:rect('.conversation-head'),messages:rect('#messages'),
        composer:rect('#chatForm'),
        columns:getComputedStyle(document.querySelector('.chat-layout')).gridTemplateColumns};
    });
    if(viewport.mobile){
      for(const [element,rect] of Object.entries({
        chat:geometry.chat,conversation:geometry.conversation,
        head:geometry.head,messages:geometry.messages,composer:geometry.composer
      })){
        assert.ok(rect.width >= geometry.width*0.92,
          label+' '+element+' must use full viewport width: '+JSON.stringify(geometry));
        assert.ok(rect.right <= geometry.width+2,
          label+' '+element+' must not overflow viewport: '+JSON.stringify(geometry));
      }
    }


    // GS-028: only Projects and Private AI chats, no separate Group Chats rail.
    assert.equal(await page.locator('.group-rail').count(),0,'remove standalone Group Chats');
    assert.equal(await page.locator('#groupList').count(),0,'no duplicate group listing');
    assert.equal(await page.locator('#privateChannelMenu').evaluate(x=>x.open),false);
    assert.equal(await page.locator('#projectList').evaluate(x=>
      Boolean(x.compareDocumentPosition(document.querySelector('#privateChannelMenu')) &
        Node.DOCUMENT_POSITION_FOLLOWING)),true);
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    const preservedProject=page.locator('[data-project-cluster="project-existing"]');
    assert.equal(await preservedProject.count(),1,'existing project appears');
    await preservedProject.locator('[data-project-toggle]').click();
    if(await preservedProject.locator('.project-chat-list').isHidden()){
      await preservedProject.locator('[data-project-toggle]').click();
    }
    assert.equal(await preservedProject.locator('[data-group="group-existing"]').isVisible(),true);
    await preservedProject.locator('[data-group="group-existing"]').click();
    await page.waitForFunction(()=>
      document.querySelector('#messages')?.textContent.includes('Preserved project reply'));
    assert.equal(groups[0].conversation_id,'room-existing');
    assert.equal(groups[0].approval_modes['qwen2.5-coder:3b'],'manual');
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    const olderChats=page.locator('[data-project-cluster="__unassigned__"]');
    assert.equal(await olderChats.count(),1,'legacy chats remain under Projects');
    if(await olderChats.locator('.project-chat-list').isHidden()){
      await olderChats.locator('[data-project-toggle]').click();
    }
    await olderChats.locator('[data-group="group-unassigned"]').click();
    await page.waitForFunction(()=>
      document.querySelector('#messages')?.textContent.includes('Preserved legacy reply'));
    assert.equal(groups[1].conversation_id,'room-unassigned');
    // Navigation is the previously broken startup handler.
    await page.locator('.nav-button[data-view="agents"]').click();
    assert.equal(await page.locator('#view-agents').evaluate(el=>el.classList.contains('active')),true,label+' Agents click');

    // Owner's explicit device login is an active control, not a cosmetic provider card.
    await page.locator('#chatgptConnectButton').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#chatgptConnectButton')?.disabled===false);
    await page.locator('#chatgptConnectButton').click();
    await page.locator('#chatgptDevicePanel').waitFor({state:'visible'});
    assert.equal(await page.locator('#chatgptDeviceCode').innerText(),'ABCD-1234');
    assert.match(await page.locator('#chatgptVerifyLink').getAttribute('href'),/^https:\/\/auth\.openai\.com\//);

    // Reaching a disabled control must explain the exact reason rather than appearing broken.
    assert.equal(await page.locator('#addModelButton').isEnabled(),true,label+' installed model available');
    await page.locator('#addModelButton').click();
    await page.waitForFunction(()=>document.querySelector('#registeredModels')?.textContent.includes('granite4:3b'));
    assert.equal(await page.locator('#addModelButton').isEnabled(),true,label+' Codex should appear for registration');
    await page.locator('#availableModel').selectOption('codex');
    await page.locator('#addModelButton').click();
    await page.waitForFunction(()=>document.querySelector('#registeredModels')?.textContent.includes('codex'));
    assert.equal(await page.locator('#addModelButton').isEnabled(),false,label+' all agents registered');
    assert.match(await page.locator('#modelImportStatus').innerText(),/already registered|No additional installed/);

    await page.locator('.nav-button[data-view="chat"]').click();
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    await page.locator('#addProjectButton').click();
    const picker=page.locator('#projectDialog');
    await picker.locator('#folderEntries .folder-entry').first().waitFor({state:'visible'});
    assert.equal(await picker.locator('#projectPath').getAttribute('type'),'hidden');
    assert.equal(await picker.locator('#saveProject').isDisabled(),true,
      'folder must be chosen before creating project');
    assert.equal(await picker.locator('#folderPicker').isVisible(),true);
    await picker.locator('#folderEntries .folder-entry').first().click();
    assert.equal(await picker.locator('#folderEntries .folder-use').count(),0,
      'allowed root itself must not be selectable');
    await picker.locator('#folderEntries .folder-entry').first().click();
    await picker.locator('#folderEntries .folder-use').click();
    assert.equal(await picker.locator('#saveProject').isEnabled(),true);
    assert.equal(await picker.locator('#selectedProjectFolder').isVisible(),true);
    assert.equal(await picker.locator('#folderPicker').isVisible(),false);
    assert.match(await picker.locator('#selectedFolderPath').innerText(),/Demo/);
    await picker.locator('#changeProjectFolder').click();
    assert.equal(await picker.locator('#saveProject').isDisabled(),true,
      'changing selected folder must clear old selection');
    await picker.locator('#folderEntries .folder-entry').first().click();
    await picker.locator('#folderEntries .folder-entry').first().click();
    await picker.locator('#folderEntries .folder-use').click();
    await picker.locator('#projectName').fill(label+' Demo');
    await picker.locator('#saveProject').click();
    await page.locator('#projectDialog').waitFor({state:'hidden'});
    await page.waitForFunction(name=>
      [...document.querySelectorAll('#projectSelect option')].some(el=>el.textContent===name),
      label+' Demo');
    assert.equal(exceptions.length,0,label+' project error: '+exceptions.join(', '));

    // New project dialog never asks for a typed path; backend still rejects unsafe API paths.
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    await page.locator('#addProjectButton').click();
    await page.locator('#folderEntries .folder-entry').first().waitFor({state:'visible'});
    assert.equal(await page.locator('#saveProject').isDisabled(),true);
    assert.equal(await page.locator('input#projectPath').isVisible(),false);
    const outside=await page.evaluate(async()=>{
      const response=await fetch('/api/projects/add',{
        method:'POST',headers:{'Content-Type':'application/json',
          'X-Ground-Space-CSRF':'functional-test-token'},
        body:JSON.stringify({path:'D:\\\\Forbidden',name:'Unsafe'})});
      return {status:response.status,data:await response.json()};
    });
    assert.equal(outside.status,400);
    assert.match(outside.data.error,/allowed project root/);
    await page.locator('#cancelProject').click();
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    const createdProject=projects[projects.length-1].id;
    const cluster=page.locator('[data-project-cluster="'+createdProject+'"]');
    if(await cluster.locator('.project-chat-list').isHidden()){
      await cluster.locator('[data-project-toggle]').click();
    }
    await cluster.locator('[data-new-project-group]').click();
    assert.equal(await page.locator('#groupProject').inputValue(),createdProject,
      'new project chat defaults to owning project');
    await page.locator('#groupName').fill(label+' Review');
    await page.locator('#groupMemberOptions input[name="group-member"]').first().check();
    await page.locator('#groupMemberOptions .group-member-policy').first().selectOption('manual');
    await page.locator('#saveGroup').click();
    await page.locator('#groupDialog').waitFor({state:'hidden'});
    await page.waitForFunction(name=>
      document.querySelector('#conversationTitle')?.textContent===name,
      label+' Review');
    assert.equal(exceptions.length,0,label+' group error: '+exceptions.join(', '));
    assert.equal(groups[groups.length-1].approval_modes['qwen2.5-coder:3b'],'manual');
    assert.equal(groups[groups.length-1].project_id,createdProject);
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    const createdCluster=page.locator('[data-project-cluster="'+createdProject+'"]');
    assert.equal(await createdCluster.locator('[data-group="'+groups[groups.length-1].id+'"]').isVisible(),true,
      'new chat nested under the original project');
    if(viewport.mobile)await page.locator('#closeMobileRail').click();
    // A manual-approval bot must not respond until its queued reply is approved.
    await page.locator('#prompt').fill('How is our project doing?');
    await page.locator('#sendButton').click();
    await page.locator('#messages button[data-group-decision="approve"]').first().waitFor({state:'visible'});
    assert.equal(tasks[tasks.length-1].approval.status,'pending');
    await page.locator('#messages button[data-group-decision="approve"]').first().click();
    await page.waitForFunction(()=>document.querySelector('#messages')?.textContent.includes('Queued — waiting for worker'));
    assert.equal(tasks[tasks.length-1].approval.status,'approved');
    // Per-bot approval choices are editable in the current group's Members dialog.
    await page.locator('#editGroupButton').click();
    await page.locator('#groupMemberOptions .group-member-policy').first().selectOption('approve_for_me');
    await page.locator('#saveGroup').click();
    await page.locator('#groupDialog').waitFor({state:'hidden'});
    assert.equal(groups[groups.length-1].approval_modes['qwen2.5-coder:3b'],'approve_for_me');
    // Codex can be added to the same AI members selector, configured per group,
    // and asked to write files only after this specific job is approved.
    await page.locator('#editGroupButton').click();
    await page.locator('#groupMemberOptions input[value="codex"]').check();
    await page.locator('#groupMemberOptions .group-member-policy[data-model="codex"]').selectOption('manual');
    await page.locator('#saveGroup').click();
    await page.locator('#groupDialog').waitFor({state:'hidden'});
    assert.equal(groups[groups.length-1].approval_modes.codex,'manual');
    await page.locator('#openModelSettings').click();
    await page.locator('#modelSettingsDialog').waitFor({state:'visible'});
    assert.equal(await page.locator('#modelProviderChoice option[value="claude"]').isDisabled(),true);
    await page.locator('#codexModelChoice').selectOption('gpt-5.6-sol');
    await page.locator('#codexReasoningEffort').selectOption('medium');
    await page.locator('#saveModelSettings').click();
    await page.locator('#modelSettingsDialog').waitFor({state:'hidden'});
    assert.equal(modelProfiles['codex:group:'+groups[groups.length-1].id].model_id,'gpt-5.6-sol');
    assert.equal(modelProfiles['codex:group:'+groups[groups.length-1].id].reasoning_effort,'medium');
    await page.locator('#prompt').fill('@Codex create a basic test module');
    await page.locator('#sendButton').click();
    await page.locator('#messages button[data-codex-decision="approve"]').last().waitFor({state:'visible'});
    assert.equal(codex.jobs[codex.jobs.length-1].scope,'workspace_write');
    assert.equal(codex.jobs[codex.jobs.length-1].status,'pending_approval');
    assert.equal(codex.jobs[codex.jobs.length-1].model_id,'gpt-5.6-sol');
    await page.locator('#messages button[data-codex-decision="approve"]').last().click();
    await page.waitForFunction(()=>document.querySelector('#messages')?.textContent.includes('running'));
    assert.equal(codex.jobs[codex.jobs.length-1].status,'running');
    await page.locator('#editGroupButton').click();
    await page.locator('#groupMemberOptions input[value="granite4:3b"]').check();
    await page.locator('#saveGroup').click();
    await page.locator('#groupDialog').waitFor({state:'hidden'});
    await page.locator('#prompt').fill('Build a small Python inventory');
    await page.locator('#startCollaborationButton').click();
    await page.locator('#messages .collaboration-card').first().waitFor({state:'visible'});
    assert.equal(collaborations[collaborations.length-1].state,'proposal_pending');
    await page.locator('#messages button[data-flow-advance]').first().click();
    await page.waitForFunction(()=>document.querySelector('#messages')?.textContent.includes('codex_pending'));
    assert.equal(collaborations[collaborations.length-1].state,'codex_pending');
    assert.equal(codex.jobs[codex.jobs.length-1].reasoning_effort,'medium');
    await page.locator('#messages button[data-codex-decision="approve"]').last().waitFor({state:'visible'});
    if(viewport.mobile){
      assert.equal(await page.locator('#mobileRailBackdrop').isVisible(),false,'Drawer must close after group selection');
      const availableHeight=await page.locator('#messages').evaluate(el=>el.getBoundingClientRect().height);
      assert.ok(availableHeight>150,'Chat messages should retain usable viewport height; observed '+availableHeight);
      await page.locator('#mobileOptionsToggle').click();
      assert.equal(await page.locator('#chatOptions').isVisible(),true,'Model options toggle');
    }
    // Codex per-project owner approval options must work in desktop and mobile view.
    await page.locator('.nav-button[data-view="tasks"]').click();
    const maxScroll=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
    assert.ok(maxScroll<=2,label+' task table must not overflow horizontally: '+maxScroll);
    assert.equal(await page.locator('#taskRows .task-name').first().isVisible(),true);
    const directRow=page.locator('#taskRows tr[data-task="GS-PENDING-DIRECT"]');
    await directRow.locator('button[data-task-decision="approve"]:visible').click();
    await page.waitForFunction(()=>!document.querySelector('tr[data-task="GS-PENDING-DIRECT"] button[data-task-decision]'));
    assert.equal(tasks.find(task=>task.task_id==='GS-PENDING-DIRECT').approval.status,'approved');
    await page.locator('.nav-button[data-view="agents"]').click();
    await page.locator('#codexAdvanced > summary').click();
    assert.equal(await page.locator('#codexAgentSettings').isVisible(),true);
    assert.equal(await page.locator('#codexAgentChannel').isVisible(),false);
    const selectedProject=projects[projects.length-1].id;
    await page.locator('#codexPolicyProject').selectOption(selectedProject);
    await page.locator('#codexApprovalMode').selectOption('auto_read_only');
    await page.locator('#saveCodexPolicy').click();
    await page.waitForFunction(id=>document.querySelector('#codexPolicyProject')?.value===id,selectedProject);
    assert.equal(codex.project_modes[selectedProject],'auto_read_only');
    await page.locator('#codexApprovalMode').selectOption('manual');
    await page.locator('#saveCodexPolicy').click();
    assert.equal(codex.project_modes[selectedProject],'manual');
    await page.locator('#codexReviewProject').selectOption(selectedProject);
    await page.locator('#codexReviewPrompt').fill('Review current implementation');
    await page.locator('#submitCodexReview').click();
    await page.locator('#codexJobList .codex-actions button[data-decision="approve"]').first().waitFor({state:'visible'});
    assert.equal(codex.jobs[codex.jobs.length-1].status,'pending_approval');
    await page.locator('#codexJobList .codex-actions button[data-decision="approve"]').first().click();
    await page.waitForFunction(()=>document.querySelector('#codexJobList')?.textContent.includes('running'));
    assert.equal(codex.jobs[codex.jobs.length-1].status,'running');
    assert.equal(exceptions.length,0,label+' Codex settings and approvals: '+exceptions.join(', '));
    // Owner project removal must be subtle, explicitly confirmed and metadata-only.
    await page.locator('.nav-button[data-view="chat"]').click();
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    const existing=page.locator('[data-project-cluster="project-existing"]');
    const preservedChatId=groups.find(g=>g.id==='group-existing').conversation_id;
    const preservedApproval=groups.find(g=>g.id==='group-existing').approval_modes['qwen2.5-coder:3b'];
    await existing.locator('[data-project-menu]').click();
    assert.equal(await page.locator('#removeProjectDialog').isVisible(),true);
    assert.match(await page.locator('#removeProjectDialog').innerText(),/will not be deleted/);
    assert.match(await page.locator('#removeProjectChatNotice').innerText(),/1 existing project chat/);
    await page.locator('#cancelRemoveProject').click();
    assert.ok(projects.some(p=>p.id==='project-existing'),'Cancel must preserve the project');
    await existing.locator('[data-project-menu]').click();
    await page.locator('#confirmRemoveProject').click();
    await page.waitForFunction(()=>!document.querySelector('[data-project-cluster="project-existing"]'));
    assert.equal(projects.some(p=>p.id==='project-existing'),false,'project unregistered');
    const preserved=groups.find(g=>g.id==='group-existing');
    assert.equal(preserved.project_id,null,'group moved to unassigned');
    assert.equal(preserved.conversation_id,preservedChatId,'conversation ID stays');
    assert.equal(preserved.approval_modes['qwen2.5-coder:3b'],preservedApproval);
    assert.ok(conversations[preservedChatId].some(x=>x.content==='Preserved project reply'));
    const unassignedFolder=page.locator('[data-project-cluster="__unassigned__"]');
    if(await unassignedFolder.locator('.project-chat-list').isHidden()){
      await unassignedFolder.locator('[data-project-toggle]').click();
    }
    assert.equal(await unassignedFolder.locator('[data-group="group-existing"]').isVisible(),true);
    assert.equal(exceptions.length,0,label+' project removal: '+exceptions.join(', '));
    console.log('PASS: '+label+' buttons, project add/remove, preserved chats, Codex and mobile layout');
    await context.close();
  }
} finally{
  if(browser)await browser.close();
  await new Promise(ok=>server.close(ok));
}
