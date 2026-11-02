/** XML229 WP1: standalone source-only topology inspection; no engineering acceptance. */
import {createTopologyWorkerClient} from './topology-worker-client.mjs';
import {parseOccurrenceScene, affectedOccurrenceIds, escapeValue as esc} from './occurrence-scene.mjs';
import {createTopologyCanvas} from './projected-canvas.mjs';
import {buildAudit,renderAuditHTML,renderAuditSummary,filterCounts} from './audit-view.mjs';
import {eligibleActions,previewBatchPlan,explicitlyRejectedActionIds} from './batch-plan.mjs';
import {runValidatedPasses} from './batch-runner.mjs';
import {assertOperationsPreview} from './uxml-operations-view.mjs';
import {createOperationsPreviewPanel} from './uxml-operations-panel.mjs';
import {runShortBulk} from './short-bulk.mjs';
import {secondPassHTML} from './second-pass.mjs';
import {enqueueManualFix,runManualFixQueue} from './manual-fix-queue.mjs';
import {trialRemaining,trialGroup,trialGroupTitles,trialGroupFilters,trialValidationSummary,trialDisabledReason} from './trial-clarity.mjs';

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
export function mountTopologyWorkspace(root, {runEngine,cancelEngine}={}) {
  if(!root)throw Error('Topology workspace root is required');
  // One isolated engine per workspace; test injection does not start a Worker.
  const ownedWorker=runEngine?null:createTopologyWorkerClient();
  runEngine ||= ownedWorker.run;
  cancelEngine ||= ownedWorker?()=>ownedWorker.cancel():()=>{};
  const state={epoch:0,source:null,original:null,revision:0,applied:0,history:[],resolutions:[],shortElements:[],shortSelection:null,scene:null,plan:null,findings:[],result:null,
    selected:new Set(),search:'',filter:'all',category:'all',hubEnabled:false,hubParity:null,hubRevision:null,analysisProof:null,evidenceProofReason:'EVIDENCE_ANALYSIS_REQUIRED',opsPreview:null,opsPreviewError:null,
     activeJob:null,shortBulkFinalizing:false,fixFinalizing:false,manualPorts:[],secondPass:null,openRules:new Map(),openCases:new Set(),fix:null,batch:null,gapReviews:new Map(),busy:false,batchRunning:false,shortBulk:null,independentShortGroups:false,manualQueue:[],manualQueueRunning:false,manualQueueCheckpoint:null,manualQueueStatus:''};
  // The queue lives alongside Second Pass, without changing the engineering audit.
  const queuePanel=document.createElement('section');
  queuePanel.dataset.manualQueue='';
  queuePanel.className='audit-joint';
  queuePanel.setAttribute('aria-label','Approved Manual Fix Queue');
  const secondPanel=query(root,'[data-second-pass]');
  if(secondPanel)secondPanel.insertAdjacentElement('beforebegin',queuePanel);
  const canvas=createTopologyCanvas(query(root,'[data-canvas]'),onHits);
  const updateStatus=message=>{query(root,'[data-status]').textContent=message;};
  const displayMessage=message=>{query(root,'[data-hits]').textContent=message;};
  function hubCanRelease(fix=false){
    if(!state.hubEnabled)return true;
    return state.hubParity?.status==='EQUAL'&&state.hubRevision===state.revision&&
      (!fix||state.fix?.hubRoute===true);
  }
  function renderHubParity(){
    const badge=query(root,'[data-uxml-parity]');
    const details=query(root,'[data-uxml-differences]');
    if(!badge||!details)return;
    const status=state.hubEnabled?(state.hubParity?.status||'NOT_CHECKED'):'OFF';
    badge.dataset.parity=status;
    badge.textContent=!state.hubEnabled?'UXML preview OFF · direct TopoFix':
      'Universal XML route (preview) · '+status;
    const differences=state.hubParity?.differences||[];
    details.textContent=!state.hubEnabled?'UXML preview off. Direct route remains available.':
      status==='EQUAL'?'EQUAL · direct findings and plan match the pinned UXML reader'+
        (state.hubRevision===state.revision?' · hub corrected XML verified for download.':' · run Auto fix through hub to enable corrected download.'):
      differences.length?differences.join('\n'):
      'Analyze to compare direct PSI116 and pinned UXML. Download blocked until EQUAL.';
  }
  function recordHubResult(result,expectedRawSha=state.source?.rawSha256){
    if(!state.hubEnabled)return;
    const parity=result?.topologyUxmlParity;
    state.hubParity=parity&&['EQUAL','DIFFERENT','UNAVAILABLE'].includes(parity.status)?
      {status:parity.status,differences:Array.isArray(parity.differences)?parity.differences:[]}:
      {status:'DIFFERENT',differences:['/handshake: MISSING_UXML_PARITY_RECEIPT']};
    if(state.hubParity.status!=='EQUAL'){
      // Parity is authoritative; a non-applicable preview cannot publish rows.
      state.opsPreview=null;
      state.opsPreviewError=null;
    }else if(result?.topologyOperationsPreview?.error){
      state.opsPreview=null;
      state.opsPreviewError=String(result.topologyOperationsPreview.error);
    }else if(result?.topologyOperationsPreview){
      try{
        state.opsPreview=assertOperationsPreview(result.topologyOperationsPreview,
          expectedRawSha);
        state.opsPreviewError=null;
      }catch(error){
        // Read-only presentation failure cannot downgrade the hub's EQUAL
        // resolver and patch-back parity or disable native Auto-fix.
        state.opsPreview=null;
        state.opsPreviewError='UXML_OPS_PREVIEW_INVALID:'+
          String(error?.message||error);
      }
    }else if(result?.topologySummary?.generateTopoFix!==true){
      state.opsPreview=null;
      state.opsPreviewError='MISSING_CANONICAL_S2_OPERATIONS_PREVIEW';
    }
    renderHubParity();
    opsPanel.render();
  }
  const opsPanel=createOperationsPreviewPanel(root,{
    snapshot:()=>({hubEnabled:state.hubEnabled,parity:state.hubParity,
      preview:state.opsPreview,previewError:state.opsPreviewError,
      proof:analysisProofCurrent(),
      busy:state.busy||state.batchRunning,
      reviewOnlyCount:state.plan?
        buildAudit(state.findings,state.plan.actions||[]).counts.manual:0}),
    onLocate:(keys,opId)=>{
      const ids=keys.map(key=>state.scene?.byKey.get(key)?.id).filter(Boolean);
      if(!ids.length){displayMessage('No exact source occurrence; location not guessed.');return;}
      select(ids);canvas.focus(ids);
      displayMessage('Operations preview: '+ids.length+
        ' exact original source occurrence(s) highlighted for '+opId+'.');
      query(root,'[data-canvas]')?.scrollIntoView({block:'center'});
    },
    onReview:()=>{
      state.filter='manual';renderActions();
      query(root,'[data-audit-filter="manual"]')?.scrollIntoView({block:'center'});
    },
  });
  function sourceMeta(){
    query(root,'[data-source-meta]').textContent=state.source.name+' · working revision '+state.revision+
      ' · '+state.scene.records.length+' occurrences · SHA256 '+state.source.sourceSha256;
  }
  function acceptAnalysis(result,sourceSha){
    if(result?.ok!==true||result.outputKind!=='topology-sidecars'||result.ciiText||
       result.acceptedFinalTransferred!==false||result.nativeCiiReleaseAuthorized!==false||
       result.topoFixCommitted===true||result.topoFixXmlText)throw Error('Topology-only recheck rejected');
    const plan=JSON.parse(result.topologyFixPlanText||'null');
    const findings=JSON.parse(result.topologyFindingsText||'null');
    if(plan?.source?.sha256!==sourceSha||findings?.source?.sha256!==sourceSha||
       !Array.isArray(plan.actions)||!Array.isArray(findings.findings))throw Error('TOPOFIX_PLAN_SOURCE_DRIFT');
    return {plan,findings:findings.findings,resolutions:findings.resolvedConnections||[],shortElements:findings.shortElements||[],manualPorts:findings.manualConnectionPorts||[]};
  }
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
    const shortButton=query(root,'[data-select-short]');
    if(shortButton)shortButton.disabled=!state.plan||state.busy||state.batchRunning||
      (state.hubEnabled&&(state.hubParity?.status!=='EQUAL'||!analysisProofCurrent()));
    const plan=state.plan;
    const summary=query(root,'[data-plan-summary]');
    const panel=query(root,'[data-issues]');
    const resolved=query(root,'[data-resolved]');
    if(resolved)resolved.innerHTML=state.resolutions.length?
      '<details><summary>'+state.resolutions.length+' connections / terminations automatically resolved · source evidence</summary><ul>'+
      state.resolutions.map((r,i)=>'<li><button data-resolved-index="'+i+'">'+esc(r.code.replaceAll('_',' '))+
        ' · '+esc(r.node_keys.join(', '))+'</button><p>'+esc(r.message)+'</p></li>').join('')+'</ul></details>':'';
    const evidence=query(root,'[data-download-resolutions]');
    if(evidence)evidence.disabled=!state.plan||state.busy||state.batchRunning||!analysisProofCurrent();
    const evidenceStatus=query(root,'[data-evidence-proof]');
    if(evidenceStatus)evidenceStatus.textContent=analysisProofCurrent()?
      'Connection evidence verified for working revision '+state.revision+'.':
      'Connection evidence unavailable: '+(state.evidenceProofReason||'EVIDENCE_ANALYSIS_REQUIRED')+
      ' · Re-analyse current XML to retry.';
    if(!plan){
      summary.textContent='Analyze XML to see findings grouped by engineering rule.';
      panel.innerHTML='';
      const receiptButton=query(root,'[data-download-gap-review]');
      if(receiptButton)receiptButton.disabled=true;
      getNodes(root,'[data-audit-filter]').forEach(button=>{
        button.textContent=button.dataset.auditLabel+' (0)';
      });
      const allButton=query(root,'[data-auto-fix-all]');
      if(allButton){allButton.disabled=true;allButton.textContent='Autofix-All (0 actions)';}
      renderTrialResult();explainDisabledActions();
      return;
    }
    const audit=buildAudit(state.findings,plan.actions||[]);
    summary.textContent=renderAuditSummary(audit);
    const visible=renderAuditHTML(audit,{search:state.search,filter:state.filter,
      category:state.category,reviews:Object.fromEntries(state.gapReviews),
      sourceByKey:state.scene?.byKey,openRules:state.openRules.get(state.filter)||null,openCases:state.openCases});
    panel.innerHTML=visible.html;
    renderReviewNavigation(audit);
    const receiptButton=query(root,'[data-download-gap-review]');
    if(receiptButton)receiptButton.disabled=!state.gapReviews.size;
    const current=filterCounts(audit,{search:state.search,category:state.category});
    getNodes(root,'[data-audit-filter]').forEach(button=>{
      const key=button.dataset.auditFilter;
      button.setAttribute('aria-pressed',String(key===state.filter));
      button.textContent=button.dataset.auditLabel+' ('+current[key]+')';
    });
    const batchButton=query(root,'[data-auto-fix-all]');
    const allowed=eligibleActions(state.findings,plan.actions||[]);
    if(batchButton){
      batchButton.disabled=state.busy||state.batchRunning||allowed.length===0||
        (state.hubEnabled&&state.hubParity?.status!=='EQUAL');
      batchButton.textContent='Autofix-All ('+allowed.length+' actions)';
    }
    renderTrialResult();explainDisabledActions();
  }
  /** Presentation-only snapshot, no fix or admission modifications. */
  function renderTrialResult(){
    const panel=query(root,'[data-trial-result]');
    if(!panel)return;
    panel.hidden=!state.source||state.revision===0||
      state.fix?.sourceSha256!==state.source?.sourceSha256;
    if(panel.hidden)return;
    const checks=trialValidationSummary(state.history,state.fix);
    query(panel,'[data-trial-head]').textContent='Revision '+state.revision+
      ': '+state.applied+' fixes applied · '+checks;
    query(panel,'[data-trial-checks]').textContent=
      'Validated working copy only. These checks do not certify engineering connectivity.';
    const audit=buildAudit(state.findings,state.plan?.actions||[]);
    const groups=trialRemaining(audit);
    getNodes(panel,'[data-what-left]').forEach(button=>{
      const kind=button.dataset.whatLeft;
      button.textContent=trialGroupTitles[kind]+' ('+groups[kind].length+')';
      button.disabled=groups[kind].length===0;
      button.setAttribute('aria-pressed',String(state.filter===trialGroupFilters[kind]));
    });
    const busy=state.busy||state.batchRunning;
    query(panel,'[data-trial-current]').disabled=busy||!hubCanRelease();
    query(panel,'[data-trial-history]').disabled=busy||!hubCanRelease();
    query(panel,'[data-trial-evidence]').disabled=busy||!analysisProofCurrent();
  }
  function renderReviewNavigation(audit){
    const groups=trialRemaining(audit);
    getNodes(root,'[data-finding-id]').forEach(article=>{
      const findingId=article.dataset.findingId;
      const item=audit.items.find(row=>row.finding.finding_id===findingId);
      if(!item)return;
      const group=trialGroup(item),rows=groups[group];
      const index=rows.findIndex(row=>row.finding.finding_id===findingId);
      if(index<0)return;
      const nav=document.createElement('nav');nav.className='audit-review-nav';
      nav.dataset.trialNav=group;
      const label=document.createElement('strong');
      label.textContent=trialGroupTitles[group]+' · '+(index+1)+' of '+rows.length;
      label.dataset.trialCounter='';
      nav.appendChild(label);
      for(const [direction,labelText,edge] of [
        [-1,'Previous',index===0],[1,'Next',index===rows.length-1]]){
        const button=document.createElement('button');
        button.type='button';button.dataset.trialStep=String(direction);
        button.dataset.trialId=findingId;button.dataset.trialGroup=group;
        button.textContent=labelText;button.disabled=edge;
        nav.appendChild(button);
      }
      // Append only navigation. The original engine/action controls stay intact.
      const guidance=article.querySelector('.audit-next-step');
      if(guidance)guidance.insertAdjacentElement('afterend',nav);
    });
  }
  function explainDisabledActions(){
    for(const button of getNodes(root,'button')){
      // Titles and inline reasons created here are owned and removed together.
      const tagged=button.hasAttribute('data-reason-set');
      const following=button.nextElementSibling;
      if(following?.matches('.action-unavailable-reason')&&
         following.hasAttribute('data-generated-reason'))following.remove();
      if(tagged){
        button.removeAttribute('title');
        button.removeAttribute('data-reason-set');
      }
      if(button.disabled){
        const reason=trialDisabledReason(button,state,
          {proofCurrent:analysisProofCurrent(),hubCanRelease:hubCanRelease()});
        if(!reason)continue;
        button.title=reason;
        button.setAttribute('data-reason-set','');
        const small=document.createElement('small');
        small.className='action-unavailable-reason';
        small.setAttribute('data-generated-reason','');
        small.textContent=reason;
        button.insertAdjacentElement('afterend',small);
      }
    }
  }
  function visitTrialFinding(findingId){
    const audit=buildAudit(state.findings,state.plan?.actions||[]);
    const item=audit.items.find(row=>row.finding.finding_id===findingId);
    if(!item)return;
    const group=trialGroup(item);
    state.filter=trialGroupFilters[group];
    state.category='all';state.search='';
    query(root,'[data-search]').value='';
    query(root,'[data-audit-category]').value='all';
    const set=state.openRules.get(state.filter)||new Set();
    set.add(item.finding.code);state.openRules.set(state.filter,set);
    state.openCases.add(findingId);
    renderRecords();renderActions();
    const target=getNodes(root,'[data-finding-id]')
      .find(row=>row.dataset.findingId===findingId);
    if(target){
      target.closest('.audit-rule')?.setAttribute('open','');
      target.closest('.audit-case')?.setAttribute('open','');
      target.scrollIntoView({block:'nearest'});
    }
    const ids=(item.finding.node_keys||[])
      .map(key=>state.scene?.byKey.get(key)?.id).filter(Boolean);
    if(ids.length){select(ids);canvas.focus(ids);}
    explainDisabledActions();
  }
  function setFixStatus(message,kind='info',actionId=''){
    const panel=query(root,'[data-fix-result]');
    if(!panel)return;
    panel.setAttribute('data-result',kind);
    panel.textContent=message;
    if(['ready','stopped','rejected'].includes(kind)&&state.fix?.sourceSha256===state.source?.sourceSha256&&hubCanRelease(true)){
      const button=document.createElement('button');
      button.type='button';button.setAttribute('data-download-fix','');
      button.textContent='Download validated corrected XML';
      panel.appendChild(button);
      if(state.fix.report){
        const receipt=document.createElement('button');
        receipt.type='button';receipt.dataset.downloadBatchReport='';
        receipt.textContent=state.fix.receiptKey==='second-pass'?'Download connection repair receipt':'Download bulk audit / excluded actions';
        panel.appendChild(receipt);
      }
    }
  }
  function saveGapReview(button){
    const id=button.dataset.saveGapReview;
    const finding=state.findings.find(f=>f.finding_id===id);
    const allowed=['NEAR_MISS_PIPE_JOINT','NEAR_MISS_BRANCH_ENDS','BRANCH_END_UNVERIFIED'];
    if(!state.source||!finding||!allowed.includes(finding.code))return;
    const parent=button.closest('.audit-item');
    const disposition=parent?.querySelector('[data-gap-review-choice]')?.value;
    const note=parent?.querySelector('[data-gap-review-note]')?.value.trim()||'';
    const notice=query(root,'[data-gap-review-status]');
    if(!['intentional','repair','unresolved'].includes(disposition)||note.length<10){
      if(notice)notice.textContent='Select a disposition and enter at least 10 characters of engineering evidence/reference.';
      return;
    }
    state.gapReviews.set(id,{disposition,note,rule:finding.code,
      node_keys:[...(finding.node_keys||[])],sourceSha256:state.source.sourceSha256});
    renderActions();
    if(notice)notice.textContent='Saved '+state.gapReviews.size+' reviewer decision(s) for this source. Export review receipt; not engineering acceptance.';
  }
  function downloadGapReview(){
    if(!state.source||!state.gapReviews.size)return;
    const decisions=[...state.gapReviews.entries()].map(([findingId,record])=>({
      findingId,...record
    }));
    const receipt={schema:'xml229-preview-gap-review/v1',
      source:{name:state.source.name,sha256:state.source.sourceSha256,
        rawSha256:state.source.rawSha256},
      status:'REVIEWER_ANNOTATIONS_ONLY_NOT_CONNECTION_CERTIFICATION',
      reviewedAt:new Date().toISOString(),decisions};
    const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)+'\n'],
      {type:'application/json'}));
    const a=document.createElement('a');
    a.href=url;a.download=(state.source.name.replace(/\.xml$/i,'')||'input')+'.gap-review.json';
    document.body.appendChild(a);a.click();a.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function downloadBatchReport(){
    const fix=state.fix;
    if(state.busy||state.batchRunning||!fix?.report||
       fix.sourceSha256!==state.source?.sourceSha256||!hubCanRelease(true))return;
    const filename=(state.source.name.replace(/\\.xml$/i,'')||'input')+
      '.autofix-batch-report.json';
    const url=URL.createObjectURL(new Blob([JSON.stringify(fix.report,null,2)],
      {type:'application/json'}));
    const a=document.createElement('a');
    a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function downloadFix(){
    if(state.busy||state.batchRunning||!state.fix||
       state.fix.sourceSha256!==state.source?.sourceSha256||!hubCanRelease(true))return;
    const blob=new Blob([state.fix.xml],{type:'application/xml;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const anchor=document.createElement('a');
    anchor.href=url;anchor.download=state.fix.name;
    document.body.appendChild(anchor);anchor.click();anchor.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function downloadCurrent(history=false){
    if(state.busy||state.batchRunning||!state.source||!state.revision||!hubCanRelease())return;
    const body=history?JSON.stringify({schema:'topofix-working-history/v1',
      originalSha256:state.original.sourceSha256,currentSha256:state.source.sourceSha256,
      revision:state.revision,repairs:state.history},null,2):state.source.sourceText;
    const a=document.createElement('a'),url=URL.createObjectURL(new Blob([body],
      {type:history?'application/json':'application/xml'}));
    a.href=url;a.download=state.source.name+'.revision-'+state.revision+(history?'.repairs.json':'.topofix.xml');
    document.body.appendChild(a);a.click();a.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function analysisProofCurrent(){
    const p=state.analysisProof;
    return !!(p&&state.source&&state.result&&
      p.epoch===state.epoch&&p.revision===state.revision&&
      p.sourceSha256===state.source.sourceSha256&&
      p.result===state.result&&p.hubEnabled===state.hubEnabled&&
      (!state.hubEnabled||state.hubParity?.status==='EQUAL'));
  }
  // Shared custody predicate: a proof belongs to exactly the current
  // source/revision/epoch/route, and to a complete read-only analysis result.
  function establishCurrentAnalysisProof(result,{epoch=state.epoch,
    revision=state.revision,sourceRef=state.source,
    sourceSha256=state.source?.sourceSha256,hubEnabled=state.hubEnabled,
    accepted=null}={}){
    if(!state.source||state.source!==sourceRef||
       state.epoch!==epoch||state.revision!==revision||
       state.source.sourceSha256!==sourceSha256||
       state.hubEnabled!==hubEnabled)
      throw Error('EVIDENCE_RECHECK_STALE_REVISION');
    const current=accepted||acceptAnalysis(result,sourceSha256);
    if(hubEnabled&&state.hubParity?.status!=='EQUAL')
      throw Error('EVIDENCE_RECHECK_PARITY_NOT_EQUAL');
    state.result=result;
    state.analysisProof={epoch,revision,sourceSha256,result,hubEnabled};
    state.evidenceProofReason='';
    return current;
  }
  function clearEvidenceProof(reason){
    state.analysisProof=null;state.result=null;
    state.evidenceProofReason=reason;
  }
  function readOnlyAnalysisJob(source){
    return {sourceKind:'xml',sourceText:source.sourceText,
      sourceName:source.name,topologyPreFinalOnly:true,
      options:{outputMode:'enriched-only',analyzeTopology:true,generateTopoFix:false,
        useTopoFixForCii:false,topologyActionIds:[],
        topologyUxmlPreview:state.hubEnabled},
      sourceRawSha256:source.rawSha256};
  }
  // One fresh analysis after a validated bulk/queue publish. Never
  // promote a prior-revision transaction or result to connection evidence.
  async function refreshPublishedEvidence(generation,revision,sourceRef){
    clearEvidenceProof('EVIDENCE_RECHECK_PENDING');refresh();
    const sourceSha256=sourceRef?.sourceSha256,hubEnabled=state.hubEnabled;
    try{
      if(generation!==state.epoch||revision!==state.revision||
         state.source!==sourceRef||!sourceSha256||
         hubEnabled!==state.hubEnabled)
        throw Error('EVIDENCE_RECHECK_STALE_REVISION');
      const recheck=await runEngine(readOnlyAnalysisJob(sourceRef));
      if(generation!==state.epoch)return false;
      if(revision!==state.revision||state.source!==sourceRef||
         state.source?.sourceSha256!==sourceSha256||
         hubEnabled!==state.hubEnabled)
        throw Error('EVIDENCE_RECHECK_STALE_REVISION');
      if(hubEnabled)recordHubResult(recheck,sourceRef.rawSha256);
      const current=establishCurrentAnalysisProof(recheck,
        {epoch:generation,revision,sourceRef,sourceSha256,hubEnabled});
      state.plan=current.plan;state.findings=current.findings;
      state.resolutions=current.resolutions;state.shortElements=current.shortElements;
      state.manualPorts=current.manualPorts;
      return true;
    }catch(error){
      if(generation!==state.epoch)return false;
      const reason=String(error?.message||error);
      clearEvidenceProof(reason==='EVIDENCE_RECHECK_STALE_REVISION'?
        'EVIDENCE_RECHECK_STALE_REVISION':
        reason==='EVIDENCE_RECHECK_PARITY_NOT_EQUAL'?
          'EVIDENCE_RECHECK_PARITY_NOT_EQUAL':
        reason.includes('SOURCE_DRIFT')?'EVIDENCE_RECHECK_SOURCE_DRIFT':
          'EVIDENCE_RECHECK_FAILED:'+String(error?.name||'Error'));
      return false;
    }finally{
      if(generation===state.epoch)refresh();
    }
  }
  function downloadResolutions(){
    if(!state.source||!state.plan||!analysisProofCurrent()||state.busy||state.batchRunning)return;
    const receipt={schema:'topofix-connection-evidence/v1',sourceSha256:state.source.sourceSha256,
      toleranceMm:25,resolvedConnections:state.resolutions,remainingFindings:state.findings,
      workingRevision:state.revision,xmlChangedByResolution:false};
    const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
    a.href=url;a.download=state.source.name+'.connection-evidence.json';document.body.appendChild(a);a.click();a.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function planAutoFixAll(){
    if(state.busy||!state.plan||!state.source)return;
    const plan=previewBatchPlan(state.findings,state.plan.actions||[],state.scene?.byKey);
    state.batch={...plan,sourceSha256:state.source.sourceSha256,epoch:state.epoch};
    const panel=query(root,'[data-batch-confirm]');
    const excluded=plan.notEligible;
    const skipped=plan.skipped.length;
    panel.textContent='Autofix-All: '+plan.candidateCount+' eligible XML-changing actions. '+
      plan.actionIds.length+' conflict-free actions selected for one validated transaction. '+
      skipped+' overlapping/unsafe for this batch; '+excluded+
      ' KEEP, evidence-only, manual or otherwise ineligible actions excluded. '+
      'Includes compatible port closures at ≤25 mm. Original file will not change.';
    if(!plan.actionIds.length){
      panel.textContent+=' No safe batch available; review items individually.';
      return;
    }
    const run=document.createElement('button');
    run.type='button';run.dataset.runAutoFixAll='';
    run.textContent='Run validated batch · '+plan.actionIds.length+' actions';
    panel.appendChild(run);
    const cancel=document.createElement('button');
    cancel.type='button';cancel.dataset.cancelAutoFixAll='';
    cancel.textContent='Cancel batch';panel.appendChild(cancel);
  }
  async function runFix(actionIds,receiptKey='single',jointRepairs=[],shortElementRequests=[]){
    const allowed=new Set(eligibleActions(state.findings,state.plan?.actions||[])
      .map(a=>a.action_id));
    let ids=[...new Set(actionIds)].sort();
    const joint=jointRepairs.length===1&&ids.length===1&&
      ids[0]==='JOIN:'+jointRepairs[0].findingId+':'+jointRepairs[0].moveKey;
    const drop=shortElementRequests.length===1&&ids.length===1&&ids[0]===shortElementRequests[0].id;
    const dropWitness=drop?state.shortElements.find(r=>r.id===ids[0]):null;
    if(!state.source||state.busy||(state.batchRunning&&receiptKey!=='batch')||!ids.length||(joint&&drop)||(!joint&&!drop&&ids.some(id=>!allowed.has(id)))||
      (state.hubEnabled&&(state.hubParity?.status!=='EQUAL'||joint||drop))){
      setFixStatus('Auto fix is not authorized for this selection. No XML was modified.','rejected');
      return;
    }
    const generation=state.epoch,source=state.source,batch=receiptKey==='batch';
    let readyForHubRelease=false;
    const skippedByPlan=batch?[...(state.batch?.skipped||[])]:[];
    const skippedByEngine=[];
    state.busy=true;state.lastFailure='';refresh();
    query(root,'[data-progress]').textContent='APPLYING · '+ids.length+' action(s). Waiting for validation and working-copy recheck…';
    setFixStatus('Applying '+ids.length+' selected PSI116 action(s) to an isolated copy. '+
      'Any rejected action will be excluded from the next full validation attempt.');
    try{
      let result=null,txn=null,validation=null,reasons=[];
      for(let attempt=0;attempt<=ids.length&&attempt<25;attempt++){
        result=await runEngine({sourceKind:'xml',sourceText:source.sourceText,
          sourceName:source.name,topologyPreFinalOnly:true,
          options:{outputMode:'enriched-only',analyzeTopology:true,
            generateTopoFix:true,useTopoFixForCii:false,topologyActionIds:ids,
            topologyJointRepairs:jointRepairs,topologyShortElementRequests:shortElementRequests,
            topologyUxmlPreview:state.hubEnabled},sourceRawSha256:source.rawSha256});
        if(generation!==state.epoch)return;
        recordHubResult(result);
        if(state.hubEnabled&&state.hubParity?.status!=='EQUAL')
          throw Error('UXML_PREVIEW_PARITY_BLOCKED: '+state.hubParity?.differences.join(' | '));
        txn=JSON.parse(result?.topoFixTransactionText||'null');
        validation=JSON.parse(result?.topoFixValidationText||'null');
        reasons=[...(txn?.rejectReasons||[]),...(validation?.rejectReasons||[])];
        if(result?.ok!==true||result.outputKind!=='topology-sidecars'||
           result.acceptedFinalTransferred!==false||
           result.nativeCiiReleaseAuthorized!==false||
           result.ciiText||result.enrichedText||
           txn?.source?.sha256!==source.sourceSha256||
           validation?.sourceSha256!==source.sourceSha256||
           txn.sourceXmlMutated!==false)
          throw Error('Pre-Final source custody or execution contract rejected: '+
            (reasons.join(', ')||result?.error||'contract failure'));
        if(result.topoFixCommitted===true)break;
        const rejected=batch?explicitlyRejectedActionIds(reasons)
          .filter(id=>ids.includes(id)):[];
        if(!rejected.length||ids.length<=rejected.length)
          throw Error('PSI116 rejected the transaction: '+
            (reasons.join(', ')||result?.error||'not committed'));
        for(const id of rejected)skippedByEngine.push({actionId:id,
          reason:reasons.find(reason=>reason.includes('Action '+id))||'ENGINE_REJECTED'});
        const removed=new Set(rejected);
        ids=ids.filter(id=>!removed.has(id));
        setFixStatus('PSI116 rejected '+skippedByEngine.length+
          ' source action(s). Rechecking the remaining '+ids.length+
          ' as a fresh, all-or-nothing XML transaction. No output released yet.');
      }
      if(generation!==state.epoch)return;
      if(!result||result.topoFixCommitted!==true||!result.topoFixXmlText||
         !result.topoFixLineageText||!result.topoFixPreFinalHandoffText)
        throw Error('No fully validated XML and source lineage were produced');
      const selected=[...(txn?.selectedActions||[])].sort();
      if(txn?.schema!=='psi116-topofix-transaction/v1'||
         validation?.schema!=='psi116-topofix-validation/v1'||
         txn.committed!==true||validation.committed!==true||
         selected.length!==ids.length||selected.some((v,i)=>v!==ids[i])||
         reasons.length||validation.summary?.blockingFailureCount!==0||
         !Array.isArray(validation.checks)||!validation.checks.length||
         validation.checks.some(c=>c.blocking&&!c.passed)||
         !Array.isArray(txn.operations)||!txn.operations.length)
        throw Error('Selected IDs, validation or lineage receipt failed: '+
          (reasons.join(', ')||'receipt consistency'));
      const fixedSha=await sha256(new TextEncoder().encode(result.topoFixXmlText));
      if(generation!==state.epoch)return;
      if(txn.fixedXmlSha256!==fixedSha||validation.fixedXmlSha256!==fixedSha)
        throw Error('Corrected XML digest mismatch');
      const suffix=batch?'batch-'+ids.length:joint?(jointRepairs[0].mode==='SECOND_PASS'?'second-pass':'joint-closure'):drop?'short-element-drop':'single-fix';
      const excluded=[...skippedByPlan,...skippedByEngine];
      const proposed=eligibleActions(state.findings,state.plan.actions).length;
      const beforeCount=state.findings.length;
      const nextSource={...source,sourceText:result.topoFixXmlText,sourceSha256:fixedSha,rawSha256:fixedSha};
      const nextScene=parseOccurrenceScene(nextSource.sourceText,fixedSha);
      const lineage=JSON.parse(result.topoFixLineageText);
      const changedLocations=(lineage.sourceOccurrenceMap||[])
        .filter(r=>r.operationId&&Number.isInteger(r.fixedNodeOrdinal))
        .map(r=>[r.branchOccurrenceIndex,r.fixedNodeOrdinal]);
      const changedIds=nextScene.records.filter(r=>changedLocations.some(([b,s])=>
        r.branchIndex===b&&r.sourceIndex===s)).map(r=>r.id);
      setFixStatus('XML validated. Rechecking the corrected working copy and refreshing the canvas…');
      const recheck=await runEngine({sourceKind:'xml',sourceText:nextSource.sourceText,
        sourceName:source.name,topologyPreFinalOnly:true,
        options:{outputMode:'enriched-only',analyzeTopology:true,generateTopoFix:false,
          useTopoFixForCii:false,topologyActionIds:[],
          topologyUxmlPreview:state.hubEnabled},sourceRawSha256:fixedSha});
      if(generation!==state.epoch)return;
      recordHubResult(recheck,fixedSha);
      if(state.hubEnabled&&state.hubParity?.status!=='EQUAL')
        throw Error('UXML_RECHECK_PARITY_BLOCKED: '+state.hubParity?.differences.join(' | '));
      const current=acceptAnalysis(recheck,fixedSha);
      const priorReviews=Object.fromEntries(state.gapReviews);
      // A changed working source can never inherit an earlier release.
      state.hubRevision=null;state.fixFinalizing=true;
      state.source=nextSource;state.scene=nextScene;state.plan=current.plan;
      invalidateManualQueue();
      state.resolutions=current.resolutions;
      state.shortElements=current.shortElements;state.shortSelection=null;state.manualPorts=current.manualPorts;state.secondPass=null;state.openCases.clear();
      const shortPanel=query(root,'[data-short-preview]');if(shortPanel)shortPanel.textContent='';
      state.findings=current.findings;state.result=recheck;state.selected.clear();state.gapReviews.clear();
      state.selected=new Set(changedIds);
      state.revision++;state.applied+=ids.length;
      establishCurrentAnalysisProof(recheck,{epoch:generation,
        revision:state.revision,sourceRef:state.source,sourceSha256:fixedSha,
        accepted:current});
      state.history.push({sourceSha256:source.sourceSha256,fixedSha256:fixedSha,
        actionIds:ids,operations:txn.operations,validation:validation.checks,jointRepairs,reviews:priorReviews,
        resolvedConnections:current.resolutions});
      canvas.setScene(nextScene);sourceMeta();
      query(root,'[data-gap-review-status]').textContent='Working copy changed. Prior source review notes are in the repair history; review current findings.';
      query(root,'[data-progress]').textContent='APPLIED · revision '+state.revision+' · '+
        state.applied+' action(s) applied · findings '+beforeCount+' → '+current.findings.length+
        ' after full recheck. Canvas and counts show the corrected working copy.';
      state.fix={sourceSha256:fixedSha,receiptKey,actionIds:ids,
        hubRoute:state.hubEnabled,
        xml:result.topoFixXmlText,
        name:(source.name.replace(/\\.xml$/i,'')||'input')+'.'+suffix+
          '.validated.topofix.xml',
        report:batch||drop||joint?{schema:drop?'xml229-short-element-drop/v1':joint?'xml229-confirmed-connection/v1':'xml229-preview-batch-topofix/v1',
          status:'VALIDATED_COPY_NOT_ENGINEERING_ACCEPTANCE',
          source:{name:source.name,sha256:source.sourceSha256},
          fixedXmlSha256:fixedSha,
          proposedMutationCount:proposed,
          selectedActionIds:ids,excludedActions:excluded,
          ...(joint?{connectionApproval:jointRepairs[0],transaction:txn,validation,lineage,
            findingsBefore:beforeCount,findingsAfter:current.findings.length}:{}),
          ...(drop?{operations:txn.operations,selectedElement:dropWitness,
            selection:shortElementRequests,transaction:txn,validation,lineage,
            preFinalHandoff:JSON.parse(result.topoFixPreFinalHandoffText)}:{}),
          validationChecks:validation.checks}:null};
      setFixStatus('APPLIED to working copy: '+ids.length+' action(s), '+
        validation.checks.length+' validation checks, output SHA256 '+fixedSha+
        (batch?' · '+excluded.length+' excluded from bulk; see batch report.':'')+
        '. Canvas and counts rechecked. Download the validated copy for review. Original unchanged; '+
        'not connectivity certification or engineering acceptance.','ready',receiptKey);
      updateStatus('Repair applied and rechecked. Working revision '+state.revision+'.');
      readyForHubRelease=true;
    }catch(error){
      if(generation===state.epoch){
        const detail=error?.message||String(error);
        if(state.hubEnabled)holdShortHubRelease('RUN_FIX_PUBLICATION_FAILED:'+detail);
        const message=drop?(detail.includes('RECONNECTION')?
          'The element was retained because its surrounding ports could not reconnect. Check restraints, mating diameters and port directions.':
          'Drop and close failed validation. The element was retained; reopen the preview and check its current source ports.'):detail;
        state.lastFailure=message;
        query(root,'[data-progress]').textContent='NOT APPLIED · '+message+
          ' · working revision '+state.revision+' retained.';
        setFixStatus('Auto fix NOT applied: '+
        message+(state.fix?.sourceSha256===state.source.sourceSha256?'. Last validated XML and receipt retained. ':'. No new corrected XML was emitted. ')+
        'Current working revision retained.','rejected');
      }
    }finally{
      if(generation===state.epoch){
        state.busy=false;state.batch=null;
        try{query(root,'[data-batch-confirm]').textContent='';}catch{}
        // The UI is refreshed while release is still withheld.
        // A rendering exception is a fail-closed ERROR, not an open gate.
        refresh();
        state.fixFinalizing=false;
        if(readyForHubRelease&&state.hubEnabled&&
           state.hubParity?.status==='EQUAL'&&analysisProofCurrent()){
          state.hubRevision=state.revision;
          refresh(); // guarded; on failure refresh() revokes release
        }
      }
    }
  }
  function autoFix(actionId){return runFix([actionId],'single');}

  // This preview is only a view of source-qualified data already received.
  // Paginate so one click never constructs an unbounded DOM tree.
  const SHORT_SELECTION_PAGE_SIZE=24;
  function renderShortSelection(){
    // Selection only: no separate hub short-op preview or approval gate.
    const p=state.shortSelection,panel=query(root,'[data-short-preview]');
    if(!p||!state.source||p.sha!==state.source.sourceSha256){panel.textContent='';return;}
    const rows=state.shortElements,total=rows.length;
    const pages=Math.max(1,Math.ceil(total/SHORT_SELECTION_PAGE_SIZE));
    p.page=Math.max(0,Math.min(p.page,pages-1));
    const start=p.page*SHORT_SELECTION_PAGE_SIZE;
    const visible=rows.slice(start,start+SHORT_SELECTION_PAGE_SIZE);
    const eligible=rows.filter(r=>r.eligible).length;
    const hubReady=!state.hubEnabled||
      (state.hubParity?.status==='EQUAL'&&analysisProofCurrent());
    panel.innerHTML='<h3>Select short elements ≤6 mm</h3>'+
      '<p role="status">'+total+' measured candidates · '+eligible+
      ' eligible under source checks. Select owners, then Apply. '+
      'Each hub transaction independently checks canonical UXML operation authority, '+
      'loss contract, original source and native validation before retaining a revision.</p>'+
      '<label><input type="checkbox" data-short-independent '+
        (state.independentShortGroups?'checked ':'')+
        (state.busy||state.batchRunning?'disabled ':'')+'>'+
        'Group independent owners (up to 32; OFF = legacy one-owner comparison)</label>'+
       '<p data-short-selection-count>'+p.selected.size+' selected · page '+(p.page+1)+' of '+pages+'</p>'+
      '<button data-select-gaskets '+(state.busy||state.batchRunning?'disabled':'')+
        '>Select eligible gaskets (all pages)</button>'+
      '<ul>'+visible.map((r,i)=>'<li><label><input type="checkbox" data-short-index="'+(start+i)+'" '+
        (!r.eligible||state.busy||state.batchRunning?'disabled ':'')+
        (p.selected.has(r.id)?'checked ':'')+'>'+
        esc(r.componentType+' · '+Number(r.lengthMm).toFixed(3)+' mm'+
        (r.lengthBasis==='SOURCE_STRAIGHT_TWO_PORT_SPAN'?'':' source span; physical length unverified')+
        ' · '+r.componentRefNo+' · '+r.recordCount+' records · weight '+r.weightRemoved)+
        '</label><small>'+esc((r.nodeKeys||[]).join(', ')+' · '+
        (r.eligible?'Length basis: straight port spacing':r.reason||'Manual review'))+
        '</small></li>').join('')+'</ul>'+
      '<div class="short-preview-pagination"><button data-short-prev '+
        (!p.page||state.busy||state.batchRunning?'disabled':'')+'>Previous</button>'+
      '<button data-short-next '+
        (p.page>=pages-1||state.busy||state.batchRunning?'disabled':'')+'>Next</button></div>'+
      (total?'<button data-run-short-drop '+
        (!p.selected.size||!hubReady||state.busy||state.batchRunning?'disabled':'')+
        '>Apply '+p.selected.size+' selected &amp; close</button>':
        '<p>No measurable two-port elements at ≤6 mm.</p>')+
      '<p>Cancel retains the last validated revision. Refused owners are reported individually and never written.</p>';
    explainDisabledActions();
  }
  function selectShortElements(){
    if(!state.source||!state.plan||state.busy||state.batchRunning)return;
    state.shortSelection={sha:state.source.sourceSha256,epoch:state.epoch,page:0,selected:new Set()};
    renderShortSelection();
    query(root,'[data-short-preview]').scrollIntoView({block:'nearest'});
  }

  function showShortBulkAudit(outcome){
    // Presentation only. Each applied op is the exact canonical operation
    // returned after export_edit_ops -> apply_edit_ops -> byte-equal native
    // comparison; every refusal is retained with its original named reason.
    const panel=query(root,'[data-fix-result]');if(!panel)return;
    const applied=outcome?.applied||[],skipped=outcome?.skipped||[];
    if(!applied.length&&!skipped.length)return;
    const details=document.createElement('details');
    details.dataset.shortBulkOperations='';
    const summary=document.createElement('summary');
    summary.textContent='Review source-bound Apply operations: '+applied.length+
      ' validated, '+skipped.length+' skipped/refused';
    details.appendChild(summary);
    const list=document.createElement('ul');
    for(const pass of applied){
      const op=pass.canonicalEditOps?.[0];
      const removed=(op?.removedWithRecord||[])
        .map(x=>x.recordKey+' / '+x.field).join('; ')||'none';
      const li=document.createElement('li');
      li.textContent=pass.id+' · validated original source operation · removed records: '+
        (op?.targets||[]).join(', ')+' · removedWithRecord: '+removed;
      list.appendChild(li);
    }
    for(const item of skipped){
      const li=document.createElement('li');
      li.textContent=item.id+' · SKIPPED (no write) · '+item.reason;
      list.appendChild(li);
    }
    details.appendChild(list);panel.appendChild(details);
  }

  function holdShortHubRelease(reason){
    if(!state.hubEnabled)return;
    // Set source-release custody FIRST. Neither a canvas render exception nor
    // a second publication exception may preserve a stale EQUAL download gate.
    state.hubParity={status:'DIFFERENT',differences:[String(reason||'SHORT_BULK_HUB_HOLD')]};
    state.hubRevision=null;
    state.opsPreview=null;state.opsPreviewError=null;
    clearEvidenceProof('EVIDENCE_RECHECK_PARITY_NOT_EQUAL');
    // Rendering is advisory; hard release gates above survive UI exceptions.
    try{renderHubParity();opsPanel.render();}catch{/* custody already HELD */}
  }

  /** One UI publication for a fully audited sequence (or last validated checkpoint).
   * Never call runFix() or repaint the canvas per selected element.
   */
  async function publishShortBulk(outcome,generation=state.epoch){
    // Decide and enforce hub authority before ANY working-source mutation.
    const reason=outcome?.stopReason||'COMPLETE';
    // The Worker may carry a stronger hub-HOLD witness than its stop label.
    // A COMPLETE/CANCELLED label never overrides an explicit native mismatch.
    const hubMismatch=state.hubEnabled&&(
      (reason!=='COMPLETE'&&reason!=='CANCELLED')||outcome?.hubMismatch===true);
    // RELEASE LAST: revoke previous authority until every parse, UI write,
    // source-count check and evidence recheck has succeeded.
    state.hubRevision=null;
    if(hubMismatch)holdShortHubRelease(outcome?.stopMessage||'SHORT_BULK_HUB_HOLD:'+reason);
    if(!outcome||outcome.originSha256!==state.source?.sourceSha256)
      throw Error('SHORT_BULK_ORIGINAL_SOURCE_DRIFT');
    const beforeCount=state.findings.length,applied=outcome.applied||[];
    if(outcome.latest&&applied.length){
      const next=outcome.latest;
      const scene=parseOccurrenceScene(next.source.sourceText,next.source.sourceSha256);
      const previous=state.source;
      const reviews=Object.fromEntries(state.gapReviews);
      state.source=next.source;
      invalidateManualQueue();
      state.scene=scene;state.plan=next.plan;state.findings=next.findings.findings;
      state.resolutions=next.findings.resolvedConnections||[];
      state.shortElements=next.findings.shortElements||[];
      state.manualPorts=next.findings.manualConnectionPorts||[];
      state.secondPass=null;state.shortSelection=null;state.selected.clear();
      state.gapReviews.clear();state.openCases.clear();
      query(root,'[data-short-preview]').textContent='';
      for(const [i,pass] of applied.entries()){
        state.history.push({sourceSha256:pass.sourceSha256,fixedSha256:pass.fixedSha256,
          actionIds:[pass.id],operations:pass.transaction.operations,
          canonicalEditOps:pass.canonicalEditOps,validation:pass.validation.checks,
          reviews:i===0?reviews:{},resolvedConnections:i===applied.length-1?state.resolutions:[]});
      }
      state.revision+=applied.length;
      state.applied+=applied.length;
      clearEvidenceProof('EVIDENCE_RECHECK_PENDING');
      state.fix={sourceSha256:state.source.sourceSha256,receiptKey:'drop',
        hubRoute:state.hubEnabled,
        actionIds:applied.map(p=>p.id),xml:state.source.sourceText,
        name:(previous.name.replace(/\\.xml$/i,'')||'input')+'.bulk-'+applied.length+'.validated.topofix.xml',
        report:{schema:'xml229-short-element-bulk/v2',
          status:'VALIDATED_WORKING_COPY_NOT_ENGINEERING_ACCEPTANCE',
          source:{name:previous.name,sha256:outcome.originSha256},
          fixedXmlSha256:state.source.sourceSha256,
          requestedIds:outcome.requested,
          applied:applied,skipped:outcome.skipped,
          completed:outcome.completed,failedId:outcome.failedId||null,
          pendingIds:outcome.pendingIds||[],
          eligibleOnCurrentXml:next.findings.shortElements.filter(r=>r.eligible).length,
          stopReason:outcome.stopReason,
          stopMessage:outcome.stopMessage,findingsBefore:beforeCount,
          findingsAfter:state.findings.length}};
      canvas.setScene(scene);sourceMeta();
      query(root,'[data-gap-review-status]').textContent=
        'Bulk working revision changed. Review current findings and download source-bound repair history.';
    }
    const done=applied.length,skipped=outcome.skipped?.length||0;
    const selected=outcome.requested?.length||0,failed=outcome.failedId?1:0;
    const checked=done+skipped+failed,unprocessed=Math.max(0,selected-checked);
    const nowEligible=state.shortElements.filter(r=>r.eligible).length;
    if(checked+unprocessed!==selected)throw Error('SHORT_BULK_COUNT_RECONCILIATION_FAILED');
    const message=(reason==='COMPLETE'?'BULK COMPLETE':'BULK STOPPED · '+reason)+
      ' · selected '+selected+' = '+done+' validated + '+skipped+' skipped + '+failed+
      ' failed + '+unprocessed+' unprocessed · eligible on CURRENT XML '+nowEligible+
      ' · working revision '+state.revision+
      (outcome.stopMessage?' · '+outcome.stopMessage:'')+
      (hubMismatch?' · last validated checkpoint retained; corrected downloads HELD.':
       done?' · validated XML, source-linked operations and lineage digests downloadable.':
         ' · no XML changed.');
    query(root,'[data-progress]').textContent=message;
    setFixStatus(message,hubMismatch?'rejected':
      reason==='COMPLETE'&&done?'ready':done?'stopped':'rejected','drop');
    showShortBulkAudit(outcome);
    updateStatus('Selected short-element batch finished. '+done+
      ' validated; '+skipped+' skipped/refused. Engineering review remains required.');
    // On a hub mismatch, do not reset the negative parity by reanalysing
    // the partially validated checkpoint until an explicit fresh Analyze.
    if(outcome.latest&&done&&!hubMismatch)
      await refreshPublishedEvidence(generation,state.revision,state.source);
    // No preview heartbeat may overwrite a terminal Apply result. A later
    // evidence mismatch is a HOLD, never an implied corrected download.
    if(generation===state.epoch)
      query(root,'[data-progress]').textContent=
        state.hubEnabled&&state.hubParity?.status!=='EQUAL'?
          message+' · HUB EVIDENCE HOLD: re-analyse before download.':message;
    // FINAL statement. Never add any throwable UI work after hub release:
    // even CANCELLED outcomes must finish all writes/recheck first.
    if(state.hubEnabled&&!hubMismatch&&generation===state.epoch&&
       state.hubParity?.status==='EQUAL'&&analysisProofCurrent())
      state.hubRevision=state.revision;
  }

  /** All short-bulk publication paths (finish, engine ERROR, Cancel) go here.
   * A publication failure never rethrows and cannot unlock a corrected download.
   * Retry uses the ACTUAL outcome, not a fabricated zero-progress checkpoint.
   */
  async function publishShortBulkGuarded(outcome,generation=state.epoch){
    try{
      await publishShortBulk(outcome,generation);
      return true;
    }catch(error){
      const why=String(error?.message||error);
      const label='SHORT_BULK_PUBLICATION_FAILED:'+why;
      if(state.hubEnabled)holdShortHubRelease(label);
      // If parse/scene setup failed before source publication, the original
      // SHA still matches and the same validated outcome can be re-presented.
      // If source already advanced, retry is source-bound and must refuse;
      // NEVER silently re-apply a transaction against the advanced source.
      const retry={...outcome,stopReason:'ERROR',stopMessage:label,
        hubMismatch:state.hubEnabled};
      try{
        if(generation===state.epoch&&state.source?.sourceSha256===outcome?.originSha256)
          await publishShortBulk(retry,generation);
      }catch(republishError){
        if(state.hubEnabled)holdShortHubRelease(
          'SHORT_BULK_REPUBLISH_FAILED:'+String(republishError?.message||republishError));
      }
      // No second publication or renderer is trusted for release custody.
      if(state.hubEnabled)holdShortHubRelease(label);
      const retained=state.revision;
      const validated=outcome?.applied?.length||0;
      const report='BULK STOPPED · ERROR · '+label+
        ' · working revision '+retained+' retained; '+
        validated+' native-validated item(s) in attempted publication'+
        (state.hubEnabled?' · corrected downloads HELD.':
          ' · working-source release requires review.');
      try{
        if(generation===state.epoch){
          query(root,'[data-progress]').textContent=report;
          setFixStatus(report,'rejected','drop');
          updateStatus('Publication failed; working revision '+retained+
            ' retained. Inspect the source-bound receipt before retry.');
        }
      }catch{/* no UI exception may escape the source-release gate */}
      return false;
    }
  }
  async function dropShortElements(){
    if(state.hubEnabled&&
       (state.hubParity?.status!=='EQUAL'||!analysisProofCurrent())){
      setFixStatus('UXML_SHORT_PARITY_OR_EVIDENCE_REQUIRED: Analyze the current source and verify EQUAL before Apply.','rejected');
      return;
    }
    const p=state.shortSelection;
    if(state.busy||state.batchRunning||!p||p.epoch!==state.epoch||
       p.sha!==state.source?.sourceSha256)return;
    // Do not silently drop a source-bound selection: per-owner Apply reports
    // each ineligible/refused item with its exact current-revision reason.
    const ids=[...p.selected];
    if(!ids.length){setFixStatus('Select at least one source-qualified element.','rejected');return;}
    const generation=state.epoch,source={...state.source};
    state.batchRunning=true;state.activeJob='short-bulk';
    state.shortBulk=null;refresh();
    const startedAt=Date.now();
    let lastCompleted=0,lastApplied=0,lastSkipped=0,bulkFinished=false,
      itemInFlight=false;
    const paintBulkProgress=()=>{
      if(generation!==state.epoch||!state.batchRunning||bulkFinished)return;
      const elapsed=Math.max(0,(Date.now()-startedAt)/1000);
      const remaining=lastCompleted>0&&lastCompleted<ids.length?
        Math.ceil(elapsed*(ids.length-lastCompleted)/lastCompleted):null;
      const eta=remaining===null?'estimating after first item':
        '~ETA '+(remaining>=60?Math.ceil(remaining/60)+' min':
          Math.max(1,remaining)+' sec')+' (approximate)';
      query(root,'[data-progress]').textContent=
        'Applying '+Math.min(ids.length,lastCompleted+(itemInFlight?1:0))+' of '+ids.length+' · '+
        lastApplied+' validated · '+lastSkipped+' skipped · '+eta+
        ' · Cancel available; only validated working revisions retained.';
    };
    const heartbeat=setInterval(paintBulkProgress,1000);
    paintBulkProgress();
    try{
      const outcome=await runShortBulk({
        source,shortElements:state.shortElements,selectedIds:ids,runEngine,
        hubEnabled:state.hubEnabled,enableIndependentGroups:state.independentShortGroups,
        isCurrent:()=>generation===state.epoch,
        onCheckpoint:checkpoint=>{if(generation===state.epoch)state.shortBulk=checkpoint;},
        onProgress:step=>{
          if(generation!==state.epoch)return;
          lastCompleted=step.completed;lastApplied=step.applied;lastSkipped=step.skipped;
          itemInFlight=step.status==='APPLYING';
          paintBulkProgress();
        },
      });
      if(generation!==state.epoch)return;
      bulkFinished=true;clearInterval(heartbeat);
      state.shortBulkFinalizing=true;state.shortBulk=null;refresh();
      await publishShortBulkGuarded(outcome,generation);
    }catch(error){
      if(generation!==state.epoch)return;
      // The native job itself failed before a terminal outcome. Preserve
      // its latest validated checkpoint rather than inventing an empty batch.
      const checkpoint=state.shortBulk||{originSha256:source.sourceSha256,latest:null,
        applied:[],skipped:[],requested:ids,completed:0};
      bulkFinished=true;clearInterval(heartbeat);
      state.shortBulkFinalizing=true;state.shortBulk=null;
      await publishShortBulkGuarded({...checkpoint,stopReason:'ERROR',
        stopMessage:String(error?.message||error),hubMismatch:state.hubEnabled},generation);
    }finally{
      clearInterval(heartbeat);
      if(generation===state.epoch){
        state.batchRunning=false;state.shortBulkFinalizing=false;
        state.activeJob=null;state.shortBulk=null;refresh();
      }
    }
  }

  function invalidateManualQueue(){
    state.manualQueue=state.manualQueue.map(entry=>entry.status==='APPROVED'
      ?{...entry,status:'STALE'}:entry);
    state.manualQueueStatus='Working XML changed; re-preview and re-approve stale entries.';
  }
  function renderManualQueue(){
    if(!queuePanel.isConnected)return;
    queuePanel.hidden=!state.plan&&!state.manualQueue.length;
    if(queuePanel.hidden)return;
    const approved=state.manualQueue.filter(x=>x.status==='APPROVED');
    const list=state.manualQueue.map(item=>'<li><strong>'+esc(item.findingId)+'</strong> · '+
      esc(item.sourceKey)+' → '+esc(item.peerKey)+' · '+esc(item.status)+
      (item.status==='APPROVED'?'<button data-queue-remove="'+esc(item.id)+'" type="button" '+
      (state.busy||state.batchRunning?'disabled':'')+'>Remove</button>':'')+'</li>').join('');
    queuePanel.innerHTML='<h3>Manual Fix Queue · '+approved.length+' approved</h3>'+
      '<p>Select source and partner in Second Pass, preview, provide evidence, then Add to queue. '+
      'Only authoritatively qualified and explicitly approved movements execute.</p>'+
      (state.manualQueue.length?'<ol>'+list+'</ol>':'<p>No approved repairs queued.</p>')+
      '<div><button data-queue-apply type="button" '+
      (!approved.length||state.busy||state.batchRunning||state.hubEnabled?'disabled':'')+
      '>Apply '+approved.length+' approved fix(es) &amp; recheck</button> '+
      '<button data-queue-clear type="button" '+
      (!state.manualQueue.length||state.busy||state.batchRunning?'disabled':'')+
      '>Clear queue</button></div>'+
      '<p data-queue-status role="status">'+esc(state.manualQueueStatus||
      'Queued repairs are preview-only until Apply. Full source evidence remains available.')+'</p>';
    explainDisabledActions();
  }
  function queueSecondPass(){
    const d=state.secondPass;
    if(state.busy||state.batchRunning||!d?.preview||!d.confirmed||
       d.evidence.trim().length<10||d.epoch!==state.epoch||
       d.sourceSha256!==state.source?.sourceSha256)return;
    try{
      state.manualQueue=enqueueManualFix(state.manualQueue,d,state.source.sourceSha256);
      state.manualQueueStatus='Approved exact pair queued. XML unchanged; review other cases or apply the queue.';
      d.status='QUEUED · '+state.manualQueue.length+' approved pair(s). No XML changes.';
      renderManualQueue();renderSecondPass();
    }catch(error){
      d.status='NOT QUEUED · '+String(error?.message||error);
      renderSecondPass();
    }
  }
  async function publishManualQueue(outcome,generation=state.epoch){
    if(!outcome||outcome.initialSha256!==state.source?.sourceSha256)
      throw Error('SECOND_PASS_QUEUE_SOURCE_PUBLISH_DRIFT');
    const before=state.findings.length,applied=outcome.applied||[];
    if(outcome.latest&&applied.length){
      const next=outcome.latest;
      const scene=parseOccurrenceScene(next.source.sourceText,next.source.sourceSha256);
      state.source=next.source;state.scene=scene;
      state.plan=next.plan;state.findings=next.findings.findings;
      state.resolutions=next.findings.resolvedConnections||[];
      state.shortElements=next.findings.shortElements||[];
      state.manualPorts=next.findings.manualConnectionPorts||[];
      state.selected.clear();state.openCases.clear();state.gapReviews.clear();
      state.secondPass=null;state.shortSelection=null;
      const shortPanel=query(root,'[data-short-preview]');
      if(shortPanel)shortPanel.textContent='';
      for(const item of applied){
        state.history.push({sourceSha256:item.sourceSha256,
          fixedSha256:item.fixedXmlSha256,actionIds:[item.actionId],
          jointRepairs:[{mode:'SECOND_PASS',findingId:item.findingId,
            sourceSha256:item.sourceSha256,portKeys:[item.sourceKey,item.peerKey],
            approvedRepair:item.preview.repair,evidence:item.evidence,confirmed:true}],
          operations:item.transaction.operations,validation:item.validation.checks,
          preFinalHandoff:item.preFinal,lineage:item.lineage,
          lineageSha256:item.lineageSha256});
      }
      state.revision+=applied.length;
      state.applied+=applied.length;
      clearEvidenceProof('EVIDENCE_RECHECK_PENDING');
      state.fix={sourceSha256:state.source.sourceSha256,receiptKey:'manual-queue',
        xml:state.source.sourceText,
        name:(state.source.name.replace(/\\.xml$/i,'')||'input')+
          '.manual-queue-'+applied.length+'.validated.topofix.xml',
        report:{schema:'xml229-manual-fix-queue/v1',
          status:'VALIDATED_WORKING_COPY_NOT_ENGINEERING_ACCEPTANCE',
          originalSourceSha256:outcome.initialSha256,
          fixedXmlSha256:state.source.sourceSha256,
          requested:outcome.requested,applied,blocked:outcome.blocked,
          unprocessed:outcome.pending,stopReason:outcome.stopReason,
          stopMessage:outcome.message,findingsBefore:before,
          findingsAfter:state.findings.length}};
      canvas.setScene(scene);sourceMeta();
      query(root,'[data-gap-review-status]').textContent=
        'Manual queue applied. Prior review notes remain in the source-linked repair history.';
    }
    const appliedIds=new Set(applied.map(x=>x.id));
    const blockedIds=new Set((outcome.blocked||[]).map(x=>x.id));
    const pendingIds=new Set(outcome.pending||[]);
    state.manualQueue=state.manualQueue.map(entry=>({...entry,status:
      appliedIds.has(entry.id)?'APPLIED':
      blockedIds.has(entry.id)?'BLOCKED':
      pendingIds.has(entry.id)?'STALE':
      entry.status==='APPROVED'?'STALE':entry.status}));
    const total=outcome.requested?.length||0,a=applied.length,b=outcome.blocked?.length||0;
    const remaining=outcome.pending?.length||0;
    if(total!==a+b+remaining)throw Error('SECOND_PASS_QUEUE_COUNT_MISMATCH');
    state.manualQueueStatus=(outcome.stopReason==='COMPLETE'?'QUEUE COMPLETE':'QUEUE STOPPED · '+outcome.stopReason)+
      ' · '+total+' selected = '+a+' applied + '+b+' blocked + '+remaining+' re-review required'+
      (outcome.message?' · '+outcome.message:'');
    query(root,'[data-progress]').textContent=state.manualQueueStatus;
    setFixStatus(state.manualQueueStatus,a?'ready':'rejected','manual-queue');
    updateStatus('Manual Fix Queue reconciled. '+a+' validated connections; source review remains required.');
    renderManualQueue();
    if(outcome.latest&&a)await refreshPublishedEvidence(generation,state.revision,state.source);
  }
  async function applyManualQueue(){
    if(state.hubEnabled){state.manualQueueStatus='UXML_PREVIEW_AUTO_ONLY: manual queue Apply held. Turn preview off for the existing route.';renderManualQueue();return;}
    if(state.busy||state.batchRunning||!state.source||!state.plan)return;
    const entries=state.manualQueue.filter(x=>x.status==='APPROVED');
    if(!entries.length)return;
    const generation=state.epoch,original={...state.source};
    if(entries.some(x=>x.approvedSourceSha256!==original.sourceSha256)){
      state.manualQueueStatus='Approved queue is stale. Re-preview and approve on the current XML.';
      renderManualQueue();return;
    }
    state.batchRunning=true;state.manualQueueRunning=true;
    state.manualQueueCheckpoint={initialSha256:original.sourceSha256,
      latest:null,applied:[],blocked:[],requested:entries.map(x=>x.id),
      pending:entries.map(x=>x.id)};
    const startedAt=Date.now();
    let activeStage='RECHECK',verified=0,remaining=entries.length;
    const heartbeat=()=>{
      if(generation!==state.epoch||!state.manualQueueRunning)return;
      state.manualQueueStatus='QUEUE '+activeStage+' · '+verified+'/'+entries.length+
        ' verified · '+remaining+' remaining · '+Math.floor((Date.now()-startedAt)/1000)+
        ' s elapsed. Audit and canvas show the pre-queue revision.';
      const node=query(root,'[data-queue-status]');
      if(node)node.textContent=state.manualQueueStatus;
      query(root,'[data-progress]').textContent=state.manualQueueStatus;
    };
    const heartbeatId=setInterval(heartbeat,1000);
    heartbeat();refresh();
    try{
      const outcome=await runManualFixQueue({source:original,entries,runEngine,
        isCurrent:()=>generation===state.epoch,
        onCheckpoint:saved=>{if(generation===state.epoch)state.manualQueueCheckpoint=saved;},
        onProgress:progress=>{
          if(generation!==state.epoch)return;
          activeStage=progress.status;verified=progress.applied;
          remaining=progress.remaining;heartbeat();
        }});
      if(generation!==state.epoch)return;
      await publishManualQueue(outcome,generation);
    }catch(error){
      if(generation!==state.epoch)return;
      const saved=state.manualQueueCheckpoint;
      await publishManualQueue({...saved,stopReason:'ERROR',message:String(error?.message||error)},generation);
    }finally{
      clearInterval(heartbeatId);
      if(generation===state.epoch){
        state.batchRunning=false;state.manualQueueRunning=false;
        state.manualQueueCheckpoint=null;refresh();
      }
    }
  }
  function renderSecondPass(){
    const panel=query(root,'[data-second-pass]');if(!panel)return;
    panel.hidden=!state.secondPass;
    panel.innerHTML=secondPassHTML(state.secondPass?{...state.secondPass,busy:state.busy||state.batchRunning}:null,state.scene,state.manualPorts);
    explainDisabledActions();
  }
  function updateSecondApply(){
    const d=state.secondPass;
    getNodes(root,'[data-apply-second],[data-queue-second]').forEach(button=>{
      button.disabled=state.hubEnabled||state.busy||state.batchRunning||!d?.preview||!d.confirmed||d.evidence.trim().length<10;
    });
    explainDisabledActions();
  }
  function beginSecondPass(findingId){
    if(state.busy||state.batchRunning)return;
    const finding=state.findings.find(f=>f.finding_id===findingId);if(!finding)return;
    const keys=(finding.node_keys||[]).filter(k=>state.manualPorts.some(p=>p.key===k&&!p.closed));
    state.secondPass={sourceSha256:state.source.sourceSha256,epoch:state.epoch,findingId,
      witnessKeys:finding.node_keys||[],sourceKey:keys[0]||'',peerKey:keys[1]||'',
      evidence:state.gapReviews.get(findingId)?.note||'',search:'',confirmed:false,preview:null};
    renderSecondPass();query(root,'[data-second-pass]').scrollIntoView({block:'start'});
  }
  function useSelectedPartner(){
    const d=state.secondPass;if(!d||state.busy)return;
    const records=[...state.selected].map(id=>state.scene.byId.get(id)).filter(Boolean);
    if(records.length!==1||records[0].key===d.sourceKey||!state.manualPorts.some(p=>p.key===records[0].key&&!p.closed)){
      d.status='Select exactly one different, open physical port on the canvas or in Source occurrences.';
    }else{
      d.peerKey=records[0].key;d.preview=null;d.confirmed=false;
      d.status='Canvas partner selected. Preview before applying.';
    }
    renderSecondPass();
  }
  async function previewSecondPass(){
    const d=state.secondPass;if(!d||state.busy||state.batchRunning||!d.sourceKey||!d.peerKey)return;
    const generation=state.epoch;
    const request={mode:'SECOND_PASS',sourceSha256:d.sourceSha256,findingId:d.findingId,portKeys:[d.sourceKey,d.peerKey]};
    d.preview=null;d.confirmed=false;d.busy=true;d.status='Checking physical ports, movement groups and constraints…';
    state.busy=true;refresh();
    try{
      const result=await runEngine({sourceKind:'xml',sourceText:state.source.sourceText,sourceName:state.source.name,
        topologyPreFinalOnly:true,options:{outputMode:'enriched-only',analyzeTopology:true,generateTopoFix:false,
          useTopoFixForCii:false,topologyConnectionPreview:request}});
      if(generation!==state.epoch||state.secondPass!==d)return;
      if(result?.ok!==true)throw Error(result?.error||'The port preview engine rejected this request.');
      acceptAnalysis(result,d.sourceSha256);
      const preview=JSON.parse(result.topologyFindingsText).manualConnectionPreview;
      if(preview?.sourceSha256!==d.sourceSha256||preview.findingId!==d.findingId||
        JSON.stringify(preview.portKeys)!==JSON.stringify(request.portKeys)||!preview.repair||!Array.isArray(preview.changes))
        throw Error('Second-pass preview source or selected-port mismatch.');
      d.preview=preview;d.status='PREVIEW ONLY · working XML and counts unchanged. Inspect the movement, enter evidence and confirm to apply.';
    }catch(error){
      if(generation===state.epoch&&state.secondPass===d){
        const detail=error?.message||String(error);
        d.status=detail.includes('INCOMPATIBLE_PORTS')?
          'Cannot close these ports: check matching diameters/bore, facing directions, owner types and closed-end declarations. Correct missing or conflicting source evidence and re-export.':
          detail.includes('MOVE_GROUP')?'Movement is constrained by restraints, shared ownership or pipe collapse. Select another qualified pair or correct the authoring model and re-export.':
          'Preview unavailable · '+detail;
      }
    }finally{
      if(generation===state.epoch){
        state.busy=false;d.busy=false;refresh();
        if(state.secondPass===d){
          if(d.preview){const ids=[d.sourceKey,d.peerKey].map(k=>state.scene.byKey.get(k)?.id).filter(Boolean);select(ids);canvas.focus(ids);}
          query(root,'[data-second-pass]').scrollIntoView({block:'start'});
        }
      }
    }
  }
  async function applySecondPass(){
    const d=state.secondPass;
    if(!d?.preview||!d.confirmed||d.evidence.trim().length<10||state.busy||state.batchRunning||
      d.epoch!==state.epoch||d.sourceSha256!==state.source?.sourceSha256)return;
    const repair=d.preview.repair;
    const request={mode:'SECOND_PASS',sourceSha256:d.sourceSha256,findingId:d.findingId,
      portKeys:[d.sourceKey,d.peerKey],moveKey:repair.movePortKey,targetKey:repair.targetPortKey,
      approvedRepair:repair,evidence:d.evidence.trim(),confirmed:true};
    await runFix(['JOIN:'+d.findingId+':'+repair.movePortKey],'second-pass',[request]);
    if(state.secondPass===d){d.status='NOT APPLIED · '+(state.lastFailure||'Working revision retained.');renderSecondPass();}
  }

  function closeJoint(button){
    if(state.busy)return;
    const item=button.closest('.audit-item');
    const finding=state.findings.find(f=>f.finding_id===button.dataset.closeJoint);
    const targetKey=item.querySelector('[data-joint-target]')?.value;
    const evidence=item.querySelector('[data-joint-evidence]')?.value.trim()||'';
    if(!finding||!item.querySelector('[data-joint-confirm]')?.checked||evidence.length<10){
      setFixStatus('Choose the retained port, confirm the intended connection and enter at least 10 characters of connection evidence.','rejected');return;
    }
    const moveKey=finding.node_keys.find(k=>k!==targetKey);
    const request={sourceSha256:state.source.sourceSha256,findingId:finding.finding_id,moveKey,targetKey,evidence};
    return runFix(['JOIN:'+finding.finding_id+':'+moveKey],'joint',[request]);
  }
  async function autoFixAll(){
    const b=state.batch;
    if(!b||b.epoch!==state.epoch||b.sourceSha256!==state.source?.sourceSha256||
       !b.actionIds.length)return;
    state.batchRunning=true;root.setAttribute('aria-busy','true');
    const generation=state.epoch,initialSha=state.source.sourceSha256;
    const initialFindings=state.findings.length,initialApplied=state.applied;
    const outcome=await runValidatedPasses({initialPlan:b,
      readState:()=>({sha:state.source.sourceSha256,revision:state.revision,fix:state.fix,failure:state.lastFailure}),
      isCurrent:()=>generation===state.epoch,
      runPass:async plan=>{state.batch={...plan,sourceSha256:state.source.sourceSha256,epoch:state.epoch};await runFix(plan.actionIds,'batch');},
      nextPlan:()=>previewBatchPlan(state.findings,state.plan.actions,state.scene.byKey)});
    if(generation!==state.epoch)return;
    const {passes,lastFix,stopReason,stopMessage}=outcome;
    state.batch=null;
    const remaining=eligibleActions(state.findings,state.plan.actions).length;
    if(lastFix&&lastFix.sourceSha256===state.source.sourceSha256)state.fix=lastFix;
    if(passes.length&&(passes.length>1||stopReason!=='COMPLETE')){
      state.fix={...lastFix,report:{schema:'xml229-preview-batch-topofix/v2',
        status:'VALIDATED_COPY_NOT_ENGINEERING_ACCEPTANCE',source:{name:state.source.name,sha256:initialSha},
        fixedXmlSha256:state.source.sourceSha256,passes,stopReason,stopMessage,
        appliedActionCount:state.applied-initialApplied,remainingEligibleActions:remaining},
        name:state.source.name+'.batch-'+(state.applied-initialApplied)+'.validated.topofix.xml'};
    }
    if(stopReason!=='COMPLETE'||passes.length>1){
      const stopped=stopReason!=='COMPLETE';
      const message=(stopped?'STOPPED: '+stopReason+' · '+stopMessage+' · ':'APPLIED · ')+
        passes.length+' validated passes · '+(state.applied-initialApplied)+' action(s) · findings '+
        initialFindings+' → '+state.findings.length+' · '+remaining+' eligible actions remain.'+
        (stopped&&state.fix?' Last validated XML and receipt retained.':'');
      setFixStatus(message,stopped?'stopped':'ready','batch');
      query(root,'[data-progress]').textContent=message;
    }
    state.batchRunning=false;refresh();
  }
  function refresh() {
    try{
    root.setAttribute('aria-busy',String(state.busy||state.batchRunning));
    renderRecords();renderActions();renderSelection();renderSecondPass();renderManualQueue();opsPanel.render();
    renderTrialResult();
    query(root,'[data-analyze]').disabled=!state.source||state.busy||state.batchRunning;
    const hubToggle=query(root,'[data-uxml-toggle]');
    if(hubToggle){hubToggle.checked=state.hubEnabled;hubToggle.disabled=state.busy||state.batchRunning;}
    renderHubParity();
    query(root,'[data-cancel]').disabled=
      !(state.busy||state.batchRunning)||state.shortBulkFinalizing||state.fixFinalizing;
    getNodes(root,'[data-auto-fix],[data-close-joint],[data-add-second-pass]').forEach(button=>
      button.disabled=state.busy||state.batchRunning||
        (state.hubEnabled&&(state.hubParity?.status!=='EQUAL'||!button.hasAttribute('data-auto-fix'))));
    getNodes(root,'[data-download-working],[data-download-history]').forEach(button=>
      button.disabled=state.busy||state.batchRunning||!state.revision||!hubCanRelease());
    getNodes(root,'[data-download-fix],[data-download-batch-report]').forEach(button=>
      button.disabled=state.busy||state.batchRunning||!hubCanRelease(true));
    explainDisabledActions();
    }catch(error){
      // A renderer exception cannot strand Busy or preserve a stale hub release.
      const detail='WORKSPACE_REFRESH_ERROR:'+String(error?.message||error);
      try{cancelEngine();}catch{}
      state.epoch++;state.busy=false;state.batchRunning=false;
      state.shortBulkFinalizing=false;state.fixFinalizing=false;
      state.activeJob=null;state.shortBulk=null;state.lastFailure=detail;
      if(state.hubEnabled)holdShortHubRelease(detail);
      try{
        root.setAttribute('aria-busy','false');
        getNodes(root,'[data-download-working],[data-download-history],[data-download-fix],[data-download-batch-report]')
          .forEach(button=>{button.disabled=true;});
        query(root,'[data-cancel]').disabled=true;
        query(root,'[data-progress]').textContent='BULK STOPPED · ERROR · '+detail+
          ' · working revision '+state.revision+' retained.'+
          (state.hubEnabled?' · corrected downloads HELD.':'');
        setFixStatus('ERROR · '+detail+' · last validated revision retained.','rejected');
      }catch{/* already revoked; no secondary render exception escapes */}
    }
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
    // Retire stale progress and Cancel dispatch before the old finally can run.
    state.activeJob=null;
    cancelEngine();
    const generation=++state.epoch;
    state.shortBulk=null;
    state.source=null;state.original=null;state.revision=0;state.hubParity=null;state.hubRevision=null;clearEvidenceProof('EVIDENCE_ANALYSIS_REQUIRED');state.opsPreview=null;state.opsPreviewError=null;state.applied=0;state.history=[];state.resolutions=[];state.shortElements=[];state.shortSelection=null;
    const shortPanel=query(root,'[data-short-preview]');if(shortPanel)shortPanel.textContent='';
    state.manualPorts=[];state.secondPass=null;state.manualQueue=[];
    state.manualQueueCheckpoint=null;state.manualQueueRunning=false;
    state.manualQueueStatus='';state.openRules.clear();state.openCases.clear();
    state.scene=null;state.plan=null;state.findings=[];state.result=null;state.fix=null;state.batch=null;state.gapReviews.clear();
    query(root,'[data-progress]').textContent='Reading original · no repairs applied.';
    query(root,'[data-gap-review-status]').textContent='No review decisions recorded for this file.';
    state.selected.clear();state.busy=false;state.batchRunning=false;canvas.setScene(null);
    query(root,'[data-source-meta]').textContent='Reading '+file.name+'…';
    displayMessage('');setFixStatus('');refresh();
    try {
      const raw=new Uint8Array(await file.arrayBuffer());
      const sourceText=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(raw);
      const sourceSha256=await sha256(new TextEncoder().encode(sourceText));
      const rawSha256=await sha256(raw);
      if(generation!==state.epoch)return;
      const scene=parseOccurrenceScene(sourceText,sourceSha256);
      if(!scene.records.some(r=>r.position))throw Error('No explicit XYZ source positions available');
      state.source={sourceText,sourceSha256,rawSha256,name:file.name};
      state.original={...state.source};
      query(root,'[data-progress]').textContent='Original loaded · revision 0 · no repairs applied.';
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
    state.plan=null;state.findings=[];state.batch=null;state.manualPorts=[];state.secondPass=null;clearEvidenceProof('EVIDENCE_RECHECK_PENDING');state.opsPreview=null;state.opsPreviewError=null;
    query(root,'[data-batch-confirm]').textContent='';setFixStatus('');refresh();updateStatus('Running authoritative PSI116 topology analysis…');
    try {
      const result=await runEngine(readOnlyAnalysisJob(source));
      if(generation!==state.epoch)return;
      recordHubResult(result);
      // DIFFERENT still publishes read-only findings/plan so the Owner sees
      // precisely what disagrees. Only the current connection-evidence proof
      // (and existing hub Auto-fix) is withheld. Do not turn it into analysis
      // failure or hide the source-qualified review cases.
      const current=acceptAnalysis(result,source.sourceSha256);
      state.plan=current.plan;state.findings=current.findings;
      state.resolutions=current.resolutions;state.shortElements=current.shortElements;
      state.manualPorts=current.manualPorts;
      if(!state.hubEnabled||state.hubParity?.status==='EQUAL')
        establishCurrentAnalysisProof(result,{epoch:generation,
          revision:state.revision,sourceRef:source,sourceSha256:source.sourceSha256,
          accepted:current});
      else clearEvidenceProof('EVIDENCE_RECHECK_PARITY_NOT_EQUAL');
      updateStatus('Authoritative topology analysis complete. '+current.plan.actions.length+
        ' plan entries. No Weight/O1/Final/native session was supplied or created.');
    } catch(error) {
      if(generation===state.epoch){
        clearEvidenceProof('EVIDENCE_RECHECK_FAILED:'+String(error?.name||'Error'));
        updateStatus('Topology analysis failed: '+(error?.message||String(error)));
      }
    } finally {
      if(generation===state.epoch){state.busy=false;refresh();}
    }
  }
  const click=async event=>{
    const target=event.target.closest('button');if(!target||!root.contains(target))return;
    // A disabled Cancel is not an authorized action, including injected clicks
    // while completed Apply is still performing its evidence recheck.
    if(target.hasAttribute('data-cancel')&&target.disabled)return;
    if(target.hasAttribute('data-auto-fix-all'))planAutoFixAll();
    else if(target.hasAttribute('data-run-auto-fix-all'))autoFixAll();
    else if(target.hasAttribute('data-cancel-auto-fix-all')){
      state.batch=null;query(root,'[data-batch-confirm]').textContent='';
    }
    else if(target.hasAttribute('data-save-gap-review'))saveGapReview(target);
    else if(target.hasAttribute('data-download-gap-review'))downloadGapReview();
    else if(target.hasAttribute('data-close-joint'))closeJoint(target);
    else if(target.hasAttribute('data-add-second-pass'))beginSecondPass(target.dataset.addSecondPass);
    else if(target.hasAttribute('data-queue-second'))queueSecondPass();
    else if(target.hasAttribute('data-queue-apply'))applyManualQueue();
    else if(target.hasAttribute('data-queue-remove')){
      state.manualQueue=state.manualQueue.filter(x=>x.id!==target.dataset.queueRemove);
      state.manualQueueStatus='Queued pair removed; source XML unchanged.';renderManualQueue();
    }
    else if(target.hasAttribute('data-queue-clear')){
      state.manualQueue=[];state.manualQueueStatus='Queue cleared; source XML unchanged.';
      renderManualQueue();
    }
    else if(target.hasAttribute('data-preview-second'))previewSecondPass();
    else if(target.hasAttribute('data-apply-second'))applySecondPass();
    else if(target.hasAttribute('data-cancel-second')){state.secondPass=null;renderSecondPass();}
    else if(target.hasAttribute('data-second-use-selection'))useSelectedPartner();
    else if(target.hasAttribute('data-second-locate')){
      const d=state.secondPass;if(d){const ids=[d.sourceKey,d.peerKey].map(k=>state.scene.byKey.get(k)?.id).filter(Boolean);select(ids);canvas.focus(ids);}
    }
    else if(target.hasAttribute('data-rules-expand')||target.hasAttribute('data-rules-collapse')){
      const open=target.hasAttribute('data-rules-expand');
      const rules=getNodes(root,'.audit-rule');state.openRules.set(state.filter,new Set(open?rules.map(r=>r.dataset.ruleCode):[]));
      rules.forEach(r=>r.open=open);
    }
    else if(target.hasAttribute('data-select-short'))selectShortElements();
    else if(target.hasAttribute('data-select-gaskets')){
      const p=state.shortSelection;if(!p||state.busy||state.batchRunning)return;
      for(const r of state.shortElements)if(r.eligible&&r.componentType==='GASK')p.selected.add(r.id);
      renderShortSelection();
    }
    else if(target.hasAttribute('data-short-prev')){
      if(state.shortSelection&&!state.busy&&!state.batchRunning){state.shortSelection.page--;renderShortSelection();}
    }
    else if(target.hasAttribute('data-short-next')){
      if(state.shortSelection&&!state.busy&&!state.batchRunning){state.shortSelection.page++;renderShortSelection();}
    }
    else if(target.hasAttribute('data-short-independent')){
      if(!state.busy&&!state.batchRunning){
        state.independentShortGroups=!!target.checked;
        renderShortSelection();
      }
    }
    else if(target.hasAttribute('data-run-short-drop'))dropShortElements();
    else if(target.hasAttribute('data-analyze'))analyze();
    else if(target.hasAttribute('data-cancel')&&state.fixFinalizing){
      return; // completed native fix cannot be cancelled mid-publication
    }
    else if(target.hasAttribute('data-cancel')&&state.shortBulkFinalizing){
      // Native Apply is complete; recheck is still running. Preserve
      // the truthful terminal status and committed working revisions.
      return;
    }
    else if(target.hasAttribute('data-cancel')&&state.manualQueueRunning){
      const saved=state.manualQueueCheckpoint;
      cancelEngine();state.epoch++;state.busy=false;
      state.batchRunning=false;state.manualQueueRunning=false;
      state.manualQueueCheckpoint=null;
      await publishManualQueue({...saved,stopReason:'CANCELLED',
        message:'Operator cancelled. Last validated checkpoint retained.'},state.epoch);
      refresh();
    }
    else if(target.hasAttribute('data-cancel')&&state.shortBulk){
      // Terminate current Worker, then publish ONLY the last pre-Final-verified
      // checkpoint. Do not invoke a second engine run or leave a half-applied UI.
      const saved=state.shortBulk;
      cancelEngine();state.epoch++;state.busy=false;state.batchRunning=false;
      state.activeJob=null;
      state.shortBulk=null;
      await publishShortBulkGuarded({...saved,stopReason:'CANCELLED',
        stopMessage:'User cancelled active batch'},state.epoch);
      refresh();
    }
    else if(target.hasAttribute('data-cancel')){cancelEngine();state.secondPass=null;state.shortSelection=null;
      query(root,'[data-short-preview]').textContent='';state.epoch++;state.busy=false;state.batchRunning=false;state.activeJob=null;refresh();
      state.batch=null;query(root,'[data-batch-confirm]').textContent='';
      query(root,'[data-progress]').textContent='CANCELLED · working revision '+state.revision+' retained.';
      setFixStatus('Operation cancelled. No new working revision applied.','rejected');
      updateStatus('Pending result invalidated. Current working revision retained.');}
    else if(target.hasAttribute('data-occ-id')){select([target.dataset.occId],event.shiftKey);displayMessage('');}
    else if(target.hasAttribute('data-hit-id')){select([target.dataset.hitId],event.shiftKey);displayMessage('');}
    else if(target.hasAttribute('data-audit-filter')){
      state.filter=target.dataset.auditFilter;renderActions();
    }
    else if(target.hasAttribute('data-what-left')){
      const groups=trialRemaining(buildAudit(state.findings,state.plan?.actions||[]));
      const first=groups[target.dataset.whatLeft]?.[0];
      if(first)visitTrialFinding(first.finding.finding_id);
    }
    else if(target.hasAttribute('data-trial-step')){
      const groups=trialRemaining(buildAudit(state.findings,state.plan?.actions||[]));
      const rows=groups[target.dataset.trialGroup]||[];
      const index=rows.findIndex(row=>row.finding.finding_id===target.dataset.trialId);
      const next=rows[index+Number(target.dataset.trialStep)];
      if(index>=0&&next)visitTrialFinding(next.finding.finding_id);
    }
    else if(target.hasAttribute('data-trial-current'))downloadCurrent();
    else if(target.hasAttribute('data-trial-history'))downloadCurrent(true);
    else if(target.hasAttribute('data-trial-evidence'))downloadResolutions();
    else if(target.hasAttribute('data-download-batch-report'))downloadBatchReport();
    else if(target.hasAttribute('data-download-working'))downloadCurrent();
    else if(target.hasAttribute('data-download-history'))downloadCurrent(true);
    else if(target.hasAttribute('data-download-resolutions'))downloadResolutions();
    else if(target.hasAttribute('data-resolved-index')){
      const row=state.resolutions[Number(target.dataset.resolvedIndex)];
      const ids=(row?.node_keys||[]).map(k=>state.scene.byKey.get(k)?.id).filter(Boolean);
      select(ids);canvas.focus(ids);
    }
    else if(target.hasAttribute('data-download-fix'))downloadFix();
    else if(target.hasAttribute('data-auto-fix'))autoFix(target.dataset.autoFix);
    else if(target.hasAttribute('data-audit-action')){
      const action=state.plan?.actions.find(a=>a.action_id===target.dataset.auditAction);
      const ids=affectedOccurrenceIds(action,state.findings,state.scene);
      if(ids.length){select(ids);canvas.focus(ids);displayMessage('Source-qualified witnesses: '+ids.length);}
      else displayMessage('No authoritative node keys; no guessed location.');
    }
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
    if(event.target.matches('[data-short-index]')&&!state.busy&&!state.batchRunning){
      const p=state.shortSelection,r=state.shortElements[Number(event.target.dataset.shortIndex)];
      if(p&&r?.eligible&&p.epoch===state.epoch&&p.sha===state.source?.sourceSha256){
        if(event.target.checked)p.selected.add(r.id);else p.selected.delete(r.id);
        renderShortSelection();
      }
    }
    const d=state.secondPass;
    if(d&&!state.busy&&!state.batchRunning&&
       event.target.matches('[data-second-source],[data-second-peer]')){
      if(event.target.matches('[data-second-source]')){d.sourceKey=event.target.value;d.peerKey='';}
      else d.peerKey=event.target.value;
      d.preview=null;d.confirmed=false;d.status='Selection changed. Preview this exact pair before applying.';renderSecondPass();
    }
    if(d&&!state.busy&&!state.batchRunning&&event.target.matches('[data-second-confirm]')){d.confirmed=event.target.checked;updateSecondApply();}
    if(event.target.matches('[data-file]')&&event.target.files?.[0]){
      const file=event.target.files[0];event.target.value='';load(file);
    }
    if(event.target.matches('[data-uxml-toggle]')){
      if(state.busy||state.batchRunning){event.target.checked=state.hubEnabled;return;}
      state.hubEnabled=event.target.checked;state.hubParity=null;clearEvidenceProof('EVIDENCE_ANALYSIS_REQUIRED');state.opsPreview=null;state.opsPreviewError=null;
      state.shortSelection=null;
      query(root,'[data-short-preview]').textContent='';
      opsPanel.reset();
      renderHubParity();renderActions();refresh();
      updateStatus(state.hubEnabled?
        'Universal XML preview ON. Select Analyze to verify the pinned reader.':
        'Universal XML preview OFF. Direct PSI116 route available.');
    }
    if(event.target.matches('[data-audit-category]')){state.category=event.target.value;renderActions();}
    if(event.target.matches('[data-helpers]'))canvas.setShowHelpers(event.target.checked);
    if(event.target.matches('[data-labels]'))canvas.setShowLabels(event.target.checked);
  };
  const input=event=>{
    const d=state.secondPass;
    if(d&&event.target.matches('[data-second-evidence]')){d.evidence=event.target.value;updateSecondApply();}
    if(d&&event.target.matches('[data-second-search]')){
      d.search=event.target.value;const position=event.target.selectionStart;renderSecondPass();
      const input=query(root,'[data-second-search]');input.focus();input.setSelectionRange(position,position);
    }
    if(event.target.matches('[data-search]')){state.search=event.target.value.trim();renderRecords();renderActions();}
  };
  const toggled=event=>{
    if(!event.target.isConnected)return;
    if(event.target.matches('.audit-rule')){
      const set=state.openRules.get(state.filter)||new Set(getNodes(root,'.audit-rule[open]').map(r=>r.dataset.ruleCode));
      if(event.target.open)set.add(event.target.dataset.ruleCode);else set.delete(event.target.dataset.ruleCode);
      state.openRules.set(state.filter,set);
    }
    if(event.target.matches('.audit-case')){
      if(event.target.open)state.openCases.add(event.target.dataset.caseId);else state.openCases.delete(event.target.dataset.caseId);
    }
  };
  root.addEventListener('toggle',toggled,true);
  root.addEventListener('click',click);root.addEventListener('change',changed);
  root.addEventListener('input',input);refresh();
  return {getState:()=>({sourceSha256:state.source?.sourceSha256||null,revision:state.revision,applied:state.applied,
    occurrences:state.scene?.records.length||0,actions:state.plan?.actions.length||0,
    selected:[...state.selected],busy:state.busy,
    hubEnabled:state.hubEnabled,hubParity:state.hubParity?.status||'OFF',
    hubRevision:state.hubRevision,activeJob:state.activeJob,
    shortBulkFinalizing:state.shortBulkFinalizing,fixFinalizing:state.fixFinalizing,
    queued:state.manualQueue.map(x=>({id:x.id,status:x.status})),queueBusy:state.manualQueueRunning}),load,analyze,
    dispose(){
      state.activeJob=null;
      cancelEngine();ownedWorker?.dispose();state.epoch++;
      opsPanel.dispose();canvas.dispose();root.removeEventListener('toggle',toggled,true);root.removeEventListener('click',click);
      root.removeEventListener('change',changed);root.removeEventListener('input',input);}};
}
const root=document.querySelector('#xml229-topology-workspace');
if(root)mountTopologyWorkspace(root);
