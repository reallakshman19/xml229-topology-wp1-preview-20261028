import test from 'node:test';
import assert from 'node:assert/strict';
import {initialView,framePoints,projectOccurrence,zoomAt,cameraPresets} from '../tabs/topology-workspace/projected-canvas.mjs';
const bounds={center:{x:1e7,y:-2e7,z:3e7},span:6000};
const points=[{x:1e7-3000,y:-2e7-2000,z:3e7-1000},{x:1e7+3000,y:-2e7+2000,z:3e7+1000}];
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-6,`${a} != ${b}`);
test('all presets fit distant asymmetric geometry in portrait and wide canvases',()=>{
 for(const [yaw,pitch] of Object.values(cameraPresets))for(const [w,h] of [[240,600],[1200,300]]){
  const v=framePoints(points,bounds,{...initialView(),yaw,pitch},w,h);
  for(const p of points){const q=projectOccurrence(p,bounds,v,w,h);assert.ok(q.x>=0&&q.x<=w&&q.y>=0&&q.y<=h);}
 }
});
test('focus frames selected endpoints locally and centres their projected bounds',()=>{
 const selected=[points[0],{...points[0],x:points[0].x+2,z:points[0].z+1}];
 const v=framePoints(selected,bounds,initialView(),800,500);
 const p=selected.map(p=>projectOccurrence(p,bounds,v,800,500));
 near((p[0].x+p[1].x)/2,400);near((p[0].y+p[1].y)/2,250);
 assert.ok(v.scale>framePoints(points,bounds,initialView(),800,500).scale);
});
test('cursor-centred zoom preserves the exact screen point under the pointer',()=>{
 const v=framePoints(points,bounds,initialView(),800,500),p=projectOccurrence(points[0],bounds,v,800,500);
 const next=zoomAt(v,2.3,p.x,p.y,800,500),q=projectOccurrence(points[0],bounds,next,800,500);
 near(p.x,q.x);near(p.y,q.y);
});
test('top is XY, front is XZ, right is YZ; single point and zero span remain finite',()=>{
 const b={center:{x:0,y:0,z:0},span:1};
 for(const [name,hidden] of [['top','z'],['front','y'],['right','x']]){
  const [yaw,pitch]=cameraPresets[name],v={...initialView(),yaw,pitch,scale:1};
  const p=projectOccurrence({x:0,y:0,z:0},b,v,500,500),q=projectOccurrence({x:0,y:0,z:0,[hidden]:10},b,v,500,500);
  near(p.x,q.x);near(p.y,q.y);
 }
 const v=framePoints([{x:0,y:0,z:0}],b,initialView(),200,200);
 assert.ok(Number.isFinite(v.scale));
});
