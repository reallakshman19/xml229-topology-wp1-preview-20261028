/** Lane-A follow-up safety source-order and UI-failure falsifiers.
 * The earlier #32 structural source proof remains; these tests protect the
 * independent runFix path and the post-complete UI/Error status.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const workspace=readFileSync('tabs/topology-workspace/workspace-app.mjs','utf8');
const docs=readFileSync('docs/uxml-short-drop-edit-ops.md','utf8');
const method=(start,end)=>{
 const a=workspace.indexOf(start),b=workspace.indexOf(end,a+start.length);
 assert.ok(a>=0&&b>a,start+' must exist before '+end);
 return workspace.slice(a,b);
};
const fix=method('  async function runFix(', '  function autoFix(');
const refresh=method('  function refresh() {','  function select(ids,add=false)');

function assertRunFixReleaseLast(source){
 const scene=source.indexOf('canvas.setScene(nextScene);sourceMeta();');
 const status=source.indexOf("updateStatus('Repair applied and rechecked.");
 const refresh=source.indexOf('        refresh();',status);
 const release=source.indexOf('state.hubRevision=state.revision;',status);
 assert.ok(scene>=0&&status>scene&&refresh>status&&release>refresh,
   'runFix must withhold hubRevision until after canvas/status and guarded refresh');
 assert.ok(source.indexOf('state.hubRevision=null;state.fixFinalizing=true;')<scene,
   'runFix must revoke previously admitted revision before mutation');
 assert.match(source,/if\(state\.hubEnabled\)holdShortHubRelease\('RUN_FIX_PUBLICATION_FAILED:/);
}
test('runFix releases hub only after canvas/status/refresh and guards publication faults',()=>{
 assertRunFixReleaseLast(fix);
});
test('KILL early runFix release mutation',()=>{
 const code=fix.replace('state.hubRevision=state.revision;','')
  .replace('canvas.setScene(nextScene);sourceMeta();',
   'state.hubRevision=state.revision;canvas.setScene(nextScene);sourceMeta();');
 let killed=false;
 try{assertRunFixReleaseLast(code);}catch(e){
  assert.equal(e.name,'AssertionError');killed=true;
 }
 assert.equal(killed,true);
 console.info('MUTANT_KILLED: RUNFIX_RELEASE_EARLY');
});
test('refresh errors end in ERROR/HOLD, never busy, and cannot escape',()=>{
 assert.match(refresh,/try\s*{/);
 assert.match(refresh,/catch\(error\)/);
 assert.match(refresh,/state\.epoch\+\+;state\.busy=false;state\.batchRunning=false/);
 assert.match(refresh,/holdShortHubRelease\(detail\)/);
 assert.match(refresh,/state\.activeJob=null;state\.shortBulk=null/);
 assert.match(refresh,/WORKSPACE_REFRESH_ERROR/);
 assert.match(refresh,/corrected downloads HELD/);
});
test('KILL refresh error catch mutation',()=>{
 const mutant=refresh.replace('if(state.hubEnabled)holdShortHubRelease(detail);','');
 let killed=false;
 try{assert.match(mutant,/holdShortHubRelease\(detail\)/);}
 catch(e){assert.equal(e.name,'AssertionError');killed=true;}
 assert.equal(killed,true);
 console.info('MUTANT_KILLED: REFRESH_HUB_HOLD_REMOVED');
});
test('Cancel while runFix is publishing is disabled and cannot clear a validated revision',()=>{
 assert.match(fix,/state\.hubRevision=null;state\.fixFinalizing=true/);
 assert.match(fix,/state\.fixFinalizing=false/);
 assert.match(workspace,/state\.shortBulkFinalizing\|\|state\.fixFinalizing/);
 assert.match(workspace,/data-cancel'\)\&\&state\.fixFinalizing/);
});
test('stale pre-Apply preview instruction is gone; after-Apply audit remains',()=>{
 assert.doesNotMatch(docs,/Preview selected UXML edit operations/);
 assert.match(docs,/Direct Apply — current workflow/);
 assert.match(docs,/removedWithRecord/);
 assert.match(docs,/batch report/);
});
