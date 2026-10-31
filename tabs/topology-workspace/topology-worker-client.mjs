/** Isolate expensive Pyodide topology analysis/transactions from canvas input.
 * Worker termination is the hard cancellation boundary for synchronous WASM.
 */
export function createTopologyWorkerClient({
  WorkerCtor=globalThis.Worker,
  workerUrl=new URL('./topology-worker.mjs',import.meta.url),
  jobTimeoutMs=180000,
  startupTimeoutMs=15000,
}={}) {
  let worker=null;
  let sequence=0;
  let completedInWorker=0;
  let disposed=false;
  let startupTimeout=null;
  const assetHelp='Check vendor/pyodide/pyodide.asm.wasm and vendor/pyodide/python_stdlib.zip; obtain pinned assets using the fetch commands in .github/workflows/repair-validation.yml.';
  const pending=new Map();

  function reset(reason) {
    if(startupTimeout!==null){clearTimeout(startupTimeout);startupTimeout=null;}
    const old=worker;
    worker=null;
    completedInWorker=0;
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
    let created;
    try{created=new WorkerCtor(workerUrl,{type:'module'});}
    catch(error){throw Error('TOPOLOGY_WORKER_START_FAILED: '+
      (error?.message||String(error))+'. '+assetHelp);}
    created.addEventListener('message',({data})=>{
      if(worker!==created||!data)return;
      if(data.type==='READY'){
        if(startupTimeout!==null){clearTimeout(startupTimeout);startupTimeout=null;}
        return;
      }
      if(!Number.isSafeInteger(data.id))return;
      if(startupTimeout!==null){clearTimeout(startupTimeout);startupTimeout=null;}
      const task=pending.get(data.id);
      if(!task) return;
      pending.delete(data.id);
      clearTimeout(task.timeout);
      if(data.type==='RESULT') task.resolve(data.result);
      else if(data.type==='ERROR') task.reject(Error('TOPOLOGY_WORKER_ERROR: '+String(data.message||'unknown failure')));
      else task.reject(Error('TOPOLOGY_WORKER_PROTOCOL_ERROR'));
      // Engine job scratch directories live in Pyodide's in-memory FS.
      // Recycle only when idle, bounding memory during hundreds of sequential drops.
      if(++completedInWorker>=8 && !pending.size && worker===created){
        worker=null;completedInWorker=0;created.terminate();
      }
    });
    const crashed=(event)=>{
      const message=event?.message || 'Worker failed to load or exchange data';
      reset('TOPOLOGY_WORKER_CRASH: '+message+'. '+assetHelp);
    };
    created.addEventListener('error',crashed);
    created.addEventListener('messageerror',crashed);
    worker=created;
    startupTimeout=setTimeout(()=>{
      if(worker===created)reset('TOPOLOGY_WORKER_START_FAILED: worker did not start. '+assetHelp);
    },startupTimeoutMs);
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
