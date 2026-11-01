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
  let completedInWorker=0;
  let bulkLeases=0;
  let disposed=false;
  const pending=new Map();

  function reset(reason) {
    const old=worker;
    worker=null;
    completedInWorker=0;
    bulkLeases=0;
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
      if(data.type==='PROGRESS'){
        // A progress message can only refresh its own read-only preview job.
        // It cannot complete the job or publish operations/Apply authority.
        if(task.previewTotal>0&&Number.isSafeInteger(data.completed)&&
           data.total===task.previewTotal&&data.completed>task.lastProgress&&
           data.completed<=data.total){
          task.lastProgress=data.completed;
          clearTimeout(task.timeout);
          task.timeout=setTimeout(()=>reset(
            'TOPOLOGY_WORKER_TIMEOUT: no progress; original and last validated revision retained.'),
            jobTimeoutMs);
          task.onProgress?.(data.completed,data.total);
        }
        return;
      }
      pending.delete(data.id);
      clearTimeout(task.timeout);
      if(data.type==='RESULT') task.resolve(data.result);
      else if(data.type==='ERROR') task.reject(Error('TOPOLOGY_WORKER_ERROR: '+String(data.message||'unknown failure')));
      else task.reject(Error('TOPOLOGY_WORKER_PROTOCOL_ERROR'));
      // Engine job scratch directories live in Pyodide's in-memory FS.
      // Recycle only when idle, bounding memory during hundreds of sequential drops.
      if(++completedInWorker>=8 && !pending.size && bulkLeases===0 && worker===created){
        worker=null;completedInWorker=0;created.terminate();
      }
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
  function run(job,{onProgress}={}) {
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
      const previewTotal=Array.isArray(job?.options?.topologyShortPreviewRequests)
        ?job.options.topologyShortPreviewRequests.length:0;
      pending.set(id,{resolve,reject,timeout,previewTotal,lastProgress:0,
        onProgress:previewTotal&&typeof onProgress==='function'?onProgress:null});
      try {target.postMessage({type:'RUN',id,job});}
      catch(error){reset('TOPOLOGY_WORKER_SEND_FAILED: '+(error?.message||String(error)));}
    });
  }
  function beginBulkSession(){
    if(disposed)throw Error('TOPOLOGY_WORKER_DISPOSED');
    bulkLeases++;
  }
  function endBulkSession(){
    if(bulkLeases>0)bulkLeases--;
    // Keep the already-verified Worker for the immediate post-bulk read-only
    // evidence check. Its normal idle recycle resumes after that job.
  }
  run.beginBulkSession=beginBulkSession;
  run.endBulkSession=endBulkSession;
  return {
    run,beginBulkSession,endBulkSession,
    cancel(){reset('TOPOLOGY_WORKER_CANCELLED: last validated revision retained.');},
    dispose(){disposed=true;reset('TOPOLOGY_WORKER_DISPOSED');},
  };
}

let sharedClient;
function client(){return sharedClient ||= createTopologyWorkerClient();}
export function runTopologyWorkerJob(job){return client().run(job);}
export function cancelTopologyWorkerJobs(){sharedClient?.cancel();}
export function disposeTopologyWorker(){sharedClient?.dispose();sharedClient=null;}
