"""L4-S2: exact keys, immutable memo custody, and serial Worker parity.

Full fixture tests require the seven pinned XCU reader files (XCU_UXML_ROOT).
They use independent processes for memo-on/off; each executes owners serially.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict, FrozenInstanceError, replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'converters'))
sys.path.insert(0, str(ROOT / 'tools/speed'))
from psi116_topology_resolver import short_memo as memo, ResolverConfig, resolve_psi116
from psi116_topology_resolver.transaction import apply_topofix_transaction
from psi116_topology_resolver import lineage
from test_uxml_short_memo import selected_request
from test_short_elements import fixture
from gen_fixture import generate
import measure


def _run_fixture(path, prefix, enabled):
    # measure.py's measurement flag is not its memo flag. Disable the actual
    # session for the independent OFF control, without altering any Worker check.
    @contextmanager
    def session(token):
        with memo.memo_session(token, enabled=enabled):
            yield
    with patch.object(measure, 'memo_session', session):
        report, fixed = measure.measure(path, 89, measured=enabled,
            progress=lambda i, n, t: print(f'{i}/{n} {t:.3f}s', flush=True))
    Path(str(prefix) + '.json').write_bytes(json.dumps(report).encode('utf-8'))
    Path(str(prefix) + '.xml').write_bytes(fixed)


class CheapMemoSafety(unittest.TestCase):
    def tearDown(self):
        memo.clear_memo()

    def isolation_contract(self):
        before, policy, cfg = selected_request(fixture())
        with memo.memo_session('cheap-isolation'):
            first = apply_topofix_transaction(before, policy=policy, config=cfg)
            self.assertTrue(first.committed)
            hit = apply_topofix_transaction(before, policy=policy, config=cfg)
            pristine = hit.validation_payload()
            self.assertEqual(first.transaction_payload(), hit.transaction_payload())
            first.checks[0].details['INSERT_MUTATION'] = ['poison']
            hit.checks[0].details['HIT_MUTATION'] = {'nested': ['poison']}
            again = apply_topofix_transaction(before, policy=policy, config=cfg)
            self.assertEqual(again.validation_payload(), pristine)
            self.assertIsNot(hit, again)
            self.assertGreaterEqual(memo.stats()['transaction_hit'], 2)
            with self.assertRaises(FrozenInstanceError):
                again.source_result.document.branches[0].nodes[0].raw_xml = 'forged'
            self.assertEqual(again.source_result.document.source_text, fixture())

    def test_T2_mutation_isolated_and_M1_raw_object_mutant_red(self):
        self.isolation_contract()
        # Real mutant: replace both immutable snapshot and materialization
        # boundaries with the original mutable result, not just a mock of a
        # check. The exact same isolation assertion must fail.
        with patch.object(memo, '_snapshot', side_effect=lambda value: value), \
             patch.object(memo, '_restore', side_effect=lambda value: value):
            with self.assertRaises(AssertionError):
                self.isolation_contract()
        print('MUTANT_RED:M1-store-and-return-mutable-object')
        # Direct generic store exercises nested list/dict isolation too.
        store = memo.ShortMemo('mutable-evidence')
        data = {'evidence': [{'nodes': [1, 2]}]}
        store.put('transaction', ('invented',), data)
        data['evidence'][0]['nodes'].append(3)
        value = store.get('transaction', ('invented',))
        value['evidence'][0]['nodes'].append(4)
        self.assertEqual(store.get('transaction', ('invented',)),
                         {'evidence': [{'nodes': [1, 2]}]})

    def digest_contract(self):
        a = bytes(bytearray(b'one\r\n'))
        equal = bytes(bytearray(a))
        b = bytes(bytearray(b'two\r\n'))
        self.assertIsNot(a, equal)
        with memo.memo_session('cheap-digest'), patch.object(memo, '_digest', wraps=memo._digest) as calls:
            self.assertEqual(memo._cached_digest(a), sha256(a).hexdigest())
            self.assertEqual(memo._cached_digest(equal), sha256(a).hexdigest())
            self.assertEqual(memo._cached_digest(b), sha256(b).hexdigest())
            self.assertNotEqual(memo._cached_digest(a), memo._cached_digest(b))
            self.assertEqual(calls.call_count, 2)

    def test_T3_exact_digest_reuse_and_M2_recycled_id_mutant_red(self):
        self.digest_contract()
        # Simulate a deterministically recycled object id. An id-only cache
        # with no retained bytes/equality guard returns the wrong SHA.
        def id_only(store, data):
            recycled_id = 17
            if recycled_id not in store.digests:
                store.digests[recycled_id] = memo._digest(data)
            return store.digests[recycled_id]
        with patch.object(memo.ShortMemo, 'digest', id_only):
            with self.assertRaises(AssertionError):
                self.digest_contract()
        print('MUTANT_RED:M2-id-only-recycled-identity')

    def test_T3_original_canonical_key_bytes_and_mutable_witness(self):
        before, policy, cfg = selected_request(fixture())
        def old_json(v):
            return json.dumps(v, sort_keys=True, separators=(',', ':'),
                              allow_nan=False, ensure_ascii=False).encode('utf-8')
        payload = asdict(before)
        for name in ('source_text', 'source_sha256', 'source_path'):
            payload['document'].pop(name)
        with memo.memo_session('exact-canonical'):
            self.assertEqual(memo._document_bytes(before), old_json(payload))
            key = memo.transaction_key(before, policy, cfg)
            self.assertEqual(key[2], sha256(before.document.source_text.encode()).hexdigest())
            self.assertEqual(key[3], sha256(old_json(asdict(policy))).hexdigest())
            self.assertEqual(key[4], sha256(old_json(asdict(cfg))).hexdigest())
            self.assertEqual(key[-1], sha256(old_json(payload)).hexdigest())
            # Same objects with changed mutable evidence cannot reuse a digest.
            policy.short_element_requests[0]['nodeKeys'].append('SYNTHETIC-FORGED')
            self.assertNotEqual(key, memo.transaction_key(before, policy, cfg))
            self.assertNotEqual(key[4], memo.transaction_key(before, policy,
                replace(cfg, short_span_threshold_mm=5.0))[4])
            self.assertNotEqual(key[-2], memo.transaction_key(before, policy, cfg, route='uxml')[-2])

    def lineage_contract(self):
        before, policy, cfg = selected_request(fixture())
        with memo.memo_session('cheap-lineage'):
            txn = apply_topofix_transaction(before, policy=policy, config=cfg)
            proof = lineage.build_topofix_source_lineage(txn)
            proof['sourceOccurrenceMap'][0]['syntheticForgery'] = True
            with self.assertRaisesRegex(lineage.TopoFixLineageError, 'TOPOFIX_LINEAGE_RECEIPT_DRIFT'):
                lineage.verify_topofix_pre_final(before.document.source_text, txn.fixed_xml,
                    txn.transaction_payload(), txn.validation_payload(), proof,
                    reviewed_action_ids=policy.selected_action_ids)

    def test_M3_skipped_lineage_recheck_red(self):
        self.lineage_contract()
        # Mutant skips verification entirely, accepting a forged receipt.
        with patch.object(lineage, 'verify_topofix_pre_final', return_value={'requiresFreshWorkerBasis': True}):
            with self.assertRaises(AssertionError):
                self.lineage_contract()
        print('MUTANT_RED:M3-skipped-lineage-recheck')


class CheapMemoFullFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Do not silently replace or bypass the pinned reader.
        measure.reader_root()
        cls.temp = tempfile.TemporaryDirectory(prefix='cheap-memo-fixture-')
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        source = directory / 'invented.xml'
        source.write_bytes(generate())
        original = source.read_bytes()
        # Two independent processes, each serial across all 89 owners.
        processes = []
        for enabled in (True, False):
            prefix = directory / ('on' if enabled else 'off')
            proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()),
                '--fixture-worker', str(source), str(prefix), 'on' if enabled else 'off'])
            processes.append((proc, prefix))
        try:
            for proc, prefix in processes:
                if proc.wait() != 0:
                    raise RuntimeError(f'FULL_FIXTURE_WORKER_FAILED:{prefix.name}')
        finally:
            for proc, _ in processes:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait()
        cls.on = json.loads((directory/'on.json').read_bytes())
        cls.off = json.loads((directory/'off.json').read_bytes())
        cls.on_bytes = (directory/'on.xml').read_bytes()
        cls.off_bytes = (directory/'off.xml').read_bytes()
        if source.read_bytes() != original:
            raise RuntimeError('ORIGINAL_FIXTURE_MUTATED')
        print('L4_S2_MEASURED=' + json.dumps({k: cls.on[k] for k in
            ('owners','applied','wallSeconds','meanSeconds','stages')}, sort_keys=True))
        print('L4_S2_MEMO_OFF=' + json.dumps({k: cls.off[k] for k in
            ('owners','applied','wallSeconds','meanSeconds')}, sort_keys=True))

    def test_T1_full_89_memo_on_off_byte_identical(self):
        self.assertEqual((self.on['applied'], self.off['applied']), (89, 89))
        self.assertEqual((self.on['skipped'], self.off['skipped']), ([], []))
        self.assertEqual(self.on_bytes, self.off_bytes)
        self.assertTrue(all(r['parity'] == 'EQUAL' for r in self.on['perOwner']))
        self.assertTrue(all(r['parity'] == 'EQUAL' for r in self.off['perOwner']))

    def test_T5_full_fixture_digest_copy_counts_and_checks(self):
        self.assertEqual(self.on['applied'], 89)
        self.assertEqual((self.on['branches'], self.on['nodes'], self.on['initialEligible']), (41, 1654, 89))
        for r in self.on['perOwner']:
            with self.subTest(owner=r['ownerOrdinal']):
                s = r['stages']
                self.assertLessEqual(s['memo_copy']['calls'], 2)
                self.assertLessEqual(s['memo_digest']['calls'], 6)
                for name in ('direct','export','validate','apply','replay'):
                    self.assertEqual(s['native_transaction_'+name]['calls'], 1)
                self.assertEqual(s['lineage_recheck']['calls'], 5)
                self.assertEqual(s['hub_parity']['calls'], 2)
                self.assertEqual(s['patch_back_compare']['calls'], 1)
                self.assertEqual(r['parity'], 'EQUAL')
                self.assertEqual(r['memoDelta']['transaction_miss'], 2)
                self.assertEqual(r['memoDelta']['transaction_hit'], 3)
        print('L4_S2_MAX_DIGEST=' + str(max(r['stages']['memo_digest']['calls'] for r in self.on['perOwner'])))


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--fixture-worker':
        _run_fixture(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4] == 'on')
    else:
        unittest.main()
