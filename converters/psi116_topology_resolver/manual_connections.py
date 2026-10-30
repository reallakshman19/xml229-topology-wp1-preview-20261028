"""Source-bound preview and explicit approval of one manual connection.

Distance never supplies design intent. Automatic discovery retains its 25 mm cap.
"""
from .connection_ports import PortModel

MANUAL_CODES = frozenset({'BRANCH_END_UNVERIFIED', 'NEAR_MISS_PIPE_JOINT',
    'NEAR_MISS_BRANCH_ENDS', 'COINCIDENT_NODE_IDENTITY_AMBIGUOUS',
    'COINCIDENT_NODE_ALIAS_CANDIDATE', 'PORT_CONNECTION_WITHIN_TOLERANCE'})


def manual_ports(doc, config):
    model = PortModel(doc, config)
    return [{'key':p.node.key, 'ownerType':model.kind(p.group),
             'componentRefNo':p.node.component_ref_no, 'endpoint':p.node.endpoint,
             'closed':model.closed(p), 'normal':p.normal,
             'outsideDiameter':p.node.outside_diameter}
            for p in model.ports]


def preview_connection(result, request, config):
    if request.get('mode') != 'SECOND_PASS':
        raise ValueError('SECOND_PASS_MODE_REQUIRED')
    if request.get('sourceSha256') != result.document.source_sha256:
        raise ValueError('SECOND_PASS_SOURCE_DRIFT')
    finding = next((f for f in result.findings if f.finding_id == request.get('findingId')), None)
    keys = request.get('portKeys')
    if (not finding or finding.code not in MANUAL_CODES or not isinstance(keys, list)
        or len(keys) != 2 or any(not isinstance(k, str) for k in keys)
        or keys[0] == keys[1] or not set(keys) & set(finding.node_keys)):
        raise ValueError('Select two distinct ports including a witness of this connection finding.')
    model = PortModel(result.document, config)
    if any(k not in model.port_by_key for k in keys):
        raise ValueError('Selected record is not a qualified physical port; correct its source owner/ports and re-export.')
    repair = model.confirmed_repair(*(model.port_by_key[k] for k in keys))
    changes = []
    for key in repair['moveKeys']:
        n = model.by_key[key]
        before = {'Position':n.position.as_list(), 'NodeNumber':n.node_number}
        after = {'Position':[v+d for v,d in zip(n.position.as_list(),repair['delta'])],
                 'NodeNumber':repair['aliases'].get(key,n.node_number)}
        if before != after:
            changes.append({'sourceKey':key, 'before':before, 'after':after})
    return {'sourceSha256':result.document.source_sha256, 'findingId':finding.finding_id,
            'portKeys':keys, 'repair':repair, 'changes':changes}


def approved_connection(result, request, config):
    preview = preview_connection(result, request, config)
    if (request.get('confirmed') is not True or not isinstance(request.get('evidence'), str)
        or len(request['evidence'].strip()) < 10):
        raise ValueError('Confirm this exact intended connection and provide its design/reasoning reference.')
    repair = preview['repair']
    if (request.get('approvedRepair') != repair or request.get('moveKey') != repair['movePortKey']
        or request.get('targetKey') != repair['targetPortKey']):
        raise ValueError('SECOND_PASS_PREVIEW_DRIFT: reopen the preview and approve the current movement.')
    return repair
