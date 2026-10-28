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
 result.ruleGroups=await page.locator('.audit-rule').count();
 result.autofixCandidates=await page.locator('[data-auto-fix]').count();
 result.warningFound=await page.locator('.audit-severity.warning').count();
 result.gapCoverage=await page.locator('.audit-coverage').textContent();
 if(!result.gapCoverage.includes('NOT IMPLEMENTED'))throw Error('Missing explicit gap coverage status');
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
