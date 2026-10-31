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

test('missing pinned Pyodide asset surfaces filename and permits retry',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000,startupTimeoutMs:1000});
 const p=c.run(validJob),w=FakeWorker.instances.at(-1);
 w.emit('message',{type:'READY'});
 w.emit('message',{type:'ERROR',id:w.sent[0].id,
   message:'TOPOLOGY_PYODIDE_ASSET_MISSING: vendor/pyodide/pyodide.asm.wasm (HTTP 404). Obtain pinned runtime assets using .github/workflows/repair-validation.yml.'});
 await assert.rejects(p,/pyodide\.asm\.wasm.*repair-validation\.yml/);
 c.cancel();
 const next=c.run(validJob),w2=FakeWorker.instances.at(-1);
 assert.notEqual(w2,w);
 w2.emit('message',{type:'READY'});
 w2.emit('message',{type:'RESULT',id:w2.sent[0].id,result:{ok:true}});
 assert.deepEqual(await next,{ok:true});c.dispose();
});

test('silent worker startup failure fails fast and does not strand the next Analyze',async()=>{
 const c=createTopologyWorkerClient({WorkerCtor:FakeWorker,jobTimeoutMs:1000,startupTimeoutMs:20});
 const failed=c.run(validJob),w=FakeWorker.instances.at(-1);
 await assert.rejects(failed,/TOPOLOGY_WORKER_START_FAILED.*pyodide\.asm\.wasm.*python_stdlib\.zip/);
 assert.equal(w.terminated,true);
 const next=c.run(validJob),fresh=FakeWorker.instances.at(-1);
 fresh.emit('message',{type:'READY'});
 fresh.emit('message',{type:'RESULT',id:fresh.sent[0].id,result:{ok:true}});
 await next;c.dispose();
});
