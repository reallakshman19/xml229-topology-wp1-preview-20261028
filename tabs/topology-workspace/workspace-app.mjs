/** XML229 WP1: standalone source-only topology inspection; no engineering acceptance. */
import {runXmlCii2019StandaloneEngineJob} from '../xml-cii-2019-standalone/xml-cii-workflow-engine-client.js';
import {parseOccurrenceScene, affectedOccurrenceIds, escapeValue as esc} from './occurrence-scene.mjs';
import {createTopologyCanvas} from './projected-canvas.mjs';
import {buildAudit,renderAuditHTML,renderAuditSummary,filterCounts} from './audit-view.mjs';
import {eligibleActions,previewBatchPlan,explicitlyRejectedActionIds} from './batch-plan.mjs';

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
  const state={epoch:0,source:null,original:null,revision:0,applied:0,history:[],resolutions:[],scene:null,plan:null,findings:[],result:null,
    selected:new Set(),search:'',filter:'all',category:'all',fix:null,batch:null,gapReviews:new Map(),busy:false,batchRunning:false};
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
    return {plan,findings:findings.findings,resolutions:findings.resolvedConnections||[]};
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
      sourceByKey:state.scene?.byKey});
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
      batchButton.disabled=state.busy||allowed.length===0;
      batchButton.textContent='Autofix-All ('+allowed.length+' actions)';
    }
  }
  function setFixStatus(message,kind='info',actionId=''){
    const panel=query(root,'[data-fix-result]');
    if(!panel)return;
    panel.setAttribute('data-result',kind);
    panel.textContent=message;
    if(kind==='ready'&&state.fix?.receiptKey===actionId){
      const button=document.createElement('button');
      button.type='button';button.setAttribute('data-download-fix','');
      button.textContent='Download validated corrected XML';
      panel.appendChild(button);
      if(state.fix.report){
        const receipt=document.createElement('button');
        receipt.type='button';receipt.dataset.downloadBatchReport='';
        receipt.textContent='Download bulk audit / excluded actions';
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
  async function runFix(actionIds,receiptKey='single',jointRepairs=[]){
    const allowed=new Set(eligibleActions(state.findings,state.plan?.actions||[])
      .map(a=>a.action_id));
    let ids=[...new Set(actionIds)].sort();
    const joint=jointRepairs.length===1&&ids.length===1&&
      ids[0]==='JOIN:'+jointRepairs[0].findingId+':'+jointRepairs[0].moveKey;
    if(!state.source||state.busy||!ids.length||(!joint&&ids.some(id=>!allowed.has(id)))){
      setFixStatus('Auto fix is not authorized for this selection. No XML was modified.','rejected');
      return;
    }
    const generation=state.epoch,source=state.source,batch=receiptKey==='batch';
    const skippedByPlan=batch?[...(state.batch?.skipped||[])]:[];
    const skippedByEngine=[];
    state.busy=true;state.fix=null;refresh();
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
            topologyJointRepairs:jointRepairs}});
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
      const suffix=batch?'batch-'+ids.length:joint?'joint-closure':'single-fix';
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
        report:batch?{schema:'xml229-preview-batch-topofix/v1',
          status:'VALIDATED_COPY_NOT_ENGINEERING_ACCEPTANCE',
          source:{name:source.name,sha256:source.sourceSha256},
          fixedXmlSha256:fixedSha,
          proposedMutationCount:proposed,
          selectedActionIds:ids,excludedActions:excluded,
          validationChecks:validation.checks}:null};
      setFixStatus('APPLIED to working copy: '+ids.length+' action(s), '+
        validation.checks.length+' validation checks, output SHA256 '+fixedSha+
        (batch?' · '+excluded.length+' excluded from bulk; see batch report.':'')+
        '. Canvas and counts rechecked. Download the validated copy for review. Original unchanged; '+
        'not connectivity certification or engineering acceptance.','ready',receiptKey);
      updateStatus('Repair applied and rechecked. Working revision '+state.revision+'.');
    }catch(error){
      if(generation===state.epoch){
        query(root,'[data-progress]').textContent='NOT APPLIED · '+(error?.message||String(error))+
          ' · working revision '+state.revision+' retained.';
        setFixStatus('Auto fix NOT applied: '+
        (error?.message||String(error))+'. No corrected XML is available. '+
        'Current working revision retained.','rejected');
      }
    }finally{
      if(generation===state.epoch){state.busy=false;state.batch=null;
        query(root,'[data-batch-confirm]').textContent='';refresh();}
    }
  }
  function autoFix(actionId){return runFix([actionId],'single');}
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
    const seen=new Set([initialSha]),passes=[];
    let lastFix=null;
    for(let pass=0;pass<8;pass++){
      const beforeRevision=state.revision;
      await runFix(state.batch.actionIds,'batch');
      if(generation!==state.epoch)return;
      if(state.revision===beforeRevision)break;
      lastFix=state.fix;passes.push(lastFix.report);
      if(seen.has(state.source.sourceSha256))break;
      seen.add(state.source.sourceSha256);
      const next=previewBatchPlan(state.findings,state.plan.actions,state.scene.byKey);
      if(!next.actionIds.length)break;
      state.batch={...next,sourceSha256:state.source.sourceSha256,epoch:state.epoch};
    }
    state.batch=null;
    if(passes.length>1&&lastFix){
      const remaining=eligibleActions(state.findings,state.plan.actions).length;
      state.fix={...lastFix,report:{schema:'xml229-preview-batch-topofix/v2',
        status:'VALIDATED_COPY_NOT_ENGINEERING_ACCEPTANCE',source:{name:state.source.name,sha256:initialSha},
        fixedXmlSha256:state.source.sourceSha256,passes,
        appliedActionCount:state.applied-initialApplied,remainingEligibleActions:remaining},
        name:state.source.name+'.batch-'+(state.applied-initialApplied)+'.validated.topofix.xml'};
      setFixStatus('APPLIED '+(state.applied-initialApplied)+' actions across '+passes.length+
        ' validated passes. '+remaining+' eligible actions remain.','ready','batch');
      query(root,'[data-progress]').textContent='APPLIED · '+passes.length+' validated passes · '+
        (state.applied-initialApplied)+' action(s) · findings '+initialFindings+' → '+state.findings.length+
        ' · '+remaining+' eligible actions remain.';
    }
    state.batchRunning=false;refresh();
  }
  function refresh() {
    root.setAttribute('aria-busy',String(state.busy||state.batchRunning));
    renderRecords();renderActions();renderSelection();
    query(root,'[data-analyze]').disabled=!state.source||state.busy;
    query(root,'[data-cancel]').disabled=!state.busy;
    getNodes(root,'[data-auto-fix],[data-close-joint]').forEach(button=>button.disabled=state.busy);
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
    const generation=++state.epoch;
    state.source=null;state.original=null;state.revision=0;state.applied=0;state.history=[];state.resolutions=[];
    state.scene=null;state.plan=null;state.findings=[];state.result=null;state.fix=null;state.batch=null;state.gapReviews.clear();
    query(root,'[data-progress]').textContent='Reading original · no repairs applied.';
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
    state.plan=null;state.findings=[];state.fix=null;state.batch=null;
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
    else if(target.hasAttribute('data-analyze'))analyze();
    else if(target.hasAttribute('data-cancel')){state.epoch++;state.busy=false;state.batchRunning=false;refresh();
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
    if(event.target.matches('[data-file]')&&event.target.files?.[0]){
      const file=event.target.files[0];event.target.value='';load(file);
    }
    if(event.target.matches('[data-audit-category]')){state.category=event.target.value;renderActions();}
    if(event.target.matches('[data-helpers]'))canvas.setShowHelpers(event.target.checked);
    if(event.target.matches('[data-labels]'))canvas.setShowLabels(event.target.checked);
  };
  const input=event=>{
    if(event.target.matches('[data-search]')){state.search=event.target.value.trim();renderRecords();renderActions();}
  };
  root.addEventListener('click',click);root.addEventListener('change',changed);
  root.addEventListener('input',input);refresh();
  return {getState:()=>({sourceSha256:state.source?.sourceSha256||null,revision:state.revision,applied:state.applied,
    occurrences:state.scene?.records.length||0,actions:state.plan?.actions.length||0,
    selected:[...state.selected],busy:state.busy}),load,analyze,
    dispose(){state.epoch++;canvas.dispose();root.removeEventListener('click',click);
      root.removeEventListener('change',changed);root.removeEventListener('input',input);}};
}
const root=document.querySelector('#xml229-topology-workspace');
if(root)mountTopologyWorkspace(root);
