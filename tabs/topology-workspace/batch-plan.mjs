/** Grouped, deterministic preview Auto fix planning. No transaction or XML edits here. */
export const MUTATING_KINDS=new Set([
  "ALIAS_COINCIDENT_NODE","CONTRACT_PRESERVE_OWNER",
  "SAFE_DROP_PIPE_GEOMETRY","REMOVE_FALSE_RIGID"
]);

export function eligibleActions(findings=[],actions=[]){
  const byId=new Map(findings.map(f=>[f.finding_id,f]));
  return actions.filter(a=>{
    const witnesses=(a.finding_ids||[]).map(id=>byId.get(id));
    return a.status==="PROPOSED" && !(a.blockers||[]).length &&
      Number(a.confidence)>=.95 && MUTATING_KINDS.has(a.disposition) &&
      (a.proposed_changes||[]).length>0 && witnesses.length>0 &&
      witnesses.every(f=>f && f.blocking!==true);
  });
}

export function previewBatchPlan(findings=[],actions=[]){
  const map=new Map(findings.map(f=>[f.finding_id,f]));
  const candidates=eligibleActions(findings,actions);
  const selected=[],skipped=[],used=new Map();
  for(const action of candidates.slice().sort((a,b)=>a.action_id.localeCompare(b.action_id))){
    const keys=new Set((action.finding_ids||[]).flatMap(
      id=>map.get(id)?.node_keys||[]));
    const collisions=[...keys].filter(k=>used.has(k));
    if(!keys.size){
      skipped.push({actionId:action.action_id,reason:"NO_SOURCE_QUALIFIED_WITNESSES"});
      continue;
    }
    if(collisions.length){
      skipped.push({actionId:action.action_id,
        reason:"SHARED_SOURCE_OCCURRENCE",
        conflictsWith:[...new Set(collisions.map(k=>used.get(k)))]});
      continue;
    }
    selected.push(action.action_id);
    for(const key of keys)used.set(key,action.action_id);
  }
  return {candidateCount:candidates.length,actionIds:selected,skipped,
    notEligible:actions.length-candidates.length};
}
