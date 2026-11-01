/** UI-only labels and grouping. Never changes admission, engine or policy.
 * Counts use the currently published read-only audit, not a guessed fix list.
 */
export function trialGroup(item) {
  if(item.fix?.kind==='manual')return 'review';
  if(item.fix?.kind==='auto')return 'auto';
  if(item.fix?.kind==='keep')return 'preserve';
  return 'information';
}
export const trialGroupFilters=Object.freeze({
  review:'manual',auto:'auto',preserve:'keep',information:'information',
});
export const trialGroupTitles=Object.freeze({
  review:'Needs your review',
  auto:'Auto fixes available',
  preserve:'No action needed: kept by rule',
  information:'Informational / evidence-only',
});
export function trialRemaining(audit) {
  const groups={review:[],auto:[],preserve:[],information:[]};
  for(const item of audit?.items||[])groups[trialGroup(item)].push(item);
  return groups;
}
export function trialValidationSummary(history,fix){
  // Source-linked native validation checks are authoritative. Never invent
  // a 9/9 receipt merely because the current scene looks repaired.
  const entry=history?.[history.length-1];
  const checks=Array.isArray(entry?.validation)?entry.validation:
    Array.isArray(fix?.report?.validationChecks)?fix.report.validationChecks:
    Array.isArray(fix?.report?.validation?.checks)?fix.report.validation.checks:null;
  if(!checks?.length)return 'validation checks not available';
  return checks.filter(c=>c.passed===true).length+'/'+checks.length+' checks passed';
}
export function trialDisabledReason(button,state,{proofCurrent=false,hubCanRelease=false}={}){
  if(!button?.disabled)return '';
  const has=name=>button.hasAttribute('data-'+name);
  const busy=state.busy||state.batchRunning;
  if(has('preview-short')||has('run-short-drop')||has('select-gaskets')||
     has('short-hub-preview')){
    if(!state.plan)return 'Analyze the current XML to identify eligible short elements.';
    if(busy)return 'Finish or cancel the active validation first.';
    if(state.hubEnabled&&state.hubParity?.status!=='EQUAL')
      return 'Universal XML parity must be EQUAL before short-element changes.';
    if(has('run-short-drop')&&state.hubEnabled&&!state.shortHubPreview)
      return 'Preview the selected UXML short-drop operations before Apply.';
    return 'Select at least one eligible short element in the preview.';
  }
  if(has('auto-fix-all')||has('auto-fix')){
    if(busy)return 'Finish or cancel the active validation first.';
    if(state.hubEnabled&&state.hubParity?.status!=='EQUAL')
      return 'Universal XML parity must be EQUAL before Auto fix is available.';
    if(!state.plan)return 'Analyze the current XML before attempting Auto fix.';
    return 'No current source-qualified Auto fixes are available for this selection.';
  }
  if(has('trial-current')||has('trial-history')){
    if(busy)return 'Finish the current validation before downloading.';
    if(state.hubEnabled&&!hubCanRelease)
      return 'Hub parity and the corrected revision must match before download.';
    return 'No current validated corrected download is available.';
  }
  if(has('trial-evidence')){
    if(busy)return 'Wait for the current evidence recheck to finish.';
    return 'Connection evidence unavailable: '+(state.evidenceProofReason||'EVIDENCE_ANALYSIS_REQUIRED')+
      '. Analyze the current revision to retry.';
  }
  if(has('what-left'))return 'There are no findings in this group.';
  if(has('trial-step'))return 'No more cases in this group in that direction.';
  if(has('download-resolutions')){
    if(busy)return 'Wait for the current validation and evidence recheck to finish.';
    return 'Connection evidence unavailable: '+(state.evidenceProofReason||'EVIDENCE_ANALYSIS_REQUIRED')+
      '. Analyze the current revision to retry.';
  }
  if(has('download-working')||has('download-history')||has('download-fix')||has('download-batch-report')){
    if(busy)return 'Finish or cancel the active validation before downloading.';
    if(!state.revision)return 'No validated corrected revision exists. Analyze and apply an eligible fix first.';
    if(state.hubEnabled&&!hubCanRelease)
      return 'Hub parity/revision verification is required for this download.';
    return 'The current revision has no eligible validated download.';
  }
  if(has('download-gap-review'))return 'Save a source review note before downloading a review receipt.';
  if(has('apply-second')||has('queue-second')||has('queue-apply')||has('close-joint')||has('add-second-pass')){
    if(state.hubEnabled)return 'Runs on the direct route only. Untick Universal XML route to use it.';
    if(busy)return 'Wait for the active transaction to finish.';
    return 'Select an exact source pair, preview it, confirm it and supply the required design evidence.';
  }
  if(has('analyze'))return !state.source?'Load a source XML file first.':'Finish or cancel the active validation first.';
  if(has('cancel'))return 'No active operation to cancel.';
  return 'This control is not available until the required analysis, selection or validation is complete.';
}
