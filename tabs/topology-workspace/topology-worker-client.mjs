/** Isolate expensive Pyodide topology analysis/transactions from canvas input.
 * Worker termination is the hard cancellation boundary for synchronous WASM.
 */
export function createTopologyWorkerClient({
  WorkerCtor=globalThis.Worker,
  workerUrl=new URL('./topology-worker.mjs',import.meta.url),
  jobTimeoutMs=180000,
}={}) {
  let worker=null;
  let sequence=0;
  let disposed=false;
  const pending=new Map();

  function reset(reason) {
    const old=worker;
    worker=null;
    if(old) old.terminate();
    for(const {reject,timeout} of pending.values()) {
      clearTimeout(timeout);
      reject(Error(reason));
    }
    pending.clear();
  }
  function ensureWorker() {
    if(worker) return worker;
    if(typeof WorkerCtor !== 'function') throw Error('TOPOLOGY_WORKER_UNAVAILABLE: use a browser with module Worker support.');
    const created=new WorkerCtor(workerUrl,{type:'module'});
    created.addEventListener('message',({data})=>{
      if(worker!==created || !data || !Number.isSafeInteger(data.id)) return;
      const task=pending.get(data.id);
      if(!task) return;
      pending.delete(data.id);
      clearTimeout(task.timeout);
      if(data.type==='RESULT') task.resolve(data.result);
      else if(data.type==='ERROR') task.reject(Error('TOPOLOGY_WORKER_ERROR: '+String(data.message||'unknown failure')));
      else task.reject(Error('TOPOLOGY_WORKER_PROTOCOL_ERROR'));
    });
    const crashed=(event)=>{
      const message=event?.message || 'Worker failed to load or exchange data';
      reset('TOPOLOGY_WORKER_CRASH: '+message);
    };
    created.addEventListener('error',crashed);
    created.addEventListener('messageerror',crashed);
    worker=created;
    return worker;
  }
  function run(job) {
    if(disposed) return Promise.reject(Error('TOPOLOGY_WORKER_DISPOSED'));
    if(job?.sourceKind!=='xml' || job.topologyPreFinalOnly!==true ||
       job.options?.analyzeTopology!==true || job.options?.useTopoFixForCii===true) {
      return Promise.reject(Error('TOPOLOGY_WORKER_PREFINAL_ONLY'));
    }
    return new Promise((resolve,reject)=>{
      let target;
      try {target=ensureWorker();}
      catch(error) {reject(error);return;}
      const id=++sequence;
      const timeout=setTimeout(()=>reset('TOPOLOGY_WORKER_TIMEOUT: no result; original and last validated revision retained.'),jobTimeoutMs);
      pending.set(id,{resolve,reject,timeout});
      try {target.postMessage({type:'RUN',id,job});}
      catch(error){reset('TOPOLOGY_WORKER_SEND_FAILED: '+(error?.message||String(error)));}
    });
  }
  return {
    run,
    cancel(){reset('TOPOLOGY_WORKER_CANCELLED: last validated revision retained.');},
    dispose(){disposed=true;reset('TOPOLOGY_WORKER_DISPOSED');},
  };
}

let sharedClient;
function client(){return sharedClient ||= createTopologyWorkerClient();}
export function runTopologyWorkerJob(job){return client().run(job);}
export function cancelTopologyWorkerJobs(){sharedClient?.cancel();}
export function disposeTopologyWorker(){sharedClient?.dispose();sharedClient=null;}
