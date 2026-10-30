/** Dedicated, disposable PSI116 topology worker. Never runs native CII or Final. */
import {runXmlCii2019StandaloneEngine} from '../../converters/xml-cii-2019-standalone/engine.js';

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
    const result = await runXmlCii2019StandaloneEngine(job);
    self.postMessage({type:'RESULT',id,result});
  } catch(error) {
    self.postMessage({type:'ERROR',id,message:error?.message || String(error)});
  }
};
