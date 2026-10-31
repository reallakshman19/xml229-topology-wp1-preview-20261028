/** XCU-owned PSI116 ES modules. Verify each blob before running any import.
 * Dependency modules execute only from verified in-memory Blob URLs; no
 * network check/import race, no vendored reader, and no UXML reconstruction.
 */
export const XCU_COMMIT='9f51bfcaf98af4041ec0c0615dc67c9c357b0632';
export const XCU_READER_BLOBS=Object.freeze({
 'UxmlConstants.js':'457b970f9cbccd29d38cecd0842614c339108107',
 'UxmlTypes.js':'5bac50ca692c483c3800ae7ec712710e7ae08572',
 'UxmlProfileDetector.js':'b4edfc1b47337a0ad62d2a01c0c8f2ff86844803',
 'UxmlValidationGate.js':'7a6070f9b77602f227a30d7e06a3e425d17c9c16',
 'UxmlPsi116SchemaMapper.js':'978a63141fb94ef9cad3c8eaa637a37675a605f9',
});
const order=['UxmlConstants.js','UxmlTypes.js','UxmlProfileDetector.js',
 'UxmlValidationGate.js','UxmlPsi116SchemaMapper.js'];
const root=new URL('../../vendor/uxml/uxml/',import.meta.url);
const hex=bytes=>Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
export async function gitBlobSha1(bytes){
 const prefix=new TextEncoder().encode('blob '+bytes.length+'\0');
 const message=new Uint8Array(prefix.length+bytes.length);
 message.set(prefix);message.set(bytes,prefix.length);
 return hex(new Uint8Array(await crypto.subtle.digest('SHA-1',message)));
}
export async function loadPinnedPsi116Reader({fetchImpl=fetch}={}){
 const texts=new Map();
 for(const file of order){
   const response=await fetchImpl(new URL(file,root),{cache:'no-store'});
   if(!response?.ok)throw Error('UXML_READER_FETCH_FAILED:'+file+':HTTP_'+(response?.status||'UNAVAILABLE'));
   const bytes=new Uint8Array(await response.arrayBuffer());
   const got=await gitBlobSha1(bytes),expected=XCU_READER_BLOBS[file];
   if(got!==expected)throw Error('UXML_READER_BLOB_HASH_MISMATCH:'+file+':expected='+expected+':actual='+got);
   texts.set(file,new TextDecoder('utf-8',{fatal:true}).decode(bytes));
 }
 const urls=new Map();
 try{
   for(const file of order){
     let code=texts.get(file);
     code=code.replace(/(['"])\.\/(Uxml[A-Za-z0-9]+\.js)\1/g,
       (match,quote,dependency)=>{
         const pinned=urls.get(dependency);
         if(!pinned)throw Error('UXML_READER_UNPINNED_IMPORT:'+file+':'+dependency);
         return quote+pinned+quote;
       });
     const imports=[...code.matchAll(/from\s*(['"])([^'"]+)\1/g)];
     if(imports.some(m=>m[2].startsWith('./')||m[2].startsWith('../')))
       throw Error('UXML_READER_UNVERIFIED_DEPENDENCY:'+file);
     urls.set(file,URL.createObjectURL(new Blob([code],{type:'text/javascript'})));
   }
   const module=await import(urls.get('UxmlPsi116SchemaMapper.js'));
   if(typeof module.mapPsi116ToUxml!=='function'||
      module.UXML_PSI116_MAPPER_SCHEMA!=='uxml-psi116-source-reader/v1')
     throw Error('UXML_READER_EXPORT_CONTRACT_MISMATCH');
   return Object.freeze({commit:XCU_COMMIT,read(xmlText,fileSha256){
     const doc=module.mapPsi116ToUxml(xmlText,{fileSha256});
     if(doc.schemaVersion!=='uxml-topology-v1'||doc.profile!=='UXML-TOPOLOGY-FULL'||
       doc.psi116?.sourceSha256!==fileSha256||doc.sources?.[0]?.hash!==fileSha256||
       !Array.isArray(doc.validation?.blockerCodes)||doc.validation.blockerCodes.length)
       throw Error('UXML_READER_DOCUMENT_CONTRACT_MISMATCH:'+(doc.validation?.blockerCodes||[]).join(','));
     return doc;
   }});
 } finally {
   for(const url of urls.values())URL.revokeObjectURL(url);
 }
}
