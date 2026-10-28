/** Standalone preview Chromium journey: exact public fixture, real Pyodide and rule audit. */
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
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
 const expected={all:210,error:0,warning:151,auto:76,manual:10,evidence:18};
 for(const [key,count] of Object.entries(expected))
  if(!result.filterCounts[key].includes('('+count+')'))
   throw Error('Filter count drift: '+key+' actual '+result.filterCounts[key]);
 if(!((await page.locator('[data-auto-fix-all]').textContent()).includes('(66 actions)')))
   throw Error('Distinct action count not shown for Autofix-All');
 await page.locator('[data-audit-filter="error"]').click();
 result.emptyError=await page.locator('[data-issues]').textContent();
 if(!result.emptyError.includes('No ERROR findings')||
    !result.emptyError.includes('not proof of complete network connectivity'))
   throw Error('ERROR tab missing clear empty state');
 await page.locator('[data-audit-filter="all"]').click();
 result.ruleGroups=await page.locator('.audit-rule').count();
 result.autofixCandidates=await page.locator('[data-auto-fix]').count();
 result.warningFound=await page.locator('.audit-severity.warning').count();
 result.gapCoverage=await page.locator('.audit-coverage').textContent();
 if(!result.gapCoverage.includes('ACTIVE')||!result.gapCoverage.includes('not a complete solver graph'))throw Error('Gap coverage must be bounded and honest');
 await page.locator('[data-audit-category]').selectOption('gaps');
 result.gapGroups=await page.locator('.audit-rule').count();
 result.gapItems=await page.locator('.audit-item').count();
 if(result.gapItems<1)throw Error('Reference file must show evidence-qualified open ends');
 if(await page.locator('[data-audit-category]').inputValue()!=='gaps')throw Error('Gap filter did not activate');
 if(await page.locator('.audit-item [data-auto-fix]').count())throw Error('Gap candidates must not receive auto-join control');
 const gapRule=page.locator('.audit-rule').first();
 if(!(await gapRule.evaluate(el=>el.open)))await gapRule.locator('summary').first().click();
 const review=page.locator('.audit-item').first();
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
 if(result.fixState==='ready' && !(await page.locator('[data-download-fix]').count()))throw Error('Missing validated XML download action');
 await page.locator('[data-auto-fix-all]').click();
 result.batchPreview=await page.locator('[data-batch-confirm]').textContent();
 if(!result.batchPreview.includes('66 eligible XML-changing actions')||
    !result.batchPreview.includes('conflict-free actions'))
   throw Error('Batch preview missing eligible and excluded count');
 const selected=Number(result.batchPreview.match(/(\\d+) conflict-free actions/)?.[1]);
 if(!Number.isInteger(selected)||selected<1||selected>66)
   throw Error('Invalid conflict-free action count');
 await page.locator('[data-run-auto-fix-all]').click();
 await page.waitForFunction(()=>['ready','rejected'].includes(
   document.querySelector('[data-fix-result]')?.getAttribute('data-result')),null,{timeout:180000});
 result.batchState=await page.locator('[data-fix-result]').getAttribute('data-result');
 result.batchMessage=await page.locator('[data-fix-result]').textContent();
 if(result.batchState!=='ready')
   throw Error('Autofix-All must produce a validated copy for reference fixture: '+result.batchMessage);
 const dl=page.waitForEvent('download');
 await page.locator('[data-download-fix]').click();
 const output=await dl;
 result.batchOutputName=output.suggestedFilename();
 if(!result.batchOutputName.includes('.batch-'+selected+'.validated.topofix.xml'))
   throw Error('Batch output lacks specific selected action count');
 const xml=await readFile(await output.path(),'utf8');
 if(!xml.includes('PipeStressExport'))throw Error('Batch fixed XML missing expected source root');
 result.originalOccurrences=await page.locator('[data-occ-summary]').textContent();
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
