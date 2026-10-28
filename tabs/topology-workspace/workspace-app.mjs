/** XML229 WP1: standalone source-only topology inspection; no engineering acceptance. */
import {runXmlCii2019StandaloneEngineJob} from '../xml-cii-2019-standalone/xml-cii-workflow-engine-client.js';
import {parseOccurrenceScene, affectedOccurrenceIds, escapeValue as esc} from './occurrence-scene.mjs';
import {createTopologyCanvas} from './projected-canvas.mjs';

async function sha256(bytes) {
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  return Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');
}
const query=(root,selector)=>root.querySelector(selector);
const getNodes=(root,selector)=>[...root.querySelectorAll(selector)];
function inspectRecord(record) {
  const facts=[
    ['Source key',record.key],['Branch',record.branchName],['Branch ordinal',record.branchOrdinal],
    ['Node ordinal',record.nodeOrdinal],['NodeNumber label',record.nodeNumberRaw || '(empty)'],
    ['NodeName',record.nodeName],['Component',record.type],['ComponentRefNo',record.refNo],
    ['Endpoint',record.endpoint],['Connection',record.connectionType],
    ['XYZ',record.position?Object.values(record.position).join(' / '):'NO POSITION'],
    ['Support reference',record.support?'Yes':'No'],['Restraint',record.restraint?'Present':'Not found'],
    ['Source Weight (not Final)',record.weight || '(blank)'],
  ];
  return '<dl>'+facts.map(([name,value])=>'<dt>'+esc(name)+'</dt><dd>'+esc(value)+'</dd>').join('')+
    '</dl><h3>Occurrence XML (DOM-serialized; not original bytes)</h3><pre>'+esc(record.xmlFragment)+'</pre>';
}
function recordButton(record,selected) {
  const name=record.nodeNumberRaw || '(no label)';
  return '<button data-occ-id="'+esc(record.id)+'" aria-selected="'+selected.has(record.id)+'">'+
    esc(name+' · '+record.type)+'<small>'+esc(record.branchName+' · B'+record.branchOrdinal+
    ' / N'+record.nodeOrdinal+(record.position?'':' · NO POSITION'))+'</small></button>';
}
function actionButton(action) {
  const blocked=action.status==='BLOCKED'||(action.blockers||[]).length>0;
  return '<button data-action-id="'+esc(action.action_id)+'"><strong>'+esc(action.action_id)+
    '</strong> · '+esc(action.disposition)+'<small>'+esc((blocked?'BLOCKED · ':'')+
    (action.message||action.branch_name||'No narrative supplied'))+'</small></button>';
}
export function mountTopologyWorkspace(root, {runEngine=runXmlCii2019StandaloneEngineJob}={}) {
  if(!root)throw Error('Topology workspace root is required');
  const state={epoch:0,source:null,scene:null,plan:null,findings:[],result:null,
    selected:new Set(),search:'',busy:false};
  const canvas=createTopologyCanvas(query(root,'[data-canvas]'),onHits);
  const updateStatus=message=>{query(root,'[data-status]').textContent=message;};
  const displayMessage=message=>{query(root,'[data-hits]').textContent=message;};
  function renderSelection() {
    const ids=[...state.selected],records=ids.map(id=>state.scene?.byId.get(id)).filter(Boolean);
    query(root,'[data-selection]').textContent=records.length?
      records.length+' source occurrence(s) selected':'Choose a node on the canvas or in the occurrence list.';
    query(root,'[data-inspector]').innerHTML=records[0]?inspectRecord(records[0]):'';
    canvas.setSelection(ids);
  }
  function renderRecords() {
    const panel=query(root,'[data-occurrences]'),summary=query(root,'[data-occ-summary]');
    const q=state.search.toLowerCase();
    const matching=(state.scene?.records||[]).filter(r=>[
      r.nodeNumberRaw,r.nodeName,r.branchName,r.type,r.refNo,r.key
    ].some(value=>String(value||'').toLowerCase().includes(q)));
    summary.textContent=state.scene?matching.length+' of '+state.scene.records.length+
      ' source occurrences (including non-route helpers)':'Load XML to inspect every source record.';
    panel.innerHTML=matching.slice(0,350).map(r=>recordButton(r,state.selected)).join('')+
      (matching.length>350?'<p>Showing first 350 matches. Narrow the search.</p>':'');
  }
  function renderActions() {
    const actions=state.plan?.actions||[];
    const keep=actions.filter(a=>a.disposition==='KEEP');
    const shown=actions.filter(a=>a.disposition!=='KEEP');
    const blocked=shown.filter(a=>a.status==='BLOCKED'||a.blockers?.length);
    const summary=query(root,'[data-plan-summary]');
    summary.textContent=state.plan?actions.length+' total · '+keep.length+
      ' KEEP (unchanged) · '+blocked.length+' blocked/exception · '+shown.length+
      ' visible non-KEEP actions. All entries are read-only.':'Real engine findings appear after analysis. KEEP is summarized.';
    const q=state.search.toLowerCase();
    const matches=shown.filter(a=>[a.action_id,a.disposition,a.message,a.branch_name,
      ...(a.node_numbers||[]),...(a.component_ref_nos||[])].some(v=>
      String(v||'').toLowerCase().includes(q)));
    query(root,'[data-issues]').innerHTML=matches.slice(0,250).map(actionButton).join('')+
      (matches.length>250?'<p>Showing first 250 actions; narrow the search.</p>':'');
  }
  function refresh() {
    renderRecords();renderActions();renderSelection();
    query(root,'[data-analyze]').disabled=!state.source||state.busy;
    query(root,'[data-cancel]').disabled=!state.busy;
  }
  function select(ids,add=false) {
    if(!add)state.selected.clear();
    for(const id of ids) {
      if(!state.scene?.byId.has(id))continue;
      if(add&&state.selected.has(id))state.selected.delete(id);
      else state.selected.add(id);
    }
    renderRecords();renderSelection();
  }
  function onHits(hits,add) {
    if(hits.length===1){select([hits[0].id],add);displayMessage('');return;}
    if(!hits.length){displayMessage('No visible source occurrence at this point.');return;}
    query(root,'[data-hits]').innerHTML='<strong>Coincident / overlapping records: choose exact occurrence</strong>'+
      hits.slice(0,50).map(record=>'<button data-hit-id="'+esc(record.id)+'">'+
        esc((record.nodeNumberRaw||'(empty)')+' · B'+record.branchOrdinal+
        '/N'+record.nodeOrdinal+' · '+record.type)+'</button>').join('')+
      (hits.length>50?'… More than 50 hits; use text search.':'');
  }
  async function load(file) {
    const generation=++state.epoch;
    state.source=null;state.scene=null;state.plan=null;state.findings=[];state.result=null;
    state.selected.clear();state.busy=false;canvas.setScene(null);
    query(root,'[data-source-meta]').textContent='Reading '+file.name+'…';
    displayMessage('');refresh();
    try {
      const raw=new Uint8Array(await file.arrayBuffer());
      const sourceText=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(raw);
      const sourceSha256=await sha256(new TextEncoder().encode(sourceText));
      const rawSha256=await sha256(raw);
      if(generation!==state.epoch)return;
      const scene=parseOccurrenceScene(sourceText,sourceSha256);
      if(!scene.records.some(r=>r.position))throw Error('No explicit XYZ source positions available');
      state.source={sourceText,sourceSha256,rawSha256,name:file.name};
      state.scene=scene;canvas.setScene(scene);
      query(root,'[data-source-meta]').textContent=file.name+' · '+scene.branches.length+
        ' branches · '+scene.records.length+' original occurrences · text SHA256 '+sourceSha256+
        (rawSha256!==sourceSha256?' · raw bytes differ':'');
      updateStatus('Source loaded. Geometry is for inspection; select Analyze for real PSI116 findings.');
    } catch(error) {
      if(generation!==state.epoch)return;
      updateStatus('Source rejected: '+(error?.message||String(error)));
      query(root,'[data-source-meta]').textContent='No admissible source';
    }
    refresh();
  }
  async function analyze() {
    if(!state.source||state.busy)return;
    const generation=state.epoch,source=state.source;state.busy=true;
    state.plan=null;state.findings=[];refresh();updateStatus('Running authoritative PSI116 topology analysis…');
    try {
      const result=await runEngine({sourceKind:'xml',sourceText:source.sourceText,
        sourceName:source.name,topologyPreFinalOnly:true,
        options:{outputMode:'enriched-only',analyzeTopology:true,generateTopoFix:false,
          useTopoFixForCii:false,topologyActionIds:[]}});
      if(generation!==state.epoch)return;
      if(result?.ok!==true||result.outputKind!=='topology-sidecars'||
          result.ciiText||result.acceptedFinalTransferred!==false||
          result.nativeCiiReleaseAuthorized!==false||result.topoFixCommitted===true||
          result.topoFixXmlText)
        throw Error(result?.error||'Topology-only engine contract rejected');
      const plan=JSON.parse(result.topologyFixPlanText||'null');
      const findings=JSON.parse(result.topologyFindingsText||'null');
      if(plan?.source?.sha256!==source.sourceSha256||
         findings?.source?.sha256!==source.sourceSha256)
        throw Error('TOPOFIX_PLAN_SOURCE_DRIFT');
      if(!Array.isArray(plan.actions)||!Array.isArray(findings.findings))
        throw Error('PSI116 sidecar structure invalid');
      state.plan=plan;state.findings=findings.findings;state.result=result;
      updateStatus('Authoritative topology analysis complete. '+plan.actions.length+
        ' plan entries. No Weight/O1/Final/native session was supplied or created.');
    } catch(error) {
      if(generation===state.epoch)updateStatus('Topology analysis failed: '+(error?.message||String(error)));
    } finally {
      if(generation===state.epoch){state.busy=false;refresh();}
    }
  }
  const click=event=>{
    const target=event.target.closest('button');if(!target||!root.contains(target))return;
    if(target.hasAttribute('data-analyze'))analyze();
    else if(target.hasAttribute('data-cancel')){state.epoch++;state.busy=false;refresh();
      updateStatus('Pending analysis result invalidated. Original source remains available.');}
    else if(target.hasAttribute('data-occ-id')){select([target.dataset.occId],event.shiftKey);displayMessage('');}
    else if(target.hasAttribute('data-hit-id')){select([target.dataset.hitId],event.shiftKey);displayMessage('');}
    else if(target.hasAttribute('data-action-id')){
      const action=state.plan?.actions.find(a=>a.action_id===target.dataset.actionId);
      const ids=affectedOccurrenceIds(action,state.findings,state.scene);
      if(ids.length){select(ids);canvas.focus(ids);displayMessage('Source-qualified action witnesses: '+ids.length);}
      else displayMessage('No authoritative original node_keys for this action; no guessed match.');
    }
    else if(target.hasAttribute('data-mode')){
      getNodes(root,'[data-mode]').forEach(el=>el.setAttribute('aria-pressed',
        String(el===target)));canvas.setMode(target.dataset.mode);
    }
    else if(target.hasAttribute('data-view'))canvas.setPreset(target.dataset.view);
    else if(target.hasAttribute('data-zoom'))canvas.zoom(Number(target.dataset.zoom));
    else if(target.hasAttribute('data-fit'))canvas.fit();
    else if(target.hasAttribute('data-focus'))canvas.focus(state.selected);
  };
  const changed=event=>{
    if(event.target.matches('[data-file]')&&event.target.files?.[0])load(event.target.files[0]);
    if(event.target.matches('[data-helpers]'))canvas.setShowHelpers(event.target.checked);
    if(event.target.matches('[data-labels]'))canvas.setShowLabels(event.target.checked);
  };
  const input=event=>{
    if(event.target.matches('[data-search]')){state.search=event.target.value.trim();renderRecords();renderActions();}
  };
  root.addEventListener('click',click);root.addEventListener('change',changed);
  root.addEventListener('input',input);refresh();
  return {getState:()=>({sourceSha256:state.source?.sourceSha256||null,
    occurrences:state.scene?.records.length||0,actions:state.plan?.actions.length||0,
    selected:[...state.selected],busy:state.busy}),load,analyze,
    dispose(){state.epoch++;canvas.dispose();root.removeEventListener('click',click);
      root.removeEventListener('change',changed);root.removeEventListener('input',input);}};
}
const root=document.querySelector('#xml229-topology-workspace');
if(root)mountTopologyWorkspace(root);
