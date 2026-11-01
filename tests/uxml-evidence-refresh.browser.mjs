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
 // Only in the synthetic REVISION_RACE browser test, intercept the served
 // workspace module and expose a test-only closure accessor. The product JS
 // committed to the repository has no revision-mutation test hook.
 if(mode==='REVISION_RACE'){
   await page.route('**/tabs/topology-workspace/workspace-app.mjs',async route=>{
     const response=await route.fetch();
     const original=await response.text();
     const marker='  function sourceMeta(){';
     assert.equal(original.split(marker).length,2,
       'private state accessor inserted only in test-delivered module bytes');
     await route.fulfill({response,body:original.replace(marker,
       '  window.__syntheticRevisionRaceBump=()=>++state.revision;\n'+marker)});
   });
 }
 await page.goto(url);
 await page.evaluate(async mode=>{
   const root=document.querySelector('#xml229-topology-workspace');
   root.id='injected-evidence-mount';
   const [{mountTopologyWorkspace},{createTopologyWorkerClient}]=await Promise.all([
     import('/tabs/topology-workspace/workspace-app.mjs'),
     import('/tabs/topology-workspace/topology-worker-client.mjs')]);
   root.id='xml229-topology-workspace';
   const client=createTopologyWorkerClient();
   let committed=false,shortTransactions=0;
   const stages=[];
   const runEngine=async job=>{
     if(mode==='DELAY_ANALYSIS'&&!job.options?.generateTopoFix){
       await new Promise(resolve=>{
         window.__evidenceFixture.releaseAnalysis=resolve;
         window.__evidenceFixture.analysisHeld=true;
       });
     }
     const result=await client.run(job);
     stages.push(job.options?.generateTopoFix?'TRANSACTION':
       committed?'POST_PUBLISH_RECHECK':'READ_ONLY_ANALYSIS');
     if(job.options?.generateTopoFix&&result?.topoFixCommitted===true)committed=true;
     if(job.options?.generateTopoFix&&job.options?.topologyShortElementRequests?.length){
       shortTransactions++;
       if(mode==='HUB_SHORT_DIFF'||
          (mode==='HUB_SHORT_DIFF_SECOND'&&shortTransactions===2)){
         // Perturb only the returned synthetic parity, not native Worker
         // transaction bytes. The product must never release this revision.
         return {...result,topoFixCommitted:false,topoFixXmlText:'',
           topologyUxmlParity:{status:'DIFFERENT',
             differences:['/synthetic-hub-short: UXML_PATCH_BYTES_DIFFERENT']}};
       }
     }
     if(committed&&!job.options?.generateTopoFix&&mode==='REVISION_RACE'){
       // The real Worker has already returned a valid read-only recheck.
       // Hold the wrapper's result until the browser advances the simulated
       // working revision; the product must reject that now-stale result.
       await new Promise(resolve=>{
         window.__evidenceFixture.releaseRace=resolve;
         window.__evidenceFixture.raceStarted=true;
       });
     }
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
 assert.match(await resultPanel.locator('[data-what-left="auto"]').textContent(),
    /Auto fixes available \(\d+\)/);
  assert.match(await resultPanel.locator('[data-what-left="preserve"]').textContent(),
    /No action needed: kept by rule \(\d+\)/);
  assert.match(await resultPanel.locator('[data-what-left="information"]').textContent(),
    /Informational \/ evidence-only \(\d+\)/);
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
   assert.match(await page.locator('[data-download-resolutions]').getAttribute('title'),
     /EVIDENCE_RECHECK_SOURCE_DRIFT/);
   assert.match(await page.locator('[data-download-resolutions] + .action-unavailable-reason').textContent(),
     /EVIDENCE_RECHECK_SOURCE_DRIFT/);
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
      const shortApply=page.locator('[data-run-short-drop]');
      assert.equal(await shortApply.isDisabled(),true);
      assert.match(await shortApply.getAttribute('title'),/Select at least one eligible short element/);
      assert.equal(await page.locator('[data-run-short-drop] + .action-unavailable-reason').count(),1);
      await page.locator('[data-select-gaskets]').click();
      assert.equal(await page.locator('[data-short-index]:checked').count(),1);
      assert.equal(await shortApply.isEnabled(),true);
      assert.equal(await shortApply.getAttribute('title'),null);
      assert.equal(await shortApply.getAttribute('data-reason-set'),null);
      assert.equal(await page.locator('[data-run-short-drop] + .action-unavailable-reason').count(),0);
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
      assert.equal(await page.locator('[data-queue-second]').count(),1,
        'the manual queue must expose its source-qualified Apply control');
      for(const selector of ['[data-apply-second]','[data-queue-second]']){
        const button=page.locator(selector);
        if(!await button.count())continue; // a non-queue Apply is optional in this view
        assert.equal(await button.isDisabled(),true);
        assert.match(await button.getAttribute('title'),/Select an exact source pair/);
        assert.equal(await page.locator(selector+' + .action-unavailable-reason').count(),1);
      }
      const queueApply=page.locator('[data-queue-apply]');
      assert.equal(await queueApply.isDisabled(),true);
      assert.match(await queueApply.getAttribute('title'),/Select an exact source pair/);
      await page.locator('[data-second-evidence]').fill('SYNTHETIC-DRAWING-REFRESH approves this exact port pair');
      await page.locator('[data-second-confirm]').check();
      for(const selector of ['[data-apply-second]','[data-queue-second]']){
        const button=page.locator(selector);
        if(!await button.count())continue;
        assert.equal(await button.isEnabled(),true);
        assert.equal(await button.getAttribute('title'),null);
        assert.equal(await button.getAttribute('data-reason-set'),null);
        assert.equal(await page.locator(selector+' + .action-unavailable-reason').count(),0);
      }
      await page.locator('[data-queue-second]').click();
      assert.match(await page.locator('[data-manual-queue]').textContent(),/1 approved/);
      assert.equal(await queueApply.isEnabled(),true);
      assert.equal(await queueApply.getAttribute('title'),null);
      assert.equal(await page.locator('[data-queue-apply] + .action-unavailable-reason').count(),0);
      await page.locator('[data-queue-apply]').click();
      await finishAndCheck(page,mode,'MANUAL_QUEUE');
      assert.deepEqual(errors,[]);
    }finally{await page.close();}
  }
});

test('revision-race negative: in-flight read-only recheck cannot enable evidence for a newer working revision',
  {timeout:180000},async()=>{
 const {page,errors}=await openInjected('REVISION_RACE');
 try{
   await loadAndAnalyze(page,shortXML);
   await page.locator('[data-preview-short]').click();
   await page.locator('[data-select-gaskets]').click();
   assert.equal(await page.locator('[data-short-index]:checked').count(),1);
   await page.locator('[data-run-short-drop]').click();
   await page.waitForFunction(()=>window.__evidenceFixture?.raceStarted===true,
     null,{timeout:120000});
   const bumped=await page.evaluate(()=>window.__syntheticRevisionRaceBump());
   assert.equal(bumped,2,'test must advance private state.revision from 1 while recheck is in flight');
   await page.evaluate(()=>window.__evidenceFixture.releaseRace());
   await page.waitForFunction(()=>document.querySelector('main')?.getAttribute('aria-busy')==='false'&&
     document.querySelector('[data-evidence-proof]')?.textContent
       ?.includes('EVIDENCE_RECHECK_STALE_REVISION'),null,{timeout:30000});
   const state=await page.evaluate(()=>window.__evidenceFixture.workspace.getState());
   assert.equal(state.revision,2);
   assert.equal(await page.locator('[data-download-resolutions]').isDisabled(),true);
   assert.equal(await page.locator('[data-trial-evidence]').isDisabled(),true);
   assert.match(await page.locator('[data-evidence-proof]').textContent(),
     /Connection evidence unavailable: EVIDENCE_RECHECK_STALE_REVISION/);
   assert.equal(await page.locator('[data-download-working]').isEnabled(),true,
     'do not delete the already validated corrected XML on a stale read-only recheck');
   assert.deepEqual(errors,[]);
 }finally{await page.close();}
});

test('UI clarity: hub-only short-drop explanation, review Next/Previous and retained source selection',
  {timeout:180000},async()=>{
 const {page,errors}=await openInjected('PASS');
 try{
   await loadAndAnalyze(page,manualXML);
   const directDownload=page.locator('[data-download-working]');
   assert.equal(await directDownload.isDisabled(),true);
   assert.match(await directDownload.getAttribute('title'),/No validated corrected revision exists/);
   assert.equal(await page.locator('[data-download-working] + .action-unavailable-reason').count(),1);
   await page.locator('[data-uxml-toggle]').check();
   const all=page.locator('[data-auto-fix-all]');
   assert.equal(await all.isDisabled(),true);
   assert.match(await all.getAttribute('title'),/Universal XML parity must be EQUAL/);
   assert.equal(await page.locator('[data-auto-fix-all] + .action-unavailable-reason').count(),1);
   const queueApply=page.locator('[data-queue-apply]');
   assert.equal(await queueApply.isDisabled(),true);
   assert.match(await queueApply.getAttribute('title'),/Runs on the direct route only/);
   const evidence=page.locator('[data-download-resolutions]');
   assert.equal(await evidence.isDisabled(),true);
   assert.match(await evidence.getAttribute('title'),/EVIDENCE_ANALYSIS_REQUIRED/);
   assert.equal(await page.locator('[data-download-resolutions] + .action-unavailable-reason').count(),1);
   const short=page.locator('[data-preview-short]');
   assert.equal(await short.isDisabled(),true);
   assert.match(await short.getAttribute('title'),
     /Universal XML parity must be EQUAL before short-element changes/);
   assert.match(await page.locator('[data-preview-short] + .action-unavailable-reason').textContent(),
     /Universal XML parity must be EQUAL before short-element changes/);
   await page.locator('[data-uxml-toggle]').uncheck();
   assert.equal(await short.isEnabled(),true);
   assert.equal(await short.getAttribute('title'),null);
   assert.equal(await short.getAttribute('data-reason-set'),null);
   assert.equal(await page.locator('[data-preview-short] + .action-unavailable-reason').count(),0);
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
   const autofixAll=page.locator('[data-auto-fix-all]');
   assert.equal(await autofixAll.isEnabled(),true);
   await page.locator('[data-uxml-toggle]').check();
   assert.equal(await autofixAll.isDisabled(),true);
   assert.match(await autofixAll.getAttribute('title'),/Universal XML parity must be EQUAL/);
   await page.locator('[data-uxml-toggle]').uncheck();
   assert.equal(await autofixAll.isEnabled(),true);
   assert.equal(await autofixAll.getAttribute('title'),null);
   assert.equal(await autofixAll.getAttribute('data-reason-set'),null);
   assert.equal(await page.locator('[data-auto-fix-all] + .action-unavailable-reason').count(),0);
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
   // Compare overview counts with independently rendered resolver dispositions,
    // not with trialGroup() (a group-assignment mutant must fail).
    const cards=await page.locator('[data-finding-id]').evaluateAll(els=>els.map(el=>({
      id:el.dataset.findingId,
      kind:['manual','auto','keep','evidence'].find(k=>
        el.querySelector('.audit-resolution')?.classList.contains(k))||'other',
    })));
    assert.ok(cards.length>0,'post-fix synthetic findings must be present');
    const groupByKind={manual:'review',auto:'auto',keep:'preserve',
      evidence:'information',other:'information'};
    const expected={review:[],auto:[],preserve:[],information:[]};
    for(const card of cards)expected[groupByKind[card.kind]].push(card.id);
    const labels={review:'Needs your review',auto:'Auto fixes available',
      preserve:'No action needed: kept by rule',information:'Informational / evidence-only'};
    const filters={review:'manual',auto:'auto',preserve:'keep',information:'information'};
    for(const kind of Object.keys(expected)){
      const button=page.locator('[data-what-left="'+kind+'"]');
      assert.equal(await button.textContent(),labels[kind]+' ('+expected[kind].length+')',
        kind+': exact post-fix count from independently classified finding cards');
      assert.equal(await button.isDisabled(),expected[kind].length===0);
      if(!expected[kind].length)continue;
      await button.click();
      assert.equal(await page.locator('[data-audit-filter="'+filters[kind]+'"]').getAttribute('aria-pressed'),
        'true',kind+': group must activate its exact filter');
      assert.equal(await button.getAttribute('aria-pressed'),'true');
      const shown=await page.locator('[data-finding-id]').evaluateAll(
        els=>els.map(el=>el.dataset.findingId));
      assert.deepEqual(shown.sort(),[...expected[kind]].sort(),
        kind+': group must show only its own source findings');
    }
    assert.equal(await page.locator('[data-trial-current]').isEnabled(),true);
   assert.equal(await page.locator('[data-trial-result] [data-approve],[data-trial-result] [data-apply]').count(),0);
   assert.deepEqual(errors,[]);
 }finally{await page.close();}
});
test('UI clarity: disabled Cancel reason disappears on actual analysis start',
 {timeout:180000},async()=>{
 const {page,errors}=await openInjected('DELAY_ANALYSIS');
 try{
   await page.locator('[data-file]').setInputFiles({
     name:'synthetic-delayed-analysis.xml',mimeType:'application/xml',
     buffer:Buffer.from(manualXML,'utf8')
   });
   await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')
     ?.textContent?.includes('4 of 4'));
   const cancel=page.locator('[data-cancel]');
   assert.equal(await cancel.isDisabled(),true);
   assert.equal(await cancel.getAttribute('title'),'No active operation to cancel.');
   await page.locator('[data-analyze]').click();
   await page.waitForFunction(()=>window.__evidenceFixture?.analysisHeld===true);
   assert.equal(await cancel.isEnabled(),true);
   assert.equal(await cancel.getAttribute('title'),null);
   assert.equal(await cancel.getAttribute('data-reason-set'),null);
   assert.equal(await page.locator('[data-cancel] + .action-unavailable-reason').count(),0);
   await page.evaluate(()=>window.__evidenceFixture.releaseAnalysis());
   await page.waitForFunction(()=>document.querySelector('[data-status]')
     ?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
   assert.equal(await cancel.isDisabled(),true);
   assert.equal(await cancel.getAttribute('title'),'No active operation to cancel.');
   assert.deepEqual(errors,[]);
 }finally{await page.close();}
});


const hubShortXML=shortXML.replace('<PipeStressExport>',
  '<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">');

async function prepareHubShort(page){
  await page.locator('[data-file]').setInputFiles({
    name:'synthetic-hub-gasket.xml',mimeType:'application/xml',
    buffer:Buffer.from(hubShortXML,'utf8')
  });
  await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')
    ?.textContent?.includes('6 of 6'));
  await page.locator('[data-uxml-toggle]').check();
  await page.locator('[data-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-uxml-parity]')
    ?.dataset?.parity==='EQUAL'&&document.querySelector('[data-status]')
    ?.textContent?.includes('Authoritative topology analysis complete.'),
    null,{timeout:120000});
  const short=page.locator('[data-preview-short]');
  assert.equal(await short.isEnabled(),true,'EQUAL hub must enable short drop preview');
  assert.equal(await short.getAttribute('title'),null);
  await short.click();
  await page.locator('[data-select-gaskets]').click();
  assert.equal(await page.locator('[data-short-index]:checked').count(),1);
  const apply=page.locator('[data-run-short-drop]');
  assert.equal(await apply.isDisabled(),true,
    'hub requires exact selected operations preview before explicit Apply');
  assert.match(await apply.getAttribute('title'),/Preview the selected UXML short-drop operations/);
  await page.locator('[data-short-hub-preview]').click();
  await page.waitForFunction(()=>document.querySelector('[data-short-hub-status]')
    ?.textContent?.includes('verified for exact current selection'),
    null,{timeout:120000});
  assert.equal(await apply.isEnabled(),true);
  assert.equal(await apply.getAttribute('title'),null);
  const op=page.locator('[data-ops-rows] [data-op-id]')
    .filter({hasText:'Drop selected short component and close ports'});
  assert.equal(await op.count(),1,'read-only Operations preview must show short delete+close');
  assert.match(await op.textContent(),/Source record: Present → Removed/);
  assert.equal(await page.locator('[data-download-working]').isDisabled(),true,
    'preview never writes a corrected source before Apply');
}

test('hub short-drop EQUAL: selected preview, source patch, validated download',
 {timeout:240000},async()=>{
  const {page,errors}=await openInjected('PASS');
  try{
    await prepareHubShort(page);
    await page.locator('[data-run-short-drop]').click();
    await page.waitForFunction(()=>document.querySelector('[data-progress]')
      ?.textContent?.includes('BULK COMPLETE')&&
      document.querySelector('main')?.getAttribute('aria-busy')==='false',
      null,{timeout:120000});
    const current=await page.evaluate(()=>window.__evidenceFixture.workspace.getState());
    assert.equal(current.revision,1);
    assert.equal(current.hubParity,'EQUAL');
    assert.equal(await page.locator('[data-download-working]').isEnabled(),true);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});

test('hub short-drop DIFFERENT: no corrected download or source publication',
 {timeout:240000},async()=>{
  const {page,errors}=await openInjected('HUB_SHORT_DIFF');
  try{
    await prepareHubShort(page);
    await page.locator('[data-run-short-drop]').click();
    await page.waitForFunction(()=>document.querySelector('[data-progress]')
      ?.textContent?.includes('UXML_SHORT_PARITY_DIFFERENT')&&
      document.querySelector('main')?.getAttribute('aria-busy')==='false',
      null,{timeout:120000});
    const current=await page.evaluate(()=>window.__evidenceFixture.workspace.getState());
    assert.equal(current.revision,0);
    assert.equal(current.hubParity,'DIFFERENT');
    assert.equal(await page.locator('[data-download-working]').isDisabled(),true);
    assert.equal(await page.locator('[data-download-fix]').count(),0);
    assert.match(await page.locator('[data-uxml-differences]').textContent(),
      /UXML_SHORT_PARITY_DIFFERENT/);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});


const hubTwoShortXML='<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+
 '<Branch><Branchname>TWO-SYNTH</Branchname>'+
 node(10,'PIPE','P',1,0)+node(20,'PIPE','P',2,100)+
 node(-1,'GASK','SHORT-A',1,100)+node(30,'RIGID','SHORT-A',2,103)+
 node(-1,'FLAN','F',1,103)+node(40,'RIGID','F',2,189)+
 node(-1,'PIPE','M',1,189)+node(70,'PIPE','M',2,300)+
 node(-1,'GASK','SHORT-B',1,300)+node(80,'RIGID','SHORT-B',2,303)+
 node(-1,'FLAN','G',1,303)+node(90,'RIGID','G',2,389)+
 '</Branch></PipeStressExport>';

async function prepareTwoShort(page){
  await page.locator('[data-file]').setInputFiles({
    name:'synthetic-two-gaskets.xml',mimeType:'application/xml',
    buffer:Buffer.from(hubTwoShortXML,'utf8')
  });
  await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')
    ?.textContent?.includes('12 of 12'),null,{timeout:30000});
  await page.locator('[data-uxml-toggle]').check();
  await page.locator('[data-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-uxml-parity]')
    ?.dataset?.parity==='EQUAL'&&document.querySelector('[data-status]')
    ?.textContent?.includes('Authoritative topology analysis complete.'),
    null,{timeout:120000});
  await page.locator('[data-preview-short]').click();
  const candidates=page.locator('[data-short-index]:not([disabled])');
  assert.ok(await candidates.count()>=2,
    'two independent selected synthetic owners must qualify');
  assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true);
}

async function previewCurrentShort(page){
  await page.locator('[data-short-hub-preview]').click();
  await page.waitForFunction(()=>document.querySelector('[data-short-hub-status]')
    ?.textContent?.includes('verified for exact current selection'),
    null,{timeout:120000});
  assert.equal(await page.locator('[data-run-short-drop]').isEnabled(),true);
}

test('hub preview selection change invalidates Apply and requires re-preview',
  {timeout:240000},async()=>{
  const {page,errors}=await openInjected('PASS');
  try{
    await prepareTwoShort(page);
    const eligible=page.locator('[data-short-index]:not([disabled])');
    await eligible.nth(0).check();
    await previewCurrentShort(page);
    const firstOps=await page.locator('[data-ops-rows] [data-op-id]')
      .filter({hasText:'Drop selected short component'}).count();
    assert.equal(firstOps,1);
    await eligible.nth(1).check();
    const apply=page.locator('[data-run-short-drop]');
    assert.equal(await apply.isDisabled(),true);
    assert.match(await apply.getAttribute('title'),
      /Preview the selected UXML short-drop operations/);
    assert.match(await page.locator('[data-run-short-drop] + .action-unavailable-reason')
      .textContent(),/Preview the selected UXML short-drop operations/);
    const before=await page.evaluate(()=>window.__evidenceFixture.stages
      .filter(s=>s==='TRANSACTION').length);
    // Dispatch a synthetic click to ensure the handler (not merely disabled
    // browser semantics) refuses a stale source/selection authorization.
    await page.evaluate(()=>document.querySelector('[data-run-short-drop]')
      .dispatchEvent(new MouseEvent('click',{bubbles:true})));
    assert.equal(await page.evaluate(()=>window.__evidenceFixture.stages
      .filter(s=>s==='TRANSACTION').length),before);
    assert.match(await page.locator('[data-fix-result]').textContent(),
      /UXML_SHORT_PREVIEW_OR_PARITY_REQUIRED/);
    await previewCurrentShort(page);
    assert.equal(await apply.getAttribute('title'),null);
    assert.equal(await page.locator('[data-ops-rows] [data-op-id]')
      .filter({hasText:'Drop selected short component'}).count(),2);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});

test('hub second-item DIFFERENT never exposes intermediate download',
  {timeout:300000},async()=>{
  const {page,errors}=await openInjected('HUB_SHORT_DIFF_SECOND');
  try{
    await prepareTwoShort(page);
    await page.locator('[data-select-gaskets]').click();
    assert.equal(await page.locator('[data-short-index]:checked').count(),2);
    await previewCurrentShort(page);
    assert.equal(await page.locator('[data-download-working]').isDisabled(),true);
    await page.evaluate(()=>{
      const working=document.querySelector('[data-download-working]');
      const panel=document.querySelector('[data-fix-result]');
      window.__downloadEnabledTransitions=[];
      window.__downloadFixEverAdded=false;
      const audit=records=>{
        window.__downloadEnabledTransitions.push(!working.disabled);
        if(records.some(record=>[...record.addedNodes].some(node=>
          node.nodeType===1&&(
            node.matches?.('[data-download-fix]')||
            node.querySelector?.('[data-download-fix]')))))
          window.__downloadFixEverAdded=true;
        if(panel.querySelector('[data-download-fix]'))
          window.__downloadFixEverAdded=true;
      };
      window.__downloadObserver=new MutationObserver(audit);
      window.__downloadObserver.observe(working,
        {attributes:true,attributeFilter:['disabled']});
      window.__downloadObserver.observe(panel,{childList:true,subtree:true});
    });
    await page.locator('[data-run-short-drop]').click();
    await page.waitForFunction(()=>document.querySelector('[data-progress]')
      ?.textContent?.includes('UXML_SHORT_PARITY_DIFFERENT')&&
      document.querySelector('main')?.getAttribute('aria-busy')==='false',
      null,{timeout:180000});
    const state=await page.evaluate(()=>window.__evidenceFixture.workspace.getState());
    assert.equal(state.revision,1,'first validated owner may remain as a private working copy');
    assert.equal(state.hubParity,'DIFFERENT');
    assert.equal(await page.locator('[data-download-working]').isDisabled(),true);
    assert.equal(await page.locator('[data-download-fix]').count(),0);
    const transitions=await page.evaluate(()=>{
      window.__downloadObserver.disconnect();
      return window.__downloadEnabledTransitions;
    });
    assert.ok(transitions.every(enabled=>enabled===false),
      'working download must stay disabled even transiently during mismatch');
    assert.equal(await page.evaluate(()=>window.__downloadFixEverAdded),false,
      'corrected-file download button must never appear, even briefly');
    assert.match(await page.locator('[data-uxml-differences]').textContent(),
      /UXML_SHORT_PARITY_DIFFERENT/);
    assert.deepEqual(errors,[]);
  }finally{await page.close();}
});

test.after(async()=>{
 await browser.close();
 await new Promise(done=>server.close(done));
});
