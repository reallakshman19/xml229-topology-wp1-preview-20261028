/** Human-readable PSI116 rule audit. Presentation only: all severities and witnesses come from findings. */
const RULES=Object.freeze({
 CONNECTION_DECLARATION_CONFLICT:["Connection and closure declarations conflict","A shared source node is also declared CLOS. Reconcile the branch connection/termination declaration before changing it."],
 PORT_CONNECTION_WITHIN_TOLERANCE:["Connection within 25 mm tolerance","Compatible physical ports have a unique counterpart within the inclusive project tolerance. Auto fix closes the interface and preserves finite component geometry."],
 NEAR_MISS_PIPE_JOINT:["Possible pipe-joint gap","Adjacent source PIPE occurrences have separated ends within the 3D near-miss screening range. Verify intended connection; source ordering alone is not proof."],
 NEAR_MISS_BRANCH_ENDS:["Possible gap between branch ends","Pipe endpoints in different branches nearly meet but do not coincide within the connection tolerance. Confirm design connectivity before joining."],
 BRANCH_END_UNVERIFIED:["Branch termination needs confirmation","The source branch end has no matching other-branch endpoint within tolerance. It might be a legitimate boundary, not a defect."],
 COINCIDENT_NODE_ALIAS_CANDIDATE:["Coincident node identity candidate","Two or more source nodes occupy the same connection position. PSI116 proposes a canonical identity; inspect its reported connection authority."],
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
// Engineering subject classification is separate from solver severity and repair eligibility.
// No source rule currently establishes that an open end/gap/disconnection has been checked.
const CATEGORIES=Object.freeze({
 gaps:{title:"Potential gaps & open ends",explain:"3D near-miss PIPE joints and branch-end evidence. These are review candidates; confirmed disconnections require design/connection authority."},
 connection:{title:"Connection topology & node identity",explain:"Coincident identities and zero/short route relationships. These findings do NOT prove a gap or a disconnected pipe."},
 overlap:{title:"Overlaps & duplicate geometry",explain:"Duplicate or collinear pipe runs and generated pipe-carrier overlaps. Not every overlapping representation is defective."},
 component:{title:"Component topology & ports",explain:"Elbow, tee, OLET, support and component-port ownership or integrity; not automatically a physical pipe disconnection."},
 non_topology:{title:"Non-topology engineering data",explain:"Rigid classification and other engineering attributes, not pipe connectivity or overlap."},
 unclassified:{title:"Unclassified rule — review",explain:"New PSI116 rules must be mapped explicitly; the preview will not infer an engineering category."}
});
const CATEGORY_BY_RULE=Object.freeze({
 CONNECTION_DECLARATION_CONFLICT:"gaps",
 PORT_CONNECTION_WITHIN_TOLERANCE:"gaps",
 NEAR_MISS_PIPE_JOINT:"gaps",
 NEAR_MISS_BRANCH_ENDS:"gaps",
 BRANCH_END_UNVERIFIED:"gaps",
 COINCIDENT_NODE_ALIAS_CANDIDATE:"connection",
 COINCIDENT_NODE_IDENTITY_AMBIGUOUS:"connection",
 ZERO_LENGTH_ROUTE_SPAN:"connection",
 SHORT_ROUTE_SPAN:"connection",
 DUPLICATE_ROUTE_SPAN:"overlap",
 COLLINEAR_ROUTE_OVERLAP:"overlap",
 AUTO_PIPE_INLINE_COMPONENT_CARRIER:"overlap",
 COMPONENT_PORTS_COINCIDENT:"component",
 ZERO_LENGTH_COMPONENT_SPAN:"component",
 SHORT_INLINE_COMPONENT_SPAN:"component",
 ELBO_OWNER_ENDPOINT_MISSING:"component",
 ELBO_HELPER_PORTS_MISSING:"component",
 JUNCTION_OWNER_INFERRED_FROM_PORT_SET:"component",
 SUPPORT_ON_PIPE_CARRIER:"component",
 JUNCTION_ON_PIPE_CARRIER:"component",
 NON_RIGID_COMPONENT_CLASSIFIED_RIGID:"non_topology",
 INSTRUMENT_RIGID_EVIDENCE_REQUIRED:"non_topology"
});
const MANUAL_GUIDE=Object.freeze({
 NEAR_MISS_PIPE_JOINT:"Confirm that these PIPE ports should connect. For an eligible joint at ≤25 mm, choose the retained port and use Close joint & recheck below. The other port moves to it; both component records remain. For shared or complex ownership, repair the authoring model and re-export.",
 NEAR_MISS_BRANCH_ENDS:"Check the intended branch connection. For an eligible pair of PIPE ports at ≤25 mm, choose the retained port and use Close joint & recheck. If the separation is intentional, record that outcome; shared or complex joints require upstream repair.",
 BRANCH_END_UNVERIFIED:"No compatible port connection qualified under the ≤25 mm policy. Check this branch head/tail HREF/TREF and its target component/port in the authoring model. Restore a missing target in the export or correct its position/link, re-export and rerun TopoFix; document an intentional boundary instead when applicable.",
 COINCIDENT_NODE_IDENTITY_AMBIGUOUS:"Inspect the original branch connection and component port records. Confirm which nodes truly connect in the 3D source, correct the owner/link upstream, and re-run the audit. Do not merge by XYZ alone.",
 ZERO_LENGTH_COMPONENT_SPAN:"Inspect the fitting's endpoint mapping and physical length. Correct the authoritative component geometry or helper ports upstream; do not delete the component to silence the error.",
 ZERO_LENGTH_ROUTE_SPAN:"Verify the connection ownership and whether the span is a legitimate coincident junction. Correct the upstream branch route only after component and restraint evidence is confirmed.",
 SHORT_ROUTE_SPAN:"Check the measured span, adjacent fittings, supports and unit tolerance. Adjust the authored route only if the short span is not an intentional component connection.",
 DUPLICATE_ROUTE_SPAN:"Compare both route occurrences, endpoints and owner references. Confirm which line is intended before removing or reconnecting anything in the source model.",
 COLLINEAR_ROUTE_OVERLAP:"Inspect both spans and component ownership. A short overlap at two PIPE ports can be closed using Close joint & recheck on its associated joint finding. Multi-span or shared-owner overlaps need an upstream route repair and re-export.",
 ELBO_OWNER_ENDPOINT_MISSING:"Restore or correct the elbow's Endpoint=0 engineering owner in the upstream PSI116 export; do not invent an owner based only on coordinates.",
 ELBO_HELPER_PORTS_MISSING:"Check the elbow tangent/port records (Endpoint=1 and Endpoint=2). Restore missing helper records in the source authoring system.",
 INSTRUMENT_RIGID_EVIDENCE_REQUIRED:"Verify the instrument's support, mounting and rigid-body classification from project engineering data. Update Rigid only with documented authority.",
});
const RULE_IMPACT=Object.freeze({
 COINCIDENT_NODE_IDENTITY_AMBIGUOUS:"A coincident 3D position is not sufficient to establish pipe connectivity. Automatic node merging could create a false load path.",
 ZERO_LENGTH_COMPONENT_SPAN:"A component may have collapsed endpoints; removing or contracting it could erase fitting or boundary evidence.",
 ZERO_LENGTH_ROUTE_SPAN:"The connection has no measurable span. This might be intentional; check the owner and physical route.",
 SHORT_ROUTE_SPAN:"The short distance may be a construction detail or a route defect. Threshold alone cannot establish the correction.",
 DUPLICATE_ROUTE_SPAN:"Duplicate pipe centreline geometry may double count a routed segment or represent an intentional overlay.",
 COLLINEAR_ROUTE_OVERLAP:"Overlapping pipe spans could represent duplicate geometry or an intentionally shared region. The owning route is unproven.",
 ELBO_OWNER_ENDPOINT_MISSING:"The elbow lacks its designated engineering-owner record; port reconstruction without source evidence is unsafe.",
 ELBO_HELPER_PORTS_MISSING:"Missing elbow helper endpoints can make the projected fitting incomplete; do not infer tangent geometry.",
 NON_RIGID_COMPONENT_CLASSIFIED_RIGID:"The Rigid=2 flag conflicts with this component class and may change downstream interpretation.",
 INSTRUMENT_RIGID_EVIDENCE_REQUIRED:"The rigid classification needs engineering justification before it can be accepted.",
 NEAR_MISS_PIPE_JOINT:"The two PIPE ends are close but outside the connection tolerance. They may be disconnected or intentionally separated.",
 NEAR_MISS_BRANCH_ENDS:"Two separate branch ends nearly meet in 3D; design intent is required before joining them.",
 BRANCH_END_UNVERIFIED:"The branch termination has no confirmed matching end; it may be an approved open boundary.",
});
const FIXABLE=new Set(["ALIAS_COINCIDENT_NODE","CONTRACT_PRESERVE_OWNER","SAFE_DROP_PIPE_GEOMETRY","REMOVE_FALSE_RIGID","CLOSE_PORT_CONNECTION"]);
const RECOMMEND=Object.freeze({
 CLOSE_PORT_CONNECTION:"Close compatible ports under the inclusive ≤25 mm project policy, retain component references and dimensions, then rerun the complete audit.",
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
   const category=CATEGORY_BY_RULE[f.code]||"unclassified";
   const item={finding:f,action:effective,linked,fix,severity:severity(f),title,rule,category};
   items.push(item);
   if(!groups.has(f.code))groups.set(f.code,{code:f.code,title,rule,category,items:[]});
   groups.get(f.code).items.push(item);
 }
 const counts={ERROR:0,WARNING:0,INFO:0,auto:0,manual:0,evidence:0,keep:0};
 counts.categories={gaps:0,connection:0,overlap:0,component:0,non_topology:0,unclassified:0};
 for(const item of items){
   counts[item.severity]++;counts[item.fix.kind]++;
   counts.categories[item.category]++;
 }
 counts.autoActions=new Set(items.filter(i=>i.fix.kind==="auto")
   .map(i=>i.action?.action_id).filter(Boolean)).size;
 return {groups:[...groups.values()].sort((a,b)=>{
   const score=g=>g.items.some(i=>i.severity==="ERROR")?0:g.items.some(i=>i.severity==="WARNING")?1:2;
   return score(a)-score(b)||b.items.length-a.items.length||a.title.localeCompare(b.title);
 }),items,counts};
}
function itemHTML(item,reviews={},sourceByKey=null){
 const saved=reviews[item.finding.finding_id]||null;
 const {finding:f,action:a,fix}=item;
 const pair=(f.node_keys||[]).map(k=>sourceByKey?.get?.(k)||sourceByKey?.[k]);
 const canClose=['NEAR_MISS_PIPE_JOINT','NEAR_MISS_BRANCH_ENDS',
  'COINCIDENT_NODE_IDENTITY_AMBIGUOUS','COINCIDENT_NODE_ALIAS_CANDIDATE'].includes(f.code)&&
  pair.length===2&&pair.every(r=>r?.position&&r.type==='PIPE'&&['1','2'].includes(r.endpoint)&&!r.restraint)&&
  Math.hypot(pair[0].position.x-pair[1].position.x,pair[0].position.y-pair[1].position.y,pair[0].position.z-pair[1].position.z)<=25;
 const nodes=(f.node_numbers||[]).slice(0,7).join(", ");
 const detail=(f.node_keys||[]).slice(0,12).join(", ");
 const reason=f.message||"Refer to rule evidence";
 const impact=RULE_IMPACT[f.code]||"Review the source-qualified engineering evidence before changing geometry or attributes.";
 const numeric=Number.isFinite(f.length_mm)?' · Measured 3D length / overlap: '+f.length_mm.toFixed(3)+' mm':'';
 const details=f.details||{};
 const optional=['gapMm','nearestSourceRecordMm','nearestSourceRecordKey','maximumResidualMm','overlapLengthMm','connectionAuthority','ownerType',
   'preferredOwnerNodeNumber','missingEndpoints','endpointSet','crossBranch','confidence'];
 const evidence=optional.filter(k=>details[k]!==undefined&&details[k]!==null)
   .map(k=>k.replace(/([a-z])([A-Z])/g,'$1 $2')+': '+
     (Array.isArray(details[k])?details[k].join(', '):String(details[k]))).join(' · ');
 const sourceRows=(f.node_keys||[]).slice(0,8).map(key=>{
   const r=sourceByKey?.get?.(key)||sourceByKey?.[key];
   const position=r?.position?Object.values(r.position).join(', '):'no explicit XYZ';
   return '<li><strong>'+esc(key)+'</strong> — '+esc(r?.type||'Source record')+
     ' · Node '+esc(r?.nodeNumber??'unknown')+' · XYZ '+esc(position)+'</li>';
 }).join("");
 const chosen=a?.disposition||"NO_ACTION";
 const remedy=fix.kind==="manual"
   ?(chosen==="REVIEW_SOURCE_RECORD"&&a?.message?a.message:
     MANUAL_GUIDE[f.code]||"Inspect the original source-qualified records and component ownership. Correct the upstream engineering XML/export under human authority, then rerun the PSI116 audit.")
   :(RECOMMEND[chosen]||a?.message||"Review source geometry and ownership manually.");
 return '<article class="audit-item">'+
  '<h4 class="audit-item-title">'+esc(item.title)+'</h4>'+
  '<div class="audit-item-top"><span class="audit-severity '+item.severity.toLowerCase()+'">'+esc(item.severity)+'</span>'+
  '<span class="audit-resolution '+fix.kind+'">'+esc(fix.text)+'</span></div>'+
  '<p class="audit-plain"><strong>What was detected:</strong> '+esc(reason)+'</p>'+
  '<p class="audit-impact"><strong>Why it matters:</strong> '+esc(impact)+'</p>'+
  '<p class="audit-evidence"><strong>Rule trigger:</strong> '+esc(item.rule+numeric)+
    (evidence?' · '+esc(evidence):'')+'</p>'+
  '<p class="audit-impact"><strong>Severity / blocking:</strong> '+esc(item.severity)+
    (f.blocking?' · Blocked from automatic correction by the analyzer.':
      ' · Diagnostic finding; severity alone does not authorize a fix.')+'</p>'+
  '<p class="audit-remedy"><strong>'+(fix.kind==="manual"?"Manual fix steps:":"Recommended action:")+'</strong> '+esc(remedy)+'</p>'+
  '<p class="audit-context"><strong>Source:</strong> '+esc(f.branch_name||"Unknown branch")+
  (nodes?' · Node '+esc(nodes):'')+'</p>'+
  (a?'<div class="audit-controls"><button data-audit-action="'+esc(a.action_id)+'">Locate on canvas</button>'+
    (fix.kind==="auto"?'<button class="audit-primary" data-auto-fix="'+esc(a.action_id)+'">Auto fix · validated copy</button>':'')+
    '</div>':'')+
  (item.category==="gaps"&&fix.kind==="manual"?'<div class="audit-review">'+
    '<strong>Engineering review (session only, not acceptance)</strong>'+
    (saved?'<p class="audit-review-saved">Reviewer-marked: '+esc(saved.disposition==='intentional'?'Intentional termination':saved.disposition==='repair'?'Connection correction needed':'Still unresolved')+
       ' · evidence: '+esc(saved.note)+'</p>':'')+
    '<label>Disposition<select data-gap-review-choice>'+
       '<option value="">Select review outcome</option>'+
       '<option value="intentional"'+(saved?.disposition==='intentional'?' selected':'')+'>Intended end (requires evidence)</option>'+
       '<option value="repair"'+(saved?.disposition==='repair'?' selected':'')+'>Missing connection / repair needed</option>'+
       '<option value="unresolved"'+(saved?.disposition==='unresolved'?' selected':'')+'>Unresolved / investigate</option>'+
    '</select></label>'+
    '<label>Drawing, P&ID or reasoning reference<input data-gap-review-note type="text" maxlength="250" placeholder="Evidence required" value="'+esc(saved?.note||'')+'"></label>'+
    '<button data-save-gap-review="'+esc(f.finding_id)+'">Save review note</button>'+
    '</div>':'')+
  (canClose?'<div class="audit-joint"><strong>Close this joint · ≤25 mm</strong>'+
    '<label>Keep this port fixed; move the other port to it<select data-joint-target>'+
    pair.map(r=>'<option value="'+esc(r.key)+'">'+esc(r.key+' · '+r.refNo)+'</option>').join('')+'</select></label>'+
    '<label>Connection evidence / reason<input data-joint-evidence maxlength="250" placeholder="Drawing, P&amp;ID or confirmed connection reason"></label>'+
    '<label><input type="checkbox" data-joint-confirm> These two ports must connect.</label>'+
    '<p>Sets the moved port’s XYZ and NodeNumber to the retained port. Keeps both PIPE records and component references.</p>'+
    '<button data-close-joint="'+esc(f.finding_id)+'">Close joint &amp; recheck</button></div>':'')+
  (sourceRows?'<details class="audit-source"><summary>Source evidence — '+(f.node_keys||[]).length+
     ' original occurrence(s)</summary><ul>'+sourceRows+'</ul></details>':'')+
  '<details class="audit-proof"><summary>Rule evidence and technical IDs</summary>'+
  '<p><strong>Rule:</strong> '+esc(f.code)+' · <strong>Finding:</strong> '+esc(f.finding_id)+
  (a?' · <strong>Action:</strong> '+esc(a.action_id)+' · <strong>Disposition:</strong> '+esc(a.disposition):'')+'</p>'+
  '<p><strong>Source occurrence keys:</strong> '+esc(detail||"Not supplied")+'</p>'+
  (a?.blockers?.length?'<p><strong>Blockers:</strong> '+esc(a.blockers.join(", "))+'</p>':'')+
  (a?.authority?'<p><strong>Authority:</strong> '+esc(a.authority)+'</p>':'')+
  '</details></article>';
}
export function renderAuditHTML(audit,{search="",filter="all",category="all",reviews={},sourceByKey=null}={}){
 const q=search.trim().toLowerCase();
 const match=i=>[i.title,i.rule,i.finding.code,i.finding.message,i.finding.branch_name,
  i.action?.action_id,i.action?.disposition,...(i.finding.node_numbers||[]),
  ...(i.finding.node_keys||[])].some(s=>String(s??"").toLowerCase().includes(q));
 const relevant=i=>match(i)&&(category==="all"||category===i.category)&&
  (filter==="all"||filter===i.severity.toLowerCase()||filter===i.fix.kind);
 let shown=0;
 const sections=Object.keys(CATEGORIES).map(categoryId=>{
   const categoryGroups=audit.groups.filter(g=>g.category===categoryId);
   const groupHTML=categoryGroups.map(g=>{
     const matches=g.items.filter(relevant);
     if(!matches.length)return "";
     shown+=matches.length;
     const sev=matches.some(i=>i.severity==="ERROR")?"ERROR":matches.some(i=>i.severity==="WARNING")?"WARNING":"INFO";
     const autos=new Set(matches.filter(i=>i.fix.kind==="auto").map(i=>i.action?.action_id).filter(Boolean)).size;
     const manuals=matches.filter(i=>i.fix.kind==="manual").length;
     return '<details class="audit-rule" '+(sev!=="INFO"||g.category==="gaps"?'open':'')+'><summary>'+
      '<span class="audit-rule-title">'+esc(g.title)+'</span>'+
      '<span class="audit-rule-stats">'+matches.length+' findings · '+esc(sev)+
      (autos?' · '+autos+' Auto fix actions':'')+(manuals?' · '+manuals+' manual':'')+'</span></summary>'+
      '<p class="audit-rule-why"><strong>Why this rule flags a finding:</strong> '+esc(g.rule)+'</p>'+
      matches.slice(0,200).map(i=>itemHTML(i,reviews,sourceByKey)).join("")+
      (matches.length>200?'<p>Showing 200 findings; narrow search.</p>':'')+'</details>';
   }).filter(Boolean);
   if(!groupHTML.length)return "";
   const count=categoryGroups.flatMap(g=>g.items).filter(relevant).length;
   const info=CATEGORIES[categoryId];
   return '<section class="audit-category" data-category-id="'+categoryId+'">'+
     '<h3>'+esc(info.title)+' <span class="audit-category-count">'+count+'</span></h3>'+
     '<p class="audit-category-explain">'+esc(info.explain)+'</p>'+
     groupHTML.join("")+'</section>';
 }).filter(Boolean);
 const empty=filter==="error"?
  '<div class="audit-empty"><strong>No ERROR findings in this selection.</strong>'+
  '<p>Warnings and potential gaps are shown separately. Zero ERROR findings is not proof of complete network connectivity.</p></div>':
  '<p>No findings match this filter. Try All findings or clear search.</p>';
 return {shown,html:sections.join("")||empty};
}
/** Counts represent finding rows in the current issue class and search, independent of severity filter.
 * Auto fix is a finding count; batching counts distinct eligible source actions separately. */
export function filterCounts(audit,{search="",category="all"}={}){
 const q=search.trim().toLowerCase();
 const matched=audit.items.filter(i=>{
   if(category!=="all"&&i.category!==category)return false;
   return [i.title,i.rule,i.finding.code,i.finding.message,i.finding.branch_name,
     i.action?.action_id,i.action?.disposition,...(i.finding.node_numbers||[]),
     ...(i.finding.node_keys||[])].some(v=>String(v??"").toLowerCase().includes(q));
 });
 return {all:matched.length,error:matched.filter(i=>i.severity==="ERROR").length,
   warning:matched.filter(i=>i.severity==="WARNING").length,
   auto:matched.filter(i=>i.fix.kind==="auto").length,
   manual:matched.filter(i=>i.fix.kind==="manual").length,
   evidence:matched.filter(i=>i.fix.kind==="evidence").length};
}

export function renderAuditSummary(audit){
 const c=audit.counts;
 return audit.items.length+' findings under '+audit.groups.length+' engineering rules · '+
 c.ERROR+' errors · '+c.WARNING+' warnings · '+c.INFO+' informational · '+
 c.auto+' findings linked to '+c.autoActions+' distinct Auto fix actions · '+c.manual+' manual fix / review · '+c.evidence+' evidence-only · '+
 c.keep+' preserve. By class: '+
 c.categories.gaps+' possible gaps/termination reviews, '+c.categories.connection+' connection/identity, '+c.categories.overlap+' overlap, '+
 c.categories.component+' component topology, '+c.categories.non_topology+' non-topology.'+
 ' Compatible ports use the inclusive ≤25 mm repair policy; unresolved connections remain for review. Original source unchanged.';
}
