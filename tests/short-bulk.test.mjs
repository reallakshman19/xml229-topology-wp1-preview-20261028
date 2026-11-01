import test from 'node:test';
import assert from 'node:assert/strict';
import {runShortBulk} from '../tabs/topology-workspace/short-bulk.mjs';

function driver(n,{cancelAt=Infinity,failAt=Infinity,hubEnabled=false,differentAt=Infinity}={}){
  const selectedIds=Array.from({length:n},(_,i)=>'SHORT:'+i);
  const source={name:'original.xml',sourceText:'xml|h0',sourceSha256:'h0'};
  const initial=selectedIds.map(id=>({id,eligible:true,sourceSha256:'h0',nodeKeys:[id+':S1',id+':S2']}));
  let count=0,active=true,checkpoints=0,progress=0,equalChecks=0,leaseStarts=0,leaseEnds=0;
  const revisions=[];
  const hash=async xml=>xml.startsWith('xml|')?xml.split('|').at(-1):'full-lineage-sha';
  const oldRawSha=k=>k===1?'h0':'h'+(k-1);
  async function runEngine(job){
    count++;
    assert.equal(job.options.topologyShortElementRequests.length,1,'one atomic owner');
    assert.equal(job.topologyPreFinalOnly,true);
    assert.equal(job.options.useTopoFixForCii,false);
    assert.equal(job.options.topologyUxmlPreview,hubEnabled);
    assert.equal(job.options.topologyBulkSession,hubEnabled);
    assert.equal(job.options.topologyBulkSpeedProfile,hubEnabled);

    assert.equal(job.sourceRawSha256,oldRawSha(count));
    assert.equal(job.sourceText,'xml|h'+(count-1));
    if(count===failAt)return {ok:false,error:'SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED'};
    if(hubEnabled)equalChecks++;
    const old='h'+(count-1),next='h'+count,id=job.options.topologyActionIds[0];
    const remaining=selectedIds.slice(count).map(id=>({
      id,eligible:true,sourceSha256:next,nodeKeys:[id+':S1',id+':S2'],
    }));
    const txn={schema:'psi116-topofix-transaction/v1',source:{sha256:old},
      sourceXmlMutated:false,committed:true,selectedActions:[id],fixedXmlSha256:next,
      operations:[{operation:'REMOVE_SELECTED_SHORT_ELEMENT_RECORD',source_node_key:id}]};
    const validation={schema:'psi116-topofix-validation/v1',sourceSha256:old,
      fixedXmlSha256:next,committed:true,summary:{blockingFailureCount:0},
      checks:[{code:'SELECTED_RECORD_REMOVAL_ACCOUNTED',blocking:true,passed:true}]};
    const lineage={sourceXmlSha256:old,fixedXmlSha256:next,state:'PRE_FINAL_ONLY',
      sourceXmlMutated:false,counts:{removedSelectedShortElementOccurrences:2},
      sourceOccurrenceMap:Array.from({length:1654},(_,i)=>({sourceNodeOrdinal:i}))};
    return {ok:true,outputKind:'topology-sidecars',acceptedFinalTransferred:false,
      nativeCiiReleaseAuthorized:false,ciiText:null,enrichedText:'',topoFixCommitted:true,
      topologyUxmlParity:{status:count===differentAt?'DIFFERENT':'EQUAL',
        differences:count===differentAt?['/synthetic: perturbed UXML']:[]},
      topoFixXmlText:'xml|'+next,topoFixTransactionText:JSON.stringify(txn),
      topoFixValidationText:JSON.stringify(validation),
      topoFixLineageText:JSON.stringify(lineage),
      topoFixPreFinalHandoffText:JSON.stringify({requiresFreshWorkerBasis:true,nativeCiiReleaseAuthorized:false}),
      topoFixPostFindingsText:JSON.stringify({source:{sha256:next},findings:[],
        resolvedConnections:[],manualConnectionPorts:[],shortElements:remaining}),
      topoFixPostPlanText:JSON.stringify({source:{sha256:next},actions:[]})};
  }
  runEngine.beginBulkSession=()=>{leaseStarts++;};
  runEngine.endBulkSession=()=>{leaseEnds++;};
  const run=()=>runShortBulk({source,shortElements:initial,selectedIds,runEngine,hash,
    hubEnabled,
    isCurrent:()=>active,onCheckpoint:entry=>{checkpoints++;revisions.push(entry.latest.source.sourceSha256);if(checkpoints===cancelAt)active=false;},
    onProgress:()=>{progress++;}});
  return {run,get count(){return count;},get checkpoints(){return checkpoints;},
    get progress(){return progress;},get equalChecks(){return equalChecks;},
    get revisions(){return [...revisions];},get leaseStarts(){return leaseStarts;},
    get leaseEnds(){return leaseEnds;}};
}
test('89 of 89 requested owners run headlessly with source-bound reanalysis and compact lineage',async()=>{
 const d=driver(89);const r=await d.run();
 assert.equal(r.stopReason,'COMPLETE');assert.equal(r.applied.length,89);
 assert.equal(r.completed,89);assert.equal(r.pendingIds.length,0);
 assert.equal(r.currentEligible,0);assert.equal(r.latest.source.sourceSha256,'h89');
 assert.equal(d.count,89);assert.equal(d.checkpoints,89);
 const elapsed=r.applied.map(item=>item.elapsedMs);
 assert.equal(elapsed.length,89);
 assert.ok(elapsed.every(n=>Number.isInteger(n)&&n>=0));
 console.info('SYNTHETIC_SHORT_BULK_PER_ITEM_ELAPSED_MS: '+elapsed.join(','));
 for(const p of r.applied){
   assert.equal(p.lineage.sourceOccurrenceMap,undefined);
   assert.equal(p.lineage.sourceOccurrenceMapCount,1654);
   assert.equal(p.lineage.fullLineageSha256,'full-lineage-sha');
 }
});
test('cancellation retains only completed, verified revisions',async()=>{
 const d=driver(89,{cancelAt:3});const r=await d.run();
 assert.equal(r.stopReason,'CANCELLED');assert.equal(r.applied.length,3);
 assert.equal(r.latest.source.sourceSha256,'h3');assert.equal(d.count,3);
});
test('engine rejection retains last completed transaction and marks outstanding owners',async()=>{
 const d=driver(89,{failAt:3});const r=await d.run();
 assert.equal(r.stopReason,'TRANSACTION_FAILED');assert.equal(r.failedId,'SHORT:2');
 assert.equal(r.applied.length,2);assert.equal(r.pendingIds.length,86);
 assert.equal(r.latest.source.sourceSha256,'h2');
});

test('hub short items require EQUAL before staging any source changes',async()=>{
 const d=driver(2,{hubEnabled:true,differentAt:1});
 const result=await d.run();
 assert.equal(result.stopReason,'TRANSACTION_FAILED');
 assert.match(result.stopMessage,/UXML_SHORT_PARITY_DIFFERENT/);
 assert.equal(result.applied.length,0);
 assert.equal(result.latest,null);
 assert.equal(result.pendingIds.length,1);
});
test('hub short items stay serial and each carries fresh raw source custody',async()=>{
 const d=driver(2,{hubEnabled:true});
 const result=await d.run();
 assert.equal(result.stopReason,'COMPLETE');
 assert.equal(result.applied.length,2);
 assert.ok(result.applied.every(p=>p.hubRoute===true));
 assert.equal(result.latest.source.rawSha256,'h2');
});


test('three hub owners each commit distinct revision and pass three independent EQUAL checks',async()=>{
 const d=driver(3,{hubEnabled:true});
 const r=await d.run();
 assert.equal(r.stopReason,'COMPLETE');
 assert.equal(r.completed,3);
 assert.equal(r.applied.length,3);
 assert.equal(d.count,3);
 assert.equal(d.equalChecks,3,'each source-bound Worker job performed its own EQUAL check');
 assert.equal(d.checkpoints,3,'each item independently retained one validated checkpoint');
 assert.deepEqual(d.revisions,['h1','h2','h3']);
 assert.deepEqual(r.applied.map(x=>x.sourceSha256),['h0','h1','h2']);
 assert.deepEqual(r.applied.map(x=>x.fixedSha256),['h1','h2','h3']);
 assert.ok(r.applied.every(x=>x.validation.checks.length===1 &&
   x.validation.summary.blockingFailureCount===0));
 assert.equal(d.leaseStarts,1,'one warm lease for serial batch');
 assert.equal(d.leaseEnds,1,'lease must close even on completion');
});

test('hub mismatch at item 2 stops immediately, retaining only revision 1 for review',async()=>{
 const d=driver(3,{hubEnabled:true,differentAt:2});
 const r=await d.run();
 assert.equal(r.stopReason,'TRANSACTION_FAILED');
 assert.equal(r.failedId,'SHORT:1');
 assert.match(r.stopMessage,/UXML_SHORT_PARITY_DIFFERENT/);
 assert.equal(d.count,2,'item 3 never submitted');
 assert.equal(d.equalChecks,2,'item 2 parity was checked rather than skipped');
 assert.equal(d.checkpoints,1,'no checkpoint for failed second item');
 assert.deepEqual(d.revisions,['h1']);
 assert.equal(r.applied.length,1);
 assert.equal(r.latest.source.sourceSha256,'h1');
 assert.deepEqual(r.pendingIds,['SHORT:2']);
 assert.equal(d.leaseStarts,1);
 assert.equal(d.leaseEnds,1,'failed batch releases its warm lease');
});
