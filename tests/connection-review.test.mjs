import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveConnectionReview,reviewConnectionHTML} from '../tabs/topology-workspace/connection-review.mjs';

const sha='a'.repeat(64);
const occurrence=(branch,index,nodeNumber,x,type='PIPE',ref='P',connectionType='')=>({
  id:sha+':B'+branch+':N'+nodeNumber+':S'+index,
  key:'B'+branch+':N'+nodeNumber+':S'+index,
  branchIndex:branch,sourceIndex:index,branchName:'branch '+branch,
  nodeNumber,type,refNo:ref,endpoint:index?'2':'1',
  connectionType,position:{x,y:0,z:0},outsideDiameter:114.3,wallThickness:6.02
});
const a=occurrence(0,1,6880,1100,'RIGID','V','CLOS');
const b=occurrence(1,0,6450,1340.6,'FBLI','BL');
const witness=[{sourceKey:a.key,rowKind:'PORT',bindingStatus:'BOUND',
  sourceSha256:sha,closureDeclarations:[{
    sourceKey:a.key,bindingKinds:['EXACT_SOURCE_RECORD']}]}];
const ports=[{key:a.key,closed:true},{key:b.key,closed:false}];
const scene=records=>({sourceSha256:sha,records});

test('6880 / 6450 stays REVIEW ONLY with verified CLOS provenance and exact 240.6 mm',()=>{
  const r=resolveConnectionReview(scene([a,b]),ports,witness,true,'6880','6450');
  assert.equal(r.disposition,'CONFLICTS_WITH_CLOS');
  assert.equal(r.status,'REVIEW ONLY');
  assert.equal(r.distanceMm.toFixed(3),'240.600');
  assert.deepEqual(r.vector,{x:240.5999999999999,y:0,z:0});
  const html=reviewConnectionHTML(r);
  for(const token of ['REVIEW ONLY','CONFLICTS_WITH_CLOS','240.600','B0:N6880:S1',
    '114.300','6.020','upstream CAD','reimport','PROPOSAL'])
    assert.ok(html.includes(token),token);
  assert.doesNotMatch(html,/data-(?:apply|queue)|<button|CLOSE_PORT_CONNECTION/i);
});

test('duplicates require exact source-key selection, never nearest point',()=>{
  const alternate=occurrence(2,0,6880,1340.59,'PIPE','OTHER');
  const s=scene([a,alternate,b]);
  const unresolved=resolveConnectionReview(s,ports,witness,true,6880,6450);
  assert.equal(unresolved.occurrencesA.length,2);
  assert.equal(unresolved.a,null);
  assert.equal(unresolved.distanceMm,null);
  assert.equal(unresolved.disposition,'AMBIGUOUS_PORT');
  const chosen=resolveConnectionReview(s,ports,witness,true,6880,6450,a.key);
  assert.equal(chosen.a.key,a.key);
  assert.equal(chosen.disposition,'CONFLICTS_WITH_CLOS');
  const wrong=resolveConnectionReview(s,ports,witness,true,6880,6450,'B99:N6880:S1');
  assert.equal(wrong.disposition,'AMBIGUOUS_PORT');
});

test('missing numbers, malformed input, same record and helpers remain explicitly review only',()=>{
  const helper=occurrence(1,1,-900,1400,'BRAN','OTHER','');
  const s=scene([a,b,helper]);
  assert.equal(resolveConnectionReview(s,ports,witness,true,6880,999).disposition,'MISSING_OCCURRENCE');
  assert.equal(resolveConnectionReview(s,ports,witness,true,'688','6450').disposition,'MISSING_OCCURRENCE');
  assert.equal(resolveConnectionReview(s,ports,witness,true,'6880x','6450').disposition,'INVALID_NODE_NUMBER');
  assert.equal(resolveConnectionReview(s,ports,witness,true,6880,6880).disposition,'SAME_SOURCE_OCCURRENCE');
  assert.equal(resolveConnectionReview(s,ports,witness,true,-900,6450).disposition,'HELPER_ONLY_ENDPOINT');
  assert.equal(resolveConnectionReview(s,ports,witness,true,6880,'').disposition,'MISSING_INPUT');
});

test('stale witness source SHA cannot promote closure proof or executable status',()=>{
  const stale=[{...witness[0],sourceSha256:'b'.repeat(64)}];
  const r=resolveConnectionReview(scene([a,b]),ports,stale,true,6880,6450);
  assert.equal(r.evidence,false);
  assert.equal(r.disposition,'SOURCE_UNVERIFIED');
  assert.equal(r.status,'REVIEW ONLY');
});

test('missing browser sidecar fails closed instead of appearing open or fully verified',()=>{
  const r=resolveConnectionReview(scene([a,b]),ports,null,false,6880,6450);
  assert.equal(r.disposition,'SOURCE_UNVERIFIED');
  assert.match(reviewConnectionHTML(r),/evidence unavailable or stale/);
});

test('unavailable exact Position blocks a fabricated distance',()=>{
  const noPosition={...b,position:null};
  const r=resolveConnectionReview(scene([a,noPosition]),ports,witness,true,6880,6450);
  assert.equal(r.disposition,'MISSING_POSITION');
  assert.equal(r.distanceMm,null);
});

test('no declared CLOS on authoritative open ports still never gives Apply from review',()=>{
  const x=occurrence(0,0,10,0);
  const y=occurrence(1,0,20,15);
  const r=resolveConnectionReview(scene([x,y]),[{key:x.key,closed:false},{key:y.key,closed:false}],[],true,10,20);
  assert.equal(r.disposition,'SOURCE_REVIEW_REQUIRED');
  assert.equal(r.status,'REVIEW ONLY');
  assert.doesNotMatch(reviewConnectionHTML(r),/<button|data-(?:apply|queue)/i);
});
