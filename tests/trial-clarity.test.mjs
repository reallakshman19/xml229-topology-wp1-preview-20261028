import test from 'node:test';
import assert from 'node:assert/strict';
import {trialGroup,trialRemaining,trialValidationSummary,trialDisabledReason} from '../tabs/topology-workspace/trial-clarity.mjs';
const item=(kind)=>({fix:{kind},finding:{finding_id:kind}});
test('remaining cases separated by actual fix dispositions, no review-only mutation promotion',()=>{
 const audit={items:['manual','keep','evidence','auto','manual'].map(item)};
 const groups=trialRemaining(audit);
 assert.deepEqual(Object.fromEntries(Object.entries(groups).map(([k,rows])=>[k,rows.length])),
  {review:2,preserve:2,information:1});
 assert.equal(trialGroup(item('keep')),'preserve');
 assert.equal(trialGroup(item('manual')),'review');
});
test('native validation counts require passed checks, never fabricate 9/9',()=>{
 assert.equal(trialValidationSummary([{validation:[{passed:true},{passed:false}]}]),
  '1/2 checks passed');
 assert.equal(trialValidationSummary([],{report:{validationChecks:[{passed:true},{passed:true}]}}),
  '2/2 checks passed');
 assert.equal(trialValidationSummary([],null),'validation checks not available');
});
test('disabled action shows exact hub/direct reason without modifying disabled property',()=>{
 const button={disabled:true,hasAttribute:x=>x==='data-preview-short'};
 const state={hubEnabled:true,busy:false,batchRunning:false,plan:{}};
 const why=trialDisabledReason(button,state);
 assert.match(why,/Runs on the direct route only.*Untick Universal XML route/);
 assert.equal(button.disabled,true);
});
