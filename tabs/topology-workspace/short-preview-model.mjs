/** Read-only partial short-op preview: selection custody and plain refusal reasons.
 * This module NEVER authorizes a refused item or changes native eligibility.
 */
const same=(a,b)=>JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
const unique=a=>new Set(a).size===a.length;
export function refusalPlainReason(code){
  const s=String(code||'');
  if(s.startsWith('UXML_LOSS_CONTRACT_FIELD_TOUCH'))
    return 'This original record contains information that the hub cannot safely preserve when removing or closing it.';
  if(s.startsWith('UXML_SHORT_NOT_ELIGIBLE_OR_WITNESS_DRIFT'))
    return 'The selected owner no longer qualifies or its exact original-record evidence has changed.';
  if(s.startsWith('UXML_SHORT_NATIVE_REFUSED'))
    return 'The existing native short-element transaction refused this removal or closure.';
  if(s.startsWith('UXML_CLOS_WRITE_HELD'))
    return 'This change would touch a protected closed end (CLOS). Manual review required.';
  if(s.startsWith('UXML_SHORT_SOURCE')||s.startsWith('UXML_FILE_SHA256'))
    return 'The current original-source identity or selected record set does not match.';
  if(s.startsWith('UXML_SHORT_DELETE_SET_MISMATCH'))
    return 'The deletion set does not match the exact selected original owner records.';
  if(s.startsWith('UXML_PREVIEW_MISSING_SOURCE_REF'))
    return 'An exact original-source record reference is missing for this operation.';
  return 'This item did not pass a required source-safety check. Review the reason code and source record; do not apply.';
}
export function assessShortPreview(preview,selectedIds){
  const info=preview?.shortPreview;
  if(!info||!Array.isArray(selectedIds)||!Array.isArray(info.selectedIds)||
     !Array.isArray(info.acceptedIds)||!Array.isArray(info.refused)||
     !selectedIds.every(x=>typeof x==='string'&&x)||
     !info.selectedIds.every(x=>typeof x==='string'&&x)||
     !info.acceptedIds.every(x=>typeof x==='string'&&x)||
     !info.refused.every(x=>x&&typeof x.id==='string'&&x.id&&
        typeof x.code==='string'&&x.code)||
     !unique(selectedIds)||!unique(info.selectedIds)||
     !unique(info.acceptedIds)||!unique(info.refused.map(x=>x.id))||
     !same(info.selectedIds,selectedIds)||
     !unique([...info.acceptedIds,...info.refused.map(x=>x.id)])||
     !same([...info.acceptedIds,...info.refused.map(x=>x.id)],selectedIds)||
     !same(info.acceptedIds,
       (preview.ops||[]).filter(op=>op.kind==='DROP_SHORT_ELEMENT')
         .map(op=>op.sourceActionId)))
    throw Error('UXML_SHORT_PREVIEW_RESULT_SET_MISMATCH');
  return {
    readyIds:[...info.acceptedIds],
    refused:info.refused.map(x=>({id:x.id,code:x.code,
      plainReason:refusalPlainReason(x.code)})),
    readyCount:info.acceptedIds.length,
    refusedCount:info.refused.length,
    complete:info.acceptedIds.length>0&&info.refused.length===0,
  };
}
