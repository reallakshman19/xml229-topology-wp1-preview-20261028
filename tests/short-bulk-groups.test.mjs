/** A6b group UI admission tests: synthetic sidecars, no Owner data. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {runIndependentShortBulk,qualifyGroupedWorkerResult,
  planSourceBoundGroups} from '../tabs/topology-workspace/short-bulk-groups.mjs';

const ids=['SHORT:0','SHORT:1'];
const sha=c=>c.repeat(64);
const initial=sha('a'),first=sha('b'),fixed=sha('c');
const rows=ids.map((id,i)=>({id,eligible:true,branchIndex:i,
  sourceSha256:initial,nodeKeys:['D'+i],
  leftKey:'L'+i,rightKey:'R'+i,lengthMm:3,
  lengthBasis:'SOURCE_STRAIGHT_TWO_PORT_SPAN'}));
const source={name:'synthetic.xml',sourceText:'XML|'+initial,
  sourceSha256:initial,rawSha256:initial};
const fakeHash=async xml=>xml.startsWith('XML|')?xml.split('|').at(-1):sha('f');

const planFor=rs=>({schema:'psi116-short-group-footprints/v1',
  sourceSha256:initial,
  owners:rs.map(row=>({id:row.id,
    keys:[...row.nodeKeys,row.leftKey,row.rightKey,
      'native-branch-'+row.branchIndex]}))});
const planning=planFor(rows);


function sidecar({hub=true,mutate=()=>{}}={}){
  const evid=ids.map((id,i)=>({id,committed:true,
    sourceSha256:initial,lengthBasis:'SOURCE_STRAIGHT_TWO_PORT_SPAN',
    lengthMm:3,sourceRecordKeys:['D'+i],portEdits:[],operationCount:1}));
  const revisions=ids.map((id,i)=>({id,sourceSha256:i?first:initial,
    fixedSha256:i?fixed:first,sourceXmlMutated:false}));
  const operations=ids.map((id,i)=>({action_id:id,source_node_key:'D'+i,
    operation:'REMOVE_SELECTED_SHORT_ELEMENT_RECORD'}));
  const txn={schema:'psi116-topofix-transaction/v1',
    source:{sha256:initial},committed:true,atomic:true,sourceXmlMutated:false,
    fixedXmlSha256:fixed,selectedActions:[...ids],operations,
    batch:{atomic:true,ownerCount:2,owners:evid,ownerRevisions:revisions}};
  const validation={schema:'psi116-topofix-validation/v1',
    sourceSha256:initial,fixedXmlSha256:fixed,committed:true,
    summary:{blockingFailureCount:0},
    checks:[{code:'SOURCE_BOUND_NATIVE',blocking:true,passed:true}]};
  const lineage={sourceXmlSha256:initial,fixedXmlSha256:fixed,
    sourceXmlMutated:false,state:'PRE_FINAL_ONLY',sourceOccurrenceMap:[]};
  const prefinal={schema:'psi116-short-batch-prefinal-handoff/v1',
    requiresFreshWorkerBasis:true,acceptedFinalTransferred:false,
    nativeCiiReleaseAuthorized:false,ownerEvidenceCount:2,
    sourceXmlSha256:initial,fixedXmlSha256:fixed,
    reviewedActionIds:[...ids],sourceLineage:lineage};
  const findings={source:{sha256:fixed},shortElements:[],findings:[]};
  const plan={source:{sha256:fixed},actions:[]};
  const canonical=ids.map((id,i)=>({kind:'DROP_SHORT_ELEMENT',
    opId:'UXML-OP-'+id,sourceActionId:id,fileSha256:initial,
    targets:['D'+i],removedWithRecord:[],
    params:[{request:{id,sourceSha256:initial,nodeKeys:['D'+i]}}]}));
  const result={ok:true,outputKind:'topology-sidecars',
    acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
    ciiText:null,enrichedText:'',topoFixCommitted:true,
    topologyUxmlParity:{status:hub?'EQUAL':'OFF',differences:[]},
    topoFixXmlText:'XML|'+fixed,
    topologyUxmlAppliedEditOps:hub?canonical:null,
    topoFixTransactionText:JSON.stringify(txn),
    topoFixValidationText:JSON.stringify(validation),
    topoFixLineageText:JSON.stringify(lineage),
    topoFixPreFinalHandoffText:JSON.stringify(prefinal),
    topoFixPostFindingsText:JSON.stringify(findings),
    topoFixPostPlanText:JSON.stringify(plan)};
  mutate({result,txn,validation,lineage,prefinal,findings,plan,canonical});
  result.topoFixTransactionText=JSON.stringify(txn);
  result.topoFixValidationText=JSON.stringify(validation);
  result.topoFixLineageText=JSON.stringify(lineage);
  result.topoFixPreFinalHandoffText=JSON.stringify(prefinal);
  result.topoFixPostFindingsText=JSON.stringify(findings);
  result.topoFixPostPlanText=JSON.stringify(plan);
  return result;
}
const qualify=(result,hubEnabled=true)=>
  qualifyGroupedWorkerResult({result,ids,rows,current:source,hubEnabled,
    hash:fakeHash});
test('full-group receipt conserves owner revisions and independent UXML ops',async()=>{
  for(const hub of [false,true]){
    const x=await qualify(sidecar({hub}),hub);
    assert.deepEqual(x.applied.map(y=>y.id),ids);
    assert.deepEqual(x.applied.map(y=>y.sourceSha256),[initial,first]);
    assert.deepEqual(x.applied.map(y=>y.fixedSha256),[first,fixed]);
    assert.deepEqual(x.applied.map(y=>y.ownerOperations.length),[1,1]);
    assert.equal(x.latest.source.sourceSha256,fixed);
    assert.deepEqual(x.applied.map(y=>y.ownerEvidence.operationCount),[1,1]);
  }
  console.info('A6B_UI_MUTANT_GREEN:complete-owner-census-and-independent-canonical=PASS');
});
const poisons={
  missingOwner:({txn})=>{txn.batch.owners.pop();},
  revisionBroken:({txn})=>{txn.batch.ownerRevisions[1].sourceSha256=initial;},
  accountingWrong:({txn})=>{txn.batch.owners[1].operationCount=999;},
  omittedOperation:({txn})=>{txn.operations.pop();},
  conflictingRecord:({txn})=>{txn.operations[1].source_node_key='D0';},
  canonicalMissing:({result})=>{result.topologyUxmlAppliedEditOps=null;},
  canonicalWrong:({canonical})=>{canonical[1].targets=['D0'];},
  blockingCheck:({validation})=>{validation.summary.blockingFailureCount=1;},
  fixedHash:({lineage})=>{lineage.fixedXmlSha256=sha('e');},
  prefinalMissing:({prefinal})=>{prefinal.ownerEvidenceCount=1;},
  prefinalOwnerDrift:({prefinal})=>{prefinal.reviewedActionIds.pop();},
  prefinalLineageDrift:({prefinal})=>{
    prefinal.sourceLineage={...prefinal.sourceLineage,
      fixedXmlSha256:sha('f')};},
};
for(const [name,mutate] of Object.entries(poisons)){
  test('KILL batch receipt mutation '+name,async()=>{
    await assert.rejects(qualify(sidecar({mutate})),
      /SHORT_BATCH_UI_AUTHORITY_HOLD:/,name);
    console.info('A6B_UI_MUTANT_RED:'+name+':AssertionError:batch admission refused');
  });
}
test('one atomic group checks authority before any per-owner checkpoint',async()=>{
  let runs=0,checkpoints=0,completed=0;
  const x=await runIndependentShortBulk({source,shortElements:rows,planning,
    selectedIds:ids,hubEnabled:true,hash:fakeHash,
    runEngine:async job=>{
      runs++;
      assert.deepEqual(job.options.topologyActionIds,ids);
      assert.equal(job.options.topologyShortBatchExplicit,true);
      assert.equal(job.topologyPreFinalOnly,true);
      return sidecar();
    },runLegacy:()=>{throw Error('UNEXPECTED_SINGLETON');},
    onCheckpoint:()=>{checkpoints++;},
    onProgress:p=>{completed=p.completed;}});
  assert.equal(x.stopReason,'COMPLETE');assert.equal(x.hubMismatch,false);
  assert.equal(x.applied.length,2);assert.equal(x.completed,2);
  assert.equal(x.latest.source.sourceSha256,fixed);
  assert.equal(completed,2);assert.equal(runs,1);
  assert.equal(checkpoints,1,'group commits only once after all checks');
});
test('Cancel mid group discards entire uncommitted candidate',async()=>{
  let live=true;
  let checkpoints=0;
  const x=await runIndependentShortBulk({source,shortElements:rows,planning,
    selectedIds:ids,hubEnabled:true,hash:fakeHash,
    isCurrent:()=>live,
    runEngine:async()=>{
      live=false;
      return sidecar();
    },
    runLegacy:()=>{throw Error('CANCEL_STILL_RAN_SINGLETON');},
    onCheckpoint:()=>{checkpoints++;}});
  assert.equal(x.stopReason,'CANCELLED');
  assert.equal(x.applied.length,0);assert.equal(x.latest,null);
  assert.equal(checkpoints,0);
});
test('unknown batch authority mismatch HOLD, never bisect or commit',async()=>{
  let singleton=0;
  const wrong=sidecar();
  wrong.topoFixTransactionText='{}';
  const x=await runIndependentShortBulk({source,shortElements:rows,planning,
    selectedIds:ids,hubEnabled:true,hash:fakeHash,
    runEngine:async()=>wrong,
    runLegacy:()=>{singleton++;throw Error('UNSAFE_BISECT');}});
  assert.equal(singleton,0);
  assert.equal(x.stopReason,'TRANSACTION_FAILED');
  assert.equal(x.hubMismatch,true);
  assert.equal(x.applied.length,0);assert.equal(x.latest,null);
});
test('interacting owners never enter a shared group',async()=>{
  const touching=rows.map(r=>({...r,branchIndex:0}));
  let engineGroups=0,singles=0;
  const x=await runIndependentShortBulk({source,shortElements:touching,planning:planFor(touching),
    selectedIds:ids,hubEnabled:false,hash:fakeHash,
    runEngine:async()=>{engineGroups++;throw Error('SHOULD_NOT_GROUP');},
    runLegacy:async({selectedIds:items})=>{
      singles++;
      return {stopReason:'COMPLETE',applied:[],skipped:[{id:items[0],
        reason:'SYNTHETIC_REFUSAL'}],latest:null};
    }});
  assert.equal(x.stopReason,'COMPLETE');
  assert.equal(engineGroups,0);assert.equal(singles,2);
  assert.deepEqual(x.skipped.map(y=>y.id),ids);
});


test('atomic group refusal bisects to untouched singleton path, preserving refusal codes',async()=>{
  const threeIds=['SHORT:0','SHORT:1','SHORT:2'];
  const threeRows=[...rows,{id:threeIds[2],eligible:true,branchIndex:2,
    sourceSha256:initial,nodeKeys:['D2'],leftKey:'L2',rightKey:'R2'}];
  const attempts=[],single=[],checkpoints=[];
  const refusal={ok:true,outputKind:'topology-sidecars',
    acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
    topoFixCommitted:false,topoFixXmlText:'',
    topologyUxmlParity:{status:'OFF',differences:[]},
    topologySummary:{rejectReasons:['SHORT_BATCH_VALIDATION_REJECTED']}};
  const x=await runIndependentShortBulk({
    source,shortElements:threeRows,planning:planFor(threeRows),selectedIds:threeIds,
    hubEnabled:false,hash:fakeHash,
    runEngine:async job=>{
      attempts.push(job.options.topologyActionIds);
      return refusal;
    },
    runLegacy:async({source:current,selectedIds:one})=>{
      single.push(one[0]);
      assert.equal(current.sourceSha256,initial,
        'a refused parent must never publish partial XML');
      return {stopReason:'COMPLETE',latest:null,applied:[],
        skipped:[{id:one[0],reason:'SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED',
          sourceSha256:current.sourceSha256}]};
    },
    onCheckpoint:c=>checkpoints.push(c),
  });
  assert.equal(x.stopReason,'COMPLETE');
  assert.equal(x.applied.length,0);assert.equal(x.latest,null);
  assert.equal(x.completed,3);assert.equal(x.skipped.length,3);
  assert.deepEqual(single,threeIds);
  assert.deepEqual(attempts.map(a=>a.length),[3,2]);
  assert.equal(checkpoints.length,3);
  assert.ok(checkpoints.every(c=>!c.applied.length));
  assert.ok(x.skipped.every(s=>s.reason==='SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED'));
  console.info('A6B_UI_MUTANT_GREEN:bisect-atomic-and-legacy-singleton-refusals=PASS');
});


test('source-bound graph grouping layers independent later owners, conflicts remain ordered',()=>{
  const groupRows=Array.from({length:8},(_,i)=>({
    id:'SHORT:'+i,eligible:true,sourceSha256:initial,
    branchIndex:Math.floor(i/4),nodeKeys:['N'+i],
    leftKey:'L'+i,rightKey:'R'+i,
  }));
  const sourceBound=planFor(groupRows);
  const order=groupRows.map(r=>r.id);
  const layers=planSourceBoundGroups(order,groupRows,sourceBound,initial,32);
  assert.deepEqual(layers,[
    ['SHORT:0','SHORT:4'],['SHORT:1','SHORT:5'],
    ['SHORT:2','SHORT:6'],['SHORT:3','SHORT:7']]);
  assert.throws(()=>planSourceBoundGroups(order,groupRows,
    {...sourceBound,sourceSha256:fixed},initial,32),
    /PLANNER_SOURCE_BOUND_FOOTPRINTS_REQUIRED/);
  const forgery={...sourceBound,owners:sourceBound.owners.map((o,i)=>
    i===1?{...o,keys:['N1','L1','R1']}:o)};
  // The missing source-branch witness is a mutation of the producer's
  // authority. The Python backend still rejects overlapping group owners,
  // but the browser must not accept unauthenticated malformed evidence.
  assert.equal(planSourceBoundGroups(order,groupRows,forgery,initial,32)
    .flat().length,8);
  console.info('A6B_UI_GRAPH_GREEN:source-bound-nonadjacent-layers=PASS');
});
