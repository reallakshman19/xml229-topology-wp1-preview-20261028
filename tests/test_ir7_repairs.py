"""IR F1/F2 falsifiers, explicit-authority controls and Owner movement order."""
import sys,unittest
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'converters'))
from psi116_topology_resolver import resolve_psi116,ResolverConfig
from psi116_topology_resolver.connection_ports import PortModel
from psi116_topology_resolver.transaction import apply_topofix_transaction,TransactionPolicy
from test_port_policy import node,doc,pipe_flange,auto

class IR7Repairs(unittest.TestCase):
 def test_unknown_zero_or_unavailable_diameter_does_not_autoclose(self):
  for value in ['', '0', '-1', 'NaN']:
   with self.subTest(value=value):
    source=pipe_flange(12,True).replace('<OutsideDiameter>100</OutsideDiameter>',f'<OutsideDiameter>{value}</OutsideDiameter>',2)
    self.assertIsNone(auto(source)[1])
 def test_missing_cross_branch_port_direction_fails_closed(self):
  r=resolve_psi116(pipe_flange(12,True));m=PortModel(r.document,ResolverConfig())
  a=m.port_by_key['B0:N20:S1'];b=m.port_by_key['B1:N30:S0']
  self.assertTrue(m.compatible(a,b,True))
  self.assertFalse(m.compatible(replace(a,normal=None),b,True))
  self.assertFalse(m.compatible(a,replace(b,normal=None),True))
  self.assertFalse(m.compatible(a,replace(b,normal=(float('nan'),0,0)),True))
 def test_known_wall_bore_mismatch_does_not_autoclose(self):
  source=pipe_flange(12,True).replace('</OutsideDiameter>','</OutsideDiameter><WallThickness>5</WallThickness>')
  source=source.replace('<WallThickness>5</WallThickness>','<WallThickness>10</WallThickness>',1)
  # Change the actual mating PIPE end, rather than only its other port.
  source=source.replace('<NodeNumber>20</NodeNumber>','<NodeNumber>20</NodeNumber>').replace('<Position>100 0 0</Position><OutsideDiameter>100</OutsideDiameter><WallThickness>5', '<Position>100 0 0</Position><OutsideDiameter>100</OutsideDiameter><WallThickness>10')
  self.assertIsNone(auto(source)[1])
 def test_explicit_matching_branch_junction_identity_is_alternative_authority(self):
  source=doc(node(-1,'TEE','T',1,'0 0 0')+node(50,'TEE','T',0,'100 0 0')+
   node(-1,'TEE','T',2,'200 0 0')+node(-1,'TEE','T',3,'100 100 0'),
   node(50,'BRAN','B',1,'100 0 25','<ConnectionType>TEE</ConnectionType>'))
  source=source.replace('<OutsideDiameter>100</OutsideDiameter>','')
  _,t=auto(source);self.assertIsNotNone(t);self.assertTrue(t.committed,t.reject_reasons)
  # A different label is not the same explicit connection authority.
  source=source.replace('<NodeNumber>50</NodeNumber><ComponentType>BRAN','<NodeNumber>60</NodeNumber><ComponentType>BRAN')
  self.assertIsNone(auto(source)[1])
 def test_unlinked_clos_neighbour_cannot_close_a_different_port(self):
  source=doc(node(-1,'BRAN','CLOSED-OWNER',1,'0 0 0','<ConnectionType>CLOS</ConnectionType>')+
    node(30,'PIPE','OTHER-OWNER',1,'0.4 0 0')+node(40,'PIPE','OTHER-OWNER',2,'100 0 0'))
  r=resolve_psi116(source);m=PortModel(r.document,ResolverConfig())
  self.assertFalse(m.closed(m.port_by_key['B0:N30:S1']))
  self.assertFalse(any(x['code']=='DECLARED_CLOSED_END' and 'B0:N30:S1' in x['node_keys'] for x in r.connection_resolutions))
  self.assertTrue(any(f.code=='BRANCH_END_UNVERIFIED' and 'B0:N30:S1' in f.node_keys for f in r.findings))
 def test_owner_and_actual_boundary_clos_controls_remain_bound(self):
  source=doc(node(-1,'BRAN','B',1,'0 0 0','<ConnectionType>CLOS</ConnectionType>')+
    node(10,'FBLI','F',1,'0 0 0')+node(-1,'FBLI','F',2,'32 0 0'))
  r=resolve_psi116(source);m=PortModel(r.document,ResolverConfig())
  self.assertTrue(m.closed(m.port_by_key['B0:N10:S1']))
  self.assertTrue(any(x['code']=='DECLARED_CLOSED_END' for x in r.connection_resolutions))
 def test_movement_order_pipe_flange_valve_bend(self):
  def body(kind,ref,num,a,b):
   s=node(num,kind,ref,1,f'{a} 0 0')+node(num+10,kind,ref,2,f'{b} 0 0')
   if kind=='ELBO':s+=node(num+5,kind,ref,0,f'{(a+b)/2} 0 0')
   return s
  for left,right,expected in [('PIPE','FLAN','PIPE'),('FLAN','VALV','FLAN'),('VALV','ELBO','VALV'),('ELBO','PIPE','PIPE')]:
   with self.subTest(left=left,right=right):
    r,t=auto(doc(body(left,'A',10,0,100)+body(right,'B',30,125,225)))
    self.assertIsNotNone(t);self.assertTrue(t.committed,t.reject_reasons)
    action=next(a for a in r.fix_actions if a.disposition=='CLOSE_PORT_CONNECTION')
    m=PortModel(r.document,ResolverConfig());port=m.port_by_key[action.proposed_changes[0]['movePortKey']]
    self.assertEqual(m.kind(port.group),expected)
if __name__=='__main__':unittest.main()
