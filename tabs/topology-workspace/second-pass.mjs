import {escapeValue as esc} from './occurrence-scene.mjs';

const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y,a.z-b.z);
export function connectionCandidates(scene,ports,sourceKey,search=''){
 const source=scene?.byKey.get(sourceKey),q=search.trim().toLowerCase();
 if(!source?.position)return [];
 return ports.filter(p=>p.key!==sourceKey&&!p.closed).map(p=>({
  ...p,record:scene.byKey.get(p.key)
 })).filter(p=>p.record?.position&&(!q||[p.key,p.ownerType,p.componentRefNo,p.record.branchName]
  .some(v=>String(v||'').toLowerCase().includes(q))))
  .map(p=>({...p,distanceMm:distance(source.position,p.record.position)}))
  .sort((a,b)=>a.distanceMm-b.distanceMm||a.key.localeCompare(b.key));
}
export function secondPassHTML(draft,scene,ports){
 if(!draft)return '';
 const rows=draft.witnessKeys.map(k=>({record:scene.byKey.get(k),port:ports.find(p=>p.key===k)}))
  .filter(r=>r.record?.position&&r.port&&!r.port.closed);
 const label=p=>p.key+' · '+p.ownerType+' · '+(p.componentRefNo||'no reference');
 const candidates=connectionCandidates(scene,ports,draft.sourceKey,draft.search);
 const selected=ports.find(p=>p.key===draft.peerKey);
 const options=candidates.slice(0,200);
 if(selected&&!options.some(p=>p.key===selected.key)){
  const full=connectionCandidates(scene,ports,draft.sourceKey).find(p=>p.key===selected.key);
  if(full)options.push(full);
 }
 const repair=draft.preview?.repair;
 return '<h3>Second pass · selected connection</h3><fieldset '+(draft.busy?'disabled':'')+'>'+
  '<p>Automatic closure remains ≤25 mm. Choose the exact intended connection for this separate pass.</p>'+
  (rows.length?'<label>Source port<select data-second-source>'+rows.map(({port})=>
   '<option value="'+esc(port.key)+'" '+(port.key===draft.sourceKey?'selected':'')+'>'+esc(label(port))+'</option>').join('')+'</select></label>':
   '<p>No qualified physical port belongs to this finding. Correct the owner/port definition in the authoring model, re-export and recheck.</p>')+
  '<label>Find partner by node, branch or component<input data-second-search type="search" value="'+esc(draft.search||'')+'"></label>'+
  '<label>Partner port · nearest first, actual 3D distance<select data-second-peer><option value="">Choose intended partner</option>'+
  options.map(p=>'<option value="'+esc(p.key)+'" '+(p.key===draft.peerKey?'selected':'')+'>'+esc(p.distanceMm.toFixed(3)+' mm · '+label(p))+'</option>').join('')+'</select></label>'+
  (candidates.length>200?'<p>Showing nearest 200 of '+candidates.length+' matches. Narrow the search or pick the exact port on the canvas.</p>':'')+
  '<div><button data-second-use-selection>Use canvas selection as partner</button><button data-second-locate>Focus both ports</button></div>'+
  '<label>Connection evidence / reason<input data-second-evidence maxlength="250" placeholder="Drawing, P&amp;ID or confirmed connection reason" value="'+esc(draft.evidence||'')+'"></label>'+
  '<button data-preview-second '+(!draft.sourceKey||!draft.peerKey||draft.busy?'disabled':'')+'>Preview second pass</button>'+
  '<p data-second-status role="status">'+esc(draft.status||'No movement approved. Preview leaves the working XML unchanged.')+'</p>'+
  (repair?'<div class="second-pass-preview"><strong>'+repair.distanceMm.toFixed(3)+' mm closure'+
   (repair.distanceMm>25?' · exceeds automatic tolerance':'')+'</strong><p>Move '+esc(repair.movePortKey)+' to fixed '+esc(repair.targetPortKey)+
   ' · displacement ['+repair.delta.map(v=>v.toFixed(3)).join(', ')+'] mm · '+repair.moveKeys.length+' affected record(s).</p>'+
   '<table><thead><tr><th>Source record</th><th>Before</th><th>After</th></tr></thead><tbody>'+
   draft.preview.changes.map(c=>'<tr><td>'+esc(c.sourceKey)+'</td><td>'+esc(c.before.Position.join(', '))+'<br>Node '+esc(c.before.NodeNumber)+
    '</td><td>'+esc(c.after.Position.join(', '))+'<br>Node '+esc(c.after.NodeNumber)+'</td></tr>').join('')+'</tbody></table>'+
   '<label><input data-second-confirm type="checkbox" '+(draft.confirmed?'checked':'')+'> These exact ports must connect; I approve the displayed movement.</label>'+
   '<button data-apply-second '+(!draft.confirmed||draft.evidence.trim().length<10||draft.busy?'disabled':'')+'>Apply second pass &amp; recheck</button></div>':'')+
  '<button data-cancel-second>Close second pass</button></fieldset>';
}
