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
  'SHORT_BATCH_OWNER_WRITE_OUTSIDE_FOOTPRINT',
  'SHORT_BATCH_INTERMEDIATE_PREFLIGHT_REJECTED',
  'SHORT_BATCH_SEQUENTIAL_OWNER_QUALIFICATION_REFUSED',
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
/** The only group-order authority: source-bound native footprints from
 * read-only Analyze, NOT guessed branch/position equivalence in JS.
 * JS validates the Python-emitted footprint (planning.owners, then
 * batch.sourceFootprints) against its independent source-record lower bound;
 * it does NOT treat a JS-calculated zone as authority to widen native Apply.
 */
export function planSourceBoundGroups(ids,rows,planning,sourceSha,maximum=MAX_GROUP,sourceRecords){
  requireBatch(planning?.schema==='psi116-short-group-footprints/v1'&&
    planning.sourceSha256===sourceSha&&Array.isArray(planning.owners)&&
    unique(ids)&&Number.isInteger(maximum)&&maximum>=2&&maximum<=MAX_GROUP,
    'PLANNER_SOURCE_BOUND_FOOTPRINTS_REQUIRED');
  requireBatch(Array.isArray(sourceRecords)&&sourceRecords.length>0&&
    sourceRecords.every(record=>typeof record.key==='string'&&
      Number.isInteger(record.branchIndex)), 'PLANNER_ORIGINAL_RECORDS_REQUIRED');
  const originalByKey=new Map(sourceRecords.map(record=>[record.key,record]));
  requireBatch(originalByKey.size===sourceRecords.length,
    'PLANNER_ORIGINAL_RECORD_KEYS_DUPLICATED');
  const byBranch=new Map(),byPositive=new Map();
  for(const record of sourceRecords){
    if(!byBranch.has(record.branchIndex))byBranch.set(record.branchIndex,[]);
    byBranch.get(record.branchIndex).push(record.key);
    if(Number.isInteger(record.nodeNumber)&&record.nodeNumber>0){
      if(!byPositive.has(record.nodeNumber))byPositive.set(record.nodeNumber,[]);
      byPositive.get(record.nodeNumber).push(record.key);
    }
  }
  const nativeMinimum=row=>{
    const owned=new Set([...(byBranch.get(row.branchIndex)||[]),
      ...row.nodeKeys,row.leftKey,row.rightKey]);
    requireBatch([...owned].every(key=>originalByKey.has(key)),
      'PLANNER_ORIGINAL_SOURCE_RECORD_MISSING');
    // Mirror PortModel.moving_group transitive finite-owner/positive-link
    // reachability, not merely one-hop node-number aliases. A finite VALV
    // may carry the move from branch B0 into its second port in B1, then
    // via a shared positive node into a PIPE in B2.
    const finite=new Set(['FLAN','GASK','VALV','INST','RIGID','REDU',
      'ELBO','TEE','OLET','COUP','FBLI','CAP']);
    const aliases={BEND:'ELBO',ELBOW:'ELBO',REDUCER:'REDU',
      WELDOLET:'OLET',SOCKOLET:'OLET'};
    const kind=record=>aliases[record.type]||record.type;
    const groupByKey=new Map();
    for(const branchKeys of byBranch.values()){
      const groups=[];
      for(const key of branchKeys){
        const record=originalByKey.get(key);
        if(!record.position||['ATTA','SUPPORT','ANCI'].includes(kind(record)))
          continue;
        const last=groups.at(-1);
        if(last&&record.refNo&&kind(record)!=='BRAN'&&
          kind(last.at(-1))!=='BRAN'&&last.at(-1).refNo===record.refNo)
          last.push(record);
        else groups.push([record]);
      }
      for(const group of groups){
        const type=kind(group.find(r=>kind(r)!=='RIGID')||group[0]);
        if(finite.has(type))
          for(const record of group)groupByKey.set(record.key,group.map(r=>r.key));
      }
    }
    const reached=new Set(owned),pending=[...owned];
    while(pending.length){
      const record=originalByKey.get(pending.pop());
      if(!record?.position)continue;
      const adjacent=[...(groupByKey.get(record.key)||[])];
      const peers=[...(byBranch.get(record.branchIndex)||[]),
        ...(Number.isInteger(record.nodeNumber)&&record.nodeNumber>0?
          byPositive.get(record.nodeNumber)||[]:[])];
      for(const key of peers){
        const other=originalByKey.get(key);
        if(!other?.position)continue;
        const positive=Number.isInteger(record.nodeNumber)&&
          record.nodeNumber>0&&record.nodeNumber===other.nodeNumber;
        const coincident=record.branchIndex===other.branchIndex&&
          Math.hypot(record.position.x-other.position.x,
            record.position.y-other.position.y,
            record.position.z-other.position.z)<=1e-6;
        if(positive||coincident)adjacent.push(key);
      }
      for(const key of adjacent)
        if(!reached.has(key)){reached.add(key);pending.push(key);}
    }
    const contact=new Set(reached);
    const positions=[...reached].map(k=>originalByKey.get(k).position)
      .filter(p=>p&&Number.isFinite(p.x)&&Number.isFinite(p.y)&&
        Number.isFinite(p.z));
    // JS lower bound mirrors Python's grouping-only reservation:
    // 25mm actual policy + 2*(6mm short motion + 0.5mm contact tolerance).
    // This is NOT permission to repair a gap greater than 25mm.
    // Compare Euclidean distance and include boundary epsilon.
    for(const record of sourceRecords){
      const p=record.position;
      if(contact.has(record.key)||!p)continue;
      if(positions.some(q=>Math.hypot(p.x-q.x,p.y-q.y,p.z-q.z)<=25+2*(6+0.5)+1e-9))
        contact.add(record.key);
    }
    return contact;
  };
  const rowMap=new Map(rows.map(row=>[row.id,row]));
  const zones=new Map();
  for(const entry of planning.owners){
    requireBatch(typeof entry?.id==='string'&&
      !zones.has(entry.id)&&Array.isArray(entry.keys)&&entry.keys.length>0&&
      entry.keys.every(key=>typeof key==='string'&&key.length>0)&&
      unique(entry.keys),'PLANNER_MALFORMED_NATIVE_FOOTPRINTS');
    zones.set(entry.id,new Set(entry.keys));
  }
  const groups=[],prior=[],assigned=[];
  let barrier=0;
  for(const id of ids){
    const row=rowMap.get(id);
    const zone=row?.eligible===true&&row.sourceSha256===sourceSha?
      zones.get(id):null;
    if(!zone){
      groups.push([id]);prior.push(null);
      assigned.push(groups.length-1);barrier=groups.length;
      continue;
    }
    const minimumZone=nativeMinimum(row);
    requireBatch([...minimumZone].every(key=>zone.has(key)),
      'PLANNER_NATIVE_FOOTPRINT_UNDERCOVERS_SOURCE');
    requireBatch([...row.nodeKeys,row.leftKey,row.rightKey]
      .every(key=>zone.has(key)), 'PLANNER_NATIVE_SOURCE_RECORD_CENSUS');
    let minimum=barrier;
    for(let i=0;i<prior.length;i++){
      if(prior[i]&&[...zone].some(key=>prior[i].has(key)))
        minimum=Math.max(minimum,assigned[i]+1);
    }
    let layer=minimum;
    while(layer<groups.length&&groups[layer].length>=maximum)layer++;
    if(layer===groups.length)groups.push([]);
    requireBatch(!prior.some((other,i)=>assigned[i]===layer&&other&&
      [...zone].some(key=>other.has(key))),
      'PLANNER_OVERLAPPING_OWNERS_IN_GROUP');
    groups[layer].push(id);prior.push(zone);assigned.push(layer);
  }
  requireBatch(groups.flat().length===ids.length&&
    unique(groups.flat())&&
    ids.every(id=>groups.some(group=>group.includes(id))),
    'PLANNER_OWNER_CENSUS');
  return groups;
}
function safeRefusal(result,hub){
  if(result?.ok!==true||result.topoFixCommitted===true||
     result.topoFixXmlText||result.outputKind!=='topology-sidecars'||
     result.acceptedFinalTransferred!==false||
     result.nativeCiiReleaseAuthorized!==false)return false;
  const reasons=result.topologySummary?.rejectReasons;
  if(!Array.isArray(reasons)||reasons.length!==1)return false;
  const code=reasons[0];
  // Preserve the entire native refusal in custody, including colon details,
  // but recognize only a named allowlisted leading code for safe bisection.
  if(typeof code!=='string'||!BISECT_CODES.has(code.split(':',1)[0]))
    return false;
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
  const sourceFootprints=txn?.batch?.sourceFootprints;
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
    Array.isArray(sourceFootprints)&&sourceFootprints.length===ids.length&&
    sourceFootprints.every((v,i)=>v?.id===ids[i]&&
      Array.isArray(v.keys)&&v.keys.length>0&&unique(v.keys)&&
      v.keys.every(k=>typeof k==='string'&&k.length>0))&&
    preFinal?.schema==='psi116-short-batch-prefinal-handoff/v1'&&
    preFinal.requiresFreshWorkerBasis===true&&
    preFinal.acceptedFinalTransferred===false&&
    preFinal.nativeCiiReleaseAuthorized===false&&
    preFinal.sourceXmlSha256===sourceSha&&
    preFinal.fixedXmlSha256===fixedSha&&
    same(preFinal.reviewedActionIds,ids)&&
    preFinal.ownerEvidenceCount===ids.length&&
    same(preFinal.sourceLineage,lineage)&&
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
    const ops=perOps.get(id),footprint=new Set(sourceFootprints[i].keys);
    requireBatch(req?.eligible===true&&req.sourceSha256===sourceSha&&
      same([...ev.sourceRecordKeys].sort(),[...req.nodeKeys].sort())&&
      ev.operationCount===ops.length&&ops.length>=req.nodeKeys.length&&
      unique(ops.map(x=>x.source_node_key))&&
      same(ops.filter(op=>op.operation==='REMOVE_SELECTED_SHORT_ELEMENT_RECORD')
          .map(op=>op.source_node_key).sort(),[...req.nodeKeys].sort())&&
      ev.portEdits.length===ops.filter(op=>op.operation==='CLOSE_COMPONENT_PORT').length,
      'BATCH_PER_OWNER_ACCOUNTING');
    // This witness is recomputed by the Python group transaction from
    // its CURRENT source; JS validates actual edits against it before any
    // checkpoint. A removed native guard cannot be papered over by JS.
    requireBatch([...req.nodeKeys,req.leftKey,req.rightKey]
      .every(k=>footprint.has(k))&&
      ops.every(op=>footprint.has(op.source_node_key))&&
      ev.portEdits.every(edit=>footprint.has(edit.key)),
      'BATCH_OWNER_EDITS_OUTSIDE_FOOTPRINT');
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
  hash,runLegacy,planning,sourceRecords,maximum=MAX_GROUP,
}){
  if(!source||!Array.isArray(shortElements)||!Array.isArray(selectedIds)||
     !unique(selectedIds)||typeof runEngine!=='function'||
     typeof runLegacy!=='function'||typeof hash!=='function'||
     !Number.isInteger(maximum)||maximum<2||maximum>MAX_GROUP)
    throw Error('SHORT_BATCH_INVALID_SELECTION');
  let current={...source},rows=shortElements,latest=null;
  const requested=[...selectedIds],applied=[],skipped=[],processed=new Set();
  const plannedGroups=planSourceBoundGroups(requested,rows,planning,
    current.sourceSha256,maximum,sourceRecords);
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
    processed.add(id);completed++;
    checkpoint();notify(id,output.applied.length?'VALIDATED':'REFUSED');
  };
  const runGroup=async ids=>{
    if(stopReason!=='COMPLETE')return;
    if(!isCurrent()){stopReason='CANCELLED';return;}
    if(ids.length===1){await mergeLegacy(ids[0]);return;}
    const rowMap=new Map(rows.map(r=>[r.id,r]));
    const groupRows=ids.map(id=>rowMap.get(id));
    if(groupRows.some(row=>!row?.eligible||row.sourceSha256!==current.sourceSha256)){
      const mid=Math.floor(ids.length/2);
      await runGroup(ids.slice(0,mid));
      if(stopReason==='COMPLETE')await runGroup(ids.slice(mid));
      return;
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
      for(const id of ids)processed.add(id);
      completed+=ids.length;
      checkpoint();notify(ids.at(-1),'VALIDATED');
    }catch(error){
      stopReason='TRANSACTION_FAILED';failedId=ids[0];
      stopMessage=String(error?.message||error);
    }
  };
  if(lease)runEngine.beginBulkSession();
  try{
    for(const ids of plannedGroups){
      if(stopReason!=='COMPLETE')break;
      if(!isCurrent()){stopReason='CANCELLED';break;}
      await runGroup(ids);
    }
  }finally{if(lease)runEngine.endBulkSession();}
  const hubMismatch=hubEnabled&&
    stopReason!=='COMPLETE'&&stopReason!=='CANCELLED';
  const pendingIds=requested.filter(id=>!processed.has(id)&&id!==failedId);
  return {originSha256:source.sourceSha256,latest,applied,skipped,requested,
    completed,failedId,pendingIds,currentEligible:rows.filter(r=>r.eligible).length,
    stopReason,stopMessage,hubMismatch};
}
