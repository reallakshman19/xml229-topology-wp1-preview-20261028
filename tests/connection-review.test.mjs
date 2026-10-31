import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveConnectionReview,reviewConnectionHTML} from '../tabs/topology-workspace/connection-review.mjs';
import {createTopologyCanvas} from '../tabs/topology-workspace/projected-canvas.mjs';

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
  assert.ok(Math.abs(r.vector.x-240.6)<1e-9);
  assert.equal(r.vector.y,0);
  assert.equal(r.vector.z,0);
  const html=reviewConnectionHTML(r);
  for(const token of ['REVIEW ONLY','CONFLICTS_WITH_CLOS','240.600','B0:N6880:S1',
    '114.300','6.020','upstream CAD','reimport','PROPOSAL'])
    assert.ok(html.includes(token),token);
  assert.doesNotMatch(html,/data-(?:apply|queue)|<button|CLOSE_PORT_CONNECTION/i);
});


test('off-port CLOS declaration binds the selected port solely through source witness',()=>{
  const openLooking=occurrence(0,1,6880,1100,'RIGID','V');
  const offPortCLOS=occurrence(0,2,-1,1100.49,'ATTA','SUP','CLOS');
  const boundOnly=[{sourceKey:openLooking.key,rowKind:'PORT',bindingStatus:'BOUND',
    sourceSha256:sha,closureDeclarations:[{
      sourceKey:offPortCLOS.key,bindingKinds:['BRANCH_BOUNDARY_END']}]}];
  const explicitOpenPorts=[{key:openLooking.key,closed:false},{key:b.key,closed:false}];
  const r=resolveConnectionReview(scene([openLooking,offPortCLOS,b]),
    explicitOpenPorts,boundOnly,true,'6880','6450');
  assert.equal(openLooking.connectionType,'');
  assert.equal(r.first.rawClos,false);
  assert.equal(explicitOpenPorts[0].closed,false);
  assert.equal(r.first.bindingStatus,'BOUND');
  assert.deepEqual(r.first.declarationKeys,[offPortCLOS.key]);
  assert.equal(r.first.blocked,true);
  assert.equal(r.disposition,'CONFLICTS_WITH_CLOS');
  assert.match(reviewConnectionHTML(r),/B0:N-1:S2/);
});

test('selected source wall thickness comes from this occurrence, not a constant',()=>{
  const differentWall={...b,wallThickness:8.75};
  const r=resolveConnectionReview(scene([a,differentWall]),ports,witness,true,6880,6450);
  assert.equal(r.second.wallThickness,8.75);
  const html=reviewConnectionHTML(r);
  assert.match(html,/wall 8\.750 mm/);
  assert.match(html,/wall 6\.020 mm/);
});

test('setReviewPair draws a dashed, labeled review-only line and clearing removes it',()=>{
  const calls=[];
  const ctx={
    setTransform(){},fillRect(){},save(){},restore(){},beginPath(){},fill(){},arc(){},
    setLineDash(value){calls.push(['dash',...value]);},
    moveTo(...args){calls.push(['move',...args]);},
    lineTo(...args){calls.push(['line',...args]);},
    stroke(){calls.push(['stroke']);},
    fillText(value){calls.push(['text',value]);}
  };
  const canvas={width:0,height:0,style:{},
    getContext:()=>ctx,
    getBoundingClientRect:()=>({width:640,height:480}),
    addEventListener(){},removeEventListener(){}
  };
  const pair=[{...a,route:true,nodeNumberRaw:'6880'},
    {...b,route:true,nodeNumberRaw:'6450'}];
  const picture={sourceSha256:sha,records:pair,segments:[],
    byId:new Map(pair.map(r=>[r.id,r])),
    bounds:{center:{x:1220,y:0,z:0},span:240.6}};
  const model=createTopologyCanvas(canvas);
  try{
    model.setScene(picture);
    calls.length=0;
    model.setReviewPair(pair.map(r=>r.id));
    const dash=calls.findIndex(c=>c[0]==='dash'&&c[1]===9&&c[2]===7);
    assert.ok(dash>=0,'missing dashed proposal stroke');
    const dashEnd=calls.findIndex((c,i)=>i>dash&&c[0]==='dash'&&c.length===1);
    assert.ok(dashEnd>dash,'proposal dash not reset');
    const overlay=calls.slice(dash,dashEnd);
    assert.ok(overlay.some(c=>c[0]==='move'),'missing overlay start');
    assert.ok(overlay.some(c=>c[0]==='line'),'missing overlay segment');
    assert.ok(overlay.some(c=>c[0]==='stroke'),'missing overlay stroke');
    assert.ok(calls.some(c=>c[0]==='text'&&c[1]==='PROPOSAL · REVIEW ONLY'),
      'missing explicit non-executable label');
    assert.equal(picture.segments.length,0,'overlay must never become a solver edge');
    calls.length=0;
    model.setReviewPair([]);
    assert.ok(!calls.some(c=>c[0]==='dash'&&c[1]===9&&c[2]===7));
    assert.ok(!calls.some(c=>c[0]==='text'&&c[1]==='PROPOSAL · REVIEW ONLY'));
  }finally{model.dispose();}
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
