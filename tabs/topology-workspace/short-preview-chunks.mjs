/** Read-only aggregation of per-chunk UXML short-operation previews.
 * Every chunk must independently pass its own exact selected=accepted+refused
 * custody contract. Only after the complete set passes is a report published.
 */
import {assessShortPreview} from './short-preview-model.mjs';

export const SHORT_HUB_PREVIEW_CHUNK_SIZE=4;
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);

export function mergeShortHubPreviewChunks(chunks, selectedIds) {
  if(!Array.isArray(chunks)||!chunks.length||!Array.isArray(selectedIds)||
     !selectedIds.length||new Set(selectedIds).size!==selectedIds.length)
    throw Error('UXML_SHORT_PREVIEW_CHUNKS_INVALID');
  const first=chunks[0]?.preview;
  if(!first||first.schema!=='uxml-operations-preview/v1'||
     !first.sourceSha256||!Array.isArray(first.ops)||
     !Number.isSafeInteger(first.summary?.sourceRecordCount))
    throw Error('UXML_SHORT_PREVIEW_CHUNK_SCHEMA_INVALID');
  const baseline=first.ops.filter(x=>x.kind!=='DROP_SHORT_ELEMENT');
  const allShort=[],refused=[],observed=[],allIds=new Set();
  for(const piece of chunks){
    if(!piece||!Array.isArray(piece.ids)||!piece.ids.length||!piece.preview||
       piece.preview.schema!==first.schema||
       piece.preview.sourceSha256!==first.sourceSha256||
       piece.preview.summary?.sourceRecordCount!==first.summary.sourceRecordCount||
       !Array.isArray(piece.preview.ops))
      throw Error('UXML_SHORT_PREVIEW_CHUNK_SOURCE_DRIFT');
    const matchingBaseline=piece.preview.ops.filter(x=>x.kind!=='DROP_SHORT_ELEMENT');
    if(!same(matchingBaseline,baseline))
      throw Error('UXML_SHORT_PREVIEW_CHUNK_BASELINE_DRIFT');
    const assessed=assessShortPreview(piece.preview,piece.ids);
    const selected=piece.preview.shortPreview.selectedIds;
    if(!same(selected,piece.ids))
      throw Error('UXML_SHORT_PREVIEW_CHUNK_ORDER_DRIFT');
    for(const id of piece.ids){
      if(allIds.has(id))throw Error('UXML_SHORT_PREVIEW_CHUNK_DUPLICATE');
      allIds.add(id);
    }
    observed.push(...selected);
    allShort.push(...piece.preview.ops.filter(x=>x.kind==='DROP_SHORT_ELEMENT'));
    refused.push(...assessed.refused.map(({id,code})=>({id,code})));
  }
  if(!same(observed,selectedIds))
    throw Error('UXML_SHORT_PREVIEW_CHUNK_SET_MISMATCH');
  const ops=[...baseline,...allShort],edited=new Set(),byKind={};
  const opIds=new Set();
  for(const op of ops){
    if(opIds.has(op.opId))throw Error('UXML_SHORT_PREVIEW_CHUNK_OP_DUPLICATE');
    opIds.add(op.opId);
    byKind[op.kind]=(byKind[op.kind]||0)+1;
    for(const change of op.changes||[])edited.add(change.recordKey);
  }
  if(edited.size>first.summary.sourceRecordCount)
    throw Error('UXML_SHORT_PREVIEW_CHUNK_RECORD_COUNT_INVALID');
  const merged={
    schema:first.schema,sourceSha256:first.sourceSha256,
    summary:{totalOps:ops.length,byKind:Object.fromEntries(
      Object.entries(byKind).sort(([a],[b])=>a.localeCompare(b))),
      sourceRecordCount:first.summary.sourceRecordCount,
      untouchedRecordCount:first.summary.sourceRecordCount-edited.size},
    shortPreview:{selectedIds:[...selectedIds],
      acceptedIds:allShort.map(x=>x.sourceActionId),refused},
    ops,
  };
  assessShortPreview(merged,selectedIds);
  return merged;
}
