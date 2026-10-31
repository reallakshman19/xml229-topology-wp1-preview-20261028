"""Read-only witnesses of source CLOS (closed-end) declarations bound to ports.

A port bound to CLOS is excluded from every pairing (PortModel.compatible), so a
nearby counterpart never appears as a connection finding. These rows show that
binding to the engineer. ``bound_closure_records`` remains the only authority on
which declarations bind; the binding-kind labels below only describe a binding it
already returned. Nothing here proposes, joins or edits anything.
"""
from .connection_ports import PortModel, bound_closure_records

BOUND = 'BOUND'
UNQUALIFIED = 'UNQUALIFIED'
NO_BINDING = 'NO_BINDING'
EVIDENCE_UNAVAILABLE = 'EVIDENCE_UNAVAILABLE'
_STATUS_ORDER = {BOUND: 0, UNQUALIFIED: 1, NO_BINDING: 2, EVIDENCE_UNAVAILABLE: 3}


def _binding_kinds(doc, declaration, node, tolerance):
    """Describe which bound_closure_records() branch matched; never decides binding."""
    distance = declaration.position.distance_to(node.position)
    kinds = []
    if declaration.key == node.key:
        kinds.append('EXACT_SOURCE_RECORD')
    elif (node.positive and declaration.positive and declaration.node_number == node.node_number
          and distance <= tolerance):
        kinds.append('SAME_POSITIVE_NODE_NUMBER_WITHIN_TOLERANCE')
    if (node.component_ref_no and declaration.component_ref_no == node.component_ref_no
            and declaration.endpoint == node.endpoint and distance <= 1e-6):
        kinds.append('SAME_COMPONENT_OWNER_ENDPOINT')
    last = len(doc.branches[declaration.branch_index].nodes) - 1
    if declaration.component_type == 'BRAN' and distance <= 1e-6:
        if declaration.endpoint == 1 and declaration.source_index == 0:
            kinds.append('BRANCH_BOUNDARY_START')
        elif declaration.endpoint == 2 and declaration.source_index == last:
            kinds.append('BRANCH_BOUNDARY_END')
    return kinds or ['UNCLASSIFIED']


def _record(node):
    return {'sourceKey': node.key, 'branchIndex': node.branch_index, 'branchName': node.branch_name,
            'sourceIndex': node.source_index, 'nodeNumber': node.node_number,
            'positiveNodeNumber': node.positive, 'componentType': node.component_type,
            'componentRefNo': node.component_ref_no, 'endpoint': node.endpoint}


def _declaration(doc, declaration, node, tolerance):
    return {**_record(declaration), 'connectionType': declaration.connection_type,
            'distanceMm': declaration.position.distance_to(node.position),
            'bindingKinds': _binding_kinds(doc, declaration, node, tolerance)}


def closure_binding_witnesses(doc, config):
    """One row per qualified port with CLOS bound, plus one per CLOS declaration bound to no port."""
    tolerance = config.connection_tolerance_mm
    model = PortModel(doc, config)
    declarations = [n for b in doc.branches for n in b.nodes if n.connection_type == 'CLOS']
    clos_branches = {n.branch_index for n in declarations}
    rows, bound_to_port = [], set()
    for port in model.ports:
        node = port.node
        if node.branch_index not in clos_branches:
            continue
        records = bound_closure_records(doc, node, tolerance)
        if not records:
            continue
        bound_to_port.update(r.key for r in records)
        rows.append({**_record(node), 'sourceSha256': doc.source_sha256, 'rowKind': 'PORT',
                     'portQualified': True, 'ownerType': model.kind(port.group),
                     'bindingStatus': BOUND,
                     'closureDeclarations': [_declaration(doc, r, node, tolerance) for r in records],
                     'pairingEffect': 'PORT_EXCLUDED_FROM_AUTOMATIC_AND_SECOND_PASS_PAIRING',
                     'reason': 'Source CLOS declaration bound to this port; the tool will not pair it with any counterpart.'})
    for declaration in declarations:
        if declaration.key in bound_to_port:
            continue
        row = {**_record(declaration), 'sourceSha256': doc.source_sha256, 'rowKind': 'DECLARATION',
               'portQualified': False, 'ownerType': None, 'connectionType': declaration.connection_type,
               'closureDeclarations': [], 'pairingEffect': 'NONE_NOT_A_QUALIFIED_PORT'}
        if declaration.position is None:
            rows.append({**row, 'bindingStatus': EVIDENCE_UNAVAILABLE, 'boundRecordKeys': [],
                         'reason': 'CLOS declaration has no readable Position; its binding cannot be evaluated.'})
            continue
        # Same-branch scan: bound_closure_records() only binds within a branch.
        keys = [n.key for n in doc.branches[declaration.branch_index].nodes if n.position
                and declaration.key in {r.key for r in bound_closure_records(doc, n, tolerance)}]
        if keys:
            rows.append({**row, 'bindingStatus': UNQUALIFIED, 'boundRecordKeys': keys,
                         'reason': 'CLOS declaration binds only to source records that are not a qualified physical port.'})
        else:
            rows.append({**row, 'bindingStatus': NO_BINDING, 'boundRecordKeys': [],
                         'reason': 'CLOS declaration binds to no source record.'})
    rows.sort(key=lambda r: (r['branchIndex'], r['sourceIndex'], _STATUS_ORDER[r['bindingStatus']]))
    return rows
