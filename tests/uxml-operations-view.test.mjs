import test from 'node:test';
import assert from 'node:assert/strict';
import {assertOperationsPreview,filterOperationRows,kindCounts,
 visibleOperationExport,operationsCSV} from '../tabs/topology-workspace/uxml-operations-view.mjs';

const sha='a'.repeat(64);
function sample(){
 return {schema:'uxml-operations-preview/v1',sourceSha256:sha,
  summary:{totalOps:2,byKind:{ALIAS_COINCIDENT_NODE:1,CLOSE_PORT_CONNECTION:1},
   sourceRecordCount:3,untouchedRecordCount:1},
  ops:[
   {opId:'UXML-OP-A',kind:'ALIAS_COINCIDENT_NODE',
    kindName:'Alias coincident node',sourceActionId:'ACT-A',
    uxmlIds:['UXML-A'],sourceRecords:[
     {format:'PSI116',recordKey:'B0:N1:S0',changed:true}],
    changes:[{recordKey:'B0:N1:S0',field:'NodeNumber',before:'1',after:'2'}],
    policyReason:'PROPOSED, 0.99 ≥ 0.95'},
   {opId:'UXML-OP-B',kind:'CLOSE_PORT_CONNECTION',
    kindName:'Close compatible connection ports',sourceActionId:'ACT-B',
    uxmlIds:['UXML-B'],sourceRecords:[
     {format:'PSI116',recordKey:'B0:N2:S1',changed:true}],
    changes:[{recordKey:'B0:N2:S1',field:'Position',
     before:'20 0 0',after:'21 0 0'}],
    policyReason:'PROPOSED, 0.99 ≥ 0.95'},
  ]};
}
test('preview validates operation count, source custody, field changes and untouched count',()=>{
 const preview=sample();
 assert.equal(assertOperationsPreview(preview,sha),preview);
 assert.deepEqual(kindCounts(preview).map(row=>row.count),[1,1]);
 assert.throws(()=>assertOperationsPreview(preview,'b'.repeat(64)),/SOURCE_OR_SCHEMA/);
 const changed=sample();
 changed.ops[0].changes[0].recordKey='B0:N3:S2';
 assert.throws(()=>assertOperationsPreview(changed,sha),/ROW_INVALID/);
 const wrong=sample();
 wrong.summary.untouchedRecordCount=0;
 assert.throws(()=>assertOperationsPreview(wrong,sha),/SUMMARY_MISMATCH/);
});
test('kind filter and exact record-key query never hide operations in the canonical export',()=>{
 const preview=sample();
 assert.deepEqual(filterOperationRows(preview,{kind:'ALIAS_COINCIDENT_NODE'})
   .map(r=>r.opId),['UXML-OP-A']);
 assert.deepEqual(filterOperationRows(preview,{search:'b0:n2:s1'})
   .map(r=>r.opId),['UXML-OP-B']);
 assert.equal(preview.ops.length,2);
});
test('export mirrors active kind/search and drops every non-visible internal field',()=>{
 const preview=sample();
 const filtered=visibleOperationExport(preview,3,{kind:'ALIAS_COINCIDENT_NODE'});
 assert.equal(filtered.operations.length,1);
 assert.deepEqual(filtered.operations.map(row=>row.opId),['UXML-OP-A']);
 assert.equal(filtered.summary.totalOps,2);
 assert.equal(filtered.summary.visibleOpsCount,1);
 assert.equal(filtered.summary.untouchedRecordCount,1);
 assert.deepEqual(Object.keys(filtered.summary.byKind).sort(),
   ['Alias coincident node','Close compatible connection ports']);
 assert.equal('kind' in filtered.operations[0],false);
 assert.equal('sourceActionId' in filtered.operations[0],false);
 assert.equal('sourceRecordCount' in filtered.summary,false);
 assert.equal('schema' in filtered,false);
 assert.equal('sourceSha256' in filtered,false);
 const searched=visibleOperationExport(preview,3,{search:'B0:N2:S1'});
 assert.deepEqual(searched.operations.map(row=>row.opId),['UXML-OP-B']);
 assert.equal(searched.summary.visibleOpsCount,1);
 const csv=operationsCSV(preview,3,{kind:'ALIAS_COINCIDENT_NODE'});
 assert.equal(csv.trimEnd().split('\n').length,2);
 assert.match(csv,/Alias coincident node/);
 assert.doesNotMatch(csv,/Close compatible connection ports/);
 const zero=visibleOperationExport(preview,3,{search:'NOT_A_SOURCE_REF'});
 assert.equal(zero.operations.length,0);
 assert.equal(zero.summary.visibleOpsCount,0);
 assert.equal(operationsCSV(preview,3,{search:'NOT_A_SOURCE_REF'}).trimEnd().split('\n').length,1);
});
test('JSON and CSV disclose only visible columns, one row per operation and reject formula-like data',()=>{
 const preview=sample();
 preview.ops[0].policyReason='=INJECT()';
 const data=visibleOperationExport(preview,1);
 assert.equal(data.operations.length,2);
 assert.equal(data.summary.reviewOnlyCount,1);
 assert.equal('sourceSha256' in data,false);
 assert.equal('sourceText' in data,false);
 assert.equal('fileSha256' in data.operations[0],false);
 const csv=operationsCSV(preview,1);
 assert.equal(csv.trimEnd().split('\n').length,3);
 assert.match(csv,/'=INJECT\(\)/);
 assert.match(csv,/Alias coincident node/);
});

test('short owner raw-only child disclosure is validated and exported without turning fields into actions',()=>{
 const preview={schema:'uxml-operations-preview/v1',sourceSha256:sha,
  summary:{totalOps:1,byKind:{DROP_SHORT_ELEMENT:1},
    sourceRecordCount:2,untouchedRecordCount:1},
  ops:[{opId:'UXML-OP-SHORT-1',kind:'DROP_SHORT_ELEMENT',
    kindName:'Drop selected short component and close ports',
    sourceActionId:'SHORT:1',uxmlIds:['OWNER'],
    sourceRecords:[{format:'PSI116',recordKey:'B0:N3:S2',changed:true}],
    changes:[{recordKey:'B0:N3:S2',field:'Source record',
      before:'Present',after:'Removed'}],
    removedWithRecord:[{recordKey:'B0:N3:S2',field:'SIF'},
      {recordKey:'B0:N3:S2',field:'CorrosionAllowance'}],
    policyReason:'Only the original deleted owner is removed'}]};
 assert.equal(assertOperationsPreview(preview,sha),preview);
 const visible=visibleOperationExport(preview);
 assert.deepEqual(visible.operations[0].removedWithRecord,preview.ops[0].removedWithRecord);
 assert.match(operationsCSV(preview),/Removed with deleted element/);
 assert.match(operationsCSV(preview),/CorrosionAllowance/);
 for(const mutate of [
   x=>{delete x.removedWithRecord;},
   x=>x.removedWithRecord.push({recordKey:'B0:N99:S99',field:'SIF'}),
   x=>x.removedWithRecord.push({recordKey:'B0:N3:S2',field:'SIF'}),
   x=>x.removedWithRecord.push({recordKey:'B0:N3:S2',field:''}),
 ]){
   const damaged=structuredClone(preview);
   mutate(damaged.ops[0]);
   assert.throws(()=>assertOperationsPreview(damaged,sha),/UXML_OPS_PREVIEW_ROW_INVALID/);
 }
});
