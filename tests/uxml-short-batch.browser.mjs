/** A6b real Chromium/Pyodide group-vs-serial timing and independent parity.
 * Generated source only; uses production Worker package, no source patching.
 * The opt-in batch stage is NOT enabled from the workspace UI in this test.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {chromium} from 'playwright';

const root=path.resolve(process.cwd(),'dist');
const mime={'.html':'text/html','.mjs':'text/javascript','.js':'text/javascript',
  '.json':'application/json','.css':'text/css','.wasm':'application/wasm',
  '.zip':'application/zip','.py':'text/plain'};
const node=(n,type,ref,end,x)=>
  '<Node><NodeNumber>'+n+'</NodeNumber><ComponentType>'+type+
  '</ComponentType><ComponentRefNo>'+ref+'</ComponentRefNo><Endpoint>'+end+
  '</Endpoint><Position>'+x+' 0 0</Position><OutsideDiameter>100</OutsideDiameter>'+
  '<BendRadius>0</BendRadius><AlphaAngle>0</AlphaAngle></Node>';
function fixture(count){
  return '<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'+
    Array.from({length:count},(_,i)=>{
      const x=i*1500,k=i*100,r=String(i);
      return '<Branch><Branchname>A6B-SYNTHETIC-'+i+'</Branchname>'+
        node(10+k,'PIPE','P'+r,1,x)+node(20+k,'PIPE','P'+r,2,x+100)+
        node(-1,'GASK','SHORT'+r,1,x+100)+node(30+k,'RIGID','SHORT'+r,2,x+103)+
        node(-1,'FLAN','F'+r,1,x+103)+node(40+k,'RIGID','F'+r,2,x+189)+
        '</Branch>';
    }).join('')+'</PipeStressExport>';
}
const server=createServer(async(req,res)=>{
  try{
    const rel=decodeURIComponent(new URL(req.url,'http://localhost').pathname)
      .replace(/^\/+/, '')||'index.html';
    const file=path.resolve(root,rel);
    if(!file.startsWith(root+path.sep)){res.writeHead(403).end();return;}
    res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream'});
    res.end(await readFile(file));
  }catch(e){res.writeHead(404).end(String(e));}
});

test('A6b generated 5-owner batch real Pyodide direct and UXML equals serial',
     {timeout:540000},async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:1200,height:800}});
  const errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  try{
    const url='http://127.0.0.1:'+server.address().port+'/index.html';
    await page.goto(url);
    const outcomes=await page.evaluate(async xml=>{
      const {createTopologyWorkerClient}=await import(
        '/tabs/topology-workspace/topology-worker-client.mjs');
      const client=createTopologyWorkerClient();
      const sha=async value=>{
        const hash=await crypto.subtle.digest(
          'SHA-256',new TextEncoder().encode(value));
        return [...new Uint8Array(hash)].map(b=>b.toString(16)
          .padStart(2,'0')).join('');
      };
      const fixedJobs={};
      const groups=[];
      try{
        for(const hub of [false,true]){
          const initialSha=await sha(xml);
          const base={sourceKind:'xml',sourceText:xml,
            sourceName:'a6b-generated.xml',
            topologyPreFinalOnly:true,sourceRawSha256:initialSha};
          const initial=await client.run({...base,options:{
            outputMode:'enriched-only',analyzeTopology:true,
            generateTopoFix:false,useTopoFixForCii:false,
            topologyUxmlPreview:hub}});
          if(initial.ok!==true)throw Error('A6B_ANALYZE_FAILED:'+initial.error);
          if(hub&&initial.topologyUxmlParity?.status!=='EQUAL')
            throw Error('A6B_INITIAL_HUB_PARITY_NOT_EQUAL');
          const rows=JSON.parse(initial.topologyFindingsText).shortElements
            .filter(r=>r.eligible&&r.componentRefNo.startsWith('SHORT'));
          if(rows.length!==5)throw Error('A6B_FIVE_ELIGIBLE_REQUIRED:'+rows.length);
          const requests=rows.map(r=>({
            id:r.id,sourceSha256:initialSha,nodeKeys:[...r.nodeKeys]}));
          const options={
            outputMode:'enriched-only',analyzeTopology:true,
            generateTopoFix:true,useTopoFixForCii:false,
            topologyUxmlPreview:hub,topologyBulkSpeedProfile:true,
            topologyActionIds:rows.map(r=>r.id),
            topologyShortElementRequests:requests,
            topologyShortBatchExplicit:true};
          const started=performance.now();
          const grouped=await client.run({...base,options});
          const groupElapsedMs=performance.now()-started;
          if(grouped.ok!==true||!grouped.topoFixCommitted)
            throw Error('A6B_GROUP_NOT_COMMITTED:'+
              (grouped.error||grouped.topologyUxmlParity?.differences?.join(';')||'unknown'));
          if(hub&&grouped.topologyUxmlParity?.status!=='EQUAL')
            throw Error('A6B_GROUP_UXML_PARITY_FAILED');
          const groupTxn=JSON.parse(grouped.topoFixTransactionText);
          const handoff=JSON.parse(grouped.topoFixPreFinalHandoffText);
          if(groupTxn.batch?.ownerCount!==5||groupTxn.batch?.ownerRevisions?.length!==5)
            throw Error('A6B_GROUP_OWNER_REVISIONS_INCOMPLETE');
          if(handoff.ownerEvidenceCount!==5||handoff.nativeCiiReleaseAuthorized!==false)
            throw Error('A6B_PREFINAL_COUNT_OR_RELEASE_DRIFT');
          if(hub&&grouped.topologyUxmlAppliedEditOps?.length!==5)
            throw Error('A6B_GROUP_CANONICAL_OPS_MISSING');
          let working=xml;
          const serialStarted=performance.now();
          const serialTimings=[];
          for(const row of rows){
            const currentSha=await sha(working);
            const oldOptions={...options,
              topologyShortBatchExplicit:false,
              topologyActionIds:[row.id],
              topologyShortElementRequests:[{
                id:row.id,sourceSha256:currentSha,
                nodeKeys:[...row.nodeKeys]}]};
            const t=performance.now();
            const one=await client.run({...base,sourceText:working,
              sourceRawSha256:currentSha,options:oldOptions});
            serialTimings.push({owner:row.id,elapsedMs:performance.now()-t});
            if(one.ok!==true||!one.topoFixCommitted)
              throw Error('A6B_SINGLE_OWNER_NOT_COMMITTED:'+row.id+':'+one.error);
            if(hub&&one.topologyUxmlParity?.status!=='EQUAL')
              throw Error('A6B_SINGLE_HUB_PARITY:'+row.id);
            working=one.topoFixXmlText;
          }
          const serialElapsedMs=performance.now()-serialStarted;
          fixedJobs[hub?'uxml':'direct']={
            exactXml:working===grouped.topoFixXmlText,
            groupElapsedMs,serialElapsedMs,
            groupPhases:grouped.topologyBulkTiming,
            groupOperations:groupTxn.summary?.appliedOperationCount,
            ownerEvidence:groupTxn.batch.ownerCount,
            serialTimings,
            hubParity:grouped.topologyUxmlParity?.status,
          };
          if(working!==grouped.topoFixXmlText)
            throw Error('A6B_REAL_PYODIDE_BATCH_BYTES_DIFFERENT');
          groups.push(hub?'UXML':'NATIVE');
        }
      }finally{client.dispose();}
      return {tested:groups,results:fixedJobs};
    },fixture(5));
    assert.deepEqual(outcomes.tested,['NATIVE','UXML']);
    for(const [route,result] of Object.entries(outcomes.results)){
      assert.equal(result.exactXml,true,route);
      assert.equal(result.ownerEvidence,5);
      assert.equal(result.serialTimings.length,5);
      assert.ok(result.groupElapsedMs>0&&result.serialElapsedMs>0);
      console.info('A6B_REAL_PYODIDE_BATCH_TIMING_'+route.toUpperCase()+'='+
        JSON.stringify(result));
    }
    assert.deepEqual(errors,[]);
  }finally{
    await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
});
