"""Measure the unchanged Python Worker short-Apply path, one owner at a time."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from hashlib import sha256, sha1
from pathlib import Path
import ast
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'converters'))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.short_memo import memo_session, stats

PKG = 'psi116_topology_resolver'
STAGES = ('parse', 'model_analyse', 'resolve', 'native_transaction_direct',
          'native_transaction_export', 'native_transaction_validate',
          'native_transaction_apply', 'native_transaction_replay',
          'native_transaction_nested', 'uxml_reader', 'uxml_adapter',
          'canonical_export', 'canonical_rederivation', 'patch_back',
          'patch_back_compare', 'hub_parity', 'lineage_recheck',
          'memo_digest', 'memo_copy', 'memo_other', 'other')


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def digest(data):
    return sha256(data).hexdigest()


def reader_root(value=None):
    root = Path(value or os.environ.get('XCU_UXML_ROOT', ROOT / 'dist/vendor/uxml')).resolve()
    # The same seven immutable Git blob pins as the product fetch script.
    script = (ROOT / 'tools/fetch-uxml-reader.sh').read_bytes().decode('utf-8').replace('\r\n', '\n')
    pins = re.findall(r'^fetch_pinned (\S+) ([0-9a-f]{40})$', script, re.M)
    require(len(pins) == 7, 'READER_PIN_LIST_DRIFT')
    for name, expected in pins:
        path = root / name
        require(path.is_file(), 'XCU_PINNED_READER_REQUIRED')
        data = path.read_bytes()
        require(sha1(f'blob {len(data)}\0'.encode()+data).hexdigest() == expected,
                'UXML_READER_BLOB_HASH_MISMATCH')
    return root


def read_hub(path, root):
    proc = subprocess.run(['node', str(root/'tools/psi116-to-uxml.mjs'), str(path)],
                          cwd=root, capture_output=True, timeout=120, check=False)
    require(proc.returncode == 0 and not proc.stderr, 'XCU_PSI116_READER_FAILED')
    hub = json.loads(proc.stdout)
    require(hub['sources'][0]['sourceText'].encode('utf-8') == path.read_bytes(),
            'XCU_SOURCE_BYTES_DRIFT')
    return hub


def worker_code(measured=False):
    # Execute the actual checked-in Python template, not a reimplementation.
    js = (ROOT/'converters/xml-cii-2019-standalone/topology-integration.js').read_bytes().decode('utf-8').replace('\r\n', '\n')
    source = js.split('const TOPOLOGY_SNIPPET = `', 1)[1].split('`;\n', 1)[0]
    source = source.replace('\\\\', '\\')
    tree = ast.parse(source)
    # Pyodide's virtual filesystem writes UTF-8/LF. On Windows, Path.write_text
    # translates LF to CRLF after the transaction has computed its exact SHA.
    # Adapt only scratch-file I/O in the local harness, never product code.
    class BinaryWrites(ast.NodeTransformer):
        def visit_Call(self, node):
            node = self.generic_visit(node)
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'write_text':
                require(len(node.args) == 1 and len(node.keywords) == 1 and
                        node.keywords[0].arg == 'encoding' and
                        isinstance(node.keywords[0].value, ast.Constant) and
                        node.keywords[0].value.value == 'utf-8', 'WORKER_WRITE_SHAPE_DRIFT')
                node.func.attr = 'write_bytes'
                node.args[0] = ast.Call(func=ast.Attribute(value=node.args[0], attr='encode',
                                                         ctx=ast.Load()),
                                        args=[ast.Constant('utf-8')], keywords=[])
                node.keywords = []
            return node
    tree = BinaryWrites().visit(tree)
    if measured:
        # The comparer is local to the template; wrap just this definition.
        for i, statement in enumerate(tree.body):
            if isinstance(statement, ast.FunctionDef) and statement.name == 'compare_hub_values':
                tree.body.insert(i+1, ast.parse('compare_hub_values = _profile_hub(compare_hub_values)').body[0])
                break
        else:
            raise RuntimeError('WORKER_PARITY_FUNCTION_NOT_FOUND')
    return compile(ast.fix_missing_locations(tree), '<topology-worker-python>', 'exec')


class Meter:
    """Exclusive clocks: children are subtracted from the parent's elapsed time.

    Inclusive clocks are also retained for per-call diagnosis; never add them.
    Exact-input repeats are counted in memory and only counts are emitted.
    """
    def __init__(self):
        self.stack = []
        self.exclusive = defaultdict(float)
        self.inclusive = defaultdict(float)
        self.calls = Counter()
        self.repeat = Counter()
        self.seen = set()
        self.records = []
        self.seen_txn_bytes = set()
        self.same_bytes = Counter()

    @contextmanager
    def stage(self, label, fingerprint=None):
        self.calls[label] += 1
        if fingerprint is not None:
            identity = (label.split('native_transaction_')[0] if label.startswith('native_transaction_') else label, fingerprint)
            if identity in self.seen:
                self.repeat[label] += 1
            self.seen.add(identity)
            if label.startswith('native_transaction_'):
                if fingerprint[0] in self.seen_txn_bytes:
                    self.same_bytes[label] += 1
                self.seen_txn_bytes.add(fingerprint[0])
        frame = [label, 0.0]
        self.stack.append(frame)
        started = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter()-started
            self.stack.pop()
            self.exclusive[label] += elapsed-frame[1]
            self.inclusive[label] += elapsed
            if self.stack:
                self.stack[-1][1] += elapsed
            if label.startswith('native_transaction_'):
                self.records.append({'stage': label, 'inclusiveSeconds': elapsed,
                                     'exclusiveSeconds': elapsed-frame[1]})

    def wrap(self, func, label, key=None, outer_only=False):
        def wrapped(*args, **kwargs):
            name = label(*args, **kwargs) if callable(label) else label
            if outer_only and any(frame[0] == name for frame in self.stack):
                return func(*args, **kwargs)
            fingerprint = key(*args, **kwargs) if key else None
            with self.stage(name, fingerprint):
                return func(*args, **kwargs)
        return wrapped

    def txn_label(self, source, **kwargs):
        if not kwargs['policy'].short_element_requests:
            return 'native_transaction_nested'
        labels = [frame[0] for frame in self.stack]
        for context, suffix in [('lineage_recheck','replay'), ('canonical_rederivation','validate'),
                                ('canonical_export','export'), ('patch_back','apply')]:
            if context in labels:
                return 'native_transaction_'+suffix
        return 'native_transaction_direct'

    def result(self, wall):
        self.exclusive['other'] = wall-sum(self.exclusive.values())
        self.inclusive['other'] = self.exclusive['other']
        self.calls['other'] = 1
        return {name: {'seconds': self.exclusive[name], 'inclusiveSeconds': self.inclusive[name],
                       'calls': self.calls[name], 'repeatedInputCalls': self.repeat[name],
                       'sameTransactionBytesCalls': self.same_bytes[name]}
                for name in STAGES}


def source_key(source, *args, **kwargs):
    if hasattr(source, 'document'):
        return source.document.source_sha256
    if hasattr(source, 'source_sha256'):
        return source.source_sha256
    if isinstance(source, Path) or (isinstance(source, str) and '<' not in source):
        return digest(Path(source).read_bytes())
    return digest(source.encode('utf-8'))


def txn_key(source, **kwargs):
    # Same bytes AND same policy AND same route, not proof of interchangeable authority.
    return (source_key(source), repr(kwargs['policy']), kwargs.get('memo_route','native'))


@contextmanager
def instrumentation(meter):
    # Patch function aliases only inside the measuring process; restore all even
    # on refusal. Identity-sensitive short_memo resolver checks still compare
    # the same wrapper object through both imports.
    modules = {name: importlib.import_module(PKG+'.'+name) for name in
               ('parser','resolver','transaction','short_elements','short_memo',
                'uxml_adapter','uxml_edit_ops','lineage')}
    specs = [
        ('parser','read_psi116_xml','parse',source_key),
        ('transaction','_parse_clone','parse',source_key),
        ('lineage','_xml_root','parse',source_key),
        ('resolver','analyze_document','model_analyse',source_key),
        ('resolver','resolve_psi116','resolve',source_key),
        ('transaction','apply_topofix_transaction',meter.txn_label,txn_key),
        ('uxml_adapter','resolve_from_uxml','uxml_adapter',None),
        ('uxml_edit_ops','export_edit_ops','canonical_export',None),
        ('uxml_edit_ops','_validate_ops','canonical_rederivation',None),
        ('uxml_edit_ops','apply_edit_ops','patch_back',None),
        ('uxml_edit_ops','compare_hub_patch','patch_back_compare',None),
        ('lineage','build_topofix_source_lineage','lineage_recheck',None),
        ('lineage','verify_topofix_pre_final','lineage_recheck',None),
        ('short_memo','_document_digest','memo_digest',None),
        ('short_memo','_digest','memo_digest',None),
        ('short_memo','deepcopy','memo_copy',None),
        ('short_memo','_snapshot','memo_copy',None),
        ('short_memo','_restore','memo_copy',None),
        ('short_memo','source_resolve','resolve',None),
        ('short_memo','uxml_resolve','memo_other',lambda hub,*a,**kw: hub['sources'][0]['hash']),
    ]
    changes = []
    try:
        for mod, attr, label, key in specs:
            original = getattr(modules[mod], attr)
            wrapper = meter.wrap(original, label, key,
                                 outer_only=label in ('resolve','memo_digest'))
            for module in [m for n,m in list(sys.modules.items()) if n == PKG or n.startswith(PKG+'.')]:
                for name, val in list(vars(module).items()):
                    if val is original:
                        changes.append((module,name,original))
                        setattr(module,name,wrapper)
        yield
    finally:
        for mod, name, original in reversed(changes):
            setattr(mod,name,original)


def worker_job(source, hub, row, directory, *, meter=None, compiled=None):
    names = ('findings','plan','transaction','validation','fixed','lineage','handoff',
             'post_findings','post_plan','status')
    paths = {name: directory/(name+'.json' if name != 'fixed' else 'fixed.xml') for name in names}
    for path in paths.values():
        if path.exists():
            path.unlink()  # only the disposable scratch directory, never source
    variables = {'job_topology_input_path': str(source), 'job_topology_uxml_json': json.dumps(hub),
                 'job_connection_preview_json': 'null', 'job_generate_topofix': True,
                 'job_topology_action_ids': [row['id']],
                 'job_short_elements_json': json.dumps([{k:row[k] for k in ('id','sourceSha256','nodeKeys')}]),
                 'job_joint_repairs_json': '[]', 'job_bulk_speed_profile': False}
    variables.update({'job_topology_'+name+'_path':str(path) for name,path in paths.items()})
    if meter:
        variables['_profile_hub'] = lambda fn: meter.wrap(fn,'hub_parity',outer_only=True)
    exec(compiled or worker_code(bool(meter)), variables)
    def load(name):
        return json.loads(paths[name].read_bytes())
    status = load('status')
    if not status['committed'] and status['hubParity']['status']=='DIFFERENT' and not paths['fixed'].exists():
        # Same narrow no-output owner refusals as short-bulk.mjs; report only
        # the code, never the source-bearing suffix. All other mismatches stop.
        differences = status['hubParity']['differences']
        match = re.fullmatch(r'/patchBack: UxmlPatchError: (UXML_[A-Z0-9_]+)(?::[^\r\n]*)?', differences[0]) if len(differences)==1 else None
        if match and match[1] in {'UXML_LOSS_CONTRACT_FIELD_TOUCH', 'UXML_CLOS_WRITE_HELD',
                                 'UXML_SHORT_NATIVE_REFUSED', 'UXML_SHORT_NOT_ELIGIBLE_OR_WITNESS_DRIFT'}:
            return None, match[1]
    require(status['committed'] and status['hubParity']['status']=='EQUAL', 'WORKER_NOT_EQUAL_COMMITTED')
    fixed = paths['fixed'].read_bytes()
    txn, validation, lineage, handoff, findings, plan = [load(n) for n in
        ('transaction','validation','lineage','handoff','post_findings','post_plan')]
    sha, fixed_sha = digest(source.read_bytes()), digest(fixed)
    ops = status['appliedEditOps']
    request = {k:row[k] for k in ('id','sourceSha256','nodeKeys')}
    require(isinstance(ops,list) and len(ops)==1 and ops[0]['kind']=='DROP_SHORT_ELEMENT' and
            ops[0]['sourceActionId']==row['id'] and ops[0]['opId']=='UXML-OP-'+row['id'] and
            ops[0]['fileSha256']==sha and ops[0]['params'][0]['request']==request and
            isinstance(ops[0]['removedWithRecord'],list) and
            isinstance(ops[0]['targets'],list) and ops[0]['targets'] and
            len(set(ops[0]['targets']))==len(ops[0]['targets']) and
            all(isinstance(w.get('field'),str) and w['field'] and w.get('recordKey') in ops[0]['targets']
                for w in ops[0]['removedWithRecord']) and
            len({(w['recordKey'],w['field']) for w in ops[0]['removedWithRecord']})==len(ops[0]['removedWithRecord']),
            'CANONICAL_OP_RECEIPT_DRIFT')
    source_hashes = {'source.bytes': sha, 'txn.source.sha256': txn['source']['sha256'],
                     'validation.sourceSha256': validation['sourceSha256'],
                     'lineage.sourceXmlSha256': lineage['sourceXmlSha256']}
    fixed_hashes = {'fixed.bytes': fixed_sha, 'txn.fixedXmlSha256': txn['fixedXmlSha256'],
                    'validation.fixedXmlSha256': validation['fixedXmlSha256'],
                    'lineage.fixedXmlSha256': lineage['fixedXmlSha256'],
                    'findings.source.sha256': findings['source']['sha256'],
                    'plan.source.sha256': plan['source']['sha256']}
    checks = {
        'source_hashes': all(v == sha for v in source_hashes.values()),
        'fixed_hashes': all(v == fixed_sha for v in fixed_hashes.values()),
        'txn.schema': txn['schema']=='psi116-topofix-transaction/v1',
        'validation.schema': validation['schema']=='psi116-topofix-validation/v1',
        'txn.committed': txn['committed'], 'validation.committed': validation['committed'],
        'txn.sourceXmlMutated': not txn['sourceXmlMutated'],
        'txn.selectedActions': txn['selectedActions']==[row['id']],
        'lineage.state': lineage['state']=='PRE_FINAL_ONLY',
        'lineage.sourceXmlMutated': not lineage['sourceXmlMutated'],
        'handoff.requiresFreshWorkerBasis': handoff['requiresFreshWorkerBasis'],
        'handoff.nativeCiiReleaseAuthorized': not handoff['nativeCiiReleaseAuthorized'],
        'handoff.acceptedFinalTransferred': not handoff['acceptedFinalTransferred'],
        'validation.checks': bool(validation['checks']),
        'validation.blockingFailureCount': validation['summary']['blockingFailureCount']==0,
        'validation.blockingChecks': all(c['passed'] or not c['blocking'] for c in validation['checks']),
        'plan.actions': isinstance(plan['actions'],list),
        'findings.findings': isinstance(findings['findings'],list),
        'findings.shortElements': isinstance(findings['shortElements'],list),
        'txn.removeOperation': any(o['operation']=='REMOVE_SELECTED_SHORT_ELEMENT_RECORD' for o in txn['operations']),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        details = ', '.join(f'{name}={str(value)[:12]}'
                            for name, value in {**source_hashes, **fixed_hashes}.items())
        raise RuntimeError('SOURCE_LINEAGE_OR_RECHECK_DRIFT: failed=' + ','.join(failed) + '; ' + details)
    return fixed, findings['shortElements']


def measure(path, owners=None, *, reader=None, measured=True, progress=None, memo_enabled=True):
    root = reader_root(reader)
    path = Path(path)
    original = path.read_bytes()
    initial = resolve_psi116(path)
    rows = short_elements(initial.document, ResolverConfig())
    selected = [r['id'] for r in rows if r['eligible']]
    if owners is not None:
        require(0 < owners <= len(selected), 'OWNER_COUNT_OUT_OF_RANGE')
        selected = selected[:owners]
    require(bool(selected), 'NO_ELIGIBLE_SHORT_OWNERS')
    reports = []
    skipped = []
    fixed = original
    compiled = worker_code(measured)
    session = memo_session('l4-s1') if memo_enabled else memo_session('l4-s1', enabled=False)
    with tempfile.TemporaryDirectory(prefix='topofix-speed-') as temp, session:
        directory = Path(temp)
        source = directory/'current.xml'
        source.write_bytes(original)
        for i, identifier in enumerate(selected, 1):
            row = next((r for r in rows if r['id']==identifier),None)
            if row is None or not row['eligible'] or row['sourceSha256'] != digest(source.read_bytes()):
                skipped.append({'ownerOrdinal':i,'code':'NOT_ELIGIBLE_ON_CURRENT_REVISION'})
                continue
            meter = Meter() if measured else None
            previous = stats()
            started = time.perf_counter()
            with instrumentation(meter) if meter else nullcontext():
                with meter.stage('uxml_reader') if meter else nullcontext():
                    hub = read_hub(source,root)
                next_bytes, next_rows = worker_job(source,hub,row,directory,meter=meter,compiled=compiled)
                if next_bytes is not None:
                    fixed, rows = next_bytes, next_rows
                    source.write_bytes(fixed)
                else:
                    skipped.append({'ownerOrdinal':i,'code':next_rows})
            wall = time.perf_counter()-started
            current = stats()
            report = {'ownerOrdinal':i,'wallSeconds':wall,'parity':'EQUAL' if next_bytes is not None else 'REFUSED',
                      'memoDelta':{k:v-previous.get(k,0) for k,v in current.items()},
                      'stages':meter.result(wall) if meter else {},
                      'transactionCalls':meter.records if meter else []}
            reports.append(report)
            if progress:
                progress(i, len(selected), wall)
    require(path.read_bytes()==original,'ORIGINAL_SOURCE_MUTATED')
    total = sum(r['wallSeconds'] for r in reports)
    aggregate = {s:{'seconds':sum(r['stages'].get(s,{}).get('seconds',0) for r in reports),
                    'inclusiveSeconds':sum(r['stages'].get(s,{}).get('inclusiveSeconds',0) for r in reports),
                    'calls':sum(r['stages'].get(s,{}).get('calls',0) for r in reports),
                    'repeatedInputCalls':sum(r['stages'].get(s,{}).get('repeatedInputCalls',0) for r in reports),
                    'sameTransactionBytesCalls':sum(r['stages'].get(s,{}).get('sameTransactionBytesCalls',0) for r in reports)}
                 for s in STAGES} if measured else {}
    return {'schema':'topofix-speed/v1','measured':measured,'owners':len(reports),'requested':len(selected),'applied':sum(r['parity']=='EQUAL' for r in reports),'skipped':skipped,
            'branches':len(initial.document.branches),
            'nodes':sum(len(b.nodes) for b in initial.document.branches),
            'initialEligible':sum(r['eligible'] for r in short_elements(initial.document,ResolverConfig())),
            'wallSeconds':total,'meanSeconds':total/len(reports) if reports else 0,'stages':aggregate,'perOwner':reports}, fixed


def table(report):
    print(f"Attempted owners: {report['owners']}  applied: {report['applied']}  skipped: {len(report['skipped'])}  total: {report['wallSeconds']:.3f} s  mean: {report['meanSeconds']:.3f} s")
    print(f"{'Stage':30} {'total s':>10} {'mean s':>10} {'share %':>9} {'calls':>8} {'calls/own':>10} {'repeats':>8}")
    if not report['owners']:
        return
    for stage,v in report['stages'].items():
        print(f"{stage:30} {v['seconds']:10.3f} {v['seconds']/report['owners']:10.3f} "
              f"{100*v['seconds']/report['wallSeconds']:9.2f} {v['calls']:8d} "
              f"{v['calls']/report['owners']:10.2f} {v['repeatedInputCalls']:8d}")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('psi116',type=Path)
    p.add_argument('--owners',type=int)
    p.add_argument('--out',type=Path,default=Path('timings.json'))
    p.add_argument('--xcu-root',type=Path)
    p.add_argument('--measurement-off',action='store_true')
    p.add_argument('--memo-off',action='store_true', help='disable memo, keep every Worker check')
    p.add_argument('--final-out',type=Path, help='write final PSI116 bytes to a new local file')
    a=p.parse_args()
    require(a.out.resolve()!=a.psi116.resolve(),'OUTPUT_IS_ORIGINAL_SOURCE')
    if a.final_out is not None:
        require(a.final_out.resolve() not in (a.psi116.resolve(), a.out.resolve()),
                'FINAL_OUTPUT_PATH_COLLISION')
        require(not a.final_out.exists(), 'FINAL_OUTPUT_EXISTS')
    report,fixed=measure(a.psi116,a.owners,reader=a.xcu_root,measured=not a.measurement_off,
                     memo_enabled=not a.memo_off,
                     progress=lambda i,n,t:print(f'{i}/{n} {t:.3f}s',file=sys.stderr,flush=True))
    with a.out.open('xb') as f:
        f.write((json.dumps(report,indent=2)+'\n').encode('utf-8'))
    if a.final_out is not None:
        require(report['applied']==report['requested'] and not report['skipped'], 'FINAL_OUTPUT_INCOMPLETE')
        with a.final_out.open('xb') as f:
            f.write(fixed)
    table(report)


if __name__=='__main__':
    main()
