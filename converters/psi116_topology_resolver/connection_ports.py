"""Physical PSI116 port interfaces under the Owner's inclusive 25 mm policy.

Finite component ports translate together. PIPE ports may extend/shorten the pipe.
Source records and negative helper identities are retained, never discarded.
"""
from dataclasses import dataclass
from math import sqrt, isfinite, floor

FINITE = frozenset({'FLAN','GASK','VALV','INST','RIGID','REDU','ELBO','TEE','OLET','COUP','FBLI','CAP'})
SUPPORTED = FINITE | {'PIPE','BRAN'}
MOVE_ORDER = {'PIPE':0, 'FLAN':1, 'VALV':2, 'ELBO':3}

def bound_closure_records(doc, node, tolerance=0.5):
    """A CLOS declaration belongs to an owner/port or the exact branch boundary."""
    branch=doc.branches[node.branch_index]
    physical=[n for n in branch.nodes if n.position and n.component_type not in {'BRAN','ATTA','SUPPORT','ANCI'}]
    result=[]
    for declaration in branch.nodes:
        if declaration.connection_type!='CLOS' or not declaration.position or not node.position:continue
        distance=declaration.position.distance_to(node.position)
        direct=declaration.key==node.key or (node.positive and declaration.positive and
                declaration.node_number==node.node_number and distance<=tolerance)
        owner=(bool(node.component_ref_no) and declaration.component_ref_no==node.component_ref_no and
               declaration.endpoint==node.endpoint and distance<=1e-6)
        boundary=(declaration.component_type=='BRAN' and distance<=1e-6 and physical and
            ((declaration.endpoint==1 and declaration.source_index==0 and node.key==physical[0].key) or
             (declaration.endpoint==2 and declaration.source_index==len(branch.nodes)-1 and node.key==physical[-1].key)))
        if direct or owner or boundary:result.append(declaration)
    return result

@dataclass(frozen=True)
class Port:
    node: object
    group: int
    normal: tuple | None

class PortModel:
    def __init__(self, doc, config):
        self.doc, self.config = doc, config
        self.nodes = [n for b in doc.branches for n in b.nodes if n.position]
        self.by_key = {n.key:n for n in self.nodes}
        # Exact candidates: same-branch contact and shared positive NodeNumber.
        # All original Euclidean distance checks remain authoritative.
        self._global_order = {n.key:i for i,n in enumerate(self.nodes)}
        self._nodes_by_branch = {}
        self._positive_by_number = {}
        for n in self.nodes:
            self._nodes_by_branch.setdefault(n.branch_index, []).append(n)
            if n.positive:self._positive_by_number.setdefault(n.node_number, []).append(n)
        self.groups, self.node_group, self.branch_groups = [], {}, {}
        for branch in doc.branches:
            groups=[]
            for n in branch.nodes:
                if not n.position or n.component_type in {'ATTA','SUPPORT','ANCI'}:continue
                # RIGID is an exported endpoint representation of the same physical owner.
                if (groups and n.component_ref_no and n.component_type!='BRAN'
                    and groups[-1][-1].component_type!='BRAN'
                    and groups[-1][-1].component_ref_no==n.component_ref_no):groups[-1].append(n)
                else:groups.append([n])
            ids=[]
            for group in groups:
                gid=len(self.groups);self.groups.append(group);ids.append(gid)
                for n in group:self.node_group[n.key]=gid
            self.branch_groups[branch.index]=ids
        self._kinds = tuple(next((n.component_type for n in g if n.component_type!='RIGID'),
                                 g[0].component_type) for g in self.groups)
        self._pipe_group_by_node = {n.key:gid for gid,g in enumerate(self.groups)
            if self._kinds[gid]=='PIPE' for n in g}
        self._source_collapsed_pipe_groups = frozenset(
            gid for gid,g in enumerate(self.groups) if self._kinds[gid]=='PIPE'
            and len(g)>1 and max(sum((a-b)**2 for a,b in
                zip(g[0].position.as_list(),q.position.as_list())) for q in g[1:])<=1e-12)
        # Exact 1e-6 proximity: 27 neighboring 3D cells cover every possible
        # match; final membership still uses the original Euclidean test.
        self._exact_cells={}
        self._unindexed_nodes=[]
        for n in self.nodes:
            xyz=n.position.as_list()
            if all(isfinite(v/1e-6) for v in xyz):
                cell=tuple(floor(v/1e-6) for v in xyz)
                self._exact_cells.setdefault(cell,[]).append(n)
            else:self._unindexed_nodes.append(n)
        self.ports=[];self.group_ports={}
        for gid,group in enumerate(self.groups):
            kind=self.kind(gid)
            if kind not in SUPPORTED:continue
            # Duplicated/absent port labels are not a qualified physical port profile.
            if kind=='BRAN':port_nodes=group
            else:
                port_nodes=[n for n in group if n.endpoint in {1,2,3}]
                if len({n.endpoint for n in port_nodes})!=len(port_nodes):continue
                if kind not in {'TEE','OLET','CAP'} and {1,2}-set(n.endpoint for n in port_nodes):continue
            center=next((n for n in group if n.endpoint==0),None)
            for n in port_nodes:
                other=center if kind in {'TEE','OLET','ELBO'} else next((o for o in port_nodes if o.key!=n.key),None)
                normal=None
                if other:
                    delta=tuple(a-b for a,b in zip(n.position.as_list(),other.position.as_list()))
                    length=sqrt(sum(v*v for v in delta))
                    if length>1e-9:normal=tuple(v/length for v in delta)
                p=Port(n,gid,normal);self.ports.append(p);self.group_ports.setdefault(gid,[]).append(p)
            if center and center.positive and kind in {'TEE','OLET'}:
                self.ports.append(Port(center,gid,None))
        self.port_by_key={p.node.key:p for p in self.ports}
        self.closed_keys={p.node.key for p in self.ports if self.closed(p)}

    def kind(self,gid):
        return self._kinds[gid]

    def closed(self,p):
        if hasattr(self,'closed_keys'):return p.node.key in self.closed_keys
        return bool(bound_closure_records(self.doc,p.node,self.config.connection_tolerance_mm))

    def junction_mismatch(self,a,b):
        return any(p.node.component_type=='BRAN' and p.node.connection_type in {'TEE','OLET'} and
                   self.kind(q.group) in {'TEE','OLET'} and p.node.connection_type!=self.kind(q.group)
                   for p,q in ((a,b),(b,a)))

    def compatible(self,a,b,cross=False):
        if a.group==b.group or self.closed(a) or self.closed(b) or self.junction_mismatch(a,b):return False
        x,y=a.node,b.node
        # A declared branch-to-junction connection may have a smaller branch bore.
        junction=(x.component_type=='BRAN' and x.connection_type in {'TEE','OLET'} and x.connection_type==self.kind(b.group)) or \
                 (y.component_type=='BRAN' and y.connection_type in {'TEE','OLET'} and y.connection_type==self.kind(a.group))
        explicit=junction and x.positive and y.positive and x.node_number==y.node_number
        if (x.endpoint==0 or y.endpoint==0) and not explicit:return False
        if explicit:return True  # independently bound source branch/junction identity
        diameters=(x.outside_diameter,y.outside_diameter)
        if not all(v is not None and isfinite(v) and v>0 for v in diameters):return False
        if abs(diameters[0]-diameters[1])>.5:return False
        walls=(x.wall_thickness,y.wall_thickness)
        if all(v is not None and isfinite(v) and v>0 for v in walls):
            if abs((diameters[0]-2*walls[0])-(diameters[1]-2*walls[1]))>.5:return False
        for normal in (a.normal,b.normal):
            if normal is None or len(normal)!=3 or not all(isfinite(v) for v in normal):return False
            if abs(sum(v*v for v in normal)-1)>.001:return False
        if sum(v*w for v,w in zip(a.normal,b.normal))>-.9:return False
        return True

    def moving_group(self,p,target):
        """Translate finite owners and their existing contacts; stop at PIPE ports."""
        delta=tuple(b-a for a,b in zip(p.node.position.as_list(),target.node.position.as_list()))
        move={p.node.key};pending=[p.node.key]
        while pending:
            key=pending.pop();n=self.by_key[key];gid=self.node_group.get(key)
            if gid is not None and self.kind(gid) not in SUPPORTED:
                raise ValueError('UNSUPPORTED_POPULATED_OWNER')
            more=[]
            if gid is not None and self.kind(gid) in FINITE:more+=self.groups[gid]
            # Only nodes in the same branch or bearing an identical positive
            # shared NodeNumber can satisfy the original predicate.
            possible=self._nodes_by_branch[n.branch_index]
            if n.positive:
                extras=[o for o in self._positive_by_number.get(n.node_number, ())
                        if o.branch_index!=n.branch_index]
                if extras:
                    possible=sorted((*possible,*extras),key=lambda o:self._global_order[o.key])
            for other in possible:
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
        # Unchanged PIPE groups keep their geometry. Retain rejection of any
        # pre-existing collapse outside moved groups, but permit a move that
        # actually repairs a previously collapsed pipe.
        touched={self._pipe_group_by_node[k] for k in move
                 if k in self._pipe_group_by_node}
        if self._source_collapsed_pipe_groups - touched:
            raise ValueError('PIPE_COLLAPSE')
        for gid in touched:
            g=self.groups[gid]
            points=[]
            for n in g:
                xyz=n.position.as_list()
                points.append(tuple(xyz[i]+(delta[i] if n.key in move else 0) for i in range(3)))
            if len(points)>1 and max(sum((a-b)**2 for a,b in zip(points[0],q)) for q in points[1:])<=1e-12:
                raise ValueError('PIPE_COLLAPSE')
        return sorted(move),delta

    def repair(self,a,b):
        return self._repair(a,b,confirmed=False)

    def confirmed_repair(self,a,b):
        """Explicit second-pass pair only; never used by automatic discovery."""
        return self._repair(a,b,confirmed=True)

    def _repair(self,a,b,*,confirmed):
        if not self.compatible(a,b,a.node.branch_index!=b.node.branch_index):raise ValueError('INCOMPATIBLE_PORTS')
        distance=a.node.position.distance_to(b.node.position)
        if not isfinite(distance):raise ValueError('NONFINITE_PORT_DISTANCE')
        if not confirmed and distance>min(25.,self.config.joint_repair_threshold_mm)+1e-9:raise ValueError('PORT_DISTANCE_EXCEEDS_POLICY')
        # Keep the more constrained/finite owner. Try the other side if the first is anchored.
        def priority(p):return (MOVE_ORDER.get(self.kind(p.group),4),-p.node.branch_index,-p.node.source_index)
        moving,target=sorted((a,b),key=priority)
        choices=[(moving,target),(target,moving)]
        for moving,target in choices:
            try:keys,delta=self.moving_group(moving,target)
            except ValueError:continue
            target_xyz=target.node.position.as_list()
            if all(isfinite(v/1e-6) for v in target_xyz):
                cell=tuple(floor(v/1e-6) for v in target_xyz)
                nearby=list(self._unindexed_nodes)
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        for dz in (-1,0,1):
                            nearby.extend(self._exact_cells.get((cell[0]+dx,cell[1]+dy,cell[2]+dz),()))
            else:nearby=self.nodes
            target_cluster=[n for n in nearby if n.position.distance_to(target.node.position)<=1e-6]
            identities=([target.node.node_number] if target.node.positive else
                sorted({n.node_number for n in target_cluster if n.positive and n.key not in keys}))
            if len(identities)>1:continue
            owner=identities[0] if identities else None
            # Only moved keys can be aliased; avoid another whole-model scan.
            moved_nodes=sorted((self.by_key[k] for k in keys),
                               key=lambda n:self._global_order[n.key])
            aliases={n.key:owner for n in moved_nodes if n.positive and owner is not None
                     and n.position.distance_to(moving.node.position)<=1e-6 and n.node_number!=owner}
            if not any(abs(v)>1e-9 for v in delta) and not aliases:raise ValueError('NO_XML_CHANGE')
            return {'movePortKey':moving.node.key,'targetPortKey':target.node.key,
                    'moveKeys':keys,'delta':list(delta),'aliases':aliases,'distanceMm':distance,
                    'policy':'USER_SELECTED_SECOND_PASS' if confirmed else 'OWNER_PORT_CONNECTION_LE_25_MM'}
        raise ValueError('MOVE_GROUP_REQUIRES_REVIEW')

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
        # 25 mm spatial cells bound candidate search but never replace the
        # inclusive exact-distance and engineering compatibility tests.
        bucket_size=25.
        def cell(p):
            xyz=p.node.position.as_list()
            return tuple(floor(v/bucket_size) for v in xyz) if all(isfinite(v) for v in xyz) else None
        cells=[cell(p) for p in self.ports]
        finite_grid={}
        for i,c in enumerate(cells):
            if c is not None:finite_grid.setdefault(c,[]).append(i)
        unindexed=[i for i,c in enumerate(cells) if c is None]
        for i,a in enumerate(self.ports):
            if a.node.key in occupied:continue
            if self.kind(a.group)=='BRAN' and a.node.key not in boundary:continue
            c=cells[i]
            if c is None:indices=range(i+1,len(self.ports))
            else:
                indexes=set(unindexed)
                # The inclusive 25 mm guard below has a +1e-9 margin.
                # Near a cell edge, that can span cells two steps apart.
                for dx in range(-2,3):
                    for dy in range(-2,3):
                        for dz in range(-2,3):
                            indexes.update(finite_grid.get((c[0]+dx,c[1]+dy,c[2]+dz),()))
                indices=sorted(j for j in indexes if j>i)
            for j in indices:
                b=self.ports[j]
                if b.node.key in occupied or a.node.branch_index==b.node.branch_index:continue
                if self.kind(b.group)=='BRAN' and b.node.key not in boundary:continue
                if a.node.key not in boundary and b.node.key not in boundary:continue
                if a.node.position.distance_to(b.node.position)>min(25.,self.config.joint_repair_threshold_mm)+1e-9:continue
                if not self.compatible(a,b,True):continue
                if a.node.position.distance_to(b.node.position)<=min(25.,self.config.joint_repair_threshold_mm)+1e-9:
                    pairs[tuple(sorted((a.node.key,b.node.key)))]=(a,b)
        # Multiple counterparts are an engineering exception, not a nearest-neighbour guess.
        counts={}
        for key in pairs:
            for k in key:counts[k]=counts.get(k,0)+1
        repairs=[]
        for key,(a,b) in sorted(pairs.items()):
            if any(counts[k]>1 for k in key):continue
            try:repairs.append(self.repair(a,b))
            except ValueError:pass
        return repairs
