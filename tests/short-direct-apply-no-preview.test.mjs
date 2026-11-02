import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('no separate short UXML preview gate remains in active UI and Worker code',()=>{
  const paths=[
    'tabs/topology-workspace/workspace-app.mjs',
    'tabs/topology-workspace/trial-clarity.mjs',
    'tabs/topology-workspace/topology-worker.mjs',
    'tabs/topology-workspace/topology-worker-client.mjs',
    'converters/xml-cii-2019-standalone/topology-integration.js',
    'index.html','topology-workspace.html',
  ];
  for(const path of paths){
    const body=readFileSync(path,'utf8');
    assert.doesNotMatch(body,/shortHubPreview|shortHubProgress|previewToken|topologyShortPreviewRequests|data-short-hub-preview|job_short_preview/,
      path+' cannot retain the obsolete preview approval protocol');
    assert.doesNotMatch(body,/Preview selected UXML|Preview the selected UXML short-drop operations before Apply/,
      path+' cannot demand a second preview action');
  }
  const ui=readFileSync(paths[0],'utf8');
  assert.match(ui,/data-run-short-drop/);
  assert.match(ui,/shortSelection/);
  assert.match(ui,/runShortBulk\(/);
});
test('hub Apply keeps canonical export, re-derived Apply and independent native parity',()=>{
  const bridge=readFileSync('converters/xml-cii-2019-standalone/topology-integration.js','utf8');
  for(const authority of [
    'export_edit_ops(hub_doc, policy=selection',
    'apply_edit_ops(Path(job_topology_input_path), hub_doc, ops',
    'compare_hub_patch(direct_transaction, patched)',
    'status["appliedEditOps"]',
  ])assert.ok(bridge.includes(authority),authority+' must not be bypassed');
  const apply=readFileSync('converters/psi116_topology_resolver/uxml_edit_ops.py','utf8');
  assert.match(apply,/canonical = _short_canonical_operation\(/);
  assert.match(apply,/UXML_SHORT_TARGETS_OR_PARAMS_DIFFER_FROM_AUTHORITY/);
  assert.match(apply,/UXML_LOSS_CONTRACT_FIELD_TOUCH/);
  const bulk=readFileSync('tabs/topology-workspace/short-bulk.mjs','utf8');
  assert.match(bulk,/UXML_SHORT_APPLY_CANONICAL_OP_RECEIPT_MISSING_OR_DRIFT/);
  assert.match(bulk,/namedHubOwnerRefusal/);
});
