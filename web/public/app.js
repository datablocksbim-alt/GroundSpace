const state={agent:'qwen',csrf:'',conversationId:localStorage.getItem('gs_conversation_id')||crypto.randomUUID(),poll:null,data:null,refreshing:false,groupId:null,projectId:localStorage.getItem('gs_project_id')||'',directConversationId:null,selectedModel:localStorage.getItem('gs_model')||'qwen2.5-coder:3b',performance:localStorage.getItem('gs_performance')||'balanced'};
const $=s=>document.querySelector(s);const $$=s=>[...document.querySelectorAll(s)];
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}
function clearDialogError(id){const el=$(id);el.hidden=true;el.textContent='';}
function showDialogError(id,error){const el=$(id);el.textContent=error?.message||String(error);el.hidden=false;el.scrollIntoView({block:'nearest'});}
async function api(path,options={}){const headers={'Content-Type':'application/json',...(options.headers||{})};if(options.method==='POST')headers['X-Ground-Space-CSRF']=state.csrf;const response=await fetch(path,{...options,headers});const body=await response.json();if(!response.ok)throw new Error(body.error||`Request failed (${response.status})`);return body}
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
const mobileViewport=window.matchMedia('(max-width: 760px)');
function setMobileRail(open){
  const active=Boolean(open&&mobileViewport.matches);
  const rail=$('#agentRail');
  rail.classList.toggle('mobile-open',active);
  rail.inert=mobileViewport.matches&&!active;
  $('#mobileRailBackdrop').hidden=!active;
  $('#mobileRailToggle').setAttribute('aria-expanded',String(active));
  $('#mobileRailToggle').setAttribute('aria-label',active?'Close chats and projects':'Open chats and projects');
  if(active)$('#closeMobileRail').focus();
}
function setMobileOptions(open){
  const active=Boolean(open&&mobileViewport.matches);
  $('#chatForm').classList.toggle('options-open',active);
  $('#mobileOptionsToggle').setAttribute('aria-expanded',String(active));
  $('#mobileOptionsToggle').innerHTML=active?'Hide options <span aria-hidden="true">⌃</span>':'Options <span aria-hidden="true">⌄</span>';
}
function syncMobileViewportHeight(){
  const viewport=window.visualViewport;
  if(!mobileViewport.matches||!viewport){document.documentElement.style.removeProperty('--gs-mobile-viewport-height');return;}
  // Mobile Safari does not always resize CSS 100dvh when the software keyboard opens.
  const height=Math.round(viewport.height);
  if(height>0)document.documentElement.style.setProperty('--gs-mobile-viewport-height',height+'px');
}
function syncMobileLayout(){
  if(!mobileViewport.matches){setMobileRail(false);setMobileOptions(false);$('#agentRail').inert=false;}
  else if(!$('#agentRail').classList.contains('mobile-open'))$('#agentRail').inert=true;
  syncMobileViewportHeight();
}
function setView(name){
  if(name==='agents')checkChatGPTConnection().catch(()=>{});
  setMobileRail(false);$$('.nav-button').forEach(x=>x.classList.toggle('active',x.dataset.view===name));$$('.view').forEach(x=>x.classList.toggle('active',x.id===`view-${name}`));if(name!=='chat')refresh()}
function conversationFor(agent,projectId){
  const key='gs_room_'+agent+'_'+(projectId||'general');
  let value=localStorage.getItem(key);
  if(!value){
    value=(!projectId&&agent==='qwen')?(localStorage.getItem('gs_conversation_id')||crypto.randomUUID()):crypto.randomUUID();
    localStorage.setItem(key,value);
  }
  return value;
}
function setAgent(agent){
  state.agent=agent;state.groupId=null;
  $('#privateChannelMenu').open=false;
  state.conversationId=conversationFor(agent,state.projectId);
  $$('.agent-choice').forEach(x=>x.classList.toggle('active',x.dataset.agent===agent));
  $('#conversationTitle').textContent=agent==='qwen'?'Local AI channel':agent==='codex'?'Codex workspace agent':'Administrator channel';
  $('#editGroupButton').hidden=true;
  $('#startCollaborationButton').hidden=true;
  $('#openModelSettings').hidden=agent!=='codex';
  $('#projectSelect').disabled=false;
  $('#modelControls').hidden=true;
  $('#permissionPill').textContent=agent==='qwen'?'READ · PROPOSE':agent==='codex'?'WORKSPACE · CODE':'TASK STATUS · READ';
  $('#requestType').hidden=agent!=='qwen';
  $('#prompt').placeholder=agent==='qwen'?'Ask for an explanation…':agent==='codex'?'Ask Codex to create, edit, test or delete project files…':'Try “list tasks” or “status GS-…”';
  renderWorkspaces();renderMessages();renderActiveAgents();updateComposerAvailability();
  setMobileRail(false);
}
function selectGroup(groupId){
  const group=(state.data?.workspaces?.groups||[]).find(g=>g.id===groupId);
  if(!group){toast('Group not found');return;}
  state.groupId=group.id;state.agent='group';
  state.conversationId=group.conversation_id;
  $$('.agent-choice').forEach(x=>x.classList.remove('active'));
  $('#conversationTitle').textContent=group.name;
  $('#editGroupButton').hidden=false;
  $('#startCollaborationButton').hidden=false;
  $('#openModelSettings').hidden=!group.models.includes('codex');
  $('#privateChannelMenu').open=false;
  $('#projectSelect').disabled=true;
  $('#modelControls').hidden=true;
  $('#requestType').hidden=false;
  $('#permissionPill').textContent='COORDINATOR · READ / PROPOSE';
  $('#prompt').placeholder='Ask Coordinator, type /goal, or mention @Qwen…';
  renderWorkspaces();renderMessages();renderActiveAgents();updateComposerAvailability();
  setMobileRail(false);
}
function chooseProject(projectId){
  state.projectId=projectId;
  localStorage.setItem('gs_project_id',projectId);
  if(state.agent==='group'){toast('Edit group members to change its project');return;}
  state.conversationId=conversationFor(state.agent,projectId);
  renderWorkspaces();renderMessages();
  setMobileRail(false);
}
function taskStatus(task){
  if(!task)return '';
  const labels={queued:'Queued — waiting for worker',claimed:'Worker assigned',running:'Generating response…',retry_pending:'Retry pending — check Tasks for details',failed:'Task failed — check Tasks for details',blocked:'Task blocked',cancelled:'Task cancelled',completed:'Completed'};
  const approval=task.approval?.status;
  if(approval==='rejected')return '<small class="task-state">Rejected — bot will not run</small>';
  if(approval==='pending')return '<small class="task-state">Waiting for your approval</small>';
  const status=String(task.status||'queued');
  const stage=(['retry_pending','failed','blocked'].includes(status)&&task.failed_stage)?' · '+task.failed_stage:'';
  return `<small class="task-state ${esc(status)}">${esc((labels[status]||status)+stage)}</small>`;
}

function copyButton(taskId){
  return '<button type="button" class="copy-response" data-task-id="'+esc(taskId)+'" aria-label="Copy full AI response">Copy response</button>';
}
function responseMeta(entry,task){
  const result=task?.result||{};
  const model=entry.model||result.model;
  const rate=entry.tokens_per_second??result.tokens_per_second;
  const duration=entry.generation_seconds??result.generation_seconds;
  const bits=[];
  if(model)bits.push(model);
  if(Number.isFinite(Number(rate))&&Number(rate)>0)bits.push(rate+' tokens/s');
  if(Number.isFinite(Number(duration))&&Number(duration)>0)bits.push(duration+'s generation');
  return bits.length?'<small class="response-meta">'+esc(bits.join(' · '))+'</small>':'';
}

function renderMessages(){
  const root=$('#messages');
  const nearBottom=(root.scrollHeight-root.scrollTop-root.clientHeight)<100;
  const messages=(state.data?.conversations?.[state.conversationId]||[]).filter(x=>state.agent==='group'||!x.agent||x.agent===state.agent);
  const tasks=new Map((state.data?.tasks||[]).map(task=>[task.task_id,task]));
  const codexJobs=new Map((state.data?.codex?.jobs||[]).map(job=>[job.id,job]));
  const replies=new Set(messages.filter(x=>x.role==='assistant').map(x=>x.task_id));
  if(!messages.length){
    root.innerHTML=`<div class="empty-state"><span>GS / 003</span><h2>Communication, grounded.</h2><p>${state.agent==='qwen'?'Ask the selected local model for an explanation, assessment, or code proposal. Requests run automatically within the agent’s allowed permissions.' :state.agent==='group'?'Coordinator answers by default. Use /goal to plan or @Qwen to ask a specialist.':'Use read-only Administrator commands: help, list tasks, or status &lt;task-id&gt;.'}</p></div>`;
    return;
  }
  const html=[];
  for(const entry of messages){
    const task=tasks.get(entry.task_id);
    const groupTasks=Array.isArray(entry.task_ids)?entry.task_ids.map(id=>tasks.get(id)).filter(Boolean):[];
    const jobs=Array.isArray(entry.codex_job_ids)?entry.codex_job_ids.map(id=>codexJobs.get(id)).filter(Boolean):[];
    const codexProgress=jobs.map(job=>{
      const actions=job.status==='pending_approval'?'<span class="group-approval-actions">'+
        '<button type="button" data-codex-decision="approve" data-job-id="'+esc(job.id)+'">Approve workspace task</button>'+
        '<button type="button" data-codex-decision="reject" data-job-id="'+esc(job.id)+'">Reject</button></span>':'';
      return '<span class="group-task-status">Codex · '+esc(job.status)+' · '+
        esc(job.scope==='workspace_write'?'Can change project files':'Read-only')+
        (job.model_id?' · '+esc(job.model_id):' · CLI default')+
        (job.reasoning_effort?' · '+esc(job.reasoning_effort):'')+actions+'</span>';
    }).join('');
    const groupProgress=groupTasks.map(t=>{
      const pending=t.status==='queued'&&t.approval?.status==='pending';
      const actions=pending?'<span class="group-approval-actions">'+
        '<button type="button" data-group-decision="approve" data-task-id="'+esc(t.task_id)+'">Approve reply</button>'+
        '<button type="button" data-group-decision="reject" data-task-id="'+esc(t.task_id)+'">Reject</button></span>':'';
      return '<span class="group-task-status">'+esc(t.payload?.speaker||t.payload?.model||t.requested_worker)+
        ' · '+taskStatus(t)+actions+'</span>';
    }).join('');
    const progress=['user','note'].includes(entry.role)?(groupTasks.length?groupProgress:taskStatus(task))+codexProgress:'';
    const noteKind=entry.role==='note'&&['goal','milestone'].includes(entry.kind)?entry.kind:'';
    const noteLabel=noteKind?'<span class="note-label">'+esc(noteKind)+'</span>':'';
    const memberLabel=state.agent==='group'&&['assistant','system'].includes(entry.role)
      ?'<span class="member-label">'+esc(entry.speaker||entry.model||'Local AI')+'</span>':'';
    const identity=entry.task_id||entry.note_id||entry.group_turn_id||'local';
    const timestamp=new Date(entry.timestamp);
    const shortTime=Number.isNaN(timestamp.getTime())?'':timestamp.toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
    const fullTime=Number.isNaN(timestamp.getTime())?'':timestamp.toLocaleString();
    const meta='<small class="message-meta"><span class="message-id">'+esc(identity)+' · </span><span class="message-time" title="'+esc(fullTime)+'">'+esc(shortTime)+'</span></small>';
    html.push(`<div class="message ${esc(entry.role)} ${noteKind}">${noteLabel}${memberLabel}<span class="message-content">${esc(entry.content)}</span>${meta}${progress}${entry.role==='assistant'?responseMeta(entry,task)+copyButton(entry.task_id):''}</div>`);
    for(const job of jobs){
      if(job.status==='completed'&&job.answer)
        html.push('<div class="message assistant"><span class="member-label">Codex</span>'+
          '<span class="message-content">'+esc(job.answer)+'</span>'+
          '<small>'+esc(job.id)+' · '+esc(job.scope)+'</small></div>');
      else if(job.status==='failed'&&job.error)
        html.push('<div class="message system"><span class="member-label">Codex</span>'+
          '<span class="message-content">'+esc(job.error)+'</span></div>');
    }
    // Group replies may appear in task records before persistence in chat history.
    if(['user','note'].includes(entry.role)&&groupTasks.length){
      for(const groupTask of groupTasks){
        if(groupTask.status==='completed'&&!replies.has(groupTask.task_id)
           &&typeof groupTask.result?.answer==='string'&&groupTask.result.answer){
          const model=groupTask.payload?.speaker||groupTask.result.model||groupTask.payload?.model||'Local AI';
          html.push(`<div class="message assistant"><span class="member-label">${esc(model)}</span><span class="message-content">${esc(groupTask.result.answer)}</span><small>${esc(groupTask.task_id)} · recovered from task result</small>${responseMeta({},groupTask)}${copyButton(groupTask.task_id)}</div>`);
        }
      }
    }
    // Queue completion can be visible before the history writer finishes.
    // Show the authoritative result in that case instead of losing the reply.
    if(['user','note'].includes(entry.role)&&task?.status==='completed'&&!replies.has(entry.task_id)&&typeof task.result?.answer==='string'&&task.result.answer){
      html.push(`<div class="message assistant">${esc(task.result.answer)}<small>${esc(entry.task_id)} · recovered from task result</small>${responseMeta({},task)}${copyButton(entry.task_id)}</div>`);
    }
  }
  if(state.agent==='group'&&state.groupId){
    const flows=(state.data?.collaborations||[]).filter(f=>f.group_id===state.groupId).slice(0,4);
    for(const flow of flows.reverse()){
      const status=esc(flow.state);
      const action=flow.state==='completed'||flow.state==='failed'?'': '<button type="button" data-flow-advance="'+esc(flow.id)+'">Check &amp; advance</button>';
      html.unshift('<div class="collaboration-card"><strong>Multi-agent workflow</strong> <span class="flow-state">'+status+'</span>'+
        '<p>'+esc(flow.goal)+'</p><small>Qwen proposal → Codex implementation → Granite report review</small>'+
        '<small>'+esc(flow.id)+'</small>'+action+'</div>');
    }
  }
  root.innerHTML=html.join('');
  if(nearBottom)root.scrollTop=root.scrollHeight;
}


function renderWorkspaces(){
  const workspace=state.data?.workspaces||{};
  const projects=workspace.projects||[];
  const groups=workspace.groups||[];
  const names=new Map(projects.map(p=>[p.id,p.name]));
  $('#groupList').innerHTML=groups.map(g=>
    '<button type="button" class="group-room '+(g.id===state.groupId?'active':'')+
    '" data-group="'+esc(g.id)+'"><span class="room-avatar">◎</span><span><b>'+esc(g.name)+
    '</b><small>'+esc(g.models.length+' AI · '+(names.get(g.project_id)||'General'))+'</small></span></button>'
  ).join('')||'<p class="rail-empty">No groups yet</p>';
  $('#projectList').innerHTML=projects.map(p=>
    '<button type="button" class="project-room '+(p.id===state.projectId&&state.agent!=='group'?'active':'')+
    '" data-project="'+esc(p.id)+'" title="'+esc(p.path)+'">'+esc(p.name)+'</button>'
  ).join('')||'<p class="rail-empty">Choose a folder to begin</p>';
  const selector=$('#projectSelect');
  const current=state.agent==='group'?(groups.find(g=>g.id===state.groupId)?.project_id||''):state.projectId;
  const signature=JSON.stringify(projects.map(p=>[p.id,p.name]));
  if(selector.dataset.optionsKey!==signature){
    selector.innerHTML='<option value="">No project</option>'+
      projects.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+'</option>').join('');
    selector.dataset.optionsKey=signature;
  }
  selector.value=current;
}
function activeAgentEntry(name,detail,available=true,kind='model'){
  const initials=kind==='coordinator'?'CO':name.split(/[^A-Za-z0-9]+/).filter(Boolean).map(part=>part[0]).join('').slice(0,2).toUpperCase()||'AI';
  return '<div class="active-agent '+esc(kind)+'"><span class="active-agent-avatar">'+esc(initials)+
    '</span><span><b>'+esc(name)+'</b><small>'+esc(detail)+'</small></span><i class="agent-presence '+
    (available?'':'offline')+'" title="'+esc(available?'Available':'Offline')+'"></i></div>';
}
function renderActiveAgents(){
  const root=$('#activeAgentList');
  if(!root)return;
  const registered=new Map((state.data?.models?.registered||[]).map(item=>[item.model,item]));
  let entries=[];
  let note='Participants available in this conversation.';
  if(state.agent==='group'){
    const group=(state.data?.workspaces?.groups||[]).find(item=>item.id===state.groupId);
    if(group){
      entries.push(activeAgentEntry('Coordinator','Default group router',true,'coordinator'));
      entries.push(...group.models.map(model=>{
        const item=registered.get(model);
        return activeAgentEntry(item?.label||model,item?.role||'Proposal-only',Boolean(item?.available));
      }));
      note=group.models.length+' group participant'+(group.models.length===1?'':'s')+' · Replies run sequentially.';
    }
  }else if(state.agent==='codex'){
    const item=registered.get('codex');
    if(item)entries.push(activeAgentEntry('Codex',item.role,Boolean(item.available)));
    note='Codex coding agent · Selected project · Explicit approval by default.';
  }else if(state.agent==='qwen'){
    const item=registered.get(state.selectedModel);
    if(item)entries.push(activeAgentEntry(item.label||item.model,item.role||'Proposal-only',Boolean(item.available)));
    note='Selected local model for this direct conversation.';
  }else{
    entries.push(activeAgentEntry('Administrator','Read-only task operations',true,'coordinator'));
    note='Administrator reads Ground Space task state only.';
  }
  root.innerHTML=entries.join('')||'<p class="rail-empty">No active agents</p>';
  $('#activeAgentNote').textContent=note;
}
function projectOptions(selected){
  return '<option value="">No project</option>'+
    (state.data?.workspaces?.projects||[]).map(p=>'<option value="'+esc(p.id)+'"'+
      (p.id===selected?' selected':'')+'>'+esc(p.name)+'</option>').join('');
}
function openGroupEditor(groupId=''){
  setMobileRail(false);
  clearDialogError('#groupDialogError');
  const group=(state.data?.workspaces?.groups||[]).find(g=>g.id===groupId);
  $('#groupForm').dataset.editGroup=group?.id||'';
  $('#groupDialogTitle').textContent=group?'Edit group':'New group chat';
  $('#groupName').value=group?.name||'';
  $('#groupName').disabled=!!group;
  $('#saveGroup').textContent=group?'Save changes':'Create group';
  $('#groupProject').innerHTML=projectOptions(group?.project_id||state.projectId);
  $('#groupMemberOptions').innerHTML=(state.data?.models?.registered||[]).map(item=>{
    const mode=group?.approval_modes?.[item.model]||(item.model==='codex'?'manual':'approve_for_me');
    const opts=[['manual','Ask me'],['approve_for_me','Approve for me'],['disabled','Off']]
      .map(([value,label])=>'<option value="'+value+'"'+(mode===value?' selected':'')+'>'+label+'</option>').join('');
    return '<div class="group-member-setting"><label class="member-option"><input type="checkbox" name="group-member" value="'+esc(item.model)+
      '"'+(group?.models.includes(item.model)?' checked':'')+'><span><b>'+esc(item.model)+
      '</b><small>'+esc(item.available?(item.model==='codex'?'Available · workspace coding agent':'Available · read/propose only'):'Offline')+
      '</small></span></label><label class="group-member-policy-label">Bot approval'+
      '<select class="group-member-policy" data-model="'+esc(item.model)+'" aria-label="Approval for '+esc(item.model)+'">'+
      opts+'</select></label></div>';
  }).join('')||'<p>No registered local models. Add them under Agents first.</p>';
  $('#groupDialog').showModal();
}
async function saveGroup(event){
  event.preventDefault();
  const models=$$('input[name="group-member"]:checked').map(x=>x.value);
  const groupId=$('#groupForm').dataset.editGroup;
  try{
    const approval_modes={};
    for(const select of $$('.group-member-policy')){
      if(models.includes(select.dataset.model))approval_modes[select.dataset.model]=select.value;
    }
    const payload={name:$('#groupName').value,models,approval_modes,
      project_id:$('#groupProject').value||null};
    const response=await api(groupId?'/api/groups/update':'/api/groups/create',{
      method:'POST',body:JSON.stringify(groupId?{...payload,group_id:groupId}:payload)
    });
    $('#groupDialog').close();
    await refresh();
    selectGroup(response.id);
    toast(groupId?'Group updated':'Group created');
  }catch(error){showDialogError('#groupDialogError',error);}
}
async function browseFolders(path=null){
  try{
    const data=await api('/api/projects/browse'+(path?'?path='+encodeURIComponent(path):''));
    clearDialogError('#projectDialogError');
    $('#folderPicker').hidden=false;
    $('#folderCurrent').textContent=data.current||'Allowed project roots';
    $('#folderUp').disabled=data.is_root_list;
    $('#folderUp').dataset.parent=data.parent||'';
    const choose=data.current?'<button type="button" class="folder-use" data-folder="'+esc(data.current)+'">✓ Use this folder</button>':'';
    $('#folderEntries').innerHTML=choose+(data.folders||[]).map(item=>
      '<button type="button" class="folder-entry" data-folder="'+esc(item.path)+'">📁 '+esc(item.name)+'</button>'
    ).join('')||'<p>No subfolders</p>';
  }catch(error){showDialogError('#projectDialogError',error);}
}


function renderAgentCard(item, all){
  const profiles=state.data?.agent_configs?.profiles||{};
  const codex=item.model==='codex';
  const profile=profiles[item.model]||{model_id:codex?'':item.model,
    level:codex?'':'balanced',
    access:codex?['read','review','workspace_write']:['chat','read','propose','review'],
    approval:codex?'manual':'auto_read_only'};
  const available=all.filter(x=>x.provider==='ollama');
  const models=codex
    ?[['','CLI default'],['gpt-6.1-sol','GPT-6.1 Sol (verified on ASUS)'],['gpt-5.6-sol','GPT-5.6 Sol (requires CLI support)']]
    :available.map(x=>[x.model,x.model+(x.available?'':' (offline)')]);
  if(!models.some(x=>x[0]===profile.model_id))models.push([profile.model_id,profile.model_id+' (saved custom)']);
  const opts=(entries,value)=>entries.map(([id,label])=>'<option value="'+esc(id)+'"'+(id===value?' selected':'')+'>'+esc(label)+'</option>').join('');
  const access=codex
    ?[['read','Read'],['review','Review'],['workspace_write','Workspace coding · write/run/delete']]
    :[['chat','Chat'],['read','Read'],['propose','Propose'],['review','Review']];
  const checks=access.map(([id,label])=>'<label class="agent-access-option"><input type="checkbox" data-agent-access value="'+esc(id)+'"'+
    ((profile.access||[]).includes(id)?' checked':'')+'><span>'+esc(label)+'</span></label>').join('');
  const level=codex?[['','CLI default'],['low','Low'],['medium','Medium'],['high','High']]
    :[['fast','Low · fast'],['balanced','Medium · balanced'],['detailed','High · detailed']];
  const approvals=codex
    ?[['manual','Ask me'],['auto_read_only','Auto · read-only'],['disabled','Off']]
    :[['auto_read_only','Auto · read-only'],['disabled','Off']];
  const selectedApproval=approvals.some(x=>x[0]===profile.approval)?profile.approval:approvals[0][0];
  return '<details class="registered-model agent-config-card" data-agent-item="'+esc(item.model)+'">'+
    '<summary><span class="agent-config-heading"><b>'+esc(item.model)+'</b>'+
    '<small>'+esc(item.available?'Ready · '+(codex?'Connected CLI':'Local Ollama'):'Unavailable')+'</small>'+
    '<span class="agent-summary-value">'+esc((codex?(profile.model_id||'CLI default'):profile.model_id))+
    ' · '+esc(profile.level||'Default')+' · '+esc(profile.approval)+'</span></span>'+
    '<span class="agent-settings-chevron" aria-hidden="true">⌄</span></summary>'+
    '<div class="agent-config-fields">'+
    '<label class="agent-config-field"><span>Model</span><select data-agent-field="model_id" aria-label="'+esc(item.model)+' model">'+opts(models,profile.model_id)+'</select></label>'+
    '<fieldset class="agent-config-field agent-config-access"><legend>Access · multi-select</legend><div class="agent-access-grid">'+checks+'</div></fieldset>'+
    '<label class="agent-config-field"><span>Level</span><select data-agent-field="level" aria-label="'+esc(item.model)+' level">'+opts(level,profile.level)+'</select></label>'+
    '<label class="agent-config-field"><span>Approval</span><select data-agent-field="approval" aria-label="'+esc(item.model)+' approval">'+opts(approvals,selectedApproval)+'</select></label>'+
    '<p class="agent-config-note">'+(codex?'Workspace coding bundles write, run and delete; it still requires ASUS server opt-in and task approval.':'Local models never receive filesystem write access.')+
    ' Existing group overrides stay in place; saved defaults apply to new tasks.</p>'+
    '<div class="agent-config-actions"><button type="button" class="remove-model" data-model="'+esc(item.model)+'">Remove</button>'+
    '<button type="button" class="save-agent-config" data-agent="'+esc(item.model)+'">Save configuration</button></div>'+
    '<p class="agent-config-feedback" role="status" aria-live="polite"></p></div></details>';
}

function renderModels(){
  const data=state.data?.models||{};
  const registered=data.registered||[];
  const online=registered.filter(item=>item.available&&item.provider==='ollama');
  const chatModels=registered.filter(item=>item.provider==='ollama');
  $('#codexAgentChannel').hidden=!registered.some(item=>item.model==='codex');
  $('#privateChannelMenu .private-channel-count').textContent=String(2+(registered.some(item=>item.model==='codex')?1:0));
  const choices=$('#modelSelect');
  const choicesKey=JSON.stringify(chatModels.map(item=>[item.model,item.available]));
  if(choices.dataset.optionsKey!==choicesKey){
    choices.innerHTML=chatModels.map(item=>'<option value="'+esc(item.model)+'" '+(!item.available?'disabled':'')+'>'+esc(item.model+(item.available?'':' (offline)'))+'</option>').join('');
    choices.dataset.optionsKey=choicesKey;
  }
  if(!online.some(item=>item.model===state.selectedModel)){
    state.selectedModel=online[0]?.model||'';
    if(state.selectedModel)localStorage.setItem('gs_model',state.selectedModel);
  }
  choices.value=state.selectedModel;
  const perf=$('#performanceSelect');
  const profileKey=JSON.stringify((data.presets||[]).map(item=>[item.id,item.label]));
  if(perf.dataset.optionsKey!==profileKey){
    perf.innerHTML=(data.presets||[]).map(item=>'<option value="'+esc(item.id)+'">'+esc(item.label)+'</option>').join('');
    perf.dataset.optionsKey=profileKey;
  }
  if(!(data.presets||[]).some(item=>item.id===state.performance))state.performance='balanced';
  perf.value=state.performance;
  const discovered=data.discovered||[];
  const available=$('#availableModel');
  const keep=available.value;
  const availableKey=JSON.stringify(discovered);
  if(available.dataset.optionsKey!==availableKey){
    available.innerHTML=discovered.map(name=>'<option value="'+esc(name)+'">'+esc(name==='codex'?'Connected · Codex CLI':'Local · '+name)+'</option>').join('')+
      '<option value="" disabled>Claude · Not connected</option><option value="" disabled>Grok · Not connected</option>';
    available.dataset.optionsKey=availableKey;
  }
  if(discovered.includes(keep))available.value=keep;
  if(!discovered.length)available.innerHTML='<option value="">No additional Ollama models</option>';
  $('#addModelButton').disabled=!discovered.length;
  $('#modelImportStatus').textContent=discovered.length
    ? discovered.length+' AI agent'+(discovered.length===1?'':'s')+' available to add on this ASUS.'
    : data.registered?.some(item=>item.available)
      ? 'All detected Ollama models are already registered, or no additional model is installed. To add more, install them in Ollama on the ASUS first.'
      : 'No additional installed Ollama models detected. Check that Ollama is running on the ASUS. Online AI accounts require a separate integration.';
  const cards=$('#registeredModels');
  const signature=JSON.stringify(registered.map(item=>[item.model,item.available,
    state.data?.agent_configs?.profiles?.[item.model]]));
  if(cards.dataset.signature!==signature){
    cards.innerHTML=registered.map(item=>renderAgentCard(item,registered)).join('')||
      '<p>No agents registered yet. Add a local model or a connected provider.</p>';
    cards.dataset.signature=signature;
  }
  updateComposerAvailability();
}
async function copyText(value){
  try{
    if(!navigator.clipboard?.writeText)throw new Error('Clipboard API unavailable');
    await navigator.clipboard.writeText(value);
  }catch(error){
    const area=document.createElement('textarea');
    area.value=value;area.style.position='fixed';area.style.opacity='0';
    document.body.appendChild(area);area.select();
    const ok=document.execCommand('copy');area.remove();
    if(!ok)throw new Error('Clipboard unavailable — select the reply manually');
  }
}
async function copyReply(taskId){
  const conversation=state.data?.conversations?.[state.conversationId]||[];
  const history=conversation.find(entry=>entry.role==='assistant'&&entry.task_id===taskId);
  const task=(state.data?.tasks||[]).find(entry=>entry.task_id===taskId);
  const answer=history?.content||task?.result?.answer;
  if(typeof answer!=='string'||!answer){toast('Reply not ready');return;}
  try{await copyText(answer);toast('Response copied');}catch(error){toast(error.message);}
}

function renderAgents(){const root=$('#agentGrid');root.innerHTML=(state.data?.agents||[]).map(a=>`<article class="agent-card"><header><h2>${esc(a.agent_id.replaceAll('-',' '))}</h2><span class="${a.active?'live':'live offline'}">${a.active?'● ONLINE':'○ INACTIVE'}</span></header><p>${esc(a.role)}${a.model?` · ${esc(a.model)}`:''}</p><div class="chips">${a.permissions.map(p=>`<span>${esc(p)}</span>`).join('')}</div></article>`).join('')}
function taskLabel(task){
  const source=task.payload?.prompt||task.payload?.operation||task.payload?.request_type||task.requested_worker||'Task';
  return String(source).replace(/\s+/g,' ').trim().slice(0,160);
}
function renderTasks(){
  const rows=$('#taskRows'),tasks=state.data?.tasks||[];
  rows.innerHTML=tasks.map(t=>{
    const label=taskLabel(t),time=t.updated_at?new Date(t.updated_at).toLocaleString():'—';
    return '<tr data-task="'+esc(t.task_id)+'" tabindex="0" aria-label="Inspect '+esc(label)+'">'+
      '<td class="task-primary"><b class="task-name" title="'+esc(label)+'">'+esc(label)+'</b>'+
      '<small class="task-short-id" title="'+esc(t.task_id)+'">'+esc(t.task_id)+'</small></td>'+
      '<td class="task-worker">'+esc(t.requested_worker)+'</td>'+
      '<td class="task-approval">'+esc(t.approval?.status||'unknown')+'</td>'+
      '<td class="task-status"><span class="badge '+esc(t.status)+'">'+esc(t.status)+'</span></td>'+
      '<td class="task-date">'+esc(time)+'</td></tr>';
  }).join('')||'<tr><td colspan="5">No tasks yet.</td></tr>';
  for(const row of rows.querySelectorAll('tr[data-task]')){
    const show=async()=>{$('#taskDetail').textContent=JSON.stringify(await api('/api/tasks/'+encodeURIComponent(row.dataset.task)),null,2)};
    row.addEventListener('click',()=>show().catch(error=>toast(error.message)));
    row.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show().catch(error=>toast(error.message));}});
  }
}
const CODEX_MODES={
  manual:'Every Codex review waits for your explicit approval.',
  auto_read_only:'Approve for me: Codex starts read-only reviews automatically. File edits, installs and elevated commands stay blocked.',
  disabled:'Codex review requests are blocked for this scope.'
};
function codexProjectMode(projectId){
  const data=state.data?.codex||{};
  return (projectId&&data.project_modes?.[projectId])||data.default_mode||'manual';
}
function refreshCodexPolicyDescription(){
  const selected=$('#codexApprovalMode').value;
  $('#codexPolicyDescription').textContent=CODEX_MODES[selected]||CODEX_MODES.manual;
}
let chatgptStatus=null;
async function checkChatGPTConnection(){
  const status=await api('/api/auth/chatgpt/status');
  chatgptStatus=status;
  renderChatGPTConnection();
  return status;
}
function renderChatGPTConnection(){
  const enabled=Boolean(state.data?.chatgpt_connection?.enabled);
  const status=chatgptStatus;
  const connected=Boolean(status?.connected);
  $('#chatgptConnectButton').disabled=!enabled||connected;
  $('#chatgptConnectionStatus').textContent=connected
    ? 'Connected to Codex '+(status.auth_mode==='chatgpt'?'with ChatGPT':'using local credentials')+
      (status.plan_type?' · '+status.plan_type:'')
    : !enabled?'Private owner sign-in is disabled on ASUS until deliberately enabled at startup.'
    : status?.login_state==='pending'?'Waiting for you to approve the device code on OpenAI.'
    : status?.login_state==='unavailable'?'Codex app-server is unavailable; check CLI version/login on ASUS.'
    : 'Not connected yet. Continue with ChatGPT to begin.';
}
async function startChatGPTDeviceLogin(){
  const button=$('#chatgptConnectButton');
  button.disabled=true;
  try{
    const details=await api('/api/auth/chatgpt/device/start',{method:'POST',body:'{}'});
    $('#chatgptVerifyLink').href=details.verification_url;
    $('#chatgptDeviceCode').textContent=details.user_code;
    $('#chatgptDevicePanel').hidden=false;
    toast('Device code ready. Approve sign-in at the official OpenAI page.');
    chatgptStatus={login_state:'pending'};
    renderChatGPTConnection();
  }catch(error){toast(error.message);}
  finally{renderChatGPTConnection();}
}
function modelProfileKey(){
  return state.agent==='group'&&state.groupId?'codex:group:'+state.groupId:'codex:direct';
}
function currentCodexProfile(){
  return state.data?.model_profiles?.profiles?.[modelProfileKey()]||{model_id:'',reasoning_effort:''};
}
function updateCustomModelVisibility(){
  const custom=$('#codexModelChoice').value==='_custom';
  $('#codexCustomModel').hidden=!custom;
  $('#codexCustomModelLabel').hidden=!custom;
  $('#codexCustomModel').required=custom;
}
function openModelSettings(){
  if($('#openModelSettings').hidden)return;
  const profile=currentCodexProfile();
  $('#modelSettingsScope').textContent=state.agent==='group'
    ?'This group’s Codex model and effort will be used for @Codex and Co-work tasks.'
    :'This private Codex chat uses these model and reasoning settings.';
  const choice=$('#codexModelChoice');
  const preset=[...choice.options].some(o=>o.value===profile.model_id&&o.value!=='_custom');
  choice.value=preset?profile.model_id:'_custom';
  $('#codexCustomModel').value=preset?'':profile.model_id;
  $('#codexReasoningEffort').value=profile.reasoning_effort||'';
  updateCustomModelVisibility();
  clearDialogError('#modelSettingsError');
  $('#modelSettingsDialog').showModal();
}
async function saveModelSettings(event){
  event.preventDefault();
  const button=$('#saveModelSettings');
  button.disabled=true;
  try{
    const model_id=$('#codexModelChoice').value==='_custom'
      ?$('#codexCustomModel').value.trim():$('#codexModelChoice').value;
    await api('/api/model-profiles/set',{method:'POST',body:JSON.stringify({
      provider:'codex',group_id:state.agent==='group'?state.groupId:null,
      model_id,reasoning_effort:$('#codexReasoningEffort').value
    })});
    $('#modelSettingsDialog').close();
    await refresh();
    toast('Codex model settings saved for future tasks');
  }catch(error){showDialogError('#modelSettingsError',error);}
  finally{button.disabled=false;}
}
function renderCodex(){
  const codex=state.data?.codex;
  if(!codex)return;
  const projects=state.data?.workspaces?.projects||[];
  const signature=JSON.stringify(projects.map(p=>[p.id,p.name]));
  const policyScope=$('#codexPolicyProject');
  const reviewScope=$('#codexReviewProject');
  if(policyScope.dataset.signature!==signature){
    const prev=policyScope.value;
    policyScope.innerHTML='<option value="">All projects — default</option>'+
      projects.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+'</option>').join('');
    policyScope.dataset.signature=signature;
    policyScope.value=projects.some(p=>p.id===prev)?prev:'';
  }
  if(reviewScope.dataset.signature!==signature){
    const prev=reviewScope.value||state.projectId;
    reviewScope.innerHTML='<option value="">Select a registered project</option>'+
      projects.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+'</option>').join('');
    reviewScope.dataset.signature=signature;
    reviewScope.value=projects.some(p=>p.id===prev)?prev:'';
  }
  const scope=policyScope.value;
  const modeField=$('#codexApprovalMode');
  if(policyScope.dataset.activeScope!==scope){
    policyScope.dataset.activeScope=scope;
    modeField.value=codexProjectMode(scope);
  }
  refreshCodexPolicyDescription();
  $('#codexAvailability').textContent=codex.cli_installed?
    (codex.registered?'Codex agent registered · ':'Codex not added · ')+
    (codex.write_enabled?'Writable workspace tasks enabled on ASUS':'Writable tasks disabled until ASUS enables the opt-in'):
    'Codex CLI not detected. Install and sign in on ASUS to enable reviews; you may still configure approvals.';
  $('#submitCodexReview').disabled=!codex.cli_installed||!projects.length;
  const list=$('#codexJobList');
  list.innerHTML=(codex.jobs||[]).map(job=>{
    const status=esc(job.status);
    const actions=job.status==='pending_approval'
      ?'<div class="codex-actions"><button type="button" class="codex-decision" data-decision="approve" data-job="'+esc(job.id)+'">Approve task</button>'+
       '<button type="button" class="codex-decision" data-decision="reject" data-job="'+esc(job.id)+'">Reject</button></div>':'';
    return '<article class="codex-job"><header><strong>'+esc(job.project_name)+'</strong><span class="codex-state">'+status+'</span></header>'+
      '<small>'+esc(job.id)+' · '+esc(job.scope)+' · '+esc(job.mode_at_submission)+'</small>'+
      '<details><summary>'+esc(job.prompt)+'</summary>'+
      (job.answer?'<pre>'+esc(job.answer)+'</pre>':'')+
      (job.error?'<p>'+esc(job.error)+'</p>':'')+'</details>'+actions+'</article>';
  }).join('')||'<p>No Codex reviews yet.</p>';
}
async function refresh(){
  if(state.refreshing)return;
  state.refreshing=true;
  try{
    const data=await api('/api/bootstrap');
    state.csrf=data.csrf_token;
    state.data=data;
    if(state.directConversationId===null){
      state.directConversationId=conversationFor('qwen',state.projectId);
      if(state.agent!=='group')state.conversationId=state.directConversationId;
    }
    if(state.agent==='group'&&state.groupId){
      const current=(data.workspaces?.groups||[]).find(g=>g.id===state.groupId);
      if(current){
        $('#conversationTitle').textContent=current.name;
        state.conversationId=current.conversation_id;
      }
    }
    $('#systemState').textContent=(data.models?.registered?.some(x=>x.available))?'Local systems ready':'Ollama unavailable';
    renderModels();renderWorkspaces();renderMessages();renderActiveAgents();renderAgents();renderTasks();renderCodex();renderChatGPTConnection();
    $('#openModelSettings').hidden=!(state.agent==='codex'||(state.agent==='group'&&
      (data.workspaces?.groups||[]).some(g=>g.id===state.groupId&&g.models.includes('codex'))));
  }finally{state.refreshing=false;}
}
async function submit(event){
  event.preventDefault();
  const prompt=$('#prompt').value.trim();
  if(!prompt)return;
  $('#sendButton').disabled=true;
  try{
    const isGroup=state.agent==='group';
    const notes=/^\/(goal|milestone)(\s|$)/i.test(prompt);
    const endpoint=isGroup&&!notes?'/api/groups/send':'/api/chat';
    const response=await api(endpoint,{method:'POST',body:JSON.stringify({
      agent:state.agent,group_id:state.groupId,project_id:state.projectId,
      prompt,request_type:$('#requestType').value,model:state.selectedModel,
      performance:state.performance,conversation_id:state.conversationId
    })});
    if(!isGroup&&state.agent==='qwen')localStorage.setItem('gs_conversation_id',state.conversationId);
    $('#prompt').value='';
    updateSlashMenu();
    await refresh();
    toast(response.codex_job?.status==='pending_approval'?'Codex task waiting for approval':response.entry?(response.task||response.task_ids?'Planning note saved · Coordinator reply queued':'Planning note saved'):isGroup?'Message sent to Coordinator or mentioned specialist':'Task submitted');
  }catch(error){toast(error.message)}
  finally{updateComposerAvailability();}
}
function isSlashAnnotation(){return /^\/(goal|milestone)(\s|$)/i.test($('#prompt').value.trim());}
function updateComposerAvailability(){
  $('#sendButton').disabled=state.agent==='qwen'&&!state.selectedModel&&!isSlashAnnotation();
}
function chooseSlash(kind){
  $('#prompt').value='/'+kind+' ';
  $('#slashMenu').hidden=true;
  updateComposerAvailability();
  $('#prompt').focus();
}
function groupMentionOptions(){
  if(state.agent!=='group'||!state.groupId)return [];
  const group=(state.data?.workspaces?.groups||[]).find(item=>item.id===state.groupId);
  if(!group)return [];
  const models=group.models||[];
  const options=[{token:'@Coordinator',label:'Coordinator',detail:'Default group planner'}];
  for(const model of models){
    const lower=model.toLowerCase();
    let token='@'+model;
    let label=model;
    if(lower.startsWith('qwen2.5-coder')){token='@Qwen';label='Qwen';}
    else if(lower.startsWith('granite')){token='@Granite';label='Granite';}
    else if(lower==='codex'){token='@Codex';label='Codex';}
    else if(lower.startsWith('ministral')){token='@Ministral';label='Ministral';}
    options.push({token,label,detail:model});
  }
  return options.filter((item,index,all)=>all.findIndex(other=>other.token.toLowerCase()===item.token.toLowerCase())===index);
}
function mentionQuery(){
  if(state.agent!=='group')return null;
  const value=$('#prompt').value;
  const caret=$('#prompt').selectionStart??value.length;
  const before=value.slice(0,caret);
  const match=before.match(/(^|\s)@([A-Za-z0-9._:/-]*)$/);
  return match?{query:match[2].toLowerCase(),start:caret-match[2].length-1,end:caret}:null;
}
function updateMentionMenu(){
  const match=mentionQuery();
  const menu=$('#mentionMenu');
  if(!match){menu.hidden=true;menu.innerHTML='';return;}
  const options=groupMentionOptions().filter(item=>item.token.slice(1).toLowerCase().startsWith(match.query));
  menu.innerHTML=options.map(item=>'<button type="button" data-mention="'+esc(item.token)+
    '"><span>'+esc(item.token)+'</span><small>'+esc(item.detail)+'</small></button>').join('');
  menu.hidden=options.length===0;
}
function chooseMention(token){
  const match=mentionQuery();
  if(!match)return;
  const field=$('#prompt');
  field.value=field.value.slice(0,match.start)+token+' '+field.value.slice(match.end);
  const caret=match.start+token.length+1;
  field.setSelectionRange(caret,caret);
  $('#mentionMenu').hidden=true;
  field.focus();
}
function updateSlashMenu(){
  const value=$('#prompt').value.trim();
  const active=/^\/[a-z]*$/i.test(value);
  const prefix=active?value.slice(1).toLowerCase():'';
  let count=0;
  $$('#slashMenu button[data-slash]').forEach(button=>{
    const visible=active&&button.dataset.slash.startsWith(prefix);
    button.hidden=!visible;
    if(visible)count++;
  });
  $('#slashMenu').hidden=count===0;
  updateMentionMenu();
  updateComposerAvailability();
}
$('#prompt').addEventListener('input',updateSlashMenu);
$('#prompt').addEventListener('keydown',event=>{
  if(event.key==='Escape'){$('#slashMenu').hidden=true;$('#mentionMenu').hidden=true;return;}
  if(event.key==='Enter'&&!event.shiftKey&&!$('#mentionMenu').hidden){
    const first=$$('#mentionMenu button[data-mention]').find(button=>!button.hidden);
    if(first){event.preventDefault();chooseMention(first.dataset.mention);return;}
  }
  if(event.key==='Enter'&&!event.shiftKey&&!$('#slashMenu').hidden){
    const first=$$('#slashMenu button[data-slash]').find(button=>!button.hidden);
    if(first){event.preventDefault();chooseSlash(first.dataset.slash);}
  }
});
$('#mentionMenu').addEventListener('click',event=>{
  const button=event.target.closest('button[data-mention]');
  if(button)chooseMention(button.dataset.mention);
});
$('#slashMenu').addEventListener('click',event=>{
  const button=event.target.closest('button[data-slash]');
  if(button)chooseSlash(button.dataset.slash);
});

$('#modelSelect').addEventListener('change',()=>{state.selectedModel=$('#modelSelect').value;localStorage.setItem('gs_model',state.selectedModel);renderActiveAgents();});
$('#performanceSelect').addEventListener('change',()=>{state.performance=$('#performanceSelect').value;localStorage.setItem('gs_performance',state.performance);});
$('#chatgptConnectButton').addEventListener('click',startChatGPTDeviceLogin);
$('#chatgptCheckButton').addEventListener('click',()=>checkChatGPTConnection().catch(error=>toast(error.message)));
$('#chatgptCopyCode').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText($('#chatgptDeviceCode').textContent);toast('Device code copied');}
  catch(error){toast('Copy unavailable; select the code manually');}
});
$('#addModelButton').addEventListener('click',async()=>{
  const model=$('#availableModel').value;
  if(!model)return;
  try{await api('/api/models/add',{method:'POST',body:JSON.stringify({model})});await refresh();toast('Model added');}
  catch(error){toast(error.message);}
});

$('#registeredModels').addEventListener('click',async event=>{
  const button=event.target.closest('button.save-agent-config');
  if(!button)return;
  const root=button.closest('[data-agent-item]');
  const agent_id=button.dataset.agent;
  const select=key=>root.querySelector('[data-agent-field="'+key+'"]').value;
  const access=[...root.querySelectorAll('input[data-agent-access]:checked')].map(x=>x.value);
  button.disabled=true;
  const feedback=root.querySelector('.agent-config-feedback');
  feedback.textContent='Saving…';
  try{
    await api('/api/agents/configure',{method:'POST',
      body:JSON.stringify({agent_id,model_id:select('model_id'),level:select('level'),
        approval:select('approval'),access})});
    if(state.agent==='qwen'&&state.selectedModel===agent_id){
      // Keep stable agent identity in chat; the backend resolves its saved model.
      localStorage.setItem('gs_model',agent_id);
    }
    feedback.textContent='Saved for future direct, group and Co-work tasks';
    await refresh();
    toast('Agent configuration saved');
  }catch(error){feedback.textContent=error.message;button.disabled=false;}
});

$('#registeredModels').addEventListener('click',async event=>{
  const button=event.target.closest('button.remove-model');
  if(!button)return;
  try{await api('/api/models/remove',{method:'POST',body:JSON.stringify({model:button.dataset.model})});await refresh();toast('Model removed');}
  catch(error){toast(error.message);}
});
$('#messages').addEventListener('click',event=>{
  const step=event.target.closest('button[data-flow-advance]');
  if(step){
    step.disabled=true;
    api('/api/collaboration/advance',{method:'POST',body:JSON.stringify({flow_id:step.dataset.flowAdvance})})
      .then(async result=>{await refresh();toast(result.waiting_for||'Workflow advanced to '+result.state);})
      .catch(error=>{toast(error.message);step.disabled=false;});
    return;
  }
  const decision=event.target.closest('button[data-group-decision]');
  if(decision){
    decision.disabled=true;
    api('/api/groups/'+decision.dataset.groupDecision,{
      method:'POST',body:JSON.stringify({group_id:state.groupId,task_id:decision.dataset.taskId})
    }).then(()=>refresh()).then(()=>toast(decision.dataset.groupDecision==='approve'?
      'Read-only bot reply approved':'Bot reply rejected'))
      .catch(error=>{toast(error.message);decision.disabled=false;});
    return;
  }
  const codexDecision=event.target.closest('button[data-codex-decision]');
  if(codexDecision){
    codexDecision.disabled=true;
    api('/api/codex/'+codexDecision.dataset.codexDecision,{method:'POST',
      body:JSON.stringify({job_id:codexDecision.dataset.jobId})})
      .then(()=>refresh()).then(()=>toast('Codex job decision recorded'))
      .catch(error=>{toast(error.message);codexDecision.disabled=false;});
    return;
  }
  const button=event.target.closest('button.copy-response');
  if(button)copyReply(button.dataset.taskId);
});


$('#openModelSettings').addEventListener('click',openModelSettings);
$('#cancelModelSettings').addEventListener('click',()=>$('#modelSettingsDialog').close());
$('#codexModelChoice').addEventListener('change',updateCustomModelVisibility);
$('#modelSettingsForm').addEventListener('submit',saveModelSettings);
$('#newGroupButton').addEventListener('click',()=>openGroupEditor());
$('#editGroupButton').addEventListener('click',()=>openGroupEditor(state.groupId));
$('#startCollaborationButton').addEventListener('click',async()=>{
  if(state.agent!=='group'||!state.groupId){toast('Select a group');return;}
  const goal=$('#prompt').value.trim();
  if(!goal){toast('Describe the coding goal in the message box first');$('#prompt').focus();return;}
  const button=$('#startCollaborationButton');button.disabled=true;
  try{
    await api('/api/collaboration/start',{method:'POST',body:JSON.stringify({group_id:state.groupId,goal})});
    $('#prompt').value='';
    await refresh();
    toast('Qwen proposal requested; advance after review and approval');
  }catch(error){toast(error.message);}
  finally{button.disabled=false;}
});
$('#groupForm').addEventListener('submit',saveGroup);
$('#cancelGroup').addEventListener('click',()=>$('#groupDialog').close());
$('#groupList').addEventListener('click',event=>{
  const button=event.target.closest('button[data-group]');
  if(button)selectGroup(button.dataset.group);
});
$('#projectSelect').addEventListener('change',()=>chooseProject($('#projectSelect').value));
$('#projectList').addEventListener('click',event=>{
  const button=event.target.closest('button[data-project]');
  if(button){if(state.agent==='group')setAgent('qwen');chooseProject(button.dataset.project);}
});
$('#addProjectButton').addEventListener('click',()=>{
  setMobileRail(false);
  clearDialogError('#projectDialogError');
  $('#projectName').value='';$('#projectPath').value='';$('#folderPicker').hidden=true;$('#projectDialog').showModal();
});
$('#cancelProject').addEventListener('click',()=>$('#projectDialog').close());
$('#projectForm').addEventListener('submit',async event=>{
  event.preventDefault();
  try{
    clearDialogError('#projectDialogError');
    const project=await api('/api/projects/add',{method:'POST',body:JSON.stringify({
      path:$('#projectPath').value,name:$('#projectName').value
    })});
    $('#projectDialog').close();
    await refresh();
    if(state.agent==='group')setAgent('qwen');
    chooseProject(project.id);
    toast('Project folder registered — file access remains disabled');
  }catch(error){showDialogError('#projectDialogError',error);}
});
$('#browseRoots').addEventListener('click',()=>browseFolders());
$('#folderUp').addEventListener('click',()=>browseFolders($('#folderUp').dataset.parent||null));
$('#folderEntries').addEventListener('click',event=>{
  const button=event.target.closest('button[data-folder]');
  if(!button)return;
  if(button.classList.contains('folder-use')){
    $('#projectPath').value=button.dataset.folder;
    $('#folderPicker').hidden=true;
  }else browseFolders(button.dataset.folder);
});

$('#mobileRailToggle').addEventListener('click',()=>setMobileRail(!$('#agentRail').classList.contains('mobile-open')));
$('#mobileRailBackdrop').addEventListener('click',()=>{setMobileRail(false);$('#mobileRailToggle').focus();});
$('#closeMobileRail').addEventListener('click',()=>{setMobileRail(false);$('#mobileRailToggle').focus();});
$('#mobileOptionsToggle').addEventListener('click',()=>setMobileOptions(!$('#chatForm').classList.contains('options-open')));
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&$('#agentRail').classList.contains('mobile-open')){setMobileRail(false);$('#mobileRailToggle').focus();}
});
mobileViewport.addEventListener('change',syncMobileLayout);
window.visualViewport?.addEventListener('resize',syncMobileViewportHeight);
window.addEventListener('orientationchange',syncMobileViewportHeight);
syncMobileLayout();
$('#codexPolicyProject').addEventListener('change',()=>{
  $('#codexPolicyProject').dataset.activeScope='';
  renderCodex();
});
$('#codexApprovalMode').addEventListener('change',refreshCodexPolicyDescription);
$('#codexPolicyForm').addEventListener('submit',async event=>{
  event.preventDefault();
  try{
    const scope=$('#codexPolicyProject').value||null;
    await api('/api/codex/policy',{method:'POST',body:JSON.stringify({
      project_id:scope,mode:$('#codexApprovalMode').value
    })});
    await refresh();
    toast('Codex approval settings saved');
  }catch(error){toast(error.message);}
});
$('#codexReviewForm').addEventListener('submit',async event=>{
  event.preventDefault();
  $('#submitCodexReview').disabled=true;
  try{
    const response=await api('/api/codex/submit',{method:'POST',body:JSON.stringify({
      project_id:$('#codexReviewProject').value,prompt:$('#codexReviewPrompt').value.trim()
    })});
    $('#codexReviewPrompt').value='';
    await refresh();
    toast(response.status==='pending_approval'?'Review pending your approval':'Read-only review started');
  }catch(error){toast(error.message);}
  finally{renderCodex();}
});
$('#codexJobList').addEventListener('click',async event=>{
  const button=event.target.closest('button[data-decision][data-job]');
  if(!button)return;
  button.disabled=true;
  try{
    await api('/api/codex/'+button.dataset.decision,{method:'POST',
      body:JSON.stringify({job_id:button.dataset.job})});
    await refresh();toast(button.dataset.decision==='approve'?'Codex review started':'Codex review rejected');
  }catch(error){toast(error.message);button.disabled=false;}
});

$$('.nav-button').forEach(x=>x.onclick=()=>setView(x.dataset.view));$$('.agent-choice').forEach(x=>x.onclick=()=>setAgent(x.dataset.agent));$('#chatForm').addEventListener('submit',submit);refresh().catch(error=>toast(error.message));
// Keep every task in this conversation observable, even after refresh or later messages.
setInterval(()=>refresh().catch(()=>{$('#systemState').textContent='Ground Space disconnected'}),2500);
