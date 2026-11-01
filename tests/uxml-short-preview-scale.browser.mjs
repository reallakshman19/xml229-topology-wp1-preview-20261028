/** Real Chromium + pinned Worker: a SINGLE source-bound preview job emits
 * four-owner progress and ETA; cancellation invalidates the partial evidence,
 * the next attempt starts a new Worker and requalifies the exact source.
 * Public synthetic source only. No native engine/policy test hooks.
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
const syntheticXML='<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+
 Array.from({length:5},(_,i)=>{
  const x=i*1000,k=i*100,ref=String(i);
  return '<Branch><Branchname>PUBLIC-SYNTH-'+i+'</Branchname>'+
   node(10+k,'PIPE','P'+ref,1,x)+node(20+k,'PIPE','P'+ref,2,x+100)+
   node(-1,'GASK','SHORT'+ref,1,x+100)+node(30+k,'RIGID','SHORT'+ref,2,x+103)+
   node(-1,'FLAN','F'+ref,1,x+103)+node(40+k,'RIGID','F'+ref,2,x+189)+
   '</Branch>';
 }).join('')+'</PipeStressExport>';

test('one real Worker preview session: ETA, Cancel then restarted Worker re-preview',
 {timeout:360000},async()=>{
  const server=createServer(async(req,res)=>{
    try{
      const rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname)
        .replace(/^\/+/, '')||'index.html';
      const file=path.resolve(root,rel);
      if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
      res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});
      res.end(await readFile(file));
    }catch(error){res.writeHead(404).end(String(error));}
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
    await page.evaluate(async xml=>{
      const root=document.querySelector('#xml229-topology-workspace');
      const [{mountTopologyWorkspace},{createTopologyWorkerClient}]=await Promise.all([
        import('/tabs/topology-workspace/workspace-app.mjs'),
        import('/tabs/topology-workspace/topology-worker-client.mjs')]);
      const fixture={previewJobs:[],progress:[],workerCount:0,
        holdSecond:true,holding:false,releaseLate:null,lateDelivered:false};
      const NativeWorker=window.Worker;
      class CountedWorker extends NativeWorker{
        constructor(...args){super(...args);fixture.workerCount++;}
      }
      const client=createTopologyWorkerClient({WorkerCtor:CountedWorker});
      const runEngine=async (job,{onProgress}={})=>{
        const part=job.options?.topologyShortPreviewRequests||[];
        if(part.length)fixture.previewJobs.push(part.length);
        const result=await client.run(job,{onProgress:(completed,total)=>{
          onProgress?.(completed,total);
          fixture.progress.push({completed,total,
            status:document.querySelector('[data-short-hub-status]')?.textContent||''});
        }});
        // Hold the second completed Worker result only in this injected
        // synthetic harness. Cancel must discard it and force Worker restart.
        if(part.length&&fixture.holdSecond&&fixture.previewJobs.length===2){
          fixture.holding=true;
          await new Promise(resolve=>{
            // Deliver a VALID late RESULT even after Cancel. This must fail
            // when previewToken is removed from the workspace current() guard.
            fixture.releaseLate=()=>{fixture.lateDelivered=true;fixture.holding=false;resolve();};
          });
        }
        return result;
      };
      const cancelEngine=()=>client.cancel();
      fixture.client=client;
      fixture.workspace=mountTopologyWorkspace(root,{runEngine,cancelEngine});
      window.__scaleFixture=fixture;
      await fixture.workspace.load(new File([xml],'public-synthetic-five.xml',
        {type:'text/xml'}));
    },syntheticXML);
    await page.locator('[data-uxml-toggle]').check();
    await page.evaluate(()=>window.__scaleFixture.workspace.analyze());
    await page.waitForFunction(()=>
      window.__scaleFixture.workspace.getState().hubParity==='EQUAL',null,
      {timeout:120000});
    await page.locator('[data-preview-short]').click();
    await page.locator('[data-select-gaskets]').click();
    assert.equal(await page.locator('[data-short-index]:checked').count(),5);
    await page.locator('[data-short-hub-preview]').click();
    await page.waitForFunction(()=>document.querySelector('[data-short-hub-status]')
      ?.textContent?.includes('5 ready / 0 refused'),null,{timeout:120000});
    const first=await page.evaluate(()=>({
      sizes:window.__scaleFixture.previewJobs,
      progress:window.__scaleFixture.progress,
      workerCount:window.__scaleFixture.workerCount}));
    assert.deepEqual(first.sizes,[5],
      'one Worker preview job per full selection, never one analysis per four');
    assert.deepEqual(first.progress.map(p=>[p.completed,p.total]),[[4,5],[5,5]]);
    assert.match(first.progress[0].status,/Previewing 4 of 5/);
    assert.match(first.progress[0].status,/Estimated time remaining: ~/);
    assert.ok(first.workerCount>=1);
    assert.equal(await page.locator('[data-run-short-drop]').isEnabled(),true);
    assert.equal(await page.locator('[data-ops-rows] [data-op-id]')
      .filter({hasText:'Drop selected short component'}).count(),5);
    assert.equal(await page.locator('[data-download-working]').isDisabled(),true);

    // Revocation by source-bound selection change must hold until new analysis.
    await page.locator('[data-short-index="0"]').uncheck();
    await page.locator('[data-short-index="0"]').check();
    assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true);
    await page.locator('[data-short-hub-preview]').click();
    await page.waitForFunction(()=>window.__scaleFixture.holding===true,null,
      {timeout:120000});
    assert.deepEqual(await page.evaluate(()=>window.__scaleFixture.previewJobs),[5,5]);
    assert.equal(await page.locator('[data-cancel]').isEnabled(),true);
    assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true);
    assert.match(await page.locator('[data-short-hub-preview]').getAttribute('title'),
      /Finish or cancel the active preview first/);
    await page.locator('[data-cancel]').click();
    await page.waitForFunction(()=>document.querySelector('main')
      ?.getAttribute('aria-busy')==='false',null,{timeout:15000});
    assert.match(await page.locator('[data-short-hub-status]').textContent(),/CANCELLED/);
    assert.equal(await page.locator('[data-short-index]:checked').count(),5);
    assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true);
    assert.equal(await page.locator('[data-download-working]').isDisabled(),true);
    await page.evaluate(()=>window.__scaleFixture.releaseLate());
    await page.waitForTimeout(120);
    assert.equal(await page.evaluate(()=>window.__scaleFixture.lateDelivered),true);
    assert.match(await page.locator('[data-short-hub-status]').textContent(),/CANCELLED/,
      'late valid RESULT must not overwrite a cancelled preview');
    assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true,
      'late valid RESULT cannot resurrect Apply after Cancel');

    // After hard Worker termination, re-preview must spawn a NEW Worker and
    // independently requalify pinned reader/parity and every native owner.
    await page.locator('[data-short-hub-preview]').click();
    await page.waitForFunction(()=>document.querySelector('[data-short-hub-status]')
      ?.textContent?.includes('5 ready / 0 refused'),null,{timeout:120000});
    const final=await page.evaluate(()=>({
      previewJobs:window.__scaleFixture.previewJobs,
      workerCount:window.__scaleFixture.workerCount,
      revision:window.__scaleFixture.workspace.getState().revision,
      progress:window.__scaleFixture.progress}));
    assert.deepEqual(final.previewJobs,[5,5,5]);
    assert.ok(final.workerCount>first.workerCount,
      'cancel terminates Worker, retry creates and verifies a fresh instance');
    assert.equal(final.revision,0,'read-only preview never advances revision');
    assert.equal(await page.locator('[data-run-short-drop]').isEnabled(),true);
    assert.equal(await page.locator('[data-download-working]').isDisabled(),true);
    assert.deepEqual(errors,[]);
    console.log('SYNTHETIC_SINGLE_PREVIEW_WORKER_RESTART_PASS '+JSON.stringify({
      selected:5,jobSizes:final.previewJobs,progressEvents:final.progress.length,
      freshWorkerAfterCancel:true,revision:final.revision,pageErrors:errors}));
  }finally{
    await page.close();await browser.close();await new Promise(done=>server.close(done));
  }
});


test('loading a new file retires preview state; later short-bulk Cancel publishes CANCELLED',
 {timeout:360000},async()=>{
  const server=createServer(async(req,res)=>{
    try{
      const rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname)
        .replace(/^\/+/,'')||'index.html';
      const file=path.resolve(root,rel);
      if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
      res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});
      res.end(await readFile(file));
    }catch(error){res.writeHead(404).end(String(error));}
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
    await page.evaluate(async xml=>{
      const root=document.querySelector('#xml229-topology-workspace');
      const [{mountTopologyWorkspace},{createTopologyWorkerClient}]=await Promise.all([
        import('/tabs/topology-workspace/workspace-app.mjs'),
        import('/tabs/topology-workspace/topology-worker-client.mjs')]);
      const client=createTopologyWorkerClient();
      const fixture={holdPreview:false,previewHeld:false,releasePreview:null,
        bulkCalls:0,bulkHolding:false,releaseBulk:null,staleDelivered:false};
      const runEngine=async (job,opts={})=>{
        const short=job.options?.topologyShortPreviewRequests||[];
        if(short.length&&fixture.holdPreview){
          const valid=await client.run(job,opts);
          fixture.previewHeld=true;
          await new Promise(resolve=>{
            fixture.releasePreview=()=>{fixture.staleDelivered=true;resolve();};
          });
          return valid;
        }
        if(job.options?.generateTopoFix&&job.options?.topologyShortElementRequests?.length){
          fixture.bulkCalls++;
          if(fixture.bulkCalls===2){
            fixture.bulkHolding=true;
            // Leave item two in flight while Cancel publishes the verified
            // checkpoint for item one, then settle this stale promise below.
            return new Promise(resolve=>{fixture.releaseBulk=()=>resolve({ok:false});});
          }
        }
        return client.run(job,opts);
      };
      fixture.client=client;
      fixture.workspace=mountTopologyWorkspace(root,{runEngine,cancelEngine:()=>client.cancel()});
      window.__reloadPreviewFixture=fixture;
      await fixture.workspace.load(new File([xml],'public-original.xml',{type:'text/xml'}));
    },syntheticXML);
    await page.locator('[data-uxml-toggle]').check();
    await page.evaluate(()=>window.__reloadPreviewFixture.workspace.analyze());
    await page.waitForFunction(()=>
      window.__reloadPreviewFixture.workspace.getState().hubParity==='EQUAL',
      null,{timeout:120000});
    await page.locator('[data-preview-short]').click();
    await page.locator('[data-select-gaskets]').click();
    assert.equal(await page.locator('[data-short-index]:checked').count(),5);
    await page.evaluate(()=>{window.__reloadPreviewFixture.holdPreview=true;});
    await page.locator('[data-short-hub-preview]').click();
    await page.waitForFunction(()=>window.__reloadPreviewFixture.previewHeld,
      null,{timeout:120000});
    assert.match(await page.locator('[data-short-hub-status]').textContent(),/Previewing/);

    // Replacement source with a different identity. The old Worker result
    // is still deliberately held while load() cancels and invalidates it.
    const reloaded=syntheticXML.replace('PUBLIC-SYNTH-0','PUBLIC-RELOADED-0');
    await page.evaluate(async xml=>window.__reloadPreviewFixture.workspace.load(
      new File([xml],'public-reloaded.xml',{type:'text/xml'})),reloaded);
    assert.equal((await page.evaluate(()=>
      window.__reloadPreviewFixture.workspace.getState())).busy,false);
    assert.match(await page.locator('[data-progress]').textContent(),
      /Original loaded · revision 0/);
    assert.equal(await page.locator('button[title*="active preview"]').count(),0,
      'old preview disabled reasons must be removed after load');
    await page.evaluate(()=>window.__reloadPreviewFixture.releasePreview());
    await page.waitForTimeout(100);
    assert.equal(await page.evaluate(()=>
      window.__reloadPreviewFixture.staleDelivered),true);
    assert.doesNotMatch(await page.locator('[data-progress]').textContent(),/Previewing/);
    assert.equal(await page.locator('button[title*="active preview"]').count(),0);

    // A fresh qualified preview on the new source is required before Apply.
    await page.evaluate(()=>window.__reloadPreviewFixture.holdPreview=false);
    await page.evaluate(()=>window.__reloadPreviewFixture.workspace.analyze());
    await page.waitForFunction(()=>
      window.__reloadPreviewFixture.workspace.getState().hubParity==='EQUAL',
      null,{timeout:120000});
    await page.locator('[data-preview-short]').click();
    await page.locator('[data-select-gaskets]').click();
    await page.locator('[data-short-hub-preview]').click();
    await page.waitForFunction(()=>document.querySelector('[data-run-short-drop]')
      ?.disabled===false,null,{timeout:120000});

    // First short bulk item is a real, independently validated native
    // transaction; second item is held before return, with a checkpoint.
    await page.locator('[data-run-short-drop]').click();
    await page.waitForFunction(()=>window.__reloadPreviewFixture.bulkHolding,
      null,{timeout:120000});
    assert.equal(await page.locator('[data-cancel]').isEnabled(),true);
    await page.locator('[data-cancel]').click();
    await page.waitForFunction(()=>
      document.querySelector('[data-progress]')?.textContent?.includes('BULK STOPPED · CANCELLED'),
      null,{timeout:120000});
    const result=await page.evaluate(()=>({
      progress:document.querySelector('[data-progress]')?.textContent,
      state:window.__reloadPreviewFixture.workspace.getState(),
      cancelledPreviewClaim:document.querySelector('[data-short-hub-status]')
        ?.textContent?.includes('UXML_SHORT_PREVIEW_CANCELLED')||false,
    }));
    assert.match(result.progress,/BULK STOPPED · CANCELLED/);
    assert.doesNotMatch(result.progress,/BULK STOPPED · ERROR/);
    assert.equal(result.cancelledPreviewClaim,false,
      'short-bulk Cancel must not be routed through stale preview Cancel');
    assert.equal(result.state.revision,1,
      'last validated native bulk checkpoint is retained');
    assert.equal(result.state.busy,false);
    await page.evaluate(()=>window.__reloadPreviewFixture.releaseBulk());
    await page.waitForTimeout(100);
    assert.match(await page.locator('[data-progress]').textContent(),
      /BULK STOPPED · CANCELLED/);
    assert.deepEqual(errors,[]);
    console.log('SYNTHETIC_PREVIEW_LOAD_BULK_CANCEL_PASS '+JSON.stringify({
      stalePreviewRetired:true,staleResultIgnored:true,
      bulkStopReason:'CANCELLED',checkpointRevision:result.state.revision,
      pageErrors:errors}));
  }finally{
    await page.close();await browser.close();await new Promise(done=>server.close(done));
  }
});
