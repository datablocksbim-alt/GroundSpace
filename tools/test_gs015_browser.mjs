// Real browser click-through smoke test for Ground Space UI flows.
// npm install --no-save playwright && npx playwright install chromium
// node tools/test_gs015_browser.mjs
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {chromium} from 'playwright';

const ROOT = resolve(import.meta.dirname, '..');
const registered = [{model:'qwen2.5-coder:3b',available:true,label:'Qwen',role:'proposal-only'}];
const discovered = ['granite4:3b'];
const projects = [];
const groups = [];
const conversations = {};
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
  tasks:[],
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
        registered.push({model:body.model,available:true,label:body.model,role:'proposal-only'});
        return json(res,201,bootstrap().models);
      }
      if(path==='/api/groups/create'){
        if(!body.name||!body.models?.length)return json(res,400,{error:'Choose between 1 and 6 local AI models'});
        const group={id:'group-'+(groups.length+1),name:body.name,models:body.models,
          project_id:body.project_id,conversation_id:'room-'+(groups.length+1)};
        groups.push(group);return json(res,201,group);
      }
      if(path==='/api/chat'){
        const id=body.conversation_id||'chat';
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
  browser=await chromium.launch({headless:true});
  for(const viewport of [{width:390,height:844,mobile:true},{width:1280,height:800,mobile:false}]){
    const label=viewport.mobile?'mobile':'desktop';
    registered.splice(0,registered.length,{model:'qwen2.5-coder:3b',available:true,label:'Qwen',role:'proposal-only'});
    discovered.splice(0,discovered.length,'granite4:3b');
    const context=await browser.newContext({viewport:{width:viewport.width,height:viewport.height},isMobile:viewport.mobile,hasTouch:viewport.mobile});
    const page=await context.newPage();
    const exceptions=[];
    page.on('pageerror',error=>exceptions.push(error.message));
    await page.goto(url,{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('#systemState')?.textContent==='Local systems ready');
    assert.equal(exceptions.length,0,label+' startup errors: '+exceptions.join(', '));

    // Navigation is the previously broken startup handler.
    await page.locator('.nav-button[data-view="agents"]').click();
    assert.equal(await page.locator('#view-agents').evaluate(el=>el.classList.contains('active')),true,label+' Agents click');

    // Reaching a disabled control must explain the exact reason rather than appearing broken.
    assert.equal(await page.locator('#addModelButton').isEnabled(),true,label+' installed model available');
    await page.locator('#addModelButton').click();
    await page.waitForFunction(()=>document.querySelector('#registeredModels')?.textContent.includes('granite4:3b'));
    assert.equal(await page.locator('#addModelButton').isEnabled(),false,label+' no undiscovered models');
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
    await page.locator('#saveGroup').click();
    await page.locator('#groupDialog').waitFor({state:'hidden'});
    await page.waitForFunction(name=>
      document.querySelector('#conversationTitle')?.textContent===name,
      label+' Review');
    assert.equal(exceptions.length,0,label+' group error: '+exceptions.join(', '));
    if(viewport.mobile){
      assert.equal(await page.locator('#mobileRailBackdrop').isVisible(),false,'Drawer must close after group selection');
      const availableHeight=await page.locator('#messages').evaluate(el=>el.getBoundingClientRect().height);
      assert.ok(availableHeight>150,'Chat messages should retain usable viewport height; observed '+availableHeight);
      await page.locator('#mobileOptionsToggle').click();
      assert.equal(await page.locator('#chatOptions').isVisible(),true,'Model options toggle');
    }
    console.log('PASS: '+label+' buttons, project browser/save/rejection, local AI model import, group creation, and chat layout');
    await context.close();
  }
} finally{
  if(browser)await browser.close();
  await new Promise(ok=>server.close(ok));
}
