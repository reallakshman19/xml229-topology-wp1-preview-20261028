import test from 'node:test';
import assert from 'node:assert/strict';
import {connectionCandidates,secondPassHTML} from '../tabs/topology-workspace/second-pass.mjs';
import {buildAudit,renderAuditHTML} from '../tabs/topology-workspace/audit-view.mjs';
const records=[
 {key:'source',position:{x:0,y:0,z:0},branchName:'A'},
 {key:'near',position:{x:25.001,y:0,z:0},branchName:'B'},
 {key:'far',position:{x:75,y:0,z:0},branchName:'C'},
 {key:'closed',position:{x:1,y:0,z:0},branchName:'D'}];
const scene={byKey:new Map(records.map(r=>[r.key,r]))};
const ports=records.map(r=>({key:r.key,ownerType:'PIPE',componentRefNo:r.key,closed:r.key==='closed'}));
test('partner discovery uses actual 3D distance beyond 25 mm without silently selecting nearest',()=>{
 const rows=connectionCandidates(scene,ports,'source');
 assert.deepEqual(rows.map(r=>[r.key,r.distanceMm]),[['near',25.001],['far',75]]);
 const draft={witnessKeys:['source'],sourceKey:'source',peerKey:'',evidence:'',search:''};
 const html=secondPassHTML(draft,scene,ports);
 assert.match(html,/Choose intended partner/);
 assert.doesNotMatch(html,/value="near" selected/);
 assert.doesNotMatch(html,/data-apply-second/);
 assert.match(html,/25.001 mm/);
 assert.equal(connectionCandidates(scene,ports,'source','C')[0].key,'far');
});
test('approved movement shows field changes and keeps Apply disabled without evidence and confirmation',()=>{
 const draft={witnessKeys:['source'],sourceKey:'source',peerKey:'far',evidence:'',search:'',
  preview:{repair:{distanceMm:75,movePortKey:'source',targetPortKey:'far',delta:[75,0,0],moveKeys:['source']},
   changes:[{sourceKey:'source',before:{Position:[0,0,0],NodeNumber:20},after:{Position:[75,0,0],NodeNumber:30}}]}};
 let html=secondPassHTML(draft,scene,ports);
 assert.match(html,/75.000 mm closure · exceeds automatic tolerance/);
 assert.match(html,/Node 20/);assert.match(html,/Node 30/);
 assert.match(html,/data-apply-second disabled/);
 html=secondPassHTML({...draft,confirmed:true,evidence:'Drawing TEST-02 confirms connection'},scene,ports);
 assert.doesNotMatch(html,/data-apply-second disabled/);
 assert.match(secondPassHTML({...draft,busy:true},scene,ports),/<fieldset disabled>/);
});
test('single-ended case offers Add second pass and manual groups/cases start collapsed by rule',()=>{
 const findings=[1,2].map(i=>({finding_id:'F-'+i,code:'BRANCH_END_UNVERIFIED',severity:'INFO',
  node_keys:['source'],node_numbers:[i],branch_name:'Branch '+i,message:'Unverified end'}));
 const audit=buildAudit(findings,[]);
 const {html,shown}=renderAuditHTML(audit,{filter:'manual'});
 assert.equal(shown,2);
 assert.equal((html.match(/class="audit-rule"/g)||[]).length,1);
 assert.equal((html.match(/class="audit-case"/g)||[]).length,2);
 assert.match(html,/Manual Fix · By Rule/);assert.match(html,/2 manual/);
 assert.doesNotMatch(html,/<details class="audit-(?:rule|case)"[^>]*\sopen/);
 assert.match(html,/data-add-second-pass="F-1"/);
 const expanded=renderAuditHTML(audit,{filter:'manual',openRules:new Set(['BRANCH_END_UNVERIFIED']),openCases:new Set(['F-2'])}).html;
 assert.match(expanded,/data-rule-code="BRANCH_END_UNVERIFIED" open/);
 assert.match(expanded,/data-case-id="F-2" open/);
});
test('unknown manual rules remain visible and cannot offer an unsupported connection repair',()=>{
 const audit=buildAudit([{finding_id:'X',code:'NEW_RULE',severity:'WARNING',message:'Needs review'}],[]);
 const html=renderAuditHTML(audit,{filter:'manual'}).html;
 assert.match(html,/new rule/);assert.doesNotMatch(html,/data-add-second-pass/);
});
test('search and evidence are escaped; a canvas-selected far partner remains visible under a narrow search',()=>{
 const html=secondPassHTML({witnessKeys:['source'],sourceKey:'source',peerKey:'far',search:'near',evidence:'<img onerror=x>'},scene,ports);
 assert.match(html,/value="far" selected/);assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img/);
});
