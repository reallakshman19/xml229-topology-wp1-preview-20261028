"""Explicit engineering expectations for a selected >25 mm second pass."""
import copy
import unittest
from dataclasses import replace
from test_port_policy import pipe_flange, doc, node
from psi116_topology_resolver import resolve_psi116, ResolverConfig
from psi116_topology_resolver.manual_connections import preview_connection
from psi116_topology_resolver.joint_repair import repair_action_id
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.lineage import build_topofix_source_lineage, verify_topofix_pre_final


def selection(result):
    finding = next(f for f in result.findings if f.code == 'BRANCH_END_UNVERIFIED'
                   and 'B0:N20:S1' in f.node_keys)
    return {'mode':'SECOND_PASS', 'sourceSha256':result.document.source_sha256,
            'findingId':finding.finding_id, 'portKeys':['B0:N20:S1','B1:N30:S0']}


def approval(result):
    request = selection(result)
    preview = preview_connection(result, request, ResolverConfig())
    repair = preview['repair']
    return {**request, 'moveKey':repair['movePortKey'], 'targetKey':repair['targetPortKey'],
            'approvedRepair':repair, 'confirmed':True, 'evidence':'DESIGN-TEST-02 confirms these two ports'}


def apply(result, request):
    return apply_topofix_transaction(result, policy=TransactionPolicy(
        selected_action_ids=(repair_action_id(request),), joint_repairs=(request,)))


class ManualConnections(unittest.TestCase):
    def test_75_mm_preview_does_not_mutate_or_enter_automatic_plan(self):
        source = pipe_flange(75, True)
        result = resolve_psi116(source)
        before = result.document.source_text
        p = preview_connection(result, selection(result), ResolverConfig())
        self.assertEqual(p['repair']['distanceMm'], 75)
        self.assertEqual(p['repair']['movePortKey'], 'B0:N20:S1')
        self.assertEqual(p['repair']['delta'], [75.,0.,0.])
        self.assertEqual(p['changes'][0]['after']['Position'], [175.,0.,0.])
        self.assertEqual(result.document.source_text, before)
        self.assertFalse(any(a.disposition.startswith('CLOSE_') for a in result.fix_actions))

    def test_selected_75_mm_pipe_to_flange_closes_with_full_receipt_and_lineage(self):
        source = pipe_flange(75, True)
        result = resolve_psi116(source)
        request = approval(result)
        txn = apply(result, request)
        self.assertTrue(txn.committed, txn.reject_reasons)
        self.assertTrue(all(c.passed for c in txn.checks))
        branches = txn.after_result.document.branches
        self.assertEqual(branches[0].nodes[1].position.as_list(), [175.,0.,0.])
        self.assertEqual(branches[0].nodes[1].node_number, 30)
        self.assertEqual([n.position.x for n in branches[1].nodes], [175.,261.])
        self.assertEqual(sum(len(b.nodes) for b in branches), 4)
        self.assertEqual(txn.transaction_payload()['policy']['joint_repairs'][0], request)
        proof = verify_topofix_pre_final(source, txn.fixed_xml, txn.transaction_payload(),
            txn.validation_payload(), build_topofix_source_lineage(txn),
            reviewed_action_ids=txn.policy.selected_action_ids)
        self.assertFalse(proof['nativeCiiReleaseAuthorized'])

    def test_exact_boundary_never_increases_automatic_tolerance(self):
        for gap in (25.001,75,500):
            result = resolve_psi116(pipe_flange(gap,True))
            self.assertFalse(any(a.disposition=='CLOSE_PORT_CONNECTION' for a in result.fix_actions))
            self.assertTrue(apply(result, approval(result)).committed)

    def test_stale_missing_or_tampered_approval_fails_closed(self):
        result = resolve_psi116(pipe_flange(75,True))
        for change in (lambda r:r.update(sourceSha256='stale'),
                       lambda r:r.update(confirmed=False), lambda r:r.update(evidence=''),
                       lambda r:r['approvedRepair'].update(distanceMm=25),
                       lambda r:r['approvedRepair'].update(moveKeys=['B0:N10:S0']),
                       lambda r:r.update(targetKey='B1:N-1:S1')):
            request = copy.deepcopy(approval(result)); change(request)
            with self.assertRaises(ValueError): apply(result,request)

    def test_arbitrary_nonwitness_pair_or_unqualified_port_rejected(self):
        result = resolve_psi116(pipe_flange(75,True)); request = selection(result)
        for keys in (['B0:N10:S0','B1:N-1:S1'], ['B0:N20:S1','missing'], ['B0:N20:S1']*2):
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                preview_connection(result,{**request,'portKeys':keys},ResolverConfig())

    def test_unknown_diameter_or_facing_and_owned_closure_cannot_be_overridden(self):
        for source in (pipe_flange(75,True).replace('<OutsideDiameter>100</OutsideDiameter>',''),
            pipe_flange(75,True).replace('261 0 0','175 0 0'),
            pipe_flange(75,True).replace('<NodeNumber>30</NodeNumber>','<NodeNumber>30</NodeNumber><ConnectionType>CLOS</ConnectionType>')):
            result=resolve_psi116(source)
            with self.assertRaises(ValueError):preview_connection(result,selection(result),ResolverConfig())

    def test_two_restrained_owners_cannot_be_forced(self):
        source = pipe_flange(75,True).replace('<NodeNumber>20</NodeNumber>',
            '<NodeNumber>20</NodeNumber><Restraint>X</Restraint>').replace('<NodeNumber>30</NodeNumber>',
            '<NodeNumber>30</NodeNumber><Restraint>X</Restraint>')
        result=resolve_psi116(source)
        with self.assertRaisesRegex(ValueError,'MOVE_GROUP'):preview_connection(result,selection(result),ResolverConfig())

    def test_forged_manual_action_without_policy_approval_cannot_apply(self):
        from psi116_topology_resolver.joint_repair import with_confirmed_joint_repairs
        result = resolve_psi116(pipe_flange(75,True)); request=approval(result)
        forged=with_confirmed_joint_repairs(result,(request,),ResolverConfig())
        txn=apply_topofix_transaction(forged,policy=TransactionPolicy(selected_action_ids=(repair_action_id(request),)))
        self.assertFalse(txn.committed)
        self.assertIsNone(txn.fixed_xml)

if __name__=='__main__':unittest.main()
