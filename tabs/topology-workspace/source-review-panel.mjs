/** TOPO-A-P2 Source Review UI. Standalone evidence shelf; no Apply or repair imports. */
import {SOURCE_REVIEW_DECISIONS,canAddSourceReview,upsertSourceReview,
  editSourceReview,sourceReviewStatus,exportSourceReviewJSON,
  importSourceReviewJSON,exportSourceReviewCSV} from './source-review-queue.mjs';
const esc=v=>String(v??'').replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const friendly=d=>d.replaceAll('_',' ').toLowerCase();
export function mountSourceReviewPanel(reviewPanel,{getReview,getCurrentSha}){
  if(!reviewPanel)throw Error('SOURCE_REVIEW_PANEL_MISSING');
  let rows=[],message='Read-only evidence. Nothing in this queue can be applied to XML.';
  // Preserve unsaved form edits across unrelated workspace refreshes.
  let renderedRows=null,renderedSha=undefined;
  const add=document.createElement('button');
  add.type='button';add.dataset.sourceReviewAdd='';
  add.textContent='Add to Source Review';add.disabled=true;
  // DELIBERATE BEHAVIORAL RED: add a forbidden executable dataset key.
  add.dataset.queueApply='';
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
    '<label>Import Source Review JSON<input data-source-review-import type="file" accept=".json,application/json"></label>'+
    '</div><p data-source-review-status role="status" aria-live="polite"></p>'+
    '<div data-source-review-rows></div>';
  reviewPanel.insertAdjacentElement('afterend',panel);
  const container=panel.querySelector('[data-source-review-rows]');
  function eligible(){
    const result=getReview();
    return canAddSourceReview(result)&&result.sourceSha256===getCurrentSha();
  }
  function render(){
    add.disabled=!eligible();
    const sourceSha=getCurrentSha();
    panel.querySelector('[data-source-review-status]').textContent=
      rows.length+' review record(s) · '+message;
    if(rows===renderedRows&&sourceSha===renderedSha)return;
    renderedRows=rows;renderedSha=sourceSha;
    if(!rows.length){container.innerHTML='<p>No source review records yet.</p>';return;}
    container.innerHTML=rows.map((row,index)=>{
      const a=row.ports[0],b=row.ports[1],stale=sourceReviewStatus(row,getCurrentSha());
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
        ' · updated '+esc(row.updatedAt)+'</p>'+
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
      if(!eligible())throw Error('Choose two distinct exact source occurrences first.');
      const result=getReview();
      const outcome=upsertSourceReview(rows,result);
      rows=outcome.rows;
      message=outcome.inserted?'Exact pair added for design review.':
        'Existing unordered pair refreshed: disposition, distance and time updated; saved engineer decision and note preserved.';
    }catch(error){message=String(error?.message||error);}
    render();
  }
  function onQueueClick(event){
    const button=event.target.closest('button');if(!button||!panel.contains(button))return;
    event.preventDefault();event.stopPropagation();
    try{
      if(button.hasAttribute('data-source-review-save')){
        const owner=button.closest('[data-source-review-row]');
        const id=owner?.dataset.sourceReviewRow;
        const decision=owner.querySelector('[data-source-review-decision]').value;
        const note=owner.querySelector('[data-source-review-note]').value;
        rows=editSourceReview(rows,id,decision,note);
        message='Audit decision saved; no XML or executable queue change.';
      }else if(button.hasAttribute('data-source-review-export-json')){
        download(exportSourceReviewJSON(rows,getCurrentSha()),
          'source-review-queue.json','application/json');
        message='Review JSON exported; source and repair queues unchanged.';
      }else if(button.hasAttribute('data-source-review-export-csv')){
        download(exportSourceReviewCSV(rows,getCurrentSha()),
          'source-review-queue.csv','text/csv;charset=utf-8');
        message='Review CSV exported; source and repair queues unchanged.';
      }else return;
    }catch(error){message=String(error?.message||error);}
    render();
  }
  async function onQueueChange(event){
    if(!event.target.matches('[data-source-review-import]'))return;
    const input=event.target,file=input.files?.[0];
    if(!file)return;
    try{
      if(file.size>1048576)throw Error('SOURCE_REVIEW_IMPORT_SIZE');
      const outcome=importSourceReviewJSON(await file.text(),rows);
      rows=outcome.rows;message='Import: '+outcome.added+' new, '+outcome.updated+
        ' existing pair(s); unmatched source hashes remain STALE_SOURCE.';
    }catch(error){message='Import rejected: '+String(error?.message||error);}
    input.value='';render();
  }
  function onReviewChanged(event){
    // A <select> dispatches input BEFORE change. Re-rendering its option list on
    // input would detach the select before the P1 exact-source change handler runs.
    if(event.type==='input'&&event.target.matches('[data-review-choice]'))return;
    add.disabled=!eligible();
  }
  reviewPanel.addEventListener('click',onReviewClick);
  reviewPanel.addEventListener('input',onReviewChanged);
  reviewPanel.addEventListener('change',onReviewChanged);
  panel.addEventListener('click',onQueueClick);
  panel.addEventListener('change',onQueueChange);
  render();
  return {refresh:render,getRows:()=>rows.map(r=>({...r})),dispose(){
    reviewPanel.removeEventListener('click',onReviewClick);
    reviewPanel.removeEventListener('input',onReviewChanged);
    reviewPanel.removeEventListener('change',onReviewChanged);
    panel.removeEventListener('click',onQueueClick);
    panel.removeEventListener('change',onQueueChange);
    add.remove();panel.remove();
  }};
}
