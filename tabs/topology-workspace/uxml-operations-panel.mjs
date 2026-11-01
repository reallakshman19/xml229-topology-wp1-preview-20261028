/** Read-only UXML Operations preview controller.
 * No mutation/approval/queue action exists in this module. All text is
 * escaped; exports contain only displayed operation fields.
 */
import {filterOperationRows,kindCounts,visibleOperationExport,operationsCSV} from './uxml-operations-view.mjs';
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
})[ch]);
const label=value=>value==null?'(absent)':String(value);
const query=(root,selector)=>root.querySelector(selector);

export function createOperationsPreviewPanel(root,{snapshot,onLocate,onReview}){
  const panel=query(root,'[data-ops-panel]');
  if(!panel)throw Error('UXML_OPERATIONS_PANEL_MISSING');
  let kind='all',search='';
  function ready(state){
    return state.hubEnabled&&state.parity?.status==='EQUAL'&&
      state.preview&&state.proof===true&&!state.busy;
  }
  function render(){
    const state=snapshot();
    panel.hidden=!state.hubEnabled;
    if(!state.hubEnabled)return;
    const applicable=ready(state);
    const status=state.parity?.status||'NOT_CHECKED';
    const summary=query(panel,'[data-ops-summary]');
    const why=query(panel,'[data-ops-status]');
    const rows=query(panel,'[data-ops-rows]');
    const select=query(panel,'[data-ops-kind]');
    const searchBox=query(panel,'[data-ops-search]');
    panel.dataset.opsState=status;
    query(panel,'[data-ops-review-count]').textContent=String(state.reviewOnlyCount||0);
    for(const b of panel.querySelectorAll('[data-ops-json],[data-ops-csv]'))
      b.disabled=!applicable;
    if(!applicable){
      summary.textContent='No operations applicable to this preview state.';
      why.textContent=['DIFFERENT','UNAVAILABLE'].includes(status)?
        status+' · '+(state.parity?.differences||[]).join(' | ')+
        ' · No operations applicable or exportable.':
        status==='EQUAL'&&state.previewError?
          'Preview unavailable: '+state.previewError+
          ' · Hub Auto-fix parity remains EQUAL; the operation disclosure is unavailable.':
        status==='EQUAL'?'Source custody / operations preview not ready; re-analyse.':
        'Select Analyze to compare the original PSI116 with pinned UXML.';
      rows.textContent='';
      select.innerHTML='<option value="all">All kinds</option>';
      select.disabled=true;searchBox.disabled=true;
      return;
    }
    const data=state.preview,counts=kindCounts(data);
    select.disabled=false;searchBox.disabled=false;
    if(!counts.some(item=>item.kind===kind))kind='all';
    select.innerHTML='<option value="all">All kinds</option>'+
      counts.map(item=>'<option value="'+esc(item.kind)+'">'+
        esc(item.name)+' ('+item.count+')</option>').join('');
    select.value=kind;
    const filtered=filterOperationRows(data,{kind,search});
    const kinds=counts.map(item=>item.name+': '+item.count).join(' · ');
    summary.textContent=data.summary.totalOps+' operation(s) · '+(kinds||'no kinds')+
      ' · '+data.summary.untouchedRecordCount+' untouched original source records'+
      ' · '+state.reviewOnlyCount+' Source Review Queue case(s) (never operations)';
    why.textContent=filtered.length+' of '+data.summary.totalOps+
      ' operation(s) shown. Proposals require separate native validation before any Apply.';
    rows.innerHTML=filtered.map(op=>
      '<article class="uxml-op-row" data-op-id="'+esc(op.opId)+'">'+
        '<h3><span class="uxml-op-badge">'+esc(op.kindName)+'</span> '+
        esc(op.opId)+'</h3>'+
        '<div class="uxml-op-meta"><strong>UXML IDs:</strong> '+
        esc(op.uxmlIds.join(', '))+'</div>'+
        '<div class="uxml-op-meta"><strong>Original source records:</strong> '+
        op.sourceRecords.map(r=>esc(r.format+':'+r.recordKey+
          (r.changed?' [changes]':' [witness]'))).join(' · ')+'</div>'+
        '<ul class="uxml-op-changes">'+op.changes.map(c=>
          '<li>'+esc(c.recordKey+' · '+c.field+': '+
            label(c.before)+' → '+(c.after==null?'(removed)':label(c.after)))+
          '</li>').join('')+'</ul>'+
        '<p class="uxml-op-meta"><strong>Auto-eligible because:</strong> '+
        esc(op.policyReason)+'</p>'+
        '<button type="button" data-ops-locate="'+esc(op.opId)+
        '">Find / Review exact source location</button></article>'
      ).join('')||'<p>No operations match the selected kind or source record key.</p>';
  }
  function exportRows(format){
    const state=snapshot();
    if(!ready(state))return;
    // Export exactly the rows visible under the CURRENT kind/search inputs.
    const filter={kind,search};
    const body=format==='csv'?
      operationsCSV(state.preview,state.reviewOnlyCount,filter):
      JSON.stringify(visibleOperationExport(state.preview,state.reviewOnlyCount,filter),null,2)+'\n';
    const url=URL.createObjectURL(new Blob([body],
      {type:format==='csv'?'text/csv;charset=utf-8':'application/json'}));
    const link=document.createElement('a');
    link.href=url;link.download='uxml-operations-preview.'+format;
    document.body.appendChild(link);link.click();link.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  const click=event=>{
    const button=event.target.closest('button');
    if(!button||!panel.contains(button))return;
    const state=snapshot();
    if(button.hasAttribute('data-ops-review')){onReview();return;}
    if(!ready(state))return;
    if(button.hasAttribute('data-ops-json'))exportRows('json');
    else if(button.hasAttribute('data-ops-csv'))exportRows('csv');
    else if(button.hasAttribute('data-ops-locate')){
      const op=state.preview.ops.find(row=>row.opId===button.dataset.opsLocate);
      if(op)onLocate(op.sourceRecords.map(ref=>ref.recordKey),op.opId);
    }
  };
  const changed=event=>{
    if(event.target.matches('[data-ops-kind]')){kind=event.target.value;render();}
  };
  const typed=event=>{
    if(event.target.matches('[data-ops-search]')){search=event.target.value;render();}
  };
  panel.addEventListener('click',click);
  panel.addEventListener('change',changed);
  panel.addEventListener('input',typed);
  return {render,reset(){kind='all';search='';query(panel,'[data-ops-search]').value='';render();},
    dispose(){panel.removeEventListener('click',click);
      panel.removeEventListener('change',changed);panel.removeEventListener('input',typed);}};
}
