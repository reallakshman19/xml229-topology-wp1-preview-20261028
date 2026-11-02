import test from 'node:test';
import assert from 'node:assert/strict';
import {runShortBulk,namedHubOwnerRefusal} from '../tabs/topology-workspace/short-bulk.mjs';

function driver(n,{cancelAt=Infinity,failAt=Infinity,hubEnabled=false,differentAt=Infinity,
  refusalAt=Infinity,refusalCode='UXML_LOSS_CONTRACT_FIELD_TOUCH',
  forgedOpAt=Infinity,receiptMutationAt=Infinity,receiptMutation=()=>{},
  throwAt=Infinity,nonCommittedAt=Infinity,
  lineageDriftAt=Infinity,validationDriftAt=Infinity}={}){
  const selectedIds=Array.from({length:n},(_,i)=>'SHORT:'+i);
  const source={name:'original.xml',sourceText:'xml|h0',sourceSha256:'h0'};
  const initial=selectedIds.map(id=>({id,eligible:true,sourceSha256:'h0',nodeKeys:[id+':S1',id+':S2']}));
  let count=0,revision=0,active=true,checkpoints=0,progress=0,equalChecks=0,leaseStarts=0,leaseEnds=0;
  const revisions=[];
  const hash=async xml=>xml.startsWith('xml|')?xml.split('|').at(-1):'full-lineage-sha';
  async function runEngine(job){
    count++;
    assert.equal(job.options.topologyShortElementRequests.length,1,'one atomic owner');
    assert.equal(job.topologyPreFinalOnly,true);
    assert.equal(job.options.useTopoFixForCii,false);
    assert.equal(job.options.topologyUxmlPreview,hubEnabled);
    assert.equal(job.options.topologyBulkSession,hubEnabled);
    assert.equal(job.options.topologyBulkSpeedProfile,hubEnabled);

    assert.equal(job.sourceRawSha256,'h'+revision);
    assert.equal(job.sourceText,'xml|h'+revision);
    if(count===failAt)return {ok:false,error:'SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED'};
    if(count===throwAt)throw Error('TOPOLOGY_WORKER_TIMEOUT: synthetic in-flight failure');
    if(hubEnabled)equalChecks++;
    const old='h'+revision,next='h'+(revision+1),id=job.options.topologyActionIds[0];
    if(count===refusalAt)return {ok:true,outputKind:'topology-sidecars',
      acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
      topoFixCommitted:false,topoFixXmlText:'',
      topologyUxmlParity:{status:'DIFFERENT',
        differences:['/patchBack: UxmlPatchError: '+refusalCode+':'+id]}};
    if(count===nonCommittedAt)return {ok:true,outputKind:'topology-sidecars',
      acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
      topoFixCommitted:false,topoFixXmlText:'',
      topologyUxmlParity:{status:'EQUAL',differences:[]}};
    revision++;
    const remaining=selectedIds.slice(count).map(id=>({
      id,eligible:true,sourceSha256:next,nodeKeys:[id+':S1',id+':S2'],
    }));
    const txn={schema:'psi116-topofix-transaction/v1',source:{sha256:old},
      sourceXmlMutated:false,committed:true,selectedActions:[id],fixedXmlSha256:next,
      operations:[{operation:'REMOVE_SELECTED_SHORT_ELEMENT_RECORD',source_node_key:id}]};
    const validation={schema:'psi116-topofix-validation/v1',sourceSha256:old,
      fixedXmlSha256:next,committed:true,summary:{blockingFailureCount:0},
      checks:[{code:'SELECTED_RECORD_REMOVAL_ACCOUNTED',blocking:true,passed:true}]};
    if(count===validationDriftAt)validation.summary.blockingFailureCount=1;
    const lineage={sourceXmlSha256:old,fixedXmlSha256:next,state:'PRE_FINAL_ONLY',
      sourceXmlMutated:false,counts:{removedSelectedShortElementOccurrences:2},
      sourceOccurrenceMap:Array.from({length:1654},(_,i)=>({sourceNodeOrdinal:i}))};
    if(count===lineageDriftAt)lineage.fixedXmlSha256='FORGED_LINEAGE_SHA';
    const request=job.options.topologyShortElementRequests[0];
    const canonical={opId:'UXML-OP-'+id,kind:'DROP_SHORT_ELEMENT',
      sourceActionId:id,fileSha256:old,
      targets:[id+':S1',id+':S2'],
      params:[{request:{id,sourceSha256:old,nodeKeys:[...request.nodeKeys]}}],
      removedWithRecord:[{recordKey:id+':S1',field:'Weight'}]};
    if(count===receiptMutationAt)receiptMutation(canonical,{id,old,request});
    return {ok:true,outputKind:'topology-sidecars',acceptedFinalTransferred:false,
      nativeCiiReleaseAuthorized:false,ciiText:null,enrichedText:'',topoFixCommitted:true,
      topologyUxmlAppliedEditOps:count===forgedOpAt?null:[canonical],
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

test('hub Apply skips one exact canonical loss refusal, continues on unchanged source',async()=>{
  const d=driver(3,{hubEnabled:true,refusalAt:2});
  const r=await d.run();
  assert.equal(r.stopReason,'COMPLETE');
  assert.equal(r.applied.length,2);
  assert.equal(r.skipped.length,1);
  assert.deepEqual(r.skipped[0],{id:'SHORT:1',
    reason:'UXML_LOSS_CONTRACT_FIELD_TOUCH:SHORT:1',sourceSha256:'h1'});
  assert.equal(r.latest.source.sourceSha256,'h2');
  assert.equal(d.checkpoints,3,'refusal creates a no-write checkpoint, plus two validated steps');
  assert.equal(r.applied[0].canonicalEditOps[0].removedWithRecord[0].field,'Weight');
  assert.equal(r.applied[1].canonicalEditOps[0].sourceActionId,'SHORT:2');
});
test('missing canonical authority receipt fails closed before even one hub write',async()=>{
  const d=driver(2,{hubEnabled:true,forgedOpAt:1});
  const r=await d.run();
  assert.equal(r.stopReason,'TRANSACTION_FAILED');
  assert.match(r.stopMessage,/UXML_SHORT_APPLY_CANONICAL_OP_RECEIPT_MISSING_OR_DRIFT/);
  assert.equal(r.applied.length,0);
  assert.equal(r.latest,null);
});
test('only source-bound UxmlPatchError veto is a skippable refusal; parity drift holds',()=>{
  const base={ok:true,topoFixCommitted:false,topoFixXmlText:'',
    acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
    topologyUxmlParity:{status:'DIFFERENT',
      differences:['/patchBack: UxmlPatchError: UXML_CLOS_WRITE_HELD:B0:N1']}};
  assert.equal(namedHubOwnerRefusal(base),'UXML_CLOS_WRITE_HELD:B0:N1');
  for(const mutant of [
    {...base,topologyUxmlParity:{status:'DIFFERENT',differences:['/uxmlReader: BAD']}},
    {...base,topologyUxmlParity:{status:'DIFFERENT',differences:['/patchBack: ValueError: UXML_CLOS_WRITE_HELD']}},
    {...base,topoFixCommitted:true},
    {...base,topoFixXmlText:'forged corrected output'},
    {...base,topologyUxmlParity:{status:'DIFFERENT',differences:[
      '/patchBack: UxmlPatchError: UXML_CLOS_WRITE_HELD:B0:N1','/findings: DIFFERENT']}},
  ])assert.equal(namedHubOwnerRefusal(mutant),null);
});

test('forged and ineligible selections are separately skipped without a Worker or write',async()=>{
  let calls=0;
  const r=await runShortBulk({
    source:{sourceSha256:'h0',sourceText:'xml|h0',name:'synthetic.xml'},
    selectedIds:['MISSING:OWNER','CLOSED:OWNER'],
    shortElements:[{id:'CLOSED:OWNER',eligible:false,
      sourceSha256:'h0',reason:'CLOS_WRITE_HELD',nodeKeys:['SYNTHETIC_KEY']}],
    hubEnabled:true,
    runEngine:async()=>{calls++;throw Error('FORGED_ITEM_REACHED_ENGINE');},
    hash:async()=>{throw Error('FORGED_ITEM_WRITTEN');},
  });
  assert.equal(r.stopReason,'COMPLETE');
  assert.equal(r.applied.length,0);
  assert.equal(r.latest,null);
  assert.equal(calls,0);
  assert.deepEqual(r.skipped.map(x=>({id:x.id,reason:x.reason})),[
    {id:'MISSING:OWNER',reason:'NOT_ELIGIBLE_ON_CURRENT_REVISION'},
    {id:'CLOSED:OWNER',reason:'CLOS_WRITE_HELD'}]);
  assert.equal(r.completed,2);
});


const allowedHubRefusalCodes=[
  'UXML_LOSS_CONTRACT_FIELD_TOUCH',
  'UXML_CLOS_WRITE_HELD',
  'UXML_SHORT_NATIVE_REFUSED',
  'UXML_SHORT_NOT_ELIGIBLE_OR_WITNESS_DRIFT',
];
const heldHubDisagreementCodes=[
  'UXML_SHORT_TARGETS_OR_PARAMS_DIFFER_FROM_AUTHORITY',
  'UXML_SHORT_DELETE_SET_MISMATCH',
  'UXML_SHORT_OWNER_DELETE_TARGET_MISMATCH',
  'UXML_SHORT_UNEXPECTED_MUTATION_KIND',
  'UXML_SHORT_PORT_FIELDS_INVALID',
  'UXML_SHORT_SOURCE_REF_NOT_FOUND',
  'UXML_SHORT_ORIGINAL_RECORD_NOT_FOUND',
  'UXML_SHORT_REQUEST_SCHEMA_INVALID',
  'UXML_SHORT_REQUEST_SELECTION_MISMATCH',
  'UXML_SHORT_REQUEST_SOURCE_OR_SELECTION_DRIFT',
  'UXML_SHORT_EXACT_ONE_OP_REQUIRED',
  'UXML_SHORT_EXACT_ONE_REQUEST_REQUIRED',
  'UXML_SHORT_NATIVE_TRANSACTION_REJECTED',
  'UXML_SHORT_KIND_REFUSED',
];
const refusalSidecar=code=>({
  ok:true,topoFixCommitted:false,topoFixXmlText:'',
  acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
  topologyUxmlParity:{status:'DIFFERENT',
    differences:['/patchBack: UxmlPatchError: '+code+':SYNTHETIC_NODE']},
});
test('exactly four source-only hub owner codes can be SKIPPED; authority disagreements HOLD',()=>{
  for(const code of allowedHubRefusalCodes)
    assert.equal(namedHubOwnerRefusal(refusalSidecar(code)),
      code+':SYNTHETIC_NODE',code);
  for(const code of heldHubDisagreementCodes)
    assert.equal(namedHubOwnerRefusal(refusalSidecar(code)),null,code);
  for(const altered of [
    {...refusalSidecar(allowedHubRefusalCodes[0]),
      topologyUxmlParity:{...refusalSidecar(allowedHubRefusalCodes[0]).topologyUxmlParity,
        status:'EQUAL'}},
    {...refusalSidecar(allowedHubRefusalCodes[0]),ok:false},
    {...refusalSidecar(allowedHubRefusalCodes[0]),
      topologyUxmlParity:{status:'DIFFERENT',differences:[
        '/patchBack: UxmlPatchError: UXML_LOSS_CONTRACT_FIELD_TOUCH:X',
        '/findings: DRIFT']}},
    {...refusalSidecar(allowedHubRefusalCodes[0]),
      topologyUxmlParity:{status:'DIFFERENT',differences:[
        '/patchBack: UxmlPatchError: UXML_LOSS_CONTRACT_FIELD_TOUCH:X\ninjected']}},
  ])assert.equal(namedHubOwnerRefusal(altered),null,'not a single isolated source veto');
});
test('TARGETS_OR_PARAMS disagreement at item 2 revokes parity; revision 1 only',async()=>{
  const d=driver(3,{hubEnabled:true,refusalAt:2,
    refusalCode:'UXML_SHORT_TARGETS_OR_PARAMS_DIFFER_FROM_AUTHORITY'});
  const r=await d.run();
  assert.equal(r.stopReason,'TRANSACTION_FAILED');
  assert.equal(r.hubMismatch,true);
  assert.equal(r.failedId,'SHORT:1');
  assert.match(r.stopMessage,
    /UXML_SHORT_PARITY_DIFFERENT: \/patchBack: UxmlPatchError: UXML_SHORT_TARGETS_OR_PARAMS_DIFFER_FROM_AUTHORITY:SHORT:1/);
  assert.equal(r.applied.length,1);
  assert.equal(r.skipped.length,0,'a hub authority disagreement is never an owner skip');
  assert.equal(r.latest.source.sourceSha256,'h1');
  assert.equal(d.checkpoints,1);
  assert.deepEqual(r.pendingIds,['SHORT:2']);
});
test('refusal checkpoint survives Cancel immediately after no-write second owner',async()=>{
  const d=driver(3,{hubEnabled:true,refusalAt:2,cancelAt:2});
  const r=await d.run();
  assert.equal(r.stopReason,'CANCELLED');
  assert.equal(r.applied.length,1);
  assert.equal(r.skipped.length,1);
  assert.equal(r.completed,2);
  assert.equal(r.latest.source.sourceSha256,'h1');
  assert.deepEqual(r.pendingIds,['SHORT:2']);
  assert.equal(d.count,2,'no third source revision requested after refusal checkpoint');
  assert.equal(d.checkpoints,2,'a refusal advances checkpoint without writing');
});
test('canonical receipt fields: each forged witness is rejected before publication',async()=>{
  const cases={
    fileSha256:op=>{op.fileSha256='FORGED_SHA';},
    opId:op=>{op.opId='UXML-OP-FORGED';},
    sourceActionId:op=>{op.sourceActionId='FORGED_ACTION';},
    requestNodeKeys:op=>{op.params[0].request.nodeKeys=['FORGED_NODE'];},
    requestSourceSha:op=>{op.params[0].request.sourceSha256='FORGED_SHA';},
    duplicateTargets:op=>{op.targets.push(op.targets[0]);},
    removedWithRecordOutsideTargets:op=>{
      op.removedWithRecord[0].recordKey='FORGED_RECORD';},
  };
  for(const [name,mutate] of Object.entries(cases)){
    const d=driver(2,{hubEnabled:true,receiptMutationAt:1,
      receiptMutation:mutate});
    const r=await d.run();
    assert.equal(r.stopReason,'TRANSACTION_FAILED',name);
    assert.equal(r.hubMismatch,true,name+' must revoke hub parity');
    assert.match(r.stopMessage,
      /UXML_SHORT_APPLY_CANONICAL_OP_RECEIPT_MISSING_OR_DRIFT/,name);
    assert.equal(r.applied.length,0,name+' must not enter applied ledger');
    assert.equal(r.skipped.length,0,name+' must not be misclassified as skippable');
    assert.equal(r.latest,null,name+' must not publish source revision');
    assert.equal(d.checkpoints,0,name+' must not create a checkpoint');
  }
});

test('all failed hub transactions HOLD; cancellation and completion do not',async()=>{
  const cases=[
    ['lineage drift',{lineageDriftAt:2},/SHORT_BULK_SOURCE_LINEAGE_OR_RECHECK_DRIFT/],
    ['validation drift',{validationDriftAt:2},/SHORT_BULK_SOURCE_LINEAGE_OR_RECHECK_DRIFT/],
    ['Worker timeout',{throwAt:2},/TOPOLOGY_WORKER_TIMEOUT/],
    ['non-committed EQUAL',{nonCommittedAt:2},/SHORT_BULK_TRANSACTION_REJECTED/],
  ];
  for(const [name,opts,error] of cases){
    const d=driver(3,{hubEnabled:true,...opts});
    const result=await d.run();
    assert.equal(result.stopReason,'TRANSACTION_FAILED',name);
    assert.equal(result.hubMismatch,true,name+' must revoke hub release authority');
    assert.match(result.stopMessage,error,name);
    assert.deepEqual(d.revisions,['h1'],name+' validated one checkpoint only');
    assert.equal(result.applied.length,1,name);
    assert.equal(result.skipped.length,0,name);
    assert.equal(result.latest.source.sourceSha256,'h1',name);
    assert.equal(result.completed,1,name);
    assert.equal(result.failedId,'SHORT:1',name);
    assert.deepEqual(result.pendingIds,['SHORT:2'],name);
  }
  const complete=await driver(2,{hubEnabled:true}).run();
  assert.equal(complete.stopReason,'COMPLETE');
  assert.equal(complete.hubMismatch,false);
  const cancelled=await driver(3,{hubEnabled:true,cancelAt:1}).run();
  assert.equal(cancelled.stopReason,'CANCELLED');
  assert.equal(cancelled.hubMismatch,false);
  const hubOff=await driver(3,{hubEnabled:false,throwAt:2}).run();
  assert.equal(hubOff.stopReason,'TRANSACTION_FAILED');
  assert.equal(hubOff.hubMismatch,false,'hub-off writer semantics remain unchanged');
});
