/** Node-level production workspace dispatch, history and release-last mutant kills. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
// Only the top-level auto-mount selector is DOM dependent. Keep mount inert
// without loading a browser; the exact production helpers remain imported.
globalThis.document={querySelector:()=>null};
const {
  shortBulkWorkspaceEngineArgs,shortBulkWorkspaceHistoryEntry,
  shortBulkWorkspaceNeedsAnalysis,settleShortBulkPublication,
}=await import('../tabs/topology-workspace/workspace-app.mjs');

const source=await readFile(
  new URL('../tabs/topology-workspace/workspace-app.mjs',import.meta.url),'utf8');
function compiled(name,src=source){
  const marker=new RegExp('export (?:async )?function '+name+'\\(');
  const match=marker.exec(src);
  assert.ok(match,'production export '+name+' exists');
  const start=match.index,bodyAt=src.indexOf(') {',start);
  assert.ok(bodyAt>start,'production function body starts after parameters');
  const open=bodyAt+2;
  let depth=0,close=-1;
  for(let i=open;i<src.length;i++){
    if(src[i]==='{')depth++;
    if(src[i]==='}'&&--depth===0){close=i+1;break;}
  }
  assert.ok(close>open,'balanced production function '+name);
  return Function('return ('+src.slice(start,close).replace(/^export /,'')+')')();
}
function red(name,control){
  let error;
  try{control();}catch(e){error=e;}
  assert.ok(error instanceof assert.AssertionError,
    name+' mutated execution must make real contract assert RED');
  console.info('A6B_R1_WORKSPACE_MUTANT_RED:'+name+':'+error.name+':'+error.message.split('\n')[0]);
}

test('workspace dispatch respects OFF default, ON choice, and app invokes seam',()=>{
  const common={source:{sourceSha256:'S'},shortElements:[],selectedIds:['A'],
    runEngine:()=>{},hubEnabled:true,shortBatchPlanning:{schema:'proof'},
    shortBatchSourceRecords:[],isCurrent:()=>true,
    onCheckpoint:()=>{},onProgress:()=>{}};
  const off=shortBulkWorkspaceEngineArgs({...common,independentShortGroups:false});
  const on=shortBulkWorkspaceEngineArgs({...common,independentShortGroups:true});
  assert.equal(off.enableIndependentGroups,false);
  assert.equal(on.enableIndependentGroups,true);
  assert.equal(off.shortBatchPlanning,common.shortBatchPlanning);
  assert.match(source,/await runShortBulk\(shortBulkWorkspaceEngineArgs\(/,
    'real dropShortElements must invoke audited dispatcher');
  console.info('A6B_R1_WORKSPACE_MUTANT_GREEN:toggle-dispatch-on-off=PASS');
  const mutated=compiled('shortBulkWorkspaceEngineArgs',source.replace(
    'enableIndependentGroups:options.independentShortGroups===true',
    'enableIndependentGroups:true'));
  red('toggle-forced-ON',()=>assert.equal(mutated({
    ...common,independentShortGroups:false}).enableIndependentGroups,false,
    'GROUP_TOGGLE_DISPATCH_IGNORED'));
  const disabled=compiled('shortBulkWorkspaceEngineArgs',source.replace(
    'enableIndependentGroups:options.independentShortGroups===true',
    'enableIndependentGroups:false'));
  red('toggle-forced-OFF',()=>assert.equal(disabled({
    ...common,independentShortGroups:true}).enableIndependentGroups,true,
    'GROUP_TOGGLE_DISPATCH_IGNORED'));
});

test('real per-owner history retains distinct evidence and app invokes seam',()=>{
  const item={id:'SHORT:PUBLIC',sourceSha256:'a',fixedSha256:'b',
    ownerOperations:[{action_id:'SHORT:PUBLIC'}],
    ownerEvidence:{id:'SHORT:PUBLIC',operationCount:1},
    ownerRevision:{id:'SHORT:PUBLIC'},transaction:{operations:[{action_id:'GROUP'}]},
    validation:{checks:[]},canonicalEditOps:[]};
  const got=shortBulkWorkspaceHistoryEntry(item,0,1,{},[]);
  assert.deepEqual(got.operations,item.ownerOperations);
  assert.deepEqual(got.ownerEvidence,item.ownerEvidence);
  assert.deepEqual(got.ownerRevision,item.ownerRevision);
  assert.match(source,/state\.history\.push\(shortBulkWorkspaceHistoryEntry\(/);
  console.info('A6B_R1_WORKSPACE_MUTANT_GREEN:owner-evidence-history=PASS');
  const mutated=compiled('shortBulkWorkspaceHistoryEntry',source.replace(
    'ownerEvidence:pass.ownerEvidence||null','ownerEvidence:null'));
  red('ownerEvidence-null',()=>assert.deepEqual(
    mutated(item,0,1,{},[]).ownerEvidence,item.ownerEvidence,
    'OWNER_EVIDENCE_HISTORY_DROPPED'));
});

test('release-last waits for evidence and terminal paint; mutation is RED in Node',async()=>{
  let resolveEvidence,painted=false,proof=true;
  const state={hubEnabled:true,hubParity:{status:'EQUAL'},hubRevision:null,
    epoch:7,revision:42};
  const pending=new Promise(resolve=>{resolveEvidence=resolve;});
  const task=settleShortBulkPublication({
    state,outcome:{latest:true},done:2,hubMismatch:false,generation:7,
    refreshEvidence:()=>pending,renderTerminal:()=>{painted=true;},
    analysisProofCurrent:()=>proof});
  assert.equal(state.hubRevision,null,'no publish-time release');
  assert.equal(painted,false,'terminal paint waits for recheck');
  resolveEvidence();await task;
  assert.equal(painted,true);assert.equal(state.hubRevision,42);
  const failed={...state,hubRevision:null};
  await assert.rejects(settleShortBulkPublication({
    state:failed,outcome:{latest:true},done:2,hubMismatch:false,generation:7,
    refreshEvidence:async()=>{throw Error('EVIDENCE_FAILED');},
    renderTerminal:()=>{},analysisProofCurrent:()=>true}),/EVIDENCE_FAILED/);
  assert.equal(failed.hubRevision,null,'failed evidence must hold download');
  assert.match(source,/await settleShortBulkPublication\(/);
  const area=source.slice(source.indexOf('async function publishShortBulk('),
    source.indexOf('async function publishShortBulkGuarded('));
  assert.doesNotMatch(area,/state\.hubRevision=state\.revision/,
    'UI publication cannot bypass release-last helper');
  console.info('A6B_R1_WORKSPACE_MUTANT_GREEN:release-last-after-recheck=PASS');
  const changed=source.replace(
    'if(outcome.latest&&done&&!hubMismatch)await refreshEvidence();',
    'state.hubRevision=state.revision;\n  if(outcome.latest&&done&&!hubMismatch)await refreshEvidence();');
  const mutant=compiled('settleShortBulkPublication',changed);
  const bad={...state,hubRevision:null};
  let finish;
  const neverYet=new Promise(resolve=>{finish=resolve;});
  const attempt=mutant({state:bad,outcome:{latest:true},done:2,
    hubMismatch:false,generation:7,
    refreshEvidence:()=>neverYet,renderTerminal:()=>{},
    analysisProofCurrent:()=>true});
  red('release-last-bypassed',()=>assert.equal(bad.hubRevision,null,
    'RELEASE_LAST_BYPASSED_AT_PUBLISH'));
  finish();await attempt;
});

test('second grouped Apply requires fresh Analyze, OFF remains legacy fallback',()=>{
  assert.equal(shortBulkWorkspaceNeedsAnalysis(true,null),true);
  assert.equal(shortBulkWorkspaceNeedsAnalysis(true,{owners:[]}),false);
  assert.equal(shortBulkWorkspaceNeedsAnalysis(false,null),false);
  assert.match(source,/GROUPED_SHORT_APPLY_REANALYZE_REQUIRED/);
  assert.match(source,/shortBulkWorkspaceNeedsAnalysis\(/
    );
  console.info('A6B_R1_WORKSPACE_MUTANT_GREEN:second-grouped-run-message=PASS');
});
