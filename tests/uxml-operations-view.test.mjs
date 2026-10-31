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
