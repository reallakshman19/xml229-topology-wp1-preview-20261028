import test from 'node:test';
import assert from 'node:assert/strict';
import {assessShortPreview,refusalPlainReason}
  from '../tabs/topology-workspace/short-preview-model.mjs';

const ids=['SHORT:0:A','SHORT:0:B','SHORT:1:C'];
const make=()=>({
  shortPreview:{
    selectedIds:[...ids],
    acceptedIds:[ids[0],ids[2]],
    refused:[{id:ids[1],code:'UXML_LOSS_CONTRACT_FIELD_TOUCH:B0:N3:S1'}],
  },
  ops:[{kind:'DROP_SHORT_ELEMENT',sourceActionId:ids[0]},
       {kind:'DROP_SHORT_ELEMENT',sourceActionId:ids[2]}],
});
test('two accepted and one refused: no admission until exact re-preview',()=>{
  const report=assessShortPreview(make(),ids);
  assert.equal(report.readyCount,2);
  assert.equal(report.refusedCount,1);
  assert.equal(report.complete,false);
  assert.deepEqual(report.readyIds,[ids[0],ids[2]]);
  assert.equal(report.refused[0].id,ids[1]);
  assert.match(report.refused[0].code,/UXML_LOSS_CONTRACT_FIELD_TOUCH/);
  assert.match(report.refused[0].plainReason,/cannot safely preserve/);
  assert.throws(()=>assessShortPreview(make(),[ids[0],ids[2]]),
    /UXML_SHORT_PREVIEW_RESULT_SET_MISMATCH/,
    'deselecting the refused owner must invalidate the old preview');
  const fresh=make();
  fresh.shortPreview={selectedIds:[ids[0],ids[2]],
    acceptedIds:[ids[0],ids[2]],refused:[]};
  assert.equal(assessShortPreview(fresh,[ids[0],ids[2]]).complete,true);
});
test('mutant acceptance/refusal mismatch is rejected, never implicitly authorized',()=>{
  for(const edit of [
    p=>p.shortPreview.refused=[],
    p=>p.shortPreview.acceptedIds.push(ids[1]),
    p=>p.shortPreview.acceptedIds.pop(),
    p=>p.shortPreview.selectedIds.pop(),
    p=>p.shortPreview.refused.push({...p.shortPreview.refused[0]}),
    p=>p.shortPreview.refused[0].code='',
    p=>p.ops.pop(),
    p=>p.ops.push({kind:'DROP_SHORT_ELEMENT',sourceActionId:ids[1]}),
  ]){
    const p=make();edit(p);
    assert.throws(()=>assessShortPreview(p,ids),
      /UXML_SHORT_PREVIEW_RESULT_SET_MISMATCH/);
  }
});
test('named refusals have safe plain explanations without authorizing action',()=>{
  assert.match(refusalPlainReason('UXML_CLOS_WRITE_HELD:B0:S4'),/protected closed end/);
  assert.match(refusalPlainReason('UXML_SHORT_NOT_ELIGIBLE_OR_WITNESS_DRIFT'),
    /no longer qualifies/);
  assert.match(refusalPlainReason('UXML_PREVIEW_MISSING_SOURCE_REF'),/reference is missing/);
  assert.match(refusalPlainReason('UNKNOWN_SYNTHETIC_CODE'),/required source-safety check/);
});
