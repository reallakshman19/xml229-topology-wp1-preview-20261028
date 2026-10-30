/** Source-bound bulk short-element orchestration without intermediate canvas renders.
 * Existing Python atomic transactions and full pre-Final replay remain the authority.
 * A failed later transaction cannot publish unvalidated bytes.
 */
async function digestXml(text) {
  const bytes=new TextEncoder().encode(text);
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  return [...new Uint8Array(hash)].map(v=>v.toString(16).padStart(2,'0')).join('');
}

export async function runShortBulk({
  source,shortElements,selectedIds,runEngine,
  isCurrent=()=>true,onCheckpoint=()=>{},onProgress=()=>{},
  hash=digestXml,
}){
  if(!source?.sourceSha256||typeof source.sourceText!=='string'||
     !Array.isArray(shortElements)||!Array.isArray(selectedIds)||
     new Set(selectedIds).size!==selectedIds.length)
    throw Error('SHORT_BULK_INVALID_SELECTION');
  let current={...source},rows=shortElements;
  const applied=[],skipped=[],requested=[...selectedIds];
  let latest=null,completed=0,stopReason='COMPLETE',stopMessage='';
  for(const id of requested){
    if(!isCurrent()){stopReason='CANCELLED';break;}
    const row=rows.find(r=>r.id===id);
    if(!row?.eligible||row.sourceSha256!==current.sourceSha256){
      skipped.push({id,reason:row?.reason||'NOT_ELIGIBLE_ON_CURRENT_REVISION'});
      completed++;
      onProgress({completed,total:requested.length,applied:applied.length,skipped:skipped.length,id,status:'SKIPPED'});
      continue;
    }
    try{
      onProgress({completed,total:requested.length,applied:applied.length,skipped:skipped.length,id,status:'APPLYING'});
      const request={id:row.id,sourceSha256:current.sourceSha256,nodeKeys:[...row.nodeKeys]};
      const result=await runEngine({
        sourceKind:'xml',sourceText:current.sourceText,sourceName:current.name,topologyPreFinalOnly:true,
        options:{outputMode:'enriched-only',analyzeTopology:true,generateTopoFix:true,
          useTopoFixForCii:false,topologyActionIds:[id],topologyShortElementRequests:[request]},
      });
      if(!isCurrent()){stopReason='CANCELLED';break;}
      if(result?.ok!==true || result.outputKind!=='topology-sidecars'||
         result.acceptedFinalTransferred!==false||
         result.nativeCiiReleaseAuthorized!==false||
         result.ciiText||result.enrichedText||result.topoFixCommitted!==true||
         !result.topoFixXmlText)
        throw Error('SHORT_BULK_TRANSACTION_REJECTED: '+String(result?.error||'no committed result'));
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
      applied.push({id,sourceSha256:current.sourceSha256,fixedSha256:fixedSha,
        request,selectedElement:row,transaction:txn,validation,lineage,preFinal});
      current={...current,sourceText:result.topoFixXmlText,sourceSha256:fixedSha};
      rows=findings.shortElements;
      latest={source:current,findings,plan};
      completed++;
      // Every checkpoint has passed the existing Python pre-Final replay.
      // UI saves it without repainting the canvas or presenting individual prompts.
      onCheckpoint({originSha256:source.sourceSha256,latest,
        applied:[...applied],skipped:[...skipped],requested,completed});
      onProgress({completed,total:requested.length,applied:applied.length,skipped:skipped.length,id,status:'VALIDATED'});
    }catch(error){
      if(!isCurrent()){stopReason='CANCELLED';break;}
      stopReason='TRANSACTION_FAILED';
      const reason=String(error?.message||error);
      stopMessage=reason.includes('RECONNECTION')
        ?'Selected element retained: surrounding ports cannot reconnect. Check restraints, mating diameters and port directions.'
        :reason;
      break; // Fail closed: do not silently skip a failed authoritative transaction.
    }
  }
  return {originSha256:source.sourceSha256,latest,applied,skipped,requested,
    completed,stopReason,stopMessage};
}
