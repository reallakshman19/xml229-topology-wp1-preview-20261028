/** Projected-3D Canvas 2D navigation adapted from Topology 5B makeProjector/drawGraph.
 * Route strokes are display-only source order, never PSI116 connection authority. */
const palette = ['#60a5fa','#34d399','#fbbf24','#f472b6','#a78bfa','#fb7185','#2dd4bf'];
const initialView = () => ({ yaw: -0.18, pitch: 0.08, zoom: 1, panX: 0, panY: 0 });
function dimensions(canvas) {
  const rect = canvas.getBoundingClientRect();
  return { width: Math.max(400, rect.width || 400), height: Math.max(300, rect.height || 300) };
}
export function projectOccurrence(position, bounds, view, width, height) {
  if (!position) return null;
  const scale = Math.min(width,height) * .78 / bounds.span * view.zoom;
  const dx = position.x - bounds.center.x, dy = position.y - bounds.center.y;
  const dz = position.z - bounds.center.z;
  const rx = dx * Math.cos(view.yaw) - dy * Math.sin(view.yaw);
  const ry = dx * Math.sin(view.yaw) + dy * Math.cos(view.yaw);
  const py = ry * Math.cos(view.pitch) - dz * Math.sin(view.pitch);
  return { x: width / 2 + view.panX + rx * scale,
    y: height / 2 + view.panY - py * scale };
}
export function hitOccurrences(scene, view, width, height, x, y, showHelpers = true) {
  if (!scene) return [];
  return scene.records.filter(r => r.position && (r.route || showHelpers))
    .map(r => ({ record: r, point: projectOccurrence(r.position,scene.bounds,view,width,height) }))
    .map(hit => ({ ...hit, distance: Math.hypot(hit.point.x-x,hit.point.y-y) }))
    .filter(hit => hit.distance <= 10)
    .sort((a,b) => a.distance-b.distance || a.record.branchIndex-b.record.branchIndex ||
      a.record.sourceIndex-b.record.sourceIndex).map(hit => hit.record);
}
function fillCanvas(canvas, ctx, width, height) {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * dpr);canvas.height = Math.floor(height * dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle = '#07101f';ctx.fillRect(0,0,width,height);
}
export function createTopologyCanvas(canvas, onHits = () => {}) {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw Error('2D Canvas unavailable');
  let scene=null, selected=new Set(), mode='select', view=initialView(), pointer=null;
  let showHelpers=true, showLabels=true, disposed=false;
  const size = () => dimensions(canvas);
  const project = p => {
    const {width,height}=size();
    return scene ? projectOccurrence(p,scene.bounds,view,width,height) : null;
  };
  function drawRoutes() {
    ctx.lineWidth=2.5;ctx.setLineDash([]);
    for(const edge of scene.segments) {
      const a=scene.byId.get(edge.a),b=scene.byId.get(edge.b);
      if(!a?.position||!b?.position)continue;
      const p=project(a.position),q=project(b.position);
      ctx.strokeStyle=palette[edge.branchIndex%palette.length];
      ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();
    }
  }
  function drawRecords() {
    for(const r of scene.records){
      if(!r.position||(!r.route&&!showHelpers))continue;
      const p=project(r.position),active=selected.has(r.id);
      ctx.beginPath();ctx.arc(p.x,p.y,active?7:r.route?3.5:2.7,0,Math.PI*2);
      ctx.fillStyle=active?'#ffffff':r.route?palette[r.branchIndex%palette.length]:'#94a3b8';
      ctx.fill();
      if(active){ctx.strokeStyle='#fbbf24';ctx.lineWidth=2;ctx.stroke();}
      if(showLabels&&(active||(r.route&&selected.size===0))){
        ctx.fillStyle='#cbd5e1';ctx.font='11px system-ui';
        ctx.fillText(r.nodeNumberRaw+' '+r.type,p.x+6,p.y-6);
      }
    }
  }
  function draw() {
    if(disposed)return;
    const {width,height}=size();fillCanvas(canvas,ctx,width,height);
    if(!scene)return;
    drawRoutes();drawRecords();
    ctx.fillStyle='rgba(2,6,23,.8)';ctx.fillRect(10,height-27,Math.min(width-20,520),20);
    ctx.fillStyle='#cbd5e1';ctx.font='11px system-ui';
    ctx.fillText('Source-order display only · '+mode+' · wheel zoom · select by occurrence',17,height-13);
  }
  const down=e=>{
    if(e.button!==0&&e.button!==1)return;
    pointer={x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,
      button:e.button,dragged:false,shift:e.shiftKey};
    canvas.setPointerCapture?.(e.pointerId);
  };
  const move=e=>{
    if(!pointer)return;
    const dx=e.clientX-pointer.lastX,dy=e.clientY-pointer.lastY;
    pointer.lastX=e.clientX;pointer.lastY=e.clientY;
    if(Math.hypot(e.clientX-pointer.x,e.clientY-pointer.y)>4)pointer.dragged=true;
    if(!pointer.dragged)return;
    const dragMode=pointer.button===1||pointer.shift?'orbit':mode;
    if(dragMode==='orbit'){view.yaw+=dx*.008;view.pitch=Math.max(-1.2,Math.min(1.2,view.pitch+dy*.006));}
    else if(dragMode==='pan'){view.panX+=dx;view.panY+=dy;}
    draw();
  };
  const up=e=>{
    const downEvent=pointer;pointer=null;
    if(!downEvent||downEvent.dragged||mode!=='select'||e.button!==0)return;
    const rect=canvas.getBoundingClientRect(),{width,height}=size();
    const x=e.clientX-rect.left,y=e.clientY-rect.top;
    onHits(hitOccurrences(scene,view,width,height,x,y,showHelpers),downEvent.shift);
  };
  const wheel=e=>{
    e.preventDefault();view.zoom=Math.max(.05,Math.min(50,view.zoom*(e.deltaY<0?1.12:.89)));draw();
  };
  const abort=()=>{pointer=null;};
  canvas.addEventListener('pointerdown',down);canvas.addEventListener('pointermove',move);
  canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',abort);
  canvas.addEventListener('wheel',wheel,{passive:false});
  const observer=typeof ResizeObserver!=='undefined'?new ResizeObserver(draw):null;
  observer?.observe(canvas);
  draw();
  return {
    setScene(next){const changed=next?.sourceSha256!==scene?.sourceSha256;scene=next;
      if(changed)view=initialView();draw();},
    setSelection(ids){selected=new Set(ids);draw();},
    setMode(value){if(['select','pan','orbit'].includes(value))mode=value;draw();},
    setShowHelpers(value){showHelpers=!!value;draw();},
    setShowLabels(value){showLabels=!!value;draw();},
    zoom(factor){view.zoom=Math.max(.05,Math.min(50,view.zoom*factor));draw();},
    setPreset(preset){const camera={iso:[-.18,.08],top:[0,Math.PI/2-.01],
      front:[0,0],right:[Math.PI/2,0]}[preset];if(camera){[view.yaw,view.pitch]=camera;draw();}},
    fit(){view=initialView();draw();},
    focus(ids){const pts=[...ids].map(id=>scene?.byId.get(id)?.position).filter(Boolean);
      if(!pts.length)return;
      const middle={x:pts.reduce((s,p)=>s+p.x,0)/pts.length,
        y:pts.reduce((s,p)=>s+p.y,0)/pts.length,z:pts.reduce((s,p)=>s+p.z,0)/pts.length};
      const p=project(middle),{width,height}=size();
      view.panX+=width/2-p.x;view.panY+=height/2-p.y;draw();},
    getView(){return {...view};},
    dispose(){disposed=true;observer?.disconnect();
      canvas.removeEventListener('pointerdown',down);canvas.removeEventListener('pointermove',move);
      canvas.removeEventListener('pointerup',up);canvas.removeEventListener('pointercancel',abort);
      canvas.removeEventListener('wheel',wheel);},
  };
}
