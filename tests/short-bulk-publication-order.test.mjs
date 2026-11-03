/**
 * Source-order safety contract for UXML short bulk publication.
 * This test intentionally kills an in-memory RELEASE-EARLY mutant. A release
 * token must not be assigned before the last potentially throwing statement.
 * Run with node --test tests/short-bulk-publication-order.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source=readFileSync('tabs/topology-workspace/workspace-app.mjs','utf8');
const between=(start,end)=>{
  const first=source.indexOf(start),last=source.indexOf(end,first+start.length);
  assert.ok(first>=0&&last>first,'named product source blocks must exist');
  return source.slice(first,last);
};
const publish=between('  async function publishShortBulk(', '  /** All short-bulk publication paths');
const wrapper=between('  async function publishShortBulkGuarded(', '  async function dropShortElements()');
const settle=between('export async function settleShortBulkPublication(', 'async function sha256(');

function assertReleaseLast(body,finalizer=settle){
  const call=body.lastIndexOf('await settleShortBulkPublication(');
  assert.ok(call>=0,'workspace MUST invoke the audited release-last finalizer');
  for(const required of [
    "parseOccurrenceScene(next.source.sourceText",
    'canvas.setScene(scene);sourceMeta();',
    "if(checked+unprocessed!==selected)throw",
    "query(root,'[data-progress]').textContent=message;",
    "setFixStatus(message,",
    'showShortBulkAudit(outcome);',
    'updateStatus(',
  ]){
    const at=body.indexOf(required);
    assert.ok(at>=0&&at<call,
      'workspace finalizer must follow every prior potentially throwing step: '+required);
  }
  const release=/state\.hubRevision=state\.revision;/g;
  const callback=body.indexOf("refreshEvidence:()=>refreshPublishedEvidence(",call);
  assert.ok(callback>call,
    'workspace must pass fresh evidence recheck into audited finalizer');
  const found=[...finalizer.matchAll(release)];
  assert.equal(found.length,1,'one and only one source-release promotion');
  const at=found[0].index;
  for(const required of [
    'await refreshEvidence();','renderTerminal();',
    "state.hubParity?.status==='EQUAL'&&analysisProofCurrent()",
  ]){
    const index=finalizer.indexOf(required);
    assert.ok(index>=0&&index<at,
      'finalizer release must FOLLOW evidence and final rendering: '+required);
  }
  assert.match(finalizer.slice(at),/^state\.hubRevision=state\.revision;\s*}\s*$/,
    'finalizer promotion is the last statement with no further throwable work');
  assert.ok(body.indexOf('state.hubRevision=null;')<body.indexOf('state.source=next.source;'),
    'previous authority must be revoked before source mutation');
  assert.match(body,/outcome\?\.hubMismatch===true/,
    'UI must retain Worker explicit mismatch HOLD');
}

test('hub revision is released LAST after canvas, reconciliation, status and evidence recheck',()=>{
  assertReleaseLast(publish);
});
test('KILL in-memory RELEASE-EARLY mutant: moving promotion before canvas must fail source-order proof',()=>{
  const release='state.hubRevision=state.revision;';
  const mutant=settle.replace(release,'').replace(
    'if(outcome.latest&&done&&!hubMismatch)await refreshEvidence();',
    release+'\n  if(outcome.latest&&done&&!hubMismatch)await refreshEvidence();');
  let killed=false;
  try{assertReleaseLast(publish,mutant);}catch(error){
    assert.equal(error.name,'AssertionError');
    killed=true;
  }
  assert.equal(killed,true,'source-release mutation must be detected');
  console.info('MUTANT_KILLED: RELEASE_EARLY · pre-canvas promotion violates final-statement contract');
});
test('one non-throwing guarded publisher handles finish, native ERROR and Cancel',()=>{
  assert.match(wrapper,/try\s*{\s*await publishShortBulk\(outcome,generation\)/);
  assert.match(wrapper,/catch\(error\)/);
  assert.match(wrapper,/holdShortHubRelease\(label\)/);
  assert.match(wrapper,/const retry=\{\.\.\.outcome,stopReason:'ERROR'/,
    'fallback must use actual validated outcome, not an empty checkpoint');
  assert.match(wrapper,/catch\(republishError\)/);
  assert.match(wrapper,/return false;/);
  const all=source.match(/\bawait publishShortBulk\(/g)||[];
  assert.equal(all.length,2,'only the guarded wrapper calls the raw publisher');
  const calls=source.match(/\bawait publishShortBulkGuarded\(/g)||[];
  assert.equal(calls.length,3,'normal completion, outer error and Cancel use one guarded publisher');
});
test('KILL UI native-HOLD-witness deletion: declared COMPLETE still cannot bypass explicit disagreement',()=>{
  assert.match(publish,/outcome\?\.hubMismatch===true/);
  const mutant=publish.replace('||outcome?.hubMismatch===true','');
  let killed=false;
  try{assertReleaseLast(mutant);}catch(error){
    assert.equal(error.name,'AssertionError');
    killed=true;
  }
  assert.equal(killed,true);
  console.info('MUTANT_KILLED: UI_DROPS_NATIVE_HUB_MISMATCH · worker HOLD witness missing');
});
