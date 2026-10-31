/** UXML-PREVIEW browser acceptance with injected runEngine, synthetic only.
 * Separately verifies the real exporter via Python. No Apply is invoked.
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
 '.wasm':'application/wasm','.zip':'application/zip'};
const synthetic='<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+
 '<Branch><Branchname>PREVIEW</Branchname>'+
 '<Node><NodeNumber>1</NodeNumber><ComponentType>PIPE</ComponentType>'+
 '<Endpoint>1</Endpoint><Position>0 0 0</Position></Node>'+
 '<Node><NodeNumber>2</NodeNumber><ComponentType>PIPE</ComponentType>'+
 '<Endpoint>2</Endpoint><Position>20 0 0</Position></Node>'+
 '</Branch></PipeStressExport>';

test('injected hub EQUAL previews each S2 row, filters, finds, exports; DIFFERENT and UNAVAILABLE have zero applicable rows',async()=>{
 const server=createServer(async(req,res)=>{
   try{
     const rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname)
       .replace(/^\/+/,'')||'index.html';
     const target=path.resolve(root,rel);
     if(!target.startsWith(root+path.sep)){res.writeHead(403).end();return;}
     const body=await readFile(target);
     res.setHeader('Content-Type',mime[path.extname(target)]||'application/octet-stream');
     res.writeHead(200).end(body);
   }catch(error){res.writeHead(404).end(String(error));}
 });
 await new Promise(done=>server.listen(0,'127.0.0.1',done));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:850}});
 const errors=[];
 page.on('pageerror',error=>errors.push(String(error)));
 try{
   await page.route('**/index.html',async route=>{
     const response=await route.fetch();
     const original=await response.text();
     const html=original.replace(
       '<script type="module" src="./tabs/topology-workspace/workspace-app.mjs"></script>','');
     assert.notEqual(html,original,'test must suppress the default worker');
     await route.fulfill({response,body:html});
   });
   await page.goto('http://127.0.0.1:'+server.address().port+'/index.html');
   await page.evaluate(async()=>{
     const root=document.querySelector('#xml229-topology-workspace');
     root.id='injecting-preview';
     const {mountTopologyWorkspace}=await import('/tabs/topology-workspace/workspace-app.mjs');
     root.id='xml229-topology-workspace';
     window.__mode='EQUAL';
     window.__previewWorkspace=mountTopologyWorkspace(root,{
       cancelEngine:()=>{},
       runEngine:async job=>{
         const bytes=new TextEncoder().encode(job.sourceText);
         const digest=await crypto.subtle.digest('SHA-256',bytes);
         const hash=[...new Uint8Array(digest)]
           .map(b=>b.toString(16).padStart(2,'0')).join('');
         const state=window.__mode;
         const parityStatus=state.startsWith('PREVIEW_')?'EQUAL':state;
         const findings={source:{sha256:hash},findings:[
           {finding_id:'AUTO-A',code:'NEAR_MISS_PIPE_JOINT',
            node_keys:['B0:N1:S0'],blocking:false,severity:'WARNING',message:'synthetic'},
           {finding_id:'REVIEW-A',code:'CONFLICTS_WITH_CLOS',
            node_keys:['B0:N2:S1'],blocking:true,severity:'WARNING',message:'review only'},
         ]};
         const actions=[
           {action_id:'ACT-PREVIEW',status:'PROPOSED',confidence:0.99,
            disposition:'ALIAS_COINCIDENT_NODE',blockers:[],finding_ids:['AUTO-A'],
            proposed_changes:[{key:'B0:N1:S0',field:'NodeNumber'}]},
           {action_id:'ACT-REVIEW',status:'BLOCKED',confidence:0.40,
            disposition:'KEEP',blockers:['REVIEW_ONLY'],finding_ids:['REVIEW-A'],
            proposed_changes:[]},
         ];
         const preview={
           schema:'uxml-operations-preview/v1',sourceSha256:hash,
           summary:{totalOps:2,
             byKind:{ALIAS_COINCIDENT_NODE:1,CLOSE_PORT_CONNECTION:1},
             sourceRecordCount:2,untouchedRecordCount:0},
           ops:[
             {opId:'UXML-OP-A',kind:'ALIAS_COINCIDENT_NODE',
              kindName:'Alias coincident node',sourceActionId:'ACT-PREVIEW',
              uxmlIds:['PSI116-B0-A'],sourceRecords:[
                {format:'PSI116',recordKey:'B0:N1:S0',changed:true}],
              changes:[{recordKey:'B0:N1:S0',field:'NodeNumber',before:'1',after:'2'}],
              policyReason:'PROPOSED; no blockers; confidence 0.99 >= 0.95.'},
             {opId:'UXML-OP-B',kind:'CLOSE_PORT_CONNECTION',
              kindName:'Close compatible connection ports',sourceActionId:'ACT-PORT',
              uxmlIds:['PSI116-B0-B','PSI116-PORT-B'],
              sourceRecords:[{format:'PSI116',recordKey:'B0:N2:S1',changed:true}],
              changes:[{recordKey:'B0:N2:S1',field:'Position',
                before:'20 0 0',after:'21 0 0'}],
              policyReason:'PROPOSED; no blockers; confidence 0.97 >= 0.95.'}
           ],
         };
         return {
           ok:true,outputKind:'topology-sidecars',acceptedFinalTransferred:false,
           nativeCiiReleaseAuthorized:false,topoFixCommitted:false,topoFixXmlText:'',
           ciiText:null,enrichedText:'',
           topologyFindingsText:JSON.stringify(findings),
           topologyFixPlanText:JSON.stringify({source:{sha256:hash},actions}),
           topologyUxmlParity:{status:parityStatus,differences:parityStatus==='EQUAL'?[]:
             ['/findings/example: DIRECT != UXML']},
           // Nonempty SAME preview in every parity mode: exercises the actual
           // parity gate instead of passing because input has no operations.
           topologyOperationsPreview:state==='PREVIEW_FAILURE'?
             {error:'UXML_OPS_PREVIEW_UNAVAILABLE:RuntimeError:SYNTHETIC_PREVIEW_FAILURE'}:
             state==='PREVIEW_INVALID'?{...preview,sourceSha256:'synthetic-mismatched-sha'}:
             preview,
         };
       },
     });
   });
   const panel=page.locator('[data-ops-panel]');
   assert.equal(await page.locator('[data-uxml-toggle]').isChecked(),false);
   assert.equal(await panel.isHidden(),true,'preview hidden while hub toggle OFF');
   await page.locator('[data-file]').setInputFiles({
     name:'preview-only-synthetic.xml',mimeType:'application/xml',
     buffer:Buffer.from(synthetic,'utf8'),
   });
   await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')
      ?.textContent?.includes('2 of 2'));
   await page.locator('[data-uxml-toggle]').check();
   await page.locator('[data-analyze]').click();
   await page.waitForFunction(()=>document.querySelector('[data-uxml-parity]')?.dataset?.parity==='EQUAL'&&
     document.querySelectorAll('[data-ops-rows] [data-op-id]').length===2);
   assert.equal(await panel.isVisible(),true);
   assert.match(await panel.locator('[data-ops-summary]').textContent(),/2 operation\(s\)/);
   assert.match(await panel.locator('[data-ops-summary]').textContent(),/0 untouched original source records/);
   assert.match(await panel.locator('[data-ops-summary]').textContent(),/1 Source Review Queue case/);
   assert.match(await panel.locator('[data-ops-rows]').textContent(),/NodeNumber: 1 → 2/);
   assert.match(await panel.locator('[data-ops-rows]').textContent(),/Position: 20 0 0 → 21 0 0/);
   assert.equal(await panel.locator('[data-op-id]').count(),2);
   assert.equal(await panel.locator('[data-auto-fix],[data-apply-second],[data-queue-apply],[data-short-drop]').count(),0);
   await panel.locator('[data-ops-kind]').selectOption('ALIAS_COINCIDENT_NODE');
   assert.equal(await panel.locator('[data-op-id]').count(),1);
   const filteredJSONDownload=page.waitForEvent('download');
   await panel.locator('[data-ops-json]').click();
   const filteredJSON=JSON.parse(await readFile(await (await filteredJSONDownload).path(),'utf8'));
   assert.deepEqual(filteredJSON.operations.map(row=>row.opId),['UXML-OP-A']);
   assert.equal(filteredJSON.summary.visibleOpsCount,1);
   assert.equal(filteredJSON.summary.totalOps,2);
   assert.equal('kind' in filteredJSON.operations[0],false);
   assert.equal('sourceActionId' in filteredJSON.operations[0],false);
   assert.equal('sourceRecordCount' in filteredJSON.summary,false);
   assert.equal('schema' in filteredJSON,false);
   assert.deepEqual(Object.keys(filteredJSON.summary.byKind).sort(),
     ['Alias coincident node','Close compatible connection ports']);
   const filteredCSVDownload=page.waitForEvent('download');
   await panel.locator('[data-ops-csv]').click();
   const filteredCSV=await readFile(await (await filteredCSVDownload).path(),'utf8');
   assert.equal(filteredCSV.trimEnd().split('\n').length,2);
   assert.match(filteredCSV,/Alias coincident node/);
   assert.doesNotMatch(filteredCSV,/Close compatible connection ports/);
   await panel.locator('[data-ops-kind]').selectOption('all');
   await panel.locator('[data-ops-search]').fill('B0:N2:S1');
   assert.equal(await panel.locator('[data-op-id]').count(),1);
   const searchedDownload=page.waitForEvent('download');
   await panel.locator('[data-ops-json]').click();
   const searched=JSON.parse(await readFile(await (await searchedDownload).path(),'utf8'));
   assert.deepEqual(searched.operations.map(row=>row.opId),['UXML-OP-B']);
   assert.equal(searched.summary.visibleOpsCount,1);
   await panel.locator('[data-ops-search]').fill('');
   await panel.locator('[data-ops-locate="UXML-OP-A"]').click();
   assert.match(await page.locator('[data-selection]').textContent(),/1 source occurrence/);
   const jsonDownload=page.waitForEvent('download');
   await panel.locator('[data-ops-json]').click();
   const json=JSON.parse(await readFile(await (await jsonDownload).path(),'utf8'));
   assert.equal(json.operations.length,2);
   assert.equal(json.operations[0].changes[0].before,'1');
   assert.equal(json.operations[0].changes[0].after,'2');
   assert.equal('sourceSha256' in json,false);
   assert.equal('sourceText' in json,false);
   const csvDownload=page.waitForEvent('download');
   await panel.locator('[data-ops-csv]').click();
   const csv=await readFile(await (await csvDownload).path(),'utf8');
   assert.equal(csv.trimEnd().split('\n').length,3,'CSV is one row per operation');
   assert.match(csv,/Alias coincident node/);
   await panel.locator('[data-ops-review]').click();
   assert.equal(await page.locator('[data-audit-filter="manual"]').getAttribute('aria-pressed'),'true');

   // Builder throws on a synthetic UXML: parity remains EQUAL, Auto-fix
   // admission remains enabled, preview fails independently and visibly.
   await page.evaluate(()=>{window.__mode='PREVIEW_FAILURE';});
   await page.locator('[data-analyze]').click();
   await page.waitForFunction(()=>document.querySelector('[data-uxml-parity]')
     ?.dataset?.parity==='EQUAL'&&document.querySelector('[data-ops-status]')
     ?.textContent?.includes('SYNTHETIC_PREVIEW_FAILURE'));
   assert.equal(await panel.locator('[data-op-id]').count(),0);
   assert.match(await panel.locator('[data-ops-status]').textContent(),
     /Preview unavailable: UXML_OPS_PREVIEW_UNAVAILABLE:RuntimeError:SYNTHETIC_PREVIEW_FAILURE/);
   assert.equal(await page.locator('[data-auto-fix-all]').isDisabled(),false,
     'read-only preview error must never disable EQUAL hub Auto-fix');
   assert.equal(await panel.locator('[data-ops-json]').isDisabled(),true);
   assert.equal(await panel.locator('[data-ops-csv]').isDisabled(),true);
   assert.equal(await panel.locator('[data-apply-second],[data-download-fix],[data-queue-apply]').count(),0);
   // Also test JS validation exceptions, not just a Python named error.
   await page.evaluate(()=>{window.__mode='PREVIEW_INVALID';});
   await page.locator('[data-analyze]').click();
   await page.waitForFunction(()=>document.querySelector('[data-uxml-parity]')
     ?.dataset?.parity==='EQUAL'&&document.querySelector('[data-ops-status]')
     ?.textContent?.includes('UXML_OPS_PREVIEW_INVALID'));
   assert.equal(await panel.locator('[data-op-id]').count(),0);
   assert.equal(await page.locator('[data-auto-fix-all]').isDisabled(),false);
   assert.match(await panel.locator('[data-ops-status]').textContent(),/Preview unavailable:/);
   await page.evaluate(()=>{window.__mode='DIFFERENT';});
   await page.locator('[data-analyze]').click();
   await page.waitForFunction(()=>document.querySelector('[data-uxml-parity]')
      ?.dataset?.parity==='DIFFERENT');
   assert.equal(await panel.locator('[data-op-id]').count(),0);
   assert.match(await panel.locator('[data-ops-status]').textContent(),/DIRECT != UXML/);
   assert.equal(await page.evaluate(()=>window.__mode),'DIFFERENT');
   assert.match(await page.locator('[data-uxml-differences]').textContent(),
     /DIRECT != UXML/);
   assert.equal(await panel.locator('[data-ops-json]').isDisabled(),true);
   assert.equal(await panel.locator('[data-ops-csv]').isDisabled(),true);
   assert.equal(await page.locator('[data-auto-fix-all]').isDisabled(),true);
   assert.equal(await panel.locator('[data-apply-second],[data-download-fix]').count(),0);

   await page.evaluate(()=>{window.__mode='UNAVAILABLE';});
   await page.locator('[data-analyze]').click();
   await page.waitForFunction(()=>document.querySelector('[data-uxml-parity]')
      ?.dataset?.parity==='UNAVAILABLE');
   assert.equal(await panel.locator('[data-op-id]').count(),0);
   assert.match(await panel.locator('[data-ops-status]').textContent(),/No operations applicable/);
   assert.equal(await panel.locator('[data-ops-json]').isDisabled(),true);
   assert.deepEqual(errors,[]);
 }finally{
   await page.close();await browser.close();
   await new Promise(done=>server.close(done));
 }
});
