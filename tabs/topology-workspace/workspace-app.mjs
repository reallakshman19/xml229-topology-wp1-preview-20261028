/** XML229 WP1: standalone source-only topology inspection; no engineering acceptance. */
import {createTopologyWorkerClient} from './topology-worker-client.mjs';
import {parseOccurrenceScene, affectedOccurrenceIds, escapeValue as esc} from './occurrence-scene.mjs';
import {createTopologyCanvas} from './projected-canvas.mjs';
import {buildAudit,renderAuditHTML,renderAuditSummary,filterCounts} from './audit-view.mjs';
import {eligibleActions,previewBatchPlan,explicitlyRejectedActionIds} from './batch-plan.mjs';
import {runValidatedPasses} from './batch-runner.mjs';
import {runShortBulk} from './short-bulk.mjs';
import {secondPassHTML} from './second-pass.mjs';

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
  const state={epoch:0,source:null,original:null,revision:0,applied:0,history:[],resolutions:[],shortElements:[],shortPreview:null,scene:null,plan:null,findings:[],result:null,
    selected:new Set(),search:'',filter:'all',category:'all',manualPorts:[],secondPass:null,openRules:new Map(),openCases:new Set(),fix:null,batch:null,gapReviews:new Map(),busy:false,batchRunning:false,shortBulk:null};
  const canvas=createTopologyCanvas(query(root,'[data-canvas]'),onHits);
  const updateStatus=message=>{query(root,'[data-status]').textContent=message;};
  const displayMessage=message=>{query(root,'[data-hits]').textContent=message;};
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
    const shortButton=query(root,'[data-preview-short]');
    if(shortButton)shortButton.disabled=!state.plan||state.busy||state.batchRunning;
    const plan=state.plan;
    const summary=query(root,'[data-plan-summary]');
    const panel=query(root,'[data-issues]');
    const resolved=query(root,'[data-resolved]');
    if(resolved)resolved.innerHTML=state.resolutions.length?
      '<details><summary>'+state.resolutions.length+' connections / terminations automatically resolved · source evidence</summary><ul>'+
      state.resolutions.map((r,i)=>'<li><button data-resolved-index="'+i+'">'+esc(r.code.replaceAll('_',' '))+
        ' · '+esc(r.node_keys.join(', '))+'</button><p>'+esc(r.message)+'</p></li>').join('')+'</ul></details>':'';
    const evidence=query(root,'[data-download-resolutions]');
    if(evidence)evidence.disabled=!state.plan||state.busy;
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
      return;
    }
    const audit=buildAudit(state.findings,plan.actions||[]);
    summary.textContent=renderAuditSummary(audit);
    const visible=renderAuditHTML(audit,{search:state.search,filter:state.filter,
      category:state.category,reviews:Object.fromEntries(state.gapReviews),
      sourceByKey:state.scene?.byKey,openRules:state.openRules.get(state.filter)||null,openCases:state.openCases});
    panel.innerHTML=visible.html;
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
      batchButton.disabled=state.busy||state.batchRunning||allowed.length===0;
      batchButton.textContent='Autofix-All ('+allowed.length+' actions)';
    }
  }
  function setFixStatus(message,kind='info',actionId=''){
    const panel=query(root,'[data-fix-result]');
    if(!panel)return;
    panel.setAttribute('data-result',kind);
    panel.textContent=message;
    if(['ready','stopped','rejected'].includes(kind)&&state.fix?.sourceSha256===state.source?.sourceSha256){
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
    if(!fix?.report||fix.sourceSha256!==state.source?.sourceSha256)return;
    const filename=(state.source.name.replace(/\\.xml$/i,'')||'input')+
      '.autofix-batch-report.json';
    const url=URL.createObjectURL(new Blob([JSON.stringify(fix.report,null,2)],
      {type:'application/json'}));
    const a=document.createElement('a');
    a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function downloadFix(){
    if(!state.fix||state.fix.sourceSha256!==state.source?.sourceSha256)return;
    const blob=new Blob([state.fix.xml],{type:'application/xml;charset=utf-8'});
    const url=URL.createObjectURL(blob);
    const anchor=document.createElement('a');
    anchor.href=url;anchor.download=state.fix.name;
    document.body.appendChild(anchor);anchor.click();anchor.remove();
    window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function downloadCurrent(history=false){
    if(!state.source||!state.revision)return;
    const body=history?JSON.stringify({schema:'topofix-working-history/v1',
      originalSha256:state.original.sourceSha256,currentSha256:state.source.sourceSha256,
      revision:state.revision,repairs:state.history},null,2):state.source.sourceText;
    const a=document.createElement('a'),url=URL.createObjectURL(new Blob([body],
      {type:history?'application/json':'application/xml'}));
    a.href=url;a.download=state.source.name+'.revision-'+state.revision+(history?'.repairs.json':'.topofix.xml');
    document.body.appendChild(a);a.click();a.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function downloadResolutions(){
    if(!state.source||!state.plan)return;
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
    if(!state.source||state.busy||(state.batchRunning&&receiptKey!=='batch')||!ids.length||(joint&&drop)||(!joint&&!drop&&ids.some(id=>!allowed.has(id)))){
      setFixStatus('Auto fix is not authorized for this selection. No XML was modified.','rejected');
      return;
    }
    const generation=state.epoch,source=state.source,batch=receiptKey==='batch';
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
            topologyJointRepairs:jointRepairs,topologyShortElementRequests:shortElementRequests}});
        if(generation!==state.epoch)return;
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
      const nextSource={...source,sourceText:result.topoFixXmlText,sourceSha256:fixedSha};
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
          useTopoFixForCii:false,topologyActionIds:[]}});
      if(generation!==state.epoch)return;
      const current=acceptAnalysis(recheck,fixedSha);
      const priorReviews=Object.fromEntries(state.gapReviews);
      state.source=nextSource;state.scene=nextScene;state.plan=current.plan;
      state.resolutions=current.resolutions;
      state.shortElements=current.shortElements;state.shortPreview=null;state.manualPorts=current.manualPorts;state.secondPass=null;state.openCases.clear();
      const shortPanel=query(root,'[data-short-preview]');if(shortPanel)shortPanel.textContent='';
      state.findings=current.findings;state.result=recheck;state.selected.clear();state.gapReviews.clear();
      state.selected=new Set(changedIds);
      state.revision++;state.applied+=ids.length;
      state.history.push({sourceSha256:source.sourceSha256,fixedSha256:fixedSha,
        actionIds:ids,operations:txn.operations,validation:validation.checks,jointRepairs,reviews:priorReviews,
        resolvedConnections:current.resolutions});
      canvas.setScene(nextScene);sourceMeta();
      query(root,'[data-gap-review-status]').textContent='Working copy changed. Prior source review notes are in the repair history; review current findings.';
      query(root,'[data-progress]').textContent='APPLIED · revision '+state.revision+' · '+
        state.applied+' action(s) applied · findings '+beforeCount+' → '+current.findings.length+
        ' after full recheck. Canvas and counts show the corrected working copy.';
      state.fix={sourceSha256:fixedSha,receiptKey,actionIds:ids,
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
    }catch(error){
      if(generation===state.epoch){
        const detail=error?.message||String(error);
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
      if(generation===state.epoch){state.busy=false;state.batch=null;
        query(root,'[data-batch-confirm]').textContent='';refresh();}
    }
  }
  function autoFix(actionId){return runFix([actionId],'single');}

  // This preview is only a view of source-qualified data already received.
  // Paginate so one click never constructs an unbounded DOM tree.
  const SHORT_PREVIEW_PAGE_SIZE=24;
  function renderShortPreview(){
    const p=state.shortPreview,panel=query(root,'[data-short-preview]');
    if(!p||!state.source||p.sha!==state.source.sourceSha256){panel.textContent='';return;}
    const rows=state.shortElements,total=rows.length;
    const pages=Math.max(1,Math.ceil(total/SHORT_PREVIEW_PAGE_SIZE));
    p.page=Math.max(0,Math.min(p.page,pages-1));
    const start=p.page*SHORT_PREVIEW_PAGE_SIZE;
    const visible=rows.slice(start,start+SHORT_PREVIEW_PAGE_SIZE);
    const eligible=rows.filter(r=>r.eligible).length;
    panel.innerHTML='<h3>Drop elements ≤6 mm, then close</h3>'+
      '<p role="status">PREVIEW ONLY · '+total+' measured candidates · '+eligible+
      ' eligible under source checks · working XML unchanged. Select source owners, then explicitly Apply.</p>'+
      '<p data-short-selection-count>'+p.selected.size+' selected · page '+(p.page+1)+' of '+pages+'</p>'+
      '<button data-select-gaskets>Select eligible gaskets (all pages)</button>'+
      '<ul>'+visible.map((r,i)=>'<li><label><input type="checkbox" data-short-index="'+(start+i)+'" '+
        (!r.eligible?'disabled ':'')+(p.selected.has(r.id)?'checked ':'')+'>'+
        esc(r.componentType+' · '+Number(r.lengthMm).toFixed(3)+' mm'+
        (r.lengthBasis==='SOURCE_STRAIGHT_TWO_PORT_SPAN'?'':' source span; physical length unverified')+
        ' · '+r.componentRefNo+' · '+r.recordCount+' records · weight '+r.weightRemoved)+
        '</label><small>'+esc((r.nodeKeys||[]).join(', ')+' · '+
        (r.eligible?'Length basis: straight port spacing':r.reason||'Manual review'))+
        '</small></li>').join('')+'</ul>'+
      '<div class="short-preview-pagination"><button data-short-prev '+(!p.page?'disabled':'')+'>Previous</button>'+
      '<button data-short-next '+(p.page>=pages-1?'disabled':'')+'>Next</button></div>'+
      (total?'<button data-run-short-drop '+(!p.selected.size?'disabled':'')+
        '>Apply all '+p.selected.size+' selected &amp; close</button>':
        '<p>No measurable two-port elements at ≤6 mm.</p>')+
      '<p>One source-bound transaction and recheck per element. Cancel at any point; only validated revisions are retained.</p>';
  }
  function previewShortElements(){
    if(!state.source||!state.plan||state.busy||state.batchRunning)return;
    state.shortPreview={sha:state.source.sourceSha256,epoch:state.epoch,page:0,selected:new Set()};
    renderShortPreview();
    query(root,'[data-short-preview]').scrollIntoView({block:'nearest'});
  }

  /** One UI publication for a fully audited sequence (or last validated checkpoint).
   * Never call runFix() or repaint the canvas per selected element.
   */
  function publishShortBulk(outcome){
    if(!outcome||outcome.originSha256!==state.source?.sourceSha256)
      throw Error('SHORT_BULK_ORIGINAL_SOURCE_DRIFT');
    const beforeCount=state.findings.length,applied=outcome.applied||[];
    if(outcome.latest&&applied.length){
      const next=outcome.latest;
      const scene=parseOccurrenceScene(next.source.sourceText,next.source.sourceSha256);
      const previous=state.source;
      const reviews=Object.fromEntries(state.gapReviews);
      state.source=next.source;
      state.scene=scene;state.plan=next.plan;state.findings=next.findings.findings;
      state.resolutions=next.findings.resolvedConnections||[];
      state.shortElements=next.findings.shortElements||[];
      state.manualPorts=next.findings.manualConnectionPorts||[];
      state.secondPass=null;state.shortPreview=null;state.selected.clear();
      state.gapReviews.clear();state.openCases.clear();
      query(root,'[data-short-preview]').textContent='';
      for(const [i,pass] of applied.entries()){
        state.history.push({sourceSha256:pass.sourceSha256,fixedSha256:pass.fixedSha256,
          actionIds:[pass.id],operations:pass.transaction.operations,validation:pass.validation.checks,
          reviews:i===0?reviews:{},resolvedConnections:i===applied.length-1?state.resolutions:[]});
      }
      state.revision+=applied.length;
      state.applied+=applied.length;
      state.fix={sourceSha256:state.source.sourceSha256,receiptKey:'drop',
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
    const reason=outcome.stopReason||'COMPLETE';
    const message=(reason==='COMPLETE'?'BULK COMPLETE':'BULK STOPPED · '+reason)+
      ' · selected '+selected+' = '+done+' validated + '+skipped+' skipped + '+failed+
      ' failed + '+unprocessed+' unprocessed · eligible on CURRENT XML '+nowEligible+
      ' · working revision '+state.revision+
      (outcome.stopMessage?' · '+outcome.stopMessage:'')+
      (done?' · validated XML, source-linked operations and lineage digests downloadable.':' · no XML changed.');
    query(root,'[data-progress]').textContent=message;
    setFixStatus(message,reason==='COMPLETE'&&done?'ready':done?'stopped':'rejected','drop');
    updateStatus('Selected short-element batch finished. '+done+
      ' validated; '+skipped+' not eligible on reanalysis. Engineering review remains required.');
  }
  async function dropShortElements(){
    const p=state.shortPreview;
    if(state.busy||state.batchRunning||!p||p.epoch!==state.epoch||
       p.sha!==state.source?.sourceSha256)return;
    const eligibleIds=new Set(state.shortElements.filter(r=>r.eligible).map(r=>r.id));
    const ids=[...p.selected].filter(id=>eligibleIds.has(id));
    if(!ids.length){setFixStatus('Select at least one source-qualified element.','rejected');return;}
    const generation=state.epoch,source={...state.source};
    state.batchRunning=true;state.shortBulk=null;refresh();
    const startedAt=Date.now();
    let lastBulkStatus='STARTING',lastCompleted=0,lastApplied=0,lastSkipped=0;
    const paintBulkProgress=()=>{
      if(generation!==state.epoch||!state.batchRunning)return;
      const elapsed=Math.floor((Date.now()-startedAt)/1000);
      query(root,'[data-progress]').textContent=
        'BULK '+lastBulkStatus+' · '+lastCompleted+'/'+ids.length+
        ' selected checked · '+lastApplied+' validated · '+lastSkipped+' skipped · '+
        elapsed+' s elapsed · audit/canvas show PRE-BATCH REVISION '+state.revision+
        ' (frozen snapshot until final publication). Cancel remains available.';
    };
    const heartbeat=setInterval(paintBulkProgress,1000);
    query(root,'[data-progress]').textContent=
      'BULK STARTED · 0/'+ids.length+' selected checked. Audit counts and canvas are PRE-BATCH SNAPSHOT at revision '+
      state.revision+'. Python validates each owner headlessly; canvas refreshes after the batch.';
    try{
      const outcome=await runShortBulk({
        source,shortElements:state.shortElements,selectedIds:ids,runEngine,
        isCurrent:()=>generation===state.epoch,
        onCheckpoint:checkpoint=>{if(generation===state.epoch)state.shortBulk=checkpoint;},
        onProgress:step=>{
          if(generation!==state.epoch)return;
          lastBulkStatus=step.status;
          lastCompleted=step.completed;lastApplied=step.applied;lastSkipped=step.skipped;
          paintBulkProgress();
        },
      });
      if(generation!==state.epoch)return;
      state.shortBulk=null;
      publishShortBulk(outcome);
    }catch(error){
      if(generation!==state.epoch)return;
      const checkpoint=state.shortBulk||{originSha256:source.sourceSha256,latest:null,
        applied:[],skipped:[],requested:ids,completed:0};
      state.shortBulk=null;
      publishShortBulk({...checkpoint,stopReason:'ERROR',stopMessage:error?.message||String(error)});
    }finally{
      clearInterval(heartbeat);
      if(generation===state.epoch){state.batchRunning=false;state.shortBulk=null;refresh();}
    }
  }
  function renderSecondPass(){
    const panel=query(root,'[data-second-pass]');if(!panel)return;
    panel.hidden=!state.secondPass;
    panel.innerHTML=secondPassHTML(state.secondPass?{...state.secondPass,busy:state.busy||state.batchRunning}:null,state.scene,state.manualPorts);
  }
  function updateSecondApply(){
    const d=state.secondPass,button=query(root,'[data-apply-second]');
    if(button)button.disabled=state.busy||!d?.preview||!d.confirmed||d.evidence.trim().length<10;
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
    root.setAttribute('aria-busy',String(state.busy||state.batchRunning));
    renderRecords();renderActions();renderSelection();renderSecondPass();
    query(root,'[data-analyze]').disabled=!state.source||state.busy||state.batchRunning;
    query(root,'[data-cancel]').disabled=!(state.busy||state.batchRunning);
    getNodes(root,'[data-auto-fix],[data-close-joint],[data-add-second-pass]').forEach(button=>button.disabled=state.busy||state.batchRunning);
    getNodes(root,'[data-download-working],[data-download-history]').forEach(button=>button.disabled=state.busy||!state.revision);
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
    cancelEngine();
    const generation=++state.epoch;
    state.shortBulk=null;
    state.source=null;state.original=null;state.revision=0;state.applied=0;state.history=[];state.resolutions=[];state.shortElements=[];state.shortPreview=null;
    const shortPanel=query(root,'[data-short-preview]');if(shortPanel)shortPanel.textContent='';
    state.manualPorts=[];state.secondPass=null;state.openRules.clear();state.openCases.clear();
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
    state.plan=null;state.findings=[];state.batch=null;state.manualPorts=[];state.secondPass=null;
    query(root,'[data-batch-confirm]').textContent='';setFixStatus('');refresh();updateStatus('Running authoritative PSI116 topology analysis…');
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
      state.resolutions=findings.resolvedConnections||[];
      state.shortElements=findings.shortElements||[];state.manualPorts=findings.manualConnectionPorts||[];
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
    if(target.hasAttribute('data-auto-fix-all'))planAutoFixAll();
    else if(target.hasAttribute('data-run-auto-fix-all'))autoFixAll();
    else if(target.hasAttribute('data-cancel-auto-fix-all')){
      state.batch=null;query(root,'[data-batch-confirm]').textContent='';
    }
    else if(target.hasAttribute('data-save-gap-review'))saveGapReview(target);
    else if(target.hasAttribute('data-download-gap-review'))downloadGapReview();
    else if(target.hasAttribute('data-close-joint'))closeJoint(target);
    else if(target.hasAttribute('data-add-second-pass'))beginSecondPass(target.dataset.addSecondPass);
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
    else if(target.hasAttribute('data-preview-short'))previewShortElements();
    else if(target.hasAttribute('data-select-gaskets')){
      const p=state.shortPreview;if(!p)return;
      for(const r of state.shortElements)if(r.eligible&&r.componentType==='GASK')p.selected.add(r.id);
      renderShortPreview();
    }
    else if(target.hasAttribute('data-short-prev')){
      if(state.shortPreview){state.shortPreview.page--;renderShortPreview();}
    }
    else if(target.hasAttribute('data-short-next')){
      if(state.shortPreview){state.shortPreview.page++;renderShortPreview();}
    }
    else if(target.hasAttribute('data-run-short-drop'))dropShortElements();
    else if(target.hasAttribute('data-analyze'))analyze();
    else if(target.hasAttribute('data-cancel')&&state.shortBulk){
      // Terminate current Worker, then publish ONLY the last pre-Final-verified
      // checkpoint. Do not invoke a second engine run or leave a half-applied UI.
      const saved=state.shortBulk;
      cancelEngine();state.epoch++;state.busy=false;state.batchRunning=false;
      state.shortBulk=null;
      publishShortBulk({...saved,stopReason:'CANCELLED',stopMessage:'User cancelled active batch'});
      refresh();
    }
    else if(target.hasAttribute('data-cancel')){cancelEngine();state.secondPass=null;state.shortPreview=null;
      query(root,'[data-short-preview]').textContent='';state.epoch++;state.busy=false;state.batchRunning=false;refresh();
      state.batch=null;query(root,'[data-batch-confirm]').textContent='';
      query(root,'[data-progress]').textContent='CANCELLED · working revision '+state.revision+' retained.';
      setFixStatus('Operation cancelled. No new working revision applied.','rejected');
      updateStatus('Pending result invalidated. Current working revision retained.');}
    else if(target.hasAttribute('data-occ-id')){select([target.dataset.occId],event.shiftKey);displayMessage('');}
    else if(target.hasAttribute('data-hit-id')){select([target.dataset.hitId],event.shiftKey);displayMessage('');}
    else if(target.hasAttribute('data-audit-filter')){
      state.filter=target.dataset.auditFilter;renderActions();
    }
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
    if(event.target.matches('[data-short-index]')){
      const p=state.shortPreview,r=state.shortElements[Number(event.target.dataset.shortIndex)];
      if(p&&r?.eligible&&p.epoch===state.epoch&&p.sha===state.source?.sourceSha256){
        if(event.target.checked)p.selected.add(r.id);else p.selected.delete(r.id);
        const status=query(root,'[data-short-selection-count]');
        if(status)status.textContent=p.selected.size+' selected · page '+(p.page+1);
        const run=query(root,'[data-run-short-drop]');
        if(run){run.disabled=!p.selected.size;run.textContent='Apply all '+p.selected.size+' selected & close';}
      }
    }
    const d=state.secondPass;
    if(d&&event.target.matches('[data-second-source],[data-second-peer]')){
      if(event.target.matches('[data-second-source]')){d.sourceKey=event.target.value;d.peerKey='';}
      else d.peerKey=event.target.value;
      d.preview=null;d.confirmed=false;d.status='Selection changed. Preview this exact pair before applying.';renderSecondPass();
    }
    if(d&&event.target.matches('[data-second-confirm]')){d.confirmed=event.target.checked;updateSecondApply();}
    if(event.target.matches('[data-file]')&&event.target.files?.[0]){
      const file=event.target.files[0];event.target.value='';load(file);
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
    selected:[...state.selected],busy:state.busy}),load,analyze,
    dispose(){cancelEngine();ownedWorker?.dispose();state.epoch++;canvas.dispose();root.removeEventListener('toggle',toggled,true);root.removeEventListener('click',click);
      root.removeEventListener('change',changed);root.removeEventListener('input',input);}};
}
const root=document.querySelector('#xml229-topology-workspace');
if(root)mountTopologyWorkspace(root);
