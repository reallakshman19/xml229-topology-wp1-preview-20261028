import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {SOURCE_REVIEW_SCHEMA,SOURCE_REVIEW_KIND,SOURCE_REVIEW_DECISIONS,
  canAddSourceReview,sourceReviewPairId,sourceReviewStatus,upsertSourceReview,
  editSourceReview,exportSourceReviewJSON,importSourceReviewJSON,
  exportSourceReviewCSV} from '../tabs/topology-workspace/source-review-queue.mjs';
import {resolveConnectionReview} from '../tabs/topology-workspace/connection-review.mjs';

const sha='a'.repeat(64),otherSha='b'.repeat(64);
const t0='2026-10-31T10:00:00.000Z',t1='2026-10-31T10:01:00.000Z',t2='2026-10-31T10:02:00.000Z';
const a={key:'B0:N6880:S1',branchName:'REVIEW-CLOSED',branchIndex:0,
  nodeNumber:6880,endpoint:'2',type:'RIGID',refNo:'V',position:{x:1100,y:0,z:0},connectionType:'CLOS'};
const b={key:'B1:N6450:S0',branchName:'REVIEW-OPEN',branchIndex:1,
  nodeNumber:6450,endpoint:'1',type:'FBLI',refNo:'BL',position:{x:1340.6,y:0,z:0}};
const witness=[{sourceKey:a.key,sourceSha256:sha,rowKind:'PORT',bindingStatus:'BOUND',
  closureDeclarations:[{sourceKey:a.key,bindingKinds:['EXACT_SOURCE_RECORD']}]}];
const scene={sourceSha256:sha,records:[a,b]};
const ports=[{key:a.key,closed:true},{key:b.key,closed:false}];
const result=()=>resolveConnectionReview(scene,ports,witness,true,6880,6450);
const reversed=()=>resolveConnectionReview(scene,ports,witness,true,6450,6880);
const make=()=>upsertSourceReview([],result(),{at:t0});

test('P2 add preserves source key, branch, node, endpoint, owner, source SHA, CLOS and 240.6 mm',()=>{
  const {rows,row,inserted}=make();
  assert.equal(inserted,true);assert.equal(rows.length,1);
  assert.equal(row.kind,SOURCE_REVIEW_KIND);
  assert.equal(row.sourceSha256,sha);
  assert.equal(row.disposition,'CONFLICTS_WITH_CLOS');
  assert.equal(row.distanceMm.toFixed(3),'240.600');
  assert.equal(row.decision,'DRAWING_CHECK_PENDING');
  assert.deepEqual(row.ports.map(p=>p.sourceKey),[a.key,b.key]);
  assert.deepEqual(row.ports.map(p=>[p.branch,p.branchIndex,p.nodeNumber,p.endpoint,p.owner]),
    [['REVIEW-CLOSED',0,6880,'2',{componentType:'RIGID',refNo:'V'}],
     ['REVIEW-OPEN',1,6450,'1',{componentType:'FBLI',refNo:'BL'}]]);
  assert.equal(row.id,sourceReviewPairId(sha,a.key,b.key));
});

test('P2 same/reversed re-add preserves engineer decision and note, updates only source observations',()=>{
  const {rows,row}=make();
  const saved=editSourceReview(rows,row.id,'UPSTREAM_SOURCE_CORRECTION_REQUIRED',
    'Drawing review required — preserve this note',t1);
  let current=saved;
  for(const [orientation,at] of [[result(),t2],[reversed(),'2026-10-31T10:03:00.000Z']]){
    const observed={...orientation,disposition:'SOURCE_UNVERIFIED',distanceMm:240.601};
    const second=upsertSourceReview(current,observed,{at,
      decision:'DRAWING_CHECK_PENDING',note:'must not override saved decision'});
    assert.equal(second.inserted,false);
    assert.equal(second.rows.length,1);
    assert.equal(second.row.createdAt,t0);
    assert.equal(second.row.updatedAt,at);
    assert.equal(second.row.decision,'UPSTREAM_SOURCE_CORRECTION_REQUIRED');
    assert.equal(second.row.note,'Drawing review required — preserve this note');
    assert.equal(second.row.disposition,'SOURCE_UNVERIFIED');
    assert.equal(second.row.distanceMm,240.601);
    assert.deepEqual(second.row.ports,row.ports);
    current=second.rows;
  }
});

test('P2 decision updates only audit fields, never source identity/disposition',()=>{
  const {rows,row}=make();
  for(const decision of SOURCE_REVIEW_DECISIONS){
    const next=editSourceReview(rows,row.id,decision,'Piping drawing check',t1);
    assert.equal(next.length,1);
    assert.equal(next[0].decision,decision);
    assert.deepEqual(next[0].ports,row.ports);
    assert.equal(next[0].distanceMm,row.distanceMm);
    assert.equal(next[0].sourceSha256,row.sourceSha256);
    assert.equal(next[0].disposition,row.disposition);
    assert.ok(!('approvedRepair' in next[0])&&!('operations' in next[0])&&!('mode' in next[0]));
  }
  assert.throws(()=>editSourceReview(rows,row.id,'APPROVE_APPLY','',t1),/DECISION_INVALID/);
});

test('P2 ambiguous or same-source selections cannot be added',()=>{
  const duplicate={...a,key:'B2:N6880:S0',branchIndex:2,branchName:'DUP'};
  const ambiguous=resolveConnectionReview({...scene,records:[a,duplicate,b]},ports,witness,true,6880,6450);
  assert.equal(ambiguous.disposition,'AMBIGUOUS_PORT');
  assert.equal(canAddSourceReview(ambiguous),false);
  assert.throws(()=>upsertSourceReview([],ambiguous,{at:t1}),/EXACT_PAIR_REQUIRED/);
  const same=resolveConnectionReview(scene,ports,witness,true,6880,6880);
  assert.equal(canAddSourceReview(same),false);
  assert.throws(()=>upsertSourceReview([],same,{at:t1}),/EXACT_PAIR_REQUIRED/);
});

test('P2 allows a uniquely identified unverified or helper pair for source review only',()=>{
  const uncertain={...result(),disposition:'SOURCE_UNVERIFIED',evidence:false};
  const helper={...result(),disposition:'HELPER_ONLY_ENDPOINT',distanceMm:null};
  for(const scenario of [uncertain,helper]){
    const {row}=upsertSourceReview([],scenario,{at:t0});
    assert.equal(row.kind,SOURCE_REVIEW_KIND);
    assert.equal(row.disposition,scenario.disposition);
    assert.equal(row.distanceMm,scenario.distanceMm);
  }
});

test('P2 source change marks existing and imported rows stale without rebinding',()=>{
  const {rows,row}=make();
  assert.equal(sourceReviewStatus(row,sha),'CURRENT_SOURCE');
  assert.equal(sourceReviewStatus(row,otherSha),'STALE_SOURCE');
  assert.equal(sourceReviewStatus(row,null),'STALE_SOURCE');
  const imported=importSourceReviewJSON(exportSourceReviewJSON(rows,sha,t1));
  assert.equal(imported.rows.length,1);
  assert.equal(sourceReviewStatus(imported.rows[0],otherSha),'STALE_SOURCE');
  assert.equal(imported.rows[0].sourceSha256,sha);
});

test('P2 exported JSON round-trip and same-pair import reconcile without deleting local rows',()=>{
  const {rows,row}=make();
  const changed=editSourceReview(rows,row.id,'UPSTREAM_SOURCE_CORRECTION_REQUIRED',
    'Correct in upstream CAD then reimport',t1);
  const raw=exportSourceReviewJSON(changed,sha,t2);
  const parsed=JSON.parse(raw);
  assert.equal(parsed.schema,SOURCE_REVIEW_SCHEMA);
  assert.equal(parsed.kind,SOURCE_REVIEW_KIND);
  assert.equal(parsed.rows.length,1);
  assert.deepEqual(importSourceReviewJSON(raw).rows,changed);
  const twice=importSourceReviewJSON(raw,changed);
  assert.equal(twice.added,0);assert.equal(twice.updated,1);
  assert.equal(twice.rows.length,1);
});

test('P2 CSV uses exact witness identities, stale status, and neutralizes formula notes',()=>{
  const {rows,row}=make();
  const withFormula=editSourceReview(rows,row.id,'DRAWING_CHECK_PENDING',
    '=HYPERLINK("http://unsafe")',t1);
  const csv=exportSourceReviewCSV(withFormula,otherSha);
  assert.match(csv,/STALE_SOURCE/);
  assert.match(csv,/B0:N6880:S1/);
  assert.match(csv,/B1:N6450:S0/);
  assert.match(csv,/240\.600/);
  assert.match(csv,/RIGID/);
  assert.match(csv,/FBLI/);
  assert.ok(csv.includes("'=HYPERLINK("));
  for(const leading of ['\t','\r']){
    const dangerous=editSourceReview(rows,row.id,'DRAWING_CHECK_PENDING',
      leading+'=HYPERLINK("http://unsafe")',t1);
    const escaped=exportSourceReviewCSV(dangerous,otherSha);
    assert.ok(escaped.includes('"\''+leading+'=HYPERLINK('),
      'CSV formula prefix not neutralized: '+JSON.stringify(leading));
  }
});

test('P2 forged executable/Apply fields are rejected at every import layer',()=>{
  const {rows}=make();
  const envelope=JSON.parse(exportSourceReviewJSON(rows,sha,t1));
  for(const property of ['manualQueue','mode','apply','operations','approvedRepair']){
    assert.throws(()=>importSourceReviewJSON(JSON.stringify({...envelope,[property]:{}})),
      /UNEXPECTED_FIELD/,property);
    const bad=structuredClone(envelope);
    bad.rows[0][property]={};
    assert.throws(()=>importSourceReviewJSON(JSON.stringify(bad)),/UNEXPECTED_FIELD/,property);
  }
  const badPort=structuredClone(envelope);
  badPort.rows[0].ports[0].approvedRepair={edit:'JOIN'};
  assert.throws(()=>importSourceReviewJSON(JSON.stringify(badPort)),/UNEXPECTED_FIELD/);
  assert.equal(importSourceReviewJSON(JSON.stringify(envelope)).rows[0].kind,SOURCE_REVIEW_KIND);
});

test('P2 guard: evidence UI cannot import or advertise executable paths',()=>{
  const model=readFileSync(new URL('../tabs/topology-workspace/source-review-queue.mjs',import.meta.url),'utf8');
  const ui=readFileSync(new URL('../tabs/topology-workspace/source-review-panel.mjs',import.meta.url),'utf8');
  const forbidden=/\b(?:enqueueManualFix|runManualFixQueue|applyManualQueue|applySecondPass|autoFixAll)\b|data-queue-(?:apply|second)|data-apply-second|data-close-joint|data-run-auto-fix-all/;
  assert.doesNotMatch(model,forbidden,'review model imports executable behavior');
  assert.doesNotMatch(ui,forbidden,'review panel links into executable queue or Apply');
  assert.match(ui,/data-source-review-add/);
  assert.match(ui,/stopPropagation/);
});
