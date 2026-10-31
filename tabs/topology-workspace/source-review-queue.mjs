/** TOPO-A-P2. Pure, read-only Source Review Queue data. No repair/solver imports. */
export const SOURCE_REVIEW_SCHEMA='topofix-source-review-queue/v1';
export const SOURCE_REVIEW_KIND='SOURCE_REVIEW_ONLY_NO_XML_CHANGE';
export const SOURCE_REVIEW_DECISIONS=Object.freeze([
  'INTENTIONAL_TERMINATION','DRAWING_CHECK_PENDING',
  'UPSTREAM_SOURCE_CORRECTION_REQUIRED','NO_RELIABLE_DESIGN_AUTHORITY'
]);
const SHA=/^[a-f0-9]{64}$/;
const SOURCE_KEY=/^B[0-9]+:N-?[0-9]+:S[0-9]+$/;
const ROW_KEYS=['id','kind','sourceSha256','ports','disposition','distanceMm',
  'decision','note','createdAt','updatedAt'];
const PORT_KEYS=['sourceKey','branch','branchIndex','nodeNumber','endpoint','owner'];
const OWNER_KEYS=['componentType','refNo'];
const ENVELOPE_KEYS=['schema','kind','exportedAt','sourceSha256','rows'];
const exactKeys=(obj,allowed)=>{
  if(!obj||typeof obj!=='object'||Array.isArray(obj)||
     Object.keys(obj).some(k=>!allowed.includes(k)))
    throw Error('SOURCE_REVIEW_UNEXPECTED_FIELD');
};
const validTime=value=>typeof value==='string'&&Number.isFinite(Date.parse(value))&&
  new Date(value).toISOString()===value;
const nowISO=()=>new Date().toISOString();
const validSha=value=>typeof value==='string'&&SHA.test(value);
const nonempty=(x,max=256)=>typeof x==='string'&&x.length>0&&x.length<=max;
const validDecision=d=>SOURCE_REVIEW_DECISIONS.includes(d);
const cleanNote=n=>{
  if(typeof n!=='string'||n.length>4000)throw Error('SOURCE_REVIEW_NOTE_INVALID');
  return n;
};
function portFromRecord(r){
  if(!r)throw Error('SOURCE_REVIEW_PORT_MISSING');
  return {sourceKey:r.key,branch:String(r.branchName||''),
    branchIndex:r.branchIndex,nodeNumber:r.nodeNumber,
    endpoint:String(r.endpoint??''),owner:{
      componentType:String(r.type||''),refNo:String(r.refNo||'')
    }};
}
function validatePort(p){
  exactKeys(p,PORT_KEYS);exactKeys(p.owner,OWNER_KEYS);
  if(!SOURCE_KEY.test(p.sourceKey)||!nonempty(p.branch,500)||
     !Number.isSafeInteger(p.branchIndex)||p.branchIndex<0||
     !Number.isSafeInteger(p.nodeNumber)||
     typeof p.endpoint!=='string'||p.endpoint.length>64||
     !nonempty(p.owner.componentType,100)||
     typeof p.owner.refNo!=='string'||p.owner.refNo.length>256)
    throw Error('SOURCE_REVIEW_PORT_INVALID');
  // Return allowlisted fields only: never carry executor arguments from imports.
  return {sourceKey:p.sourceKey,branch:p.branch,branchIndex:p.branchIndex,
    nodeNumber:p.nodeNumber,endpoint:p.endpoint,
    owner:{componentType:p.owner.componentType,refNo:p.owner.refNo}};
}
export function sourceReviewPairId(sha,a,b){
  if(!validSha(sha)||!SOURCE_KEY.test(a)||!SOURCE_KEY.test(b)||a===b)
    throw Error('SOURCE_REVIEW_IDENTITY_INVALID');
  return sha+'|'+[a,b].sort().join('|');
}
export function canAddSourceReview(r){
  return !!(r?.status==='REVIEW ONLY'&&validSha(r.sourceSha256)&&
    r.a&&r.b&&r.a.key!==r.b.key&&
    SOURCE_KEY.test(r.a.key)&&SOURCE_KEY.test(r.b.key));
}
function normalizedRow(row){
  exactKeys(row,ROW_KEYS);
  if(row.kind!==SOURCE_REVIEW_KIND||!validSha(row.sourceSha256)||
     !Array.isArray(row.ports)||row.ports.length!==2||
     !nonempty(row.disposition,128)||
     !(row.distanceMm===null||(typeof row.distanceMm==='number'&&
       Number.isFinite(row.distanceMm)&&row.distanceMm>=0))||
     !validDecision(row.decision)||!validTime(row.createdAt)||!validTime(row.updatedAt)||
     Date.parse(row.updatedAt)<Date.parse(row.createdAt))
    throw Error('SOURCE_REVIEW_ROW_INVALID');
  const ports=row.ports.map(validatePort).sort((a,b)=>a.sourceKey.localeCompare(b.sourceKey));
  const id=sourceReviewPairId(row.sourceSha256,ports[0].sourceKey,ports[1].sourceKey);
  if(row.id!==id)throw Error('SOURCE_REVIEW_ROW_ID_DRIFT');
  return {id,kind:SOURCE_REVIEW_KIND,sourceSha256:row.sourceSha256,ports,
    disposition:row.disposition,distanceMm:row.distanceMm,decision:row.decision,
    note:cleanNote(row.note),createdAt:row.createdAt,updatedAt:row.updatedAt};
}
export function sourceReviewStatus(row,currentSourceSha){
  return row.sourceSha256===currentSourceSha?'CURRENT_SOURCE':'STALE_SOURCE';
}
export function upsertSourceReview(rows,result,options={}){
  if(!canAddSourceReview(result))throw Error('SOURCE_REVIEW_EXACT_PAIR_REQUIRED');
  const decision=options.decision||'DRAWING_CHECK_PENDING';
  if(!validDecision(decision))throw Error('SOURCE_REVIEW_DECISION_INVALID');
  const note=cleanNote(options.note??'');
  const at=options.at||nowISO();
  if(!validTime(at))throw Error('SOURCE_REVIEW_TIME_INVALID');
  const ports=[portFromRecord(result.a),portFromRecord(result.b)]
    .map(validatePort).sort((a,b)=>a.sourceKey.localeCompare(b.sourceKey));
  const id=sourceReviewPairId(result.sourceSha256,ports[0].sourceKey,ports[1].sourceKey);
  const before=rows.find(r=>r.id===id);
  const base={id,kind:SOURCE_REVIEW_KIND,sourceSha256:result.sourceSha256,
    ports,disposition:String(result.disposition),distanceMm:Number.isFinite(result.distanceMm)?
      result.distanceMm:null,
    decision,note,createdAt:before?.createdAt||at,updatedAt:at};
  const row=normalizedRow(base);
  return {rows:before?rows.map(r=>r.id===id?row:r):[...rows,row],
    row,inserted:!before};
}
export function editSourceReview(rows,id,decision,note,at=nowISO()){
  if(!validDecision(decision))throw Error('SOURCE_REVIEW_DECISION_INVALID');
  if(!validTime(at))throw Error('SOURCE_REVIEW_TIME_INVALID');
  let found=false;
  const updated=rows.map(r=>{
    if(r.id!==id)return r;
    found=true;
    return normalizedRow({...r,decision,note:cleanNote(note),updatedAt:at});
  });
  if(!found)throw Error('SOURCE_REVIEW_ROW_NOT_FOUND');
  return updated;
}
export function exportSourceReviewJSON(rows,currentSourceSha=null,at=nowISO()){
  if(!validTime(at)||!(currentSourceSha===null||validSha(currentSourceSha)))
    throw Error('SOURCE_REVIEW_EXPORT_INVALID');
  const clean=rows.map(normalizedRow);
  return JSON.stringify({schema:SOURCE_REVIEW_SCHEMA,kind:SOURCE_REVIEW_KIND,
    exportedAt:at,sourceSha256:currentSourceSha,rows:clean},null,2)+'\n';
}
export function importSourceReviewJSON(text,existing=[]){
  if(typeof text!=='string'||text.length>1048576)throw Error('SOURCE_REVIEW_IMPORT_SIZE');
  let input;
  try{input=JSON.parse(text);}catch{throw Error('SOURCE_REVIEW_IMPORT_JSON_INVALID');}
  exactKeys(input,ENVELOPE_KEYS);
  if(input.schema!==SOURCE_REVIEW_SCHEMA||input.kind!==SOURCE_REVIEW_KIND||
     !validTime(input.exportedAt)||
     !(input.sourceSha256===null||validSha(input.sourceSha256))||
     !Array.isArray(input.rows)||input.rows.length>2000)
    throw Error('SOURCE_REVIEW_IMPORT_SCHEMA_INVALID');
  const map=new Map(existing.map(r=>{const checked=normalizedRow(r);return [checked.id,checked];}));
  let added=0,updated=0;
  for(const raw of input.rows){
    const row=normalizedRow(raw);
    if(map.has(row.id))updated++;else added++;
    const previous=map.get(row.id);
    // Reimport updates the same unordered pair; retain the most recently revised record.
    if(!previous||Date.parse(row.updatedAt)>=Date.parse(previous.updatedAt))map.set(row.id,row);
  }
  return {rows:[...map.values()],added,updated};
}
const safeCSV=v=>{
  const plain=String(v??'');
  // Prevent spreadsheet formula execution on untrusted branch names and notes.
  const safe=/^[=+\-@]/.test(plain)?'\''+plain:plain;
  return '"'+safe.replace(/"/g,'""')+'"';
};
export function exportSourceReviewCSV(rows,currentSourceSha=null){
  const columns=['source_sha256','status','a_source_key','a_branch','a_node_number','a_endpoint',
    'a_owner_type','a_owner_ref','b_source_key','b_branch','b_node_number','b_endpoint',
    'b_owner_type','b_owner_ref','disposition','distance_mm','decision','note','created_at','updated_at'];
  const table=[columns.join(',')];
  for(const source of rows){
    const r=normalizedRow(source),a=r.ports[0],b=r.ports[1];
    table.push([r.sourceSha256,sourceReviewStatus(r,currentSourceSha),a.sourceKey,a.branch,
      a.nodeNumber,a.endpoint,a.owner.componentType,a.owner.refNo,b.sourceKey,b.branch,
      b.nodeNumber,b.endpoint,b.owner.componentType,b.owner.refNo,r.disposition,
      r.distanceMm===null?'':r.distanceMm.toFixed(3),r.decision,r.note,r.createdAt,
      r.updatedAt].map(safeCSV).join(','));
  }
  return table.join('\r\n')+'\r\n';
}
