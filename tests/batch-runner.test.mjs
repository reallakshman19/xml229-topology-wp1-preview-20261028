import test from 'node:test';
import assert from 'node:assert/strict';
import {runValidatedPasses} from '../tabs/topology-workspace/batch-runner.mjs';
test('a failed second pass retains the first validated XML and receipt',async()=>{
 let state={revision:0,sha:'S0',fix:null},calls=0;
 const receipt={source:{sha256:'S0'},fixedXmlSha256:'S1',selectedActionIds:['A']};
 const r=await runValidatedPasses({initialPlan:{actionIds:['A']},readState:()=>state,
  runPass:async()=>{if(++calls===2)throw Error('PASS_2_INJECTED');state={revision:1,sha:'S1',fix:{xml:'validated XML',report:receipt}};},
  nextPlan:()=>({actionIds:['B']})});
 assert.equal(calls,2);assert.equal(r.stopReason,'PASS_FAILED');assert.equal(r.lastFix.xml,'validated XML');assert.equal(r.lastFix.report,receipt);
 assert.equal(r.passes.length,1);assert.match(r.stopMessage,/PASS_2/);
});
test('eight-pass limit retains all validated receipts and the last copy',async()=>{
 let state={revision:0,sha:'S0',fix:null},calls=0;
 const r=await runValidatedPasses({initialPlan:{actionIds:['A']},readState:()=>state,
  runPass:async()=>{calls++;state={revision:calls,sha:'S'+calls,fix:{xml:'XML'+calls,report:{pass:calls}}};},
  nextPlan:()=>({actionIds:['A']})});
 assert.equal(calls,8);assert.equal(r.stopReason,'PASS_LIMIT');assert.equal(r.passes.length,8);assert.equal(r.lastFix.xml,'XML8');
});
test('repeated outputs stop with the last receipt',async()=>{
 let state={revision:0,sha:'S0',fix:null};
 const r=await runValidatedPasses({initialPlan:{actionIds:['A']},readState:()=>state,
  runPass:async()=>{state={revision:1,sha:'S0',fix:{xml:'copy',report:{validated:true}}};},nextPlan:()=>({actionIds:['A']})});
 assert.equal(r.stopReason,'REPEATED_OUTPUT');assert.equal(r.lastFix.xml,'copy');
});
