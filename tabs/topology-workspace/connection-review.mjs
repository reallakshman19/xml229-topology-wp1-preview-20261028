/** Read-only exact-source connection search. No topology or execution authority. */
const esc = value => String(value ?? '').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const keyOf = r => r?.key || '';
const numberQuery = value => {
  const s = String(value ?? '').trim();
  return /^-?\d+$/.test(s) && Number.isSafeInteger(Number(s)) ? Number(s) : null;
};
const fixed = value => Number.isFinite(value) ? value.toFixed(3) : 'UNKNOWN';
const sourceRecord = r => r.branchName + ' · B' + r.branchIndex + '/S' + r.sourceIndex +
  ' · ' + r.key + ' · ' + r.type + ' / ' + (r.refNo || 'NO REF') +
  ' / endpoint ' + (r.endpoint || 'UNKNOWN') +
  ' · source declaration ' + (r.connectionType || 'NONE');

export function resolveConnectionReview(scene, manualPorts, witnesses, evidenceAvailable,
                                         numberA, numberB, choiceA='', choiceB='') {
  const records=scene?.records || [];
  const matching = query => {
    const n=numberQuery(query);
    return n===null ? [] : records.filter(r=>r.nodeNumber===n);
  };
  const occurrencesA=matching(numberA),occurrencesB=matching(numberB);
  const choose=(matches,key)=>matches.length===1 ? matches[0] :
    matches.find(r=>r.key===key) || null;
  const a=choose(occurrencesA,choiceA),b=choose(occurrencesB,choiceB);
  const ports=new Map((manualPorts||[]).map(p=>[p.key,p]));
  const evidence=!!evidenceAvailable && Array.isArray(witnesses) &&
    witnesses.every(w=>w.sourceSha256===scene?.sourceSha256);
  const details=r=>{
    if(!r)return null;
    const witness=evidence?witnesses.filter(w=>w.sourceKey===r.key):[];
    const port=ports.get(r.key)||null;
    const bound=witness.filter(w=>w.rowKind==='PORT'&&w.bindingStatus==='BOUND');
    const declarations=bound.flatMap(w=>w.closureDeclarations||[]);
    const declarationKeys=[...new Set(declarations.map(d=>d.sourceKey).filter(Boolean))];
    const rawClos=String(r.connectionType||'').toUpperCase()==='CLOS';
    const blocked=rawClos || port?.closed===true || bound.length>0 ||
      witness.some(w=>w.bindingStatus==='EVIDENCE_UNAVAILABLE');
    return {record:r,sourceKey:r.key,portQualified:!!port || bound.length>0,
      bindingStatus:!evidence?'EVIDENCE_UNAVAILABLE':
        bound.length?'BOUND':witness.some(w=>w.bindingStatus==='EVIDENCE_UNAVAILABLE')?
          'EVIDENCE_UNAVAILABLE':witness.some(w=>w.bindingStatus==='UNQUALIFIED')?
          'UNQUALIFIED':'NO_BOUND_WITNESS',
      rawClos,blocked,declarationKeys,declarations,
      outsideDiameter:r.outsideDiameter ?? port?.outsideDiameter ?? null,
      wallThickness:r.wallThickness ?? null};
  };
  const first=details(a),second=details(b);
  let disposition='SOURCE_REVIEW_REQUIRED',vector=null,distanceMm=null;
  if(!scene) disposition='NO_SOURCE';
  else if(!String(numberA).trim()||!String(numberB).trim()) disposition='MISSING_INPUT';
  else if(numberQuery(numberA)===null||numberQuery(numberB)===null) disposition='INVALID_NODE_NUMBER';
  else if(!occurrencesA.length||!occurrencesB.length) disposition='MISSING_OCCURRENCE';
  else if(!a||!b) disposition='AMBIGUOUS_PORT';
  else if(a.key===b.key) disposition='SAME_SOURCE_OCCURRENCE';
  else if(!a.position||!b.position) disposition='MISSING_POSITION';
  else {
    vector={x:b.position.x-a.position.x,y:b.position.y-a.position.y,
      z:b.position.z-a.position.z};
    distanceMm=Math.hypot(vector.x,vector.y,vector.z);
    if(!evidence)disposition='SOURCE_UNVERIFIED';
    else if(first.blocked||second.blocked)disposition='SOURCE_REVIEW_REQUIRED'; // DELIBERATE MUTANT, must be restored
    else if(!first.portQualified||!second.portQualified)disposition='HELPER_ONLY_ENDPOINT';
  }
  return {status:'REVIEW ONLY',disposition,occurrencesA,occurrencesB,
    a,b,first,second,vector,distanceMm,evidence,sourceSha256:scene?.sourceSha256||null};
}

function choiceHTML(which,occurrences,selected) {
  if(occurrences.length<2)return '';
  return '<label>Exact occurrence '+which+' (required; no nearest-port default)'+
    '<select data-review-choice="'+which+'"><option value="">Choose branch / source key</option>'+
    occurrences.map(r=>'<option value="'+esc(r.key)+'" '+(r.key===selected?'selected':'')+'>'+
      esc(sourceRecord(r))+'</option>').join('')+'</select></label>';
}
function listHTML(which,occurrences) {
  if(!occurrences.length)return '<p>Node '+which+': no matching source occurrence.</p>';
  return '<div class="topo-review-list"><strong>Node '+which+' · '+occurrences.length+
    ' exact source occurrence(s)</strong><ul>'+occurrences.map(r=>
      '<li>'+esc(sourceRecord(r))+' · XYZ '+esc(r.position?
        [r.position.x,r.position.y,r.position.z].map(fixed).join(' / '):'NO POSITION')+
      '</li>').join('')+'</ul></div>';
}
function detailHTML(which,detail) {
  if(!detail)return '';
  const r=detail.record;
  const declarations=detail.declarations.map(d=>d.sourceKey+
    ' ('+(d.bindingKinds||[]).join(', ')+')').join('; ');
  return '<p><strong>Port '+which+':</strong> '+esc(sourceRecord(r))+
    ' · OD '+esc(fixed(detail.outsideDiameter))+' mm · wall '+
    esc(fixed(detail.wallThickness))+' mm · CLOS binding '+
    esc(detail.bindingStatus)+' · authority declaration source key(s): '+
    esc(declarations||detail.declarationKeys.join(', ')||
      (detail.rawClos?r.key+' (raw CLOS; binding unconfirmed)':'NONE SHOWN'))+
    (detail.portQualified?'':' · helper/unqualified port; not eligible for pairing')+'</p>';
}
export function reviewConnectionHTML(result) {
  const {disposition,occurrencesA,occurrencesB,first,second,vector,distanceMm}=result;
  const directions={
    NO_SOURCE:'Load a PSI116 XML file. No source occurrence is selected.',
    MISSING_INPUT:'Enter both exact Node Numbers. Search includes CLOS and non-route records.',
    INVALID_NODE_NUMBER:'Enter complete integer Node Numbers, not partial text.',
    MISSING_OCCURRENCE:'One or both Node Numbers are absent; check branch and source export.',
    AMBIGUOUS_PORT:'Duplicate Node Numbers: choose a specific branch / source key for each side.',
    SAME_SOURCE_OCCURRENCE:'Both entries refer to the same exact source record.',
    MISSING_POSITION:'One endpoint has no readable 3D Position; no distance can be claimed.',
    SOURCE_UNVERIFIED:'CLOS evidence unavailable or stale. Analyze this exact source; do not infer an open port.',
    HELPER_ONLY_ENDPOINT:'Selected helper or unqualified endpoint is not a verified physical port. Review source ownership upstream.',
    CONFLICTS_WITH_CLOS:'CONFLICTS_WITH_CLOS: source-declared closure forbids joining. Correct the upstream CAD/piping design under engineering authority, re-export, then reimport and reanalyze.',
    SOURCE_REVIEW_REQUIRED:'This is a visual hypothesis only. Confirm source and design intent upstream before any executable workflow.'
  };
  return '<p class="topo-review-status"><strong>REVIEW ONLY · '+esc(disposition)+'</strong></p>'+
    '<p>'+esc(directions[disposition])+'</p>'+
    listHTML('A',occurrencesA)+listHTML('B',occurrencesB)+
    detailHTML('A',first)+detailHTML('B',second)+
    (vector?'<p><strong>Exact selected pair · 3D distance '+fixed(distanceMm)+
      ' mm</strong> · vector B−A (ΔX / ΔY / ΔZ) '+[vector.x,vector.y,vector.z].map(fixed).join(' / ')+
      ' mm. Canvas dashed line is PROPOSAL / REVIEW ONLY, never a solver edge.</p>':'')+
    '<p>Cannot Apply or Queue this review pair. Source XML, topology fix plan and tolerances are unchanged.</p>';
}

export function mountConnectionReview(panel,{getContext,highlight}) {
  if(!panel)throw Error('Find / Review Connection panel absent');
  let choiceA='',choiceB='',lastHighlights='';
  const inputA=panel.querySelector('[data-review-query="a"]');
  const inputB=panel.querySelector('[data-review-query="b"]');
  function render(){
    const {scene,manualPorts,witnesses,evidenceAvailable}=getContext();
    const result=resolveConnectionReview(scene,manualPorts,witnesses,evidenceAvailable,
      inputA.value,inputB.value,choiceA,choiceB);
    panel.querySelector('[data-review-choices]').innerHTML=
      choiceHTML('a',result.occurrencesA,choiceA)+choiceHTML('b',result.occurrencesB,choiceB);
    panel.querySelector('[data-review-result]').innerHTML=reviewConnectionHTML(result);
    const ids=result.a&&result.b&&result.a.key!==result.b.key&&
      result.a.position&&result.b.position?[result.a.id,result.b.id]:[];
    const key=(result.sourceSha256||'')+'|'+ids.join('|');
    if(key!==lastHighlights){lastHighlights=key;highlight(ids);}
    return result;
  }
  const onInput=event=>{
    if(event.target===inputA){choiceA='';render();}
    else if(event.target===inputB){choiceB='';render();}
  };
  const onChange=event=>{
    if(event.target.matches('[data-review-choice="a"]')){choiceA=event.target.value;render();}
    if(event.target.matches('[data-review-choice="b"]')){choiceB=event.target.value;render();}
  };
  panel.addEventListener('input',onInput);panel.addEventListener('change',onChange);
  render();
  return {refresh:render,reset(){
    inputA.value='';inputB.value='';choiceA='';choiceB='';lastHighlights='';
    highlight([]);render();
  },dispose(){panel.removeEventListener('input',onInput);panel.removeEventListener('change',onChange);}};
}
