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
    const actual=await client.run(job);
    if(mode==='cancel'&&index===2){
     probe.holding=true;
     await new Promise(resolve=>{probe.releaseLate=resolve;});
    }
    return actual;
   };
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
  if(mode==='cancel'){
   await page.waitForFunction(()=>window.__directProbe.holding,
     null,{timeout:120000});
   assert.equal(await page.locator('[data-cancel]').isEnabled(),true);
   assert.match(await page.locator('[data-progress]').textContent(),
     /Applying 2 of 3 · 1 validated · 0 skipped/);
   assert.match(await page.evaluate(()=>window.__directProbe.firstProgress),
     /Applying 1 of 3 · 0 validated · 0 skipped/,
     'first owner is displayed as 1 of N while its Worker is running');
   await page.locator('[data-cancel]').click();
   await page.waitForFunction(()=>{
    const status=document.querySelector('[data-progress]')?.textContent||'';
    return status.includes('BULK STOPPED · CANCELLED')&&
      window.__directProbe.workspace.getState().revision===1;
   },null,{timeout:120000});
   await page.evaluate(()=>window.__directProbe.releaseLate());
   await page.waitForTimeout(80);
   assert.match(await page.locator('[data-progress]').textContent(),
     /BULK STOPPED · CANCELLED/);
   assert.equal((await page.evaluate(()=>
     window.__directProbe.workspace.getState())).revision,1);
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
test('cancel during direct Apply retains the last validated checkpoint and final status',
 {timeout:360000},async()=>exercise('cancel'));
