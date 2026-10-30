"""Preview-only PSI116 connection-gap evidence; never implies solver connectivity.

Only adjacent distinct PIPE occurrence route joins and branch end-port pairs are examined.
3D distance is a candidate signal, not ownership or design-intent authority. No XML edits.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from .models import Finding, NodeRecord, Psi116Document, ResolverConfig
from .parser import _occurrence_route_nodes

def _branch_endpoints(doc: Psi116Document) -> tuple[tuple[str, NodeRecord], ...]:
    per_branch = defaultdict(list)
    for occurrence in doc.occurrences:
        anchors = _occurrence_route_nodes(occurrence)
        if anchors:
            per_branch[occurrence.branch_index].append((occurrence, anchors))
    endpoints = []
    for index in sorted(per_branch):
        route = per_branch[index]
        first = route[0][1][0]
        last = route[-1][1][-1]
        endpoints.append(("START", first))
        if last.key != first.key:
            endpoints.append(("END", last))
    return tuple(endpoints)

def _analyze_connection_gaps(
    doc: Psi116Document, config: ResolverConfig, add: Callable[..., Finding], resolutions=None
) -> None:
    """Emit review candidates, not false claims of confirmed disconnection.

    Near miss is > connection tolerance and <= short-span screening window.
    A long separation is NOT classified as a gap without an authoritative
    connection reference, because it may be a correctly modeled pipe length.
    """
    tolerance = config.connection_tolerance_mm
    screening = config.joint_repair_threshold_mm
    for span in doc.spans:
        if (span.span_role != "ROUTE_CONNECTION"
            or span.from_node.semantic_type != "PIPE"
            or span.to_node.semantic_type != "PIPE"
            or len(set(span.occurrence_ids)) != 2
            or not (tolerance < span.length_mm <= screening)):
            continue
        add(
            "NEAR_MISS_PIPE_JOINT", "WARNING", False,
            f"Adjacent source PIPE occurrences have a {span.length_mm:.3f} mm 3D separation "
            "at their inferred route join. Verify whether this is an unintended gap.",
            branch_name=span.branch_name,
            node_keys=(span.from_node.key, span.to_node.key),
            node_numbers=tuple(sorted({v for v in (
                span.from_node.node_number, span.to_node.node_number) if v is not None})),
            component_ref_nos=tuple(sorted({v for v in (
                span.from_node.component_ref_no, span.to_node.component_ref_no) if v})),
            span_ids=(span.span_id,), length_mm=span.length_mm,
            details={"gapMm":span.length_mm, "fromXYZ":span.from_node.position.as_list(),
                     "toXYZ":span.to_node.position.as_list(),
                     "connectionAuthority":"INFERRED_SOURCE_ORDER_ONLY",
                     "certainty":"POSSIBLE_GAP_REQUIRES_REVIEW",
                     "autofixAuthorized":False},
        )

    endpoints = _branch_endpoints(doc)
    records = [n for b in doc.branches for n in b.nodes]
    used_pairs = set()
    for index, (role, node) in enumerate(endpoints):
        if node.position is None:
            continue
        shared = [n for n in records if n.branch_index != node.branch_index and n.positive
                  and n.node_number == node.node_number and n.position and
                  n.position.distance_to(node.position) <= tolerance]
        closed = [n for n in records if n.branch_index in {node.branch_index, *(s.branch_index for s in shared)} and
                  n.connection_type == 'CLOS' and n.position and
                  n.position.distance_to(node.position) <= tolerance]
        if shared and closed:
            add('CONNECTION_DECLARATION_CONFLICT','WARNING',False,
                'Shared connection identity conflicts with explicit CLOS evidence; review the branch end declaration.',
                branch_name=node.branch_name,node_keys=tuple(sorted({node.key, *(n.key for n in shared+closed)})),
                node_numbers=(node.node_number,),details={'connectionAuthority':'CONFLICTING_SOURCE_DECLARATIONS',
                    'autofixAuthorized':False})
            continue
        if shared or closed:
            if resolutions is not None:
                resolutions.append({'code':'EXISTING_CONNECTION' if shared else 'DECLARED_CLOSED_END',
                    'node_keys':sorted({node.key, *(n.key for n in shared or closed)}),
                    'message':'Shared source NodeNumber and position establish an existing connection.' if shared else
                              'Source CLOS evidence establishes a declared closed termination.',
                    'authority':'SOURCE_NODE_IDENTITY_AND_XYZ' if shared else 'SOURCE_CLOS',
                    'xmlChanged':False})
            continue
        peers = [(other_role, other, node.position.distance_to(other.position))
                 for j,(other_role,other) in enumerate(endpoints)
                 if j != index and other.branch_index != node.branch_index
                 and other.position is not None]
        peers.sort(key=lambda item:(item[2],item[1].branch_index,item[1].source_index))
        aligned = [item for item in peers if item[2] <= tolerance]
        if aligned:
            # Exact 3D alignment alone is not evidence of a valid routed joint.
            # Do not diagnose a disconnection or automatically merge the endpoints.
            continue
        if (peers and node.semantic_type == "PIPE"
            and peers[0][1].semantic_type == "PIPE"
            and tolerance < peers[0][2] <= screening):
            other_role, other, distance = peers[0]
            pair = tuple(sorted((node.key, other.key)))
            if pair not in used_pairs:
                used_pairs.add(pair)
                add(
                    "NEAR_MISS_BRANCH_ENDS", "WARNING", False,
                    f"PIPE branch endpoints are {distance:.3f} mm apart in 3D; "
                    "verify design intent and branch connectivity before joining.",
                    branch_name=node.branch_name,
                    node_keys=pair,
                    node_numbers=tuple(sorted({v for v in (
                        node.node_number,other.node_number) if v is not None})),
                    component_ref_nos=tuple(sorted({v for v in (
                        node.component_ref_no,other.component_ref_no) if v})),
                    length_mm=distance,
                    details={"gapMm":distance, "fromBranch":node.branch_index,
                             "toBranch":other.branch_index,
                             "connectionAuthority":"NO_EXPLICIT_BRANCH_LINK",
                             "certainty":"POSSIBLE_GAP_REQUIRES_REVIEW",
                             "autofixAuthorized":False},
                )
            continue

        nearest_record = min(((node.position.distance_to(n.position),n.key) for n in records
            if n.branch_index != node.branch_index and n.position), default=(None,None), key=lambda x:x[0])
        add(
            "BRANCH_END_UNVERIFIED", "INFO", False,
            f"Branch {role.lower()} at Node {node.node_number} has no matching "
            "other-branch endpoint within the connection tolerance. It may be an "
            "intentional termination; an open connection is not proven.",
            branch_name=node.branch_name,
            node_keys=(node.key,),
            node_numbers=(node.node_number,) if node.node_number is not None else (),
            component_ref_nos=(node.component_ref_no,) if node.component_ref_no else (),
            details={"endRole":role, "XYZ":node.position.as_list(),
                     "nearestOtherBranchEndMm":peers[0][2] if peers else None,
                     "nearestSourceRecordMm":nearest_record[0],
                     "nearestSourceRecordKey":nearest_record[1],
                     "connectionToleranceMm":tolerance,
                     "connectionAuthority":"NOT_ESTABLISHED",
                     "certainty":"TERMINATION_INTENT_UNKNOWN",
                     "autofixAuthorized":False},
        )
