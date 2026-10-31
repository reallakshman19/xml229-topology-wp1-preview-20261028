/** Disposable PSI116 topology Worker: legacy direct or opt-in UXML handshake.
 * No native CII, Final, review-case Apply or widening of Auto-fix policy.
 */
import {runXmlCii2019StandaloneEngine} from '../../converters/xml-cii-2019-standalone/engine.js';
import {loadPinnedPsi116Reader} from './uxml-browser-reader.mjs';
let readerPromise=null;
async function sourceHash(sourceText){
 const encoded=new TextEncoder().encode(sourceText);
 const hash=await crypto.subtle.digest('SHA-256',encoded);
 return Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,'0')).join('');
}
self.onmessage=async ({data})=>{
 const {id,job,type}=data||{};
 if(type!=='RUN'||!Number.isSafeInteger(id))return;
 try{
  if(job?.sourceKind!=='xml'||job.topologyPreFinalOnly!==true||
    job.xml229NativeFinalPacket||job.stagedJsonText||
    job.options?.useTopoFixForCii===true||
    job.options?.outputMode!=='enriched-only'||
    job.options?.analyzeTopology!==true)
    throw Error('TOPOLOGY_WORKER_PREFINAL_ONLY');

  let payload=job;
  if(job.options?.topologyUxmlPreview===true){
    try{
      const sha=await sourceHash(job.sourceText);
      if(sha!==job.sourceRawSha256)throw Error('UXML_SOURCE_BYTE_SHA_MISMATCH');
      const reader=await (readerPromise ||= loadPinnedPsi116Reader());
      const uxmlDocument=reader.read(job.sourceText,sha);
      payload={...job,uxmlDocument};
    }catch(error){
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
  const result=await runXmlCii2019StandaloneEngine(payload);
  self.postMessage({type:'RESULT',id,result});
 }catch(error){
  self.postMessage({type:'ERROR',id,message:error?.message||String(error)});
 }
};
