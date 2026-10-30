import test from 'node:test';
import assert from 'node:assert/strict';
import {enqueueManualFix,queueConflict,runManualFixQueue} from '../tabs/topology-workspace/manual-fix-queue.mjs';

function preview(n,sha='h0') {
 const key='B'+n+':N1:S1',partner='B'+n+':N2:S2';
 return {sourceSha256:sha,findingId:'F'+n,portKeys:[key,partner],
   repair:{movePortKey:key,targetPortKey:partner,moveKeys:[key],
     distanceMm:30,delta:[30,0,0],aliases:{}},
   changes:[{sourceKey:key,
     before:{Position:[0,0,0],NodeNumber:1},
     after:{Position:[30,0,0],NodeNumber:2}}]};
}
function proposal(n){
 const p=preview(n);
 return {sourceSha256:'h0',findingId:p.findingId,
   sourceKey:p.portKeys[0],peerKey:p.portKeys[1],preview:p,
   confirmed:true,evidence:'Reviewed on drawing ABC-123'};
}
function driver(n,options={}){
 let entries=[];for(let i=0;i<n;i++)entries=enqueueManualFix(entries,proposal(i),'h0');
 let count=0,mutationCount=0,active=true,checkpoints=0;
 const hash=async value=>value.startsWith('xml-h')?value.slice(4):'lineage-sha';
 const engine=async job=>{
   const sha=job.sourceText.slice(4),number=Number(sha.slice(1));
   const key=job.options.topologyConnectionPreview?.findingId||
     job.options.topologyJointRepairs?.[0]?.findingId;
   const n=Number(key.slice(1));
   const p=preview(n,sha);
   if(job.options.generateTopoFix!==true){
     count++;
     if(options.staleAt===n)p.repair.delta=[99,0,0];
     return {ok:true,outputKind:'topology-sidecars',topoFixCommitted:false,
       acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,ciiText:null,
       topologyFindingsText:JSON.stringify({source:{sha256:sha},manualConnectionPreview:p})};
   }
   mutationCount++;
   const next='h'+(number+1),id='JOIN:'+p.findingId+':'+p.repair.movePortKey;
   assert.equal(job.options.topologyJointRepairs[0].evidence,'Reviewed on drawing ABC-123');
   return {ok:true,outputKind:'topology-sidecars',topoFixCommitted:true,
     topoFixXmlText:'xml-'+next,acceptedFinalTransferred:false,
     nativeCiiReleaseAuthorized:false,ciiText:null,
     topoFixTransactionText:JSON.stringify({
       schema:'psi116-topofix-transaction/v1',source:{sha256:sha},
       fixedXmlSha256:next,committed:true,sourceXmlMutated:false,
       selectedActions:[id],operations:[{operation:'CLOSE_COMPONENT_PORT'}]}),
     topoFixValidationText:JSON.stringify({
       schema:'psi116-topofix-validation/v1',sourceSha256:sha,fixedXmlSha256:next,
       committed:true,summary:{blockingFailureCount:0},
       checks:[{code:'PHYSICAL_PORTS_CLOSED',blocking:true,passed:true}]}),
     topoFixLineageText:JSON.stringify({
       sourceXmlSha256:sha,fixedXmlSha256:next,state:'PRE_FINAL_ONLY',
       sourceXmlMutated:false,sourceOccurrenceMap:[{sourceKey:'r'+n}]}),
     topoFixPreFinalHandoffText:JSON.stringify({
       originalSourceXmlSha256:sha,newSourceXmlSha256:next,
       requiresFreshWorkerBasis:true,nativeCiiReleaseAuthorized:false}),
     topoFixPostFindingsText:JSON.stringify({
       source:{sha256:next},findings:[],resolvedConnections:[],
       shortElements:[],manualConnectionPorts:[]}),
     topoFixPostPlanText:JSON.stringify({source:{sha256:next},actions:[]})};
 };
 return {entries,hash,engine,source:{name:'test.xml',sourceText:'xml-h0',sourceSha256:'h0'},
   setActive(v){active=v;},isCurrent:()=>active,
   onCheckpoint:()=>{checkpoints++;if(checkpoints===options.cancelAt)active=false;},
   get checks(){return count;},get mutations(){return mutationCount;},
   get checkpoints(){return checkpoints;}};
}
test('queue requires source evidence, explicit approval and exact preview',()=>{
 assert.throws(()=>enqueueManualFix([], {...proposal(0),confirmed:false},'h0'),/APPROVAL_REQUIRED/);
 assert.throws(()=>enqueueManualFix([], {...proposal(0),sourceSha256:'wrong'},'h0'),/SOURCE_OR_PORT_DRIFT/);
 const q=enqueueManualFix([],proposal(0),'h0');
 assert.equal(q.length,1);assert.equal(q[0].status,'APPROVED');
 assert.throws(()=>enqueueManualFix(q,proposal(0),'h0'),/DUPLICATE/);
});
test('same finding or overlapping movement cannot enter queue',()=>{
 let q=enqueueManualFix([],proposal(0),'h0');
 const other=proposal(1);other.preview.repair.moveKeys.push(q[0].sourceKey);
 assert.throws(()=>enqueueManualFix(q,other,'h0'),/CONFLICT/);
 assert.equal(queueConflict(q[0],q[0]),'SAME_FINDING');
});
test('two approved disjoint manual connections requalify on current SHA and publish verified receipts',async()=>{
 const d=driver(2);
 const result=await runManualFixQueue({...d,runEngine:d.engine,onCheckpoint:d.onCheckpoint});
 assert.equal(result.stopReason,'COMPLETE');
 assert.equal(result.applied.length,2);
 assert.equal(result.latest.source.sourceSha256,'h2');
 assert.equal(d.mutations,2);assert.equal(d.checks,2);
 assert.equal(result.pending.length,0);
});
test('a changed preview stops before the second source mutation',async()=>{
 const d=driver(3,{staleAt:1});
 const result=await runManualFixQueue({...d,runEngine:d.engine,onCheckpoint:d.onCheckpoint});
 assert.equal(result.stopReason,'BLOCKED');
 assert.match(result.message,/STALE_MOVEMENT/);
 assert.equal(result.applied.length,1);assert.equal(result.blocked.length,1);
 assert.equal(result.pending.length,1);
 assert.equal(d.mutations,1);
});
test('cancellation stops before any further mutations and retains verified checkpoint',async()=>{
 const d=driver(3,{cancelAt:1});
 const result=await runManualFixQueue({...d,runEngine:d.engine,onCheckpoint:d.onCheckpoint});
 assert.equal(result.stopReason,'CANCELLED');assert.equal(result.applied.length,1);
 assert.equal(result.latest.source.sourceSha256,'h1');assert.equal(d.mutations,1);
});
