"""Independent literal expectations for the Owner's inclusive 25 mm port policy."""
import sys,unittest
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'converters'))
from psi116_topology_resolver import resolve_psi116
from psi116_topology_resolver.transaction import apply_topofix_transaction,TransactionPolicy
from psi116_topology_resolver.lineage import build_topofix_source_lineage,verify_topofix_pre_final


def node(n,kind,ref,end,xyz,extra=''):
 return f'<Node><NodeNumber>{n}</NodeNumber><ComponentType>{kind}</ComponentType><ComponentRefNo>{ref}</ComponentRefNo><Endpoint>{end}</Endpoint><Position>{xyz}</Position><OutsideDiameter>100</OutsideDiameter>{extra}</Node>'
def doc(*branches):
 return '<PipeStressExport>'+''.join('<Branch><Branchname>TEST-'+str(i)+'</Branchname>'+b+'</Branch>' for i,b in enumerate(branches))+'</PipeStressExport>'
def pipe_flange(gap=25,cross=False):
 pipe=node(10,'PIPE','P',1,'0 0 0')+node(20,'PIPE','P',2,'100 0 0')
 flange=node(30,'FLAN','F',1,f'{100+gap} 0 0')+node(-1,'RIGID','F',2,f'{186+gap} 0 0')
 return doc(pipe,flange) if cross else doc(pipe+flange)
def auto(source):
 r=resolve_psi116(source);acts=[a for a in r.fix_actions if a.disposition=='CLOSE_PORT_CONNECTION']
 if not acts:return r,None
 t=apply_topofix_transaction(r,policy=TransactionPolicy(selected_action_ids=tuple(a.action_id for a in acts)))
 return r,t

class PortPolicy(unittest.TestCase):
 def test_exact_25_auto_closes_pipe_to_flange_and_preserves_all_flange_fields(self):
  source=pipe_flange();r,t=auto(source)
  self.assertIsNotNone(t);self.assertTrue(t.committed,t.reject_reasons)
  ns=t.after_result.document.branches[0].nodes
  self.assertEqual(ns[1].position.as_list(),[125.,0.,0.]);self.assertEqual(ns[1].node_number,30)
  self.assertEqual(ns[2].position.as_list(),[125.,0.,0.]);self.assertEqual(ns[3].position.as_list(),[211.,0.,0.])
  self.assertEqual(ns[3].node_number,-1);self.assertEqual(len(ns),4)
  lineage=build_topofix_source_lineage(t)
  verify_topofix_pre_final(source,t.fixed_xml,t.transaction_payload(),t.validation_payload(),lineage,reviewed_action_ids=t.policy.selected_action_ids)
  self.assertTrue(all(c.passed for c in t.checks))
 def test_25_0001_is_outside_policy(self):
  self.assertIsNone(auto(pipe_flange(25.0001))[1])
 def test_cross_branch_fitting_port_is_automatic_without_per_joint_confirmation(self):
  _,t=auto(pipe_flange(12,True));self.assertIsNotNone(t);self.assertTrue(t.committed,t.reject_reasons)
 def test_finite_fitting_and_contacted_gasket_translate_together_at_restrained_pipe(self):
  source=doc(node(10,'PIPE','P',1,'0 0 0')+node(20,'PIPE','P',2,'100 0 0','<Restraint>X</Restraint>'),
   node(30,'FLAN','F',1,'125 0 0')+node(-1,'RIGID','F',2,'211 0 0')+
   node(-1,'GASK','G',1,'211 0 0')+node(40,'RIGID','G',2,'214 0 0'))
  _,t=auto(source);self.assertIsNotNone(t);self.assertTrue(t.committed,t.reject_reasons)
  ns=t.after_result.document.branches[1].nodes
  self.assertEqual([n.position.x for n in ns],[100.,186.,186.,189.])
  self.assertEqual(ns[0].node_number,20);self.assertEqual(ns[1].node_number,-1)
 def test_a_finite_3_mm_gasket_is_never_a_gap(self):
  source=doc(node(10,'GASK','G',1,'0 0 0')+node(-1,'GASK','G',2,'3 0 0')+
   node(-1,'FLAN','F',1,'3 0 0')+node(20,'RIGID','F',2,'89 0 0'))
  self.assertIsNone(auto(source)[1])
 def test_explicit_closure_has_source_evidence_and_no_open_end_finding(self):
  source=doc(node(-1,'BRAN','B',1,'0 0 0','<ConnectionType>CLOS</ConnectionType>')+
   node(10,'FBLI','BLIND',1,'0 0 0')+node(-1,'FBLI','BLIND',2,'32.2 0 0'))
  r=resolve_psi116(source)
  self.assertTrue(any(x['code']=='DECLARED_CLOSED_END' and 'B0:N-1:S0' in x['node_keys'] for x in r.connection_resolutions))
  self.assertFalse(any(f.code=='BRANCH_END_UNVERIFIED' and 10 in f.node_numbers for f in r.findings))
 def test_closure_conflicting_with_shared_connection_is_not_auto_resolved(self):
  source=doc(node(10,'BRAN','B',1,'0 0 0','<ConnectionType>CLOS</ConnectionType>'),
             node(10,'BRAN','C',1,'0 0 0'))
  r=resolve_psi116(source)
  self.assertTrue(any(f.code=='CONNECTION_DECLARATION_CONFLICT' for f in r.findings))
  self.assertFalse(any(x['code']=='EXISTING_CONNECTION' for x in r.connection_resolutions))
  self.assertFalse(any(a.disposition=='CLOSE_PORT_CONNECTION' for a in r.fix_actions))
 def test_branch_stub_resolves_to_parent_tee_inside_other_branch(self):
  source=doc(node(-1,'TEE','T',1,'0 0 0')+node(50,'TEE','T',0,'100 0 0')+
   node(-1,'TEE','T',2,'200 0 0')+node(-1,'TEE','T',3,'100 100 0'),
   node(50,'BRAN','B',1,'100 0 0','<ConnectionType>TEE</ConnectionType>'))
  r=resolve_psi116(source)
  self.assertTrue(any(x['code']=='EXISTING_CONNECTION' and 'B0:N50:S1' in x['node_keys'] for x in r.connection_resolutions))
  self.assertFalse(any(f.code in {'BRANCH_END_UNVERIFIED','JUNCTION_OWNER_INFERRED_FROM_PORT_SET'} and 'B1:N50:S0' in f.node_keys for f in r.findings))
 def test_declared_branch_to_tee_owner_closes_same_identity_25_mm_offset(self):
  source=doc(node(-1,'TEE','T',1,'0 0 0')+node(50,'TEE','T',0,'100 0 0')+
   node(-1,'TEE','T',2,'200 0 0')+node(-1,'TEE','T',3,'100 100 0'),
   node(50,'BRAN','B',1,'100 0 25','<ConnectionType>TEE</ConnectionType>'))
  r,t=auto(source);self.assertIsNotNone(t);self.assertTrue(t.committed,t.reject_reasons)
  self.assertEqual(t.after_result.document.branches[1].nodes[0].position.as_list(),[100.,0.,0.])
  self.assertTrue(any(x['code']=='EXISTING_CONNECTION' for x in t.after_result.connection_resolutions))
 def test_zero_mm_physical_interface_with_different_numbers_is_automatic(self):
  _,t=auto(pipe_flange(0));self.assertIsNotNone(t);self.assertTrue(t.committed,t.reject_reasons)
 def test_competing_targets_do_not_choose_nearest_arbitrarily(self):
  source=pipe_flange(10,True).replace('</PipeStressExport>','<Branch><Branchname>C</Branchname>'+node(60,'FLAN','F2',1,'111 1 0')+node(-1,'RIGID','F2',2,'197 1 0')+'</Branch></PipeStressExport>')
  r,t=auto(source);self.assertIsNone(t)
 def test_bore_mismatch_requires_review(self):
  source=pipe_flange().replace('<ComponentType>FLAN</ComponentType>','<ComponentType>FLAN</ComponentType>').replace('<OutsideDiameter>100</OutsideDiameter></Node><Node><NodeNumber>-1','<OutsideDiameter>150</OutsideDiameter></Node><Node><NodeNumber>-1')
  self.assertIsNone(auto(source)[1])
 def test_forged_operation_group_is_rejected_atomically(self):
  r=resolve_psi116(pipe_flange());a=next(a for a in r.fix_actions if a.disposition=='CLOSE_PORT_CONNECTION')
  change={**a.proposed_changes[0],'moveKeys':['B0:N10:S0']}
  forged=replace(a,proposed_changes=(change,));r=replace(r,fix_actions=tuple(forged if x.action_id==a.action_id else x for x in r.fix_actions))
  t=apply_topofix_transaction(r,policy=TransactionPolicy(selected_action_ids=(a.action_id,)))
  self.assertFalse(t.committed);self.assertIsNone(t.fixed_xml)
if __name__=='__main__':unittest.main()
