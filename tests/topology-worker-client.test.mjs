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
