from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable, Sequence

from .models import (
    ComponentOccurrence,
    DEFINITELY_NON_RIGID_TYPES,
    Finding,
    INLINE_TYPES,
    NodeRecord,
    Position,
    Psi116Document,
    ResolverConfig,
    RouteSpan,
    SPECIAL_TYPES,
)
from .parser import _occurrence_route_nodes, _preferred_occurrence_node


def _position_bucket(position: Position, tolerance: float) -> tuple[int, int, int]:
    scale = tolerance if tolerance > 0 else 1e-9
    return tuple(int(round(value / scale)) for value in (position.x, position.y, position.z))


def _unique_ints(values: Iterable[int | None]) -> tuple[int, ...]:
    return tuple(sorted({value for value in values if value is not None}))


def _unique_text(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _finding_factory() -> tuple[list[Finding], Callable[..., Finding]]:
    findings: list[Finding] = []

    def add(code: str, severity: str, blocking: bool, message: str, **kwargs: object) -> Finding:
        finding = Finding(
            finding_id=f"FND-{len(findings) + 1:06d}",
            code=code,
            severity=severity,
            blocking=blocking,
            message=message,
            **kwargs,
        )
        findings.append(finding)
        return finding

    return findings, add


def _node_priority(node: NodeRecord) -> tuple[int, int, int, int, int]:
    semantic_priority = {
        "TEE": 1000,
        "OLET": 990,
        "ELBO": 980,
        "REDU": 970,
        "BRAN": 960,
        "ATTA": 900,
        "VALV": 850,
        "FLAN": 840,
        "GASK": 830,
        "INST": 820,
        "RIGID": 810,
        "PIPE": 500,
    }.get(node.semantic_type, 400)
    return (
        semantic_priority,
        1 if node.endpoint == 0 else 0,
        1 if node.has_restraint else 0,
        1 if node.node_name else 0,
        -(node.node_number or 0),
    )


def _preferred_owner(nodes: Sequence[NodeRecord]) -> NodeRecord | None:
    positive = [node for node in nodes if node.positive]
    return max(positive, key=_node_priority) if positive else None


def _occurrence_by_node_key(document: Psi116Document) -> dict[str, ComponentOccurrence]:
    return {
        record.key: occurrence
        for occurrence in document.occurrences
        for record in occurrence.records
    }


def _branch_endpoint_keys(document: Psi116Document) -> set[str]:
    keys: set[str] = set()
    occurrences_by_branch: dict[int, list[ComponentOccurrence]] = defaultdict(list)
    for occurrence in document.occurrences:
        occurrences_by_branch[occurrence.branch_index].append(occurrence)
    for occurrences in occurrences_by_branch.values():
        route_occurrences = [(occurrence, _occurrence_route_nodes(occurrence)) for occurrence in occurrences]
        route_occurrences = [(occurrence, nodes) for occurrence, nodes in route_occurrences if nodes]
        if not route_occurrences:
            continue
        keys.add(route_occurrences[0][1][0].key)
        keys.add(route_occurrences[-1][1][-1].key)
    return keys


def _pipe_endpoint_keys(document: Psi116Document) -> set[str]:
    keys: set[str] = set()
    for occurrence in document.occurrences:
        if occurrence.semantic_type != "PIPE":
            continue
        for node in _occurrence_route_nodes(occurrence):
            keys.add(node.key)
    return keys


def _authorized_connection_cluster(
    nodes: Sequence[NodeRecord],
    occurrences: Sequence[ComponentOccurrence],
    branch_endpoint_keys: set[str],
    pipe_endpoint_keys: set[str],
) -> tuple[bool, str, float]:
    occurrence_ids = {occurrence.occurrence_id for occurrence in occurrences}
    if len(occurrence_ids) == 1:
        return True, "SAME_COMPONENT_PORT_CLUSTER", 1.0
    branches = {node.branch_index for node in nodes}
    if any(node.key in pipe_endpoint_keys for node in nodes) and any(node.semantic_type != "PIPE" for node in nodes):
        return True, "PIPE_ENDPOINT_COMPONENT_OWNER", 1.0
    if len(branches) == 1:
        source_indices = sorted({node.source_index for node in nodes})
        if source_indices and source_indices[-1] - source_indices[0] <= max(3, len(source_indices) + 1):
            return True, "CONTIGUOUS_BRANCH_COMPONENT_STACK", 0.95
    if any(node.key in branch_endpoint_keys for node in nodes) and any(node.semantic_type in SPECIAL_TYPES for node in nodes):
        return True, "BRANCH_ENDPOINT_SPECIAL_COMPONENT", 0.95
    if len(branches) > 1 and any(node.semantic_type in {"TEE", "OLET", "ELBO", "REDU", "BRAN"} for node in nodes):
        return True, "CROSS_BRANCH_SPECIAL_COMPONENT", 0.90
    return False, "NO_EXPLICIT_CONNECTION_AUTHORITY", 0.0


def _analyze_coincident_nodes(document: Psi116Document, config: ResolverConfig, add: Callable[..., Finding]) -> None:
    groups: dict[tuple[int, int, int], list[NodeRecord]] = defaultdict(list)
    occurrence_by_key = _occurrence_by_node_key(document)
    branch_endpoint_keys = _branch_endpoint_keys(document)
    pipe_endpoint_keys = _pipe_endpoint_keys(document)
    for branch in document.branches:
        for node in branch.nodes:
            if node.positive and node.position is not None:
                groups[_position_bucket(node.position, config.connection_tolerance_mm)].append(node)
    for nodes in groups.values():
        numbers = _unique_ints(node.node_number for node in nodes)
        if len(numbers) < 2:
            continue
        max_distance = max(
            left.position.distance_to(right.position)
            for index, left in enumerate(nodes)
            for right in nodes[index + 1:]
            if left.position is not None and right.position is not None
        )
        if max_distance > config.connection_tolerance_mm:
            continue
        occurrences = list({occurrence_by_key[node.key].occurrence_id: occurrence_by_key[node.key] for node in nodes}.values())
        authorized, authority, confidence = _authorized_connection_cluster(nodes, occurrences, branch_endpoint_keys, pipe_endpoint_keys)
        owner = _preferred_owner(nodes)
        refs = _unique_text(node.component_ref_no for node in nodes)
        if len(occurrences) == 1:
            occurrence = occurrences[0]
            add(
                "COMPONENT_PORTS_COINCIDENT",
                "INFO",
                False,
                f"{occurrence.semantic_type} occurrence contains coincident positive port records; they are component evidence, not route elements.",
                branch_name=occurrence.branch_name,
                node_keys=tuple(node.key for node in nodes),
                node_numbers=numbers,
                component_ref_nos=refs,
                details={
                    "occurrenceId": occurrence.occurrence_id,
                    "semanticType": occurrence.semantic_type,
                    "maximumResidualMm": max_distance,
                },
            )
        elif authorized and owner:
            add(
                "COINCIDENT_NODE_ALIAS_CANDIDATE",
                "WARNING",
                False,
                f"Coincident connection cluster can be canonicalized to Node {owner.node_number}.",
                branch_name=owner.branch_name,
                node_keys=tuple(node.key for node in nodes),
                node_numbers=numbers,
                component_ref_nos=refs,
                details={
                    "ownerNodeNumber": owner.node_number,
                    "ownerType": owner.semantic_type,
                    "maximumResidualMm": max_distance,
                    "crossBranch": len({node.branch_index for node in nodes}) > 1,
                    "connectionAuthority": authority,
                    "confidence": confidence,
                    "occurrenceIds": sorted(occurrence.occurrence_id for occurrence in occurrences),
                },
            )
        else:
            add(
                "COINCIDENT_NODE_IDENTITY_AMBIGUOUS",
                "ERROR",
                True,
                "Coincident positive nodes have no verified branch/component connection authority.",
                branch_name=nodes[0].branch_name,
                node_keys=tuple(node.key for node in nodes),
                node_numbers=numbers,
                component_ref_nos=refs,
                details={
                    "maximumResidualMm": max_distance,
                    "connectionAuthority": authority,
                    "occurrenceIds": sorted(occurrence.occurrence_id for occurrence in occurrences),
                },
            )


def _analyze_spans(document: Psi116Document, config: ResolverConfig, add: Callable[..., Finding]) -> None:
    for span in document.spans:
        if span.length_mm <= config.exact_coincidence_tolerance_mm:
            owner = _preferred_owner((span.from_node, span.to_node))
            component_internal = span.span_role == "COMPONENT_INTERNAL"
            add(
                "ZERO_LENGTH_COMPONENT_SPAN" if component_internal else "ZERO_LENGTH_ROUTE_SPAN",
                "WARNING" if not component_internal else "ERROR",
                component_internal,
                "Component endpoints collapse to one position."
                if component_internal else "Adjacent component occurrences share a zero-length route connection.",
                branch_name=span.branch_name,
                node_keys=(span.from_node.key, span.to_node.key),
                node_numbers=_unique_ints((span.from_node.node_number, span.to_node.node_number)),
                component_ref_nos=_unique_text((span.from_node.component_ref_no, span.to_node.component_ref_no)),
                span_ids=(span.span_id,),
                length_mm=span.length_mm,
                details={
                    "fromType": span.from_node.semantic_type,
                    "toType": span.to_node.semantic_type,
                    "spanRole": span.span_role,
                    "occurrenceIds": list(span.occurrence_ids),
                    "preferredOwnerNodeNumber": owner.node_number if owner else None,
                },
            )
        elif span.length_mm < config.short_span_threshold_mm:
            inline_internal = span.span_role == "COMPONENT_INTERNAL" and (
                span.from_node.semantic_type in INLINE_TYPES or span.to_node.semantic_type in INLINE_TYPES
            )
            add(
                "SHORT_INLINE_COMPONENT_SPAN" if inline_internal else "SHORT_ROUTE_SPAN",
                "INFO" if inline_internal else "WARNING",
                False,
                "Finite inline component is shorter than the generic short-span threshold and must be retained."
                if inline_internal else f"Route connection is shorter than {config.short_span_threshold_mm:g} mm and requires semantic disposition.",
                branch_name=span.branch_name,
                node_keys=(span.from_node.key, span.to_node.key),
                node_numbers=_unique_ints((span.from_node.node_number, span.to_node.node_number)),
                component_ref_nos=_unique_text((span.from_node.component_ref_no, span.to_node.component_ref_no)),
                span_ids=(span.span_id,),
                length_mm=span.length_mm,
                details={
                    "fromType": span.from_node.semantic_type,
                    "toType": span.to_node.semantic_type,
                    "spanRole": span.span_role,
                    "occurrenceIds": list(span.occurrence_ids),
                },
            )


def _analyze_rigids(document: Psi116Document, add: Callable[..., Finding]) -> None:
    for branch in document.branches:
        for node in branch.nodes:
            if node.rigid != 2:
                continue
            semantic = node.semantic_type
            if semantic in DEFINITELY_NON_RIGID_TYPES:
                add(
                    "NON_RIGID_COMPONENT_CLASSIFIED_RIGID",
                    "ERROR",
                    False,
                    f"{semantic} Node {node.node_number} is marked Rigid=2 without a rigid component class.",
                    branch_name=node.branch_name,
                    node_keys=(node.key,),
                    node_numbers=_unique_ints((node.node_number,)),
                    component_ref_nos=_unique_text((node.component_ref_no,)),
                    details={"componentType": semantic, "rigid": node.rigid, "weight": node.weight},
                )
            elif semantic == "INST":
                add(
                    "INSTRUMENT_RIGID_EVIDENCE_REQUIRED",
                    "WARNING",
                    True,
                    "Instrument is marked rigid but PSI116 type alone is insufficient evidence for rigid-body projection.",
                    branch_name=node.branch_name,
                    node_keys=(node.key,),
                    node_numbers=_unique_ints((node.node_number,)),
                    component_ref_nos=_unique_text((node.component_ref_no,)),
                    details={"componentType": semantic, "rigid": node.rigid, "weight": node.weight},
                )


def _analyze_occurrences(document: Psi116Document, add: Callable[..., Finding]) -> None:
    for occurrence in document.occurrences:
        endpoints = set(occurrence.endpoint_set)
        positive = occurrence.positive_node_numbers
        if occurrence.semantic_type == "ELBO":
            if 0 not in endpoints:
                add(
                    "ELBO_OWNER_ENDPOINT_MISSING",
                    "ERROR",
                    True,
                    "Elbow occurrence has no Endpoint=0 engineering owner.",
                    branch_name=occurrence.branch_name,
                    node_keys=tuple(record.key for record in occurrence.records),
                    node_numbers=positive,
                    component_ref_nos=_unique_text((occurrence.component_ref_no,)),
                    details={"occurrenceId": occurrence.occurrence_id, "endpointSet": sorted(endpoints)},
                )
            missing_helpers = sorted({1, 2} - endpoints)
            if missing_helpers:
                add(
                    "ELBO_HELPER_PORTS_MISSING",
                    "WARNING",
                    False,
                    "Elbow occurrence lacks one or more PSI116 helper/tangent endpoints.",
                    branch_name=occurrence.branch_name,
                    node_keys=tuple(record.key for record in occurrence.records),
                    node_numbers=positive,
                    component_ref_nos=_unique_text((occurrence.component_ref_no,)),
                    details={
                        "occurrenceId": occurrence.occurrence_id,
                        "endpointSet": sorted(endpoints),
                        "missingEndpoints": missing_helpers,
                    },
                )
        if occurrence.semantic_type in {"TEE", "OLET"} and 0 not in endpoints and positive:
            preferred = _preferred_occurrence_node(occurrence)
            add(
                "JUNCTION_OWNER_INFERRED_FROM_PORT_SET",
                "WARNING",
                False,
                f"{occurrence.semantic_type} has no Endpoint=0 record; a deterministic positive port is retained as junction evidence.",
                branch_name=occurrence.branch_name,
                node_keys=tuple(record.key for record in occurrence.records),
                node_numbers=positive,
                component_ref_nos=_unique_text((occurrence.component_ref_no,)),
                details={
                    "occurrenceId": occurrence.occurrence_id,
                    "semanticType": occurrence.semantic_type,
                    "endpointSet": sorted(endpoints),
                    "preferredNodeNumber": preferred.node_number if preferred else None,
                    "confidence": 0.8,
                },
            )
