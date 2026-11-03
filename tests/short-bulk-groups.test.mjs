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

const sourceRecordsFor=rs=>rs.flatMap(row=>
  [...row.nodeKeys,row.leftKey,row.rightKey].map(key=>({
    key,branchIndex:row.branchIndex,nodeNumber:null,position:null})));
const planFor=rs=>({schema:'psi116-short-group-footprints/v1',
  sourceSha256:initial,
  owners:rs.map(row=>({id:row.id,
    keys:[...new Set(rs.filter(other=>
      other.branchIndex===row.branchIndex).flatMap(other=>
        [...other.nodeKeys,other.leftKey,other.rightKey]))]}))});
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
    batch:{atomic:true,ownerCount:2,owners:evid,ownerRevisions:revisions,
      sourceFootprints:ids.map((id,i)=>({id,keys:['D'+i,'L'+i,'R'+i]}))}};
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
  const x=await runIndependentShortBulk({source,shortElements:rows,planning,sourceRecords:sourceRecordsFor(rows),
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
  const x=await runIndependentShortBulk({source,shortElements:rows,planning,sourceRecords:sourceRecordsFor(rows),
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
  const x=await runIndependentShortBulk({source,shortElements:rows,planning,sourceRecords:sourceRecordsFor(rows),
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
  const x=await runIndependentShortBulk({source,shortElements:touching,planning:planFor(touching),sourceRecords:sourceRecordsFor(touching),
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
    source,shortElements:threeRows,planning:planFor(threeRows),sourceRecords:sourceRecordsFor(threeRows),selectedIds:threeIds,
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
  const layers=planSourceBoundGroups(order,groupRows,sourceBound,initial,32,sourceRecordsFor(groupRows));
  assert.deepEqual(layers,[
    ['SHORT:0','SHORT:4'],['SHORT:1','SHORT:5'],
    ['SHORT:2','SHORT:6'],['SHORT:3','SHORT:7']]);
  assert.throws(()=>planSourceBoundGroups(order,groupRows,
    {...sourceBound,sourceSha256:fixed},initial,32,sourceRecordsFor(groupRows)),
    /PLANNER_SOURCE_BOUND_FOOTPRINTS_REQUIRED/);
  const forgery={...sourceBound,owners:sourceBound.owners.map((o,i)=>
    i===1?{...o,keys:['N1','L1','R1']}:o)};
  // The missing source-branch witness is a mutation of the producer's
  // authority. The Python backend still rejects overlapping group owners,
  // but the browser must not accept unauthenticated malformed evidence.
  assert.throws(()=>
    planSourceBoundGroups(order,groupRows,forgery,initial,32,
      sourceRecordsFor(groupRows)),
    /PLANNER_NATIVE_FOOTPRINT_UNDERCOVERS_SOURCE/);
  console.info('A6B_UI_GRAPH_RED:source-branch-footprint-omitted:AssertionError:PLANNER_NATIVE_FOOTPRINT_UNDERCOVERS_SOURCE');
  console.info('A6B_UI_GRAPH_GREEN:source-bound-nonadjacent-layers=PASS');
});


test('failed first split child never becomes CANCELLED and second child never runs',async()=>{
 const four=[...rows,
  {...rows[0],id:'SHORT:2',nodeKeys:['D2'],leftKey:'L2',
    rightKey:'R2'},
  {...rows[1],id:'SHORT:3',nodeKeys:['D3'],leftKey:'L3',
    rightKey:'R3'}];
 const requested=four.map(x=>x.id);
 const groups=planSourceBoundGroups(requested,four,planFor(four),
   initial,32,sourceRecordsFor(four));
 assert.deepEqual(groups,[requested.slice(0,2),requested.slice(2)]);
 let engineCalls=0,legacyCalls=[];
 const result=await runIndependentShortBulk({
  source,shortElements:four,selectedIds:requested,
  planning:planFor(four),sourceRecords:sourceRecordsFor(four),
  hash:fakeHash,hubEnabled:false,
  runEngine:async()=>{
   engineCalls++;
   return sidecar({hub:false,mutate:({findings})=>{
    findings.shortElements=[
      {...four[2],eligible:false,sourceSha256:fixed},
      {...four[3],eligible:true,sourceSha256:fixed}];
   }});
  },
  runLegacy:async({selectedIds})=>{
   legacyCalls.push(...selectedIds);
   return {stopReason:'TRANSACTION_FAILED',
     stopMessage:'SYNTHETIC_SINGLETON_AUTHORITY_STOP',
     latest:null,applied:[],skipped:[]};
  },
 });
 assert.equal(engineCalls,1,'only first committed group runs');
 assert.deepEqual(legacyCalls,['SHORT:2'],
   'second bisect child must never run after unknown singleton failure');
 assert.equal(result.stopReason,'TRANSACTION_FAILED',
   'failure must not be downgraded to CANCELLED');
 assert.equal(result.failedId,'SHORT:2');
 assert.deepEqual(result.pendingIds,['SHORT:3']);
 assert.deepEqual(result.applied.map(x=>x.id),requested.slice(0,2));
 console.info('A6B_UI_MUTANT_GREEN:bisect-first-failure-never-cancel-downgrade=PASS');
});


test('cross-branch VALV finite closure is required by JS native minimum',()=>{
  const chainRecords=[
    {key:'A10',branchIndex:0,nodeNumber:10,type:'PIPE',refNo:'PA',position:{x:0,y:0,z:0}},
    {key:'A20',branchIndex:0,nodeNumber:20,type:'PIPE',refNo:'PA',position:{x:100,y:0,z:0}},
    {key:'A-SHORT',branchIndex:0,nodeNumber:-1,type:'GASK',refNo:'SA',position:{x:103,y:0,z:0}},
    {key:'V20',branchIndex:1,nodeNumber:20,type:'VALV',refNo:'BRIDGE',position:{x:100,y:0,z:0}},
    {key:'V50',branchIndex:1,nodeNumber:50,type:'VALV',refNo:'BRIDGE',position:{x:100,y:500,z:0}},
    {key:'B50',branchIndex:2,nodeNumber:50,type:'PIPE',refNo:'PB',position:{x:100,y:500,z:0}},
    {key:'B60',branchIndex:2,nodeNumber:60,type:'PIPE',refNo:'PB',position:{x:200,y:500,z:0}},
    {key:'B-SHORT',branchIndex:2,nodeNumber:-1,type:'GASK',refNo:'SB',position:{x:203,y:500,z:0}},
  ];
  const chainRows=[
    {id:'SHORT:A',eligible:true,sourceSha256:initial,
      branchIndex:0,nodeKeys:['A-SHORT'],leftKey:'A20',rightKey:'A10'},
    {id:'SHORT:B',eligible:true,sourceSha256:initial,
      branchIndex:2,nodeKeys:['B-SHORT'],leftKey:'B60',rightKey:'B50'},
  ];
  const allKeys=chainRecords.map(r=>r.key);
  const safe={schema:'psi116-short-group-footprints/v1',sourceSha256:initial,
    owners:chainRows.map(r=>({id:r.id,keys:allKeys}))};
  const result=planSourceBoundGroups(chainRows.map(r=>r.id),chainRows,
    safe,initial,32,chainRecords);
  assert.deepEqual(result,[['SHORT:A'],['SHORT:B']]);
  const incomplete={...safe,owners:safe.owners.map((o,i)=>
    i===0?{...o,keys:o.keys.filter(k=>!['V50','B50'].includes(k))}:o)};
  assert.throws(()=>planSourceBoundGroups(chainRows.map(r=>r.id),chainRows,
    incomplete,initial,32,chainRecords),
    /PLANNER_NATIVE_FOOTPRINT_UNDERCOVERS_SOURCE/);
  console.info('A6B_R1_JS_GREEN:cross-branch-finite-closure-native-minimum=PASS');
});

test('JS 25mm contact minimum rejects disjoint undercovered native zones',()=>{
  const a={id:'SHORT:A',eligible:true,sourceSha256:initial,branchIndex:0,
    nodeKeys:['A1'],leftKey:'A2',rightKey:'A3'};
  const b={id:'SHORT:B',eligible:true,sourceSha256:initial,branchIndex:1,
    nodeKeys:['B1'],leftKey:'B2',rightKey:'B3'};
  const records=[...sourceRecordsFor([a,b])].map(r=>({
    ...r,type:'PIPE',refNo:r.branchIndex?'PB':'PA',
    position:{x:r.key.endsWith('1')?100:200,y:r.branchIndex?20:0,z:0},
  }));
  const safe={schema:'psi116-short-group-footprints/v1',sourceSha256:initial,
    owners:[a,b].map(r=>({id:r.id,keys:records.map(v=>v.key)}))};
  assert.deepEqual(planSourceBoundGroups([a.id,b.id],[a,b],safe,
    initial,32,records),[[a.id],[b.id]]);
  const broken={...safe,owners:[a,b].map(r=>({id:r.id,keys:records
    .filter(v=>v.branchIndex===r.branchIndex).map(v=>v.key)}))};
  assert.throws(()=>planSourceBoundGroups([a.id,b.id],[a,b],broken,
    initial,32,records),/PLANNER_NATIVE_FOOTPRINT_UNDERCOVERS_SOURCE/);
  console.info('A6B_R1_JS_GREEN:twenty-mm-contact-native-minimum=PASS');
});

test('isCurrent after async qualification must discard candidate, Node kill',async()=>{
  const state=()=>({source,shortElements:rows,planning,
    sourceRecords:sourceRecordsFor(rows),selectedIds:ids,hubEnabled:false,
    runEngine:async()=>sidecar({hub:false}),
    runLegacy:()=>{throw Error('LEGACY_NOT_EXPECTED');}});
  let live=true,hashes=0,checkpoints=0;
  const hash=async input=>{
    if(++hashes===2)live=false; // final lineage hash inside qualification
    return fakeHash(input);
  };
  const good=await runIndependentShortBulk({...state(),hash,
    isCurrent:()=>live,onCheckpoint:()=>{checkpoints++;}});
  assert.equal(good.stopReason,'CANCELLED');
  assert.equal(good.applied.length,0);assert.equal(checkpoints,0);
  console.info('A6B_R1_JS_GREEN:post-qualify-epoch-guard=PASS');
  const {readFile}=await import('node:fs/promises');
  // core.autocrlf=true can yield CRLF on Windows. Normalize only the
  // source-text MUTANT fixture, never production output or XML bytes.
  const original=(await readFile(new URL('../tabs/topology-workspace/short-bulk-groups.mjs',
    import.meta.url),'utf8')).replace(/\r\n/g,'\n');
  const target="if(!isCurrent()){stopReason='CANCELLED';return;}\n      current=validated.source;";
  assert.ok(original.includes(target),'post-qualification guard must exist');
  const changed=original.replace(target,'current=validated.source;');
  const mutant=await import('data:text/javascript;base64,'+
    Buffer.from(changed).toString('base64'));
  live=true;hashes=0;
  const bad=await mutant.runIndependentShortBulk({...state(),hash,
    isCurrent:()=>live});
  await assert.rejects(async()=>assert.equal(bad.stopReason,'CANCELLED',
    'POST_QUALIFY_ISCURRENT_MUTANT_COMMITTED'));
  console.info('A6B_R1_JS_RED:isCurrent-after-qualify-removed:AssertionError:'+
    'POST_QUALIFY_ISCURRENT_MUTANT_COMMITTED');
});

test('source record interaction gate has independent Node mutation kill',async()=>{
  const collision=sidecar({hub:false,mutate:({txn})=>{
    for(let i=0;i<2;i++){
      // Both owners' footprints DO contain this key, so the independent
      // duplicate-write gate (not the earlier undercoverage guard) is tested.
      txn.batch.sourceFootprints[i].keys.push('SHARED');
      txn.operations.push({action_id:ids[i],source_node_key:'SHARED',
        operation:'CLOSE_COMPONENT_PORT'});
      txn.batch.owners[i].portEdits.push({key:'SHARED',before:{},after:{}});
      txn.batch.owners[i].operationCount=2;
    }
  }});
  await assert.rejects(qualify(collision,false),
    /BATCH_INTERACTING_SOURCE_RECORDS/);
  console.info('A6B_R1_JS_GREEN:interacting-source-records-veto=PASS');
  const {readFile}=await import('node:fs/promises');
  // core.autocrlf=true can yield CRLF on Windows. Normalize only the
  // source-text MUTANT fixture, never production output or XML bytes.
  const original=(await readFile(new URL('../tabs/topology-workspace/short-bulk-groups.mjs',
    import.meta.url),'utf8')).replace(/\r\n/g,'\n');
  const target="requireBatch(!allAffected.has(op.source_node_key),\n        'BATCH_INTERACTING_SOURCE_RECORDS');";
  assert.ok(original.includes(target),'runtime record interaction gate required');
  const mutant=await import('data:text/javascript;base64,'+
    Buffer.from(original.replace(target,'// mutated duplicate guard')).toString('base64'));
  const mutated=await mutant.qualifyGroupedWorkerResult({
    result:collision,ids,rows,current:source,hubEnabled:false,hash:fakeHash});
  await assert.rejects(async()=>assert.fail(
    'BATCH_INTERACTING_SOURCE_RECORDS_MUTANT_ACCEPTED:'+mutated.applied.length));
  console.info('A6B_R1_JS_RED:interacting-source-records-guard-removed:AssertionError:'+
    'BATCH_INTERACTING_SOURCE_RECORDS_MUTANT_ACCEPTED');
});

test('Windows CRLF source-text mutation probes normalize safely',async()=>{
  const {readFile}=await import('node:fs/promises');
  const raw=await readFile(new URL('../tabs/topology-workspace/short-bulk-groups.mjs',
    import.meta.url),'utf8');
  for(const text of [raw.replace(/\r\n/g,'\n'),
    raw.replace(/\r\n/g,'\n').replace(/\n/g,'\r\n')]){
    const canonical=text.replace(/\r\n/g,'\n');
    assert.ok(canonical.includes("if(!isCurrent()){stopReason='CANCELLED';return;}\n      current=validated.source;"));
    assert.ok(canonical.includes("requireBatch(!allAffected.has(op.source_node_key),\n        'BATCH_INTERACTING_SOURCE_RECORDS');"));
  }
  console.info('A6B_R2_CRLF_GREEN:LF-and-Windows-CRLF-source-mutants=PASS');
});

test('qualifier refuses edited keys outside native owner source footprint; mutant RED',async()=>{
  const malformed=sidecar({hub:false,mutate:({txn})=>{
    txn.batch.sourceFootprints[0].keys=['D0','L0','R0'];
    txn.operations.push({action_id:ids[0],source_node_key:'CROSS-BRANCH-PORT',
      operation:'CLOSE_COMPONENT_PORT'});
    txn.batch.owners[0].portEdits.push({key:'CROSS-BRANCH-PORT',
      before:{},after:{}});
    txn.batch.owners[0].operationCount=2;
  }});
  await assert.rejects(qualify(malformed,false),
    /BATCH_OWNER_EDITS_OUTSIDE_FOOTPRINT/);
  console.info('A6B_R1_JS_GREEN:owner-edited-keys-within-native-footprint=PASS');
  const {readFile}=await import('node:fs/promises');
  const text=await readFile(new URL('../tabs/topology-workspace/short-bulk-groups.mjs',
    import.meta.url),'utf8');
  const start=text.indexOf('    requireBatch([...req.nodeKeys,req.leftKey,req.rightKey]');
  const end=text.indexOf("'BATCH_OWNER_EDITS_OUTSIDE_FOOTPRINT');",start);
  assert.ok(start>0&&end>start,'real source-key gate must exist');
  const mutant=await import('data:text/javascript;base64,'+
    Buffer.from(text.slice(0,start)+'    // mutating actual owner edit guard away\n'+
      text.slice(end+"'BATCH_OWNER_EDITS_OUTSIDE_FOOTPRINT');".length)).toString('base64'));
  const broken=await mutant.qualifyGroupedWorkerResult({
    result:malformed,ids,rows,current:source,hubEnabled:false,hash:fakeHash});
  await assert.rejects(async()=>assert.fail(
    'BATCH_OWNER_FOOTPRINT_MUTANT_COMMITTED:'+broken.applied.length));
  console.info('A6B_R1_JS_RED:owner-edited-footprint-check-removed:AssertionError:'+
    'BATCH_OWNER_FOOTPRINT_MUTANT_COMMITTED');
});
