from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import math
from pathlib import Path
import re
from typing import Iterable, Sequence
import xml.etree.ElementTree as ET

from .models import (
    BranchRecord,
    ComponentOccurrence,
    INLINE_TYPES,
    NodeRecord,
    Position,
    Psi116Document,
    RouteSpan,
    TYPE_ALIASES,
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def _parse_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _parse_float(value: str) -> float | None:
    try:
        parsed = float(value.strip())
    except (AttributeError, TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_position(value: str) -> Position | None:
    values = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", value or "")
    if len(values) < 3:
        return None
    numbers = [float(item) for item in values[:3]]
    if not all(math.isfinite(item) for item in numbers):
        return None
    return Position(*numbers)


def _normalize_type(value: str) -> str:
    upper = (value or "").strip().upper()
    return TYPE_ALIASES.get(upper, upper or "PIPE")


def _namespace(root: ET.Element) -> str:
    if root.tag.startswith("{") and "}" in root.tag:
        return root.tag[1:].split("}", 1)[0]
    return ""


def _iter_named(root: ET.Element, name: str) -> Iterable[ET.Element]:
    for element in root.iter():
        if _local_name(element.tag) == name:
            yield element


def read_psi116_xml(source: str | Path, *, source_name: str | None = None) -> Psi116Document:
    if isinstance(source, Path) or (isinstance(source, str) and "<" not in source):
        path = Path(source)
        # Source custody hashes the exact UTF-8 input, including CRLF/lone CR.
        # Text-mode universal-newline translation would forge a different SHA
        # from the browser/Worker even though the source file was unchanged.
        source_text = path.read_bytes().decode("utf-8")
        resolved_source_name = source_name or str(path)
    else:
        source_text = str(source)
        resolved_source_name = source_name or "<memory>"
    root = ET.fromstring(source_text)
    branches: list[BranchRecord] = []
    for branch_index, branch_element in enumerate(_iter_named(root, "Branch")):
        branch_name = _child_text(branch_element, "Branchname")
        nodes: list[NodeRecord] = []
        node_elements = [child for child in branch_element if _local_name(child.tag) == "Node"]
        for source_index, node_element in enumerate(node_elements):
            raw_type = _child_text(node_element, "ComponentType")
            nodes.append(NodeRecord(
                branch_index=branch_index,
                branch_name=branch_name,
                source_index=source_index,
                node_number=_parse_int(_child_text(node_element, "NodeNumber")),
                node_name=_child_text(node_element, "NodeName"),
                endpoint=_parse_int(_child_text(node_element, "Endpoint")),
                component_type=_normalize_type(raw_type),
                raw_component_type=raw_type.strip().upper(),
                component_ref_no=_child_text(node_element, "ComponentRefNo"),
                connection_type=_child_text(node_element, "ConnectionType").upper(),
                position=_parse_position(_child_text(node_element, "Position")),
                rigid=_parse_int(_child_text(node_element, "Rigid")),
                weight=_parse_float(_child_text(node_element, "Weight")),
                outside_diameter=_parse_float(_child_text(node_element, "OutsideDiameter")),
                wall_thickness=_parse_float(_child_text(node_element, "WallThickness")),
                bend_radius=_parse_float(_child_text(node_element, "BendRadius")),
                alpha_angle=_parse_float(_child_text(node_element, "AlphaAngle")),
                has_restraint=any(_local_name(child.tag) == "Restraint" for child in node_element),
                raw_xml=ET.tostring(node_element, encoding="unicode"),
            ))
        branches.append(BranchRecord(branch_index, branch_name, tuple(nodes)))
    occurrences = _build_occurrences(branches)
    spans = _build_spans(branches, occurrences)
    return Psi116Document(
        source_path=resolved_source_name,
        source_text=source_text,
        source_sha256=sha256(source_text.encode("utf-8")).hexdigest(),
        namespace=_namespace(root),
        branches=tuple(branches),
        occurrences=tuple(occurrences),
        spans=tuple(spans),
    )


def _occurrence_group_key(node: NodeRecord) -> tuple[str, str]:
    return node.component_ref_no.strip(), node.semantic_type


def _build_occurrences(branches: Sequence[BranchRecord]) -> list[ComponentOccurrence]:
    occurrences: list[ComponentOccurrence] = []
    for branch in branches:
        current: list[NodeRecord] = []
        current_key: tuple[str, str] | None = None
        sequence = 0
        for node in branch.nodes:
            key = _occurrence_group_key(node)
            if not key[0]:
                if current:
                    sequence += 1
                    occurrences.append(_make_occurrence(branch, sequence, current_key, current))
                    current, current_key = [], None
                sequence += 1
                occurrences.append(_make_occurrence(branch, sequence, key, [node]))
                continue
            if current and key != current_key:
                sequence += 1
                occurrences.append(_make_occurrence(branch, sequence, current_key, current))
                current = []
            current_key = key
            current.append(node)
        if current:
            sequence += 1
            occurrences.append(_make_occurrence(branch, sequence, current_key, current))
    return occurrences


def _make_occurrence(
    branch: BranchRecord,
    sequence: int,
    key: tuple[str, str] | None,
    records: Sequence[NodeRecord],
) -> ComponentOccurrence:
    ref, semantic_type = key or ("", records[0].semantic_type)
    return ComponentOccurrence(
        occurrence_id=f"OCC-B{branch.index:04d}-{sequence:05d}",
        branch_index=branch.index,
        branch_name=branch.name,
        component_ref_no=ref,
        semantic_type=semantic_type,
        records=tuple(records),
    )


def _distinct_position_nodes(nodes: Sequence[NodeRecord], tolerance_mm: float = 1e-9) -> list[NodeRecord]:
    distinct: list[NodeRecord] = []
    for node in nodes:
        if not node.positive or node.position is None:
            continue
        if not distinct or distinct[-1].position is None or distinct[-1].position.distance_to(node.position) > tolerance_mm:
            distinct.append(node)
    return distinct


def _preferred_occurrence_node(occurrence: ComponentOccurrence) -> NodeRecord | None:
    positive = [record for record in occurrence.records if record.positive and record.position is not None]
    if not positive:
        return None
    priority = {0: 4, 1: 3, 2: 2, 3: 1}
    return max(
        positive,
        key=lambda node: (
            priority.get(node.endpoint, 0),
            1 if node.node_name else 0,
            1 if node.has_restraint else 0,
            -node.source_index,
        ),
    )


def _occurrence_route_nodes(occurrence: ComponentOccurrence) -> list[NodeRecord]:
    positive = [record for record in occurrence.records if record.positive and record.position is not None]
    if not positive:
        return []
    semantic = occurrence.semantic_type
    distinct = _distinct_position_nodes(positive)
    if semantic in {"ELBO", "TEE", "OLET", "ATTA", "SUPPORT", "ANCI", "BRAN"}:
        preferred = _preferred_occurrence_node(occurrence)
        return [preferred] if preferred else []
    if semantic in INLINE_TYPES or semantic == "REDU":
        if len(distinct) >= 2:
            return [distinct[0], distinct[-1]]
        return distinct[:1]
    return distinct


def _same_canonical_node(left: NodeRecord, right: NodeRecord) -> bool:
    return (
        left.node_number is not None
        and right.node_number is not None
        and left.node_number > 0
        and left.node_number == right.node_number
    )


def _build_spans(
    branches: Sequence[BranchRecord],
    occurrences: Sequence[ComponentOccurrence],
) -> list[RouteSpan]:
    occurrences_by_branch: dict[int, list[ComponentOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        occurrences_by_branch[occurrence.branch_index].append(occurrence)
    spans: list[RouteSpan] = []
    sequence = 0
    for branch in branches:
        previous_exit: tuple[NodeRecord, str] | None = None
        branch_order = 0
        for occurrence in occurrences_by_branch.get(branch.index, []):
            anchors = _occurrence_route_nodes(occurrence)
            if not anchors:
                continue
            entry, exit_node = anchors[0], anchors[-1]
            if previous_exit is not None:
                previous_node, previous_occurrence_id = previous_exit
                if previous_node.key != entry.key and not _same_canonical_node(previous_node, entry):
                    sequence += 1
                    branch_order += 1
                    spans.append(RouteSpan(
                        span_id=f"SPAN-{sequence:06d}",
                        branch_index=branch.index,
                        branch_name=branch.name,
                        branch_order=branch_order,
                        span_role="ROUTE_CONNECTION",
                        occurrence_ids=(previous_occurrence_id, occurrence.occurrence_id),
                        from_node=previous_node,
                        to_node=entry,
                        length_mm=previous_node.position.distance_to(entry.position),
                    ))
            if len(anchors) >= 2 and entry.key != exit_node.key and not _same_canonical_node(entry, exit_node):
                sequence += 1
                branch_order += 1
                spans.append(RouteSpan(
                    span_id=f"SPAN-{sequence:06d}",
                    branch_index=branch.index,
                    branch_name=branch.name,
                    branch_order=branch_order,
                    span_role="COMPONENT_INTERNAL",
                    occurrence_ids=(occurrence.occurrence_id,),
                    from_node=entry,
                    to_node=exit_node,
                    length_mm=entry.position.distance_to(exit_node.position),
                ))
            previous_exit = (exit_node, occurrence.occurrence_id)
    return spans
