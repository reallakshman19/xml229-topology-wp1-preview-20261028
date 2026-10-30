/** Source-bound, manually approved Second Pass queue.
 * No inferred pairing becomes authorization. Python remains the final oracle.
 */
const stable = value => JSON.stringify(value);
const assert = (ok,why) => {if(!ok)throw Error(why);};
const shaText = async xml => {
  const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(xml));
  return [...new Uint8Array(digest)].map(n=>n.toString(16).padStart(2,'0')).join('');
};
function witness(preview) {
  assert(preview?.repair&&Array.isArray(preview.changes)&&
    Array.isArray(preview.portKeys)&&preview.portKeys.length===2,
    'SECOND_PASS_QUEUE_INVALID_PREVIEW');
  const r=preview.repair;
  assert(Array.isArray(r.moveKeys)&&r.moveKeys.length&&Array.isArray(r.delta)&&
    r.movePortKey&&r.targetPortKey&&r.movePortKey!==r.targetPortKey,
    'SECOND_PASS_QUEUE_INVALID_MOVEMENT');
  // The approved physical movement and before/after witness, not source SHA,
  // must remain identical after earlier, separately approved queue entries.
  return stable({findingId:preview.findingId,portKeys:preview.portKeys,
    repair:r,changes:preview.changes});
}
const touched = item => new Set([item.sourceKey,item.peerKey,
  item.preview.repair.movePortKey,item.preview.repair.targetPortKey,
  ...item.preview.repair.moveKeys,
  ...item.preview.changes.map(c=>c.sourceKey)].filter(Boolean));
export function queueConflict(a,b) {
  if(a.findingId===b.findingId)return 'SAME_FINDING';
  const own=touched(a),other=touched(b);
  for(const key of own)if(other.has(key))return 'OVERLAPPING_SOURCE_PORT_OR_MOVEMENT:'+key;
  return '';
}
export function makeManualQueueItem(d,sourceSha256) {
  assert(d?.sourceSha256===sourceSha256&&d.preview?.sourceSha256===sourceSha256&&
    d.preview.findingId===d.findingId&&d.preview.portKeys?.[0]===d.sourceKey&&
    d.preview.portKeys?.[1]===d.peerKey,'SECOND_PASS_QUEUE_SOURCE_OR_PORT_DRIFT');
  assert(d.confirmed===true&&String(d.evidence||'').trim().length>=10,
    'SECOND_PASS_QUEUE_APPROVAL_REQUIRED');
  const fingerprint=witness(d.preview),r=d.preview.repair;
  return {id:'Q:'+sourceSha256.slice(0,12)+':'+d.findingId+':'+d.sourceKey+':'+d.peerKey,
    findingId:d.findingId,sourceKey:d.sourceKey,peerKey:d.peerKey,
    approvedSourceSha256:sourceSha256,preview:structuredClone(d.preview),
    fingerprint,designEvidence:d.evidence.trim(),status:'APPROVED',
    actionId:'JOIN:'+d.findingId+':'+r.movePortKey};
}
export function enqueueManualFix(queue,d,sourceSha256) {
  const item=makeManualQueueItem(d,sourceSha256);
  assert(!queue.some(x=>x.id===item.id),'SECOND_PASS_QUEUE_DUPLICATE');
  for(const prior of queue) {
    if(prior.status!=='APPROVED')continue;
    const conflict=queueConflict(prior,item);
    assert(!conflict,'SECOND_PASS_QUEUE_CONFLICT:'+conflict);
  }
  return [...queue,item];
}
/** Sequential, source-authoritative processing with no intermediate canvas redraw.
 * Source moves may change SHA, but a fresh independent preview must prove that
 * each originally approved physical movement is exactly unchanged.
 */
export async function runManualFixQueue({
  source,entries,runEngine,isCurrent=()=>true,onCheckpoint=()=>{},onProgress=()=>{},
  hash=shaText,
}) {
  assert(source?.sourceSha256&&typeof source.sourceText==='string'&&
    Array.isArray(entries)&&typeof runEngine==='function'&&
    new Set(entries.map(x=>x.id)).size===entries.length,
    'SECOND_PASS_QUEUE_INVALID_JOB');
  let current={...source},latest=null,failedId=null,stopReason='COMPLETE',message='';
  const applied=[],blocked=[],pending=entries.map(e=>e.id),requested=[...pending];
  const preFinalJob=(options)=>({sourceKind:'xml',sourceText:current.sourceText,
    sourceName:current.name,topologyPreFinalOnly:true,
    options:{outputMode:'enriched-only',analyzeTopology:true,useTopoFixForCii:false,...options}});
  for(const item of entries) {
    if(!isCurrent()){stopReason='CANCELLED';break;}
    assert(item.status==='APPROVED'&&item.designEvidence?.length>=10,'SECOND_PASS_QUEUE_UNAPPROVED');
    if(item.approvedSourceSha256!==source.sourceSha256){
      blocked.push({id:item.id,reason:'QUEUE_APPROVAL_SOURCE_DRIFT'});pending.shift();
      stopReason='STALE';message='Queue approval does not match the original working source';break;
    }
    try {
      onProgress({status:'RECHECK',id:item.id,applied:applied.length,
        remaining:pending.length,total:requested.length});
      const pair={mode:'SECOND_PASS',sourceSha256:current.sourceSha256,
        findingId:item.findingId,portKeys:[item.sourceKey,item.peerKey]};
      const previewResult=await runEngine(preFinalJob({analyzeTopology:true,
        generateTopoFix:false,topologyConnectionPreview:pair}));
      if(!isCurrent()){stopReason='CANCELLED';break;}
      assert(previewResult?.ok===true&&previewResult.outputKind==='topology-sidecars'&&
        previewResult.topoFixCommitted!==true&&
        previewResult.acceptedFinalTransferred===false&&
        previewResult.nativeCiiReleaseAuthorized===false&&
        !previewResult.ciiText&&!previewResult.enrichedText,'SECOND_PASS_QUEUE_PREVIEW_REJECTED');
      const data=JSON.parse(previewResult.topologyFindingsText||'null');
      const fresh=data?.manualConnectionPreview;
      assert(data?.source?.sha256===current.sourceSha256&&
        fresh?.sourceSha256===current.sourceSha256&&
        fresh.findingId===item.findingId,'SECOND_PASS_QUEUE_STALE_FINDING');
      assert(witness(fresh)===item.fingerprint,
        'SECOND_PASS_QUEUE_STALE_MOVEMENT_REQUIRES_REAPPROVAL');
      const repair=fresh.repair,actionId='JOIN:'+item.findingId+':'+repair.movePortKey;
      assert(actionId===item.actionId,'SECOND_PASS_QUEUE_ACTION_ID_DRIFT');
      const approval={...pair,moveKey:repair.movePortKey,targetKey:repair.targetPortKey,
        approvedRepair:repair,evidence:item.designEvidence,confirmed:true};
      onProgress({status:'VALIDATING',id:item.id,applied:applied.length,
        remaining:pending.length,total:requested.length});
      const result=await runEngine(preFinalJob({analyzeTopology:true,
        generateTopoFix:true,topologyActionIds:[actionId],
        topologyJointRepairs:[approval]}));
      if(!isCurrent()){stopReason='CANCELLED';break;}
      assert(result?.ok===true&&result.outputKind==='topology-sidecars'&&
        result.topoFixCommitted===true&&result.topoFixXmlText&&
        result.acceptedFinalTransferred===false&&
        result.nativeCiiReleaseAuthorized===false&&!result.ciiText&&!result.enrichedText,
        'SECOND_PASS_QUEUE_TRANSACTION_REJECTED:'+String(result?.error||'no verified XML'));
      const txn=JSON.parse(result.topoFixTransactionText||'null');
      const validation=JSON.parse(result.topoFixValidationText||'null');
      const lineage=JSON.parse(result.topoFixLineageText||'null');
      const preFinal=JSON.parse(result.topoFixPreFinalHandoffText||'null');
      const findings=JSON.parse(result.topoFixPostFindingsText||'null');
      const plan=JSON.parse(result.topoFixPostPlanText||'null');
      const fixedSha=await hash(result.topoFixXmlText);
      if(!isCurrent()){stopReason='CANCELLED';break;}
      assert(txn?.schema==='psi116-topofix-transaction/v1'&&
        txn.source?.sha256===current.sourceSha256&&
        txn.fixedXmlSha256===fixedSha&&txn.sourceXmlMutated===false&&
        txn.committed===true&&stable(txn.selectedActions)==stable([actionId])&&
        Array.isArray(txn.operations)&&txn.operations.length>0,
        'SECOND_PASS_QUEUE_TRANSACTION_CUSTODY_DRIFT');
      assert(validation?.schema==='psi116-topofix-validation/v1'&&
        validation.sourceSha256===current.sourceSha256&&
        validation.fixedXmlSha256===fixedSha&&validation.committed===true&&
        validation.summary?.blockingFailureCount===0&&
        Array.isArray(validation.checks)&&validation.checks.length>0&&
        !validation.checks.some(c=>c.blocking&&!c.passed),
        'SECOND_PASS_QUEUE_VALIDATION_FAILED');
      assert(lineage?.sourceXmlSha256===current.sourceSha256&&
        lineage.fixedXmlSha256===fixedSha&&lineage.state==='PRE_FINAL_ONLY'&&
        lineage.sourceXmlMutated===false&&
        preFinal?.originalSourceXmlSha256===current.sourceSha256&&
        preFinal?.newSourceXmlSha256===fixedSha&&
        preFinal?.requiresFreshWorkerBasis===true&&
        preFinal?.nativeCiiReleaseAuthorized===false,
        'SECOND_PASS_QUEUE_LINEAGE_DRIFT');
      assert(findings?.source?.sha256===fixedSha&&
        plan?.source?.sha256===fixedSha&&
        Array.isArray(findings.findings)&&Array.isArray(findings.manualConnectionPorts)&&
        Array.isArray(plan.actions),'SECOND_PASS_QUEUE_REANALYSIS_DRIFT');
      const receipt={id:item.id,findingId:item.findingId,
        sourceSha256:current.sourceSha256,fixedXmlSha256:fixedSha,
        sourceKey:item.sourceKey,peerKey:item.peerKey,
        evidence:item.designEvidence,actionId,preview:fresh,
        transaction:txn,validation,preFinal,
        lineageSha256:await hash(result.topoFixLineageText)};
      if(!isCurrent()){stopReason='CANCELLED';break;}
      applied.push(receipt);pending.shift();
      current={...current,sourceText:result.topoFixXmlText,sourceSha256:fixedSha};
      latest={source:current,findings,plan};
      onCheckpoint({initialSha256:source.sourceSha256,latest,applied:[...applied],
        blocked:[...blocked],requested,pending:[...pending]});
      onProgress({status:'VERIFIED',id:item.id,applied:applied.length,
        remaining:pending.length,total:requested.length});
    }catch(e){
      if(!isCurrent()){stopReason='CANCELLED';break;}
      failedId=item.id;stopReason='BLOCKED';
      message=String(e?.message||e);
      blocked.push({id:item.id,reason:message});pending.shift();
      break;
    }
  }
  return {initialSha256:source.sourceSha256,latest,applied,blocked,requested,
    failedId,pending,stopReason,message};
}
