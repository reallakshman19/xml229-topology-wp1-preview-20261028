/** Real Chromium + real pinned Worker: five synthetic short owners in two
 * cancellable read-only preview jobs. User cancellation must keep the exact
 * source and selection, never grant partial Apply.
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

test('five real Worker owners: progress 4/5, exact aggregated Apply gate and late cancel',
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
      const client=createTopologyWorkerClient();
      const fixture={chunkSizes:[],holdSecond:true,release:null,reject:null,client};
      const runEngine=async job=>{
        const part=job.options?.topologyShortPreviewRequests||[];
        if(part.length){
          fixture.chunkSizes.push(part.length);
          if(fixture.holdSecond&&fixture.chunkSizes.length%2===0){
            await new Promise((resolve,reject)=>{
              fixture.release=resolve;fixture.reject=reject;
            });
          }
        }
        return client.run(job);
      };
      const cancelEngine=()=>{
        if(fixture.reject){
          const reject=fixture.reject;
          fixture.reject=null;fixture.release=null;
          reject(Error('SYNTHETIC_PREVIEW_CANCELLED'));
        }
        client.cancel();
      };
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
    await page.waitForFunction(()=>window.__scaleFixture.chunkSizes.length===2,null,
      {timeout:120000});
    assert.deepEqual(await page.evaluate(()=>window.__scaleFixture.chunkSizes),[4,1]);
    assert.match(await page.locator('[data-short-hub-status]').textContent(),/Previewing 4 of 5/);
    assert.equal(await page.locator('[data-cancel]').isEnabled(),true);
    assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true);
    assert.match(await page.locator('[data-short-hub-preview]').getAttribute('title'),
      /Finish or cancel the active preview first/);
    await page.evaluate(()=>window.__scaleFixture.release());
    await page.waitForFunction(()=>document.querySelector('[data-short-hub-status]')
      ?.textContent?.includes('5 ready / 0 refused'),null,{timeout:120000});
    assert.equal(await page.locator('[data-run-short-drop]').isEnabled(),true);
    assert.equal(await page.locator('[data-ops-rows] [data-op-id]')
      .filter({hasText:'Drop selected short component'}).count(),5);
    assert.equal(await page.locator('[data-download-working]').isDisabled(),true,
      'preview cannot grant a corrected download');

    // Selection change revokes Apply. A second preview is cancelled between
    // chunks and a delayed/rejected response must not revive Apply.
    await page.locator('[data-short-index="0"]').uncheck();
    await page.locator('[data-short-index="0"]').check();
    assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true);
    await page.locator('[data-short-hub-preview]').click();
    await page.waitForFunction(()=>window.__scaleFixture.chunkSizes.length===4,null,
      {timeout:120000});
    assert.match(await page.locator('[data-short-hub-status]').textContent(),/Previewing 4 of 5/);
    await page.locator('[data-cancel]').click();
    await page.waitForFunction(()=>document.querySelector('main')
      ?.getAttribute('aria-busy')==='false',null,{timeout:10000});
    assert.match(await page.locator('[data-short-hub-status]').textContent(),/CANCELLED/);
    assert.equal(await page.locator('[data-short-index]:checked').count(),5);
    assert.equal(await page.locator('[data-run-short-drop]').isDisabled(),true);
    assert.equal(await page.locator('[data-download-working]').isDisabled(),true);
    assert.equal((await page.evaluate(()=>window.__scaleFixture.workspace.getState())).revision,0);
    assert.deepEqual(errors,[]);
    console.log('SYNTHETIC_SHORT_PREVIEW_CHUNK_BROWSER_PASS '+JSON.stringify({
      selected:5,chunkSizes:[4,1,4,1],cancelledWithoutApply:true,
      originalSourceUnchanged:true,pageErrors:errors,
    }));
  }finally{
    await page.close();await browser.close();await new Promise(done=>server.close(done));
  }
});
