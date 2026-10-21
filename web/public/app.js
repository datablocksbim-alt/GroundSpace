const state={agent:'qwen',csrf:'',conversationId:localStorage.getItem('gs_conversation_id')||crypto.randomUUID(),poll:null,data:null,refreshing:false,groupId:null,projectId:localStorage.getItem('gs_project_id')||'',directConversationId:null,selectedModel:localStorage.getItem('gs_model')||'qwen2.5-coder:3b',performance:localStorage.getItem('gs_performance')||'balanced'};
const $=s=>document.querySelector(s);const $$=s=>[...document.querySelectorAll(s)];
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}
async function api(path,options={}){const headers={'Content-Type':'application/json',...(options.headers||{})};if(options.method==='POST')headers['X-Ground-Space-CSRF']=state.csrf;const response=await fetch(path,{...options,headers});const body=await response.json();if(!response.ok)throw new Error(body.error||`Request failed (${response.status})`);return body}
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function setView(name){$$('.nav-button').forEach(x=>x.classList.toggle('active',x.dataset.view===name));$$('.view').forEach(x=>x.classList.toggle('active',x.id===`view-${name}`));if(name!=='chat')refresh()}
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
  state.conversationId=conversationFor(agent,state.projectId);
  $$('.agent-choice').forEach(x=>x.classList.toggle('active',x.dataset.agent===agent));
  $('#conversationTitle').textContent=agent==='qwen'?'Local AI channel':'Administrator channel';
  $('#editGroupButton').hidden=true;
  $('#projectSelect').disabled=false;
  $('#modelControls').hidden=agent!=='qwen';
  $('#permissionPill').textContent=agent==='qwen'?'READ · PROPOSE':'TASK STATUS · READ';
  $('#requestType').hidden=agent!=='qwen';
  $('#prompt').placeholder=agent==='qwen'?'Ask for an explanation…':'Try “list tasks” or “status GS-…”';
  renderWorkspaces();renderMessages();updateComposerAvailability();
}
function selectGroup(groupId){
  const group=(state.data?.workspaces?.groups||[]).find(g=>g.id===groupId);
  if(!group){toast('Group not found');return;}
  state.groupId=group.id;state.agent='group';
  state.conversationId=group.conversation_id;
  $$('.agent-choice').forEach(x=>x.classList.remove('active'));
  $('#conversationTitle').textContent=group.name;
  $('#editGroupButton').hidden=false;
  $('#projectSelect').disabled=true;
  $('#modelControls').hidden=true;
  $('#requestType').hidden=false;
  $('#permissionPill').textContent='GROUP · READ / PROPOSE';
  $('#prompt').placeholder='Ask the whole group, or type /goal…';
  renderWorkspaces();renderMessages();updateComposerAvailability();
}
function chooseProject(projectId){
  state.projectId=projectId;
  localStorage.setItem('gs_project_id',projectId);
  if(state.agent==='group'){toast('Edit group members to change its project');return;}
  state.conversationId=conversationFor(state.agent,projectId);
  renderWorkspaces();renderMessages();
}
function taskStatus(task){
  if(!task)return '';
  const labels={queued:'Queued — waiting for worker',claimed:'Worker assigned',running:'Generating response…',retry_pending:'Retry pending — check Tasks for details',failed:'Task failed — check Tasks for details',blocked:'Task blocked',cancelled:'Task cancelled',completed:'Completed'};
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
  const replies=new Set(messages.filter(x=>x.role==='assistant').map(x=>x.task_id));
  if(!messages.length){
    root.innerHTML=`<div class="empty-state"><span>GS / 003</span><h2>Communication, grounded.</h2><p>${state.agent==='qwen'?'Ask the selected local model for an explanation, assessment, or code proposal. Requests run automatically within the agent’s allowed permissions.':'Use read-only Administrator commands: help, list tasks, or status &lt;task-id&gt;.'}</p></div>`;
    return;
  }
  const html=[];
  for(const entry of messages){
    const task=tasks.get(entry.task_id);
    const groupTasks=Array.isArray(entry.task_ids)?entry.task_ids.map(id=>tasks.get(id)).filter(Boolean):[];
    const groupProgress=groupTasks.map(t=>'<span class="group-task-status">'+esc(t.payload?.model||t.requested_worker)+' · '+taskStatus(t)+'</span>').join('');
    const progress=['user','note'].includes(entry.role)?(groupTasks.length?groupProgress:taskStatus(task)):'';
    const noteKind=entry.role==='note'&&['goal','milestone'].includes(entry.kind)?entry.kind:'';
    const noteLabel=noteKind?'<span class="note-label">'+esc(noteKind)+'</span>':'';
    const memberLabel=state.agent==='group'&&['assistant','system'].includes(entry.role)
      ?'<span class="member-label">'+esc(entry.model||'Local AI')+'</span>':'';
    const identity=entry.task_id||entry.note_id||entry.group_turn_id||'local';
    html.push(`<div class="message ${esc(entry.role)} ${noteKind}">${noteLabel}${memberLabel}<span class="message-content">${esc(entry.content)}</span><small>${esc(identity)} · ${new Date(entry.timestamp).toLocaleString()}</small>${progress}${entry.role==='assistant'?responseMeta(entry,task)+copyButton(entry.task_id):''}</div>`);
    // Group replies may appear in task records before persistence in chat history.
    if(['user','note'].includes(entry.role)&&groupTasks.length){
      for(const groupTask of groupTasks){
        if(groupTask.status==='completed'&&!replies.has(groupTask.task_id)
           &&typeof groupTask.result?.answer==='string'&&groupTask.result.answer){
          const model=groupTask.result.model||groupTask.payload?.model||'Local AI';
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
function projectOptions(selected){
  return '<option value="">No project</option>'+
    (state.data?.workspaces?.projects||[]).map(p=>'<option value="'+esc(p.id)+'"'+
      (p.id===selected?' selected':'')+'>'+esc(p.name)+'</option>').join('');
}
function openGroupEditor(groupId=''){
  const group=(state.data?.workspaces?.groups||[]).find(g=>g.id===groupId);
  $('#groupForm').dataset.editGroup=group?.id||'';
  $('#groupDialogTitle').textContent=group?'Edit group':'New group chat';
  $('#groupName').value=group?.name||'';
  $('#groupName').disabled=!!group;
  $('#saveGroup').textContent=group?'Save changes':'Create group';
  $('#groupProject').innerHTML=projectOptions(group?.project_id||state.projectId);
  $('#groupMemberOptions').innerHTML=(state.data?.models?.registered||[]).map(item=>
    '<label class="member-option"><input type="checkbox" name="group-member" value="'+esc(item.model)+
    '"'+(group?.models.includes(item.model)?' checked':'')+'><span><b>'+esc(item.model)+
    '</b><small>'+esc(item.available?'Available · proposal only':'Offline · proposal only')+
    '</small></span></label>'
  ).join('')||'<p>No registered local models. Add them under Agents first.</p>';
  $('#groupDialog').showModal();
}
async function saveGroup(event){
  event.preventDefault();
  const models=$$('input[name="group-member"]:checked').map(x=>x.value);
  const groupId=$('#groupForm').dataset.editGroup;
  try{
    const payload={name:$('#groupName').value,models,project_id:$('#groupProject').value||null};
    const response=await api(groupId?'/api/groups/update':'/api/groups/create',{
      method:'POST',body:JSON.stringify(groupId?{...payload,group_id:groupId}:payload)
    });
    $('#groupDialog').close();
    await refresh();
    selectGroup(response.id);
    toast(groupId?'Group updated':'Group created');
  }catch(error){toast(error.message);}
}
async function browseFolders(path=null){
  try{
    const data=await api('/api/projects/browse'+(path?'?path='+encodeURIComponent(path):''));
    $('#folderPicker').hidden=false;
    $('#folderCurrent').textContent=data.current||'Allowed project roots';
    $('#folderUp').disabled=data.is_root_list;
    $('#folderUp').dataset.parent=data.parent||'';
    const choose=data.current?'<button type="button" class="folder-use" data-folder="'+esc(data.current)+'">✓ Use this folder</button>':'';
    $('#folderEntries').innerHTML=choose+(data.folders||[]).map(item=>
      '<button type="button" class="folder-entry" data-folder="'+esc(item.path)+'">📁 '+esc(item.name)+'</button>'
    ).join('')||'<p>No subfolders</p>';
  }catch(error){toast(error.message);}
}

function renderModels(){
  const data=state.data?.models||{};
  const registered=data.registered||[];
  const online=registered.filter(item=>item.available);
  const choices=$('#modelSelect');
  const choicesKey=JSON.stringify(registered.map(item=>[item.model,item.available]));
  if(choices.dataset.optionsKey!==choicesKey){
    choices.innerHTML=registered.map(item=>'<option value="'+esc(item.model)+'" '+(!item.available?'disabled':'')+'>'+esc(item.model+(item.available?'':' (offline)'))+'</option>').join('');
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
    available.innerHTML=discovered.map(name=>'<option value="'+esc(name)+'">'+esc(name)+'</option>').join('');
    available.dataset.optionsKey=availableKey;
  }
  if(discovered.includes(keep))available.value=keep;
  $('#addModelButton').disabled=!discovered.length;
  $('#registeredModels').innerHTML=registered.map(item=>
    '<div class="registered-model"><span><b>'+esc(item.model)+'</b><small>'+
    esc(item.available?'Ready · '+item.role:'Offline · '+item.role)+
    '</small></span><button type="button" class="remove-model" data-model="'+esc(item.model)+
    '" aria-label="Remove '+esc(item.model)+'">Remove</button></div>'
  ).join('')||'<p>No models registered. Add an installed model above.</p>';
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
function renderTasks(){const rows=$('#taskRows'),tasks=state.data?.tasks||[];rows.innerHTML=tasks.map(t=>`<tr data-task="${esc(t.task_id)}"><td><b>${esc(t.task_id)}</b></td><td>${esc(t.requested_worker)}</td><td>${esc(t.approval?.status||'unknown')}</td><td><span class="badge ${esc(t.status)}">${esc(t.status)}</span></td><td>${new Date(t.updated_at).toLocaleString()}</td></tr>`).join('')||'<tr><td colspan="5">No tasks yet.</td></tr>';rows.querySelectorAll('tr[data-task]').forEach(row=>row.onclick=async()=>{$('#taskDetail').textContent=JSON.stringify(await api(`/api/tasks/${row.dataset.task}`),null,2)})}
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
    renderModels();renderWorkspaces();renderMessages();renderAgents();renderTasks();
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
    if(!isGroup)localStorage.setItem('gs_conversation_id',state.conversationId);
    $('#prompt').value='';
    updateSlashMenu();
    await refresh();
    toast(response.entry?(response.task||response.task_ids?'Planning note saved · AI review queued':'Planning note saved'):isGroup?'Group request sent to each AI':'Task submitted');
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
  updateComposerAvailability();
}
$('#prompt').addEventListener('input',updateSlashMenu);
$('#prompt').addEventListener('keydown',event=>{
  if(event.key==='Escape'){$('#slashMenu').hidden=true;return;}
  if(event.key==='Enter'&&!event.shiftKey&&!$('#slashMenu').hidden){
    const first=$$('#slashMenu button[data-slash]').find(button=>!button.hidden);
    if(first){event.preventDefault();chooseSlash(first.dataset.slash);}
  }
});
$('#slashMenu').addEventListener('click',event=>{
  const button=event.target.closest('button[data-slash]');
  if(button)chooseSlash(button.dataset.slash);
});

$('#modelSelect').addEventListener('change',()=>{state.selectedModel=$('#modelSelect').value;localStorage.setItem('gs_model',state.selectedModel);});
$('#performanceSelect').addEventListener('change',()=>{state.performance=$('#performanceSelect').value;localStorage.setItem('gs_performance',state.performance);});
$('#addModelButton').addEventListener('click',async()=>{
  const model=$('#availableModel').value;
  if(!model)return;
  try{await api('/api/models/add',{method:'POST',body:JSON.stringify({model})});await refresh();toast('Model added');}
  catch(error){toast(error.message);}
});
$('#registeredModels').addEventListener('click',async event=>{
  const button=event.target.closest('button.remove-model');
  if(!button)return;
  try{await api('/api/models/remove',{method:'POST',body:JSON.stringify({model:button.dataset.model})});await refresh();toast('Model removed');}
  catch(error){toast(error.message);}
});
$('#messages').addEventListener('click',event=>{
  const button=event.target.closest('button.copy-response');
  if(button)copyReply(button.dataset.taskId);
});


$('#newGroupButton').addEventListener('click',()=>openGroupEditor());
$('#editGroupButton').addEventListener('click',()=>openGroupEditor(state.groupId));
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
  $('#projectName').value='';$('#projectPath').value='';$('#folderPicker').hidden=true;$('#projectDialog').showModal();
});
$('#cancelProject').addEventListener('click',()=>$('#projectDialog').close());
$('#projectForm').addEventListener('submit',async event=>{
  event.preventDefault();
  try{
    const project=await api('/api/projects/add',{method:'POST',body:JSON.stringify({
      path:$('#projectPath').value,name:$('#projectName').value
    })});
    $('#projectDialog').close();
    await refresh();
    if(state.agent==='group')setAgent('qwen');
    chooseProject(project.id);
    toast('Project folder registered — file access remains disabled');
  }catch(error){toast(error.message);}
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

$$('.nav-button').forEach(x=>x.onclick=()=>setView(x.dataset.view));$$('.agent-choice').forEach(x=>x.onclick=()=>setAgent(x.dataset.agent));$('#chatForm').addEventListener('submit',submit);refresh().catch(error=>toast(error.message));
// Keep every task in this conversation observable, even after refresh or later messages.
setInterval(()=>refresh().catch(()=>{$('#systemState').textContent='Ground Space disconnected'}),2500);
