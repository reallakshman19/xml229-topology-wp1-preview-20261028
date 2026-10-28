from __future__ import annotations

from collections import defaultdict
from typing import Callable

from .analysis import _unique_ints, _unique_text
from .models import Finding, INLINE_TYPES, Position, Psi116Document, ResolverConfig, RouteSpan
from .parser import _preferred_occurrence_node


def _point_segment_projection(point: Position, start: Position, end: Position) -> tuple[float, float, Position]:
    vx, vy, vz = end.x - start.x, end.y - start.y, end.z - start.z
    length_sq = vx * vx + vy * vy + vz * vz
    if length_sq <= 1e-18:
        return 0.0, point.distance_to(start), start
    wx, wy, wz = point.x - start.x, point.y - start.y, point.z - start.z
    t = (wx * vx + wy * vy + wz * vz) / length_sq
    clamped = min(1.0, max(0.0, t))
    projected = Position(start.x + clamped * vx, start.y + clamped * vy, start.z + clamped * vz)
    return t, point.distance_to(projected), projected


def _occurrence_order(document: Psi116Document) -> dict[str, int]:
    order: dict[str, int] = {}
    per_branch: dict[int, int] = defaultdict(int)
    for occurrence in document.occurrences:
        per_branch[occurrence.branch_index] += 1
        order[occurrence.occurrence_id] = per_branch[occurrence.branch_index]
    return order


def _analyze_pipe_carriers(document: Psi116Document, config: ResolverConfig, add: Callable[..., Finding]) -> None:
    pipe_spans = [
        span for span in document.spans
        if span.span_role == "COMPONENT_INTERNAL" and span.from_node.semantic_type == "PIPE"
    ]
    occurrence_order = _occurrence_order(document)
    occurrence_by_id = {occurrence.occurrence_id: occurrence for occurrence in document.occurrences}
    for occurrence in document.occurrences:
        if occurrence.semantic_type == "PIPE":
            continue
        point_node = _preferred_occurrence_node(occurrence)
        if point_node is None or point_node.position is None:
            continue
        candidates: list[tuple[RouteSpan, float, float, Position]] = []
        for span in pipe_spans:
            if span.branch_index != occurrence.branch_index:
                continue
            if span.from_node.position is None or span.to_node.position is None:
                continue
            t, residual, projected = _point_segment_projection(point_node.position, span.from_node.position, span.to_node.position)
            if residual <= config.connection_tolerance_mm and -1e-9 <= t <= 1.0 + 1e-9:
                candidates.append((span, t, residual, projected))
        if not candidates:
            continue
        candidates.sort(key=lambda row: (row[2], abs(row[1] - 0.5), row[0].span_id))
        span, t, residual, projected = candidates[0]
        at_endpoint = (
            point_node.position.distance_to(span.from_node.position) <= config.connection_tolerance_mm
            or point_node.position.distance_to(span.to_node.position) <= config.connection_tolerance_mm
        )
        details = {
            "occurrenceId": occurrence.occurrence_id,
            "semanticType": occurrence.semantic_type,
            "carrierSpanId": span.span_id,
            "carrierOccurrenceId": span.occurrence_ids[0],
            "carrierFromNode": span.from_node.node_number,
            "carrierToNode": span.to_node.node_number,
            "projectionParameter": t,
            "projectionResidualMm": residual,
            "projectedPosition": [projected.x, projected.y, projected.z],
            "atCarrierEndpoint": at_endpoint,
        }
        if occurrence.semantic_type == "ATTA":
            add(
                "SUPPORT_ON_PIPE_CARRIER",
                "INFO",
                False,
                "Support is geometrically associated with a finite pipe carrier and can split or attach to that carrier.",
                branch_name=occurrence.branch_name,
                node_keys=(point_node.key,),
                node_numbers=_unique_ints((point_node.node_number,)),
                component_ref_nos=_unique_text((occurrence.component_ref_no,)),
                span_ids=(span.span_id,),
                details=details,
            )
        elif occurrence.semantic_type in {"TEE", "OLET"}:
            add(
                "JUNCTION_ON_PIPE_CARRIER",
                "INFO",
                False,
                f"{occurrence.semantic_type} junction is associated with a finite pipe carrier.",
                branch_name=occurrence.branch_name,
                node_keys=(point_node.key,),
                node_numbers=_unique_ints((point_node.node_number,)),
                component_ref_nos=_unique_text((occurrence.component_ref_no,)),
                span_ids=(span.span_id,),
                details=details,
            )
        elif occurrence.semantic_type in INLINE_TYPES:
            pipe_occurrence = occurrence_by_id[span.occurrence_ids[0]]
            order_gap = abs(occurrence_order[occurrence.occurrence_id] - occurrence_order[pipe_occurrence.occurrence_id])
            if "PIPE AUTO" in pipe_occurrence.component_ref_no.upper() and order_gap <= 4:
                add(
                    "AUTO_PIPE_INLINE_COMPONENT_CARRIER",
                    "WARNING",
                    False,
                    f"Auto-generated pipe span overlaps inline {occurrence.semantic_type} component evidence.",
                    branch_name=occurrence.branch_name,
                    node_keys=(point_node.key, span.from_node.key, span.to_node.key),
                    node_numbers=_unique_ints((point_node.node_number, span.from_node.node_number, span.to_node.node_number)),
                    component_ref_nos=_unique_text((occurrence.component_ref_no, pipe_occurrence.component_ref_no)),
                    span_ids=(span.span_id,),
                    details={**details, "orderGap": order_gap, "projectionCardinality": "MANY_TO_ONE"},
                )


def _canonical_direction(span: RouteSpan) -> tuple[float, float, float] | None:
    if span.length_mm <= 1e-12 or span.from_node.position is None or span.to_node.position is None:
        return None
    vector = (
        (span.to_node.position.x - span.from_node.position.x) / span.length_mm,
        (span.to_node.position.y - span.from_node.position.y) / span.length_mm,
        (span.to_node.position.z - span.from_node.position.z) / span.length_mm,
    )
    for value in vector:
        if abs(value) > 1e-12:
            if value < 0:
                return tuple(-item for item in vector)
            break
    return vector


def _line_group_key(span: RouteSpan, config: ResolverConfig) -> tuple[int, ...] | None:
    direction = _canonical_direction(span)
    start = span.from_node.position
    if direction is None or start is None:
        return None
    dkey = tuple(int(round(item * 1_000_000)) for item in direction)
    moment = (
        start.y * direction[2] - start.z * direction[1],
        start.z * direction[0] - start.x * direction[2],
        start.x * direction[1] - start.y * direction[0],
    )
    tolerance = max(config.collinear_tolerance_mm, 1e-9)
    mkey = tuple(int(round(item / tolerance)) for item in moment)
    return (*dkey, *mkey)


def _projection_interval(span: RouteSpan, direction: tuple[float, float, float]) -> tuple[float, float]:
    assert span.from_node.position is not None and span.to_node.position is not None

    def dot(point: Position) -> float:
        return point.x * direction[0] + point.y * direction[1] + point.z * direction[2]

    values = sorted((dot(span.from_node.position), dot(span.to_node.position)))
    return values[0], values[1]


def _share_node_number(left: RouteSpan, right: RouteSpan) -> bool:
    left_numbers = {left.from_node.node_number, left.to_node.node_number}
    right_numbers = {right.from_node.node_number, right.to_node.node_number}
    return bool((left_numbers & right_numbers) - {None})


def _analyze_overlaps(document: Psi116Document, config: ResolverConfig, add: Callable[..., Finding]) -> None:
    groups: dict[tuple[int, ...], list[RouteSpan]] = defaultdict(list)
    for span in document.spans:
        if span.span_role != "COMPONENT_INTERNAL":
            continue
        key = _line_group_key(span, config)
        if key is not None:
            groups[key].append(span)
    for spans in groups.values():
        if len(spans) < 2:
            continue
        direction = _canonical_direction(spans[0])
        if direction is None:
            continue
        intervals = [(span, *_projection_interval(span, direction)) for span in spans]
        intervals.sort(key=lambda item: (item[1], item[2], item[0].span_id))
        for index, (left, left_start, left_end) in enumerate(intervals):
            for right, right_start, right_end in intervals[index + 1:]:
                if right_start >= left_end - config.exact_coincidence_tolerance_mm:
                    break
                overlap = min(left_end, right_end) - max(left_start, right_start)
                if overlap <= config.exact_coincidence_tolerance_mm:
                    continue
                if set(left.occurrence_ids) == set(right.occurrence_ids):
                    continue
                if left.branch_index == right.branch_index and abs(left.branch_order - right.branch_order) <= 1:
                    continue
                if _share_node_number(left, right) and overlap <= config.connection_tolerance_mm:
                    continue
                exact_duplicate = (
                    abs(left_start - right_start) <= config.connection_tolerance_mm
                    and abs(left_end - right_end) <= config.connection_tolerance_mm
                )
                add(
                    "DUPLICATE_ROUTE_SPAN" if exact_duplicate else "COLLINEAR_ROUTE_OVERLAP",
                    "ERROR",
                    True,
                    "Two PSI116 route spans occupy the same collinear interval."
                    if exact_duplicate else "Two PSI116 route spans overlap along a common centreline.",
                    branch_name=left.branch_name,
                    node_keys=(left.from_node.key, left.to_node.key, right.from_node.key, right.to_node.key),
                    node_numbers=_unique_ints((
                        left.from_node.node_number,
                        left.to_node.node_number,
                        right.from_node.node_number,
                        right.to_node.node_number,
                    )),
                    component_ref_nos=_unique_text((
                        left.from_node.component_ref_no,
                        left.to_node.component_ref_no,
                        right.from_node.component_ref_no,
                        right.to_node.component_ref_no,
                    )),
                    span_ids=(left.span_id, right.span_id),
                    length_mm=overlap,
                    details={
                        "overlapLengthMm": overlap,
                        "exactDuplicate": exact_duplicate,
                        "crossBranch": left.branch_index != right.branch_index,
                        "leftSpanRole": left.span_role,
                        "rightSpanRole": right.span_role,
                    },
                )
