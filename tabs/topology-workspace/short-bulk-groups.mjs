/** A6b independent-owner grouped short Apply.
 *
 * This module is intentionally separate from legacy one-owner runShortBulk.
 * A group is staged atomically by the explicit pre-Final Worker API. The
 * entire group MUST pass its own native + UXML authority and full owner
 * receipt census before any UI checkpoint is published. Safe group refusals
 * bisect; singleton leaves the historical path unchanged.
 */
const MAX_GROUP=32;
const BISECT_CODES=new Set([
  'SHORT_BATCH_INDEPENDENCE_CONFLICT',
  'SHORT_BATCH_OWNER_INELIGIBLE',
  'SHORT_BATCH_NOT_ELIGIBLE_OR_WITNESS_DRIFT',
  'SHORT_BATCH_NATIVE_PORT_REPAIR_REJECTED',
  'SHORT_BATCH_VALIDATION_REJECTED',
  'SHORT_BATCH_NOT_COMMITTED',
  'UXML_SHORT_BATCH_NATIVE_REFUSED',
  'UXML_SHORT_BATCH_NOT_ELIGIBLE_OR_WITNESS_DRIFT',
  'UXML_LOSS_CONTRACT_FIELD_TOUCH',
  'UXML_CLOS_WRITE_HELD',
]);
function requireBatch(ok,reason){
  if(!ok)throw Error('SHORT_BATCH_UI_AUTHORITY_HOLD:'+reason);
}
function unique(xs){return new Set(xs).size===xs.length;}
function same(xs,ys){return JSON.stringify(xs)===JSON.stringify(ys);}
function footprint(row){
  if(!row||row.eligible!==true||!Number.isInteger(row.branchIndex)||
     !Array.isArray(row.nodeKeys)||!row.nodeKeys.length||
     typeof row.leftKey!=='string'||typeof row.rightKey!=='string')return null;
  return new Set(['branch:'+row.branchIndex,...row.nodeKeys,row.leftKey,row.rightKey]);
}
function nextGroup(ids,rows,sourceSha,maximum){
  const index=new Map(rows.map(row=>[row.id,row]));
  const group=[],zones=new Set();
  for(const id of ids){
    const row=index.get(id);
    if(row?.sourceSha256!==sourceSha)break;
    const zone=footprint(row);
    if(!zone||[...zone].some(x=>zones.has(x)))break;
    if(group.length>=maximum)break;
    group.push(id);
    for(const key of zone)zones.add(key);
  }
  return group.length?group:[ids[0]];
}
function safeRefusal(result,hub){
  if(result?.ok!==true||result.topoFixCommitted===true||
     result.topoFixXmlText||result.outputKind!=='topology-sidecars'||
     result.acceptedFinalTransferred!==false||
     result.nativeCiiReleaseAuthorized!==false)return false;
  const reasons=result.topologySummary?.rejectReasons;
  if(!Array.isArray(reasons)||reasons.length!==1)return false;
  const code=reasons[0];
  if(typeof code!=='string'||!BISECT_CODES.has(code))return false;
  if(hub){
    if(result.topologyUxmlParity?.status!=='DIFFERENT'||
       !same(result.topologyUxmlParity.differences,['/batch:'+code]))return false;
  }else if(result.topologyUxmlParity?.status!=='OFF')return false;
  return true;
}
function compact(lineage,fullHash){
  const {sourceOccurrenceMap,...header}=lineage;
  return {...header,fullLineageSha256:fullHash,
    sourceOccurrenceMapCount:Array.isArray(sourceOccurrenceMap)?sourceOccurrenceMap.length:0};
}

/** The ONLY successful group-admission path into applied / current. */
export async function qualifyGroupedWorkerResult({
  result,ids,rows,current,hubEnabled,hash,
}){
  requireBatch(result?.ok===true&&result.outputKind==='topology-sidecars'&&
    result.acceptedFinalTransferred===false&&
    result.nativeCiiReleaseAuthorized===false&&
    !result.ciiText&&!result.enrichedText&&result.topoFixCommitted===true&&
    typeof result.topoFixXmlText==='string'&&result.topoFixXmlText.length>0,
    'UNCOMMITTED_OR_WRONG_OUTPUT');
  requireBatch(result.topologyUxmlParity?.status===(hubEnabled?'EQUAL':'OFF'),
    'UXML_OR_NATIVE_PARITY_NOT_APPROVED');
  const txn=JSON.parse(result.topoFixTransactionText||'null');
  const validation=JSON.parse(result.topoFixValidationText||'null');
  const lineage=JSON.parse(result.topoFixLineageText||'null');
  const preFinal=JSON.parse(result.topoFixPreFinalHandoffText||'null');
  const findings=JSON.parse(result.topoFixPostFindingsText||'null');
  const plan=JSON.parse(result.topoFixPostPlanText||'null');
  const fixedSha=await hash(result.topoFixXmlText);
  const sourceSha=current.sourceSha256;
  const ownerEvidence=txn?.batch?.owners,ownerRevisions=txn?.batch?.ownerRevisions;
  requireBatch(txn?.schema==='psi116-topofix-transaction/v1'&&
    validation?.schema==='psi116-topofix-validation/v1'&&
    txn.committed===true&&txn.atomic===true&&txn.sourceXmlMutated===false&&
    txn.source?.sha256===sourceSha&&validation.sourceSha256===sourceSha&&
    txn.fixedXmlSha256===fixedSha&&validation.fixedXmlSha256===fixedSha&&
    validation.committed===true&&validation.summary?.blockingFailureCount===0&&
    Array.isArray(validation.checks)&&validation.checks.length>0&&
    validation.checks.every(c=>!c.blocking||c.passed)&&
    same(txn.selectedActions,ids)&&txn.batch?.atomic===true&&
    txn.batch.ownerCount===ids.length&&
    Array.isArray(ownerEvidence)&&ownerEvidence.length===ids.length&&
    Array.isArray(ownerRevisions)&&ownerRevisions.length===ids.length&&
    preFinal?.requiresFreshWorkerBasis===true&&
    preFinal.nativeCiiReleaseAuthorized===false&&
    preFinal.ownerEvidenceCount===ids.length&&
    lineage?.state==='PRE_FINAL_ONLY'&&lineage.sourceXmlMutated===false&&
    lineage.sourceXmlSha256===sourceSha&&lineage.fixedXmlSha256===fixedSha&&
    findings?.source?.sha256===fixedSha&&plan?.source?.sha256===fixedSha&&
    Array.isArray(findings.shortElements)&&Array.isArray(findings.findings)&&
    Array.isArray(plan.actions),
    'BATCH_SOURCE_LINEAGE_OWNER_CENSUS');
  requireBatch(Array.isArray(txn.operations)&&txn.operations.length>0&&
    unique(ownerEvidence.map(x=>x.id))&&
    unique(ownerRevisions.map(x=>x.id))&&
    ownerEvidence.every((x,i)=>x.id===ids[i]&&x.committed===true&&
      x.sourceSha256===sourceSha&&x.lengthBasis==='SOURCE_STRAIGHT_TWO_PORT_SPAN'&&
      x.lengthMm<=6+1e-9&&Array.isArray(x.sourceRecordKeys)&&
      Array.isArray(x.portEdits)&&Number.isInteger(x.operationCount))&&
    ownerRevisions.every((x,i)=>x.id===ids[i]&&
      x.sourceXmlMutated===false&&
      typeof x.sourceSha256==='string'&&typeof x.fixedSha256==='string'&&
      x.sourceSha256.length===64&&x.fixedSha256.length===64&&
      (i===0?x.sourceSha256===sourceSha:
        x.sourceSha256===ownerRevisions[i-1].fixedSha256))&&
    ownerRevisions.at(-1).fixedSha256===fixedSha,
    'BATCH_OWNER_REVISION_CHAIN');
  const rowMap=new Map(rows.map(row=>[row.id,row]));
  const perOps=new Map(ids.map(id=>[id,[]]));
  for(const op of txn.operations){
    requireBatch(perOps.has(op.action_id)&&
      ['REMOVE_SELECTED_SHORT_ELEMENT_RECORD','CLOSE_COMPONENT_PORT'].includes(op.operation),
      'BATCH_UNDECLARED_OPERATION');
    perOps.get(op.action_id).push(op);
  }
  const allAffected=new Set();
  for(let i=0;i<ids.length;i++){
    const id=ids[i],ev=ownerEvidence[i],req=rowMap.get(id);
    const ops=perOps.get(id);
    requireBatch(req?.eligible===true&&req.sourceSha256===sourceSha&&
      same([...ev.sourceRecordKeys].sort(),[...req.nodeKeys].sort())&&
      ev.operationCount===ops.length&&ops.length>=req.nodeKeys.length&&
      unique(ops.map(x=>x.source_node_key))&&
      same(ops.filter(op=>op.operation==='REMOVE_SELECTED_SHORT_ELEMENT_RECORD')
          .map(op=>op.source_node_key).sort(),[...req.nodeKeys].sort())&&
      ev.portEdits.length===ops.filter(op=>op.operation==='CLOSE_COMPONENT_PORT').length,
      'BATCH_PER_OWNER_ACCOUNTING');
    for(const op of ops){
      requireBatch(!allAffected.has(op.source_node_key),
        'BATCH_INTERACTING_SOURCE_RECORDS');
      allAffected.add(op.source_node_key);
    }
  }
  const canonical=hubEnabled?result.topologyUxmlAppliedEditOps:[];
  requireBatch(!hubEnabled||(Array.isArray(canonical)&&
    canonical.length===ids.length&&
    unique(canonical.map(x=>x.sourceActionId))&&
    canonical.every((op,i)=>{
      const id=ids[i],row=rowMap.get(id),request=op?.params?.[0]?.request;
      return op?.kind==='DROP_SHORT_ELEMENT'&&
        op.opId==='UXML-OP-'+id&&op.sourceActionId===id&&
        op.fileSha256===sourceSha&&
        request?.id===id&&request.sourceSha256===sourceSha&&
        same(request.nodeKeys,row.nodeKeys)&&
        Array.isArray(op.targets)&&op.targets.length>0&&unique(op.targets)&&
        same([...op.targets].sort(),
          perOps.get(id).map(o=>o.source_node_key).sort())&&
        Array.isArray(op.removedWithRecord)&&
        unique(op.removedWithRecord.map(x=>x.recordKey+'\0'+x.field))&&
        op.removedWithRecord.every(x=>op.targets.includes(x.recordKey));
    })),
    'BATCH_CANONICAL_GROUP_WITNESS_MISSING');
  const lineageSha=await hash(result.topoFixLineageText);
  const shortLineage=compact(lineage,lineageSha);
  const applied=ids.map((id,i)=>({
    id,sourceSha256:ownerRevisions[i].sourceSha256,
    fixedSha256:ownerRevisions[i].fixedSha256,
    request:{id,sourceSha256:sourceSha,
      nodeKeys:[...rowMap.get(id).nodeKeys]},
    selectedElement:rowMap.get(id),transaction:txn,validation,
    ownerEvidence:ownerEvidence[i],ownerRevision:ownerRevisions[i],
    ownerOperations:perOps.get(id),
    lineage:shortLineage,preFinal,hubRoute:hubEnabled,
    bulkTiming:result.topologyBulkTiming||null,
    canonicalEditOps:hubEnabled?[canonical[i]]:[],
  }));
  return {applied,source:{...current,sourceText:result.topoFixXmlText,
    sourceSha256:fixedSha,rawSha256:fixedSha},
    latest:{source:{...current,sourceText:result.topoFixXmlText,
      sourceSha256:fixedSha,rawSha256:fixedSha},findings,plan}};
}

export async function runIndependentShortBulk({
  source,shortElements,selectedIds,runEngine,hubEnabled=false,
  isCurrent=()=>true,onCheckpoint=()=>{},onProgress=()=>{},
  hash,runLegacy,maximum=MAX_GROUP,
}){
  if(!source||!Array.isArray(shortElements)||!Array.isArray(selectedIds)||
     !unique(selectedIds)||typeof runEngine!=='function'||
     typeof runLegacy!=='function'||typeof hash!=='function'||
     !Number.isInteger(maximum)||maximum<2||maximum>MAX_GROUP)
    throw Error('SHORT_BATCH_INVALID_SELECTION');
  let current={...source},rows=shortElements,latest=null;
  const requested=[...selectedIds],applied=[],skipped=[];
  let completed=0,stopReason='COMPLETE',stopMessage='',failedId=null;
  const lease=typeof runEngine.beginBulkSession==='function'&&
    typeof runEngine.endBulkSession==='function';
  const notify=(id,status,inFlightOwners=0)=>{
    onProgress({completed,total:requested.length,applied:applied.length,
      skipped:skipped.length,currentEligible:rows.filter(r=>r.eligible).length,
      id,status,inFlightOwners});
  };
  const checkpoint=()=>onCheckpoint({originSha256:source.sourceSha256,
    latest,applied:[...applied],skipped:[...skipped],requested,completed});
  const mergeLegacy=async id=>{
    const output=await runLegacy({
      source:current,shortElements:rows,selectedIds:[id],
      // One-owner existing path is unmodified; suppress nested lease only.
      runEngine:async job=>runEngine(job),hubEnabled,isCurrent,
      hash,onCheckpoint:()=>{},onProgress:()=>{},
    });
    if(!isCurrent()){stopReason='CANCELLED';return;}
    if(output.stopReason==='CANCELLED'){stopReason='CANCELLED';return;}
    if(output.stopReason==='TRANSACTION_FAILED'){
      stopReason='TRANSACTION_FAILED';stopMessage=output.stopMessage;
      failedId=id;return;
    }
    if(output.applied.length){
      requireBatch(output.applied.length===1&&output.skipped.length===0&&
        output.latest?.source?.sourceSha256===output.applied[0].fixedSha256,
        'SINGLETON_FALLBACK_CUSTODY');
      current=output.latest.source;rows=output.latest.findings.shortElements;
      latest=output.latest;applied.push(...output.applied);
    }else{
      requireBatch(output.skipped.length===1&&output.skipped[0].id===id,
        'SINGLETON_REFUSAL_CENSUS');
      skipped.push(...output.skipped);
    }
    completed++;checkpoint();notify(id,output.applied.length?'VALIDATED':'REFUSED');
  };
  const runGroup=async ids=>{
    if(stopReason!=='COMPLETE'||!isCurrent()){stopReason='CANCELLED';return;}
    if(ids.length===1){await mergeLegacy(ids[0]);return;}
    const rowMap=new Map(rows.map(r=>[r.id,r]));
    const groupRows=ids.map(id=>rowMap.get(id));
    if(groupRows.some(row=>!row?.eligible||row.sourceSha256!==current.sourceSha256)){
      const mid=Math.floor(ids.length/2);
      await runGroup(ids.slice(0,mid));await runGroup(ids.slice(mid));return;
    }
    notify(ids[0],'APPLYING',ids.length);
    const reqs=groupRows.map(row=>({id:row.id,sourceSha256:current.sourceSha256,
      nodeKeys:[...row.nodeKeys]}));
    let result;
    try{
      result=await runEngine({
        sourceKind:'xml',sourceText:current.sourceText,sourceName:current.name,
        topologyPreFinalOnly:true,sourceRawSha256:current.rawSha256||current.sourceSha256,
        options:{outputMode:'enriched-only',analyzeTopology:true,generateTopoFix:true,
          useTopoFixForCii:false,topologyActionIds:[...ids],
          topologyShortElementRequests:reqs,topologyShortBatchExplicit:true,
          topologyUxmlPreview:hubEnabled,topologyBulkSession:true,
          topologyBulkSpeedProfile:true},
      });
    }catch(error){
      if(!isCurrent()){stopReason='CANCELLED';return;}
      stopReason='TRANSACTION_FAILED';
      failedId=ids[0];stopMessage=String(error?.message||error);return;
    }
    if(!isCurrent()){stopReason='CANCELLED';return;}
    if(result?.topoFixCommitted!==true){
      if(safeRefusal(result,hubEnabled)){
        const mid=Math.floor(ids.length/2);
        await runGroup(ids.slice(0,mid));
        if(stopReason==='COMPLETE')await runGroup(ids.slice(mid));
      }else{
        stopReason='TRANSACTION_FAILED';failedId=ids[0];
        stopMessage='SHORT_BATCH_UNQUALIFIED_REFUSAL_OR_PARITY_HOLD:'+
          String(result?.topologySummary?.rejectReasons?.[0]||result?.error||'UNKNOWN');
      }
      return;
    }
    try{
      const validated=await qualifyGroupedWorkerResult({
        result,ids,rows,current,hubEnabled,hash});
      if(!isCurrent()){stopReason='CANCELLED';return;}
      current=validated.source;rows=validated.latest.findings.shortElements;
      latest=validated.latest;applied.push(...validated.applied);
      completed+=ids.length;
      checkpoint();notify(ids.at(-1),'VALIDATED');
    }catch(error){
      stopReason='TRANSACTION_FAILED';failedId=ids[0];
      stopMessage=String(error?.message||error);
    }
  };
  if(lease)runEngine.beginBulkSession();
  try{
    let offset=0;
    while(offset<requested.length&&stopReason==='COMPLETE'){
      if(!isCurrent()){stopReason='CANCELLED';break;}
      const ids=nextGroup(requested.slice(offset),rows,
        current.sourceSha256,maximum);
      await runGroup(ids);
      if(stopReason==='COMPLETE')offset+=ids.length;
    }
  }finally{if(lease)runEngine.endBulkSession();}
  const hubMismatch=hubEnabled&&
    stopReason!=='COMPLETE'&&stopReason!=='CANCELLED';
  const pendingIds=requested.slice(completed+(failedId?1:0));
  return {originSha256:source.sourceSha256,latest,applied,skipped,requested,
    completed,failedId,pendingIds,currentEligible:rows.filter(r=>r.eligible).length,
    stopReason,stopMessage,hubMismatch};
}
