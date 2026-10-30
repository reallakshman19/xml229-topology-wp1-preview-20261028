import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'converters'))
from psi116_topology_resolver import resolve_psi116,ResolverConfig
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import apply_topofix_transaction,TransactionPolicy
from psi116_topology_resolver.lineage import build_topofix_source_lineage,verify_topofix_pre_final
from test_port_policy import node,doc

def fixture(length=3,kind='GASK',extra=''):
 return doc(node(10,'PIPE','P',1,'0 0 0')+node(20,'PIPE','P',2,'100 0 0')+
  node(-1,kind,'SHORT',1,'100 0 0',extra)+node(30,'RIGID','SHORT',2,f'{100+length} 0 0')+
  node(-1,'FLAN','F',1,f'{100+length} 0 0')+node(40,'RIGID','F',2,f'{186+length} 0 0'))
def apply(source,change=None):
 r=resolve_psi116(source);row=next(x for x in short_elements(r.document,ResolverConfig()) if x['componentRefNo']=='SHORT')
 request={k:row[k] for k in ['id','sourceSha256','nodeKeys']}
 if change:change(request)
 return apply_topofix_transaction(r,policy=TransactionPolicy(selected_action_ids=(row['id'],),short_element_requests=(request,)))

class ShortElements(unittest.TestCase):
 def test_gasket_and_rigid_endpoint_removed_then_pipe_closes_to_retained_flange(self):
  source=fixture();t=apply(source);self.assertTrue(t.committed,t.reject_reasons)
  ns=t.after_result.document.branches[0].nodes
  self.assertEqual(len(ns),4);self.assertEqual([n.component_ref_no for n in ns],['P','P','F','F'])
  self.assertEqual(ns[1].position.x,103);self.assertEqual(ns[2].position.x,103)
  self.assertEqual(ns[3].position.x-ns[2].position.x,86)
  self.assertEqual(sum(o.operation=='REMOVE_SELECTED_SHORT_ELEMENT_RECORD' for o in t.operations),2)
  self.assertEqual(next(o.retained_node_key for o in t.operations if o.operation=='CLOSE_COMPONENT_PORT'),'B0:N-1:S4')
  l=build_topofix_source_lineage(t);self.assertEqual(l['counts']['removedSelectedShortElementOccurrences'],2)
  verify_topofix_pre_final(source,t.fixed_xml,t.transaction_payload(),t.validation_payload(),l,reviewed_action_ids=t.policy.selected_action_ids)
 def test_exactly_6_mm_is_included_and_other_two_port_types_can_be_selected(self):
  for kind in ['GASK','FLAN','VALV','PIPE']:
   with self.subTest(kind=kind):self.assertTrue(apply(fixture(6,kind)).committed)
 def test_over_6_mm_is_not_offered(self):
  r=resolve_psi116(fixture(6.001));self.assertFalse(any(x['componentRefNo']=='SHORT' for x in short_elements(r.document,ResolverConfig())))
 def test_restrained_component_and_unknown_mating_metadata_do_not_qualify(self):
  r=resolve_psi116(fixture(extra='<Restraint>X</Restraint>'))
  self.assertFalse(next(x for x in short_elements(r.document,ResolverConfig()) if x['componentRefNo']=='SHORT')['eligible'])
  source=fixture().replace('<OutsideDiameter>100</OutsideDiameter>','')
  with self.assertRaisesRegex(ValueError,'NOT_QUALIFIED'):apply(source)
 def test_stale_selection_or_partial_owner_request_rejected(self):
  for change in [lambda r:r.update(sourceSha256='stale'),lambda r:r.update(nodeKeys=r['nodeKeys'][:1])]:
   with self.assertRaises(ValueError):apply(fixture(),change)
 def test_selected_weight_is_accounted_instead_of_silently_preserved(self):
  t=apply(fixture(extra='<Weight>2.5</Weight>'));self.assertTrue(t.committed,t.reject_reasons)
  c=next(c for c in t.checks if c.code=='WEIGHT_REMOVAL_ACCOUNTED');self.assertEqual(c.details['selectedWeightRemoved'],2.5)
 def test_failed_reconnection_produces_no_drop_output(self):
  # Both remaining owners are constrained; preview can qualify their interface, Apply must stay atomic.
  source=fixture().replace('<ComponentType>PIPE</ComponentType>','<ComponentType>PIPE</ComponentType><Restraint>X</Restraint>')
  source=source.replace('<ComponentType>FLAN</ComponentType>','<ComponentType>FLAN</ComponentType><Restraint>X</Restraint>')
  with self.assertRaisesRegex(ValueError,'RECONNECTION'):apply(source)
 def test_hidden_owner_record_prevents_partial_component_removal(self):
  source=fixture().replace('</Branch>','<Node><NodeNumber>90</NodeNumber><ComponentType>GASK</ComponentType><ComponentRefNo>SHORT</ComponentRefNo></Node></Branch>')
  with self.assertRaisesRegex(ValueError,'NOT_QUALIFIED'):apply(source)
 def test_shared_node_identity_without_position_is_still_protected(self):
  source=fixture().replace('</Branch>','<Node><NodeNumber>30</NodeNumber><ComponentType>ATTA</ComponentType><ComponentRefNo>SUPPORT</ComponentRefNo></Node></Branch>')
  with self.assertRaisesRegex(ValueError,'NOT_QUALIFIED'):apply(source)
if __name__=='__main__':unittest.main()
