/** Human-readable PSI116 rule audit. Presentation only: all severities and witnesses come from findings. */
const RULES=Object.freeze({
 COINCIDENT_NODE_ALIAS_CANDIDATE:["Coincident nodes with verified ownership","Two or more source nodes occupy the same connection position, and PSI116 found connection authority for one canonical identity."],
 COINCIDENT_NODE_IDENTITY_AMBIGUOUS:["Coincident connection without proven ownership","Nodes share a position but PSI116 cannot prove that they represent the same engineering connection."],
 ZERO_LENGTH_ROUTE_SPAN:["Zero-length route connection","Consecutive route endpoints have negligible separation; inspect component ownership before any contraction."],
 ZERO_LENGTH_COMPONENT_SPAN:["Collapsed component endpoints","A component's endpoints coincide; removing a component or its engineering records is not automatically permitted."],
 SHORT_ROUTE_SPAN:["Short pipe connection","A route span is shorter than the configured threshold; component and support semantics determine whether it may be simplified."],
 SHORT_INLINE_COMPONENT_SPAN:["Short inline component","A real gasket, valve, flange or other inline component may legitimately be short. Preserve its engineering evidence."],
 NON_RIGID_COMPONENT_CLASSIFIED_RIGID:["Inconsistent rigid classification","A non-rigid component is flagged Rigid=2; PSI116 can propose a controlled correction."],
 INSTRUMENT_RIGID_EVIDENCE_REQUIRED:["Instrument rigid status needs confirmation","The instrument's type alone does not prove rigid-body behavior. Review the engineering evidence."],
 ELBO_OWNER_ENDPOINT_MISSING:["Elbow engineering owner missing","An elbow has no Endpoint=0 record to anchor its engineering identity."],
 ELBO_HELPER_PORTS_MISSING:["Elbow helper endpoints missing","An elbow lacks one or more tangent/helper endpoints expected for its geometry."],
 JUNCTION_OWNER_INFERRED_FROM_PORT_SET:["Junction owner is inferred","A tee or olet has no Endpoint=0; only a deterministic port is retained as evidence."],
 COMPONENT_PORTS_COINCIDENT:["Multiple component ports at one point","Coincident ports can be legitimate component records and should not be deleted as duplicate pipe nodes."],
 AUTO_PIPE_INLINE_COMPONENT_CARRIER:["Auto-pipe overlaps an inline component","Generated pipe-carrier geometry shares space with a real component; maintain separate original identities and lineage."],
 SUPPORT_ON_PIPE_CARRIER:["Support on pipe carrier","A support is attached to carrier geometry; preserve the restraint and its source association."],
 JUNCTION_ON_PIPE_CARRIER:["Junction on pipe carrier","A junction is represented with carrier pipe geometry; preserve the component's ownership."],
 DUPLICATE_ROUTE_SPAN:["Repeated route span","The same route geometry appears multiple times without sufficient proof that one is expendable."],
 COLLINEAR_ROUTE_OVERLAP:["Overlapping pipe spans","Route segments overlap on the same line; overlap alone does not establish which span may be removed."],
});
const MANUAL_GUIDE=Object.freeze({
 COINCIDENT_NODE_IDENTITY_AMBIGUOUS:"Inspect the original branch connection and component port records. Confirm which nodes truly connect in the 3D source, correct the owner/link upstream, and re-run the audit. Do not merge by XYZ alone.",
 ZERO_LENGTH_COMPONENT_SPAN:"Inspect the fitting's endpoint mapping and physical length. Correct the authoritative component geometry or helper ports upstream; do not delete the component to silence the error.",
 ZERO_LENGTH_ROUTE_SPAN:"Verify the connection ownership and whether the span is a legitimate coincident junction. Correct the upstream branch route only after component and restraint evidence is confirmed.",
 SHORT_ROUTE_SPAN:"Check the measured span, adjacent fittings, supports and unit tolerance. Adjust the authored route only if the short span is not an intentional component connection.",
 DUPLICATE_ROUTE_SPAN:"Compare both route occurrences, endpoints and owner references. Confirm which line is intended before removing or reconnecting anything in the source model.",
 COLLINEAR_ROUTE_OVERLAP:"Inspect both overlapping spans in 3D with component ownership and route continuity. Resolve the overlap in the source CAD/export model and rerun the audit.",
 ELBO_OWNER_ENDPOINT_MISSING:"Restore or correct the elbow's Endpoint=0 engineering owner in the upstream PSI116 export; do not invent an owner based only on coordinates.",
 ELBO_HELPER_PORTS_MISSING:"Check the elbow tangent/port records (Endpoint=1 and Endpoint=2). Restore missing helper records in the source authoring system.",
 INSTRUMENT_RIGID_EVIDENCE_REQUIRED:"Verify the instrument's support, mounting and rigid-body classification from project engineering data. Update Rigid only with documented authority.",
});
const FIXABLE=new Set(["ALIAS_COINCIDENT_NODE","CONTRACT_PRESERVE_OWNER","SAFE_DROP_PIPE_GEOMETRY","REMOVE_FALSE_RIGID"]);
const RECOMMEND=Object.freeze({
 ALIAS_COINCIDENT_NODE:"Use one verified connection identity while preserving each source occurrence and trace.",
 CONTRACT_PRESERVE_OWNER:"Simplify this short span while retaining the special-component owner and engineering attributes.",
 SAFE_DROP_PIPE_GEOMETRY:"Remove only the dispensable plain-pipe record from a validated copy; retain the component owner and lineage.",
 REMOVE_FALSE_RIGID:"Set Rigid to 0 in a validated copy after checking component classification.",
 MERGE_CARRIER_WITH_COMPONENT:"Link the carrier and component through evidence/lineage. No XML record is deleted by this action.",
 KEEP:"Retain this source geometry and engineering evidence without modification.",
 BLOCK_AMBIGUOUS:"No automatic change is authorized. Investigate component ownership and connection evidence.",
});
const esc=v=>String(v??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
const severity=f=>["ERROR","WARNING","INFO"].includes(f?.severity)?f.severity:"INFO";
function resolution(action,finding){
 if(finding.blocking||action?.status==="BLOCKED"||(action?.blockers||[]).length)
   return {kind:"manual",text:"Manual fix / review"};
 if(!action)return {kind:"manual",text:"Manual fix / review"};
 if(FIXABLE.has(action.disposition)&&action.status==="PROPOSED"&&
    Number(action.confidence)>=.95&&(action.proposed_changes||[]).length)
   return {kind:"auto",text:"Auto fix available"};
 if(action.disposition==="MERGE_CARRIER_WITH_COMPONENT")
   return {kind:"evidence",text:"Evidence-only; no XML change"};
 if(action.disposition==="KEEP")
   return {kind:"keep",text:"Preserve as-is"};
 return {kind:"manual",text:"Manual fix / review"};
}
export function buildAudit(findings,actions){
 const actionMap=new Map();
 for(const a of actions||[])for(const id of a.finding_ids||[]){
   if(!actionMap.has(id))actionMap.set(id,[]);
   actionMap.get(id).push(a);
 }
 const groups=new Map(),items=[];
 for(const f of findings||[]){
   const linked=actionMap.get(f.finding_id)||[];
   const effective=linked.find(a=>a.disposition!=="KEEP")||linked[0]||null;
   const fix=resolution(effective,f);
   const [title,rule]=RULES[f.code]||[String(f.code||"Unclassified rule").replaceAll("_"," ").toLowerCase(),f.message||"Review original source evidence."];
   const item={finding:f,action:effective,linked,fix,severity:severity(f),title,rule};
   items.push(item);
   if(!groups.has(f.code))groups.set(f.code,{code:f.code,title,rule,items:[]});
   groups.get(f.code).items.push(item);
 }
 const counts={ERROR:0,WARNING:0,INFO:0,auto:0,manual:0,evidence:0,keep:0};
 for(const item of items){counts[item.severity]++;counts[item.fix.kind]++;}
 counts.autoActions=new Set(items.filter(i=>i.fix.kind==="auto")
   .map(i=>i.action?.action_id).filter(Boolean)).size;
 return {groups:[...groups.values()].sort((a,b)=>{
   const score=g=>g.items.some(i=>i.severity==="ERROR")?0:g.items.some(i=>i.severity==="WARNING")?1:2;
   return score(a)-score(b)||b.items.length-a.items.length||a.title.localeCompare(b.title);
 }),items,counts};
}
function itemHTML(item){
 const {finding:f,action:a,fix}=item;
 const nodes=(f.node_numbers||[]).slice(0,7).join(", ");
 const detail=(f.node_keys||[]).slice(0,12).join(", ");
 const reason=f.message||"Refer to rule evidence";
 const chosen=a?.disposition||"NO_ACTION";
 const remedy=fix.kind==="manual"
   ?(MANUAL_GUIDE[f.code]||"Inspect the original source-qualified records and component ownership. Correct the upstream engineering XML/export under human authority, then rerun the PSI116 audit.")
   :(RECOMMEND[chosen]||a?.message||"Review source geometry and ownership manually.");
 return '<article class="audit-item">'+
  '<div class="audit-item-top"><span class="audit-severity '+item.severity.toLowerCase()+'">'+esc(item.severity)+'</span>'+
  '<span class="audit-resolution '+fix.kind+'">'+esc(fix.text)+'</span></div>'+
  '<p class="audit-plain">'+esc(reason)+'</p>'+
  '<p class="audit-remedy"><strong>'+(fix.kind==="manual"?"Manual fix steps:":"Recommended action:")+'</strong> '+esc(remedy)+'</p>'+
  '<p class="audit-context"><strong>Source:</strong> '+esc(f.branch_name||"Unknown branch")+
  (nodes?' · Node '+esc(nodes):'')+'</p>'+
  (a?'<div class="audit-controls"><button data-audit-action="'+esc(a.action_id)+'">Locate on canvas</button>'+
    (fix.kind==="auto"?'<button class="audit-primary" data-auto-fix="'+esc(a.action_id)+'">Auto fix · validated copy</button>':'')+
    '</div>':'')+
  '<details class="audit-proof"><summary>Rule evidence and technical IDs</summary>'+
  '<p><strong>Rule:</strong> '+esc(f.code)+' · <strong>Finding:</strong> '+esc(f.finding_id)+
  (a?' · <strong>Action:</strong> '+esc(a.action_id)+' · <strong>Disposition:</strong> '+esc(a.disposition):'')+'</p>'+
  '<p><strong>Source occurrence keys:</strong> '+esc(detail||"Not supplied")+'</p>'+
  (a?.blockers?.length?'<p><strong>Blockers:</strong> '+esc(a.blockers.join(", "))+'</p>':'')+
  (a?.authority?'<p><strong>Authority:</strong> '+esc(a.authority)+'</p>':'')+
  '</details></article>';
}
export function renderAuditHTML(audit,{search="",filter="all"}={}){
 const q=search.trim().toLowerCase();
 const match=i=>[i.title,i.rule,i.finding.code,i.finding.message,i.finding.branch_name,
  i.action?.action_id,i.action?.disposition,...(i.finding.node_numbers||[]),
  ...(i.finding.node_keys||[])].some(s=>String(s??"").toLowerCase().includes(q));
 const relevant=i=>match(i)&&(filter==="all"||filter===i.severity.toLowerCase()||filter===i.fix.kind);
 let shown=0;
 const html=audit.groups.map(g=>{
   const matches=g.items.filter(relevant);
   if(!matches.length)return "";
   shown+=matches.length;
   const sev=matches.some(i=>i.severity==="ERROR")?"ERROR":matches.some(i=>i.severity==="WARNING")?"WARNING":"INFO";
   const autos=matches.filter(i=>i.fix.kind==="auto").length;
   const manuals=matches.filter(i=>i.fix.kind==="manual").length;
   return '<details class="audit-rule" '+(sev!=="INFO"?'open':'')+'><summary>'+
    '<span class="audit-rule-title">'+esc(g.title)+'</span>'+
    '<span class="audit-rule-stats">'+matches.length+' findings · '+esc(sev)+
    (autos?' · '+autos+' auto fix':'')+(manuals?' · '+manuals+' manual':'')+'</span></summary>'+
    '<p class="audit-rule-why"><strong>Why this rule flags a finding:</strong> '+esc(g.rule)+'</p>'+
    matches.slice(0,200).map(itemHTML).join("")+
    (matches.length>200?'<p>Showing 200 findings; narrow search.</p>':'')+'</details>';
 }).join("");
 return {shown,html:html||'<p>No findings match this filter. Try All findings or clear search.</p>'};
}
export function renderAuditSummary(audit){
 const c=audit.counts;
 return audit.items.length+' findings under '+audit.groups.length+' engineering rules · '+
 c.ERROR+' errors · '+c.WARNING+' warnings · '+c.INFO+' informational · '+
 c.auto+' findings linked to '+c.autoActions+' distinct Auto fix actions · '+c.manual+' manual fix / review · '+c.evidence+' evidence-only · '+
 c.keep+' preserve. Source remains unchanged until an explicitly selected validated copy is exported.';
}
