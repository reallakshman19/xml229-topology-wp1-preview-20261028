/** Exact-guard mutation qualification.
 * Each case deletes one live receipt guard in an IN-MEMORY module copy, reruns
 * the same negative assertion, and proves that the assertion FAILS. Source
 * files are never edited; this is a synthetic kill-the-mutant receipt.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const path='tabs/topology-workspace/short-bulk.mjs';
const live=readFileSync(path,'utf8');
let sequence=0;
async function instantiate(code){
  const uri='data:text/javascript;base64,'+Buffer.from(
    '// isolated guard mutant '+(++sequence)+'\n'+code).toString('base64');
  return import(uri);
}
async function invoke(mod,mutate){
  const id='SHORT:0',sourceSha256='h0',fixedSha256='h1';
  const request={id,sourceSha256,nodeKeys:['SHORT:0:S1','SHORT:0:S2']};
  const op={kind:'DROP_SHORT_ELEMENT',opId:'UXML-OP-'+id,
    sourceActionId:id,fileSha256:sourceSha256,
    targets:[...request.nodeKeys],
    params:[{request:{...request,nodeKeys:[...request.nodeKeys]}}],
    removedWithRecord:[{recordKey:'SHORT:0:S1',field:'Weight'}]};
  mutate(op);
  const result={
    ok:true,outputKind:'topology-sidecars',
    acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
    topoFixCommitted:true,ciiText:null,enrichedText:'',
    topologyUxmlParity:{status:'EQUAL',differences:[]},
    topologyUxmlAppliedEditOps:[op],
    topoFixXmlText:'xml|h1',
    topoFixTransactionText:JSON.stringify({
      schema:'psi116-topofix-transaction/v1',
      source:{sha256:sourceSha256},committed:true,sourceXmlMutated:false,
      selectedActions:[id],fixedXmlSha256,
      operations:[{operation:'REMOVE_SELECTED_SHORT_ELEMENT_RECORD'}]}),
    topoFixValidationText:JSON.stringify({
      schema:'psi116-topofix-validation/v1',committed:true,
      sourceSha256,fixedXmlSha256,summary:{blockingFailureCount:0},
      checks:[{blocking:true,passed:true}]}),
    topoFixLineageText:JSON.stringify({
      sourceXmlSha256:sourceSha256,fixedXmlSha256,state:'PRE_FINAL_ONLY',
      sourceXmlMutated:false,sourceOccurrenceMap:[]}),
    topoFixPreFinalHandoffText:JSON.stringify({
      requiresFreshWorkerBasis:true,nativeCiiReleaseAuthorized:false}),
    topoFixPostFindingsText:JSON.stringify({
      source:{sha256:fixedSha256},findings:[],shortElements:[]}),
    topoFixPostPlanText:JSON.stringify({
      source:{sha256:fixedSha256},actions:[]}),
  };
  return mod.runShortBulk({
    source:{sourceSha256,sourceText:'xml|h0',name:'synthetic.xml'},
    shortElements:[{id,eligible:true,sourceSha256,nodeKeys:[...request.nodeKeys]}],
    selectedIds:[id],hubEnabled:true,
    runEngine:async()=>result,
    hash:async value=>value==='xml|h1'?'h1':'sha-lineage',
  });
}
const guards=[
  ['fileSha256','op.fileSha256!==current.sourceSha256||',op=>{op.fileSha256='FORGED';}],
  ['opId',"op.opId!=='UXML-OP-'+id||",op=>{op.opId='FORGED';}],
  ['sourceActionId','op.sourceActionId!==id||',op=>{op.sourceActionId='FORGED';}],
  ['requestNodeKeys','JSON.stringify(requestWitness?.nodeKeys)!==JSON.stringify(request.nodeKeys)',
    op=>{op.params[0].request.nodeKeys=['FORGED'];}],
  ['requestSourceSha','requestWitness?.sourceSha256!==request.sourceSha256||',
    op=>{op.params[0].request.sourceSha256='FORGED';}],
  ['duplicateTargets','new Set(op.targets).size!==op.targets.length||',
    op=>{op.targets.push(op.targets[0]);}],
  ['removedWithRecordOutsideTargets','op.targets.includes(w.recordKey)&&',
    op=>{op.removedWithRecord[0].recordKey='FORGED';}],
];
test('live canonical receipt controls reject all seven forged fields',async()=>{
  const mod=await instantiate(live);
  for(const [name,,mutate] of guards){
    const result=await invoke(mod,mutate);
    assert.equal(result.stopReason,'TRANSACTION_FAILED',name);
    assert.equal(result.hubMismatch,true,name);
    assert.equal(result.applied.length,0,name);
    assert.match(result.stopMessage,
      /UXML_SHORT_APPLY_CANONICAL_OP_RECEIPT_MISSING_OR_DRIFT/,name);
  }
});
for(const [name,clause,mutate] of guards){
  test('KILL receipt guard mutation: '+name,async()=>{
    assert.equal(live.split(clause).length,2,
      'the guard must exist exactly once before deletion: '+name);
    // Guard expression deleted, leaving the rest of the existing IF intact.
    const mutant=live.replace(clause,
      name==='requestNodeKeys'?'false':'');
    const broken=await instantiate(mutant);
    const reference=await instantiate(live);
    const original=await invoke(reference,mutate);
    assert.equal(original.stopReason,'TRANSACTION_FAILED');
    const observed=await invoke(broken,mutate);
    let mutationFailure=null;
    try{assert.equal(observed.stopReason,'TRANSACTION_FAILED',
      'negative guard test must fail if '+name+' is deleted');}
    catch(e){mutationFailure=e;}
    assert.equal(mutationFailure?.name,'AssertionError',
      'deleting this guard must kill the original safety assertion');
    assert.equal(observed.stopReason,'COMPLETE',
      name+' mutant must demonstrate the unauthorized acceptance');
    assert.equal(observed.applied.length,1);
    console.info('MUTANT_KILLED: '+name+' · negative assertion FAILED after guard deletion');
  });
}
test('KILL refusal allowlist widening: authority mismatch must not be skippable',async()=>{
  const clause='SKIPPABLE_HUB_OWNER_CODES.has(match[1])';
  assert.equal(live.split(clause).length,2);
  const mutant=live.replace(clause,'true');
  const before=await instantiate(live),after=await instantiate(mutant);
  const disagreement={
    ok:true,topoFixCommitted:false,topoFixXmlText:'',
    acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
    topologyUxmlParity:{status:'DIFFERENT',differences:[
      '/patchBack: UxmlPatchError: UXML_SHORT_TARGETS_OR_PARAMS_DIFFER_FROM_AUTHORITY:TEST']},
  };
  assert.equal(before.namedHubOwnerRefusal(disagreement),null);
  let mutationFailure=null;
  try{assert.equal(after.namedHubOwnerRefusal(disagreement),null,
      'authority mismatch must HOLD, never SKIP');}
  catch(e){mutationFailure=e;}
  assert.equal(mutationFailure?.name,'AssertionError');
  assert.match(after.namedHubOwnerRefusal(disagreement),
    /UXML_SHORT_TARGETS_OR_PARAMS_DIFFER_FROM_AUTHORITY/);
  console.info('MUTANT_KILLED: widened refusal allowlist · negative assertion FAILED');
});
