/** Bounded pass orchestration. Always return the last validated receipt on stop. */
export async function runValidatedPasses({initialPlan,readState,runPass,nextPlan,isCurrent=()=>true,maxPasses=8}){
 const initial=readState(),seen=new Set([initial.sha]),passes=[];
 let plan=initialPlan,lastFix=initial.fix||null,stopReason='COMPLETE',stopMessage='';
 for(let pass=0;pass<maxPasses;pass++){
  const before=readState();
  try{await runPass(plan);}catch(error){stopReason='PASS_FAILED';stopMessage=error?.message||String(error);break;}
  if(!isCurrent())return {passes,lastFix,stopReason:'CANCELLED',stopMessage:'Source or request changed.'};
  const current=readState();
  if(current.revision===before.revision){stopReason='PASS_FAILED';stopMessage=current.failure||'Pass produced no validated revision.';break;}
  lastFix=current.fix;passes.push(lastFix.report);
  if(seen.has(current.sha)){stopReason='REPEATED_OUTPUT';stopMessage='Repeated output identity.';break;}
  seen.add(current.sha);plan=nextPlan();
  if(!plan.actionIds.length)break;
  if(pass===maxPasses-1){stopReason='PASS_LIMIT';stopMessage='Eight-pass limit reached.';}
 }
 return {passes,lastFix,stopReason,stopMessage};
}
