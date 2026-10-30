"""F4: declaration, physical owner and source identity must agree."""
import sys,unittest
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'converters'))
from psi116_topology_resolver import resolve_psi116,ResolverConfig
from psi116_topology_resolver.connection_ports import PortModel
from psi116_topology_resolver.transaction import apply_topofix_transaction,TransactionPolicy
from test_port_policy import node,doc


def fixture(declared='TEE',owner='TEE',number=50,offset=25):
 return doc(node(-1,owner,'J',1,'0 0 0')+node(50,owner,'J',0,'100 0 0')+
  node(-1,owner,'J',2,'200 0 0')+node(-1,owner,'J',3,'100 100 0'),
  node(number,'BRAN','B',1,f'100 0 {offset}',f'<ConnectionType>{declared}</ConnectionType>'))


class JunctionAuthority(unittest.TestCase):
 def test_exact_kind_and_positive_identity_matrix_is_symmetric(self):
  for declared,owner,number,expected in [('TEE','TEE',50,True),('OLET','OLET',50,True),
    ('TEE','OLET',50,False),('OLET','TEE',50,False),('TEE','TEE',60,False)]:
   with self.subTest(declared=declared,owner=owner,number=number):
    r=resolve_psi116(fixture(declared,owner,number));m=PortModel(r.document,ResolverConfig())
    a=m.port_by_key[f'B1:N{number}:S0'];b=m.port_by_key['B0:N50:S1']
    self.assertEqual(m.compatible(a,b,True),expected)
    self.assertEqual(m.compatible(b,a,True),expected)
 def test_matching_declared_owner_still_closes_and_resolves(self):
  for kind in ['TEE','OLET']:
   with self.subTest(kind=kind):
    r=resolve_psi116(fixture(kind,kind).replace('<OutsideDiameter>100</OutsideDiameter>',''))
    a=next(a for a in r.fix_actions if a.disposition=='CLOSE_PORT_CONNECTION')
    t=apply_topofix_transaction(r,policy=TransactionPolicy(selected_action_ids=(a.action_id,)))
    self.assertTrue(t.committed,t.reject_reasons)
    self.assertEqual(t.after_result.document.branches[1].nodes[0].position.as_list(),[100.,0.,0.])
    self.assertTrue(any('B1:N50:S0' in x['node_keys'] for x in t.after_result.connection_resolutions))
 def test_mismatch_stays_visible_even_at_shared_xyz(self):
  for declared,owner in [('TEE','OLET'),('OLET','TEE')]:
   for offset in [0,25]:
    with self.subTest(declared=declared,owner=owner,offset=offset):
     r=resolve_psi116(fixture(declared,owner,offset=offset));key='B1:N50:S0'
     finding=next(f for f in r.findings if f.code=='CONNECTION_DECLARATION_CONFLICT' and key in f.node_keys)
     self.assertIn('B0:N50:S1',finding.node_keys)
     self.assertFalse(finding.details['autofixAuthorized'])
     self.assertEqual(finding.details['connectionAuthority'],'CONFLICTING_JUNCTION_DECLARATIONS')
     self.assertIn('re-export and rerun',finding.message)
     self.assertFalse(any(key in x['node_keys'] for x in r.connection_resolutions))
     self.assertFalse(any(a.disposition=='CLOSE_PORT_CONNECTION' for a in r.fix_actions))
 def test_apply_rederives_authority_and_rejects_forged_previous_action(self):
  for declared,owner in [('TEE','OLET'),('OLET','TEE')]:
   with self.subTest(declared=declared,owner=owner):
    valid=resolve_psi116(fixture(owner,owner))
    a=next(a for a in valid.fix_actions if a.disposition=='CLOSE_PORT_CONNECTION')
    invalid=resolve_psi116(fixture(declared,owner))
    a=replace(a,finding_ids=(next(f.finding_id for f in invalid.findings if f.code=='CONNECTION_DECLARATION_CONFLICT'),))
    forged=replace(invalid,fix_actions=(a,))
    t=apply_topofix_transaction(forged,policy=TransactionPolicy(selected_action_ids=(a.action_id,)))
    self.assertFalse(t.committed);self.assertIsNone(t.fixed_xml)
    self.assertTrue(t.reject_reasons)

if __name__=='__main__':unittest.main()
