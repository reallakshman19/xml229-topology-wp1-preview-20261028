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
const pageErrors=[];const observedWorkers=[];page.on('worker',w=>observedWorkers.push(w.url()));
page.on('pageerror',e=>pageErrors.push(String(e)));page.on('console',msg=>{if(msg.type()==='error')pageErrors.push('console:'+msg.text());});
const result={};
try{
 await page.goto('http://127.0.0.1:'+port+'/index.html');
 await page.locator('[data-file]').setInputFiles(path.join(sourceRoot,'tests','FirstpassXML'));
 await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('216 of 216'),null,{timeout:30000});
 result.loaded=true;
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 if(!observedWorkers.some(url=>url.includes('/topology-worker.mjs')))
  throw Error('Topology analysis must execute in a dedicated Web Worker, not on the main thread.');
 result.topologyWorker='PASS: module Worker created for PSI116 analysis';
 result.summary=await page.locator('[data-plan-summary]').textContent();
 result.filterCounts=Object.fromEntries(await Promise.all(
  ['all','error','warning','auto','manual','evidence'].map(async key=>
   [key,await page.locator('[data-audit-filter="'+key+'"]').textContent()])));
 // Ten formerly mutating removals now retain both linked findings as review evidence.
 const expected={all:210,error:0,warning:151,auto:56,manual:30,evidence:18};
 for(const [key,count] of Object.entries(expected))
  if(!result.filterCounts[key].includes('('+count+')'))
   throw Error('Filter count drift: '+key+' actual '+result.filterCounts[key]);
 if(!((await page.locator('[data-auto-fix-all]').textContent()).includes('(56 actions)')))
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
 if(await page.locator('.audit-item [data-auto-fix]').count())throw Error('Unqualified source ports must remain in review');
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
 if(result.afterSingleAuto.includes('(56 actions)'))throw Error('Single applied fix left original actionable count');
 if(result.fixState==='ready' && !(await page.locator('[data-download-fix]').count()))throw Error('Missing validated XML download action');
 // Reset explicitly to the same S0 for the established independent batch oracle.
 await page.locator('[data-file]').setInputFiles(path.join(sourceRoot,'tests','FirstpassXML'));
 await page.waitForFunction(()=>document.querySelector('[data-progress]')?.textContent?.includes('revision 0'));
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 await page.locator('[data-auto-fix-all]').click();
 result.batchPreview=await page.locator('[data-batch-confirm]').textContent();
 if(!result.batchPreview.includes('56 eligible XML-changing actions')||
    !result.batchPreview.includes('conflict-free actions'))
   throw Error('Batch preview missing eligible and excluded count');
 const selected=Number(result.batchPreview.match(/([0-9]+) conflict-free actions/)?.[1]);
 if(!Number.isInteger(selected)||selected!==39)
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
    result.batchApplied!==46)
   throw Error('Batch output does not reflect actual validated action count');
 const xml=await readFile(await output.path(),'utf8');
 if(!xml.includes('PipeStressExport'))throw Error('Batch fixed XML missing expected source root');
 const reportDownload=page.waitForEvent('download');
 await page.locator('[data-download-batch-report]').click();
 const reportFile=await reportDownload;
 const report=JSON.parse(await readFile(await reportFile.path(),'utf8'));
 const sha=createHash('sha256').update(xml).digest('hex');
 if(report.schema!=='xml229-preview-batch-topofix/v2'||
    report.status!=='VALIDATED_COPY_NOT_ENGINEERING_ACCEPTANCE'||
    report.source?.sha256!=='feee5a5a6399207337e63bc56c8afb001fe37ab30c6a7a9283333ec60f6eea38'||
    report.fixedXmlSha256!==sha||report.appliedActionCount!==46||report.passes?.length!==2||
    report.remainingEligibleActions!==0||report.stopReason!=='COMPLETE'||
    report.passes[0].selectedActionIds.length!==39||report.passes[0].excludedActions.length!==17||
    report.passes[1].selectedActionIds.length!==7)
   throw Error('Batch receipt does not reconcile source-bound passes, actions and exclusions');
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
 result.batchExcluded=report.passes.reduce((n,p)=>n+p.excludedActions.length,0);
 result.batchSourceSha=report.source.sha256;
 result.batchOutputSha=sha;
 result.originalOccurrences=await page.locator('[data-occ-summary]').textContent();
 result.batchProgress=await page.locator('[data-progress]').textContent();
 if(!result.batchProgress.includes('46 action(s)')||!result.batchProgress.includes('141'))throw Error('Batch completion is not visible');
 const afterBatch=await page.locator('[data-auto-fix-all]').textContent();
 if(afterBatch.includes('(56 actions)'))throw Error('Batch left stale original action counts');
 // Real Pyodide closure, working-copy recheck, changed geometry, download and history.
 result.jointRepairs=[];
 for(const join of [125,124.9,98,100]){
  const nodes=[[10,'A',1,0],[20,'A',2,100],[30,'B',1,join],[40,'B',2,200]];
  const fixture='<PipeStressExport><Branch><Branchname>JOINT-TEST</Branchname>'+nodes.map(([n,ref,end,x])=>
    `<Node><NodeNumber>${n}</NodeNumber><ComponentType>PIPE</ComponentType><ComponentRefNo>PIPE-${ref}</ComponentRefNo><Endpoint>${end}</Endpoint><Position>${x} 0 0</Position><WallThickness>3.5</WallThickness><OutsideDiameter>100</OutsideDiameter></Node>`).join('')+'</Branch></PipeStressExport>';
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
 const negativePorts=[
  ['missing-diameter','<PipeStressExport><Branch><Branchname>UNKNOWN</Branchname>'+[[10,'A',1,0],[20,'A',2,100],[30,'B',1,112],[40,'B',2,200]].map(([n,ref,end,x])=>`<Node><NodeNumber>${n}</NodeNumber><ComponentType>PIPE</ComponentType><ComponentRefNo>${ref}</ComponentRefNo><Endpoint>${end}</Endpoint><Position>${x} 0 0</Position></Node>`).join('')+'</Branch></PipeStressExport>'],
  ['missing-direction','<PipeStressExport><Branch><Branchname>A</Branchname><Node><NodeNumber>10</NodeNumber><ComponentType>PIPE</ComponentType><ComponentRefNo>P</ComponentRefNo><Endpoint>1</Endpoint><Position>0 0 0</Position><OutsideDiameter>100</OutsideDiameter></Node><Node><NodeNumber>20</NodeNumber><ComponentType>PIPE</ComponentType><ComponentRefNo>P</ComponentRefNo><Endpoint>2</Endpoint><Position>100 0 0</Position><OutsideDiameter>100</OutsideDiameter></Node></Branch><Branch><Branchname>B</Branchname><Node><NodeNumber>30</NodeNumber><ComponentType>CAP</ComponentType><ComponentRefNo>C</ComponentRefNo><Endpoint>1</Endpoint><Position>112 0 0</Position><OutsideDiameter>100</OutsideDiameter></Node></Branch></PipeStressExport>']
 ];
 result.compatibilityNegatives=[];
 for(const [label,fixture] of negativePorts){
  await page.locator('[data-file]').setInputFiles({name:label+'.xml',mimeType:'application/xml',buffer:Buffer.from(fixture)});
  await page.waitForFunction(()=>!document.querySelector('[data-analyze]').disabled);
  await page.locator('[data-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
  if(await page.locator('[data-auto-fix]').count())throw Error('Unqualified '+label+' offered automatic closure');
  result.compatibilityNegatives.push(label+': PASS');
 }
 // F4: exact declaration/owner matching, including coincident audit conflicts.
 const junctionNode=(n,kind,ref,end,xyz,extra='')=>`<Node><NodeNumber>${n}</NodeNumber><ComponentType>${kind}</ComponentType><ComponentRefNo>${ref}</ComponentRefNo><Endpoint>${end}</Endpoint><Position>${xyz}</Position>${extra}</Node>`;
 const junctionFixture=(declared,owner,offset)=>'<PipeStressExport><Branch><Branchname>JUNCTION</Branchname>'+
  junctionNode(-1,owner,'J',1,'0 0 0')+junctionNode(50,owner,'J',0,'100 0 0')+
  junctionNode(-1,owner,'J',2,'200 0 0')+junctionNode(-1,owner,'J',3,'100 100 0')+
  '</Branch><Branch><Branchname>BRANCH</Branchname>'+junctionNode(50,'BRAN','B',1,'100 0 '+offset,'<ConnectionType>'+declared+'</ConnectionType>')+'</Branch></PipeStressExport>';
 result.junctionAuthority=[];
 for(const [declared,owner,offset] of [['TEE','TEE',25],['OLET','OLET',25],['TEE','OLET',25],['OLET','TEE',25],['TEE','OLET',0],['OLET','TEE',0]]){
  await page.locator('[data-file]').setInputFiles({name:'junction-authority.xml',mimeType:'application/xml',buffer:Buffer.from(junctionFixture(declared,owner,offset))});
  await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('5 of 5'));
  await page.locator('[data-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
  if(declared===owner){
   await page.locator('[data-auto-fix]').first().click();
   await page.waitForFunction(()=>['ready','rejected'].includes(document.querySelector('[data-fix-result]')?.getAttribute('data-result')),null,{timeout:120000});
   if(await page.locator('[data-fix-result]').getAttribute('data-result')!=='ready')throw Error('Matching '+declared+' authority rejected');
   const download=page.waitForEvent('download');await page.locator('[data-download-working]').click();
   const fixed=await readFile(await (await download).path(),'utf8');
   const branchPosition=await page.evaluate(xml=>new DOMParser().parseFromString(xml,'application/xml').getElementsByTagNameNS('*','Branch')[1].getElementsByTagNameNS('*','Position')[0].textContent,fixed);
   if(branchPosition!=='100 0 0')throw Error('Matching junction did not close to source owner');
  }else{
   if(await page.locator('[data-auto-fix]').count())throw Error('Mismatched junction offered Auto fix');
   const conflict=page.locator('.audit-item').filter({hasText:'The branch TEE/OLET declaration disagrees'}).first();
   if(!await conflict.count()||!(await conflict.locator('.audit-remedy').textContent()).includes('re-export and rerun'))throw Error('Junction mismatch lost manual source repair directions');
   if((await page.locator('[data-resolved]').textContent()).includes('B1:N50:S0'))throw Error('Mismatched junction hidden as resolved');
  }
  result.junctionAuthority.push({declared,owner,offset,outcome:declared===owner?'CLOSED':'MANUAL_CONFLICT'});
 }
 const fittingNodes=[[10,'A',1,0],[20,'A',2,86],[30,'B',1,96],[40,'B',2,182],[50,'C',1,192],[60,'C',2,278]];
 const chain='<PipeStressExport><Branch><Branchname>CHAIN</Branchname>'+fittingNodes.map(([n,ref,end,x])=>
   `<Node><NodeNumber>${n}</NodeNumber><ComponentType>FLAN</ComponentType><ComponentRefNo>${ref}</ComponentRefNo><Endpoint>${end}</Endpoint><Position>${x} 0 0</Position><OutsideDiameter>100</OutsideDiameter></Node>`).join('')+'</Branch></PipeStressExport>';
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
 // Inject an engine failure on pass 2 using the real first-pass Pyodide path.
 const failurePage=await browser.newPage({viewport:{width:1440,height:960}});
 await failurePage.goto('http://127.0.0.1:'+port+'/index.html');
 await failurePage.evaluate(async()=>{
  const {mountTopologyWorkspace}=await import('./tabs/topology-workspace/workspace-app.mjs');
  const {runXmlCii2019StandaloneEngineJob}=await import('./tabs/xml-cii-2019-standalone/xml-cii-workflow-engine-client.js');
  const old=document.querySelector('main'),fresh=old.cloneNode(true);old.replaceWith(fresh);
  let attempts=0;
  window.failureWorkspace=mountTopologyWorkspace(fresh,{runEngine:async job=>{
   if(job.options.generateTopoFix&&++attempts===2)throw Error('IR_F3_INJECTED_PASS_2_FAILURE');
   return runXmlCii2019StandaloneEngineJob(job);
  }});
 });
 await failurePage.locator('[data-file]').setInputFiles({name:'chain-failure.xml',mimeType:'application/xml',buffer:Buffer.from(chain)});
 await failurePage.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('6 of 6'));
 await failurePage.locator('[data-analyze]').click();
 await failurePage.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 await failurePage.locator('[data-auto-fix-all]').click();await failurePage.locator('[data-run-auto-fix-all]').click();
 await failurePage.waitForFunction(()=>document.querySelector('main').getAttribute('aria-busy')==='false'&&
  document.querySelector('[data-fix-result]')?.getAttribute('data-result')==='stopped',null,{timeout:120000});
 result.failedSecondPass=await failurePage.locator('[data-fix-result]').textContent();
 if(!result.failedSecondPass.includes('IR_F3_INJECTED_PASS_2_FAILURE')||!result.failedSecondPass.includes('receipt retained'))throw Error('Pass failure lost recovery guidance');
 const failureReceiptDownload=failurePage.waitForEvent('download');await failurePage.locator('[data-download-batch-report]').click();
 const failureReceipt=JSON.parse(await readFile(await (await failureReceiptDownload).path(),'utf8'));
 if(failureReceipt.passes?.length!==1||failureReceipt.stopReason!=='PASS_FAILED')throw Error('First pass receipt lost after second pass failure');
 const failureXmlDownload=failurePage.waitForEvent('download');await failurePage.locator('[data-download-fix]').click();
 const failureXml=await readFile(await (await failureXmlDownload).path(),'utf8');
 if(createHash('sha256').update(failureXml).digest('hex')!==failureReceipt.fixedXmlSha256)throw Error('Retained XML does not match retained receipt');
 await failurePage.close();
 // Optional short-element removal: complete GASK + RIGID owner, then PIPE-first closure.
 const shortNode=(n,kind,ref,end,x,extra='')=>`<Node><NodeNumber>${n}</NodeNumber><ComponentType>${kind}</ComponentType><ComponentRefNo>${ref}</ComponentRefNo><Endpoint>${end}</Endpoint><Position>${x} 0 0</Position><OutsideDiameter>100</OutsideDiameter>${extra}</Node>`;
 const shortFixture=('<PipeStressExport><Branch><Branchname>SHORT-DROP</Branchname>'+
  shortNode(10,'PIPE','P',1,0)+shortNode(20,'PIPE','P',2,100)+
  shortNode(-1,'GASK','SHORT',1,100,'<Weight>2.5</Weight>')+shortNode(30,'RIGID','SHORT',2,103)+
  shortNode(-1,'FLAN','F',1,103)+shortNode(40,'RIGID','F',2,189)+'</Branch></PipeStressExport>').replaceAll('</Node>','<BendRadius>0</BendRadius><AlphaAngle>0</AlphaAngle></Node>');
 await page.locator('[data-file]').setInputFiles({name:'short-drop.xml',mimeType:'application/xml',buffer:Buffer.from(shortFixture)});
 await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('6 of 6'));
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 await page.locator('[data-preview-short]').click();
 if(await page.locator('[data-short-index]').count()>24)throw Error('Unbounded short-element preview rendered');
 if(!(await page.locator('[data-short-preview]').textContent()).includes('PREVIEW ONLY'))throw Error('Short preview missing nonmutating status');
 const shortPreview=await page.locator('[data-short-preview]').textContent();
 if(!shortPreview.includes('GASK · 3.000 mm · SHORT · 2 records · weight 2.5')||!shortPreview.includes('B0:N30:S3'))throw Error('Short preview missing complete owner/length/weight/source census');
 await page.locator('[data-select-gaskets]').click();
 if(await page.locator('[data-short-index]:checked').count()!==1)throw Error('Gasket selection included unrelated elements');
 await mkdir(path.join(sourceRoot,'preview-test-results'),{recursive:true});
 await page.screenshot({path:path.join(sourceRoot,'preview-test-results','short-drop-preview.png'),fullPage:true});
 await page.locator('[data-run-short-drop]').click();
 await page.waitForFunction(()=>document.querySelector('main').getAttribute('aria-busy')==='false'&&['ready','stopped'].includes(document.querySelector('[data-fix-result]')?.getAttribute('data-result')),null,{timeout:120000});
 result.shortDrop=await page.locator('[data-progress]').textContent();
 if(!result.shortDrop.includes('BULK COMPLETE · selected 1 = 1 validated + 0 skipped + 0 failed + 0 unprocessed')||!(await page.locator('[data-occ-summary]').textContent()).includes('4 of 4'))throw Error('Drop did not update working geometry/counts: '+result.shortDrop);
 const shortXmlDownload=page.waitForEvent('download');await page.locator('[data-download-fix]').click();
 const shortXml=await readFile(await (await shortXmlDownload).path(),'utf8');
 const shortPorts=await page.evaluate(xml=>[...new DOMParser().parseFromString(xml,'application/xml').getElementsByTagNameNS('*','Node')].map(n=>({
  xyz:n.getElementsByTagNameNS('*','Position')[0].textContent,ref:n.getElementsByTagNameNS('*','ComponentRefNo')[0].textContent})),shortXml);
 if(JSON.stringify(shortPorts)!==JSON.stringify([{xyz:'0 0 0',ref:'P'},{xyz:'103 0 0',ref:'P'},{xyz:'103 0 0',ref:'F'},{xyz:'189 0 0',ref:'F'}]))throw Error('Drop failed PIPE-first closure or changed retained flange');
 const shortReceiptDownload=page.waitForEvent('download');await page.locator('[data-download-batch-report]').click();
 const shortReceipt=JSON.parse(await readFile(await (await shortReceiptDownload).path(),'utf8'));
 const shortPass=shortReceipt.applied?.[0];
 if(shortReceipt.schema!=='xml229-short-element-bulk/v2'||shortReceipt.stopReason!=='COMPLETE'||shortReceipt.applied.length!==1||shortPass.transaction.operations.filter(o=>o.operation==='REMOVE_SELECTED_SHORT_ELEMENT_RECORD').length!==2||
   shortReceipt.fixedXmlSha256!==createHash('sha256').update(shortXml).digest('hex')||
   shortPass.transaction.policy.short_element_requests[0].sourceSha256!==createHash('sha256').update(shortFixture).digest('hex')||
   shortPass.lineage.counts.removedSelectedShortElementOccurrences!==2||shortPass.selectedElement.weightRemoved!==2.5||
   shortPass.selectedElement.lengthBasis!=='SOURCE_STRAIGHT_TWO_PORT_SPAN'||
   !shortPass.validation.checks.some(c=>c.code==='SHORT_ELEMENT_LENGTH_BASIS_QUALIFIED'&&c.passed&&c.details.lengthBasis==='SOURCE_STRAIGHT_TWO_PORT_SPAN')||
   !shortPass.transaction.operations.some(o=>o.before?.includes?.('<ComponentType>RIGID</ComponentType>')))
   throw Error('Short removal receipt lost source selection/tombstones/lineage/weight');
 await writeFile(path.join(sourceRoot,'preview-test-results','short-drop.xml'),shortXml);
 await writeFile(path.join(sourceRoot,'preview-test-results','short-drop-receipt.json'),JSON.stringify(shortReceipt,null,2));
 await page.screenshot({path:path.join(sourceRoot,'preview-test-results','short-drop-applied.png'),fullPage:true});
 result.shortDropReceipt='PASS: source-bound whole owner, two tombstones, removed weight, lineage and matching XML hash';
 // A qualified interface with both neighbours restrained must fail atomically.
 const blockedShort=shortFixture.replaceAll('<ComponentType>PIPE</ComponentType>','<ComponentType>PIPE</ComponentType><Restraint>X</Restraint>')
  .replaceAll('<ComponentType>FLAN</ComponentType>','<ComponentType>FLAN</ComponentType><Restraint>X</Restraint>');
 await page.locator('[data-file]').setInputFiles({name:'short-drop-blocked.xml',mimeType:'application/xml',buffer:Buffer.from(blockedShort)});
 await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('6 of 6'));
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 await page.locator('[data-preview-short]').click();await page.locator('[data-select-gaskets]').click();
 await page.locator('[data-run-short-drop]').click();
 await page.waitForFunction(()=>document.querySelector('main').getAttribute('aria-busy')==='false'&&document.querySelector('[data-fix-result]')?.getAttribute('data-result')==='rejected',null,{timeout:120000});
 result.shortDropRejected=await page.locator('[data-progress]').textContent();
 if(result.shortDropRejected.includes('Traceback')||!result.shortDropRejected.includes('Check restraints, mating diameters and port directions.')||
  !result.shortDropRejected.includes('selected 1 = 0 validated + 0 skipped + 1 failed + 0 unprocessed')||!(await page.locator('[data-occ-summary]').textContent()).includes('6 of 6')||
  !(await page.locator('[data-download-working]').isDisabled())||await page.locator('[data-download-fix]').count())throw Error('Failed reconnection released a partial removal');
 // S1: zero-filled straight gaskets keep the inclusive boundary; curves/junctions are manual.
 result.shortLengthQualification=[];
 for(const length of [6,6.001]){
  const sample=shortFixture.replaceAll('103 0 0',(100+length)+' 0 0').replaceAll('189 0 0',(186+length)+' 0 0');
  await page.locator('[data-file]').setInputFiles({name:'short-length-boundary.xml',mimeType:'application/xml',buffer:Buffer.from(sample)});
  await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('6 of 6'));
  await page.locator('[data-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
  await page.locator('[data-preview-short]').click();
  if(length===6){
   if(await page.locator('[data-short-index]:not(:disabled)').count()!==1||!(await page.locator('[data-short-preview]').textContent()).includes('Length basis: straight port spacing'))throw Error('Zero-filled exactly 6 mm gasket lost qualification');
   await page.locator('[data-select-gaskets]').click();await page.locator('[data-run-short-drop]').click();
   await page.waitForFunction(()=>document.querySelector('main').getAttribute('aria-busy')==='false'&&document.querySelector('[data-fix-result]')?.getAttribute('data-result')==='ready',null,{timeout:120000});
   if(!(await page.locator('[data-occ-summary]').textContent()).includes('4 of 4'))throw Error('Exactly 6 mm gasket was not dropped and closed');
  }else if(await page.locator('[data-short-index]').count())throw Error('6.001 mm gasket offered by drop preview');
  result.shortLengthQualification.push({kind:'GASK',length,zeroFilled:true,outcome:length===6?'DROPPED_AND_CLOSED':'OVER_LIMIT'});
 }
 const curved='<PipeStressExport><Branch><Branchname>CURVED</Branchname>'+
  junctionNode(10,'PIPE','P',1,'100 0 0','<OutsideDiameter>100</OutsideDiameter>')+junctionNode(20,'PIPE','P',2,'4.1 0 0','<OutsideDiameter>100</OutsideDiameter>')+
  junctionNode(-1,'ELBO','SHORT',1,'4.1 0 0','<BendRadius>4.1</BendRadius><AlphaAngle>90</AlphaAngle>')+junctionNode(-1,'ELBO','SHORT',0,'0 0 0')+junctionNode(30,'RIGID','SHORT',2,'0 4.1 0')+
  junctionNode(-1,'FLAN','F',1,'0 4.1 0','<OutsideDiameter>100</OutsideDiameter>')+junctionNode(40,'RIGID','F',2,'0 90.1 0','<OutsideDiameter>100</OutsideDiameter>')+'</Branch></PipeStressExport>';
 for(const [kind,sample] of [['ELBO',curved],['TEE',shortFixture.replace('<ComponentType>GASK</ComponentType>','<ComponentType>TEE</ComponentType>')],['OLET',shortFixture.replace('<ComponentType>GASK</ComponentType>','<ComponentType>OLET</ComponentType>')]]){
  await page.locator('[data-file]').setInputFiles({name:'unqualified-length.xml',mimeType:'application/xml',buffer:Buffer.from(sample)});
  await page.waitForFunction(()=>!document.querySelector('[data-analyze]').disabled);
  await page.locator('[data-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
  await page.locator('[data-preview-short]').click();
  const preview=await page.locator('[data-short-preview]').textContent();
  if(await page.locator('[data-short-index]:disabled').count()!==1||!preview.includes('physical length unverified')||!preview.includes('not qualified by endpoint distance'))throw Error(kind+' chord was promoted to a physical length');
  result.shortLengthQualification.push({kind,outcome:'MANUAL_LENGTH_UNQUALIFIED'});
 }
 await page.screenshot({path:path.join(sourceRoot,'preview-test-results','short-length-guard.png'),fullPage:true});
 // Scale falsifier: 130 independent short-owner candidates must not render
 // a giant list or silently process every selected owner at once.
 const scalePage=await browser.newPage({viewport:{width:1200,height:850}});
 await scalePage.goto('http://127.0.0.1:'+port+'/index.html');
 await scalePage.evaluate(async()=>{
   const {mountTopologyWorkspace}=await import('./tabs/topology-workspace/workspace-app.mjs');
   const old=document.querySelector('main'),fresh=old.cloneNode(true);old.replaceWith(fresh);
   window.scaleWorkspace=mountTopologyWorkspace(fresh,{runEngine:async job=>{
     const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(job.sourceText));
     const sha=Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');
     const shortElements=Array.from({length:130},(_,i)=>({
       id:'SHORT:'+i,sourceSha256:sha,eligible:true,componentType:'GASK',
       componentRefNo:'GASK-TEST-'+i,lengthMm:3,measuredSpanMm:3,
       lengthBasis:'SOURCE_STRAIGHT_TWO_PORT_SPAN',recordCount:2,weightRemoved:0,
       nodeKeys:['B0:N'+i+':S1','B0:N'+i+':S2'],reason:''
     }));
     return {ok:true,outputKind:'topology-sidecars',ciiText:null,
       acceptedFinalTransferred:false,nativeCiiReleaseAuthorized:false,
       topoFixCommitted:false,topoFixXmlText:null,
       topologyFixPlanText:JSON.stringify({source:{sha256:sha},actions:[]}),
       topologyFindingsText:JSON.stringify({source:{sha256:sha},findings:[],shortElements})};
   }});
 });
 await scalePage.locator('[data-file]').setInputFiles({name:'scale-short.xml',mimeType:'application/xml',buffer:Buffer.from(shortFixture)});
 await scalePage.waitForFunction(()=>!document.querySelector('[data-analyze]').disabled);
 await scalePage.locator('[data-analyze]').click();
 await scalePage.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'));
 await scalePage.locator('[data-preview-short]').click();
 if(await scalePage.locator('[data-short-index]').count()!==24||
    !(await scalePage.locator('[data-short-preview]').textContent()).includes('130 measured candidates'))
   throw Error('Scale preview must render only one page of 24 out of 130');
 await scalePage.locator('[data-select-gaskets]').click();
 if(!(await scalePage.locator('[data-run-short-drop]').textContent()).includes('Apply all 130 selected'))
   throw Error('Selection must expose the bounded eight-owner batch size');
 await scalePage.locator('[data-short-next]').click();
 if(await scalePage.locator('[data-short-index]:checked').count()!==24||
    !(await scalePage.locator('[data-short-selection-count]').textContent()).includes('130 selected'))
   throw Error('Selection was lost across short-preview pages');
 if((await scalePage.locator('[data-progress]').textContent()).includes('APPLIED'))
   throw Error('A preview or selection mutated working XML');
 result.shortPreviewScale='PASS: 130 rows, 24/page, selection across pages, full-selection bulk intent, no mutation';
 await scalePage.close();
 // Manual Fix is a collapsed rule/case queue. >25 mm repairs require a separate preview and approval.
 const manualNode=(number,kind,ref,end,x,extra='')=>'<Node><NodeNumber>'+number+'</NodeNumber><ComponentType>'+kind+'</ComponentType><ComponentRefNo>'+ref+'</ComponentRefNo><Endpoint>'+end+'</Endpoint><Position>'+x+' 0 0</Position><OutsideDiameter>100</OutsideDiameter>'+extra+'</Node>';
 const manualDoc=(a,b)=>'<PipeStressExport><Branch><Branchname>SOURCE</Branchname>'+a+'</Branch><Branch><Branchname>PARTNER</Branchname>'+b+'</Branch></PipeStressExport>';
 const manualPipeFlange=manualDoc(manualNode(10,'PIPE','P',1,0)+manualNode(20,'PIPE','P',2,100),manualNode(30,'FLAN','F',1,175)+manualNode(-1,'RIGID','F',2,261));
 const manualGasket=manualDoc(manualNode(20,'GASK','G',1,100)+manualNode(-1,'RIGID','G',2,103),manualNode(10,'PIPE','P',1,-100)+manualNode(40,'PIPE','P',2,25));
 async function openManualPair(xml,peer){
  await page.locator('[data-file]').setInputFiles({name:'manual-second-pass.xml',mimeType:'application/xml',buffer:Buffer.from(xml)});
  await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('4 of 4'));
  await page.locator('[data-analyze]').click();
  await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
  await page.locator('[data-audit-category]').selectOption('all');
  await page.locator('[data-audit-filter="manual"]').click();
  if(await page.locator('.audit-rule[open]').count())throw Error('Manual rules should initially be collapsed');
  await page.locator('[data-rules-expand]').click();
  const summary=page.locator('.audit-case > summary').filter({hasText:'Node 20 · SOURCE'}).first();
  await summary.click();
  await summary.locator('..').locator('[data-add-second-pass]').click();
  await page.locator('[data-second-peer]').selectOption(peer);
 }
 result.manualSecondPass=[];
 for(const [kind,xml,peer,movedKey,expectedPositions] of [
  ['PIPE_FLANGE',manualPipeFlange,'B1:N30:S0','B0:N20:S1',[0,175,175,261]],
  ['GASK_PIPE',manualGasket,'B1:N40:S1','B1:N40:S1',[100,103,-100,100]]]){
  await openManualPair(xml,peer);
  if(kind==='GASK_PIPE'){
   await page.locator('[data-second-peer]').selectOption('');
   await page.locator('[data-occ-id$=":B1:N40:S1"]').click();
   await page.locator('[data-second-use-selection]').click();
   if(await page.locator('[data-second-peer]').inputValue()!==peer)throw Error('Exact canvas/occurrence partner selection failed');
  }
  const beforeCount=await page.locator('[data-audit-filter="manual"]').textContent();
  await page.locator('[data-preview-second]').click();
  await page.waitForFunction(()=>/PREVIEW ONLY|Cannot close|Preview unavailable/.test(document.querySelector('[data-second-status]')?.textContent||''),null,{timeout:120000});
  const preview=await page.locator('[data-second-pass]').textContent();
  if(!preview.includes('75.000 mm closure')||!preview.includes('Move '+movedKey))throw Error('Manual preview lacks exact distance or PIPE movement priority: '+preview);
  if(!await page.locator('[data-download-working]').isDisabled()||!await page.locator('[data-apply-second]').isDisabled())throw Error('Preview must not apply XML or allow unconfirmed movement');
  if(await page.locator('[data-audit-filter="manual"]').textContent()!==beforeCount)throw Error('Preview changed findings');
  const previewBounds=await page.locator('[data-second-pass]').boundingBox();
  const sideBounds=await page.locator('.topo-side').first().boundingBox();
  if(previewBounds.y<sideBounds.y-2||previewBounds.y>sideBounds.y+55)throw Error('Second-pass preview scrolled out of the findings viewport');
  await page.screenshot({path:path.join(sourceRoot,'preview-test-results','manual-'+kind.toLowerCase()+'-preview.png'),fullPage:false});
  await page.locator('[data-second-evidence]').fill('DRAWING-SYNTHETIC-02 explicitly confirms this connection');
  await page.locator('[data-second-confirm]').check();
  await page.locator('[data-apply-second]').click();
  await page.waitForFunction(()=>['ready','rejected'].includes(document.querySelector('[data-fix-result]')?.getAttribute('data-result')),null,{timeout:120000});
  const progress=await page.locator('[data-progress]').textContent();
  if(!progress.includes('APPLIED · revision 1')||!progress.includes('after full recheck'))throw Error('Second pass not applied and rechecked: '+progress+' '+await page.locator('[data-fix-result]').textContent());
  if(await page.locator('[data-audit-filter="manual"]').textContent()===beforeCount)throw Error('Manual count not refreshed after closure');
  if(!await page.locator('[data-second-pass]').isHidden())throw Error('Applied source preview should be invalidated');
  const xmlDownload=page.waitForEvent('download');await page.locator('[data-download-working]').click();
  const fixed=await readFile(await (await xmlDownload).path(),'utf8');
  const positions=await page.evaluate(xml=>[...new DOMParser().parseFromString(xml,'application/xml').getElementsByTagNameNS('*','Position')].map(n=>Number(n.textContent.split(/\s+/)[0])),fixed);
  if(JSON.stringify(positions)!==JSON.stringify(expectedPositions))throw Error('Manual corrected XML geometry drift: '+JSON.stringify(positions));
  const receiptDownload=page.waitForEvent('download');await page.locator('[data-download-batch-report]').click();
  const receipt=JSON.parse(await readFile(await (await receiptDownload).path(),'utf8'));
  if(receipt.connectionApproval.approvedRepair.distanceMm!==75||receipt.transaction.policy.joint_repairs[0].confirmed!==true||receipt.validation.checks.some(c=>c.blocking&&!c.passed))throw Error('Manual approval/validation receipt missing');
  if(createHash('sha256').update(fixed).digest('hex')!==receipt.fixedXmlSha256)throw Error('Second-pass downloaded XML hash mismatch');
  await writeFile(path.join(sourceRoot,'preview-test-results','manual-'+kind.toLowerCase()+'.xml'),fixed);
  await writeFile(path.join(sourceRoot,'preview-test-results','manual-'+kind.toLowerCase()+'-receipt.json'),JSON.stringify(receipt,null,2));
  result.manualSecondPass.push({kind,distanceMm:75,preview:'NO_MUTATION',beforeCount,afterCount:await page.locator('[data-audit-filter="manual"]').textContent(),positions,progress,downloadSha256:receipt.fixedXmlSha256});
 }
 // Prototype UX checks: navigation state, stale approval and cancellation use real controls.
 result.manualPrototypeUsability={};
 await openManualPair(manualPipeFlange,'B1:N30:S0');
 await page.locator('[data-preview-second]').click();
 await page.waitForFunction(()=>document.querySelector('[data-second-status]')?.textContent?.includes('PREVIEW ONLY'),null,{timeout:120000});
 if(await page.locator('.audit-rule[open]').count()!==1||await page.locator('.audit-case[open]').count()!==1)throw Error('Preview redraw lost manual rule/case navigation');
 result.manualPrototypeUsability.ruleAndCaseExpansionRetained=true;
 await page.locator('[data-second-evidence]').fill('SYNTHETIC-DRAWING-03 confirms the displayed connection');
 await page.locator('[data-second-confirm]').check();
 if(await page.locator('[data-apply-second]').isDisabled())throw Error('Confirmed valid preview did not enable Apply');
 await page.locator('[data-second-peer]').selectOption('');
 if(await page.locator('[data-apply-second]').count()||await page.locator('.second-pass-preview').count())throw Error('Edited partner retained obsolete approval');
 result.manualPrototypeUsability.partnerEditInvalidatesApproval=true;
 if(!await page.locator('[data-download-working]').isDisabled())throw Error('Partner editing emitted working XML');
 await page.locator('[data-cancel-second]').click();
 if(!await page.locator('[data-second-pass]').isHidden()||!await page.locator('[data-download-working]').isDisabled())throw Error('Cancel changed working copy');
 result.manualPrototypeUsability.cancelLeavesOriginal=true;
 await page.locator('[data-search]').fill('B0:N20:S1');
 if(!(await page.locator('[data-audit-filter="manual"]').textContent()).includes('(1)'))throw Error('Manual rule search count did not narrow to source case');
 await page.locator('[data-search]').fill('');
 if(!(await page.locator('[data-audit-filter="manual"]').textContent()).includes('(3)'))throw Error('Clearing search lost original manual count');
 result.manualPrototypeUsability.ruleSearchCountsRefresh=true;
 await page.screenshot({path:path.join(sourceRoot,'preview-test-results','manual-by-rule-prototype.png'),fullPage:false});
 await openManualPair(manualPipeFlange,'B1:N30:S0');
 await page.locator('[data-preview-second]').click();
 await page.waitForFunction(()=>document.querySelector('[data-second-status]')?.textContent?.includes('PREVIEW ONLY'),null,{timeout:120000});
 await page.locator('[data-second-evidence]').fill('SYNTHETIC-DRAWING-04 confirms the current source only');
 await page.locator('[data-second-confirm]').check();
 await page.locator('[data-file]').setInputFiles({name:'replacement-source.xml',mimeType:'application/xml',buffer:Buffer.from(manualGasket)});
 await page.waitForFunction(()=>document.querySelector('[data-source-meta]')?.textContent?.includes('replacement-source.xml'));
 if(!await page.locator('[data-second-pass]').isHidden()||await page.locator('[data-apply-second]').count()||!await page.locator('[data-download-working]').isDisabled())throw Error('Loading replacement source retained old approved repair');
 if(!(await page.locator('[data-progress]').textContent()).includes('revision 0'))throw Error('Replacement source reused old repair revision');
 result.manualPrototypeUsability.replacementSourceInvalidatesApproval=true;
 // Unknown diameter cannot be overridden by the new manual control.
 await openManualPair(manualPipeFlange.replaceAll('<OutsideDiameter>100</OutsideDiameter>',''),'B1:N30:S0');
 await page.locator('[data-preview-second]').click();
 await page.waitForFunction(()=>document.querySelector('[data-second-status]')?.textContent?.includes('Cannot close'),null,{timeout:120000});
 if(await page.locator('[data-apply-second]').count()||!await page.locator('[data-download-working]').isDisabled())throw Error('Incompatible manual pair exposed Apply/output');
 result.manualSecondPassNegative='UNKNOWN_DIAMETER_REJECTED';

 // A queued Second Pass must keep XML untouched until explicit queue Apply.
 // The real PSI116 transaction and full pre-Final replay run in the Worker.
 await openManualPair(manualPipeFlange,'B1:N30:S0');
 await page.locator('[data-preview-second]').click();
 await page.waitForFunction(()=>document.querySelector('[data-second-status]')?.textContent?.includes('PREVIEW ONLY'),null,{timeout:120000});
 await page.locator('[data-second-evidence]').fill('DRAWING-SYNTHETIC-Q1 explicitly approves exact paired ports');
 await page.locator('[data-second-confirm]').check();
 if(await page.locator('[data-queue-second]').isDisabled())throw Error('Qualified confirmed port pair cannot enter queue');
 await page.locator('[data-queue-second]').click();
 if(!(await page.locator('[data-manual-queue]').textContent()).includes('1 approved')||
    !(await page.locator('[data-occ-summary]').textContent()).includes('4 of 4')||
    !(await page.locator('[data-download-working]').isDisabled()))
   throw Error('Queue admission did not preserve the unchanged original working XML: queue='+await page.locator('[data-manual-queue]').textContent()+'; occurrences='+await page.locator('[data-occ-summary]').textContent());
 await page.locator('[data-queue-apply]').click();
 await page.waitForFunction(()=>document.querySelector('main')?.getAttribute('aria-busy')==='false'&&
    /QUEUE COMPLETE|QUEUE STOPPED/.test(document.querySelector('[data-queue-status]')?.textContent||''),null,{timeout:120000});
 const queueSummary=await page.locator('[data-queue-status]').textContent();
 if(!queueSummary.includes('QUEUE COMPLETE')||
    !queueSummary.includes('1 selected = 1 applied + 0 blocked + 0 re-review required')||
    !(await page.locator('[data-download-working]').isEnabled()))
   throw Error('Qualified queue did not publish one validated working revision: '+queueSummary);
 result.manualQueueRealBrowser='PASS: 1 explicitly approved pair, source-bound re-preview, atomic transaction, full replay and final UI publication';
 // TOPO-A P1: synthetic hidden CLOS pair must be findable independently of findings.
 const reviewNode=(n,kind,ref,end,x,clos='')=>
  '<Node><NodeNumber>'+n+'</NodeNumber><ComponentType>'+kind+'</ComponentType>'+
  '<ComponentRefNo>'+ref+'</ComponentRefNo><Endpoint>'+end+'</Endpoint>'+
  '<Position>'+x+' 0 0</Position><OutsideDiameter>114.3</OutsideDiameter>'+
  '<WallThickness>6.02</WallThickness>'+clos+'</Node>';
 const clos='<ConnectionType>CLOS</ConnectionType>';
 const reviewFixture='<PipeStressExport><Branch><Branchname>REVIEW-CLOSED</Branchname>'+
  reviewNode(120,'FLAN','V',1,1000)+reviewNode(6880,'RIGID','V',2,1100,clos)+
  '</Branch><Branch><Branchname>REVIEW-OPEN</Branchname>'+
  reviewNode(6450,'FBLI','BL',1,1340.6)+reviewNode(-1,'FBLI','BL',2,1372.8)+
  '</Branch></PipeStressExport>';
 await page.locator('[data-file]').setInputFiles({name:'review-6880-6450.xml',mimeType:'application/xml',
   buffer:Buffer.from(reviewFixture)});
 await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('4 of 4'));
 await page.locator('[data-analyze]').click();
 await page.waitForFunction(()=>document.querySelector('[data-status]')?.textContent?.includes('Authoritative topology analysis complete.'),null,{timeout:120000});
 // A review overlay must not replace the user's previously selected source record.
 await page.locator('[data-occ-id]').first().click();
 const priorInspector=await page.locator('[data-inspector]').textContent();
 const selectionPreserved=async()=>
   (await page.locator('[data-inspector]').textContent())===priorInspector&&
   (await page.locator('[data-occ-id][aria-selected="true"]').count())===1;
 await page.locator('[data-review-query="a"]').fill('6880');
 await page.locator('[data-review-query="b"]').fill('6450');
 if(!await selectionPreserved())throw Error('Review pair replaced shared selection');
 await page.locator('[data-review-query="a"]').fill('');
 if(!await selectionPreserved())throw Error('Clearing review lost previous selection');
 await page.locator('[data-review-query="a"]').fill('6880');
 if(!await selectionPreserved())throw Error('Reopening review lost previous selection');
 result.topoASelection='PASS: shared selection and inspector unchanged by review and clear';
 const rPanel=page.locator('[data-connection-review]');
 const rText=await rPanel.textContent();
 if(!rText.includes('CONFLICTS_WITH_CLOS')||!rText.includes('240.600')||
   !rText.includes('B0:N6880:S1')||!rText.includes('114.300')||
   !rText.includes('upstream CAD')||!rText.includes('reimport')||
   await rPanel.locator('[data-queue-apply],[data-queue-second],[data-apply-second],[data-apply]').count()||
   await page.locator('[data-download-working]').isEnabled())
   throw Error('TOPO-A P1 violated hidden CLOS review-only acceptance: '+rText);
 await mkdir(path.join(sourceRoot,'preview-test-results'),{recursive:true});
 await page.screenshot({path:path.join(sourceRoot,'preview-test-results','topo-a-p1-review-synthetic.png'),fullPage:true});
 result.topoAReview='SYNTHETIC: 6880/6450 240.600 mm, CLOS source witness, no Apply/Queue/XML mutation';

 // P2: Source Review is a separate evidence-only shelf, never the executable queue.
 const sourceQueue=page.locator('[data-source-review-queue]');
 const beforeSourceMeta=await page.locator('[data-source-meta]').textContent();
 const beforeFindings=await page.locator('[data-plan-summary]').textContent();
 const manualShelf=page.locator('[data-manual-queue]');
 if(!await manualShelf.count()||!await manualShelf.getByText('No approved repairs queued.').count())
   throw Error('P2 baseline manual queue is not empty');
 await rPanel.locator('[data-source-review-add]').click();
 if(await sourceQueue.locator('[data-source-review-row]').count()!==1||
    !(await sourceQueue.textContent()).includes('CONFLICTS_WITH_CLOS')||
    !(await sourceQueue.textContent()).includes('240.600')||
    !(await sourceQueue.textContent()).includes('B0:N6880:S1'))
   throw Error('P2 exact CLOS review row missing');
 await sourceQueue.locator('[data-source-review-decision]').selectOption('UPSTREAM_SOURCE_CORRECTION_REQUIRED');
 await sourceQueue.locator('[data-source-review-note]').fill('Drawing P2-SYNTH: correct in upstream CAD/design source; never join closed connections');
 await sourceQueue.locator('[data-source-review-save]').click();
 if(!(await sourceQueue.textContent()).includes('upstream source correction required')||
    !(await sourceQueue.textContent()).includes('Correct in the upstream CAD/design source, then reimport.'))
   throw Error('P2 engineer decision or upstream instructions not preserved');
 // Reverse the pair: same unordered source identities must update one row, not add another.
 await page.locator('[data-review-query="a"]').fill('6450');
 await page.locator('[data-review-query="b"]').fill('6880');
 await rPanel.locator('[data-source-review-add]').click();
 if(await sourceQueue.locator('[data-source-review-row]').count()!==1)
   throw Error('P2 reversed pair was duplicated');
 await sourceQueue.locator('[data-source-review-decision]').selectOption('UPSTREAM_SOURCE_CORRECTION_REQUIRED');
 await sourceQueue.locator('[data-source-review-note]').fill('Drawing P2-SYNTH: source correction required');
 await sourceQueue.locator('[data-source-review-save]').click();
 const downloadedReview=page.waitForEvent('download');
 await sourceQueue.locator('[data-source-review-export-json]').click();
 const reviewExport=JSON.parse(await readFile(await (await downloadedReview).path(),'utf8'));
 if(reviewExport.schema!=='topofix-source-review-queue/v1'||reviewExport.rows.length!==1||
    reviewExport.rows[0].disposition!=='CONFLICTS_WITH_CLOS'||
    reviewExport.rows[0].decision!=='UPSTREAM_SOURCE_CORRECTION_REQUIRED'||
    reviewExport.rows[0].distanceMm.toFixed(3)!=='240.600'||
    reviewExport.rows[0].ports.map(p=>p.sourceKey).join('|')!=='B0:N6880:S1|B1:N6450:S0')
   throw Error('P2 JSON evidence lost exact identity, closure or decision');
 const downloadedCSV=page.waitForEvent('download');
 await sourceQueue.locator('[data-source-review-export-csv]').click();
 const reviewCSV=await readFile(await (await downloadedCSV).path(),'utf8');
 if(!reviewCSV.includes('UPSTREAM_SOURCE_CORRECTION_REQUIRED')||
    !reviewCSV.includes('B0:N6880:S1')||!reviewCSV.includes('240.600'))
   throw Error('P2 CSV evidence not source qualified');
 if((await page.locator('[data-source-meta]').textContent())!==beforeSourceMeta||
    (await page.locator('[data-plan-summary]').textContent())!==beforeFindings||
    await page.locator('[data-download-working]').isEnabled()||
    !(await manualShelf.getByText('No approved repairs queued.').count())||
    await page.locator('[data-queue-apply]').isEnabled()||
    await sourceQueue.locator('[data-queue-apply],[data-queue-second],[data-apply-second],[data-close-joint],[data-run-auto-fix-all]').count()||
    await rPanel.locator('[data-queue-apply],[data-queue-second],[data-apply-second],[data-close-joint]').count())
   throw Error('P2 source review leaked into executable repair or modified XML/findings');
 result.topoAP2Isolation='PASS: 1 exact review pair, reversed duplicate update, decision, JSON/CSV, 0 executable queue and 0 XML/finding mutations';
 await mkdir(path.join(sourceRoot,'preview-test-results'),{recursive:true});
 // Capture the actual review queue (inside the independently scrollable findings aside),
 // not a full-page image that can omit the queue below the aside's scroll fold.
 await sourceQueue.screenshot({path:path.join(sourceRoot,'preview-test-results','topo-a-p2-source-review-synthetic.png')});

 // A nearby duplicate must not be chosen silently even when it looks closer.
 const duplicateBranch='<Branch><Branchname>REVIEW-DUPLICATE</Branchname>'+
  reviewNode(6880,'PIPE','ALT',1,1340.59)+reviewNode(9000,'PIPE','ALT',2,1440.59)+'</Branch>';
 const duplicateFixture=reviewFixture.replace('</PipeStressExport>',duplicateBranch+'</PipeStressExport>');
 await page.locator('[data-file]').setInputFiles({name:'review-duplicate.xml',mimeType:'application/xml',
   buffer:Buffer.from(duplicateFixture)});
 await page.waitForFunction(()=>document.querySelector('[data-occ-summary]')?.textContent?.includes('6 of 6'));
 if(!(await sourceQueue.textContent()).includes('STALE_SOURCE'))throw Error('P2 old source decision not marked STALE_SOURCE');
 const importFixture=JSON.stringify(reviewExport);
 await sourceQueue.locator('[data-source-review-import]').setInputFiles({name:'review-evidence.json',mimeType:'application/json',buffer:Buffer.from(importFixture)});
 await page.waitForFunction(()=>document.querySelector('[data-source-review-status]')?.textContent?.includes('Import:'));
 if(await sourceQueue.locator('[data-source-review-row]').count()!==1||
    !(await sourceQueue.textContent()).includes('STALE_SOURCE'))
   throw Error('P2 stale imported row was lost or re-bound');
 result.topoAP2Stale='PASS: source replacement and imported mismatched SHA remain STALE_SOURCE';
 await page.locator('[data-review-query="a"]').fill('6880');
 await page.locator('[data-review-query="b"]').fill('6450');
 if(!(await rPanel.textContent()).includes('AMBIGUOUS_PORT')||
   await rPanel.locator('[data-review-choice="a"]').count()!==1)
   throw Error('Duplicate NodeNumber auto-chosen instead of exact source disambiguation');
 await rPanel.locator('[data-review-choice="a"]').selectOption('B0:N6880:S1');
 if(!(await rPanel.textContent()).includes('240.600'))throw Error('Exact branch choice not respected');
 result.topoADuplicate='SYNTHETIC: duplicate 6880 required explicit B0 source-key selection';

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
