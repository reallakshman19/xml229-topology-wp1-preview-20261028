/** Standalone preview Chromium journey: exact public fixture, real Pyodide and rule audit. */
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const sourceRoot=process.cwd();
const root=path.join(sourceRoot,'dist');
const mime={'.html':'text/html;charset=utf-8','.mjs':'text/javascript;charset=utf-8','.js':'text/javascript;charset=utf-8','.css':'text/css;charset=utf-8','.json':'application/json','.py':'text/plain;charset=utf-8','.wasm':'application/wasm','.zip':'application/zip'};
const server=createServer(async(req,res)=>{
 try{
  const relative=decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/^\/+/,'')||'index.html';
  const abs=path.resolve(root,relative);
  if(!abs.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
  const body=await readFile(abs);res.setHeader('Content-Type',mime[path.extname(abs)]||'application/octet-stream');res.writeHead(200);res.end(body);
 }catch(e){res.writeHead(404);res.end(String(e));}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const port=server.address().port;
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:960}});
const pageErrors=[];page.on('pageerror',e=>pageErrors.push(String(e)));page.on('console',msg=>{if(msg.type()==='error')pageErrors.push('console:'+msg.text());});
const result={};
try{
 await page.goto('http://127.0.0.1:'+port+'/index.html');
 await page.locator('[data-file]').setInputFiles(path.join(sourceRoot,'tests','FirstpassXML'));
 await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('216 of 216'),null,{timeout:30000});
 result.loaded=true;
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 result.summary=await page.locator('[data-plan-summary]').textContent();
 result.filterCounts=Object.fromEntries(await Promise.all(
  ['all','error','warning','auto','manual','evidence'].map(async key=>
   [key,await page.locator('[data-audit-filter="'+key+'"]').textContent()])));
 // Ten formerly mutating removals now retain both linked findings as review evidence.
 const expected={all:220,error:0,warning:161,auto:72,manual:24,evidence:18};
 for(const [key,count] of Object.entries(expected))
  if(!result.filterCounts[key].includes('('+count+')'))
   throw Error('Filter count drift: '+key+' actual '+result.filterCounts[key]);
 if(!((await page.locator('[data-auto-fix-all]').textContent()).includes('(72 actions)')))
   throw Error('Distinct action count not shown for Autofix-All');
 await page.locator('[data-audit-filter="error"]').click();
 result.emptyError=await page.locator('[data-issues]').textContent();
 if(!result.emptyError.includes('No ERROR findings')||
    !result.emptyError.includes('not proof of complete network connectivity'))
   throw Error('ERROR tab missing clear empty state');
 await page.locator('[data-audit-filter="all"]').click();
 const preservation=page.locator('.audit-item').filter({hasText:'ABSORBED_PIPE_HAS_COMPONENT_REF_NO'}).first();
 if(!await preservation.count())throw Error('Missing original reference-bearing preservation review');
 const guidance=await preservation.locator('.audit-remedy').textContent();
 if(!guidance.includes('B3:N1600:S2')||!guidance.includes('B3:N1610:S3')||
    !guidance.includes('ComponentRefNo')||!guidance.includes('re-export')||!guidance.includes('rerun'))
   throw Error('Manual preservation directions must name source, owner, reference and recheck');
 if(await preservation.locator('[data-auto-fix]').count())throw Error('Unsafe source review offers Auto fix');
 result.manualPreservationGuidance='PASS: exact source/owner/reference, no Auto fix, re-export and recheck';
 result.ruleGroups=await page.locator('.audit-rule').count();
 result.autofixCandidates=await page.locator('[data-auto-fix]').count();
 result.warningFound=await page.locator('.audit-severity.warning').count();
 result.gapCoverage=await page.locator('.audit-coverage').textContent();
 if(!result.gapCoverage.includes('ACTIVE')||!result.gapCoverage.includes('≤25 mm'))throw Error('Port coverage must show the active inclusive repair policy');
 await page.locator('[data-audit-category]').selectOption('gaps');
 result.gapGroups=await page.locator('.audit-rule').count();
 result.gapItems=await page.locator('.audit-item').count();
 if(result.gapItems<1)throw Error('Reference file must show evidence-qualified open ends');
 if(await page.locator('[data-audit-category]').inputValue()!=='gaps')throw Error('Gap filter did not activate');
 if(!await page.locator('.audit-item [data-auto-fix]').count())throw Error('Qualified port closures must offer Auto fix');
 const gapRule=page.locator('.audit-rule').first();
 if(!(await gapRule.evaluate(el=>el.open)))await gapRule.locator('summary').first().click();
 const review=page.locator('.audit-item').filter({has:page.locator('[data-save-gap-review]')}).first();
 await review.locator('xpath=ancestor::details[contains(@class,"audit-rule")]').evaluate(el=>el.open=true);
 await review.locator('[data-gap-review-choice]').selectOption('intentional');
 await review.locator('[data-gap-review-note]').fill('P&ID-TEST-001: owner review labels this endpoint as intentional');
 await review.locator('[data-save-gap-review]').click();
 result.reviewLabel=await page.locator('.audit-review-saved').first().textContent();
 if(!result.reviewLabel.includes('Intentional termination'))throw Error('Manual termination choice not saved');
 if(await page.locator('[data-download-gap-review]').isDisabled())throw Error('Review receipt not offered');
 const downloading=page.waitForEvent('download');
 await page.locator('[data-download-gap-review]').click();
 const reviewFile=await downloading;
 const reviewJson=JSON.parse(await readFile(await reviewFile.path(),'utf8'));
 if(reviewJson?.schema!=='xml229-preview-gap-review/v1'||
    reviewJson.source?.sha256!=='feee5a5a6399207337e63bc56c8afb001fe37ab30c6a7a9283333ec60f6eea38'||
    reviewJson.decisions?.length!==1||
    reviewJson.decisions[0]?.disposition!=='intentional'||
    reviewJson.status!=='REVIEWER_ANNOTATIONS_ONLY_NOT_CONNECTION_CERTIFICATION')
   throw Error('Gap review receipt not linked to original XML or carries invalid authority');
 result.reviewReceipt='PASS: source-qualified, not engineering certification';
 await page.locator('[data-audit-category]').selectOption('all');
 result.categories=await page.locator('.audit-category').count();
 if(result.categories<2)throw Error('Issue categories missing');
 await page.locator('[data-audit-category]').selectOption('overlap');
 result.overlapGroups=await page.locator('.audit-rule').count();
 if(!result.overlapGroups)throw Error('Expected overlap findings in reference fixture');
 const overlapLabel=await page.locator('.audit-category h3').first().textContent();
 if(!overlapLabel.includes('Overlaps'))throw Error('Overlap filter mixed wrong categories');
 await page.locator('[data-audit-category]').selectOption('non_topology');
 result.nonTopologyGroups=await page.locator('.audit-rule').count();
 await page.locator('[data-audit-category]').selectOption('all');
 if(!result.ruleGroups||!result.warningFound||!result.autofixCandidates)throw Error('Audit missing grouping, severity or Auto fix controls');
 await page.locator('[data-audit-filter="manual"]').click();
 result.manualFilter=await page.locator('.audit-rule').count();
 await page.locator('[data-audit-filter="all"]').click();
 await page.locator('[data-auto-fix]').first().click();
 await page.waitForFunction(()=>['ready','rejected'].includes(document.querySelector('[data-fix-result]')?.getAttribute('data-result')),null,{timeout:120000});
 result.fixState=await page.locator('[data-fix-result]').getAttribute('data-result');
 result.fixMessage=await page.locator('[data-fix-result]').textContent();
 if(result.fixState!=='ready')throw Error('Single fix must be applied: '+result.fixMessage);
 result.singleProgress=await page.locator('[data-progress]').textContent();
 if(!result.singleProgress.includes('APPLIED · revision 1')||
    await page.locator('[data-download-working]').isDisabled())throw Error('Working copy update not visible');
 result.afterSingleAuto=await page.locator('[data-auto-fix-all]').textContent();
 if(result.afterSingleAuto.includes('(72 actions)'))throw Error('Single applied fix left original actionable count');
 if(result.fixState==='ready' && !(await page.locator('[data-download-fix]').count()))throw Error('Missing validated XML download action');
 // Reset explicitly to the same S0 for the established independent batch oracle.
 await page.locator('[data-file]').setInputFiles(path.join(sourceRoot,'tests','FirstpassXML'));
 await page.waitForFunction(()=>document.querySelector('[data-progress]')?.textContent?.includes('revision 0'));
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 await page.locator('[data-auto-fix-all]').click();
 result.batchPreview=await page.locator('[data-batch-confirm]').textContent();
 if(!result.batchPreview.includes('72 eligible XML-changing actions')||
    !result.batchPreview.includes('conflict-free actions'))
   throw Error('Batch preview missing eligible and excluded count');
 const selected=Number(result.batchPreview.match(/([0-9]+) conflict-free actions/)?.[1]);
 if(!Number.isInteger(selected)||selected!==42)
   throw Error('Invalid conflict-free action count');
 await page.locator('[data-run-auto-fix-all]').click();
 await page.waitForFunction(()=>['ready','rejected'].includes(
   document.querySelector('[data-fix-result]')?.getAttribute('data-result'))&&document.querySelector('main').getAttribute('aria-busy')==='false',null,{timeout:180000});
 result.batchState=await page.locator('[data-fix-result]').getAttribute('data-result');
 result.batchMessage=await page.locator('[data-fix-result]').textContent();
 if(result.batchState!=='ready')
   throw Error('Autofix-All must produce a validated copy for reference fixture: '+result.batchMessage);
 const dl=page.waitForEvent('download');
 await page.locator('[data-download-fix]').click();
 const output=await dl;
 result.batchOutputName=output.suggestedFilename();
 result.batchApplied=Number(result.batchOutputName.match(
  /[.]batch-([0-9]+)[.]validated[.]topofix[.]xml/)?.[1]);
 if(!Number.isInteger(result.batchApplied)||result.batchApplied<1||
    result.batchApplied!==42)
   throw Error('Batch output does not reflect actual validated action count');
 const xml=await readFile(await output.path(),'utf8');
 if(!xml.includes('PipeStressExport'))throw Error('Batch fixed XML missing expected source root');
 const reportDownload=page.waitForEvent('download');
 await page.locator('[data-download-batch-report]').click();
 const reportFile=await reportDownload;
 const report=JSON.parse(await readFile(await reportFile.path(),'utf8'));
 const sha=createHash('sha256').update(xml).digest('hex');
 if(report.schema!=='xml229-preview-batch-topofix/v1'||
    report.status!=='VALIDATED_COPY_NOT_ENGINEERING_ACCEPTANCE'||
    report.source?.sha256!=='feee5a5a6399207337e63bc56c8afb001fe37ab30c6a7a9283333ec60f6eea38'||
    report.fixedXmlSha256!==sha||report.selectedActionIds.length!==42||report.excludedActions.length!==30)
   throw Error('Batch receipt does not reconcile source-bound actions and exclusions');
 const original=await readFile(path.join(sourceRoot,'tests','FirstpassXML'),'utf8');
 const preservationCheck=await page.evaluate(({original,xml})=>{
   const parse=text=>new DOMParser().parseFromString(text,'application/xml');
   const nodes=doc=>[...doc.getElementsByTagNameNS('*','Node')];
   const signature=el=>[el.namespaceURI,el.localName,
     [...el.attributes].map(a=>[a.namespaceURI,a.localName,a.value]).sort(),
     el.localName==='NodeNumber'?'AUTHORIZED_ALIAS':el.children.length?'':el.textContent.trim(),
     [...el.children].map(signature)];
   const before=nodes(parse(original)),after=nodes(parse(xml));
   return {before:before.length,after:after.length,
     allRecordFieldsExceptNodeNumberPreserved:JSON.stringify(before.map(signature))===JSON.stringify(after.map(signature))};
 },{original,xml});
 if(preservationCheck.before!==216||preservationCheck.after!==216||
    !preservationCheck.allRecordFieldsExceptNodeNumberPreserved)
   throw Error('Source-record or engineering-field loss in browser output');
 result.sourcePreservation=preservationCheck;
 await mkdir(path.join(sourceRoot,'preview-test-results'),{recursive:true});
 // Retain the actual exported receipt for this new candidate, not a schema projection.
 await writeFile(path.join(sourceRoot,'preview-test-results','FirstpassXML.autofix-batch-report.json'),JSON.stringify(report,null,2)+'\n');
 result.batchExcluded=report.excludedActions.length;
 result.batchSourceSha=report.source.sha256;
 result.batchOutputSha=sha;
 result.originalOccurrences=await page.locator('[data-occ-summary]').textContent();
 result.batchProgress=await page.locator('[data-progress]').textContent();
 if(!result.batchProgress.includes('42 action(s) applied')||!result.batchProgress.includes('135'))throw Error('Batch completion is not visible');
 const afterBatch=await page.locator('[data-auto-fix-all]').textContent();
 if(afterBatch.includes('(72 actions)'))throw Error('Batch left stale original action counts');
 // Real Pyodide closure, working-copy recheck, changed geometry, download and history.
 result.jointRepairs=[];
 for(const join of [125,124.9,98,100]){
  const nodes=[[10,'A',1,0],[20,'A',2,100],[30,'B',1,join],[40,'B',2,200]];
  const fixture='<PipeStressExport><Branch><Branchname>JOINT-TEST</Branchname>'+nodes.map(([n,ref,end,x])=>
    `<Node><NodeNumber>${n}</NodeNumber><ComponentType>PIPE</ComponentType><ComponentRefNo>PIPE-${ref}</ComponentRefNo><Endpoint>${end}</Endpoint><Position>${x} 0 0</Position><WallThickness>3.5</WallThickness></Node>`).join('')+'</Branch></PipeStressExport>';
  await page.locator('[data-file]').setInputFiles({name:'joint-test.xml',mimeType:'application/xml',buffer:Buffer.from(fixture)});
  await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('4 of 4'));
  await page.locator('[data-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
  const joint=page.locator('.audit-item').filter({has:page.locator('[data-auto-fix]')}).first();
  await joint.locator('xpath=ancestor::details[contains(@class,"audit-rule")]').evaluate(el=>el.open=true);
  await joint.locator('[data-auto-fix]').click();
  await page.waitForFunction(()=>['ready','rejected'].includes(document.querySelector('[data-fix-result]')?.getAttribute('data-result')),null,{timeout:120000});
  const message=await page.locator('[data-fix-result]').textContent();
  if(await page.locator('[data-fix-result]').getAttribute('data-result')!=='ready')throw Error('Joint '+join+' rejected: '+message);
  const downloadingJoint=page.waitForEvent('download');await page.locator('[data-download-working]').click();
  const downloadedJoint=await downloadingJoint,closed=await readFile(await downloadedJoint.path(),'utf8');
  const ports=await page.evaluate(xml=>[...new DOMParser().parseFromString(xml,'application/xml').getElementsByTagNameNS('*','Node')].map(n=>({
    number:n.getElementsByTagNameNS('*','NodeNumber')[0].textContent,
    xyz:n.getElementsByTagNameNS('*','Position')[0].textContent,
    ref:n.getElementsByTagNameNS('*','ComponentRefNo')[0].textContent})),closed);
  if(ports.length!==4||ports[2].number!=='20'||ports[2].xyz!=='100 0 0'||ports[2].ref!=='PIPE-B')throw Error('Joint output changed wrong ownership or geometry');
  const historyDownload=page.waitForEvent('download');await page.locator('[data-download-history]').click();
  const history=JSON.parse(await readFile(await (await historyDownload).path(),'utf8'));
  if(history.repairs[0].operations[0].before.Position!==join+' 0 0'||history.repairs[0].operations[0].after.Position!=='100 0 0')throw Error('Missing joint before/after receipt');
  result.jointRepairs.push({join,progress:await page.locator('[data-progress]').textContent(),ports,history:'PASS'});
 }
 const fittingNodes=[[10,'A',1,0],[20,'A',2,86],[30,'B',1,96],[40,'B',2,182],[50,'C',1,192],[60,'C',2,278]];
 const chain='<PipeStressExport><Branch><Branchname>CHAIN</Branchname>'+fittingNodes.map(([n,ref,end,x])=>
   `<Node><NodeNumber>${n}</NodeNumber><ComponentType>FLAN</ComponentType><ComponentRefNo>${ref}</ComponentRefNo><Endpoint>${end}</Endpoint><Position>${x} 0 0</Position></Node>`).join('')+'</Branch></PipeStressExport>';
 await page.locator('[data-file]').setInputFiles({name:'chain.xml',mimeType:'application/xml',buffer:Buffer.from(chain)});
 await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('6 of 6'));
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 await page.locator('[data-auto-fix-all]').click();await page.locator('[data-run-auto-fix-all]').click();
 await page.waitForFunction(()=>document.querySelector('main').getAttribute('aria-busy')==='false'&&
   ['ready','rejected'].includes(document.querySelector('[data-fix-result]')?.getAttribute('data-result')),null,{timeout:120000});
 result.multiPass=await page.locator('[data-progress]').textContent();
 if(!result.multiPass.includes('2 validated passes')||!result.multiPass.includes('0 eligible actions remain'))throw Error('Autofix-All did not finish the conflicting fitting chain: '+result.multiPass);
 const multiDownload=page.waitForEvent('download');await page.locator('[data-download-batch-report]').click();
 const multiReport=JSON.parse(await readFile(await (await multiDownload).path(),'utf8'));
 if(multiReport.schema!=='xml229-preview-batch-topofix/v2'||multiReport.passes.length!==2||multiReport.appliedActionCount!==2)throw Error('Missing multi-pass source-bound report');
 // Source-evidenced closure resolves without a geometry edit and is exportable.
 const closed='<PipeStressExport><Branch><Branchname>CLOSED</Branchname><Node><NodeNumber>-1</NodeNumber><ComponentType>BRAN</ComponentType><ComponentRefNo>B</ComponentRefNo><Endpoint>1</Endpoint><ConnectionType>CLOS</ConnectionType><Position>0 0 0</Position></Node><Node><NodeNumber>10</NodeNumber><ComponentType>FBLI</ComponentType><ComponentRefNo>F</ComponentRefNo><Endpoint>1</Endpoint><Position>0 0 0</Position></Node><Node><NodeNumber>-1</NodeNumber><ComponentType>FBLI</ComponentType><ComponentRefNo>F</ComponentRefNo><Endpoint>2</Endpoint><Position>32.2 0 0</Position></Node></Branch></PipeStressExport>';
 await page.locator('[data-file]').setInputFiles({name:'closed.xml',mimeType:'application/xml',buffer:Buffer.from(closed)});
 await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('3 of 3'));
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 result.resolvedEvidence=await page.locator('[data-resolved]').textContent();
 if(!result.resolvedEvidence.includes('DECLARED CLOSED END'))throw Error('Source closure evidence not shown');
 const evidenceDownload=page.waitForEvent('download');await page.locator('[data-download-resolutions]').click();
 const evidence=JSON.parse(await readFile(await (await evidenceDownload).path(),'utf8'));
 if(!evidence.resolvedConnections.some(x=>x.code==='DECLARED_CLOSED_END')||evidence.xmlChangedByResolution!==false)throw Error('Source closure receipt missing');
 await mkdir(path.join(sourceRoot,'preview-test-results'),{recursive:true});
 await page.screenshot({path:path.join(sourceRoot,'preview-test-results','rule-audit.png'),fullPage:true});
 if(pageErrors.length)throw Error('Browser errors: '+pageErrors.join(' | '));
 result.status='PASS';
}catch(e){result.status='FAIL';result.error=String(e);throw e;}
finally{
 result.pageErrors=pageErrors;
 await writeFile(path.join(sourceRoot,'preview-test-results.json'),JSON.stringify(result,null,2)+'\n');
 await browser.close();await new Promise(resolve=>server.close(resolve));
 console.log(JSON.stringify(result,null,2));
}
