import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeShortHubPreviewChunks,SHORT_HUB_PREVIEW_CHUNK_SIZE}
  from '../tabs/topology-workspace/short-preview-chunks.mjs';
import {assessShortPreview} from '../tabs/topology-workspace/short-preview-model.mjs';
import {assertOperationsPreview} from '../tabs/topology-workspace/uxml-operations-view.mjs';

const sha='a'.repeat(64);
const key=n=>'B0:N'+n+':S'+n;
const sourceRecords=n=>[{format:'PSI116',recordKey:key(n),changed:true}];
const change=n=>({recordKey:key(n),field:'Source record',before:'Present',after:'Removed'});
const row=(id,n,kind='DROP_SHORT_ELEMENT')=>({
  opId:'UXML-OP-'+id,kind,
  kindName:kind==='DROP_SHORT_ELEMENT'?'Drop selected short component and close ports':'Remove dispensable pipe record',
  sourceActionId:id,uxmlIds:['PUBLIC-'+id],sourceRecords:sourceRecords(n),
  changes:[change(n)],removedWithRecord:[],
  policyReason:'Synthetic source-bound preview; no Apply permission',
});
const baseline=row('AUTO',9,'SAFE_DROP_PIPE_GEOMETRY');
const short=(id,n)=>row(id,n);
function chunk(ids,accepted,refused=[],nonshort=[baseline]){
  const ops=[...nonshort,...accepted.map((id,i)=>short(id,Number(id.split(':').at(-1))))];
  const edited=new Set(ops.flatMap(r=>r.changes.map(c=>c.recordKey)));
  const byKind=Object.fromEntries([...new Set(ops.map(r=>r.kind))].sort()
    .map(kind=>[kind,ops.filter(r=>r.kind===kind).length]));
  return {ids,preview:{schema:'uxml-operations-preview/v1',sourceSha256:sha,
    summary:{totalOps:ops.length,byKind,sourceRecordCount:100,
      untouchedRecordCount:100-edited.size},
    shortPreview:{selectedIds:ids,acceptedIds:accepted,refused},
    ops}};
}
test('4 items per cancellable Worker chunk, never an unbounded single 89-item job',()=>{
  assert.equal(SHORT_HUB_PREVIEW_CHUNK_SIZE,4);
  assert.equal(Math.ceil(89/SHORT_HUB_PREVIEW_CHUNK_SIZE),23);
});
test('source-bound aggregation: accepted/refused, untouched distinct records and canonical row order',()=>{
  const a='SHORT:0:1',b='SHORT:0:2',c='SHORT:0:3';
  const parts=[
    chunk([a,b],[a],[{id:b,code:'UXML_LOSS_CONTRACT_FIELD_TOUCH:SYNTHETIC'}]),
    chunk([c],[c]),
  ];
  const merged=mergeShortHubPreviewChunks(parts,[a,b,c]);
  assert.deepEqual(merged.shortPreview,{selectedIds:[a,b,c],
    acceptedIds:[a,c],refused:[{id:b,code:'UXML_LOSS_CONTRACT_FIELD_TOUCH:SYNTHETIC'}]});
  assert.equal(merged.summary.totalOps,3);
  assert.deepEqual(merged.summary.byKind,{DROP_SHORT_ELEMENT:2,SAFE_DROP_PIPE_GEOMETRY:1});
  assert.equal(merged.summary.untouchedRecordCount,97);
  assert.deepEqual(merged.ops.map(r=>r.sourceActionId),['AUTO',a,c]);
  assert.equal(assessShortPreview(merged,[a,b,c]).complete,false);
  assert.equal(assertOperationsPreview(merged,sha),merged);
  const all=mergeShortHubPreviewChunks([chunk([a,b],[a,b])],[a,b]);
  assert.equal(assessShortPreview(all,[a,b]).complete,true);
  assert.equal(assertOperationsPreview(all,sha),all);
});
test('chunk loss/replay/duplicates/changed baseline are refused with no partial acceptance',()=>{
  const a='SHORT:0:1',b='SHORT:0:2';
  const good=[chunk([a],[a]),chunk([b],[b])];
  for(const [label,mutate] of [
    ['stale SHA',p=>p[1].preview.sourceSha256='b'.repeat(64)],
    ['stale nonshort baseline',p=>p[1].preview.ops[0].policyReason='changed'],
    ['duplicate selected owner',p=>p[1].ids=[a]],
    ['missing second response',p=>p.pop()],
    ['forged acceptance',p=>p[0].preview.shortPreview.acceptedIds.push(b)],
    ['row replay collision',p=>{p[1].preview.ops[1].opId=p[0].preview.ops[1].opId;}],
    ['out-of-order response',p=>p.reverse()],
  ]){
    const copy=structuredClone(good);mutate(copy);
    assert.throws(()=>mergeShortHubPreviewChunks(copy,[a,b]),/UXML_SHORT_PREVIEW_/,
      label+' must not publish partial or forged operations');
  }
});
