/** UXML-PREVIEW: read-only presentation for the published S2 ops envelope.
 * All rows are derived from the pinned reader and existing Python exporter.
 * No Apply, approval, queue admission, modified source or full-file export.
 */
export const OPS_PREVIEW_SCHEMA='uxml-operations-preview/v1';
const keys=Object.freeze(['opId','kind','kindName','sourceActionId',
  'uxmlIds','sourceRecords','changes','policyReason']);
const text=value=>value===null||value===undefined?'(absent)':String(value);

export function assertOperationsPreview(preview,sourceSha256){
  if(!preview||preview.schema!==OPS_PREVIEW_SCHEMA||
    preview.sourceSha256!==sourceSha256||!Array.isArray(preview.ops)||
    !preview.summary||preview.summary.totalOps!==preview.ops.length||
    !Number.isSafeInteger(preview.summary.untouchedRecordCount)||
    preview.summary.untouchedRecordCount<0||
    !Number.isSafeInteger(preview.summary.sourceRecordCount)||
    !preview.summary.byKind||typeof preview.summary.byKind!=='object')
    throw Error('UXML_OPS_PREVIEW_SOURCE_OR_SCHEMA_MISMATCH');
  const counts={},changed=new Set(),seen=new Set();
  for(const row of preview.ops){
    if(!row||keys.some(k=>!(k in row))||
       !/^UXML-OP-/.test(row.opId)||seen.has(row.opId)||
       !Array.isArray(row.uxmlIds)||!row.uxmlIds.every(x=>typeof x==='string')||
       !Array.isArray(row.sourceRecords)||!row.sourceRecords.length||
       row.sourceRecords.some(x=>x.format!=='PSI116'||typeof x.recordKey!=='string')||
       !Array.isArray(row.changes)||!row.changes.length||
       row.changes.some(x=>typeof x.recordKey!=='string'||
         typeof x.field!=='string'||!row.sourceRecords.some(r=>r.recordKey===x.recordKey)))
      throw Error('UXML_OPS_PREVIEW_ROW_INVALID');
    seen.add(row.opId);
    counts[row.kind]=(counts[row.kind]||0)+1;
    for(const change of row.changes)changed.add(change.recordKey);
  }
  if(JSON.stringify(Object.entries(counts).sort())!==
       JSON.stringify(Object.entries(preview.summary.byKind).sort())||
     preview.summary.sourceRecordCount-changed.size!==preview.summary.untouchedRecordCount)
    throw Error('UXML_OPS_PREVIEW_SUMMARY_MISMATCH');
  return preview;
}
export function filterOperationRows(preview,{kind='all',search=''}={}){
  const query=search.trim().toLowerCase();
  return (preview?.ops||[]).filter(row=>
    (kind==='all'||row.kind===kind)&&(!query||
       row.sourceRecords.some(record=>record.recordKey.toLowerCase().includes(query))));
}
export function kindCounts(preview){
  const names=new Map((preview?.ops||[]).map(row=>[row.kind,row.kindName]));
  return Object.entries(preview?.summary?.byKind||{}).sort(([a],[b])=>a.localeCompare(b))
    .map(([kind,count])=>({kind,count,name:names.get(kind)||kind.replaceAll('_',' ').toLowerCase()}));
}
export function visibleOperationExport(preview,reviewOnlyCount=0){
  // Deliberately omit source SHA, original XML and every unseen UXML field.
  return {schema:OPS_PREVIEW_SCHEMA,
    summary:{totalOps:preview.summary.totalOps,
      byKind:{...preview.summary.byKind},
      untouchedRecordCount:preview.summary.untouchedRecordCount,
      sourceRecordCount:preview.summary.sourceRecordCount,reviewOnlyCount},
    operations:preview.ops.map(row=>({
      opId:row.opId,kind:row.kind,kindName:row.kindName,
      uxmlIds:[...row.uxmlIds],
      sourceRecords:row.sourceRecords.map(r=>({format:r.format,recordKey:r.recordKey,
        changed:r.changed===true})),
      changes:row.changes.map(c=>({recordKey:c.recordKey,field:c.field,
        before:c.before,after:c.after})),
      policyReason:row.policyReason,
    }))};
}
function csvCell(value){
  let valueText=text(value);
  // Escape spreadsheet-formula introductions without leaking any extra data.
  if(/^[\s]*[=+@-]/.test(valueText))valueText="'"+valueText;
  return '"'+valueText.replaceAll('"','""')+'"';
}
export function operationsCSV(preview,reviewOnlyCount=0){
  const published=visibleOperationExport(preview,reviewOnlyCount);
  const header=['Operation ID','Kind','UXML IDs','Original source records',
    'Before → after fields','Auto eligibility reason'];
  const rows=published.operations.map(row=>[
    row.opId,row.kindName,row.uxmlIds.join('; '),
    row.sourceRecords.map(r=>r.format+':'+r.recordKey+
      (r.changed?' (changes)':' (witness)')).join('; '),
    row.changes.map(c=>c.recordKey+'.'+c.field+': '+
      text(c.before)+' → '+text(c.after)).join('; '),
    row.policyReason,
  ]);
  return [header,...rows].map(line=>line.map(csvCell).join(',')).join('\n')+'\n';
}
