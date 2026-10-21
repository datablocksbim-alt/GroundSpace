const state={agent:'qwen',csrf:'',conversationId:localStorage.getItem('gs_conversation_id')||crypto.randomUUID(),poll:null,data:null,refreshing:false};
const $=s=>document.querySelector(s);const $$=s=>[...document.querySelectorAll(s)];
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}
async function api(path,options={}){const headers={'Content-Type':'application/json',...(options.headers||{})};if(options.method==='POST')headers['X-Ground-Space-CSRF']=state.csrf;const response=await fetch(path,{...options,headers});const body=await response.json();if(!response.ok)throw new Error(body.error||`Request failed (${response.status})`);return body}
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function setView(name){$$('.nav-button').forEach(x=>x.classList.toggle('active',x.dataset.view===name));$$('.view').forEach(x=>x.classList.toggle('active',x.id===`view-${name}`));if(name!=='chat')refresh()}
function setAgent(agent){state.agent=agent;$$('.agent-choice').forEach(x=>x.classList.toggle('active',x.dataset.agent===agent));$('#conversationTitle').textContent=agent==='qwen'?'Qwen channel':'Administrator channel';$('#permissionPill').textContent=agent==='qwen'?'READ · PROPOSE':'TASK STATUS · READ';$('#requestType').hidden=agent!=='qwen';$('#prompt').placeholder=agent==='qwen'?'Ask for an explanation…':'Try “list tasks” or “status GS-…”';renderMessages()}
function taskStatus(task){
  if(!task)return '';
  const labels={queued:'Queued — waiting for worker',claimed:'Worker assigned',running:'Generating response…',retry_pending:'Retry pending — check Tasks for details',failed:'Task failed — check Tasks for details',blocked:'Task blocked',cancelled:'Task cancelled',completed:'Completed'};
  const status=String(task.status||'queued');
  const stage=(['retry_pending','failed','blocked'].includes(status)&&task.failed_stage)?' · '+task.failed_stage:'';
  return `<small class="task-state ${esc(status)}">${esc((labels[status]||status)+stage)}</small>`;
}
function renderMessages(){
  const root=$('#messages');
  const nearBottom=(root.scrollHeight-root.scrollTop-root.clientHeight)<100;
  const messages=(state.data?.conversations?.[state.conversationId]||[]).filter(x=>!x.agent||x.agent===state.agent);
  const tasks=new Map((state.data?.tasks||[]).map(task=>[task.task_id,task]));
  const replies=new Set(messages.filter(x=>x.role==='assistant').map(x=>x.task_id));
  if(!messages.length){
    root.innerHTML=`<div class="empty-state"><span>GS / 003</span><h2>Communication, grounded.</h2><p>${state.agent==='qwen'?'Ask Qwen for an explanation, assessment, or code proposal. Requests run automatically within the agent’s allowed permissions.':'Use read-only Administrator commands: help, list tasks, or status &lt;task-id&gt;.'}</p></div>`;
    return;
  }
  const html=[];
  for(const entry of messages){
    const task=tasks.get(entry.task_id);
    const progress=entry.role==='user'?taskStatus(task):'';
    html.push(`<div class="message ${esc(entry.role)}">${esc(entry.content)}<small>${esc(entry.task_id||'local')} · ${new Date(entry.timestamp).toLocaleString()}</small>${progress}</div>`);
    // Queue completion can be visible before the history writer finishes.
    // Show the authoritative result in that case instead of losing the reply.
    if(entry.role==='user'&&task?.status==='completed'&&!replies.has(entry.task_id)&&typeof task.result?.answer==='string'&&task.result.answer){
      html.push(`<div class="message assistant">${esc(task.result.answer)}<small>${esc(entry.task_id)} · recovered from task result</small></div>`);
    }
  }
  root.innerHTML=html.join('');
  if(nearBottom)root.scrollTop=root.scrollHeight;
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
    $('#systemState').textContent=(data.agents.find(x=>x.agent_id==='qwen-proposal')?.active)?'Local systems ready':'Ollama unavailable';
    renderMessages();renderAgents();renderTasks();
  }finally{state.refreshing=false;}
}
async function submit(event){event.preventDefault();const prompt=$('#prompt').value.trim();if(!prompt)return;$('#sendButton').disabled=true;try{const response=await api('/api/chat',{method:'POST',body:JSON.stringify({agent:state.agent,prompt,request_type:$('#requestType').value,conversation_id:state.conversationId})});localStorage.setItem('gs_conversation_id',state.conversationId);$('#prompt').value='';await refresh();toast('Task submitted — status appears below your message')}catch(error){toast(error.message)}finally{$('#sendButton').disabled=false}}
$('.nav-button').forEach(x=>x.onclick=()=>setView(x.dataset.view));$$('.agent-choice').forEach(x=>x.onclick=()=>setAgent(x.dataset.agent));$('#chatForm').addEventListener('submit',submit);refresh().catch(error=>toast(error.message));
// Keep every task in this conversation observable, even after refresh or later messages.
setInterval(()=>refresh().catch(()=>{$('#systemState').textContent='Ground Space disconnected'}),2500);
