/** Actual control-flow cleanup mutants; synthetic only, no browser or private file. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createTopologyWorkerClient} from '../tabs/topology-workspace/topology-worker-client.mjs';

const stageSource=readFileSync('converters/xml-cii-2019-standalone/topology-integration.js','utf8');
const workerSource=readFileSync('tabs/topology-workspace/topology-worker.mjs','utf8');
const clientSource=readFileSync('tabs/topology-workspace/topology-worker-client.mjs','utf8');

function stageFrom(code){
  const at=code.indexOf('export async function runPsi116TopologyStage(');
  assert.ok(at>0,'real stage function exists');
  const method=code.slice(at).replace('export async function','async function');
  return new Function('topologyRequested','ensurePsi116TopologyPackage','safeStem',
    'text','TOPOLOGY_SNIPPET','readOptional','performance',
    method+'\nreturn runPsi116TopologyStage;')(
    ()=>true,async()=>{},()=> 'synthetic',x=>String(x),'SYNTHETIC_PYTHON_SNIPPET',
    ()=>'',performance);
}
async function engineCatchClears(code){
  const commands=[];
  const pyodide={
    globals:{set(){}},
    runPython:command=>{commands.push(command);},
    runPythonAsync:async()=>{throw Error('SHORT_MEMO_INJECTED_FAILURE');},
  };
  const job={sourceKind:'xml',sourceName:'synthetic.xml',
    options:{analyzeTopology:true,generateTopoFix:true,
      topologyActionIds:['SHORT-SYNTHETIC'],
      topologyShortElementRequests:[{id:'SHORT-SYNTHETIC'}],
      topologyBulkSession:true,topologyShortMemoSession:'synthetic_error_clear'}};
  await assert.rejects(stageFrom(code)(pyodide,job,'/synthetic.xml','/work/synthetic',[]),
    /SHORT_MEMO_INJECTED_FAILURE/);
  return commands.filter(command=>String(command).includes('clear_memo()')).length;
}

test('actual Pyodide stage catch clears memo after failed Python transaction',async()=>{
  assert.equal(await engineCatchClears(stageSource),1);
});
test('MUTANT: removing real stage catch/ERROR clear produces assertion failure',async()=>{
  const clear="    pyodide.runPython('from psi116_topology_resolver.short_memo import clear_memo; clear_memo()');";
  assert.ok(stageSource.includes(clear),'real cleanup call must exist');
  const mutant=stageSource.replace(clear,'    /* MUTANT: omitted ERROR clear */');
  assert.equal(await engineCatchClears(mutant),0);
  assert.throws(()=>assert.equal(0,1,'ERROR path must call clear_memo()'),{
    name:'AssertionError'});
  console.info('MEMO_MUTANT_KILLED:pyodide-worker-error-clear-removed');
});

function workerFrom(code,clear){
  const at=code.indexOf('self.onmessage=async ');
  assert.ok(at>0,'actual Worker message dispatcher must exist');
  const scope={postMessage(){}};
  const factory=new Function('self','clearXml229ShortMemo','runXmlCii2019StandaloneEngine',
    'pinnedReaderForJob','sourceHash','performance',
    code.slice(at)+'\nreturn self.onmessage;');
  return factory(scope,clear,async()=>{},async()=>{},async()=>'',performance);
}
test('actual Worker SHORT_MEMO_CLEAR message invokes engine cleanup',async()=>{
  let count=0;
  const handler=workerFrom(workerSource,async()=>{count++;});
  await handler({data:{type:'SHORT_MEMO_CLEAR'}});
  assert.equal(count,1);
});
test('MUTANT: removing actual Worker cleanup dispatch is killed',async()=>{
  const clear='try{await clearXml229ShortMemo();}';
  assert.ok(workerSource.includes(clear));
  const mutant=workerSource.replace(clear,'try{/* MUTANT: skipped cleanup */}');
  let count=0;
  const handler=workerFrom(mutant,async()=>{count++;});
  await handler({data:{type:'SHORT_MEMO_CLEAR'}});
  assert.equal(count,0);
  assert.throws(()=>assert.equal(count,1,'Worker must invoke clearXml229ShortMemo'),{
    name:'AssertionError'});
  console.info('MEMO_MUTANT_KILLED:worker-clear-handler-removed');
});

class FakeWorker{
  static instances=[];
  constructor(){this.sent=[];this.handlers={};this.terminated=false;FakeWorker.instances.push(this);}
  addEventListener(type,callback){(this.handlers[type]??=[]).push(callback);}
  postMessage(value){this.sent.push(value);}
  terminate(){this.terminated=true;}
  emit(value){for(const fn of this.handlers.message||[])fn({data:value});}
}
const job={sourceKind:'xml',topologyPreFinalOnly:true,
  options:{analyzeTopology:true,useTopoFixForCii:false}};
async function clientLifecycle(create){
  const c=create({WorkerCtor:FakeWorker,workerUrl:'synthetic://worker',jobTimeoutMs:1000});
  c.beginBulkSession();
  const result=c.run(job),worker=FakeWorker.instances.at(-1);
  worker.emit({type:'RESULT',id:worker.sent[0].id,result:{ok:true}});
  await result;
  c.endBulkSession();
  const cleared=worker.sent.some(m=>m.type==='SHORT_MEMO_CLEAR');
  const pending=c.run(job);
  c.cancel();
  await assert.rejects(pending,/CANCELLED/);
  const terminated=worker.terminated;
  c.dispose();
  return {cleared,terminated};
}
function clientFrom(code){
  let snippet=code.slice(0,code.indexOf('\nlet sharedClient;'));
  assert.ok(snippet.includes('export function createTopologyWorkerClient('));
  snippet=snippet.replace('export function createTopologyWorkerClient(',
    'function createTopologyWorkerClient(')
    .replace("new URL('./topology-worker.mjs',import.meta.url)",
      "'synthetic://worker'");
  return new Function(snippet+'\nreturn createTopologyWorkerClient;')();
}
test('real bulk completion dispatches clear; Cancel terminates memo-holding Worker',async()=>{
  assert.deepEqual(await clientLifecycle(createTopologyWorkerClient),
    {cleared:true,terminated:true});
});
test('MUTANT: removing bulk completion clear dispatch fails assertion',async()=>{
  const call="worker.postMessage({type:'SHORT_MEMO_CLEAR'})";
  assert.ok(clientSource.includes(call));
  const result=await clientLifecycle(clientFrom(clientSource.replace(
    call,'/* MUTANT: omitted CLEAR dispatch */')));
  assert.equal(result.cleared,false);
  assert.throws(()=>assert.equal(result.cleared,true),{name:'AssertionError'});
  console.info('MEMO_MUTANT_KILLED:cancel-completion-clear-dispatch-removed');
});
test('MUTANT: Cancel without terminating Worker leaves live Python memo',async()=>{
  const call="if(old) old.terminate();";
  assert.ok(clientSource.includes(call));
  const result=await clientLifecycle(clientFrom(clientSource.replace(
    call,'if(old) { /* MUTANT: retain Worker/memo */ }')));
  assert.equal(result.terminated,false);
  assert.throws(()=>assert.equal(result.terminated,true),{name:'AssertionError'});
  console.info('MEMO_MUTANT_KILLED:cancel-worker-termination-removed');
});
