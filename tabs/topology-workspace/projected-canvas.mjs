/** Orthographic inspection camera. Route strokes are display-only source order. */
const palette=['#60a5fa','#34d399','#fbbf24','#f472b6','#a78bfa','#fb7185','#2dd4bf'];
export const cameraPresets={iso:[-Math.PI/4,Math.atan(1/Math.sqrt(2))],top:[0,Math.PI/2],front:[0,0],right:[Math.PI/2,0]};
export const initialView=()=>({yaw:cameraPresets.iso[0],pitch:cameraPresets.iso[1],scale:1,panX:0,panY:0,center:null});
const dimensions=canvas=>{const r=canvas.getBoundingClientRect();return {width:Math.max(1,r.width),height:Math.max(1,r.height)};};
function plane(position,center,view){
 const x=position.x-center.x,y=position.y-center.y,z=position.z-center.z;
 return {x:x*Math.cos(view.yaw)-y*Math.sin(view.yaw),
  y:z*Math.cos(view.pitch)-(x*Math.sin(view.yaw)+y*Math.cos(view.yaw))*Math.sin(view.pitch)};
}
export function projectOccurrence(position,bounds,view,width,height){
 if(!position)return null;
 const p=plane(position,view.center||bounds.center,view);
 const scale=view.scale??Math.min(width,height)*.78/bounds.span*(view.zoom||1);
 return {x:width/2+view.panX+p.x*scale,y:height/2+view.panY-p.y*scale};
}
export function framePoints(points,bounds,view,width,height){
 if(!points.length)return {...view};
 const axes=['x','y','z'];
 const center=Object.fromEntries(axes.map(a=>[a,(Math.min(...points.map(p=>p[a]))+Math.max(...points.map(p=>p[a])))/2]));
 const projected=points.map(p=>plane(p,center,view));
 const minX=Math.min(...projected.map(p=>p.x)),maxX=Math.max(...projected.map(p=>p.x));
 const minY=Math.min(...projected.map(p=>p.y)),maxY=Math.max(...projected.map(p=>p.y));
 // A single point receives local context, rather than infinite magnification.
 const floor=Math.max(.01,bounds.span*.015);
 const scale=Math.min(width*.82/Math.max(floor,maxX-minX),height*.82/Math.max(floor,maxY-minY));
 return {...view,center,scale,panX:-(minX+maxX)/2*scale,panY:(minY+maxY)/2*scale};
}
export function zoomAt(view,factor,x,y,width,height){
 const scale=Math.max(1e-6,Math.min(1e6,view.scale*factor)),ratio=scale/view.scale;
 return {...view,scale,panX:x-width/2-(x-width/2-view.panX)*ratio,
  panY:y-height/2-(y-height/2-view.panY)*ratio};
}
export function hitOccurrences(scene,view,width,height,x,y,showHelpers=true){
 if(!scene)return [];
 return scene.records.filter(r=>r.position&&(r.route||showHelpers))
  .map(record=>({record,p:projectOccurrence(record.position,scene.bounds,view,width,height)}))
  .map(h=>({...h,d:Math.hypot(h.p.x-x,h.p.y-y)})).filter(h=>h.d<=10)
  .sort((a,b)=>a.d-b.d||a.record.branchIndex-b.record.branchIndex||a.record.sourceIndex-b.record.sourceIndex).map(h=>h.record);
}
export function createTopologyCanvas(canvas,onHits=()=>{}){
 const ctx=canvas.getContext('2d');if(!ctx)throw Error('2D Canvas unavailable');
 let scene=null,selected=new Set(),mode='select',view=initialView(),pointer=null;
 let showHelpers=true,showLabels=true,disposed=false,framedIds=null;
 const size=()=>dimensions(canvas);
 const points=ids=>(ids?[...ids].map(id=>scene?.byId.get(id)):scene?.records||[]).filter(r=>r?.position&&(r.route||showHelpers)).map(r=>r.position);
 function frame(ids=null){if(!scene)return;const {width,height}=size();view=framePoints(points(ids),scene.bounds,view,width,height);framedIds=ids?new Set(ids):null;draw();}
 const project=p=>{const {width,height}=size();return projectOccurrence(p,scene.bounds,view,width,height);};
 function draw(){
  if(disposed)return;const {width,height}=size(),dpr=globalThis.devicePixelRatio||1;
  if(canvas.width!==Math.round(width*dpr)||canvas.height!==Math.round(height*dpr)){
   canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);
  }
  ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#07101f';ctx.fillRect(0,0,width,height);if(!scene)return;
  ctx.lineWidth=2.5;ctx.setLineDash([]);
  for(const edge of scene.segments){const a=scene.byId.get(edge.a),b=scene.byId.get(edge.b);if(!a?.position||!b?.position)continue;
   const p=project(a.position),q=project(b.position);ctx.strokeStyle=palette[edge.branchIndex%palette.length];
   ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();}
  for(const r of scene.records){if(!r.position||(!r.route&&!showHelpers))continue;
   const p=project(r.position),active=selected.has(r.id);ctx.beginPath();ctx.arc(p.x,p.y,active?7:r.route?3.5:2.7,0,Math.PI*2);
   ctx.fillStyle=active?'#fff':r.route?palette[r.branchIndex%palette.length]:'#94a3b8';ctx.fill();
   if(active){ctx.strokeStyle='#fbbf24';ctx.lineWidth=2;ctx.stroke();}
   if(showLabels&&(active||(r.route&&selected.size===0))){ctx.fillStyle='#cbd5e1';ctx.font='11px system-ui';ctx.fillText(r.nodeNumberRaw+' '+r.type,p.x+6,p.y-6);}}
  // Axes use the same basis as the geometry, including the selected preset.
  const origin={x:0,y:0,z:0};
  for(const [axis,color] of [['x','#fb7185'],['y','#34d399'],['z','#60a5fa']]){
   const p=plane({...origin,[axis]:28},origin,view);ctx.strokeStyle=color;ctx.fillStyle=color;
   ctx.beginPath();ctx.moveTo(48,48);ctx.lineTo(48+p.x,48-p.y);ctx.stroke();ctx.fillText(axis.toUpperCase(),48+p.x,48-p.y);}
 }
 const down=e=>{if(![0,1,2].includes(e.button))return;e.preventDefault();canvas.focus();
  pointer={x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,button:e.button,dragged:false,shift:e.shiftKey,add:e.ctrlKey||e.metaKey||e.shiftKey};canvas.setPointerCapture?.(e.pointerId);};
 const move=e=>{if(!pointer)return;const dx=e.clientX-pointer.lastX,dy=e.clientY-pointer.lastY;pointer.lastX=e.clientX;pointer.lastY=e.clientY;
  if(Math.hypot(e.clientX-pointer.x,e.clientY-pointer.y)>4)pointer.dragged=true;if(!pointer.dragged)return;
  const orbit=pointer.button===2||(pointer.button===0&&(pointer.shift||mode==='orbit'));
  if(orbit){view.yaw+=dx*.008;view.pitch=Math.max(-Math.PI/2,Math.min(Math.PI/2,view.pitch+dy*.006));}
  else {view.panX+=dx;view.panY+=dy;}draw();};
 const up=e=>{const p=pointer;pointer=null;if(!p)return;canvas.releasePointerCapture?.(e.pointerId);
  if(p.dragged||p.button!==0||mode!=='select')return;const r=canvas.getBoundingClientRect(),{width,height}=size();
  onHits(hitOccurrences(scene,view,width,height,e.clientX-r.left,e.clientY-r.top,showHelpers),p.add);};
 const wheel=e=>{e.preventDefault();const r=canvas.getBoundingClientRect(),{width,height}=size();
  view=zoomAt(view,Math.exp(-Math.max(-500,Math.min(500,e.deltaY*(e.deltaMode===1?16:1)))*.0015),e.clientX-r.left,e.clientY-r.top,width,height);draw();};
 const abort=()=>{pointer=null;},context=e=>e.preventDefault(),dbl=()=>frame(),key=e=>{
  if(e.key.toLowerCase()==='f'){e.preventDefault();frame(selected.size?selected:null);}
  if(e.key==='Home'){e.preventDefault();frame();}};
 const listeners={pointerdown:down,pointermove:move,pointerup:up,pointercancel:abort,lostpointercapture:abort,contextmenu:context,dblclick:dbl,keydown:key};
 for(const [type,fn] of Object.entries(listeners))canvas.addEventListener(type,fn);canvas.addEventListener('wheel',wheel,{passive:false});
 const observer=typeof ResizeObserver!=='undefined'?new ResizeObserver(()=>frame(framedIds)):null;observer?.observe(canvas);draw();
 return {setScene(next){const changed=next?.sourceSha256!==scene?.sourceSha256;scene=next;if(changed){view=initialView();frame();}else draw();},
  setSelection(ids){selected=new Set(ids);draw();},setMode(value){if(['select','pan','orbit'].includes(value))mode=value;canvas.style.cursor=mode==='orbit'?'grab':mode==='pan'?'move':'crosshair';},
  setShowHelpers(value){showHelpers=!!value;draw();},setShowLabels(value){showLabels=!!value;draw();},
  zoom(factor){const {width,height}=size();view=zoomAt(view,factor,width/2,height/2,width,height);draw();},
  setPreset(preset){if(cameraPresets[preset]){[view.yaw,view.pitch]=cameraPresets[preset];frame(selected.size?selected:null);}},
  fit(){frame();},focus(ids){frame(ids);},getView(){return {...view};},
  dispose(){disposed=true;observer?.disconnect();for(const [type,fn] of Object.entries(listeners))canvas.removeEventListener(type,fn);canvas.removeEventListener('wheel',wheel);}};
}
