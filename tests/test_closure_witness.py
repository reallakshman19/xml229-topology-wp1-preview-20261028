"""Read-only CLOS binding witnesses: explain absent pairs, never join them. Synthetic fixtures only."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'converters'))
from test_port_policy import node, doc, pipe_flange
from psi116_topology_resolver import resolve_psi116, ResolverConfig
from psi116_topology_resolver import read_psi116_xml
from psi116_topology_resolver.connection_ports import PortModel, bound_closure_records
from psi116_topology_resolver.closure_witness import (ROW_KEYS, _binding_kinds, _physical,
                                                      closure_binding_witnesses)

CLOS = '<ConnectionType>CLOS</ConnectionType>'
PRE_CHANGE_KEYS = ['config', 'findings', 'manualConnectionPorts', 'resolvedConnections',
                   'schema', 'shortElements', 'source', 'summary']
# sha256 of json.dumps(findings_payload, sort_keys=True) computed at 2ba52da7 (before this change).
PRE_CHANGE_PAYLOAD_SHA256 = {
    'gap': '170bc2c166177da5217bbe4c73560f213e90c5ab56419404868f39502ce93630',
    'gap_open': 'a5dcc374378dbf188ed2292bfc5d23e1f7b735a502710d85426fcec32ca25315',
    'pipe_flange_75': '596342a6f6d3d46678f1c464151064e39c83cc9082c89cdc90ff761c43f41683',
}


def n(num, kind, ref, end, xyz, extra=''):
    return node(num, kind, ref, end, xyz, '<WallThickness>6.02</WallThickness>' + extra).replace(
        '<OutsideDiameter>100</OutsideDiameter>', '<OutsideDiameter>114.3</OutsideDiameter>')


def gap_case(clos=True):
    """Closed RIGID end 2 on one branch, open FBLI end 1 on another, 240.6 mm apart, X/Z aligned."""
    return doc(n(120, 'FLAN', 'V', 1, '1000 0 0') + n(6880, 'RIGID', 'V', 2, '1100 0 0', CLOS if clos else ''),
               n(6450, 'FBLI', 'BL', 1, '1340.6 0 0') + n(-1, 'FBLI', 'BL', 2, '1372.8 0 0'))


def witnesses(source):
    return resolve_psi116(source).findings_payload(ResolverConfig())['closureBindingWitnesses']


def payload_without_witnesses_sha(source):
    payload = resolve_psi116(source).findings_payload(ResolverConfig())
    payload.pop('closureBindingWitnesses')
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()


class ClosureWitness(unittest.TestCase):
    def test_a_closed_end_near_open_end_is_witnessed_not_joined(self):
        result = resolve_psi116(gap_case())
        rows = result.findings_payload(ResolverConfig())['closureBindingWitnesses']
        self.assertEqual([r['sourceKey'] for r in rows], ['B0:N6880:S1'])
        row = rows[0]
        self.assertEqual((row['bindingStatus'], row['rowKind'], row['nodeNumber'], row['branchIndex'],
                          row['componentType'], row['ownerType'], row['componentRefNo'], row['endpoint']),
                         ('BOUND', 'PORT', 6880, 0, 'RIGID', 'FLAN', 'V', 2))
        self.assertEqual(row['sourceSha256'], hashlib.sha256(gap_case().encode('utf-8')).hexdigest())
        self.assertEqual([(d['sourceKey'], d['bindingKinds']) for d in row['closureDeclarations']],
                         [('B0:N6880:S1', ['EXACT_SOURCE_RECORD', 'SAME_POSITIVE_NODE_NUMBER_WITHIN_TOLERANCE',
                                           'SAME_COMPONENT_OWNER_ENDPOINT'])])
        self.assertEqual(row['pairingEffect'], 'PORT_EXCLUDED_FROM_AUTOMATIC_AND_SECOND_PASS_PAIRING')
        # Explanation only: no finding or action ties the closed end to its 240.6 mm neighbour.
        pair = {'B0:N6880:S1', 'B1:N6450:S0'}
        self.assertFalse(any(pair <= set(f.node_keys) for f in result.findings))
        self.assertFalse(any({6880, 6450} <= set(a.node_numbers) for a in result.fix_actions))
        self.assertFalse(any(a.disposition == 'CLOSE_PORT_CONNECTION' for a in result.fix_actions))
        self.assertFalse(any(pair <= set(c.get('node_keys', ())) for c in result.connection_resolutions))

    def test_g_clos_hides_open_end_and_only_the_witness_explains_it(self):
        # Fails if the witness is removed or CLOS is ignored by the extractor.
        closed, opened = resolve_psi116(gap_case()), resolve_psi116(gap_case(False))
        open_end = lambda r: any(f.code == 'BRANCH_END_UNVERIFIED' and 'B0:N6880:S1' in f.node_keys
                                 for f in r.findings)
        self.assertTrue(open_end(opened))
        self.assertFalse(open_end(closed))
        closed_rows = closed.findings_payload(ResolverConfig())['closureBindingWitnesses']
        self.assertIn('B0:N6880:S1', [r['sourceKey'] for r in closed_rows if r['bindingStatus'] == 'BOUND'])
        self.assertEqual(opened.findings_payload(ResolverConfig())['closureBindingWitnesses'], [])

    def test_b_duplicate_node_numbers_on_two_branches_give_two_rows(self):
        source = doc(n(500, 'FLAN', 'A', 1, '0 0 0', CLOS) + n(-1, 'RIGID', 'A', 2, '100 0 0'),
                     n(500, 'FLAN', 'B', 1, '5000 0 0', CLOS) + n(-1, 'RIGID', 'B', 2, '5100 0 0'))
        rows = witnesses(source)
        self.assertEqual([(r['sourceKey'], r['bindingStatus']) for r in rows],
                         [('B0:N500:S0', 'BOUND'), ('B1:N500:S0', 'BOUND')])
        for row in rows:
            self.assertEqual([d['sourceKey'] for d in row['closureDeclarations']], [row['sourceKey']])

    def test_c_negative_helper_unqualified_and_unreadable_declarations_stay_explicit(self):
        source = doc(node(-1, 'BRAN', 'B', 1, '0 0 0', CLOS) + node(10, 'FBLI', 'BLIND', 1, '0 0 0') +
                     node(-1, 'FBLI', 'BLIND', 2, '32.2 0 0') + node(-1, 'ATTA', 'S', 0, '10 0 0', CLOS) +
                     node(-1, 'PIPE', 'Q', 1, '', CLOS))
        rows = {r['sourceKey']: r for r in witnesses(source)}
        self.assertEqual(list(rows), ['B0:N-1:S0', 'B0:N10:S1', 'B0:N-1:S3', 'B0:N-1:S4'])
        helper = rows['B0:N-1:S0']
        self.assertEqual((helper['bindingStatus'], helper['ownerType'], helper['positiveNodeNumber']),
                         ('BOUND', 'BRAN', False))
        # BRAN is never in the authority's `physical` list, so its own row is not a boundary binding.
        self.assertEqual(helper['closureDeclarations'][0]['bindingKinds'],
                         ['EXACT_SOURCE_RECORD', 'SAME_COMPONENT_OWNER_ENDPOINT'])
        blind = rows['B0:N10:S1']
        self.assertEqual([(d['sourceKey'], d['bindingKinds']) for d in blind['closureDeclarations']],
                         [('B0:N-1:S0', ['BRANCH_BOUNDARY_START'])])
        # The negative FBLI end 2 has no CLOS of its own and is not given one.
        self.assertNotIn('B0:N-1:S2', rows)
        self.assertEqual((rows['B0:N-1:S3']['bindingStatus'], rows['B0:N-1:S3']['portQualified'],
                          rows['B0:N-1:S3']['boundRecordKeys']), ('UNQUALIFIED', False, ['B0:N-1:S3']))
        self.assertEqual(rows['B0:N-1:S4']['bindingStatus'], 'EVIDENCE_UNAVAILABLE')
        self.assertTrue(all(tuple(r) == ROW_KEYS for r in rows.values()))

    def test_c_bran_boundary_label_follows_authority_predicates(self):
        start_only_bran = doc(node(-1, 'BRAN', 'B', 1, '0 0 0', CLOS) + node(-1, 'BRAN', 'B', 2, '0 0 0'))
        end_boundary = doc(node(10, 'FBLI', 'BL', 1, '0 0 0') + node(-1, 'FBLI', 'BL', 2, '32.2 0 0') +
                           node(-1, 'BRAN', 'B', 2, '32.2 0 0', CLOS))
        kinds = lambda src: {r['sourceKey']: [k for d in r['closureDeclarations'] for k in d['bindingKinds']]
                             for r in witnesses(src)}
        self.assertFalse(any('BRANCH_BOUNDARY_START' in v for v in kinds(start_only_bran).values()))
        self.assertEqual(kinds(end_boundary), {'B0:N-1:S1': ['BRANCH_BOUNDARY_END'],
                                               'B0:N-1:S2': ['EXACT_SOURCE_RECORD', 'SAME_COMPONENT_OWNER_ENDPOINT']})

    def test_c_labels_agree_with_authority_for_every_record_pair(self):
        sources = (gap_case(), pipe_flange(75, True).replace('<NodeNumber>30</NodeNumber>', '<NodeNumber>30</NodeNumber>' + CLOS),
                   doc(node(-1, 'BRAN', 'B', 1, '0 0 0', CLOS) + node(10, 'FBLI', 'BLIND', 1, '0 0 0') +
                       node(-1, 'FBLI', 'BLIND', 2, '32.2 0 0') + node(-1, 'BRAN', 'B', 2, '32.2 0 0', CLOS)),
                   doc(n(500, 'FLAN', 'A', 1, '0 0 0', CLOS) + n(500, 'RIGID', 'A', 2, '0.3 0 0')))
        for source in sources:
            d = read_psi116_xml(source)
            for branch in d.branches:
                physical = _physical(branch)
                for target in (x for x in branch.nodes if x.position):
                    bound = {r.key for r in bound_closure_records(d, target, 0.5)}
                    for decl in (x for x in branch.nodes if x.position and x.connection_type == 'CLOS'):
                        labelled = _binding_kinds(branch, physical, decl, target, 0.5) != ['UNCLASSIFIED']
                        self.assertEqual(labelled, decl.key in bound, (decl.key, target.key))

    def test_sort_puts_branch_0_declaration_before_branch_1_port(self):
        # Ports are collected before off-port declarations; only the sort restores source order.
        source = doc(node(10, 'PIPE', 'P', 1, '0 0 0') + node(-1, 'ATTA', 'S', 0, '50 0 0', CLOS) +
                     node(20, 'PIPE', 'P', 2, '100 0 0'),
                     n(500, 'FLAN', 'A', 1, '5000 0 0', CLOS) + n(-1, 'RIGID', 'A', 2, '5100 0 0'))
        self.assertEqual([(r['sourceKey'], r['bindingStatus']) for r in witnesses(source)],
                         [('B0:N-1:S1', 'UNQUALIFIED'), ('B1:N500:S0', 'BOUND')])

    def test_2000_node_branch_with_20_declarations_census(self):
        parts = []
        for i in range(1000):
            closed = i % 100 == 0
            parts.append(node(2 * i + 1, 'PIPE', f'P{i}', 1, f'{200 * i} 0 0', CLOS if closed else '') +
                         node(2 * i + 2, 'PIPE', f'P{i}', 2, f'{200 * i + 100} 0 0'))
            if i % 100 == 50:  # off-port declaration: exercises the reverse scan
                parts.append(node(-1, 'ATTA', f'S{i}', 0, f'{200 * i + 50} 0 0', CLOS))
        d = read_psi116_xml(doc(''.join(parts)))
        model = PortModel(d, ResolverConfig())
        rows = closure_binding_witnesses(d, ResolverConfig(), model)
        self.assertEqual(sum(len(b.nodes) for b in d.branches), 2010)
        self.assertEqual([r['bindingStatus'] for r in rows].count('BOUND'), 10)
        self.assertEqual([r['bindingStatus'] for r in rows].count('UNQUALIFIED'), 10)

    def test_off_port_same_number_closure_within_25mm_is_in_unqualified_reverse_witness(self):
        # The unqualified-declaration reverse lookup must include a remote
        # same-positive-NodeNumber alias; shrinking its 25 mm radius loses S1.
        source = doc(
            node(700, 'ATTA', 'SUP_A', 0, '0 0 0', CLOS) +
            node(700, 'ATTA', 'SUP_B', 0, '12 0 0')
        )
        rows = witnesses(source)
        row = next(r for r in rows if r['sourceKey'] == 'B0:N700:S0')
        self.assertEqual(row['bindingStatus'], 'UNQUALIFIED')
        self.assertEqual(row['boundRecordKeys'], ['B0:N700:S0', 'B0:N700:S1'])
        self.assertFalse(row['portQualified'])

    def test_c_duplicate_port_labels_are_unqualified_not_dropped(self):
        source = doc(n(30, 'FLAN', 'F', 1, '0 0 0', CLOS) + n(31, 'RIGID', 'F', 1, '86 0 0'))
        rows = witnesses(source)
        self.assertEqual([(r['sourceKey'], r['bindingStatus'], r['rowKind']) for r in rows],
                         [('B0:N30:S0', 'UNQUALIFIED', 'DECLARATION')])

    def test_d_no_clos_gives_empty_list(self):
        self.assertEqual(witnesses(pipe_flange(75, True)), [])
        self.assertEqual(witnesses(gap_case(False)), [])

    def test_e_order_is_deterministic(self):
        source = doc(n(500, 'FLAN', 'A', 1, '0 0 0', CLOS) + n(-1, 'RIGID', 'A', 2, '100 0 0', CLOS),
                     n(500, 'FLAN', 'B', 1, '5000 0 0', CLOS) + n(-1, 'RIGID', 'B', 2, '5100 0 0'))
        runs = [json.dumps(witnesses(source), sort_keys=True) for _ in range(3)]
        self.assertEqual(len(set(runs)), 1)
        keys = [(r['branchIndex'], r['sourceIndex']) for r in json.loads(runs[0])]
        self.assertEqual(keys, sorted(keys))

    def test_f_source_and_every_pre_existing_payload_field_unchanged(self):
        cases = {'gap': gap_case(), 'gap_open': gap_case(False), 'pipe_flange_75': pipe_flange(75, True)}
        for name, source in cases.items():
            with self.subTest(name):
                snapshot = source.encode('utf-8')
                before_sha = hashlib.sha256(snapshot).hexdigest()
                result = resolve_psi116(source)
                payload = result.findings_payload(ResolverConfig())
                self.assertEqual(sorted(payload), sorted(PRE_CHANGE_KEYS + ['closureBindingWitnesses']))
                self.assertEqual(payload_without_witnesses_sha(source), PRE_CHANGE_PAYLOAD_SHA256[name])
                self.assertEqual(source.encode('utf-8'), snapshot)
                self.assertEqual(result.document.source_text.encode('utf-8'), snapshot)
                self.assertEqual(result.document.source_sha256, before_sha)
                self.assertEqual(hashlib.sha256(source.encode('utf-8')).hexdigest(), before_sha)

    def test_extractor_matches_payload_member(self):
        result = resolve_psi116(gap_case())
        self.assertEqual(closure_binding_witnesses(result.document, ResolverConfig()),
                         result.findings_payload(ResolverConfig())['closureBindingWitnesses'])

    def test_runtime_without_module_reports_evidence_unavailable(self):
        result = resolve_psi116(gap_case())
        with mock.patch.dict(sys.modules, {'psi116_topology_resolver.closure_witness': None}):
            rows = result.findings_payload(ResolverConfig())['closureBindingWitnesses']
        self.assertEqual([r['bindingStatus'] for r in rows], ['EVIDENCE_UNAVAILABLE'])
        self.assertEqual(tuple(rows[0]), ROW_KEYS)
        self.assertIsNone(rows[0]['sourceKey'])
        self.assertIsNone(rows[0]['branchIndex'])


if __name__ == '__main__':
    unittest.main()
