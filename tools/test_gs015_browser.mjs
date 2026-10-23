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

    // Inline agent controls stay compact and persist across refresh.
    await page.locator('.nav-button[data-view="agents"]').click();
    const localAgent=page.locator('.agent-config-card[data-agent-item="qwen2.5-coder:3b"]');
    await localAgent.locator('summary').click();
    await localAgent.locator('[data-agent-field="level"]').selectOption('detailed');
    await localAgent.locator('.save-agent-config').click();
    await page.waitForFunction(()=>document.querySelector('.agent-config-card[data-agent-item="qwen2.5-coder:3b"] .agent-summary-value')?.textContent.includes('detailed'));
    assert.equal(agentConfigs['qwen2.5-coder:3b'].level,'detailed');
    await page.reload({waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('#registeredModels .agent-config-card'));
    await page.locator('.nav-button[data-view="agents"]').click();
    const afterReload=page.locator('.agent-config-card[data-agent-item="qwen2.5-coder:3b"]');
    await afterReload.locator('summary').click();
    assert.equal(await afterReload.locator('[data-agent-field="level"]').inputValue(),'detailed');
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


    // Primary workspace items must appear before compact private AI chats.
    assert.equal(await page.locator('#privateChannelMenu').evaluate(x=>x.open),false);
    assert.equal(await page.locator('#groupList').evaluate(x=>x.compareDocumentPosition(document.querySelector('#privateChannelMenu')) & Node.DOCUMENT_POSITION_FOLLOWING ? true:false),true);
    assert.equal(await page.locator('#projectList').evaluate(x=>x.compareDocumentPosition(document.querySelector('#privateChannelMenu')) & Node.DOCUMENT_POSITION_FOLLOWING ? true:false),true);
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
    await page.locator('#browseRoots').click();
    await page.locator('#folderEntries button.folder-entry').first().click();
    await page.locator('#folderEntries button.folder-entry').first().click();
    await page.locator('#folderEntries button.folder-use').click();
    await page.locator('#projectName').fill(label+' Demo');
    await page.locator('#saveProject').click();
    await page.locator('#projectDialog').waitFor({state:'hidden'});
    await page.waitForFunction(name=>
      [...document.querySelectorAll('#projectSelect option')].some(el=>el.textContent===name),
      label+' Demo');
    assert.equal(exceptions.length,0,label+' project error: '+exceptions.join(', '));

    // Open again and confirm invalid submissions produce a visible inline error.
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    await page.locator('#addProjectButton').click();
    await page.locator('#projectPath').fill('D:\\000_AI Project\\Forbidden');
    await page.locator('#saveProject').click();
    await page.locator('#projectDialogError').waitFor({state:'visible'});
    assert.match(await page.locator('#projectDialogError').innerText(),/allowed project root/);
    await page.locator('#cancelProject').click();
    if(viewport.mobile)await page.locator('#mobileRailToggle').click();
    await page.locator('#newGroupButton').click();
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
    console.log('PASS: '+label+' buttons, project add, Codex added in Agents, Codex approvals, group chat and layout');
    await context.close();
  }
} finally{
  if(browser)await browser.close();
  await new Promise(ok=>server.close(ok));
}
