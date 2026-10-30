"""Explicit, source-bound repair of two confirmed PIPE ports; never a proximity auto-join."""
from dataclasses import replace
from .models import FixAction

CODES = frozenset({'NEAR_MISS_PIPE_JOINT', 'NEAR_MISS_BRANCH_ENDS',
                   'PORT_CONNECTION_WITHIN_TOLERANCE',
                   'COINCIDENT_NODE_IDENTITY_AMBIGUOUS', 'COINCIDENT_NODE_ALIAS_CANDIDATE'})


def repair_action_id(request):
    return 'JOIN:' + request['findingId'] + ':' + request['moveKey']


def with_confirmed_joint_repairs(result, requests, config):
    if not requests:
        return result
    if len(requests) != 1:
        raise ValueError('Repair one confirmed joint at a time; recheck before the next joint.')
    request = requests[0]
    if request.get('sourceSha256') != result.document.source_sha256:
        raise ValueError('JOINT_REPAIR_SOURCE_DRIFT')
    if not isinstance(request.get('evidence'), str) or len(request['evidence'].strip()) < 10:
        raise ValueError('Confirm the intended connection with a design/reasoning reference.')
    finding = next((f for f in result.findings if f.finding_id == request.get('findingId')), None)
    pair = {request.get('moveKey'), request.get('targetKey')}
    if not finding or finding.code not in CODES or len(pair) != 2 or pair != set(finding.node_keys):
        raise ValueError('Repair requires exactly the two source-qualified joint witnesses.')
    records = [n for b in result.document.branches for n in b.nodes]
    by_key = {n.key: n for n in records}
    moving, target = by_key[request['moveKey']], by_key[request['targetKey']]
    for node in (moving, target):
        if (node.semantic_type != 'PIPE' or not node.positive or node.position is None
                or node.endpoint not in {1, 2} or node.has_restraint
                or node.rigid not in {None, 0}):
            raise ValueError('Only unrestrained, non-rigid PIPE endpoint ports can be closed here.')
        if sum(n.node_number == node.node_number for n in records) != 1:
            raise ValueError('Shared NodeNumber ownership requires upstream repair; no partial group move.')
        owners = [o for o in result.document.occurrences if node in o.records]
        if len(owners) != 1 or owners[0].semantic_type != 'PIPE' or len(owners[0].records) != 2:
            raise ValueError('A unique two-port PIPE owner is required; inspect component ownership upstream.')
    distance = moving.position.distance_to(target.position)
    if distance > min(25.0, config.joint_repair_threshold_mm):
        raise ValueError('Joint closure requires a 3D separation no greater than 25 mm.')
    owner = next(o for o in result.document.occurrences if moving in o.records)
    if target in owner.records:
        raise ValueError('Cannot close the two ends of the same PIPE component.')
    other = next(n for n in owner.records if n != moving)
    if other.position is None or other.position.distance_to(target.position) <= config.connection_tolerance_mm:
        raise ValueError('Closure would collapse the owning PIPE component.')
    if any(n.key not in pair and n.position and
           n.position.distance_to(moving.position) <= config.connection_tolerance_mm for n in records):
        raise ValueError('Moving port has additional coincident ownership; repair the joint group upstream.')
    action = FixAction(
        action_id=repair_action_id(request), finding_ids=(finding.finding_id,),
        disposition='CLOSE_CONFIRMED_PIPE_JOINT', status='PROPOSED', confidence=1.0,
        authority='USER_CONFIRMED_CONNECTION:' + request['evidence'].strip(),
        message='Move the explicitly selected PIPE port to the retained port and use its NodeNumber.',
        branch_name=moving.branch_name, node_numbers=(moving.node_number, target.node_number),
        owner_node_number=target.node_number, absorbed_node_numbers=(moving.node_number,),
        proposed_changes=({'moveKey':moving.key, 'targetKey':target.key},))
    # A manual decision resolves this exact pair's ambiguity, not other blocked findings.
    owners = [o for o in result.document.occurrences if moving in o.records or target in o.records]
    owner_keys = {n.key for o in owners for n in o.records}
    addressed = {finding.finding_id} | {
        f.finding_id for f in result.findings
        if (f.code == 'COLLINEAR_ROUTE_OVERLAP' and set(f.node_keys) <= owner_keys)
        or (f.code in {'SHORT_ROUTE_SPAN', 'ZERO_LENGTH_ROUTE_SPAN'} and set(f.node_keys) == pair)
    }
    actions = tuple(a for a in result.fix_actions if not (set(a.finding_ids) & addressed))
    return replace(result, fix_actions=actions + (action,))
