import test from 'node:test';
import assert from 'node:assert/strict';
import {trialGroup,trialRemaining,trialGroupFilters,trialGroupTitles,trialValidationSummary,trialDisabledReason} from '../tabs/topology-workspace/trial-clarity.mjs';
import {renderAuditHTML,filterCounts} from '../tabs/topology-workspace/audit-view.mjs';

const item=kind=>({
  fix:{kind,text:kind},finding:{finding_id:kind,code:'BRANCH_END_UNVERIFIED',
    message:'SYNTHETIC',node_keys:[],node_numbers:[],blocking:false},
  severity:'INFO',title:'Synthetic source case',rule:'Test rule',category:'gaps',action:null,
});

test('every residual disposition has exactly one group and filter; no auto-as-information',()=>{
  const items=['manual','keep','evidence','auto','manual','other'].map((kind,n)=>({
    ...item(kind),finding:{...item(kind).finding,finding_id:'CASE-'+n},
  }));
  const audit={items,groups:[{code:'BRANCH_END_UNVERIFIED',title:'Synthetic source case',
    category:'gaps',rule:'Test rule',items}]};
  const groups=trialRemaining(audit);
  assert.deepEqual(Object.fromEntries(Object.entries(groups).map(([k,rows])=>[k,rows.length])),
    {review:2,auto:1,preserve:1,information:2});
  assert.equal(trialGroup(item('keep')),'preserve');
  assert.equal(trialGroup(item('evidence')),'information');
  assert.equal(trialGroup(item('auto')),'auto');
  assert.equal(trialGroup(item('manual')),'review');
  assert.deepEqual(trialGroupFilters,{review:'manual',auto:'auto',
    preserve:'keep',information:'information'});
  assert.equal(trialGroupTitles.preserve,'No action needed: kept by rule');
  assert.equal(Object.values(groups).flat().length,items.length);
  const counts=filterCounts(audit);
  assert.deepEqual({auto:counts.auto,manual:counts.manual,keep:counts.keep,
    information:counts.information,evidence:counts.evidence},
    {auto:1,manual:2,keep:1,information:2,evidence:1});
  const expected={review:['CASE-0','CASE-4'],auto:['CASE-3'],
    preserve:['CASE-1'],information:['CASE-2','CASE-5']};
  for(const [kind,ids] of Object.entries(expected)){
    const html=renderAuditHTML(audit,{filter:trialGroupFilters[kind]});
    assert.equal(html.shown,ids.length,kind+' exact filter count');
    const seen=[...html.html.matchAll(/data-finding-id="(CASE-\d+)"/g)].map(m=>m[1]);
    assert.deepEqual(seen,ids,kind+' must not fall back to All findings');
  }
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
  assert.match(why,/Universal XML parity must be EQUAL before short-element changes/);
  assert.equal(button.disabled,true);
});

test('while short hub preview runs every disabled control names the active preview',()=>{
  const state={busy:true,activeJob:'preview',batchRunning:false,plan:{},hubEnabled:true};
  for(const name of ['short-hub-preview','preview-short','auto-fix-all',
                      'analyze','download-working','trial-current','trial-evidence']){
    const button={disabled:true,hasAttribute:x=>x==='data-'+name};
    assert.equal(trialDisabledReason(button,state),
      'Finish or cancel the active preview first.',name);
  }
  const cancel={disabled:false,hasAttribute:x=>x==='data-cancel'};
  assert.equal(trialDisabledReason(cancel,state),'');
  state.activeJob=null;
  const button={disabled:true,hasAttribute:x=>x==='data-preview-short'};
  assert.equal(trialDisabledReason(button,state),
    'Finish or cancel the active validation first.',
    'other in-flight validation retains its original wording');
});
