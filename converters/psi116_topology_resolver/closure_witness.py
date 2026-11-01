"""Read-only witnesses of source CLOS (closed-end) declarations bound to ports.

A port bound to CLOS is excluded from every pairing (PortModel.compatible), so a
nearby counterpart never appears as a connection finding. These rows show that
binding to the engineer. ``bound_closure_records`` remains the only authority on
which declarations bind; the binding-kind labels below restate its predicates
only to name which one matched. Nothing here proposes, joins or edits anything.

bindingStatus vocabulary:
  BOUND                 qualified physical port with >=1 CLOS declaration bound.
  UNQUALIFIED           CLOS declaration that has a Position but binds to no
                        qualified physical port (only to non-port records).
  EVIDENCE_UNAVAILABLE  CLOS declaration with no readable Position, so its
                        binding cannot be evaluated; or a runtime without this
                        module (see models._closure_binding_witnesses).
"""
from .connection_ports import PortModel, bound_closure_records

BOUND = 'BOUND'
UNQUALIFIED = 'UNQUALIFIED'
EVIDENCE_UNAVAILABLE = 'EVIDENCE_UNAVAILABLE'
_STATUS_ORDER = {BOUND: 0, UNQUALIFIED: 1, EVIDENCE_UNAVAILABLE: 2}
ROW_KEYS = ('sourceKey', 'branchIndex', 'branchName', 'sourceIndex', 'nodeNumber', 'positiveNodeNumber',
            'componentType', 'componentRefNo', 'endpoint', 'connectionType', 'sourceSha256', 'rowKind',
            'portQualified', 'ownerType', 'bindingStatus', 'closureDeclarations', 'boundRecordKeys',
            'pairingEffect', 'reason')


def _binding_kinds(branch, physical, declaration, node, tolerance):
    """Name each true predicate of bound_closure_records(); same terms, no extra conditions."""
    distance = declaration.position.distance_to(node.position)
    kinds = []
    if declaration.key == node.key:
        kinds.append('EXACT_SOURCE_RECORD')
    if (node.positive and declaration.positive and declaration.node_number == node.node_number
            and distance <= tolerance):
        kinds.append('SAME_POSITIVE_NODE_NUMBER_WITHIN_TOLERANCE')
    if (bool(node.component_ref_no) and declaration.component_ref_no == node.component_ref_no
            and declaration.endpoint == node.endpoint and distance <= 1e-6):
        kinds.append('SAME_COMPONENT_OWNER_ENDPOINT')
    if declaration.component_type == 'BRAN' and distance <= 1e-6 and physical:
        if declaration.endpoint == 1 and declaration.source_index == 0 and node.key == physical[0].key:
            kinds.append('BRANCH_BOUNDARY_START')
        if (declaration.endpoint == 2 and declaration.source_index == len(branch.nodes) - 1
                and node.key == physical[-1].key):
            kinds.append('BRANCH_BOUNDARY_END')
    return kinds or ['UNCLASSIFIED']


def _physical(branch):
    # Same selection as bound_closure_records() uses for its boundary clause.
    return [n for n in branch.nodes if n.position and n.component_type not in {'BRAN', 'ATTA', 'SUPPORT', 'ANCI'}]


def _record(node):
    return {'sourceKey': node.key, 'branchIndex': node.branch_index, 'branchName': node.branch_name,
            'sourceIndex': node.source_index, 'nodeNumber': node.node_number,
            'positiveNodeNumber': node.positive, 'componentType': node.component_type,
            'componentRefNo': node.component_ref_no, 'endpoint': node.endpoint,
            'connectionType': node.connection_type}


def _declaration(branch, physical, declaration, node, tolerance):
    return {**_record(declaration), 'distanceMm': declaration.position.distance_to(node.position),
            'bindingKinds': _binding_kinds(branch, physical, declaration, node, tolerance)}


def _bound_records_by_declaration(doc, branch_index, declarations, tolerance):
    """Declaration key -> keys of records it binds, from one authority call per candidate.

    Every bound_closure_records() clause requires distance <= max(tolerance, 1e-6)
    (an exact record match is distance 0), so records farther than that from all of
    a branch's declarations cannot bind and are not queried.
    """
    radius = max(tolerance, 1e-6)
    located = [d for d in declarations if d.position]
    reverse = {d.key: [] for d in located}
    for n in doc.branches[branch_index].nodes:
        if not n.position or not any(d.position.distance_to(n.position) <= radius for d in located):
            continue
        for record in bound_closure_records(doc, n, tolerance):
            if record.key in reverse:
                reverse[record.key].append(n.key)
    return reverse


def closure_binding_witnesses(doc, config, model=None):
    """One row per qualified port with CLOS bound, plus one per CLOS declaration bound to no port."""
    tolerance = config.connection_tolerance_mm
    model = model or PortModel(doc, config)
    by_branch = {}
    for b in doc.branches:
        for n in b.nodes:
            if n.connection_type == 'CLOS':
                by_branch.setdefault(b.index, []).append(n)
    physical = {i: _physical(doc.branches[i]) for i in by_branch}
    rows, bound_to_port = [], set()
    for port in model.ports:
        node = port.node
        # closed_keys is PortModel's own bound_closure_records() result for every port.
        if node.key not in model.closed_keys:
            continue
        branch = doc.branches[node.branch_index]
        records = bound_closure_records(doc, node, tolerance)
        bound_to_port.update(r.key for r in records)
        rows.append({**_record(node), 'sourceSha256': doc.source_sha256, 'rowKind': 'PORT',
                     'portQualified': True, 'ownerType': model.kind(port.group), 'bindingStatus': BOUND,
                     'closureDeclarations': [_declaration(branch, physical[node.branch_index], r, node, tolerance)
                                             for r in records],
                     'boundRecordKeys': None,
                     'pairingEffect': 'PORT_EXCLUDED_FROM_AUTOMATIC_AND_SECOND_PASS_PAIRING',
                     'reason': 'Source CLOS declaration bound to this port; the tool will not pair it with any counterpart.'})
    for branch_index, declarations in by_branch.items():
        unbound = [d for d in declarations if d.key not in bound_to_port]
        if not unbound:
            continue
        reverse = _bound_records_by_declaration(doc, branch_index, unbound, tolerance)
        for declaration in unbound:
            row = {**_record(declaration), 'sourceSha256': doc.source_sha256, 'rowKind': 'DECLARATION',
                   'portQualified': False, 'ownerType': None, 'closureDeclarations': [],
                   'pairingEffect': 'NONE_NOT_A_QUALIFIED_PORT'}
            if declaration.position is None:
                rows.append({**row, 'bindingStatus': EVIDENCE_UNAVAILABLE, 'boundRecordKeys': [],
                             'reason': 'CLOS declaration has no readable Position; its binding cannot be evaluated.'})
            else:
                # A positioned declaration always binds at least its own record.
                rows.append({**row, 'bindingStatus': UNQUALIFIED, 'boundRecordKeys': reverse[declaration.key],
                             'reason': 'CLOS declaration has a Position but binds only to source records that are not a qualified physical port.'})
    rows.sort(key=lambda r: (r['branchIndex'], r['sourceIndex'], _STATUS_ORDER[r['bindingStatus']]))
    return [{k: r[k] for k in ROW_KEYS} for r in rows]
