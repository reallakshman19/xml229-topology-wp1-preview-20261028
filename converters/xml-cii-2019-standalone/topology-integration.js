const TOPOLOGY_PACKAGE_FILES = Object.freeze([
  '__init__.py',
  'models.py',
  'parser.py',
  'analysis.py',
  'geometry_analysis.py',
  'connectivity_audit.py',
  'planner.py',
  'removal_policy.py',
  'resolver.py',
  'transaction.py',
  'joint_repair.py',
  'manual_connections.py',
  'connection_ports.py',
  'short_elements.py',
  'lineage.py',
  'uxml_adapter.py',
  'uxml_compare.py',
  'uxml_edit_ops.py',
]);

const TOPOLOGY_SNIPPET = `
from pathlib import Path
import json
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.lineage import build_topofix_source_lineage, verify_topofix_pre_final

cfg = ResolverConfig()
result = resolve_psi116(Path(job_topology_input_path))
hub_doc = json.loads(job_topology_uxml_json)
hub_parity = {"status": "OFF", "differences": []}
if hub_doc is not None:
    # The same Python resolver consumes either ORIGINAL PSI116 or XCU's UXML.
    from psi116_topology_resolver.uxml_adapter import resolve_from_uxml
    from psi116_topology_resolver.uxml_compare import _diff
    try:
        adapted = resolve_from_uxml(hub_doc, cfg, source_name=str(job_topology_input_path))
        differences = []
        _diff("/findings", result.findings_payload(cfg), adapted.findings_payload(cfg), differences)
        _diff("/fixPlan", result.fix_plan_payload(cfg), adapted.fix_plan_payload(cfg), differences)
        hub_parity = {"status": "DIFFERENT" if differences else "EQUAL",
                      "differences": differences}
    except Exception as exc:
        hub_parity = {"status": "DIFFERENT",
                      "differences": ["/uxmlReader: "+type(exc).__name__+": "+str(exc)]}
findings_payload = result.findings_payload(cfg)
preview_request = json.loads(job_connection_preview_json)
if preview_request:
    from psi116_topology_resolver.manual_connections import preview_connection
    findings_payload["manualConnectionPreview"] = preview_connection(result, preview_request, cfg)
Path(job_topology_findings_path).write_text(
    json.dumps(findings_payload, indent=2, sort_keys=True) + "\\n",
    encoding="utf-8",
)
Path(job_topology_plan_path).write_text(
    json.dumps(result.fix_plan_payload(cfg), indent=2, sort_keys=True) + "\\n",
    encoding="utf-8",
)

status = {
    "requested": True,
    "generated": bool(job_generate_topofix),
    "committed": False,
    "rejectReasons": [],
    "fixedPath": "",
    "lineagePath": "",
    "handoffPath": "",
}

if job_generate_topofix:
    direct_transaction = apply_topofix_transaction(
        result,
        policy=TransactionPolicy(selected_action_ids=tuple(job_topology_action_ids),
                                 short_element_requests=tuple(json.loads(job_short_elements_json)),
                                 joint_repairs=tuple(json.loads(job_joint_repairs_json))),
        config=cfg,
    )
    transaction = direct_transaction
    if hub_doc is not None and hub_parity["status"] == "EQUAL":
        # This is the complete S2 Auto-only patch route: UXML -> edit ops ->
        # sourceRefs -> ORIGINAL PSI116 patched by native transaction.py.
        # Direct transaction is a private comparator, never the hub download.
        from psi116_topology_resolver.uxml_edit_ops import export_edit_ops, apply_edit_ops
        from psi116_topology_resolver.uxml_compare import _diff
        try:
            if json.loads(job_joint_repairs_json) or json.loads(job_short_elements_json):
                raise ValueError("UXML_PREVIEW_AUTO_ONLY: manual and short-element repair held")
            selection = TransactionPolicy(selected_action_ids=tuple(job_topology_action_ids))
            ops = export_edit_ops(hub_doc, policy=selection, source_name=str(job_topology_input_path))
            if sorted(op["sourceActionId"] for op in ops["ops"]) != sorted(job_topology_action_ids):
                raise ValueError("UXML_SELECTED_ACTION_IDS_NOT_ALL_MUTATING")
            patched = apply_edit_ops(Path(job_topology_input_path), hub_doc, ops, config=cfg)
            if patched is None:
                raise ValueError("UXML_PATCH_NO_OPERATIONS")
            differences = []
            _diff("/transaction", direct_transaction.transaction_payload(),
                  patched.transaction_payload(), differences)
            _diff("/validation", direct_transaction.validation_payload(),
                  patched.validation_payload(), differences)
            if patched.fixed_xml != direct_transaction.fixed_xml:
                differences.append("/fixedXml: PATCH_BYTES_DIFFER_FROM_DIRECT")
            if differences:
                hub_parity = {"status": "DIFFERENT", "differences": differences}
            else:
                transaction = patched
        except Exception as exc:
            hub_parity = {"status": "DIFFERENT",
                          "differences": ["/patchBack: "+type(exc).__name__+": "+str(exc)]}
    Path(job_topology_transaction_path).write_text(
        json.dumps(transaction.transaction_payload(), indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    Path(job_topology_validation_path).write_text(
        json.dumps(transaction.validation_payload(), indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    status["committed"] = bool(transaction.committed) and (
        hub_doc is None or hub_parity["status"] == "EQUAL")
    status["rejectReasons"] = list(transaction.reject_reasons)
    if hub_doc is not None and hub_parity["status"] != "EQUAL":
        status["rejectReasons"].append("UXML_PARITY_DIFFERENT_NO_DOWNLOAD")
    if status["committed"] and transaction.fixed_xml is not None:
        lineage = build_topofix_source_lineage(transaction)
        qualified = verify_topofix_pre_final(
            result.document.source_text, transaction.fixed_xml,
            transaction.transaction_payload(), transaction.validation_payload(),
            lineage, reviewed_action_ids=tuple(job_topology_action_ids),
        )
        assert qualified["requiresFreshWorkerBasis"] and not qualified["nativeCiiReleaseAuthorized"]
        Path(job_topology_fixed_path).write_text(transaction.fixed_xml, encoding="utf-8")
        Path(job_topology_lineage_path).write_text(
            json.dumps(lineage, indent=2, sort_keys=True) + "\\n", encoding="utf-8",
        )
        status["fixedPath"] = job_topology_fixed_path
        Path(job_topology_handoff_path).write_text(
            json.dumps(qualified, indent=2, sort_keys=True) + "\\n", encoding="utf-8",
        )
        status["lineagePath"] = job_topology_lineage_path
        status["handoffPath"] = job_topology_handoff_path
        # This is the authoritative reanalysis already performed by the atomic
        # transaction. Return it for a headless multi-owner UI batch so the UI
        # need not re-run Python or repaint between each validated owner.
        after = transaction.after_result
        assert after is not None and after.document.source_sha256 == lineage["fixedXmlSha256"]
        Path(job_topology_post_findings_path).write_text(
            json.dumps(after.findings_payload(cfg), indent=2, sort_keys=True) + "\\n", encoding="utf-8"
        )
        Path(job_topology_post_plan_path).write_text(
            json.dumps(after.fix_plan_payload(cfg), indent=2, sort_keys=True) + "\\n", encoding="utf-8"
        )

status["hubParity"] = hub_parity
Path(job_topology_status_path).write_text(
    json.dumps(status, indent=2, sort_keys=True) + "\\n",
    encoding="utf-8",
)
`;

let topologyPackageLoaded = false;

function text(value) {
  return value === undefined || value === null ? '' : String(value);
}

function safeStem(sourceName) {
  const safe = (text(sourceName).trim() || 'input.xml').replace(/[\\/:*?"|]/g, '_');
  const index = safe.lastIndexOf('.');
  return index > 0 ? safe.slice(0, index) : safe;
}

function readOptional(pyodide, path) {
  try {
    return pyodide.FS.readFile(path, { encoding: 'utf8' });
  } catch {
    return '';
  }
}

export function topologyRequested(job = {}) {
  const options = job.options || {};
  return options.analyzeTopology === true
    || options.generateTopoFix === true
    || options.useTopoFixForCii === true;
}

export async function ensurePsi116TopologyPackage(pyodide) {
  if (topologyPackageLoaded) return;
  pyodide.FS.mkdirTree('/scripts/psi116_topology_resolver');
  for (const fileName of TOPOLOGY_PACKAGE_FILES) {
    const url = new URL(`../psi116_topology_resolver/${fileName}`, import.meta.url);
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load PSI116 topology module ${fileName}: HTTP ${response.status}`);
    const fileText = await response.text();
    if (!fileText.trim()) throw new Error(`PSI116 topology module ${fileName} loaded as empty text.`);
    pyodide.FS.writeFile(`/scripts/psi116_topology_resolver/${fileName}`, fileText, { encoding: 'utf8' });
  }
  pyodide.runPython('import sys\nif "/scripts" not in sys.path:\n    sys.path.insert(0, "/scripts")');
  topologyPackageLoaded = true;
}

export async function runPsi116TopologyStage(pyodide, job, inputPath, jobDir, stdout = []) {
  if (!topologyRequested(job)) {
    return {
      ciiInputPath: inputPath,
      topologyFindingsText: '',
      topologyFindingsName: '',
      topologyFixPlanText: '',
      topologyFixPlanName: '',
      topoFixXmlText: '',
      topoFixXmlName: '',
      topoFixTransactionText: '',
      topoFixTransactionName: '',
      topoFixValidationText: '',
      topoFixValidationName: '',
      topoFixLineageText: '',
      topoFixLineageName: '',
      topoFixPreFinalHandoffText: '',
      topoFixPreFinalHandoffName: '',
      topoFixCommitted: false,
      ciiInputSource: 'original',
      topologySummary: null,
    };
  }

  if (job.sourceKind !== 'xml') {
    throw new Error('PSI116 topology analysis is available only for XML source mode.');
  }

  await ensurePsi116TopologyPackage(pyodide);
  const options = job.options || {};
  const generateTopoFix = options.generateTopoFix === true;
  const useTopoFixForCii = options.useTopoFixForCii === true;
  const actionIds = Array.isArray(options.topologyActionIds)
    ? options.topologyActionIds.map((value) => text(value).trim()).filter(Boolean)
    : [];

  if (generateTopoFix && !actionIds.length) {
    throw new Error('Generating TopoFix XML requires one or more reviewed topology action IDs.');
  }
  if (useTopoFixForCii && !generateTopoFix) {
    throw new Error('Using TopoFix for CII requires Generate TopoFix XML to be enabled.');
  }

  const stem = safeStem(job.sourceName);
  const names = {
    findings: `${stem}.topology-findings.json`,
    plan: `${stem}.topology-fix-plan.json`,
    transaction: `${stem}.topofix-transaction.json`,
    validation: `${stem}.topofix-validation.json`,
    fixed: `${stem}.topofix.xml`,
    lineage: `${stem}.topofix-lineage.json`,
    postFindings: `${stem}.topofix-post-findings.json`,
    postPlan: `${stem}.topofix-post-plan.json`,
    handoff: `${stem}.topofix-prefinal-handoff.json`,
    status: `${stem}.topofix-status.json`,
  };
  const paths = Object.fromEntries(Object.entries(names).map(([key, name]) => [key, `${jobDir}/${name}`]));

  pyodide.globals.set('job_topology_input_path', inputPath);
  pyodide.globals.set('job_topology_findings_path', paths.findings);
  pyodide.globals.set('job_topology_plan_path', paths.plan);
  pyodide.globals.set('job_topology_transaction_path', paths.transaction);
  pyodide.globals.set('job_topology_validation_path', paths.validation);
  pyodide.globals.set('job_topology_fixed_path', paths.fixed);
  pyodide.globals.set('job_topology_lineage_path', paths.lineage);
  pyodide.globals.set('job_topology_post_findings_path', paths.postFindings);
  pyodide.globals.set('job_topology_post_plan_path', paths.postPlan);
  pyodide.globals.set('job_topology_handoff_path', paths.handoff);
  pyodide.globals.set('job_topology_status_path', paths.status);
  pyodide.globals.set('job_generate_topofix', generateTopoFix);
  pyodide.globals.set('job_topology_action_ids', actionIds);
  pyodide.globals.set('job_topology_uxml_json', JSON.stringify(job.uxmlDocument||null));
  pyodide.globals.set('job_joint_repairs_json', JSON.stringify(options.topologyJointRepairs || []));
  pyodide.globals.set('job_connection_preview_json', JSON.stringify(options.topologyConnectionPreview || null));
  pyodide.globals.set('job_short_elements_json', JSON.stringify(options.topologyShortElementRequests || []));
  await pyodide.runPythonAsync(TOPOLOGY_SNIPPET);

  const status = JSON.parse(readOptional(pyodide, paths.status) || '{}');
  const topologyUxmlParity = status.hubParity || null;
  const topologyFindingsText = readOptional(pyodide, paths.findings);
  const topologyFixPlanText = readOptional(pyodide, paths.plan);
  const topoFixTransactionText = generateTopoFix ? readOptional(pyodide, paths.transaction) : '';
  const topoFixValidationText = generateTopoFix ? readOptional(pyodide, paths.validation) : '';
  const topoFixCommitted = status.committed === true;
  const topoFixXmlText = topoFixCommitted ? readOptional(pyodide, paths.fixed) : '';
  const topoFixLineageText = topoFixCommitted ? readOptional(pyodide, paths.lineage) : '';
  const topoFixPreFinalHandoffText = topoFixCommitted ? readOptional(pyodide, paths.handoff) : '';
  const topoFixPostFindingsText = topoFixCommitted ? readOptional(pyodide, paths.postFindings) : '';
  const topoFixPostPlanText = topoFixCommitted ? readOptional(pyodide, paths.postPlan) : '';
  if(topoFixCommitted && (!topoFixLineageText || !topoFixPreFinalHandoffText ||
                          !topoFixPostFindingsText || !topoFixPostPlanText))
    throw new Error('TOPOFIX_PRE_FINAL_LINEAGE_RECEIPT_MISSING');

  const rejectReasons = Array.isArray(status.rejectReasons) ? status.rejectReasons.map((value) => text(value)) : [];
  if (useTopoFixForCii && !topoFixCommitted) {
    const reasonText = rejectReasons.length ? `: ${rejectReasons.join(', ')}` : '.';
    throw new Error(`Committed TopoFix XML is required before it can be used for CII conversion${reasonText}`);
  }

  stdout.push(`PSI116 topology analysis wrote ${names.findings} and ${names.plan}.`);
  if (generateTopoFix && topoFixCommitted) stdout.push(`Committed TopoFix XML: ${names.fixed}.`);
  if (generateTopoFix && !topoFixCommitted) stdout.push(`WARNING: TopoFix transaction rejected${rejectReasons.length ? `: ${rejectReasons.join(', ')}` : '.'}`);
  if (useTopoFixForCii) stdout.push('CII conversion input switched to committed TopoFix XML.');

  return {
    ciiInputPath: useTopoFixForCii ? paths.fixed : inputPath,
    topologyFindingsText,
    topologyFindingsName: names.findings,
    topologyFixPlanText,
    topologyFixPlanName: names.plan,
    topoFixXmlText,
    topoFixXmlName: topoFixCommitted ? names.fixed : '',
    topoFixTransactionText,
    topoFixTransactionName: generateTopoFix ? names.transaction : '',
    topoFixValidationText,
    topoFixValidationName: generateTopoFix ? names.validation : '',
    topoFixLineageText,
    topoFixLineageName: topoFixCommitted ? names.lineage : '',
    topoFixPreFinalHandoffText,
    topoFixPostFindingsText,
    topoFixPostPlanText,
    topoFixPreFinalHandoffName: topoFixCommitted ? names.handoff : '',
    topoFixCommitted,
    topologyUxmlParity,
    ciiInputSource: useTopoFixForCii ? 'topofix' : 'original',
    topologySummary: {
      requested: true,
      generateTopoFix,
      useTopoFixForCii,
      actionIds,
      committed: topoFixCommitted,
      rejectReasons,
    },
  };
}
