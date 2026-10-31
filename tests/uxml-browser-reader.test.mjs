import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,webcrypto} from 'node:crypto';
import {XCU_COMMIT,XCU_READER_BLOBS,gitBlobSha1,loadPinnedPsi116Reader} from '../tabs/topology-workspace/uxml-browser-reader.mjs';

globalThis.crypto ||= webcrypto;
test('UXML browser loader pins the immutable XCU commit and five evaluated dependencies',()=>{
 assert.equal(XCU_COMMIT,'9f51bfcaf98af4041ec0c0615dc67c9c357b0632');
 assert.equal(Object.keys(XCU_READER_BLOBS).length,5);
 assert.equal(XCU_READER_BLOBS['UxmlPsi116SchemaMapper.js'],'978a63141fb94ef9cad3c8eaa637a37675a605f9');
});
test('WebCrypto Git blob SHA-1 matches native Git object hashing for original bytes',async()=>{
 const sample=new Uint8Array([0xef,0xbb,0xbf,0x3c,0x61,0x3e,0x0d,0x0a,0x3c,0x2f,0x61,0x3e]);
 const reference=createHash('sha1').update('blob '+sample.length+'\0').update(sample).digest('hex');
 assert.equal(await gitBlobSha1(sample),reference);
 const mutant=sample.slice();mutant[0]^=0x1;
 assert.notEqual(await gitBlobSha1(mutant),reference);
});
test('Tampered upstream blob refused before any ES module evaluation',async()=>{
 let calls=0;
 const fetchImpl=async()=>{
   calls++;
   const bytes=new TextEncoder().encode('/*synthetic injected wrong reader code*/');
   return {ok:true,arrayBuffer:async()=>bytes.buffer};
 };
 await assert.rejects(loadPinnedPsi116Reader({fetchImpl}),
   /UXML_READER_BLOB_HASH_MISMATCH:UxmlConstants.js/);
 assert.equal(calls,1,'never request or execute mapper after first hash refusal');
});
