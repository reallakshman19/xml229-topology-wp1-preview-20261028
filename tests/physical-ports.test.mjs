import test from 'node:test';
import assert from 'node:assert/strict';
import {physicalPortSegments} from '../tabs/topology-workspace/occurrence-scene.mjs';
const n=(id,type,refNo,endpoint,x)=>({id,type,refNo,endpoint:String(endpoint),position:{x,y:0,z:0}});
test('negative gasket and flange ports render their 3 mm and 86 mm finite bodies',()=>{
 const records=[n('branch','BRAN','B',1,0),n('gasket','GASK','G',1,0),n('gasket-helper','GASK','G',2,3),
 n('flange-helper','FLAN','F',1,3),n('rigid','RIGID','F',2,89)];
 const edges=physicalPortSegments(records);
 assert.ok(edges.some(e=>e.a==='gasket'&&e.b==='gasket-helper'&&e.kind==='component'));
 assert.ok(edges.some(e=>e.a==='flange-helper'&&e.b==='rigid'&&e.kind==='component'));
 assert.ok(edges.some(e=>e.a==='gasket-helper'&&e.b==='flange-helper'));
 assert.ok(!edges.some(e=>e.a==='gasket'&&e.b==='rigid'));
});
test('TEE owner draws all three physical helper ports',()=>{
 const edges=physicalPortSegments([n('p1','TEE','T',1,0),n('p3','TEE','T',3,20),n('owner','TEE','T',0,10),n('p2','TEE','T',2,30)]);
 assert.deepEqual(edges.filter(e=>e.kind==='component').map(e=>[e.a,e.b]),[['owner','p1'],['owner','p3'],['owner','p2']]);
});
