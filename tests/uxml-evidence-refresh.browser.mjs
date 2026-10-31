/** UXML-EVIDENCE-REFRESH: injected runEngine wrapping the REAL disposable
 * module Worker/Pyodide. Synthetic short-element and approved manual queue.
 * No Owner file, no test-only product hook, no transaction policy changes.
 */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';

const root=path.resolve(process.cwd(),'dist');
const mime={'.html':'text/html;charset=utf-8','.mjs':'text/javascript;charset=utf-8',
 '.js':'text/javascript;charset=utf-8','.css':'text/css;charset=utf-8',
 '.py':'text/plain;charset=utf-8','.wasm':'application/wasm',
 '.zip':'application/zip','.json':'application/json'};
const node=(n,kind,ref,end,x,extra='')=>
 '<Node><NodeNumber>'+n+'</NodeNumber><ComponentType>'+kind+
 '</ComponentType><ComponentRefNo>'+ref+'</ComponentRefNo><Endpoint>'+end+
 '</Endpoint><Position>'+x+' 0 0</Position><OutsideDiameter>100</OutsideDiameter>'+
 extra+'<BendRadius>0</BendRadius><AlphaAngle>0</AlphaAngle></Node>';
const shortXML='<PipeStressExport><Branch><Branchname>SHORT-SYNTH</Branchname>'+
 node(10,'PIPE','P',1,0)+node(20,'PIPE','P',2,100)+
 node(-1,'GASK','SHORT',1,100,'<Weight>2.5</Weight>')+
 node(30,'RIGID','SHORT',2,103)+node(-1,'FLAN','F',1,103)+
 node(40,'RIGID','F',2,189)+'</Branch></PipeStressExport>';
const manualXML='<PipeStressExport><Branch><Branchname>SOURCE</Branchname>'+
 node(10,'PIPE','P',1,0)+node(20,'PIPE','P',2,100)+
 '</Branch><Branch><Branchname>PARTNER</Branchname>'+
 node(30,'FLAN','F',1,175)+node(-1,'RIGID','F',2,261)+
 '</Branch></PipeStressExport>';

const server=createServer(async(req,res)=>{
 try{
   const rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname)
     .replace(/^\/+/,'')||'index.html';
   const file=path.resolve(root,rel);
   if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
   const content=await readFile(file);
   res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');
   res.writeHead(200).end(content);
 }catch(error){res.writeHead(404).end(String(error));}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const url='http://127.0.0.1:'+server.address().port+'/index.html';

async function openInjected(mode){
 const page=await browser.newPage({viewport:{width:1440,height:960}});
 const errors=[];
 page.on('pageerror',err=>errors.push(String(err)));
 await page.route('**/index.html',async route=>{
   const response=await route.fetch();
   const original=await response.text();
   const html=original.replace(
     '<script type="module" src="./tabs/topology-workspace/workspace-app.mjs"></script>','');
   assert.notEqual(html,original,'default worker mount must be suppressed');
   await route.fulfill({response,body:html});
 });
 await page.goto(url);
 await page.evaluate(async mode=>{
   const root=document.querySelector('#xml229-topology-workspace');
   root.id='injected-evidence-mount';
   const [{mountTopologyWorkspace},{createTopologyWorkerClient}]=await Promise.all([
     import('/tabs/topology-workspace/workspace-app.mjs'),
     import('/tabs/topology-workspace/topology-worker-client.mjs')]);
   root.id='xml229-topology-workspace';
   const client=createTopologyWorkerClient();
   let committed=false;
   const stages=[];
   const runEngine=async job=>{
     const result=await client.run(job);
     stages.push(job.options?.generateTopoFix?'TRANSACTION':
       committed?'POST_PUBLISH_RECHECK':'READ_ONLY_ANALYSIS');
     if(job.options?.generateTopoFix&&result?.topoFixCommitted===true)committed=true;
     if(committed&&!job.options?.generateTopoFix&&mode==='STALE'){
       // Stale plan is a synthetic mutation *only of the returned read-only
       // result*, never the validated transaction or source XML.
       const plan=JSON.parse(result.topologyFixPlanText||'null');
       if(plan?.source)plan.source.sha256='SYNTHETIC_STALE_REVISION';
       return {...result,topologyFixPlanText:JSON.stringify(plan)};
     }
     return result;
   };
   window.__evidenceFixture={stages,workspace:mountTopologyWorkspace(root,
     {runEngine,cancelEngine:()=>client.cancel()}),client};
 },mode);
 return {page,errors};
}
async function loadAndAnalyze(page,xml){
 await page.locator('[data-file]').setInputFiles({
   name:'public-evidence-synthetic.xml',mimeType:'application/xml',
   buffer:Buffer.from(xml,'utf8')
 });
 const count=xml===shortXML?6:4;
 await page.waitForFunction(n=>
   document.querySelector('[data-occ-summary]')?.textContent?.includes(n+' of '+n),
   count,{timeout:30000});
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>
   document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),
   null,{timeout:120000});
 assert.equal(await page.locator('[data-evidence-proof]').textContent()
   .then(x=>x.includes('verified for working revision 0')),true);
}
async function finishAndCheck(page,mode,kind){
 await page.waitForFunction(()=>document.querySelector('main')?.getAttribute('aria-busy')==='false'&&
   /COMPLETE|STOPPED/.test(document.querySelector('[data-progress]')?.textContent||''),
   null,{timeout:120000});
 const state=await page.evaluate(()=>window.__evidenceFixture.workspace.getState());
 assert.equal(state.revision,1,kind+': validated working revision must increment');
 const stages=await page.evaluate(()=>window.__evidenceFixture.stages);
 assert.ok(stages.includes('TRANSACTION'),kind+': native transaction never executed');
 assert.ok(stages.includes('POST_PUBLISH_RECHECK'),kind+': new revision not re-analysed');
 const resultPanel=page.locator('[data-trial-result]');
 assert.equal(await resultPanel.isVisible(),true,kind+': validated revision summary absent');
 const summary=await resultPanel.locator('[data-trial-head]').textContent();
 assert.match(summary,/Revision 1: 1 fixes applied · \d+\/\d+ checks passed/,
   kind+': native validation and fix count missing from overview');
 assert.match(await resultPanel.locator('[data-what-left="review"]').textContent(),
   /Needs your review \(\d+\)/);
 assert.match(await resultPanel.locator('[data-what-left="preserve"]').textContent(),
   /Preserved by rule — no action \(\d+\)/);
 assert.match(await resultPanel.locator('[data-what-left="information"]').textContent(),
   /Informational \/ other remaining \(\d+\)/);
 assert.equal(await resultPanel.locator('[data-auto-fix],[data-apply-second],[data-queue-apply],[data-close-joint]').count(),0);
 const message=await page.locator('[data-evidence-proof]').textContent();
 if(mode==='PASS'){
   assert.match(message,/Connection evidence verified for working revision 1/);
   assert.equal(await page.locator('[data-download-resolutions]').isEnabled(),true);
   const pending=page.waitForEvent('download');
   await page.locator('[data-download-resolutions]').click();
   const dl=await pending;
   const receipt=JSON.parse(await readFile(await dl.path(),'utf8'));
   assert.equal(receipt.schema,'topofix-connection-evidence/v1');
   assert.equal(receipt.workingRevision,1);
   assert.equal(receipt.sourceSha256,state.sourceSha256);
   assert.equal(receipt.xmlChangedByResolution,false);
 }else{
   assert.equal(await page.locator('[data-download-resolutions]').isDisabled(),true);
   assert.match(message,/Connection evidence unavailable: EVIDENCE_RECHECK_SOURCE_DRIFT/);
   assert.equal(await page.locator('[data-download-working]').isEnabled(),true,
     'a failed read-only evidence recheck must not roll back validated XML');
 }
 return {stages,message};
}

test('injected Worker: short-element bulk publishes new-revision evidence, stale result fails closed',
  {timeout:360000},async()=>{
  for(const mode of ['PASS','STALE']){
    const {page,errors}=await openInjected(mode);
    try{
      await loadAndAnalyze(page,shortXML);
      await page.locator('[data-preview-short]').click();
      await page.locator('[data-select-gaskets]').click();
      assert.equal(await page.locator('[data-short-index]:checked').count(),1);
      await page.locator('[data-run-short-drop]').click();
      await finishAndCheck(page,mode,'SHORT_BULK');
      assert.deepEqual(errors,[]);
    }finally{await page.close();}
  }
});

test('injected Worker: approved manual queue publishes new-revision evidence, stale result fails closed',
  {timeout:360000},async()=>{
  for(const mode of ['PASS','STALE']){
    const {page,errors}=await openInjected(mode);
    try{
      await loadAndAnalyze(page,manualXML);
      await page.locator('[data-audit-category]').selectOption('all');
      await page.locator('[data-audit-filter="manual"]').click();
      await page.locator('[data-rules-expand]').click();
      const summary=page.locator('.audit-case > summary')
        .filter({hasText:'Node 20 · SOURCE'}).first();
      await summary.click();
      await summary.locator('..').locator('[data-add-second-pass]').click();
      await page.locator('[data-second-peer]').selectOption('B1:N30:S0');
      await page.locator('[data-preview-second]').click();
      await page.waitForFunction(()=>
        document.querySelector('[data-second-status]')?.textContent?.includes('PREVIEW ONLY'),
        null,{timeout:120000});
      await page.locator('[data-second-evidence]').fill('SYNTHETIC-DRAWING-REFRESH approves this exact port pair');
      await page.locator('[data-second-confirm]').check();
      await page.locator('[data-queue-second]').click();
      assert.match(await page.locator('[data-manual-queue]').textContent(),/1 approved/);
      await page.locator('[data-queue-apply]').click();
      await finishAndCheck(page,mode,'MANUAL_QUEUE');
      assert.deepEqual(errors,[]);
    }finally{await page.close();}
  }
});

test('UI clarity: hub-only short-drop explanation, review Next/Previous and retained source selection',
  {timeout:180000},async()=>{
 const {page,errors}=await openInjected('PASS');
 try{
   await loadAndAnalyze(page,manualXML);
   await page.locator('[data-uxml-toggle]').check();
   const short=page.locator('[data-preview-short]');
   assert.equal(await short.isDisabled(),true);
   assert.match(await short.getAttribute('title'),/Runs on the direct route only/);
   assert.match(await page.locator('[data-preview-short] + .action-unavailable-reason').textContent(),
     /Untick Universal XML route to use it/);
   await page.locator('[data-uxml-toggle]').uncheck();
   await page.locator('[data-audit-category]').selectOption('all');
   await page.locator('[data-audit-filter="manual"]').click();
   await page.locator('[data-rules-expand]').click();
   const cases=page.locator('.audit-case');
   assert.ok(await cases.count()>=2,'fixture should exercise more than one manual review');
   const first=cases.first();
   await first.locator(':scope > summary').click();
   assert.match(await first.locator('.audit-next-step').textContent(),/What you can do:/);
   const next=first.locator('[data-trial-step="1"]');
   assert.equal(await next.isEnabled(),true);
   const label=await first.locator('[data-trial-counter]').textContent();
   assert.match(label,/1 of \d+/);
   await next.click();
   const current=page.locator('.audit-case[open] [data-trial-counter]')
     .filter({hasText:/2 of \d+/}).first();
   assert.equal(await current.count(),1,'Next should update the group counter');
   assert.match(await page.locator('[data-selection]').textContent(),
     /source occurrence\(s\) selected/);
   await current.locator('xpath=..').locator('[data-trial-step="-1"]').click();
   assert.equal(await page.locator('.audit-case[open] [data-trial-counter]')
      .filter({hasText:/1 of \d+/}).count()>=1,true);
   assert.equal(await page.locator('[data-trial-result] [data-auto-fix],[data-trial-result] [data-apply-second]').count(),0);
   assert.deepEqual(errors,[]);
 }finally{await page.close();}
});

test('UI clarity: direct synthetic Auto-fix surfaces revision, native checks and remaining groups',
  {timeout:180000},async()=>{
 const {page,errors}=await openInjected('PASS');
 try{
   const autoXML=manualXML.replace('<Position>175 0 0</Position>',
     '<Position>125 0 0</Position>').replace('<Position>261 0 0</Position>',
     '<Position>211 0 0</Position>');
   await loadAndAnalyze(page,autoXML);
   const auto=page.locator('[data-auto-fix]').first();
   assert.ok(await auto.count()>0,'synthetic near-miss must offer existing Auto-fix');
   await auto.locator('xpath=ancestor::details[contains(@class,"audit-rule")]')
     .evaluate(el=>{el.open=true;});
   await auto.click();
   await page.waitForFunction(()=>document.querySelector('[data-fix-result]')?.dataset?.result==='ready'&&
     document.querySelector('[data-trial-result]')?.hidden===false,null,{timeout:120000});
   const summary=await page.locator('[data-trial-head]').textContent();
   assert.match(summary,/^Revision 1: 1 fixes applied · \d+\/\d+ checks passed$/);
   const m=summary.match(/(\d+)\/(\d+) checks passed/);
   assert.equal(m[1],m[2],'native checks must all pass, not a guessed count');
   assert.match(await page.locator('[data-what-left="review"]').textContent(),/\(\d+\)/);
   assert.match(await page.locator('[data-what-left="preserve"]').textContent(),/\(\d+\)/);
   assert.equal(await page.locator('[data-trial-current]').isEnabled(),true);
   assert.equal(await page.locator('[data-trial-result] [data-approve],[data-trial-result] [data-apply]').count(),0);
   assert.deepEqual(errors,[]);
 }finally{await page.close();}
});
test.after(async()=>{
 await browser.close();
 await new Promise(done=>server.close(done));
});
