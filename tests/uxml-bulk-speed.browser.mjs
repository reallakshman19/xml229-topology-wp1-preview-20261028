/** UXML-BULK-SPEED: synthetic 330+ element Chromium/Pyodide real Worker timing.
 * No Owner sources, no production test hook. Optional phase clocks only.
 */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
import {chromium} from 'playwright';

const root=path.resolve(process.cwd(),'dist');
const mime={'.html':'text/html','.mjs':'text/javascript','.js':'text/javascript',
 '.css':'text/css','.json':'application/json','.wasm':'application/wasm',
 '.py':'text/plain','.zip':'application/zip'};
function node(n,type,ref,endpoint,x){
 return '<Node><NodeNumber>'+n+'</NodeNumber><ComponentType>'+type+
 '</ComponentType><ComponentRefNo>'+ref+'</ComponentRefNo><Endpoint>'+endpoint+
 '</Endpoint><Position>'+x+' 0 0</Position><OutsideDiameter>100</OutsideDiameter>'+
 '<BendRadius>0</BendRadius><AlphaAngle>0</AlphaAngle></Node>';
}
function synthetic(elements=336){
 const short='<Branch><Branchname>SHORT-SYNTH-ONLY</Branchname>'+
 node(10,'PIPE','P',1,0)+node(20,'PIPE','P',2,100)+
 node(-1,'GASK','SHORT',1,100)+node(30,'RIGID','SHORT',2,103)+
 node(-1,'FLAN','F',1,103)+node(40,'RIGID','F',2,189)+'</Branch>';
 const fillers=Array.from({length:elements-3},(_,i)=>
  node(1000+i,'PIPE','FILL-'+i,0,1000+i*100)).join('');
 return '<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+short+
 '<Branch><Branchname>GENERATED-FILLER</Branchname>'+fillers+'</Branch>'+
 '</PipeStressExport>';
}
const server=createServer(async(req,res)=>{
 try{
  const rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/^\/+/, '')||'index.html';
  const file=path.resolve(root,rel);
  if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
  const bytes=await readFile(file);
  res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});
  res.end(bytes);
 }catch(e){res.writeHead(404).end(String(e));}
});
const ticks={};
test('336 generated PSI116 occurrences: real Worker/Pyodide one short-drop with all parity gates', {timeout:300000}, async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1200,height:800}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 try{
  await page.route('**/index.html',async route=>{
   const response=await route.fetch(),s=await response.text();
   const mark='<script type="module" src="./tabs/topology-workspace/workspace-app.mjs"></script>';
   assert.ok(s.includes(mark),'suppress default workspace mount');
   await route.fulfill({response,body:s.replace(mark,'')});
  });
  await page.route('**/tabs/topology-workspace/workspace-app.mjs',async route=>{
   const response=await route.fetch(),s=await response.text();
   const marker='  async function publishShortBulk(outcome,generation=state.epoch){';
   const end='\n  }\n  async function dropShortElements(){';
   assert.ok(s.includes(marker)&&s.includes(end),'test-only UI timing anchors');
   const patched=s.replace(marker,marker+
     '\n    const __speedUiStarted=performance.now();')
    .replace(end,
     '\n    window.__bulkSpeedUiRefreshMs=performance.now()-__speedUiStarted;'+end);
   await route.fulfill({response,body:patched});
  });
  const url='http://127.0.0.1:'+server.address().port+'/index.html';
  await page.goto(url);
  const source=synthetic();
  await page.evaluate(async xml=>{
   const root=document.querySelector('#xml229-topology-workspace');
   root.id='bulk-speed-injected';
   const [{mountTopologyWorkspace},{createTopologyWorkerClient}]=await Promise.all([
    import('/tabs/topology-workspace/workspace-app.mjs'),
    import('/tabs/topology-workspace/topology-worker-client.mjs')]);
   root.id='xml229-topology-workspace';
   const client=createTopologyWorkerClient();
   const timings=[];
   const runEngine=async job=>{
    const profile=job.options?.generateTopoFix===true &&
                  job.options?.topologyShortElementRequests?.length===1;
    const input=profile?{...job,options:{...job.options,
      topologyBulkSpeedProfile:true}}:job;
    const t=performance.now();
    const result=await client.run(input);
    if(!profile)window.__bulkSpeedLastParity=result.topologyUxmlParity;
    if(profile)timings.push({workerRoundTripMs:performance.now()-t,
                             ...result.topologyBulkTiming,
                             parity:result.topologyUxmlParity?.status,
                             committed:result.topoFixCommitted});
    return result;
   };
   window.__bulkSpeedProbe={timings,client,
    workspace:mountTopologyWorkspace(root,{runEngine,cancelEngine:()=>client.cancel()})};
   await window.__bulkSpeedProbe.workspace.load(new File([xml],'generated-bulk.xml',{type:'text/xml'}));
  },source);
  await page.locator('[data-uxml-toggle]').check();
  const analyzeStarted=performance.now();
  await page.evaluate(()=>window.__bulkSpeedProbe.workspace.analyze());
  ticks.initialAnalysisMs=performance.now()-analyzeStarted;
  const initialState=await page.evaluate(()=>({
   state:window.__bulkSpeedProbe.workspace.getState(),
   lastParity:window.__bulkSpeedLastParity,
   status:document.querySelector('[data-status]')?.textContent,
   progress:document.querySelector('[data-progress]')?.textContent,
   parity:document.querySelector('[data-uxml-parity]')?.textContent,
  }));
  console.info('UXML_BULK_SYNTHETIC_INITIAL_STATE '+JSON.stringify(initialState));
  assert.equal(initialState.state.hubParity,'EQUAL',
    'Generated 336-occurrence fixture must establish exact source/UXML parity');
  await page.locator('[data-preview-short]').click();
  await page.locator('[data-select-gaskets]').click();
  assert.equal(await page.locator('[data-short-index]:checked').count(),1);
  const preview=page.locator('[data-short-hub-preview]');
  assert.equal(await preview.isEnabled(),true);
  await preview.click();
  await page.waitForFunction(()=>document.querySelector('[data-run-short-drop]')?.disabled===false,
                              undefined,{timeout:120000});
  const started=performance.now();
  await page.locator('[data-run-short-drop]').click();
  await page.waitForFunction(()=>window.__bulkSpeedProbe.workspace.getState().revision===1&&
    Number.isFinite(window.__bulkSpeedUiRefreshMs),undefined,{timeout:180000});
  const elapsed=performance.now()-started;
  const observed=await page.evaluate(()=>({
   timings:window.__bulkSpeedProbe.timings,
   uiRefreshMs:window.__bulkSpeedUiRefreshMs,
   revision:window.__bulkSpeedProbe.workspace.getState().revision,
   hubParity:window.__bulkSpeedProbe.workspace.getState().hubParity,
   downloadEnabled:!document.querySelector('[data-download-working]')?.disabled,
  }));
  assert.equal(observed.revision,1);
  assert.equal(observed.hubParity,'EQUAL');
  assert.equal(observed.timings.length,1,'one worker validated transaction');
  assert.equal(observed.timings[0].parity,'EQUAL','unconditional hub parity');
  assert.equal(observed.timings[0].committed,true);
  assert.deepEqual(errors,[]);
  console.log('UXML_BULK_SPEED_REAL_BROWSER_TIMING '+JSON.stringify({
   syntheticElements:336,syntheticNodeRecords:source.match(/<Node>/g)?.length,
   firstAnalysisMs:+ticks.initialAnalysisMs.toFixed(1),
   oneItemBulkMs:+elapsed.toFixed(1),
   ...Object.fromEntries(Object.entries(observed.timings[0]).map(([k,v])=>
    [k,typeof v==='number'?+v.toFixed(1):v])),
   uiRefreshMs:+observed.uiRefreshMs.toFixed(1),
   downloadEnabled:observed.downloadEnabled,
  }));
 }finally{
  await page.close();await browser.close();await new Promise(done=>server.close(done));
 }
});
