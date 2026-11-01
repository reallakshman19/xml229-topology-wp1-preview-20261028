/** UXML-UI DIFFERENT gate: real Chromium DOM, mocked/injected runEngine.
 * Deliberately NOT part of tests/*.test.mjs: requires playwright installation
 * and dist/ runtime assembled by repair-validation workflow.
 */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';

const ROOT=path.resolve(process.cwd(),'dist');
const TYPES={'.html':'text/html;charset=utf-8','.mjs':'text/javascript;charset=utf-8',
 '.js':'text/javascript;charset=utf-8','.css':'text/css;charset=utf-8',
 '.wasm':'application/wasm','.zip':'application/zip','.py':'text/plain;charset=utf-8'};
const synthetic='<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+
 '<Branch><Branchname>SYNTHETIC</Branchname>'+
 '<Node><NodeNumber>1</NodeNumber><ComponentType>PIPE</ComponentType>'+
 '<Endpoint>1</Endpoint><Position>0 0 0</Position></Node>'+
 '<Node><NodeNumber>2</NodeNumber><ComponentType>PIPE</ComponentType>'+
 '<Endpoint>2</Endpoint><Position>20 0 0</Position></Node>'+
 '</Branch></PipeStressExport>';

test('injected runEngine DIFFERENT shows exact paths, disables all hub Auto-fix/download',async()=>{
 const server=createServer(async(req,res)=>{
   try{
     const relative=decodeURIComponent(new URL(req.url,'http://localhost').pathname)
       .replace(/^\/+/,'')||'index.html';
     const file=path.resolve(ROOT,relative);
     if(!file.startsWith(ROOT+path.sep)){res.writeHead(403).end();return;}
     const contents=await readFile(file);
     res.setHeader('Content-Type',TYPES[path.extname(file)]||'application/octet-stream');
     res.writeHead(200).end(contents);
   }catch(error){res.writeHead(404).end(String(error));}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1100,height:800}});
 const errors=[];
 page.on('pageerror',error=>errors.push(String(error)));
 try{
   // Suppress auto-mount so the test can inject its runEngine through the
   // exported mountTopologyWorkspace entrypoint, not monkeypatch a Worker.
   await page.route('**/index.html',async route=>{
     const response=await route.fetch();
     const original=await response.text();
     const html=original.replace(
       '<script type="module" src="./tabs/topology-workspace/workspace-app.mjs"></script>','');
     assert.notEqual(html,original,'auto-mount script must be removed');
     await route.fulfill({response,body:html});
   });
   await page.goto('http://127.0.0.1:'+server.address().port+'/index.html');
   await page.evaluate(async()=>{
     const root=document.querySelector('#xml229-topology-workspace');
     root.id='mocked-root';
     const {mountTopologyWorkspace}=await import('/tabs/topology-workspace/workspace-app.mjs');
     root.id='xml229-topology-workspace';
     window.__mockWorkspace=mountTopologyWorkspace(root,{
       runEngine:async job=>{
         const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(job.sourceText));
         const sha=[...new Uint8Array(digest)]
           .map(v=>v.toString(16).padStart(2,'0')).join('');
         const reason='/findings/synthetic/position: direct=20.0 uxml=21.0';
         const findings={source:{sha256:sha},findings:[{
           finding_id:'F-SYNTH',code:'NEAR_MISS_PIPE_JOINT',node_keys:['B0:N1:S0'],
           severity:'WARNING',blocking:false,message:'Synthetic mismatch'
         }]};
         const plan={source:{sha256:sha},actions:[{
           action_id:'ACT-SYNTH',status:'PROPOSED',confidence:0.99,
           disposition:'CLOSE_PORT_CONNECTION',blockers:[],finding_ids:['F-SYNTH'],
           proposed_changes:[{field:'Position',value:'synthetic'}]
         }]};
         return {ok:true,outputKind:'topology-sidecars',
           acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
           topoFixCommitted:false,topoFixXmlText:'',
           ciiText:null,enrichedText:'',
           topologyFindingsText:JSON.stringify(findings),
           topologyFixPlanText:JSON.stringify(plan),
           topologyUxmlParity:{status:'DIFFERENT',differences:[reason]}};
       },
       cancelEngine:()=>{},
     });
   });
   await page.locator('[data-file]').setInputFiles({
     name:'uxml-ui-different-synthetic.xml',mimeType:'application/xml',
     buffer:Buffer.from(synthetic,'utf8')
   });
   await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')
     ?.textContent?.includes('2 of 2'));
   assert.equal(await page.locator('[data-uxml-toggle]').isChecked(),false);
   await page.locator('[data-uxml-toggle]').check();
   await page.locator('[data-analyze]').click();
   await page.waitForFunction(()=>document.querySelector('[data-uxml-parity]')
     ?.dataset?.parity==='DIFFERENT',null,{timeout:30000});
   assert.equal(await page.locator('[data-uxml-parity]').getAttribute('data-parity'),
     'DIFFERENT');
   assert.match(await page.locator('[data-uxml-differences]').textContent(),
     /\/findings\/synthetic\/position: direct=20.0 uxml=21.0/);
   // Parity is emitted before the public analysis view finishes its render.
   // Wait for a completed, source-bound plan before checking eligible controls.
   await page.waitForFunction(()=>
     document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.')&&
     document.querySelector('[data-auto-fix-all]')?.textContent?.includes('1 actions'),
     null,{timeout:30000});
   assert.match(await page.locator('[data-auto-fix-all]').textContent(),/1 actions/);
   assert.equal(await page.locator('[data-auto-fix-all]').isDisabled(),true);
   assert.equal(await page.locator('[data-download-working]').isDisabled(),true);
   assert.equal(await page.locator('[data-download-resolutions]').isDisabled(),true);
   assert.equal(await page.locator('[data-download-fix]').count(),0);
   assert.equal(await page.evaluate(()=>
     window.__mockWorkspace.getState().hubParity),'DIFFERENT');
   assert.deepEqual(errors,[]);
 }finally{
   await page.close();await browser.close();
   await new Promise(resolve=>server.close(resolve));
 }
});
