"""L4-S1 acceptance tests; entirely invented PSI116 and the pinned XCU reader."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_fixture import generate
import measure
from psi116_topology_resolver import ResolverConfig, read_psi116_xml, resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.short_memo import memo_session
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.uxml_adapter import resolve_from_uxml
from psi116_topology_resolver.uxml_edit_ops import export_edit_ops, apply_edit_ops, compare_hub_patch
from psi116_topology_resolver.lineage import build_topofix_source_lineage, verify_topofix_pre_final


class SpeedTools(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def small(self):
        path = self.root/'small.xml'
        path.write_bytes(generate(seed=116, branches=3, owners=5, blocked=2, nodes=60))
        return path

    def test_T1_fixture_is_deterministic_and_reader_qualifies_exact_counts(self):
        a = generate()
        self.assertEqual(a, generate())
        self.assertNotEqual(a, generate(seed=117))
        doc = read_psi116_xml(a.decode('utf-8'))
        self.assertEqual(len(doc.branches), 41)
        self.assertEqual(sum(len(b.nodes) for b in doc.branches), 1654)
        rows = short_elements(doc, ResolverConfig())
        self.assertEqual(len(rows), 129)
        self.assertEqual(sum(r['eligible'] for r in rows), 89)
        self.assertTrue(all(r['componentType']=='GASK' and r['measuredSpanMm']<=6 for r in rows))
        self.assertTrue(all(r['reason'] for r in rows if not r['eligible']))
        self.assertEqual(len({r['branchIndex'] for r in rows if r['eligible']}),41)

    def test_T2_cli_five_owners_all_stages_add_up_and_every_check_runs(self):
        path = self.small()
        original = path.read_bytes()
        out = self.root/'timings.json'
        result = subprocess.run([sys.executable,'-B',str(Path(measure.__file__)),str(path),
                                 '--owners','5','--out',str(out)],capture_output=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stderr)
        data = json.loads(out.read_bytes())
        self.assertEqual((data['requested'], data['applied'], data['skipped']),(5,5,[]))
        self.assertEqual(set(data['stages']),set(measure.STAGES))
        self.assertEqual(len(data['perOwner']),5)
        for r in data['perOwner']:
            self.assertEqual(r['parity'],'EQUAL')
            self.assertEqual(set(r['stages']),set(measure.STAGES))
            stage_sum = sum(s['seconds'] for s in r['stages'].values())
            self.assertLessEqual(abs(stage_sum-r['wallSeconds']),0.05*r['wallSeconds'])
            self.assertTrue(all(s['seconds']>=0 and s['calls']>=0 for s in r['stages'].values()))
            for label in ('direct','export','validate','apply','replay'):
                self.assertEqual(r['stages']['native_transaction_'+label]['calls'],1)
            self.assertEqual(r['stages']['patch_back_compare']['calls'],1)
            self.assertEqual(r['stages']['hub_parity']['calls'],2)
            self.assertGreater(r['stages']['lineage_recheck']['calls'],0)
            self.assertGreater(r['stages']['model_analyse']['calls'],0)
            self.assertGreater(r['stages']['parse']['calls'],0)
            self.assertGreater(r['stages']['uxml_adapter']['calls'],0)
            self.assertEqual(r['stages']['uxml_reader']['calls'],1)
            self.assertEqual(len(r['transactionCalls']),sum(r['stages'][s]['calls'] for s in measure.STAGES if s.startswith('native_transaction_')))
        self.assertAlmostEqual(sum(s['seconds'] for s in data['stages'].values()),data['wallSeconds'],places=8)
        self.assertEqual(path.read_bytes(),original)
        self.assertNotIn('SHORT-000',out.read_bytes().decode('utf-8'))
        self.assertNotIn(str(path),out.read_bytes().decode('utf-8'))
        self.assertIn(b'share %',result.stdout)

    def test_T3_off_and_on_bytes_equal_independent_uninstrumented_product_calls(self):
        path = self.small()
        original = path.read_bytes()
        root = measure.reader_root()
        off, off_bytes = measure.measure(path,5,measured=False)
        on, on_bytes = measure.measure(path,5)
        self.assertEqual(off['stages'],{})
        self.assertEqual(off['applied'],5)
        self.assertEqual(on['applied'],5)
        cfg = ResolverConfig()
        # Independent baseline: call the existing reader and product APIs,
        # without worker_job, instrumentation, or the measurement loop.
        native_path = self.root/'baseline.xml'
        native_path.write_bytes(original)
        baseline = resolve_psi116(native_path,cfg)
        selected = [r['id'] for r in short_elements(baseline.document,cfg) if r['eligible']]
        with memo_session('independent-baseline'):
            for identifier in selected:
                raw = native_path.read_bytes()
                hub = json.loads(subprocess.check_output(['node',str(root/'tools/psi116-to-uxml.mjs'),str(native_path)],cwd=root))
                baseline = resolve_psi116(native_path,cfg)
                adapted = resolve_from_uxml(hub,cfg,source_name=str(native_path))
                self.assertEqual(baseline.findings_payload(cfg),adapted.findings_payload(cfg))
                self.assertEqual(baseline.fix_plan_payload(cfg),adapted.fix_plan_payload(cfg))
                row = next(r for r in short_elements(baseline.document,cfg) if r['id']==identifier)
                policy = TransactionPolicy(selected_action_ids=(identifier,),short_element_requests=({k:row[k] for k in ('id','sourceSha256','nodeKeys')},))
                direct = apply_topofix_transaction(baseline,policy=policy,config=cfg)
                envelope = export_edit_ops(hub,policy=policy,source_name=str(native_path),config=cfg)
                patched = apply_edit_ops(native_path,hub,envelope,config=cfg)
                self.assertTrue(direct.committed and patched.committed)
                self.assertEqual(compare_hub_patch(direct,patched),[])
                lineage = build_topofix_source_lineage(patched)
                handoff = verify_topofix_pre_final(raw.decode('utf-8'),patched.fixed_xml,patched.transaction_payload(),patched.validation_payload(),lineage,reviewed_action_ids=(identifier,))
                self.assertTrue(handoff['requiresFreshWorkerBasis'])
                self.assertFalse(handoff['nativeCiiReleaseAuthorized'])
                native_path.write_bytes(patched.fixed_xml.encode('utf-8'))
        self.assertEqual(off_bytes,native_path.read_bytes())
        self.assertEqual(on_bytes,off_bytes)
        self.assertEqual(path.read_bytes(),original)
        self.assertNotEqual(off_bytes,original)
        final = read_psi116_xml(off_bytes.decode('utf-8'))
        self.assertEqual(sum(len(b.nodes) for b in final.branches),50)
        self.assertEqual(sum(r['eligible'] for r in short_elements(final,cfg)),0)

    def test_T4_crlf_bom_source_and_binary_worker_outputs(self):
        from unittest.mock import patch
        path = self.small()
        original = b'\xef\xbb\xbf' + path.read_bytes().replace(b'\n', b'\r\n')
        path.write_bytes(original)
        # Reject text-mode scratch writes even on LF-only hosts; the old
        # Worker template adapter fails this test before its SHA guard.
        with patch.object(Path, 'write_text', side_effect=AssertionError('text-mode write')):
            off, off_bytes = measure.measure(path,5,measured=False)
            on, on_bytes = measure.measure(path,5)
        self.assertEqual((off['applied'], on['applied']), (5,5))
        self.assertEqual(on_bytes,off_bytes)
        self.assertEqual(path.read_bytes(),original)
        self.assertTrue(all(r['parity']=='EQUAL' for r in on['perOwner']))


    def test_T5_final_out_memo_on_off_binary_and_non_overwrite(self):
        path = self.small()
        original = b'\xef\xbb\xbf' + path.read_bytes().replace(b'\n', b'\r\n')
        path.write_bytes(original)
        command = [sys.executable, '-B', str(Path(measure.__file__)), str(path), '--owners', '5']
        outputs = []
        for enabled in (True, False):
            suffix = 'on' if enabled else 'off'
            out = self.root/(suffix+'.json')
            final = self.root/(suffix+'.xml')
            result = subprocess.run(command+['--out', str(out), '--final-out', str(final)]
                                    +([] if enabled else ['--memo-off']), capture_output=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(out.read_bytes())
            self.assertEqual((data['requested'], data['applied'], data['skipped']), (5,5,[]))
            self.assertTrue(all(r['parity']=='EQUAL' for r in data['perOwner']))
            self.assertEqual(bool(data['perOwner'][0]['memoDelta']), enabled)
            outputs.append(final.read_bytes())
        self.assertEqual(outputs[0], outputs[1])
        self.assertNotEqual(outputs[0], original)
        for target in (path, self.root/'collision.json', self.root/'on.xml'):
            out = self.root/'collision.json'
            result = subprocess.run(command+['--out', str(out), '--final-out', str(target)],
                                    capture_output=True, timeout=180)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'FINAL_OUTPUT_', result.stderr)
            self.assertFalse(out.exists())
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual((self.root/'on.xml').read_bytes(), outputs[0])


if __name__=='__main__':
    unittest.main()
