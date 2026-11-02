/** Source-bound bulk short-element orchestration without intermediate canvas renders.
 * Existing Python atomic transactions and full pre-Final replay remain the authority.
 * A failed later transaction cannot publish unvalidated bytes.
 */
// A per-owner canonical loss/eligibility veto has a named refusal, not a
// whole-source parity disagreement. Only this narrow source-coded rejection
// can be skipped; all other parity failures HOLD the batch.
// ONLY source-bound, non-mutating owner refusal codes. Authority mismatch,
 // malformed requests, and disagreement must STOP the entire batch.
const SKIPPABLE_HUB_OWNER_CODES=new Set([
  'UXML_LOSS_CONTRACT_FIELD_TOUCH',
  'UXML_CLOS_WRITE_HELD',
  'UXML_SHORT_NATIVE_REFUSED',
  'UXML_SHORT_NOT_ELIGIBLE_OR_WITNESS_DRIFT',
]);
export function namedHubOwnerRefusal(result){
  if(result?.topologyUxmlParity?.status!=='DIFFERENT'||
     result?.ok!==true||result?.topoFixCommitted===true||
     result?.topoFixXmlText||result?.acceptedFinalTransferred!==false||
     result?.nativeCiiReleaseAuthorized!==false)return null;
  const differences=result?.topologyUxmlParity?.differences;
  if(!Array.isArray(differences)||differences.length!==1)return null;
  const match=/^\/patchBack: UxmlPatchError: (UXML_[A-Z0-9_]+)(?::([^\r\n]*))?$/.exec(differences[0]);
  return match&&SKIPPABLE_HUB_OWNER_CODES.has(match[1])?
    match[1]+(match[2]===undefined?'':':'+match[2]):null;
}

let memoSessionOrdinal=0;
async function digestXml(text) {
  const bytes=new TextEncoder().encode(text);
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  return [...new Uint8Array(hash)].map(v=>v.toString(16).padStart(2,'0')).join('');
}

export async function runShortBulk({
  source,shortElements,selectedIds,runEngine,hubEnabled=false,
  isCurrent=()=>true,onCheckpoint=()=>{},onProgress=()=>{},
  hash=digestXml,
}){
  if(!source?.sourceSha256||typeof source.sourceText!=='string'||
     !Array.isArray(shortElements)||!Array.isArray(selectedIds)||
     new Set(selectedIds).size!==selectedIds.length)
    throw Error('SHORT_BULK_INVALID_SELECTION');
  let current={...source},rows=shortElements;
  const applied=[],skipped=[],requested=[...selectedIds];
  let latest=null,completed=0,stopReason='COMPLETE',stopMessage='',failedId=null;
  const lease=hubEnabled&&typeof runEngine.beginBulkSession==='function'&&
    typeof runEngine.endBulkSession==='function';
  if(lease)runEngine.beginBulkSession();
  try{
  for(const id of requested){
    if(!isCurrent()){stopReason='CANCELLED';break;}
    const row=rows.find(r=>r.id===id);
    if(!row?.eligible||row.sourceSha256!==current.sourceSha256){
      skipped.push({id,reason:row?.reason||'NOT_ELIGIBLE_ON_CURRENT_REVISION',
        sourceSha256:current.sourceSha256});
      completed++;
      // Even a no-write skip advances the audited checkpoint. Cancel must not
      // misreport an already refused item as still unprocessed.
      onCheckpoint({originSha256:source.sourceSha256,latest,
        applied:[...applied],skipped:[...skipped],requested,completed});
      onProgress({completed,total:requested.length,applied:applied.length,skipped:skipped.length,
        currentEligible:rows.filter(r=>r.eligible).length,id,status:'SKIPPED'});
      continue;
    }
    try{
      const itemStartedMs=Date.now();
      onProgress({completed,total:requested.length,applied:applied.length,skipped:skipped.length,
        currentEligible:rows.filter(r=>r.eligible).length,id,status:'APPLYING'});
      const request={id:row.id,sourceSha256:current.sourceSha256,nodeKeys:[...row.nodeKeys]};
      const result=await runEngine({
        sourceKind:'xml',sourceText:current.sourceText,sourceName:current.name,topologyPreFinalOnly:true,
        options:{outputMode:'enriched-only',analyzeTopology:true,generateTopoFix:true,
          useTopoFixForCii:false,topologyActionIds:[id],
          topologyShortElementRequests:[request],topologyUxmlPreview:hubEnabled,
          topologyBulkSession:hubEnabled,topologyBulkSpeedProfile:hubEnabled},
        sourceRawSha256:current.rawSha256||current.sourceSha256,
      });
      if(!isCurrent()){stopReason='CANCELLED';break;}
      if(hubEnabled&&result?.topologyUxmlParity?.status!=='EQUAL'){
        const refused=namedHubOwnerRefusal(result);
        if(refused){
          // Canonical source-only veto: no output was committed. Keep the
          // exact code and move to the next owner on the unchanged source.
          skipped.push({id,reason:refused,sourceSha256:current.sourceSha256});
          completed++;
          onCheckpoint({originSha256:source.sourceSha256,latest,
            applied:[...applied],skipped:[...skipped],requested,completed});
          onProgress({completed,total:requested.length,applied:applied.length,
            skipped:skipped.length,currentEligible:rows.filter(r=>r.eligible).length,
            id,status:'REFUSED',reason:refused});
          continue;
        }
        throw Error('UXML_SHORT_PARITY_'+
          String(result?.topologyUxmlParity?.status||'UNAVAILABLE')+
          ': '+(result?.topologyUxmlParity?.differences||[]).join(' | '));
      }
      if(result?.ok!==true || result.outputKind!=='topology-sidecars'||
         result.acceptedFinalTransferred!==false||
         result.nativeCiiReleaseAuthorized!==false||
         result.ciiText||result.enrichedText||result.topoFixCommitted!==true||
         !result.topoFixXmlText)
        throw Error('SHORT_BULK_TRANSACTION_REJECTED: '+String(result?.error||'no committed result'));
      // Produced only after export_edit_ops + apply_edit_ops independently
      // rederive canonical targets/params and compare full native bytes.
      const editOps=hubEnabled?result.topologyUxmlAppliedEditOps:null;
      if(hubEnabled){
        const op=Array.isArray(editOps)&&editOps.length===1?editOps[0]:null;
        const disclosure=op?.removedWithRecord;
        const requestWitness=op?.params?.[0]?.request;
        if(op?.kind!=='DROP_SHORT_ELEMENT'||
           op.opId!=='UXML-OP-'+id||
           op.sourceActionId!==id||op.fileSha256!==current.sourceSha256||
           !Array.isArray(op.targets)||!op.targets.length||
           new Set(op.targets).size!==op.targets.length||
           !Array.isArray(disclosure)||
           !disclosure.every(w=>typeof w?.recordKey==='string'&&
             op.targets.includes(w.recordKey)&&typeof w?.field==='string'&&w.field)||
           new Set(disclosure.map(w=>w.recordKey+'\0'+w.field)).size!==disclosure.length||
           requestWitness?.id!==request.id||
           requestWitness?.sourceSha256!==request.sourceSha256||
           JSON.stringify(requestWitness?.nodeKeys)!==JSON.stringify(request.nodeKeys))
          throw Error('UXML_SHORT_APPLY_CANONICAL_OP_RECEIPT_MISSING_OR_DRIFT');
      }
      const txn=JSON.parse(result.topoFixTransactionText||'null');
      const validation=JSON.parse(result.topoFixValidationText||'null');
      const lineage=JSON.parse(result.topoFixLineageText||'null');
      const preFinal=JSON.parse(result.topoFixPreFinalHandoffText||'null');
      const findings=JSON.parse(result.topoFixPostFindingsText||'null');
      const plan=JSON.parse(result.topoFixPostPlanText||'null');
      const fixedSha=await hash(result.topoFixXmlText);
      if(!isCurrent()){stopReason='CANCELLED';break;}
      if(txn?.source?.sha256!==current.sourceSha256||
         validation?.sourceSha256!==current.sourceSha256||
         txn.committed!==true||validation.committed!==true||
         txn.sourceXmlMutated!==false||
         txn.schema!=='psi116-topofix-transaction/v1'||
         validation.schema!=='psi116-topofix-validation/v1'||
         JSON.stringify(txn.selectedActions)!==JSON.stringify([id])||
         txn.fixedXmlSha256!==fixedSha||validation.fixedXmlSha256!==fixedSha||
         lineage?.sourceXmlSha256!==current.sourceSha256||
         lineage?.fixedXmlSha256!==fixedSha||
         lineage?.state!=='PRE_FINAL_ONLY'||lineage?.sourceXmlMutated!==false||
         preFinal?.requiresFreshWorkerBasis!==true||
         preFinal?.nativeCiiReleaseAuthorized!==false||
         !Array.isArray(txn.operations)||!txn.operations.some(o=>o.operation==='REMOVE_SELECTED_SHORT_ELEMENT_RECORD')||
         !Array.isArray(validation.checks)||!validation.checks.length||
         validation.summary?.blockingFailureCount!==0||
         validation.checks.some(c=>c.blocking&&!c.passed)||
         findings?.source?.sha256!==fixedSha||
         plan?.source?.sha256!==fixedSha||
         !Array.isArray(plan?.actions)||!Array.isArray(findings?.findings)||
         !Array.isArray(findings?.shortElements))
        throw Error('SHORT_BULK_SOURCE_LINEAGE_OR_RECHECK_DRIFT');
      // Full occurrence maps are verified by the authoritative Python
      // pre-Final replay. Retain their exact sidecar digest and source-linked
      // operations, not ~1,600 repeated mapping rows per selected owner.
      const fullLineageSha256=await hash(result.topoFixLineageText);
      if(!isCurrent()){stopReason='CANCELLED';break;}
      const {sourceOccurrenceMap:fullMap,...lineageHeader}=lineage;
      const compactLineage={...lineageHeader,
        fullLineageSha256,
        sourceOccurrenceMapCount:Array.isArray(fullMap)?fullMap.length:0};
      const elapsedMs=Date.now()-itemStartedMs;
      applied.push({id,sourceSha256:current.sourceSha256,fixedSha256:fixedSha,
        request,selectedElement:row,transaction:txn,validation,
        lineage:compactLineage,preFinal,elapsedMs,hubRoute:hubEnabled,
        bulkTiming:result.topologyBulkTiming||null,
        canonicalEditOps:hubEnabled?editOps:[]});
      current={...current,sourceText:result.topoFixXmlText,
        sourceSha256:fixedSha,rawSha256:fixedSha};
      rows=findings.shortElements;
      latest={source:current,findings,plan};
      completed++;
      // Every checkpoint has passed the existing Python pre-Final replay.
      // UI saves it without repainting the canvas or presenting individual prompts.
      onCheckpoint({originSha256:source.sourceSha256,latest,
        applied:[...applied],skipped:[...skipped],requested,completed});
      onProgress({completed,total:requested.length,applied:applied.length,skipped:skipped.length,
        currentEligible:rows.filter(r=>r.eligible).length,id,status:'VALIDATED',
        elapsedMs});
    }catch(error){
      if(!isCurrent()){stopReason='CANCELLED';break;}
      stopReason='TRANSACTION_FAILED';
      failedId=id;
      const reason=String(error?.message||error);
      stopMessage=reason.includes('RECONNECTION')
        ?'Selected element retained: surrounding ports cannot reconnect. Check restraints, mating diameters and port directions.'
        :reason;
      break; // Fail closed: do not silently skip a failed authoritative transaction.
    }
  }
  }finally{
    if(lease)runEngine.endBulkSession();
  }
  // Every non-cancelled hub failure is a parity/release HOLD. Unknown Worker,
  // recheck, native rejection, and malformed-result errors are not exceptions.
  const hubMismatch=hubEnabled&&stopReason!=='COMPLETE'&&stopReason!=='CANCELLED';
  return {originSha256:source.sourceSha256,latest,applied,skipped,requested,
    completed,failedId,pendingIds:requested.slice(completed+(failedId?1:0)),
    currentEligible:rows.filter(r=>r.eligible).length,stopReason,stopMessage,hubMismatch};
}
