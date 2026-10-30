import test from 'node:test';
import assert from 'node:assert/strict';
import {buildAudit,renderAuditHTML,renderAuditSummary,filterCounts} from '../tabs/topology-workspace/audit-view.mjs';

const findings=[
 {finding_id:'FND-1',code:'COINCIDENT_NODE_ALIAS_CANDIDATE',
 severity:'WARNING',blocking:false,message:'Verified candidate',node_keys:['B0:N1750:S0'],node_numbers:[1750]},
 {finding_id:'FND-2',code:'COINCIDENT_NODE_IDENTITY_AMBIGUOUS',
 severity:'ERROR',blocking:true,message:'No proven owner',node_keys:['B0:N1900:S1'],node_numbers:[1900]},
 {finding_id:'FND-3',code:'AUTO_PIPE_INLINE_COMPONENT_CARRIER',
 severity:'WARNING',blocking:false,message:'Evidence-only carrier',node_keys:['B0:N1920:S2'],node_numbers:[1920]},
 {finding_id:'FND-4',code:'SHORT_INLINE_COMPONENT_SPAN',
 severity:'INFO',blocking:false,message:'Retain short gasket',node_keys:['B0:N1950:S3'],node_numbers:[1950]},
];
const actions=[
 {action_id:'ACT-1',finding_ids:['FND-1'],disposition:'ALIAS_COINCIDENT_NODE',status:'PROPOSED',confidence:1,proposed_changes:[{operation:'ALIAS_NODE'}],blockers:[]},
 {action_id:'ACT-2',finding_ids:['FND-2'],disposition:'BLOCK_AMBIGUOUS',status:'BLOCKED',confidence:0,blockers:['NO_CONNECTION_AUTHORITY']},
 {action_id:'ACT-3',finding_ids:['FND-3'],disposition:'MERGE_CARRIER_WITH_COMPONENT',status:'PROPOSED',confidence:.95,blockers:[]},
 {action_id:'ACT-4',finding_ids:['FND-4'],disposition:'KEEP',status:'PROPOSED',confidence:1,blockers:[]}
];
test('Preservation review shows source-specific manual instructions without Auto fix',()=>{
 const message='Preserve PIPE B0:N10:S0 with ComponentRefNo UNIQUE-KEEP-REF <script>; verify owner B0:N20:S1, re-export and rerun TopoFix.';
 const action={...actions[0],disposition:'REVIEW_SOURCE_RECORD',confidence:0,proposed_changes:[],message};
 const audit=buildAudit([findings[0]],[action]);
 assert.equal(audit.counts.manual,1);
 const {html}=renderAuditHTML(audit);
 assert.match(html,/UNIQUE-KEEP-REF/);
 assert.match(html,/B0:N20:S1/);
 assert.match(html,/re-export and rerun/);
 assert.match(html,/&lt;script&gt;/);
 assert.doesNotMatch(html,/<script>/);
 assert.doesNotMatch(html,/data-auto-fix=/);
});
test('findings inherit exact PSI116 severity and grouped rule, rather than inferred action severity',()=>{
 const m=buildAudit(findings,actions);
 assert.equal(m.groups.length,4);
 assert.deepEqual([m.counts.ERROR,m.counts.WARNING,m.counts.INFO],[1,2,1]);
 assert.equal(m.groups[0].code,'COINCIDENT_NODE_IDENTITY_AMBIGUOUS');
 assert.match(renderAuditSummary(m),/4 engineering rules/);
});
test('Auto fix is not offered for blocked, low-confidence, missing changes, or evidence-only actions',()=>{
 const m=buildAudit(findings,actions);
 assert.deepEqual([m.counts.auto,m.counts.manual,m.counts.evidence,m.counts.keep],[1,1,1,1]);
 const {html}=renderAuditHTML(m);
 assert.match(html,/data-auto-fix="ACT-1"/);
 assert.doesNotMatch(html,/data-auto-fix="ACT-2"/);
 assert.doesNotMatch(html,/data-auto-fix="ACT-3"/);
 assert.doesNotMatch(html,/data-auto-fix="ACT-4"/);
 const weak=buildAudit(findings,[{...actions[0],confidence:.8},...actions.slice(1)]);
 assert.equal(weak.counts.auto,0);
 const missing=buildAudit(findings,[{...actions[0],proposed_changes:[]},...actions.slice(1)]);
 assert.equal(missing.counts.auto,0);
});
test('filters and search cover actual finding and occurrence keys',()=>{
 const m=buildAudit(findings,actions);
 assert.equal(renderAuditHTML(m,{filter:'error'}).shown,1);
 assert.equal(renderAuditHTML(m,{filter:'warning'}).shown,2);
 assert.equal(renderAuditHTML(m,{filter:'manual'}).shown,1);
 assert.equal(renderAuditHTML(m,{filter:'auto'}).shown,1);
 assert.equal(renderAuditHTML(m,{search:'B0:N1750:S0'}).shown,1);
});
test('engine messages and rule references are HTML escaped',()=>{
 const m=buildAudit([{finding_id:'X',code:'X_UNKNOWN',severity:'WARNING',
 blocking:true,message:'<img src=x onerror=alert(1)>',node_keys:['<unsafe>']}],[]);
 const h=renderAuditHTML(m).html;
 assert.match(h,/&lt;img/);
 assert.doesNotMatch(h,/<img/);
 assert.match(h,/&lt;unsafe&gt;/);
});
test('one proposed action may witness multiple distinct rule findings',()=>{
 const more=[...findings,{...findings[0],finding_id:'FND-5',code:'ZERO_LENGTH_ROUTE_SPAN',message:'Same linked action'}];
 const modified=[{...actions[0],finding_ids:['FND-1','FND-5']},...actions.slice(1)];
 const m=buildAudit(more,modified);
 assert.equal(m.items.length,5);
 assert.equal(m.counts.auto,2);
 assert.equal((renderAuditHTML(m).html.match(/data-auto-fix="ACT-1"/g)||[]).length,2);
});

test('subject categories never masquerade as severity or gap verification',()=>{
 const m=buildAudit(findings,actions);
 assert.deepEqual(m.counts.categories,{gaps:0,connection:2,overlap:1,component:1,non_topology:0,unclassified:0});
 assert.equal(renderAuditHTML(m,{category:'connection'}).shown,2);
 assert.equal(renderAuditHTML(m,{category:'overlap'}).shown,1);
 assert.equal(renderAuditHTML(m,{category:'non_topology'}).shown,0);
 assert.match(renderAuditSummary(m),/inclusive ≤25 mm repair policy/);
 assert.match(renderAuditHTML(m).html,/Connection topology &amp; node identity/);
 assert.match(renderAuditHTML(m).html,/Overlaps &amp; duplicate geometry/);
 assert.match(renderAuditHTML(m).html,/Component topology &amp; ports/);
});
test('non-topology rigid rule cannot be classified as a pipe connectivity failure',()=>{
 const f={finding_id:'RIGID-1',code:'NON_RIGID_COMPONENT_CLASSIFIED_RIGID',severity:'ERROR',
  blocking:false,message:'Rigid=2 incompatible with component',node_keys:['B0:N7:S5'],node_numbers:[7]};
 const m=buildAudit([f],[]);
 assert.equal(m.counts.categories.non_topology,1);
 assert.equal(m.counts.categories.connection,0);
 assert.equal(m.counts.ERROR,1);
 assert.equal(renderAuditHTML(m,{category:'non_topology'}).shown,1);
});
test('unknown PSI116 rule is unclassified rather than guessed into topology or overlap',()=>{
 const m=buildAudit([{finding_id:'F-NEW',code:'NEW_UNRECOGNIZED_RULE',severity:'WARNING',
  blocking:false,message:'No category authority',node_keys:['B0:N9:S0']}],[]);
 assert.equal(m.counts.categories.unclassified,1);
 assert.equal(renderAuditHTML(m,{category:'unclassified'}).shown,1);
});

test('possible pipe gaps and branch ends are never shown as Auto fix',()=>{
 const gaps=[
  {finding_id:'GAP-1',code:'NEAR_MISS_PIPE_JOINT',severity:'WARNING',blocking:false,
   message:'2 mm near miss',node_keys:['B0:N20:S1','B0:N30:S2']},
  {finding_id:'END-1',code:'BRANCH_END_UNVERIFIED',severity:'INFO',blocking:false,
   message:'Unknown termination',node_keys:['B0:N10:S0']}
 ];
 const fixes=[
  {action_id:'ACT-G1',finding_ids:['GAP-1'],disposition:'REVIEW_CONNECTION',status:'PROPOSED',
   confidence:0,proposed_changes:[],blockers:[]},
  {action_id:'ACT-G2',finding_ids:['END-1'],disposition:'REVIEW_CONNECTION',status:'PROPOSED',
   confidence:0,proposed_changes:[],blockers:[]}
 ];
 const a=buildAudit(gaps,fixes);
 assert.equal(a.counts.categories.gaps,2);
 assert.equal(a.counts.manual,2);
 assert.equal(renderAuditHTML(a,{category:'gaps'}).shown,2);
 assert.match(renderAuditHTML(a).html,/Potential gaps &amp; open ends/);
 assert.match(renderAuditHTML(a).html,/Manual fix steps/);
 assert.doesNotMatch(renderAuditHTML(a).html,/data-auto-fix=/);
 assert.equal(renderAuditHTML(a,{category:'overlap'}).shown,0);
});

test('manual evidence notes distinguish intended termination from repair needed only after review',()=>{
 const finding={finding_id:'END-Q',code:'BRANCH_END_UNVERIFIED',severity:'INFO',blocking:false,
   message:'Unknown whether open end intended',node_keys:['B3:N1600:S2']};
 const action={action_id:'ACT-Q',finding_ids:['END-Q'],disposition:'REVIEW_CONNECTION',
   status:'PROPOSED',confidence:0,proposed_changes:[],blockers:[]};
 const audit=buildAudit([finding],[action]);
 const plain=renderAuditHTML(audit,{category:'gaps'}).html;
 assert.match(plain,/data-gap-review-choice/);
 assert.match(plain,/Evidence required/);
 assert.doesNotMatch(plain,/Reviewer-marked:/);
 const reviewed=renderAuditHTML(audit,{category:'gaps',reviews:{
   'END-Q':{disposition:'intentional',note:'P&ID-100 line ends at approved cap'}
 }}).html;
 assert.match(reviewed,/Reviewer-marked: Intentional termination/);
 assert.match(reviewed,/P&amp;ID-100/);
 assert.doesNotMatch(reviewed,/data-auto-fix/);
 const unresolved=renderAuditHTML(audit,{reviews:{
   'END-Q':{disposition:'repair',note:'Drawing D-200 identifies missing tie-in'}
 }}).html;
 assert.match(unresolved,/Connection correction needed/);
});

test('counts reflect search/category and do not change when severity tab is selected',()=>{
 const m=buildAudit(findings,actions);
 assert.deepEqual(filterCounts(m),{all:4,error:1,warning:2,auto:1,manual:1,evidence:1});
 assert.deepEqual(filterCounts(m,{category:'connection'}),{
   all:2,error:1,warning:1,auto:1,manual:1,evidence:0});
 assert.equal(filterCounts(m,{search:'B0:N1750:S0'}).all,1);
 assert.equal(filterCounts(m,{category:'gaps'}).all,0);
});
test('ERROR findings explain severity, why flagged, engineering impact and source occurrence data',()=>{
 const a=buildAudit(findings,actions);
 const sourceByKey=new Map([['B0:N1900:S1',{
   type:'PIPE',nodeNumber:1900,position:{x:100,y:200,z:300}}]]);
 const h=renderAuditHTML(a,{filter:'error',sourceByKey}).html;
 assert.match(h,/Why it matters/);
 assert.match(h,/What was detected/);
 assert.match(h,/Rule trigger/);
 assert.match(h,/Block(ed)? from automatic correction/);
 assert.match(h,/Source evidence/);
 assert.match(h,/100, 200, 300/);
 const empty=renderAuditHTML(a,{filter:'error',category:'non_topology'}).html;
 assert.match(empty,/No ERROR findings/);
 assert.match(empty,/not proof of complete network connectivity/);
});
test('manual two-port joint includes exactly 25 mm with retained endpoint choice',()=>{
 const f={finding_id:'GAP',code:'NEAR_MISS_PIPE_JOINT',severity:'WARNING',node_keys:['A','B']};
 const records=new Map([['A',{key:'A',type:'PIPE',endpoint:'2',position:{x:0,y:0,z:0},refNo:'PIPE-A'}],
  ['B',{key:'B',type:'PIPE',endpoint:'1',position:{x:24.9,y:0,z:0},refNo:'PIPE-B'}]]);
 const h=renderAuditHTML(buildAudit([f],[]),{sourceByKey:records}).html;
 assert.match(h,/data-close-joint="GAP"/);assert.match(h,/Close joint &amp; recheck/);
 assert.match(h,/data-joint-target/);assert.match(h,/data-joint-confirm/);
 records.get('B').position.x=25;
 assert.match(renderAuditHTML(buildAudit([f],[]),{sourceByKey:records}).html,/data-close-joint=/);
 records.get('B').position.x=25.001;
 assert.doesNotMatch(renderAuditHTML(buildAudit([f],[]),{sourceByKey:records}).html,/data-close-joint=/);
 records.get('B').position.x=2;records.get('B').restraint=true;
 assert.doesNotMatch(renderAuditHTML(buildAudit([f],[]),{sourceByKey:records}).html,/data-close-joint=/);
});
