"""Exact port-closure candidate parity versus independent unindexed reference."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'converters'))
from psi116_topology_resolver import ResolverConfig
from psi116_topology_resolver.parser import read_psi116_xml
from psi116_topology_resolver.connection_ports import PortModel, SUPPORTED, FINITE
from test_port_policy import pipe_flange, node, doc
from test_short_elements import fixture

class UnindexedReference(PortModel):
    def moving_group(self,p,target):
        delta=tuple(b-a for a,b in zip(p.node.position.as_list(),target.node.position.as_list()))
        move={p.node.key};pending=[p.node.key]
        while pending:
            key=pending.pop();n=self.by_key[key];gid=self.node_group.get(key)
            if gid is not None and self.kind(gid) not in SUPPORTED:
                raise ValueError('UNSUPPORTED_POPULATED_OWNER')
            more=[]
            if gid is not None and self.kind(gid) in FINITE:more+=self.groups[gid]
            for other in self.nodes:
                shared=n.positive and other.positive and n.node_number==other.node_number
                if shared and n.position.distance_to(other.position)>self.config.connection_tolerance_mm:
                    if (target.node.positive and other.node_number==target.node.node_number and
                        other.position.distance_to(target.node.position)<=1e-6):continue
                    raise ValueError('SHARED_NODE_POSITION_CONFLICT')
                if shared or (n.branch_index==other.branch_index and n.position.distance_to(other.position)<=1e-6):more.append(other)
            for other in more:
                if other.key not in move:move.add(other.key);pending.append(other.key)
        if target.node.key in move and any(abs(v)>1e-9 for v in delta):raise ValueError('ALREADY_CONNECTED_MOVE_GROUP')
        if any(self.by_key[k].has_restraint for k in move) and any(abs(v)>1e-9 for v in delta):raise ValueError('RESTRAINED_MOVE_GROUP')
        for gid,g in enumerate(self.groups):
            if self.kind(gid)!='PIPE':continue
            points=[]
            for n in g:
                xyz=n.position.as_list()
                points.append(tuple(xyz[i]+(delta[i] if n.key in move else 0) for i in range(3)))
            if len(points)>1 and max(sum((a-b)**2 for a,b in zip(points[0],q)) for q in points[1:])<=1e-12:
                raise ValueError('PIPE_COLLAPSE')
        return sorted(move),delta

    def candidates(self):
        pairs={};occupied=set();adjacent=set();boundary=set()
        for ids in self.branch_groups.values():
            physical=[gid for gid in ids if self.group_ports.get(gid)]
            if not physical:continue
            first=min(self.group_ports[physical[0]],key=lambda p:p.node.endpoint or 0)
            last=max(self.group_ports[physical[-1]],key=lambda p:p.node.endpoint or 0)
            if self.kind(first.group)=='BRAN' and len(physical)>1:
                peer=min(self.group_ports[physical[1]],key=lambda p:p.node.endpoint or 0)
                if first.node.position.distance_to(peer.node.position)<=1e-6:first=peer
            if self.kind(last.group)=='BRAN' and len(physical)>1:
                peer=max(self.group_ports[physical[-2]],key=lambda p:p.node.endpoint or 0)
                if last.node.position.distance_to(peer.node.position)<=1e-6:last=peer
            boundary.update((first.node.key,last.node.key))
            for ga,gb in zip(physical,physical[1:]):
                pa=self.group_ports[ga];pb=self.group_ports[gb]
                a=next((p for p in pa if p.node.endpoint==2),pa[-1])
                b=next((p for p in pb if p.node.endpoint==1),pb[0])
                if self.compatible(a,b):
                    adjacent.add(tuple(sorted((a.node.key,b.node.key))))
                    d=a.node.position.distance_to(b.node.position)
                    if d<=1e-6 and self.kind(a.group)!='BRAN' and self.kind(b.group)!='BRAN':occupied.update((a.node.key,b.node.key))
                    if d<=min(25.,self.config.joint_repair_threshold_mm)+1e-9:pairs[tuple(sorted((a.node.key,b.node.key)))]=(a,b)
        for i,a in enumerate(self.ports):
            if a.node.key in occupied:continue
            if self.kind(a.group)=='BRAN' and a.node.key not in boundary:continue
            for b in self.ports[i+1:]:
                if b.node.key in occupied or a.node.branch_index==b.node.branch_index:continue
                if self.kind(b.group)=='BRAN' and b.node.key not in boundary:continue
                if a.node.key not in boundary and b.node.key not in boundary:continue
                if a.node.position.distance_to(b.node.position)>min(25.,self.config.joint_repair_threshold_mm)+1e-9:continue
                if not self.compatible(a,b,True):continue
                if a.node.position.distance_to(b.node.position)<=min(25.,self.config.joint_repair_threshold_mm)+1e-9:
                    pairs[tuple(sorted((a.node.key,b.node.key)))]=(a,b)
        counts={}
        for key in pairs:
            for k in key:counts[k]=counts.get(k,0)+1
        repairs=[]
        for key,(a,b) in sorted(pairs.items()):
            if any(counts[k]>1 for k in key):continue
            try:repairs.append(self.repair(a,b))
            except ValueError:pass
        return repairs

def public_cases():
    cases=[pipe_flange(x,cross) for x in (0,0.5,24.999999,25,25.000001,25.01,100)
           for cross in (True,False)]
    cases += [fixture(3),fixture(6),fixture(6.001)]
    cases += [doc(
      node(10,'PIPE','P',1,'0 0 0')+node(20,'PIPE','P',2,'100 0 0','<Restraint>X</Restraint>'),
      node(20,'FLAN','F',1,'100 0 0')+node(-1,'RIGID','F',2,'186 0 0'))]
    cases += [doc(
      node(10,'PIPE','P',1,'0 0 0')+node(20,'PIPE','P',2,'100 0 0'),
      node(21,'FLAN','F',1,'125 0 0')+node(-1,'RIGID','F',2,'211 0 0'),
      node(22,'FLAN','G',1,'125 0 0')+node(-2,'RIGID','G',2,'211 0 0'))]
    cases += [doc(*[
      node(100+i*10,'PIPE',f'P{i}',1,f'{i*1000} 0 0')+
      node(101+i*10,'PIPE',f'P{i}',2,f'{i*1000+100} 0 0')
      for i in range(12)])]
    return cases

class PortIndexParity(unittest.TestCase):
    def test_candidate_and_movement_parity(self):
        for case,source in enumerate(public_cases()):
            with self.subTest(case=case):
                document=read_psi116_xml(source)
                cfg=ResolverConfig()
                slow=UnindexedReference(document,cfg)
                indexed=PortModel(document,cfg)
                self.assertEqual(slow.candidates(),indexed.candidates())
                for i,a in enumerate(slow.ports):
                    for b in slow.ports[i+1:]:
                        if a.group==b.group:continue
                        x,y=indexed.port_by_key[a.node.key],indexed.port_by_key[b.node.key]
                        try:expected=slow.moving_group(a,b)
                        except ValueError as exc:expected=(type(exc).__name__,str(exc))
                        try:actual=indexed.moving_group(x,y)
                        except ValueError as exc:actual=(type(exc).__name__,str(exc))
                        self.assertEqual(expected,actual)

if __name__=='__main__':unittest.main()
