/** UXML-BULK-SPEED real Worker integration, synthetic three independent
 * short owners. Verifies 3 validated revisions/EQUAL and no download after
 * item-2 parity mutation. No private Owner source or product test hook.
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
function fixture(){
 return '<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+
 Array.from({length:3},(_,i)=>{
  const p=i*1000,k=i*100,ref=String(i);
  return '<Branch><Branchname>SHORT-SYNTH-'+i+'</Branchname>'+
   node(10+k,'PIPE','P'+ref,1,p)+node(20+k,'PIPE','P'+ref,2,p+100)+
   node(-1,'GASK','SHORT'+ref,1,p+100)+node(30+k,'RIGID','SHORT'+ref,2,p+103)+
   node(-1,'FLAN','F'+ref,1,p+103)+node(40+k,'RIGID','F'+ref,2,p+189)+
   '</Branch>';
 }).join('')+'</PipeStressExport>';
}

async function exercise(mismatchAt=Infinity){
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
 const page=await browser.newPage({viewport:{width:1300,height:850}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 try{
  await page.route('**/index.html',async route=>{
   const response=await route.fetch(),original=await response.text();
   const tag='<script type="module" src="./tabs/topology-workspace/workspace-app.mjs"></script>';
   assert.ok(original.includes(tag));
   await route.fulfill({response,body:original.replace(tag,'')});
  });
  const url='http://127.0.0.1:'+server.address().port+'/index.html';
  await page.goto(url);
  await page.evaluate(async ({xml,mismatchAt})=>{
   const root=document.querySelector('#xml229-topology-workspace');
   root.id='synthetic-three';
   const [{mountTopologyWorkspace},{createTopologyWorkerClient}]=await Promise.all([
    import('/tabs/topology-workspace/workspace-app.mjs'),
    import('/tabs/topology-workspace/topology-worker-client.mjs')]);
   root.id='xml229-topology-workspace';
   const client=createTopologyWorkerClient();
   let count=0;
   const parities=[],timings=[],validated=[];
   const runEngine=async job=>{
    const t=performance.now();
    const result=await client.run(job);
    if(job.options?.generateTopoFix && job.options?.topologyShortElementRequests?.length){
      count++;
      timings.push({item:count,roundTripMs:Math.round(performance.now()-t),
        readerLoadMs:Math.round(result.topologyBulkTiming?.hubReaderLoadMs||0),
        pyTopologyMs:Math.round(result.topologyBulkTiming?.pythonTopologyMs||0)});
      const mismatch=count===mismatchAt;
      const receipt=JSON.parse(result.topoFixTransactionText||'null');
      const check=JSON.parse(result.topoFixValidationText||'null');
      validated.push({item:count,transaction:receipt?.committed===true,
        validated:check?.committed===true,
        checks:check?.checks?.length||0,
        blockingFailures:check?.summary?.blockingFailureCount,
        workerParity:result.topologyUxmlParity?.status,
        sourceMatched:receipt?.source?.sha256===check?.sourceSha256});
      parities.push(mismatch?'DIFFERENT':result.topologyUxmlParity?.status);
      if(mismatch){
        return {...result,topologyUxmlParity:{status:'DIFFERENT',
          differences:['SYNTHETIC_FORCED_ITEM_TWO_PARITY']},
          topoFixCommitted:false,topoFixXmlText:''};
      }
    }
    return result;
   };
   runEngine.beginBulkSession=()=>client.beginBulkSession();
   runEngine.endBulkSession=()=>client.endBulkSession();
   window.__triple={client,parities,timings,validated,get count(){return count;},
    workspace:mountTopologyWorkspace(root,{runEngine,cancelEngine:()=>client.cancel()})};
   await window.__triple.workspace.load(new File([xml],'synthetic-three.xml',{type:'text/xml'}));
  },{xml:fixture(),mismatchAt});
  await page.locator('[data-uxml-toggle]').check();
  await page.evaluate(()=>window.__triple.workspace.analyze());
  const initial=await page.evaluate(()=>window.__triple.workspace.getState());
  assert.equal(initial.hubParity,'EQUAL','3-branch source hub parity required');
  await page.locator('[data-select-short]').click();
  await page.locator('[data-select-gaskets]').click();
  assert.equal(await page.locator('[data-short-index]:checked').count(),3,
    'all three generated qualified short owners selected');
  await page.locator('[data-short-hub-preview]').click();
  await page.waitForFunction(()=>document.querySelector('[data-run-short-drop]')?.disabled===false,
                             undefined,{timeout:120000});
  assert.match(await page.locator('[data-short-hub-status]').textContent(),
    /3 ready \/ 0 refused/,
    'combined preview must accept exactly three separate source-qualified owners');
  assert.equal(await page.locator('[data-ops-rows] [data-op-id]')
    .filter({hasText:'Drop selected short component'}).count(),3);
  const second=page.locator('[data-short-index]:checked').nth(1);
  const secondIndex=await second.getAttribute('data-short-index');
  assert.ok(Number.isInteger(Number(secondIndex)) && Number(secondIndex)>=0);
  await page.locator('[data-short-index="'+secondIndex+'"]').uncheck();
  assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true,
    'changing selection must revoke previously admitted Apply');
  assert.match(await page.locator('[data-run-short-drop]').getAttribute('title'),
    /Preview the selected UXML short-drop operations/);
  await page.locator('[data-short-index="'+secondIndex+'"]').check();
  assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true,
    'returning to the previous set does not resurrect a stale preview');
  await page.locator('[data-short-hub-preview]').click();
  await page.waitForFunction(()=>document.querySelector('[data-run-short-drop]')?.disabled===false,
                             undefined,{timeout:120000});
  assert.match(await page.locator('[data-short-hub-status]').textContent(),/3 ready \/ 0 refused/);
  await page.locator('[data-run-short-drop]').click();
  const expected=mismatchAt===Infinity?3:1;
  await page.waitForFunction(expected=>{
   const s=window.__triple.workspace.getState();
   return s.revision===expected && !s.busy &&
     document.querySelector('[data-progress]')?.textContent?.includes('BULK ');
  },expected,{timeout:180000});
  // Let post-publish evidence check resolve (never needed on DIFFERENT).
  if(mismatchAt===Infinity)await page.waitForFunction(()=>
   document.querySelector('[data-download-working]')?.disabled===false,
   undefined,{timeout:120000});
  const result=await page.evaluate(()=>({
   state:window.__triple.workspace.getState(),
   count:window.__triple.count,
   parities:window.__triple.parities,
   timings:window.__triple.timings,
   validated:window.__triple.validated,
   downloadEnabled:!document.querySelector('[data-download-working]').disabled,
   progress:document.querySelector('[data-progress]')?.textContent,
  }));
  assert.deepEqual(errors,[]);
  assert.equal(result.state.revision,expected);
  assert.equal(result.validated.length,result.count,
    'each attempted item must return a separately inspected native receipt');
  assert.ok(result.validated.every(v=>v.transaction&&v.validated&&v.checks>0&&
    v.blockingFailures===0&&v.workerParity==='EQUAL'&&v.sourceMatched),
    'no transaction, validation or Worker EQUAL may be skipped');
  if(mismatchAt===Infinity){
   assert.equal(result.count,3);
   assert.deepEqual(result.parities,['EQUAL','EQUAL','EQUAL']);
   assert.equal(result.state.hubParity,'EQUAL');
   assert.equal(result.downloadEnabled,true);
  }else{
   assert.equal(result.count,2,'item 3 never submitted after item-2 mismatch');
   assert.deepEqual(result.parities,['EQUAL','DIFFERENT']);
   assert.equal(result.state.hubParity,'DIFFERENT');
   assert.equal(result.downloadEnabled,false,'NO corrected XML download after parity mismatch');
   assert.match(result.progress,/BULK STOPPED/);
  }
  console.log('UXML_BULK_THREE_REAL_BROWSER '+JSON.stringify({
   syntheticShortOwners:3,forcedMismatchAt:mismatchAt===Infinity?null:mismatchAt,
   revision:result.state.revision,workerTransactions:result.count,
   independentParityChecks:result.parities,
   timings:result.timings,validationReceipts:result.validated,
   downloadEnabled:result.downloadEnabled}));
 }finally{
  await page.close();await browser.close();await new Promise(done=>server.close(done));
 }
}

test('three actual Worker short transactions retain three independently EQUAL revisions',
 {timeout:300000},async()=>exercise());
test('forced parity DIFFERENT on second real Worker result stops, disables download',
 {timeout:300000},async()=>exercise(2));
