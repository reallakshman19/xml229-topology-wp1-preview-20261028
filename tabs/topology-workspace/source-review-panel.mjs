/** TOPO-A-P2-UX: evidence-only shelf, isolated from all repair queues. */
import {SOURCE_REVIEW_DECISIONS,canAddSourceReview,upsertSourceReview,
  editSourceReview,sourceReviewStatus,exportSourceReviewJSON,
  importSourceReviewJSON,exportSourceReviewCSV,loadSourceReviewStorage,
  saveSourceReviewStorage,clearSourceReviewStorage} from './source-review-queue.mjs';

const esc=v=>String(v??'').replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const friendly=d=>d.replaceAll('_',' ').toLowerCase();
const STORAGE_WARNING='Queue not saved in this browser; export to keep it';

export function mountSourceReviewPanel(reviewPanel,{getReview,getCurrentSha,
  getStorage=()=>globalThis.localStorage}){
  if(!reviewPanel)throw Error('SOURCE_REVIEW_PANEL_MISSING');
  let rows=[],message='Read-only evidence. Nothing in this queue can be applied to XML.';
  let activeSha=null,storageWarning='';
  let renderedRows=null,renderedSha=undefined;
  const add=document.createElement('button');
  add.type='button';add.dataset.sourceReviewAdd='';
  add.textContent='Add to Source Review';add.disabled=true;
  reviewPanel.appendChild(add);
  const panel=document.createElement('section');
  panel.dataset.sourceReviewQueue='';
  panel.className='topo-group topo-source-review';
  panel.setAttribute('aria-label','Source Review Queue · evidence only');
  panel.innerHTML='<h2>Source Review Queue · evidence only</h2>'+
    '<p>Audit decisions only, never approval to Apply or enter the Manual Fix Queue. '+
    'Correct in the upstream CAD/design source, then reimport.</p>'+
    '<div class="topo-source-review-toolbar">'+
    '<button type="button" data-source-review-export-json>Export JSON</button>'+
    '<button type="button" data-source-review-export-csv>Export CSV</button>'+
    '<button type="button" data-source-review-clear>Clear queue for this file</button>'+
    '<label>Import Source Review JSON<input data-source-review-import type="file" accept=".json,application/json"></label>'+
    '</div><p data-source-review-status role="status" aria-live="polite"></p>'+
    '<p data-source-review-storage-status role="status" aria-live="polite"></p>'+
    '<div data-source-review-rows></div>';
  reviewPanel.insertAdjacentElement('afterend',panel);
  const container=panel.querySelector('[data-source-review-rows]');

  function sourceChanged(){
    const next=getCurrentSha();
    if(next===activeSha)return;
    activeSha=next;
    rows=[];
    storageWarning='';
    if(next){
      try{rows=loadSourceReviewStorage(getStorage(),next);}
      catch(error){storageWarning=STORAGE_WARNING;}
    }
    renderedRows=null;
    message=rows.length?'Restored '+rows.length+' review record(s) for this source SHA.':
      'No saved source reviews for this file. XML unchanged.';
  }
  function persist(){
    if(!activeSha)return;
    try{saveSourceReviewStorage(getStorage(),activeSha,rows);storageWarning='';}
    catch(error){storageWarning=STORAGE_WARNING;}
  }
  function status(){
    panel.querySelector('[data-source-review-status]').textContent=
      rows.length+' review record(s) · '+message;
    panel.querySelector('[data-source-review-storage-status]').textContent=storageWarning;
  }
  function eligible(){
    const result=getReview();
    return canAddSourceReview(result)&&result.sourceSha256===getCurrentSha();
  }
  function render(){
    sourceChanged();
    add.disabled=!eligible();
    status();
    if(rows===renderedRows&&activeSha===renderedSha)return;
    renderedRows=rows;renderedSha=activeSha;
    if(!rows.length){container.innerHTML='<p>No source review records yet.</p>';return;}
    container.innerHTML=rows.map((row,index)=>{
      const a=row.ports[0],b=row.ports[1],stale=sourceReviewStatus(row,activeSha);
      return '<article class="topo-source-review-row" data-source-review-row="'+esc(row.id)+'">'+
        '<p><strong>Record '+(index+1)+' · '+esc(stale)+'</strong></p>'+
        '<p>Pair: '+esc(a.sourceKey)+' ↔ '+esc(b.sourceKey)+
        '<small>'+esc(a.branch)+' · Node '+esc(a.nodeNumber)+' · endpoint '+esc(a.endpoint)+
        ' · owner '+esc(a.owner.componentType)+'/'+esc(a.owner.refNo)+
        ' | '+esc(b.branch)+' · Node '+esc(b.nodeNumber)+' · endpoint '+esc(b.endpoint)+
        ' · owner '+esc(b.owner.componentType)+'/'+esc(b.owner.refNo)+'</small></p>'+
        '<p>Source SHA256: <code>'+esc(row.sourceSha256)+'</code></p>'+
        '<p>Disposition: '+esc(row.disposition)+' · distance '+
        esc(row.distanceMm===null?'UNKNOWN':row.distanceMm.toFixed(3)+' mm')+
        ' · updated <span data-source-review-updated>'+esc(row.updatedAt)+'</span></p>'+
        '<label>Engineer decision<select data-source-review-decision>'+
        SOURCE_REVIEW_DECISIONS.map(d=>'<option value="'+esc(d)+'" '+
          (d===row.decision?'selected':'')+'>'+esc(friendly(d))+'</option>').join('')+
        '</select></label>'+
        '<label>Optional design note<textarea rows="2" data-source-review-note maxlength="4000">'+
          esc(row.note)+'</textarea></label>'+
        '<button type="button" data-source-review-save>Save audit decision</button>'+
        '</article>';
    }).join('');
  }
  // Input/change immediately commits the audit-only record; do not re-render
  // its controls while typing (preserve focus/caret).
  function commitEditor(owner){
    if(!owner)return;
    const id=owner.dataset.sourceReviewRow;
    const current=rows.find(row=>row.id===id);
    if(!current)return;
    const decision=owner.querySelector('[data-source-review-decision]').value;
    const note=owner.querySelector('[data-source-review-note]').value;
    if(current.decision===decision&&current.note===note)return;
    rows=editSourceReview(rows,id,decision,note);
    renderedRows=rows;
    persist();
    owner.querySelector('[data-source-review-updated]').textContent=rows.find(row=>row.id===id).updatedAt;
    message='Engineer decision and note saved automatically; source XML unchanged.';
    status();
  }
  function flushEditors(){
    for(const owner of container.querySelectorAll('[data-source-review-row]'))commitEditor(owner);
  }
  function download(text,filename,mime){
    const url=URL.createObjectURL(new Blob([text],{type:mime}));
    const link=document.createElement('a');link.href=url;link.download=filename;
    document.body.appendChild(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function onReviewClick(event){
    if(!event.target.closest('[data-source-review-add]'))return;
    event.preventDefault();event.stopPropagation();
    try{
      sourceChanged();
      flushEditors();
      if(!eligible())throw Error('Choose two distinct exact source occurrences first.');
      const outcome=upsertSourceReview(rows,getReview());
      rows=outcome.rows;persist();
      message=outcome.inserted?'Exact pair added for design review.':
        'Existing unordered pair refreshed: disposition, distance and time updated; saved engineer decision and note preserved.';
    }catch(error){message=String(error?.message||error);}
    render();
  }
  function onQueueClick(event){
    const button=event.target.closest('button');if(!button||!panel.contains(button))return;
    event.preventDefault();event.stopPropagation();
    try{
      sourceChanged();
      flushEditors();
      if(button.hasAttribute('data-source-review-save')){
        message='Engineer decision and note are saved automatically; no XML or executable queue change.';
      }else if(button.hasAttribute('data-source-review-clear')){
        if(!activeSha)return;
        if(!globalThis.confirm('Clear Source Review Queue for this file? No XML changes.'))return;
        rows=[];
        try{clearSourceReviewStorage(getStorage(),activeSha);storageWarning='';}
        catch(error){storageWarning=STORAGE_WARNING;}
        message='Source Review Queue cleared for this file; XML unchanged.';
      }else if(button.hasAttribute('data-source-review-export-json')){
        download(exportSourceReviewJSON(rows,activeSha),
          'source-review-queue.json','application/json');
        message='Review JSON exported; source and repair queues unchanged.';
      }else if(button.hasAttribute('data-source-review-export-csv')){
        download(exportSourceReviewCSV(rows,activeSha),
          'source-review-queue.csv','text/csv;charset=utf-8');
        message='Review CSV exported; source and repair queues unchanged.';
      }else return;
    }catch(error){message=String(error?.message||error);}
    render();
  }
  async function onQueueImport(event){
    if(!event.target.matches('[data-source-review-import]'))return;
    const input=event.target,file=input.files?.[0];
    if(!file)return;
    try{
      sourceChanged();flushEditors();
      if(file.size>1048576)throw Error('SOURCE_REVIEW_IMPORT_SIZE');
      const outcome=importSourceReviewJSON(await file.text(),rows);
      rows=outcome.rows;persist();
      message='Import: '+outcome.added+' new, '+outcome.updated+
        ' existing pair(s); different source hashes remain STALE_SOURCE.';
    }catch(error){message='Import rejected: '+String(error?.message||error);}
    input.value='';render();
  }
  function onQueueInput(event){
    if(event.target.matches('[data-source-review-note]'))
      commitEditor(event.target.closest('[data-source-review-row]'));
  }
  function onQueueChanged(event){
    if(event.target.matches('[data-source-review-decision]'))
      commitEditor(event.target.closest('[data-source-review-row]'));
    if(event.target.matches('[data-source-review-import]'))void onQueueImport(event);
  }
  function onReviewChanged(event){
    // Do not detach P1 exact-source select before its change handler runs.
    if(event.type==='input'&&event.target.matches('[data-review-choice]'))return;
    add.disabled=!eligible();
  }
  reviewPanel.addEventListener('click',onReviewClick);
  reviewPanel.addEventListener('input',onReviewChanged);
  reviewPanel.addEventListener('change',onReviewChanged);
  panel.addEventListener('click',onQueueClick);
  panel.addEventListener('input',onQueueInput);
  panel.addEventListener('change',onQueueChanged);
  render();
  return {refresh:render,getRows:()=>{sourceChanged();flushEditors();return rows.map(r=>({...r}));},
    dispose(){
      reviewPanel.removeEventListener('click',onReviewClick);
      reviewPanel.removeEventListener('input',onReviewChanged);
      reviewPanel.removeEventListener('change',onReviewChanged);
      panel.removeEventListener('click',onQueueClick);
      panel.removeEventListener('input',onQueueInput);
      panel.removeEventListener('change',onQueueChanged);
      add.remove();panel.remove();
    }};
}
