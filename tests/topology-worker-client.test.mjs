import test from 'node:test';
import assert from 'node:assert/strict';
import {createTopologyWorkerClient} from '../tabs/topology-workspace/topology-worker-client.mjs';

class FakeWorker {
  static instances=[];
  constructor(url,opts){this.url=url;this.opts=opts;this.handlers={};this.terminated=false;this.sent=[];FakeWorker.instances.push(this);}
  addEventListener(type,fn){(this.handlers[type] ||= []).push(fn);}
  postMessage(m){this.sent.push(m);}
  terminate(){this.terminated=true;}
  emit(type,data){for(const fn of this.handlers[type]||[])fn(type==='message'?{data}:{message:data});}
}
const validJob={sourceKind:'xml',topologyPreFinalOnly:true,options:{outputMode:'enriched-only',analyzeTopology:true,generateTopoFix:false,useTopoFixForCii:false}};

test('bounded worker protocol delivers result without executing main-thread Python',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000});
 const promise=c.run(validJob),w=FakeWorker.instances.at(-1);
 assert.equal(w.opts.type,'module');
 const request=w.sent[0];assert.equal(request.type,'RUN');
 w.emit('message',{type:'RESULT',id:request.id,result:{ok:true}});
 assert.deepEqual(await promise,{ok:true});c.dispose();
});
test('cancel terminates WASM execution and stale result cannot publish',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000});
 const promise=c.run(validJob),w=FakeWorker.instances.at(-1),request=w.sent[0];
 c.cancel();assert.equal(w.terminated,true);
 await assert.rejects(promise,/CANCELLED/);
 w.emit('message',{type:'RESULT',id:request.id,result:{ok:true}});
 const next=c.run(validJob),nextWorker=FakeWorker.instances.at(-1);
 assert.notEqual(nextWorker,w);
 nextWorker.emit('message',{type:'RESULT',id:nextWorker.sent[0].id,result:{ok:true,revision:0}});
 assert.equal((await next).revision,0);c.dispose();
});
test('crash rejects and next attempt starts fresh worker',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000});
 const p=c.run(validJob),w=FakeWorker.instances.at(-1);
 w.emit('error','boom');await assert.rejects(p,/CRASH/);
 assert.equal(w.terminated,true);
 const next=c.run(validJob),w2=FakeWorker.instances.at(-1);
 w2.emit('message',{type:'ERROR',id:w2.sent[0].id,message:'fixture invalid'});
 await assert.rejects(next,/fixture invalid/);c.dispose();
});
test('invalid native or Final request rejected before dispatch',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker});
 await assert.rejects(c.run({...validJob,topologyPreFinalOnly:false}),/PREFINAL_ONLY/);
 await assert.rejects(c.run({...validJob,options:{...validJob.options,useTopoFixForCii:true}}),/PREFINAL_ONLY/);
 c.dispose();
});

test('idle worker recycles after eight completed jobs to bound Pyodide scratch growth',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000});
 let first;
 for(let i=0;i<8;i++){
   const p=c.run(validJob),w=FakeWorker.instances.at(-1);
   first ||= w;
   assert.equal(w,first,'do not recycle before eight validated job results');
   w.emit('message',{type:'RESULT',id:w.sent.at(-1).id,result:{ok:true,pass:i}});
   assert.equal((await p).pass,i);
   if(i<7)assert.equal(w.terminated,false);
 }
 assert.equal(first.terminated,true);
 const next=c.run(validJob),w2=FakeWorker.instances.at(-1);
 assert.notEqual(w2,first);
 w2.emit('message',{type:'RESULT',id:w2.sent[0].id,result:{ok:true}});
 await next;
 c.dispose();
});


test('bulk lease keeps one warm Pyodide Worker for twelve serial independently returned jobs',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000});
 c.beginBulkSession();
 let first;
 for(let i=0;i<12;i++){
   const job={...validJob,options:{...validJob.options,topologyBulkSession:true}};
   const p=c.run(job),w=FakeWorker.instances.at(-1);
   first ||=w;
   assert.equal(w,first,'bulk lease must prevent eight-job cold-start recycle');
   w.emit('message',{type:'RESULT',id:w.sent.at(-1).id,
     result:{ok:true,revision:i+1,hubParity:'EQUAL'}});
   const returned=await p;
   assert.equal(returned.revision,i+1);
   assert.equal(returned.hubParity,'EQUAL');
   assert.equal(w.terminated,false,'warm Worker remains live during bulk');
 }
 c.endBulkSession();
 const post=c.run(validJob),w=FakeWorker.instances.at(-1);
 assert.equal(w,first,'warm Worker reused for final read-only evidence refresh');
 w.emit('message',{type:'RESULT',id:w.sent.at(-1).id,result:{ok:true,rechecked:true}});
 assert.equal((await post).rechecked,true);
 assert.equal(first.terminated,true,'ordinary idle recycle resumes after release');
 c.dispose();
});

test('bulk cancellation terminates Worker and cannot publish a stale revision',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000});
 c.beginBulkSession();
 const p=c.run({...validJob,options:{...validJob.options,topologyBulkSession:true}});
 const w=FakeWorker.instances.at(-1),id=w.sent.at(-1).id;
 c.cancel();
 assert.equal(w.terminated,true);
 await assert.rejects(p,/CANCELLED/);
 w.emit('message',{type:'RESULT',id,result:{ok:true,revision:'FORGED_STALE'}});
 c.endBulkSession();
 const post=c.run(validJob),fresh=FakeWorker.instances.at(-1);
 assert.notEqual(fresh,w);
 fresh.emit('message',{type:'RESULT',id:fresh.sent.at(-1).id,result:{ok:true,revision:0}});
 assert.equal((await post).revision,0);
 c.dispose();
});

test('one preview job streams only validated progress, keeps job pending and can cancel/restart',async()=>{
  const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000});
  const job={...validJob,options:{...validJob.options,
    topologyShortPreviewRequests:Array.from({length:9},(_,i)=>({id:'SHORT:'+i}))}};
  const observed=[];
  const p=c.run(job,{onProgress:(done,total)=>observed.push([done,total])});
  const worker=FakeWorker.instances.at(-1),id=worker.sent.at(-1).id;
  worker.emit('message',{type:'PROGRESS',id,completed:4,total:9});
  worker.emit('message',{type:'PROGRESS',id,completed:4,total:9});
  worker.emit('message',{type:'PROGRESS',id,completed:10,total:9});
  worker.emit('message',{type:'PROGRESS',id,completed:8,total:8});
  worker.emit('message',{type:'PROGRESS',id,completed:8,total:9});
  assert.deepEqual(observed,[[4,9],[8,9]],
    'no duplicate, overshoot or wrong-selection progress is forwarded');
  assert.equal(worker.terminated,false);
  c.cancel();
  await assert.rejects(p,/CANCELLED/);
  assert.equal(worker.terminated,true);
  worker.emit('message',{type:'RESULT',id,result:{ok:true,forged:true}});
  const recovered=c.run(job,{onProgress:(done,total)=>observed.push([done,total])});
  const fresh=FakeWorker.instances.at(-1);
  assert.notEqual(fresh,worker);
  fresh.emit('message',{type:'PROGRESS',id:fresh.sent.at(-1).id,completed:9,total:9});
  fresh.emit('message',{type:'RESULT',id:fresh.sent.at(-1).id,result:{ok:true,refreshed:true}});
  assert.deepEqual(await recovered,{ok:true,refreshed:true});
  assert.deepEqual(observed,[[4,9],[8,9],[9,9]]);
  c.dispose();
});

test('preview uses longer first-progress allowance, then an inactivity watchdog',async()=>{
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const job={...validJob,options:{...validJob.options,
    topologyShortPreviewRequests:[{id:'SYN-1'},{id:'SYN-2'}]}};
  const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,
    jobTimeoutMs:15,previewFirstProgressTimeoutMs:250,
    previewInactivityTimeoutMs:120});
  const observed=[];
  const pending=c.run(job,{onProgress:(completed,total)=>observed.push([completed,total])});
  const w=FakeWorker.instances.at(-1),id=w.sent.at(-1).id;
  // An ordinary 15ms watchdog would have terminated this job by now.
  await delay(50);
  assert.equal(w.terminated,false,'first preview group gets 250ms, not 15ms');
  w.emit('message',{type:'PROGRESS',id,completed:1,total:2});
  await delay(45);
  w.emit('message',{type:'PROGRESS',id,completed:2,total:2});
  w.emit('message',{type:'RESULT',id,result:{ok:true,complete:true}});
  assert.deepEqual(await pending,{ok:true,complete:true});
  assert.deepEqual(observed,[[1,2],[2,2]]);
  c.dispose();

  const idle=createTopologyWorkerClient({WorkerCtor:FakeWorker,
    jobTimeoutMs:15,previewFirstProgressTimeoutMs:250,
    previewInactivityTimeoutMs:40});
  const stalled=idle.run(job);
  const second=FakeWorker.instances.at(-1),secondId=second.sent.at(-1).id;
  second.emit('message',{type:'PROGRESS',id:secondId,completed:1,total:2});
  await assert.rejects(stalled,/no progress/);
  assert.equal(second.terminated,true,
    'progress resets inactivity timeout, but a stalled preview still fails closed');
  idle.dispose();
});
