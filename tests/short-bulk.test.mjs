import test from 'node:test';
import assert from 'node:assert/strict';
import {runShortBulk} from '../tabs/topology-workspace/short-bulk.mjs';

function driver(n,{cancelAt=Infinity,failAt=Infinity}={}){
  const selectedIds=Array.from({length:n},(_,i)=>'SHORT:'+i);
  const source={name:'original.xml',sourceText:'xml|h0',sourceSha256:'h0'};
  const initial=selectedIds.map(id=>({id,eligible:true,sourceSha256:'h0',nodeKeys:[id+':S1',id+':S2']}));
  let count=0,active=true,checkpoints=0,progress=0;
  const hash=async xml=>xml.startsWith('xml|')?xml.split('|').at(-1):'full-lineage-sha';
  async function runEngine(job){
    count++;
    assert.equal(job.options.topologyShortElementRequests.length,1,'one atomic owner');
    assert.equal(job.topologyPreFinalOnly,true);
    assert.equal(job.options.useTopoFixForCii,false);
    assert.equal(job.sourceText,'xml|h'+(count-1));
    if(count===failAt)return {ok:false,error:'SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED'};
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
      topoFixXmlText:'xml|'+next,topoFixTransactionText:JSON.stringify(txn),
      topoFixValidationText:JSON.stringify(validation),
      topoFixLineageText:JSON.stringify(lineage),
      topoFixPreFinalHandoffText:JSON.stringify({requiresFreshWorkerBasis:true,nativeCiiReleaseAuthorized:false}),
      topoFixPostFindingsText:JSON.stringify({source:{sha256:next},findings:[],
        resolvedConnections:[],manualConnectionPorts:[],shortElements:remaining}),
      topoFixPostPlanText:JSON.stringify({source:{sha256:next},actions:[]})};
  }
  const run=()=>runShortBulk({source,shortElements:initial,selectedIds,runEngine,hash,
    isCurrent:()=>active,onCheckpoint:()=>{checkpoints++;if(checkpoints===cancelAt)active=false;},
    onProgress:()=>{progress++;}});
  return {run,get count(){return count;},get checkpoints(){return checkpoints;},get progress(){return progress;}};
}
test('89 of 89 requested owners run headlessly with source-bound reanalysis and compact lineage',async()=>{
 const d=driver(89);const r=await d.run();
 assert.equal(r.stopReason,'COMPLETE');assert.equal(r.applied.length,89);
 assert.equal(r.completed,89);assert.equal(r.pendingIds.length,0);
 assert.equal(r.currentEligible,0);assert.equal(r.latest.source.sourceSha256,'h89');
 assert.equal(d.count,89);assert.equal(d.checkpoints,89);
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
