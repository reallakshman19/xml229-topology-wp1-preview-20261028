/** A6b real workspace UI group-vs-serial; public synthetic, real Chromium/Pyodide. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';

const root=path.resolve(process.cwd(),'dist');
const mime={'.html':'text/html','.mjs':'text/javascript','.js':'text/javascript',
  '.css':'text/css','.wasm':'application/wasm','.json':'application/json','.py':'text/plain'};
const node=(n,type,ref,end,x)=>'<Node><NodeNumber>'+n+'</NodeNumber>'+
  '<ComponentType>'+type+'</ComponentType><ComponentRefNo>'+ref+
  '</ComponentRefNo><Endpoint>'+end+'</Endpoint><Position>'+x+
  ' 0 0</Position><OutsideDiameter>100</OutsideDiameter>'+
  '<BendRadius>0</BendRadius><AlphaAngle>0</AlphaAngle></Node>';
function fixture(count){
 return '<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+
  Array.from({length:count},(_,i)=>{
   const x=i*1500,k=i*100,r=String(i);
   return '<Branch><Branchname>A6B-UI-SYNTHETIC-'+i+'</Branchname>'+
    node(10+k,'PIPE','P'+r,1,x)+node(20+k,'PIPE','P'+r,2,x+100)+
    node(-1,'GASK','SHORT'+r,1,x+100)+node(30+k,'RIGID','SHORT'+r,2,x+103)+
    node(-1,'FLAN','F'+r,1,x+103)+node(40+k,'RIGID','F'+r,2,x+189)+'</Branch>';
  }).join('')+'</PipeStressExport>';
}
const server=createServer(async(req,res)=>{
 try{
  const rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname)
    .replace(/^\/+/,'')||'index.html',file=path.resolve(root,rel);
  if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
  res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});
  res.end(await readFile(file));
 }catch(e){res.writeHead(404).end(String(e));}
});
let browser;
test.before(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 browser=await chromium.launch({headless:true,args:['--no-sandbox']});
});
test.after(async()=>{
 await browser?.close();
 await new Promise(resolve=>server.close(resolve));
});

const mutationPatches={
 toggleIgnored:["enableIndependentGroups:state.independentShortGroups","enableIndependentGroups:false"],
 ownerEvidenceDropped:["ownerEvidence:pass.ownerEvidence||null","ownerEvidence:null"],
 releaseLastBypassed:["      state.revision+=applied.length;","      state.revision+=applied.length;state.hubRevision=state.revision;"],
 cancelStaleAllowed:["query(root,'[data-short-preview]').textContent='';state.epoch++;state.busy=false;state.batchRunning=false;",
   "query(root,'[data-short-preview]').textContent='';state.busy=false;state.batchRunning=false;"],
};
async function scenario({count=5,hub=false,group=true,mode='normal',mutation=null}={}){
 const page=await browser.newPage({viewport:{width:1400,height:960},acceptDownloads:true});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const url='http://127.0.0.1:'+server.address().port+'/index.html';
 try{
  await page.route('**/index.html',async route=>{
   const response=await route.fetch(),html=await response.text();
   const tag='<script type="module" src="./tabs/topology-workspace/workspace-app.mjs"></script>';
   assert.ok(html.includes(tag),'must avoid mounting an unused second Worker');
   await route.fulfill({response,body:html.replace(tag,'')});
  });
  if(mutation){
   const [before,after]=mutationPatches[mutation];
   await page.route('**/tabs/topology-workspace/workspace-app.mjs',async route=>{
    const response=await route.fetch(),source=await response.text();
    assert.equal(source.split(before).length,2,mutation+' exact injection point');
    await route.fulfill({response,body:source.replace(before,after)});
   });
  }
  await page.goto(url);
  await page.evaluate(async ({xml,mode})=>{
   const root=document.querySelector('#xml229-topology-workspace');
   root.id='a6b-ui-unmounted';
   const [{mountTopologyWorkspace},{createTopologyWorkerClient}]=await Promise.all([
    import('/tabs/topology-workspace/workspace-app.mjs'),
    import('/tabs/topology-workspace/topology-worker-client.mjs')]);
   root.id='xml229-topology-workspace';
   const client=createTopologyWorkerClient();
   const probe={jobs:[],holding:false,release:null};
   const runEngine=async job=>{
    const active=job.options?.generateTopoFix===true;
    const isBatch=job.options?.topologyShortBatchExplicit===true;
    if(active)probe.jobs.push({isBatch,ids:job.options.topologyActionIds});
    if(mode==='forcedRefusal'&&active){
     if(isBatch){
      const code='SHORT_BATCH_VALIDATION_REJECTED';
      return {ok:true,outputKind:'topology-sidecars',acceptedFinalTransferred:false,
       nativeCiiReleaseAuthorized:false,topoFixCommitted:false,topoFixXmlText:'',
       topologyUxmlParity:{status:'DIFFERENT',differences:['/batch:'+code]},
       topologySummary:{rejectReasons:[code]}};
     }
     return {ok:true,outputKind:'topology-sidecars',acceptedFinalTransferred:false,
      nativeCiiReleaseAuthorized:false,topoFixCommitted:false,topoFixXmlText:'',
      topologyUxmlParity:{status:'DIFFERENT',
       differences:['/patchBack: UxmlPatchError: UXML_LOSS_CONTRACT_FIELD_TOUCH:SYNTHETIC_OWNER']}};
    }
    const result=await client.run(job);
    if((mode==='cancel'||mode==='cancelMutant')&&isBatch){
     probe.holding=true;
     await new Promise(resolve=>{probe.release=resolve;});
    }
    if(mode==='releaseHold'&&!active&&probe.jobs.some(x=>x.isBatch)){
     probe.holding=true;
     await new Promise(resolve=>{probe.release=resolve;});
    }
    return result;
   };
   probe.client=client;
   probe.workspace=mountTopologyWorkspace(root,{
    runEngine,cancelEngine:()=>client.cancel()});
   window.__a6bUi=probe;
   await probe.workspace.load(new File([xml],'public-a6b-ui.xml',
    {type:'text/xml'}));
  },{xml:fixture(count),mode});
  if(hub)await page.locator('[data-uxml-toggle]').check();
  await page.evaluate(()=>window.__a6bUi.workspace.analyze());
  await page.waitForFunction(hub=>
    !window.__a6bUi.workspace.getState().busy&&
    window.__a6bUi.workspace.getState().hubParity===(hub?'EQUAL':'OFF')&&
    window.__a6bUi.workspace.getState().actions>=0,
    hub,{timeout:180000});
  await page.locator('[data-select-short]').click();
  const toggle=page.locator('[data-short-independent]');
  assert.equal(await toggle.count(),1);
  if(group)await toggle.check();else await toggle.uncheck();
  const checked=await page.evaluate(()=>
    window.__a6bUi.workspace.getState().independentShortGroups);
  assert.equal(checked,group,'real visible comparison control must govern mode');
  await page.locator('[data-select-gaskets]').click();
  assert.equal(await page.locator('[data-short-index]:checked').count(),Math.min(count,24));
  const selectedText=await page.locator('[data-short-selection-count]').textContent();
  assert.match(selectedText,new RegExp(count+' selected'));
  const started=Date.now();
  await page.locator('[data-run-short-drop]').click();
  if(mode==='cancel'||mode==='cancelMutant'){
   await page.waitForFunction(()=>window.__a6bUi.holding,null,{timeout:180000});
   assert.equal(await page.evaluate(()=>window.__a6bUi.workspace.getState().revision),0);
   await page.locator('[data-cancel]').click();
   const held=await page.evaluate(()=>window.__a6bUi.workspace.getState());
   assert.equal(held.revision,0);
   assert.equal(held.hubRevision,null);
   await page.evaluate(()=>window.__a6bUi.release());
   await page.waitForTimeout(200);
   const after=await page.evaluate(()=>window.__a6bUi.workspace.getState());
   return {mode,revision:after.revision,hubRevision:after.hubRevision,
     text:await page.locator('[data-progress]').textContent(),jobs:
       await page.evaluate(()=>window.__a6bUi.jobs),errors};
  }
  if(mode==='releaseHold'){
   await page.waitForFunction(()=>window.__a6bUi.holding,null,{timeout:180000});
   const during=await page.evaluate(()=>window.__a6bUi.workspace.getState());
   const disabled=await page.locator('[data-download-working]').isDisabled();
   await page.evaluate(()=>window.__a6bUi.release());
   await page.waitForFunction(()=>
    !window.__a6bUi.workspace.getState().shortBulkFinalizing,
    null,{timeout:180000});
   return {mode,revDuring:during.revision,hubRevisionDuring:during.hubRevision,
     downloadDisabledDuring:disabled,errors};
  }
  await page.waitForFunction(n=>{
   const state=window.__a6bUi.workspace.getState();
   const text=document.querySelector('[data-progress]')?.textContent||'';
   return (!state.busy&&!state.shortBulkFinalizing&&!state.activeJob)&&
     (text.includes('BULK COMPLETE')||text.includes('BULK STOPPED'));
  },count,{timeout:300000});
  const status=await page.evaluate(()=>window.__a6bUi.workspace.getState());
  const message=await page.locator('[data-progress]').textContent();
  const jobs=await page.evaluate(()=>window.__a6bUi.jobs);
  const elapsedMs=Date.now()-started;
  if(mode==='forcedRefusal'){
   return {mode,hub,group,count,status,message,jobs,elapsedMs,errors};
  }
  assert.match(message,/BULK COMPLETE/,'workspace must finish: '+message);
  assert.ok(group?jobs.some(j=>j.isBatch):jobs.every(j=>!j.isBatch),
    'GROUP_TOGGLE_ENGINE_DISPATCH_MISMATCH');
  assert.equal(status.revision,count,'one history revision for every owner');
  assert.equal(status.historyOwnerEvidenceCount,group?count:0,
    'GROUP_OWNER_EVIDENCE_HISTORY_CENSUS');
  assert.equal(status.hubRevision,hub?count:null);
  assert.equal(await page.locator('[data-download-working]').isEnabled(),true);
  const pending=page.waitForEvent('download');
  await page.locator('[data-download-working]').click();
  const download=await pending;
  const bytes=await readFile(await download.path());
  return {mode,hub,group,count,status,message,jobs,elapsedMs,
    xml:bytes.toString('utf8'),errors};
 }finally{
  await page.evaluate(()=>{
   window.__a6bUi?.workspace?.dispose();
   window.__a6bUi?.client?.dispose();
  }).catch(()=>{});
  await page.close();
 }
}

test('real workspace grouped 5 and 20 owners equals serial downloaded bytes, direct and UXML',
 {timeout:1800000},async()=>{
 for(const n of [5,20]){
  for(const hub of [false,true]){
   const grouped=await scenario({count:n,hub,group:true});
   const serial=await scenario({count:n,hub,group:false});
   assert.equal(grouped.xml,serial.xml,'XML EXACT BYTES '+n+'/'+hub);
   assert.ok(grouped.jobs.some(j=>j.isBatch),
     'ON toggle must reach actual explicit batch stage');
   assert.ok(serial.jobs.every(j=>!j.isBatch),
     'OFF toggle must keep unchanged serial one-owner route');
   assert.equal(grouped.status.historyOwnerEvidenceCount,n);
   assert.deepEqual(grouped.errors,[]);
   assert.deepEqual(serial.errors,[]);
   console.info('A6B_REAL_WORKSPACE_UI_TIMING='+JSON.stringify({
    n,route:hub?'UXML':'DIRECT',
    groupMs:grouped.elapsedMs,serialMs:serial.elapsedMs,
    groupTransactions:grouped.jobs.filter(j=>j.isBatch).length,
    serialTransactions:serial.jobs.length,bytesEqual:true,
    ownerHistoryEvidence:n}));
  }
 }
 console.info('A6B_UI_MUTANT_GREEN:toggle-selects-actual-batch-and-owner-evidence=PASS');
});
test('real workspace mid-group Cancel discards only in-flight group',
 {timeout:300000},async()=>{
 const x=await scenario({count:5,hub:true,mode:'cancel'});
 assert.equal(x.revision,0);assert.equal(x.hubRevision,null);
 assert.equal(x.jobs.length,1);assert.equal(x.jobs[0].isBatch,true);
 assert.deepEqual(x.errors,[]);
 console.info('A6B_UI_MUTANT_GREEN:cancel-inflight-group-never-published=PASS');
});
test('real workspace group refusal bisects to exactly named singleton refusal',
 {timeout:300000},async()=>{
 const x=await scenario({count:5,hub:true,mode:'forcedRefusal'});
 assert.match(x.message,/BULK COMPLETE/);
 assert.equal(x.status.revision,0);
 assert.equal(x.status.historyOwnerEvidenceCount,0);
 assert.equal(x.jobs.filter(j=>j.isBatch).length>=2,true);
 assert.equal(x.jobs.filter(j=>!j.isBatch).length,5);
 assert.match(x.message,/5 skipped/);
 assert.deepEqual(x.errors,[]);
 console.info('A6B_UI_MUTANT_GREEN:real-workspace-bisect-named-refusal=PASS');
});
test('real workspace release-last stays closed during a blocked evidence recheck',
 {timeout:300000},async()=>{
 const x=await scenario({count:5,hub:true,mode:'releaseHold'});
 assert.equal(x.revDuring,5);
 assert.equal(x.hubRevisionDuring,null);
 assert.equal(x.downloadDisabledDuring,true);
 assert.deepEqual(x.errors,[]);
 console.info('A6B_UI_MUTANT_GREEN:hub-revision-release-last=PASS');
});
for(const [name,config,verify,needle] of [
 ['toggleIgnored',{count:5,hub:true,group:true,mutation:'toggleIgnored'},
   x=>assert.ok(x.jobs.some(j=>j.isBatch),'GROUP_TOGGLE_ENGINE_DISPATCH_MISMATCH'),
   'GROUP_TOGGLE_ENGINE_DISPATCH_MISMATCH'],
 ['ownerEvidenceDropped',{count:5,hub:true,group:true,mutation:'ownerEvidenceDropped'},
   x=>assert.equal(x.status.historyOwnerEvidenceCount,5,
     'GROUP_OWNER_EVIDENCE_HISTORY_CENSUS'),'GROUP_OWNER_EVIDENCE_HISTORY_CENSUS'],
 ['releaseLastBypassed',{count:5,hub:true,mode:'releaseHold',mutation:'releaseLastBypassed'},
   x=>assert.equal(x.hubRevisionDuring,null,'GROUP_RELEASE_LAST_BYPASSED'),
   'GROUP_RELEASE_LAST_BYPASSED'],
 ['cancelStaleAllowed',{count:5,hub:true,mode:'cancelMutant',mutation:'cancelStaleAllowed'},
   x=>assert.equal(x.revision,0,'GROUP_CANCEL_PUBLISHED_IN_FLIGHT'),
   'GROUP_CANCEL_PUBLISHED_IN_FLIGHT'],
]){
 test('KILL actual workspace UI source mutant '+name,{timeout:360000},async()=>{
  let red;
  try{const x=await scenario(config);verify(x);}
  catch(error){red=error;}
  assert.ok(red instanceof Error,name+' must cause assertion failure');
  assert.equal(red.name,'AssertionError',name+' must be killed by a clean assertion');
  assert.match(red.message,new RegExp(needle),name+' must die on the specifically mutated authority');
  console.info('A6B_UI_MUTANT_RED:'+name+':AssertionError:'+needle);
 });
}
