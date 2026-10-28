import test from 'node:test';
import assert from 'node:assert/strict';
import {eligibleActions,previewBatchPlan,explicitlyRejectedActionIds} from '../tabs/topology-workspace/batch-plan.mjs';
const findings=[
 {finding_id:'F1',severity:'WARNING',blocking:false,node_keys:['B0:N10:S0','B0:N20:S1']},
 {finding_id:'F2',severity:'WARNING',blocking:false,node_keys:['B0:N20:S1','B0:N30:S2']},
 {finding_id:'F3',severity:'INFO',blocking:false,node_keys:['B1:N40:S0']},
 {finding_id:'F4',severity:'ERROR',blocking:true,node_keys:['B1:N50:S0']}];
const actions=[
 {action_id:'A1',finding_ids:['F1'],status:'PROPOSED',confidence:1,blockers:[],
  disposition:'ALIAS_COINCIDENT_NODE',proposed_changes:[{operation:'ALIAS_NODE'}]},
 {action_id:'A2',finding_ids:['F2'],status:'PROPOSED',confidence:1,blockers:[],
  disposition:'CONTRACT_PRESERVE_OWNER',proposed_changes:[{operation:'CONTRACT_SPAN'}]},
 {action_id:'A3',finding_ids:['F3'],status:'PROPOSED',confidence:1,blockers:[],
  disposition:'SAFE_DROP_PIPE_GEOMETRY',proposed_changes:[{operation:'DROP_PLAIN_PIPE_NODE'}]},
 {action_id:'A4',finding_ids:['F4'],status:'PROPOSED',confidence:1,blockers:[],
  disposition:'REMOVE_FALSE_RIGID',proposed_changes:[{operation:'SET_RIGID'}]},
 {action_id:'A5',finding_ids:['F3'],status:'PROPOSED',confidence:1,blockers:[],
  disposition:'MERGE_CARRIER_WITH_COMPONENT',proposed_changes:[]}];
test('Auto fix excludes BLOCKED and evidence-only work even with eligible-looking confidence',()=>{
 assert.deepEqual(eligibleActions(findings,actions).map(a=>a.action_id),['A1','A2','A3']);
 const plan=previewBatchPlan(findings,actions);
 assert.deepEqual(plan.actionIds,['A1','A3']);
 assert.deepEqual(plan.skipped.map(a=>a.actionId),['A2']);
 assert.equal(plan.skipped[0].reason,'SHARED_SOURCE_OCCURRENCE');
 assert.deepEqual(plan.skipped[0].conflictsWith,['A1']);
 assert.equal(plan.candidateCount,3);
 assert.equal(plan.notEligible,2);
});
test('Batch is deterministic across plan order and never duplicates mutation IDs',()=>{
 const a=previewBatchPlan(findings,actions);
 const b=previewBatchPlan(findings,actions.slice().reverse());
 assert.deepEqual(a.actionIds,b.actionIds);
 assert.deepEqual(a.skipped,b.skipped);
});
test('Missing exact source-qualified witnesses are excluded from a bulk transaction',()=>{
 const altered=[...actions,{action_id:'A6',finding_ids:['MISSING'],status:'PROPOSED',
  confidence:1,blockers:[],disposition:'ALIAS_COINCIDENT_NODE',
  proposed_changes:[{operation:'ALIAS_NODE'}]}];
 assert.equal(previewBatchPlan(findings,altered).candidateCount,3);
});

test('Reject unsafe plain-pipe deletion from bulk using authoritative original occurrence',()=>{
 const source=new Map([
 ['B0:N20:S1',{nodeNumber:20,type:'PIPE',nodeName:'PIPE AUTO /A',restraint:false,weight:0}],
 ['B0:N30:S2',{nodeNumber:30,type:'PIPE',nodeName:'',restraint:false,weight:0}],
 ['B1:N40:S0',{nodeNumber:40,type:'PIPE',nodeName:'',restraint:false,weight:0}]
 ]);
 const withAbsorbed=[...actions];
 withAbsorbed[0]={...actions[0],disposition:'SAFE_DROP_PIPE_GEOMETRY',absorbed_node_numbers:[20]};
 const plan=previewBatchPlan(findings,withAbsorbed,source);
 assert.equal(plan.skipped[0].actionId,'A1');
 assert.equal(plan.skipped[0].reason,'PLAIN_PIPE_REMOVAL_NOT_PROVEN_FROM_ORIGINAL_SOURCE');
 assert.ok(plan.actionIds.includes('A2'));
});
test('Only explicit per-action PSI116 application rejection permits a retry',()=>{
 assert.deepEqual(explicitlyRejectedActionIds([
  'APPLY_FAILED:Action ACT-000030 cannot remove B4:N2060:S35: ABSORBED_PIPE_HAS_NODE_NAME',
  'VALIDATION_FAILED:NO_NEW_BLOCKING_FINDINGS',
  'APPLY_FAILED:Action ACT-000030 cannot remove B4:N2060:S35: ABSORBED_PIPE_HAS_NODE_NAME'
 ]),['ACT-000030']);
 assert.deepEqual(explicitlyRejectedActionIds(['VALIDATION_FAILED:SHOULD_NOT_SKIP']),[]);
});

test('Reference-bearing or unavailable-reference records cannot enter bulk deletion',()=>{
 const safe={nodeNumber:20,type:'PIPE',nodeName:'',refNo:'',restraint:false,weight:0};
 const removal={...actions[0],disposition:'SAFE_DROP_PIPE_GEOMETRY',absorbed_node_numbers:[20]};
 for(const record of [{...safe,refNo:'UNIQUE-KEEP-REF'},{...safe,refNo:undefined}]){
  const plan=previewBatchPlan(findings,[removal],new Map([['B0:N20:S1',record]]));
  assert.deepEqual(plan.actionIds,[]);
  assert.equal(plan.skipped[0].reason,'PLAIN_PIPE_REMOVAL_NOT_PROVEN_FROM_ORIGINAL_SOURCE');
 }
 assert.deepEqual(previewBatchPlan(findings,[removal],new Map([['B0:N20:S1',safe]])).actionIds,['A1']);
});
