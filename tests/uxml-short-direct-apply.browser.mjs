/** Genuine Chromium + pinned Pyodide: one-click hub short Apply.
 * Synthetic XML only. Each accepted owner still calls existing native
 * export_edit_ops -> apply_edit_ops -> transaction + pre-Final validation.
 */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';

const root=path.resolve(process.cwd(),'dist');
const mime={'.html':'text/html','.mjs':'text/javascript','.js':'text/javascript',
 '.css':'text/css','.json':'application/json','.wasm':'application/wasm',
 '.py':'text/plain','.zip':'application/zip'};
const node=(n,type,ref,end,x)=>
 '<Node><NodeNumber>'+n+'</NodeNumber><ComponentType>'+type+
 '</ComponentType><ComponentRefNo>'+ref+'</ComponentRefNo><Endpoint>'+end+
 '</Endpoint><Position>'+x+' 0 0</Position><OutsideDiameter>100</OutsideDiameter>'+
 '<BendRadius>0</BendRadius><AlphaAngle>0</AlphaAngle></Node>';
function fixture(count=3){
 return '<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+
  Array.from({length:count},(_,i)=>{
   const x=i*1000,k=i*100,r=String(i);
   return '<Branch><Branchname>PUBLIC-DIRECT-'+i+'</Branchname>'+
    node(10+k,'PIPE','P'+r,1,x)+node(20+k,'PIPE','P'+r,2,x+100)+
    node(-1,'GASK','SHORT'+r,1,x+100)+node(30+k,'RIGID','SHORT'+r,2,x+103)+
    node(-1,'FLAN','F'+r,1,x+103)+node(40+k,'RIGID','F'+r,2,x+189)+
    '</Branch>';
  }).join('')+'</PipeStressExport>';
}
async function exercise(mode){
 const server=createServer(async(req,res)=>{
  try{
   const rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname)
     .replace(/^\/+/,'')||'index.html';
   const file=path.resolve(root,rel);
   if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
   res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});
   res.end(await readFile(file));
  }catch(e){res.writeHead(404).end(String(e));}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1400,height:980}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 try{
  if(mode==='publishThrow'){
   await page.route('**/tabs/topology-workspace/workspace-app.mjs',async route=>{
    const response=await route.fetch(),original=await response.text();
    const needle="      canvas.setScene(scene);sourceMeta();\n      query(root,'[data-gap-review-status]')";
    assert.equal(original.split(needle).length,2,'pin exact publish mutation location');
    const replacement="      canvas.setScene=()=>{throw Error('SYNTHETIC_PUBLISH_SET_SCENE_FAILURE');};"+
      "canvas.setScene(scene);sourceMeta();\n      query(root,'[data-gap-review-status]')";
    await route.fulfill({response,body:original.replace(needle,replacement)});
   });
  }
  await page.route('**/index.html',async route=>{
   const response=await route.fetch(),html=await response.text();
   const tag='<script type="module" src="./tabs/topology-workspace/workspace-app.mjs"></script>';
   assert.ok(html.includes(tag));
   await route.fulfill({response,body:html.replace(tag,'')});
  });
  await page.goto('http://127.0.0.1:'+server.address().port+'/index.html');
  await page.evaluate(async ({xml,mode})=>{
   const root=document.querySelector('#xml229-topology-workspace');
   const [{mountTopologyWorkspace},{createTopologyWorkerClient}]=await Promise.all([
    import('/tabs/topology-workspace/workspace-app.mjs'),
    import('/tabs/topology-workspace/topology-worker-client.mjs')]);
   const client=createTopologyWorkerClient();
   const probe={jobs:[],bulkCount:0,holding:false,releaseLate:null,
     cancelled:false,mode};
   const runEngine=async job=>{
    const bulk=!!(job.options?.generateTopoFix&&
      job.options?.topologyShortElementRequests?.length);
    if(!bulk){
     const r=await client.run(job);
     if(mode==='refreshHeld'&&probe.bulkCount===3){
      probe.refreshHolding=true;
      await new Promise(resolve=>{probe.releaseRefresh=resolve;});
     }
     return mode==='different'?{...r,topologyUxmlParity:{status:'DIFFERENT',
       differences:['/synthetic: forced distinct reader']}}:r;
    }
    probe.bulkCount++;
    const index=probe.bulkCount;
    if(index===1)probe.firstProgress=
      document.querySelector('[data-progress]')?.textContent||'';
    probe.jobs.push({index,action:job.options.topologyActionIds?.[0],
      sourceSha256:job.options.topologyShortElementRequests[0].sourceSha256});
    if(mode==='refusal'&&index===2)
     return {ok:true,outputKind:'topology-sidecars',
       acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
       topoFixCommitted:false,topoFixXmlText:'',
       topologyUxmlParity:{status:'DIFFERENT',
         differences:['/patchBack: UxmlPatchError: UXML_LOSS_CONTRACT_FIELD_TOUCH:SYNTHETIC_OWNER']}};
    if(mode==='timeout'&&index===2)
      throw Error('TOPOLOGY_WORKER_TIMEOUT: synthetic dropped Worker message');
    if(mode==='nonCommittedEqual'&&index===2)
      return {ok:true,outputKind:'topology-sidecars',
        acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
        topoFixCommitted:false,topoFixXmlText:'',
        topologyUxmlParity:{status:'EQUAL',differences:[]}};
    if(mode==='outerError'&&index===2)
      return {ok:false,error:'SYNTHETIC_SECOND_JOB_STOPPED',
        topologyUxmlParity:{status:'EQUAL',differences:[]}};
    const actual=await client.run(job);
    if((mode==='lineageDrift'||mode==='validationDrift')&&index===2){
      const forged=structuredClone(actual);
      if(mode==='lineageDrift'){
        const lineage=JSON.parse(forged.topoFixLineageText);
        lineage.fixedXmlSha256='SYNTHETIC_FORGED_LINEAGE';
        forged.topoFixLineageText=JSON.stringify(lineage);
      }else{
        const validation=JSON.parse(forged.topoFixValidationText);
        validation.summary.blockingFailureCount=1;
        forged.topoFixValidationText=JSON.stringify(validation);
      }
      return forged;
    }
    if(mode==='receiptDrift'&&index===2){
      // A forged canonical witness on an otherwise EQUAL native result must
      // invalidate hub parity, not merely stop this one item.
      const forged=structuredClone(actual);
      forged.topologyUxmlAppliedEditOps[0].fileSha256='FORGED_SOURCE_SHA';
      return forged;
    }
    if((mode==='cancel'&&index===2)||
       (mode==='cancelBeforeCheckpoint'&&index===1)){
     probe.holding=true;
     await new Promise(resolve=>{probe.releaseLate=resolve;});
    }
    return actual;
   };
   if(mode==='outerError'){
     runEngine.beginBulkSession=()=>{};
     runEngine.endBulkSession=()=>{
       throw Error('SYNTHETIC_BULK_SESSION_RELEASE_FAILED');
     };
   }
   probe.client=client;
   probe.workspace=mountTopologyWorkspace(root,{
     runEngine,cancelEngine:()=>{probe.cancelled=true;client.cancel();}});
   window.__directProbe=probe;
   await probe.workspace.load(new File([xml],'public-direct-apply.xml',
     {type:'text/xml'}));
  },{xml:fixture(),mode});
  await page.locator('[data-uxml-toggle]').check();
  await page.evaluate(()=>window.__directProbe.workspace.analyze());
  await page.waitForFunction(()=>
   ['EQUAL','DIFFERENT'].includes(window.__directProbe.workspace.getState().hubParity),
   null,{timeout:120000});
  if(mode==='different'){
   assert.equal((await page.evaluate(()=>window.__directProbe.workspace.getState())).hubParity,
     'DIFFERENT');
   assert.equal(await page.locator('[data-select-short]').isDisabled(),true);
   assert.equal(await page.locator('[data-run-short-drop]').count(),0);
   assert.equal(await page.evaluate(()=>window.__directProbe.bulkCount),0);
   return;
  }
  assert.equal(await page.locator('[data-select-short]').isEnabled(),true);
  await page.locator('[data-select-short]').click();
  await page.locator('[data-select-gaskets]').click();
  assert.equal(await page.locator('[data-short-index]:checked').count(),3);
  assert.equal(await page.locator('[data-short-hub-preview]').count(),0);
  assert.equal(await page.locator('[data-run-short-drop]').isEnabled(),true,
    'hub Apply requires current analysis and EQUAL but no short preview');
  await page.locator('[data-run-short-drop]').click();
  if(mode==='cancel'||mode==='cancelBeforeCheckpoint'){
   await page.waitForFunction(()=>window.__directProbe.holding,
     null,{timeout:120000});
   assert.equal(await page.locator('[data-cancel]').isEnabled(),true);
   assert.match(await page.locator('[data-progress]').textContent(),
     mode==='cancel'?/Applying 2 of 3 · 1 validated · 0 skipped/:
       /Applying 1 of 3 · 0 validated · 0 skipped/);
   assert.match(await page.evaluate(()=>window.__directProbe.firstProgress),
     /Applying 1 of 3 · 0 validated · 0 skipped/,
     'first owner is displayed as 1 of N while its Worker is running');
   await page.locator('[data-cancel]').click();
   await page.waitForFunction(mode=>{
    const status=document.querySelector('[data-progress]')?.textContent||'';
    const checkpoint=mode==='cancel'?1:0;
    return (mode==='cancel'?status.includes('BULK STOPPED · CANCELLED'):
      status.includes('CANCELLED · working revision 0 retained'))&&
      window.__directProbe.workspace.getState().revision===checkpoint;
   },mode,{timeout:120000});
   await page.evaluate(()=>window.__directProbe.releaseLate());
   await page.waitForTimeout(80);
   assert.match(await page.locator('[data-progress]').textContent(),
     mode==='cancel'?/BULK STOPPED · CANCELLED/:
       /CANCELLED · working revision 0 retained/);
   const current=await page.evaluate(()=>window.__directProbe.workspace.getState());
   assert.equal(current.revision,mode==='cancel'?1:0);
   assert.equal(current.busy,false);
   if(mode==='cancelBeforeCheckpoint')
     assert.equal(await page.locator('[data-run-short-drop]').count(),0,
       'first-item Cancel must clear the stale pending selection');
  }else if(['receiptDrift','lineageDrift','validationDrift',
             'timeout','nonCommittedEqual','outerError'].includes(mode)){
   const expected={
    receiptDrift:'UXML_SHORT_APPLY_CANONICAL_OP_RECEIPT_MISSING_OR_DRIFT',
    lineageDrift:'SHORT_BULK_SOURCE_LINEAGE_OR_RECHECK_DRIFT',
    validationDrift:'SHORT_BULK_SOURCE_LINEAGE_OR_RECHECK_DRIFT',
    timeout:'TOPOLOGY_WORKER_TIMEOUT',
    nonCommittedEqual:'SHORT_BULK_TRANSACTION_REJECTED',
    outerError:'SYNTHETIC_BULK_SESSION_RELEASE_FAILED',
   }[mode];
   await page.waitForFunction(({expected,mode})=>{
    const status=document.querySelector('[data-progress]')?.textContent||'';
    const state=window.__directProbe.workspace.getState();
    return status.includes(mode==='outerError'?'BULK STOPPED · ERROR':
      'BULK STOPPED · TRANSACTION_FAILED')&&
      status.includes(expected)&&state.hubParity==='DIFFERENT'&&
      state.revision===1&&!state.busy;
   },{expected,mode},{timeout:180000});
   assert.equal(await page.locator('[data-download-working]').isDisabled(),true,
     'canonical witness drift revokes hub parity and corrected downloads');
   assert.equal(await page.locator('[data-download-fix]').count(),0);
   assert.equal(await page.evaluate(()=>window.__directProbe.bulkCount),2);
   const heldStatus=await page.locator('[data-progress]').textContent();
   assert.match(heldStatus,/corrected downloads HELD/);
   assert.doesNotMatch(heldStatus,/Previewing|Cancel available|downloadable/);
  }else{
   await page.waitForFunction(expected=>{
     const text=document.querySelector('[data-progress]')?.textContent||'';
     const state=window.__directProbe.workspace.getState();
     return text.includes('BULK COMPLETE')&&state.revision===expected&&!state.busy;
   },mode==='refusal'?2:3,{timeout:180000});
   const text=await page.locator('[data-progress]').textContent();
   assert.match(text,/BULK COMPLETE/);
   assert.doesNotMatch(text,/Previewing|Cancel available|read-only preview/);
   assert.equal(await page.locator('[data-short-hub-preview]').count(),0);
   const details=page.locator('[data-short-bulk-operations]');
   assert.equal(await details.count(),1,
     'post-Apply audit disclosure must remain independently accessible');
   await details.locator('summary').click();
   const audit=await details.textContent();
   assert.match(audit,/removedWithRecord/);
   if(mode==='refusal'){
     assert.match(audit,/UXML_LOSS_CONTRACT_FIELD_TOUCH:SYNTHETIC_OWNER/);
     assert.match(text,/2 validated \+ 1 skipped/);
     assert.equal((await page.evaluate(()=>window.__directProbe.bulkCount)),3);
   }else{
     assert.match(text,/3 validated \+ 0 skipped/);
     assert.equal((await page.evaluate(()=>window.__directProbe.bulkCount)),3);
   }
  }
  assert.deepEqual(errors,[]);
  console.log('SYNTHETIC_DIRECT_SHORT_APPLY_BROWSER '+JSON.stringify({
   mode,transactions:await page.evaluate(()=>window.__directProbe.bulkCount),
   revision:(await page.evaluate(()=>window.__directProbe.workspace.getState())).revision,
   progress:await page.locator('[data-progress]').textContent(),pageErrors:errors}));
 }finally{
  await page.close();await browser.close();await new Promise(done=>server.close(done));
 }
}
test('hub direct Apply without separate UXML short preview validates all three',
 {timeout:360000},async()=>exercise('success'));
test('named canonical loss refusal skips one owner, retains only validated revisions',
 {timeout:360000},async()=>exercise('refusal'));
test('hub parity DIFFERENT blocks short-element direct Apply',
 {timeout:180000},async()=>exercise('different'));
test('canonical receipt drift revokes parity after one validated checkpoint',
 {timeout:360000},async()=>exercise('receiptDrift'));
test('hub lineage drift at item two HOLDS last validated checkpoint and download',
 {timeout:360000},async()=>exercise('lineageDrift'));
test('hub validation drift at item two HOLDS last validated checkpoint and download',
 {timeout:360000},async()=>exercise('validationDrift'));
test('hub Worker timeout at item two HOLDS last validated checkpoint and download',
 {timeout:360000},async()=>exercise('timeout'));
test('hub non-committed EQUAL at item two HOLDS last validated checkpoint and download',
 {timeout:360000},async()=>exercise('nonCommittedEqual'));
test('hub outer-catch ERROR after item two HOLDS last validated checkpoint and download',
 {timeout:360000},async()=>exercise('outerError'));
test('Cancel before first item retains original revision zero',
 {timeout:360000},async()=>exercise('cancelBeforeCheckpoint'));
test('cancel during direct Apply retains the last validated checkpoint and final status',
 {timeout:360000},async()=>exercise('cancel'));
