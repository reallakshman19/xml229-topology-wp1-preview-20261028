from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Sequence

from .analysis import _preferred_owner, _unique_ints
from .removal_policy import can_remove_plain_pipe
from .models import (
    Finding,
    FixAction,
    INLINE_TYPES,
    NodeRecord,
    Psi116Document,
    ResolverConfig,
    RouteSpan,
    SPECIAL_TYPES,
)


def _node_index(document: Psi116Document) -> dict[int, list[NodeRecord]]:
    index: dict[int, list[NodeRecord]] = defaultdict(list)
    for branch in document.branches:
        for node in branch.nodes:
            if node.node_number is not None:
                index[node.node_number].append(node)
    return index


def _span_index(document: Psi116Document) -> dict[str, RouteSpan]:
    return {span.span_id: span for span in document.spans}


def _build_fix_actions(document: Psi116Document, findings: Sequence[Finding],
                       config: ResolverConfig | None = None) -> tuple[FixAction, ...]:
    nodes_by_number = _node_index(document)
    spans_by_id = _span_index(document)
    actions: list[FixAction] = []
    for finding in findings:
        disposition = "BLOCK_AMBIGUOUS"
        status = "BLOCKED"
        confidence = 0.0
        authority = "UNRESOLVED"
        message = finding.message
        owner_number: int | None = None
        absorbed: tuple[int, ...] = ()
        changes: tuple[dict[str, object], ...] = ()
        blockers: tuple[str, ...] = (finding.code,) if finding.blocking else ()

        if finding.code == 'PORT_CONNECTION_WITHIN_TOLERANCE':
            disposition, status, confidence = 'CLOSE_PORT_CONNECTION', 'PROPOSED', 1.0
            authority = 'OWNER_PORT_CONNECTION_LE_25_MM'
            changes = (finding.details['portRepair'],)
            message = finding.message
            blockers = ()
        elif finding.code == "COINCIDENT_NODE_ALIAS_CANDIDATE":
            owner_number = int(finding.details.get("ownerNodeNumber"))
            absorbed = tuple(number for number in finding.node_numbers if number != owner_number)
            disposition, status, confidence = "ALIAS_COINCIDENT_NODE", "PROPOSED", 1.0
            authority = "UNIQUE_SPECIAL_COMPONENT_OWNER"
            message = f"Canonicalize coincident node identities to Node {owner_number}; retain every source node in the ledger."
            changes = tuple({"operation": "ALIAS_NODE", "sourceNode": number, "canonicalNode": owner_number} for number in absorbed)
            blockers = ()
        elif finding.code in {"ZERO_LENGTH_ROUTE_SPAN", "ZERO_LENGTH_COMPONENT_SPAN", "SHORT_ROUTE_SPAN", "SHORT_INLINE_COMPONENT_SPAN"}:
            span = spans_by_id.get(finding.span_ids[0]) if finding.span_ids else None
            if span:
                nodes = (span.from_node, span.to_node)
                owner = _preferred_owner(nodes)
                endpoint_types = {node.semantic_type for node in nodes}
                if finding.code == "SHORT_INLINE_COMPONENT_SPAN" or "GASK" in endpoint_types or endpoint_types & INLINE_TYPES:
                    disposition, status, confidence = "KEEP", "PROPOSED", 1.0
                    authority = "FINITE_INLINE_OR_GASKET_LENGTH"
                    message = "Retain the finite inline/gasket span; the generic 6 mm threshold does not authorize contraction."
                    blockers = ()
                elif "ATTA" in endpoint_types and span.length_mm <= ResolverConfig.connection_tolerance_mm:
                    disposition, status, confidence = "KEEP", "PROPOSED", 1.0
                    authority = "SUPPORT_CONNECTION_CLUSTER_HANDLED_BY_ALIAS_PLAN"
                    message = "Retain support evidence; coincident/near-coincident node aliasing is planned at the connection cluster level."
                    blockers = ()
                elif owner and owner.semantic_type in SPECIAL_TYPES:
                    other = span.to_node if owner is span.from_node else span.from_node
                    disposition, status, confidence = "CONTRACT_PRESERVE_OWNER", "PROPOSED", 1.0
                    authority = "SPECIAL_COMPONENT_OWNS_COINCIDENT_OR_SHORT_SPAN"
                    owner_number = owner.node_number
                    absorbed = _unique_ints((other.node_number,))
                    message = f"Contract span while retaining {owner.semantic_type} owner Node {owner.node_number}."
                    changes = ({
                        "operation": "CONTRACT_SPAN",
                        "ownerNode": owner.node_number,
                        "absorbedNode": other.node_number,
                        "transfer": ["NodeName", "Restraint", "Weight", "ProcessBoundary", "SourceTrace"],
                    },)
                    blockers = ()
                elif all(node.semantic_type == "PIPE" for node in nodes):
                    candidate = min(nodes, key=lambda node: (1 if node.carries_engineering_semantics else 0, node.source_index))
                    if not candidate.carries_engineering_semantics:
                        owner = span.to_node if candidate is span.from_node else span.from_node
                        disposition, status, confidence = "SAFE_DROP_PIPE_GEOMETRY", "PROPOSED", 0.95
                        authority = "PLAIN_PIPE_NODE_WITHOUT_ENGINEERING_SEMANTICS"
                        owner_number = owner.node_number
                        absorbed = _unique_ints((candidate.node_number,))
                        message = f"Remove plain pipe geometry Node {candidate.node_number} after preserving source disposition evidence."
                        changes = ({"operation": "DROP_PLAIN_PIPE_NODE", "sourceNode": candidate.node_number, "retainedNode": owner.node_number},)
                        blockers = ()
                    else:
                        blockers = ("BOTH_PIPE_NODES_CARRY_ENGINEERING_SEMANTICS",)
                elif any(node.semantic_type in INLINE_TYPES for node in nodes):
                    disposition, status, confidence = "KEEP", "PROPOSED", 1.0
                    authority = "FINITE_INLINE_COMPONENT_MAY_BE_SHORT"
                    message = "Retain the short span; inline component length cannot be discarded solely by threshold."
                    blockers = ()
        elif finding.code == "NON_RIGID_COMPONENT_CLASSIFIED_RIGID":
            node = next((
                node for number in finding.node_numbers
                for node in nodes_by_number.get(number, [])
                if node.key in finding.node_keys
            ), None)
            disposition, status, confidence = "REMOVE_FALSE_RIGID", "PROPOSED", 0.95
            authority = "COMPONENT_CLASS_PROHIBITS_RIGID_TYPE_ONLY_INFERENCE"
            message = "Set Rigid to 0 only in a future transactional clone; retain source value and decision evidence."
            if node:
                changes = ({"operation": "SET_RIGID", "nodeNumber": node.node_number, "before": node.rigid, "after": 0},)
            blockers = ()
        elif finding.code in {
            "ELBO_HELPER_PORTS_MISSING",
            "JUNCTION_OWNER_INFERRED_FROM_PORT_SET",
            "COMPONENT_PORTS_COINCIDENT",
            "SUPPORT_ON_PIPE_CARRIER",
            "JUNCTION_ON_PIPE_CARRIER",
        }:
            disposition, status, confidence = "KEEP", "PROPOSED", 1.0
            authority = "COMPONENT_PORT_EVIDENCE_PRESERVED"
            message = "Preserve the component evidence; the resolver foundation does not fabricate or delete component ports."
            blockers = ()
        elif finding.code == "AUTO_PIPE_INLINE_COMPONENT_CARRIER":
            disposition, status, confidence = "MERGE_CARRIER_WITH_COMPONENT", "PROPOSED", 0.95
            authority = "AUTO_GENERATED_PIPE_COMPONENT_SPAN"
            message = "Retain both source identities and project the auto-pipe carrier and inline component with explicit MANY_TO_ONE lineage."
            blockers = ()
        elif finding.code in {"DUPLICATE_ROUTE_SPAN", "COLLINEAR_ROUTE_OVERLAP"}:
            blockers = ("OVERLAP_OWNERSHIP_NOT_PROVEN",)
        elif finding.code in {"NEAR_MISS_PIPE_JOINT", "NEAR_MISS_BRANCH_ENDS", "BRANCH_END_UNVERIFIED", "CONNECTION_DECLARATION_CONFLICT"}:
            # Gap evidence is a screening result, never a source-connection authority.
            # Keep it nonblocking to avoid vetoing unrelated, validated transactions.
            disposition, status, confidence = "REVIEW_CONNECTION", "PROPOSED", 0.0
            authority = "DESIGN_TERMINATION_AND_CONNECTIVITY_UNVERIFIED"
            message = "Review endpoint positions and design intent in the source model; never join nodes by proximity alone."
            blockers = ()
        elif not finding.blocking:
            disposition, status, confidence = "KEEP", "PROPOSED", 1.0
            authority = "DIAGNOSTIC_ONLY"
            blockers = ()

        actions.append(FixAction(
            action_id=f"ACT-{len(actions) + 1:06d}",
            finding_ids=(finding.finding_id,),
            disposition=disposition,
            status=status,
            confidence=confidence,
            authority=authority,
            message=message,
            branch_name=finding.branch_name,
            node_numbers=finding.node_numbers,
            component_ref_nos=finding.component_ref_nos,
            span_ids=finding.span_ids,
            owner_node_number=owner_number,
            absorbed_node_numbers=absorbed,
            proposed_changes=changes,
            blockers=blockers,
        ))
    return _coalesce_fix_actions(actions, document, findings, config or ResolverConfig())


def _removal_review(action: FixAction, records: dict[str, NodeRecord],
                    finding_keys: dict[str, tuple[str, ...]],
                    config: ResolverConfig) -> tuple[bool, str, str]:
    keys = {key for fid in action.finding_ids for key in finding_keys.get(fid, ())}
    witnesses = [records[key] for key in keys if key in records]
    owners = [n for n in witnesses if n.node_number == action.owner_node_number]
    absorbed = [n for n in witnesses if n.node_number in action.absorbed_node_numbers]
    if len(owners) != 1 or len(absorbed) != 1:
        return False, "SOURCE_RECORD_NOT_UNIQUE", (
            "Preserve the original records: a unique absorbed PIPE and owner are not proven. "
            "Review the source-qualified occurrences and design ownership, then re-export and rerun TopoFix.")
    record, owner = absorbed[0], owners[0]
    safe, reason = can_remove_plain_pipe(record, owner, config)
    message = (
        f"Preserve {record.semantic_type} {record.key}: removal is not authorized ({reason}). "
        f"Original NodeName={record.node_name!r}, ComponentRefNo={record.component_ref_no!r}, "
        f"OD={record.outside_diameter}, wall={record.wall_thickness}; "
        f"owner {owner.key} ({owner.semantic_type}) has OD={owner.outside_diameter}, wall={owner.wall_thickness}. "
        "Verify source-model identity and the property boundary against the authoritative design. "
        "Correct or preserve only under that authority; do not clear engineering fields to permit deletion. "
        "After an authorized correction, re-export and rerun full TopoFix.")
    return safe, reason, message


def _coalesce_fix_actions(actions: Sequence[FixAction], document: Psi116Document,
                         findings: Sequence[Finding], config: ResolverConfig) -> tuple[FixAction, ...]:
    """Collapse duplicate exact-coincidence operations into one deterministic plan action."""
    alias_index: dict[tuple[int | None, frozenset[int]], int] = {}
    merged: list[FixAction] = []
    records = {node.key: node for branch in document.branches for node in branch.nodes}
    finding_keys = {finding.finding_id: finding.node_keys for finding in findings}

    for action in actions:
        node_set = frozenset(action.node_numbers)
        key = (action.owner_node_number, node_set)
        if action.disposition == "ALIAS_COINCIDENT_NODE":
            alias_index[key] = len(merged)
            merged.append(action)
            continue
        if action.disposition == "CONTRACT_PRESERVE_OWNER" and key in alias_index:
            index = alias_index[key]
            alias = merged[index]
            combined = FixAction(
                action_id=alias.action_id,
                finding_ids=tuple(sorted(set(alias.finding_ids + action.finding_ids))),
                disposition="SAFE_DROP_PIPE_GEOMETRY",
                status=alias.status,
                confidence=min(alias.confidence, action.confidence),
                authority="COINCIDENT_SPECIAL_OWNER_PLAIN_PIPE_CONTRACTION",
                message=(
                    f"Remove the disposable plain-pipe record at coincident Node identity while retaining "
                    f"special-component owner Node {alias.owner_node_number} and all engineering evidence."
                ),
                branch_name=alias.branch_name or action.branch_name,
                node_numbers=tuple(sorted(set(alias.node_numbers + action.node_numbers))),
                component_ref_nos=tuple(sorted(set(alias.component_ref_nos + action.component_ref_nos))),
                span_ids=tuple(sorted(set(alias.span_ids + action.span_ids))),
                owner_node_number=alias.owner_node_number,
                absorbed_node_numbers=tuple(sorted(set(alias.absorbed_node_numbers + action.absorbed_node_numbers))),
                proposed_changes=action.proposed_changes,
                blockers=(),
            )
            safe, reason, review_message = _removal_review(combined, records, finding_keys, config)
            if not safe:
                combined = replace(combined, disposition="REVIEW_SOURCE_RECORD", confidence=0.0,
                                   authority=reason, message=review_message, proposed_changes=())
            merged[index] = combined
            continue
        merged.append(action)

    return tuple(
        FixAction(
            action_id=f"ACT-{index + 1:06d}",
            finding_ids=action.finding_ids,
            disposition=action.disposition,
            status=action.status,
            confidence=action.confidence,
            authority=action.authority,
            message=action.message,
            branch_name=action.branch_name,
            node_numbers=action.node_numbers,
            component_ref_nos=action.component_ref_nos,
            span_ids=action.span_ids,
            owner_node_number=action.owner_node_number,
            absorbed_node_numbers=action.absorbed_node_numbers,
            proposed_changes=action.proposed_changes,
            blockers=action.blockers,
        )
        for index, action in enumerate(merged)
    )
