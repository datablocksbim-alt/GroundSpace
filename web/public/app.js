const state={agent:'qwen',csrf:'',conversationId:localStorage.getItem('gs_conversation_id')||crypto.randomUUID(),poll:null,data:null,refreshing:false,selectedModel:localStorage.getItem('gs_model')||'qwen2.5-coder:3b',performance:localStorage.getItem('gs_performance')||'balanced'};
const $=s=>document.querySelector(s);const $$=s=>[...document.querySelectorAll(s)];
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}
async function api(path,options={}){const headers={'Content-Type':'application/json',...(options.headers||{})};if(options.method==='POST')headers['X-Ground-Space-CSRF']=state.csrf;const response=await fetch(path,{...options,headers});const body=await response.json();if(!response.ok)throw new Error(body.error||`Request failed (${response.status})`);return body}
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function setView(name){$$('.nav-button').forEach(x=>x.classList.toggle('active',x.dataset.view===name));$$('.view').forEach(x=>x.classList.toggle('active',x.id===`view-${name}`));if(name!=='chat')refresh()}
function setAgent(agent){state.agent=agent;$$('.agent-choice').forEach(x=>x.classList.toggle('active',x.dataset.agent===agent));$('#conversationTitle').textContent=agent==='qwen'?'Local AI channel':'Administrator channel';$('#modelControls').hidden=agent!=='qwen';$('#permissionPill').textContent=agent==='qwen'?'READ · PROPOSE':'TASK STATUS · READ';$('#requestType').hidden=agent!=='qwen';$('#prompt').placeholder=agent==='qwen'?'Ask for an explanation…':'Try “list tasks” or “status GS-…”';renderMessages()}
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
  const messages=(state.data?.conversations?.[state.conversationId]||[]).filter(x=>!x.agent||x.agent===state.agent);
  const tasks=new Map((state.data?.tasks||[]).map(task=>[task.task_id,task]));
  const replies=new Set(messages.filter(x=>x.role==='assistant').map(x=>x.task_id));
  if(!messages.length){
    root.innerHTML=`<div class="empty-state"><span>GS / 003</span><h2>Communication, grounded.</h2><p>${state.agent==='qwen'?'Ask the selected local model for an explanation, assessment, or code proposal. Requests run automatically within the agent’s allowed permissions.':'Use read-only Administrator commands: help, list tasks, or status &lt;task-id&gt;.'}</p></div>`;
    return;
  }
  const html=[];
  for(const entry of messages){
    const task=tasks.get(entry.task_id);
    const progress=entry.role==='user'?taskStatus(task):'';
    html.push(`<div class="message ${esc(entry.role)}">${esc(entry.content)}<small>${esc(entry.task_id||'local')} · ${new Date(entry.timestamp).toLocaleString()}</small>${progress}${entry.role==='assistant'?responseMeta(entry,task)+copyButton(entry.task_id):''}</div>`);
    // Queue completion can be visible before the history writer finishes.
    // Show the authoritative result in that case instead of losing the reply.
    if(entry.role==='user'&&task?.status==='completed'&&!replies.has(entry.task_id)&&typeof task.result?.answer==='string'&&task.result.answer){
      html.push(`<div class="message assistant">${esc(task.result.answer)}<small>${esc(entry.task_id)} · recovered from task result</small>${responseMeta({},task)}${copyButton(entry.task_id)}</div>`);
    }
  }
  root.innerHTML=html.join('');
  if(nearBottom)root.scrollTop=root.scrollHeight;
}

function renderModels(){
  const data=state.data?.models||{};
  const registered=data.registered||[];
  const online=registered.filter(item=>item.available);
  const choices=$('#modelSelect');
  choices.innerHTML=registered.map(item=>'<option value="'+esc(item.model)+'" '+(!item.available?'disabled':'')+'>'+esc(item.model+(item.available?'':' (offline)'))+'</option>').join('');
  if(!online.some(item=>item.model===state.selectedModel)){
    state.selectedModel=online[0]?.model||'';
    if(state.selectedModel)localStorage.setItem('gs_model',state.selectedModel);
  }
  choices.value=state.selectedModel;
  const perf=$('#performanceSelect');
  perf.innerHTML=(data.presets||[]).map(item=>'<option value="'+esc(item.id)+'">'+esc(item.label)+'</option>').join('');
  if(!(data.presets||[]).some(item=>item.id===state.performance))state.performance='balanced';
  perf.value=state.performance;
  const discovered=data.discovered||[];
  const available=$('#availableModel');
  const keep=available.value;
  available.innerHTML=discovered.map(name=>'<option value="'+esc(name)+'">'+esc(name)+'</option>').join('');
  if(discovered.includes(keep))available.value=keep;
  $('#addModelButton').disabled=!discovered.length;
  $('#registeredModels').innerHTML=registered.map(item=>
    '<div class="registered-model"><span><b>'+esc(item.model)+'</b><small>'+
    esc(item.available?'Ready · '+item.role:'Offline · '+item.role)+
    '</small></span><button type="button" class="remove-model" data-model="'+esc(item.model)+
    '" aria-label="Remove '+esc(item.model)+'">Remove</button></div>'
  ).join('')||'<p>No models registered. Add an installed model above.</p>';
  $('#sendButton').disabled=state.agent==='qwen'&&!state.selectedModel;
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
    $('#systemState').textContent=(data.models?.registered?.some(x=>x.available))?'Local systems ready':'Ollama unavailable';
    renderModels();renderMessages();renderAgents();renderTasks();
  }finally{state.refreshing=false;}
}
async function submit(event){event.preventDefault();const prompt=$('#prompt').value.trim();if(!prompt)return;$('#sendButton').disabled=true;try{const response=await api('/api/chat',{method:'POST',body:JSON.stringify({agent:state.agent,prompt,request_type:$('#requestType').value,model:state.selectedModel,performance:state.performance,conversation_id:state.conversationId})});localStorage.setItem('gs_conversation_id',state.conversationId);$('#prompt').value='';await refresh();toast('Task submitted — status appears below your message')}catch(error){toast(error.message)}finally{$('#sendButton').disabled=false}}

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

$$('.nav-button').forEach(x=>x.onclick=()=>setView(x.dataset.view));$$('.agent-choice').forEach(x=>x.onclick=()=>setAgent(x.dataset.agent));$('#chatForm').addEventListener('submit',submit);refresh().catch(error=>toast(error.message));
// Keep every task in this conversation observable, even after refresh or later messages.
setInterval(()=>refresh().catch(()=>{$('#systemState').textContent='Ground Space disconnected'}),2500);
