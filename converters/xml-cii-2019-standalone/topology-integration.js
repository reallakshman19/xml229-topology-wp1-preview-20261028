const TOPOLOGY_PACKAGE_FILES = Object.freeze([
  '__init__.py',
  'models.py',
  'parser.py',
  'analysis.py',
  'geometry_analysis.py',
  'planner.py',
  'resolver.py',
  'transaction.py',
  'lineage.py',
]);

const TOPOLOGY_SNIPPET = `
from pathlib import Path
import json
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.lineage import build_topofix_source_lineage, verify_topofix_pre_final

cfg = ResolverConfig()
result = resolve_psi116(Path(job_topology_input_path))
Path(job_topology_findings_path).write_text(
    json.dumps(result.findings_payload(cfg), indent=2, sort_keys=True) + "\\n",
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
    transaction = apply_topofix_transaction(
        result,
        policy=TransactionPolicy(selected_action_ids=tuple(job_topology_action_ids)),
        config=cfg,
    )
    Path(job_topology_transaction_path).write_text(
        json.dumps(transaction.transaction_payload(), indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    Path(job_topology_validation_path).write_text(
        json.dumps(transaction.validation_payload(), indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )
    status["committed"] = bool(transaction.committed)
    status["rejectReasons"] = list(transaction.reject_reasons)
    if transaction.committed and transaction.fixed_xml is not None:
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
  pyodide.globals.set('job_topology_handoff_path', paths.handoff);
  pyodide.globals.set('job_topology_status_path', paths.status);
  pyodide.globals.set('job_generate_topofix', generateTopoFix);
  pyodide.globals.set('job_topology_action_ids', actionIds);
  await pyodide.runPythonAsync(TOPOLOGY_SNIPPET);

  const status = JSON.parse(readOptional(pyodide, paths.status) || '{}');
  const topologyFindingsText = readOptional(pyodide, paths.findings);
  const topologyFixPlanText = readOptional(pyodide, paths.plan);
  const topoFixTransactionText = generateTopoFix ? readOptional(pyodide, paths.transaction) : '';
  const topoFixValidationText = generateTopoFix ? readOptional(pyodide, paths.validation) : '';
  const topoFixCommitted = status.committed === true;
  const topoFixXmlText = topoFixCommitted ? readOptional(pyodide, paths.fixed) : '';
  const topoFixLineageText = topoFixCommitted ? readOptional(pyodide, paths.lineage) : '';
  const topoFixPreFinalHandoffText = topoFixCommitted ? readOptional(pyodide, paths.handoff) : '';
  if(topoFixCommitted && (!topoFixLineageText || !topoFixPreFinalHandoffText))
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
    topoFixPreFinalHandoffName: topoFixCommitted ? names.handoff : '',
    topoFixCommitted,
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
