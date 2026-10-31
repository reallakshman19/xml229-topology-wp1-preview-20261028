/** Dedicated, disposable PSI116 topology worker. Never runs native CII or Final. */
import {runXmlCii2019StandaloneEngine} from '../../converters/xml-cii-2019-standalone/engine.js';

// READY precedes the costly Python runtime load, so a missing module Worker
// is distinguishable from a slow but healthy Pyodide job.
self.postMessage({type:'READY'});
let assetsChecked=false;
async function assertPinnedAssets(){
  if(assetsChecked)return;
  for(const filename of ['pyodide.asm.wasm','python_stdlib.zip']){
    const url=new URL('../../vendor/pyodide/'+filename,import.meta.url);
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),12000);
    try{
      const response=await fetch(url,{method:'HEAD',cache:'no-store',signal:controller.signal});
      if(!response.ok)throw Error('HTTP '+response.status);
    }catch(error){
      throw Error('TOPOLOGY_PYODIDE_ASSET_MISSING: vendor/pyodide/'+filename+
        ' ('+(error?.message||String(error))+'). Obtain pinned runtime assets using the fetch commands in .github/workflows/repair-validation.yml.');
    }finally{clearTimeout(timer);}
  }
  assetsChecked=true;
}

self.onmessage = async ({data}) => {
  const {id,job,type} = data || {};
  if(type !== 'RUN' || !Number.isSafeInteger(id)) return;
  try {
    if(job?.sourceKind !== 'xml' || job.topologyPreFinalOnly !== true ||
       job.xml229NativeFinalPacket || job.stagedJsonText ||
       job.options?.useTopoFixForCii === true ||
       job.options?.outputMode !== 'enriched-only' ||
       job.options?.analyzeTopology !== true) {
      throw Error('TOPOLOGY_WORKER_PREFINAL_ONLY');
    }
    await assertPinnedAssets();
    const result = await runXmlCii2019StandaloneEngine(job);
    self.postMessage({type:'RESULT',id,result});
  } catch(error) {
    self.postMessage({type:'ERROR',id,message:error?.message || String(error)});
  }
};
