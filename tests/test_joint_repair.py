"""Executable gap/overlap closure with source custody and full lineage replay."""
import sys
import unittest
from pathlib import Path
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'converters'))
from psi116_topology_resolver import resolve_psi116
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.joint_repair import repair_action_id
from psi116_topology_resolver.lineage import build_topofix_source_lineage, verify_topofix_pre_final


def fixture(join=124.9, extra=''):
    def node(num, ref, end, x, more=''):
        return f'<Node><NodeNumber>{num}</NodeNumber><ComponentType>PIPE</ComponentType><ComponentRefNo>{ref}</ComponentRefNo><Endpoint>{end}</Endpoint><Position>{x} 0 0</Position><WallThickness>3.5</WallThickness>{more}</Node>'
    return '<PipeStressExport><Branch><Branchname>A</Branchname>'+''.join([
        node(10,'PIPE-A',1,0),node(20,'PIPE-A',2,100),
        node(30,'PIPE-B',1,join,extra),node(40,'PIPE-B',2,200)])+'</Branch></PipeStressExport>'


def request_for(result):
    f=next(f for f in result.findings if f.code in {'PORT_CONNECTION_WITHIN_TOLERANCE','NEAR_MISS_PIPE_JOINT','COINCIDENT_NODE_ALIAS_CANDIDATE','COINCIDENT_NODE_IDENTITY_AMBIGUOUS'})
    return {'sourceSha256':result.document.source_sha256,'findingId':f.finding_id,
            'moveKey':'B0:N30:S2','targetKey':'B0:N20:S1','evidence':'Confirmed intended joint: TEST-DRAWING-01'}


def apply(source, mutate=None):
    result=resolve_psi116(source)
    req=request_for(result)
    if mutate: mutate(req)
    return apply_topofix_transaction(result,policy=TransactionPolicy(
        selected_action_ids=(repair_action_id(req),),joint_repairs=(req,)))


class JointRepair(unittest.TestCase):
    def test_24_9_mm_closure_preserves_both_components_and_replays_lineage(self):
        source=fixture()
        txn=apply(source)
        self.assertTrue(txn.committed, txn.reject_reasons)
        self.assertTrue(all(c.passed for c in txn.checks))
        self.assertIn('CONFIRMED_JOINT_CLOSED',[c.code for c in txn.checks])
        nodes=txn.after_result.document.branches[0].nodes
        self.assertEqual(len(nodes),4)
        self.assertEqual(nodes[1].node_number,nodes[2].node_number)
        self.assertEqual(nodes[1].position,nodes[2].position)
        self.assertEqual([n.component_ref_no for n in nodes],['PIPE-A','PIPE-A','PIPE-B','PIPE-B'])
        self.assertFalse(any(f.code=='NEAR_MISS_PIPE_JOINT' for f in txn.after_result.findings))
        lineage=build_topofix_source_lineage(txn)
        proof=verify_topofix_pre_final(source,txn.fixed_xml,txn.transaction_payload(),
            txn.validation_payload(),lineage,reviewed_action_ids=txn.policy.selected_action_ids)
        self.assertFalse(proof['nativeCiiReleaseAuthorized'])
        self.assertEqual(txn.operations[0].before['Position'],'124.9 0 0')
        self.assertEqual(txn.operations[0].after['Position'],'100 0 0')

    def test_2_mm_overlap_closes_by_moving_join_without_deleting_pipe(self):
        txn=apply(fixture(98))
        self.assertTrue(txn.committed, txn.reject_reasons)
        self.assertFalse(any(f.code=='COLLINEAR_ROUTE_OVERLAP' for f in txn.after_result.findings))
        self.assertEqual(len(txn.after_result.document.branches[0].nodes),4)

    def test_coincident_two_port_joint_gets_confirmed_identity(self):
        txn=apply(fixture(100))
        self.assertTrue(txn.committed, txn.reject_reasons)
        self.assertEqual(txn.after_result.document.branches[0].nodes[2].node_number,20)

    def test_exact_25_mm_limit_included(self):
        self.assertTrue(apply(fixture(125)).committed)

    def test_stale_source_and_missing_confirmation_rejected(self):
        for change,reason in [(lambda r:r.update(sourceSha256='stale'),'SOURCE_DRIFT'),
                              (lambda r:r.update(evidence=''),'evidence|reference')]:
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                apply(fixture(),change)

    def test_forged_pair_and_restrained_port_rejected(self):
        with self.assertRaisesRegex(ValueError,'two source-qualified'):
            apply(fixture(),lambda r:r.update(targetKey='B0:N40:S3'))
        with self.assertRaisesRegex(ValueError,'unrestrained'):
            apply(fixture(extra='<Restraint>X</Restraint>'))

    def test_duplicate_node_identity_does_not_allow_partial_group_move(self):
        source=fixture().replace('<NodeNumber>40</NodeNumber>','<NodeNumber>30</NodeNumber>')
        with self.assertRaisesRegex(ValueError,'Shared NodeNumber'):
            apply(source)

    def test_automatic_plan_never_invents_connection_confirmation(self):
        result=resolve_psi116(fixture())
        self.assertFalse(any(a.disposition=='CLOSE_CONFIRMED_PIPE_JOINT' for a in result.fix_actions))
        self.assertIn('NEAR_MISS_PIPE_JOINT',[f.code for f in result.findings])

if __name__=='__main__': unittest.main()
