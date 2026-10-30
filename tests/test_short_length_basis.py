"""S1: chord distance cannot authorize a curved component's physical length."""
import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'converters'))
from psi116_topology_resolver import resolve_psi116,ResolverConfig
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import apply_topofix_transaction,TransactionPolicy
from psi116_topology_resolver.lineage import build_topofix_source_lineage,verify_topofix_pre_final
from test_port_policy import node,doc
from test_short_elements import fixture,apply


def candidate(source):
 r=resolve_psi116(source)
 return r,next(x for x in short_elements(r.document,ResolverConfig()) if x['componentRefNo']=='SHORT')

def elbow(kind='ELBO'):
 return doc(node(10,'PIPE','P',1,'100 0 0')+node(20,'PIPE','P',2,'4.1 0 0')+
  node(-1,kind,'SHORT',1,'4.1 0 0','<BendRadius>4.1</BendRadius><AlphaAngle>90</AlphaAngle>')+
  node(-1,kind,'SHORT',0,'0 0 0')+node(30,'RIGID','SHORT',2,'0 4.1 0')+
  node(-1,'FLAN','F',1,'0 4.1 0')+node(40,'RIGID','F',2,'0 90.1 0'))


class ShortLengthBasis(unittest.TestCase):
 def test_quarter_circle_chord_under_6_does_not_authorize_arc_over_6(self):
  self.assertLess(4.1*math.sqrt(2),6);self.assertGreater(4.1*math.pi/2,6)
  for kind in ['ELBO','BEND','ELBOW']:
   with self.subTest(kind=kind):
    r,row=candidate(elbow(kind))
    self.assertAlmostEqual(row['measuredSpanMm'],4.1*math.sqrt(2))
    self.assertFalse(row['eligible']);self.assertEqual(row['lengthBasis'],'UNQUALIFIED_CURVED_OR_JUNCTION')
    # Supplying a fabricated length basis does not bypass Python's source rederivation.
    request={k:row[k] for k in ['id','sourceSha256','nodeKeys']}
    request['lengthBasis']='SOURCE_STRAIGHT_TWO_PORT_SPAN'
    with self.assertRaisesRegex(ValueError,'NOT_QUALIFIED'):
     apply_topofix_transaction(r,policy=TransactionPolicy(selected_action_ids=(row['id'],),short_element_requests=(request,)))
 def test_two_visible_junction_ports_do_not_prove_a_straight_component(self):
  for kind in ['TEE','OLET']:
   with self.subTest(kind=kind):
    _,row=candidate(fixture(3,kind));self.assertFalse(row['eligible'])
    self.assertEqual(row['lengthBasis'],'UNQUALIFIED_CURVED_OR_JUNCTION')
 def test_zero_filled_straight_gasket_keeps_the_inclusive_6_mm_boundary(self):
  zero='<BendRadius>0</BendRadius><AlphaAngle>0</AlphaAngle>'
  source=fixture(6).replace('</Node>',zero+'</Node>')
  _,row=candidate(source);self.assertTrue(row['eligible']);self.assertEqual(row['lengthMm'],6)
  self.assertEqual(row['lengthBasis'],'SOURCE_STRAIGHT_TWO_PORT_SPAN');self.assertTrue(apply(source).committed)
  r=resolve_psi116(fixture(6.001).replace('</Node>',zero+'</Node>'))
  self.assertFalse(any(x['componentRefNo']=='SHORT' for x in short_elements(r.document,ResolverConfig())))
 def test_nonzero_invalid_and_nonfinite_curvature_fields_fail_closed(self):
  for field,value in [('BendRadius','4.1'),('AlphaAngle','90'),('BendRadius','-1'),('AlphaAngle','NaN'),('BendRadius','invalid')]:
   with self.subTest(field=field,value=value):
    source=fixture(extra=f'<{field}>{value}</{field}>');_,row=candidate(source)
    self.assertFalse(row['eligible']);self.assertEqual(row['lengthBasis'],'UNQUALIFIED_CURVATURE_METADATA')
    with self.assertRaisesRegex(ValueError,'NOT_QUALIFIED'):apply(source)
 def test_all_straight_owner_records_must_lie_on_the_port_segment(self):
  for point in ['101 2 0','99.5 0 0']:
   with self.subTest(point=point):
    source=fixture(kind='PIPE');end=node(30,'RIGID','SHORT',2,'103 0 0')
    source=source.replace(end,node(-1,'PIPE','SHORT',0,point)+end)
    _,row=candidate(source);self.assertLess(row['measuredSpanMm'],6)
    self.assertFalse(row['eligible']);self.assertEqual(row['lengthBasis'],'UNQUALIFIED_NONSTRAIGHT_GEOMETRY')
 def test_length_basis_is_in_validation_and_survives_full_pre_final_replay(self):
  source=fixture(extra='<BendRadius>0</BendRadius><AlphaAngle>0</AlphaAngle>');t=apply(source)
  self.assertTrue(t.committed,t.reject_reasons)
  check=next(c for c in t.checks if c.code=='SHORT_ELEMENT_LENGTH_BASIS_QUALIFIED')
  self.assertTrue(check.passed);self.assertEqual(check.details['lengthBasis'],'SOURCE_STRAIGHT_TWO_PORT_SPAN')
  lineage=build_topofix_source_lineage(t)
  verify_topofix_pre_final(source,t.fixed_xml,t.transaction_payload(),t.validation_payload(),lineage,reviewed_action_ids=t.policy.selected_action_ids)

if __name__=='__main__':unittest.main()
