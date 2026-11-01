/** Disposable PSI116 topology Worker: legacy direct or opt-in UXML handshake.
 * No native CII, Final, review-case Apply or widening of Auto-fix policy.
 */
import {runXmlCii2019StandaloneEngine} from '../../converters/xml-cii-2019-standalone/engine.js';
import {loadPinnedPsi116Reader} from './uxml-browser-reader.mjs';
let bulkPinnedReaderPromise=null;
function pinnedReaderForJob(job){
  // One fully verified XCU module instance per live Worker during a bulk
  // lease. A fresh Worker always verifies all five immutable blobs again.
  // Each item STILL hashes and maps its distinct source and runs native EQUAL.
  if(job.options?.topologyBulkSession!==true)return loadPinnedPsi116Reader();
  if(!bulkPinnedReaderPromise){
    bulkPinnedReaderPromise=loadPinnedPsi116Reader().catch(error=>{
      bulkPinnedReaderPromise=null;
      throw error;
    });
  }
  return bulkPinnedReaderPromise;
}

async function sourceHash(sourceText){
 const encoded=new TextEncoder().encode(sourceText);
 const hash=await crypto.subtle.digest('SHA-256',encoded);
 return Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,'0')).join('');
}
self.onmessage=async ({data})=>{
 const {id,job,type}=data||{};
 if(type!=='RUN'||!Number.isSafeInteger(id))return;
 try{
  const speed=job?.options?.topologyBulkSpeedProfile===true;
  const started=speed?performance.now():0;
  const phases={};
  if(job?.sourceKind!=='xml'||job.topologyPreFinalOnly!==true||
    job.xml229NativeFinalPacket||job.stagedJsonText||
    job.options?.useTopoFixForCii===true||
    job.options?.outputMode!=='enriched-only'||
    job.options?.analyzeTopology!==true)
    throw Error('TOPOLOGY_WORKER_PREFINAL_ONLY');

  let payload=job;
  if(job.options?.topologyUxmlPreview===true){
    try{
      const hashStarted=speed?performance.now():0;
      const sha=await sourceHash(job.sourceText);
      if(speed)phases.workerSourceHashMs=performance.now()-hashStarted;
      if(sha!==job.sourceRawSha256)throw Error('UXML_SOURCE_BYTE_SHA_MISMATCH');
      // Revalidate every load, and allow retries after any failed fetch/import.
      const readerStarted=speed?performance.now():0;
      const reader=await pinnedReaderForJob(job);
      if(speed)phases.hubReaderLoadMs=performance.now()-readerStarted;
      const mapStarted=speed?performance.now():0;
      const uxmlDocument=reader.read(job.sourceText,sha);
      if(speed)phases.hubUxmlReadMs=performance.now()-mapStarted;
      payload={...job,uxmlDocument,
        // Advisory only: synchronous Python computes each native operation,
        // then posts progress in groups of four. Never send partial ops.
        topologyPreviewProgress:(completed,total)=>{
          const expected=job.options?.topologyShortPreviewRequests?.length||0;
          if(expected>0&&Number.isSafeInteger(completed)&&
             completed>=1&&completed<=expected&&total===expected)
            self.postMessage({type:'PROGRESS',id,completed,total});
        }};
    }catch(error){
      // A failed hub reader cannot authorize a mutating job, even when called
      // directly outside the UI's disabled-button guard.
      if(job.options?.generateTopoFix===true)
        throw Error('UXML_READER_UNAVAILABLE_AUTOFIX_REFUSED:'+
          (error?.message||String(error)));
      // Never silently use a broken reader: publish explicit UNAVAILABLE.
      // Direct path remains functional on this job and when toggle is OFF.
      const direct=await runXmlCii2019StandaloneEngine({
        ...job,options:{...job.options,topologyUxmlPreview:false}});
      self.postMessage({type:'RESULT',id,result:{...direct,
        topologyUxmlParity:{status:'UNAVAILABLE',
          differences:[error?.message||String(error)],
          readerCommit:'9f51bfcaf98af4041ec0c0615dc67c9c357b0632'}}});
      return;
    }
  }
  const engineStarted=speed?performance.now():0;
  const result=await runXmlCii2019StandaloneEngine(payload);
  if(speed){
    phases.enginePyodideMs=performance.now()-engineStarted;
    phases.workerTotalMs=performance.now()-started;
  }
  self.postMessage({type:'RESULT',id,result:speed?{
    ...result,topologyBulkTiming:{...phases,...(result.topologyBulkTiming||{})}
  }:result});
 }catch(error){
  self.postMessage({type:'ERROR',id,message:error?.message||String(error)});
 }
};
