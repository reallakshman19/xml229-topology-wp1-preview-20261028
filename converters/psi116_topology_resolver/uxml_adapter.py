"""UXML-S1: consume XCU-owned uxml-topology-v1 PSI116 source records.

No copy of the JavaScript reader exists here. This adapter reconstitutes only
immutable TopoFix Python NodeRecord/BranchRecord, then calls the existing
_build_occurrences, _build_spans and analyze_document. Never emit XML or patch.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from html import escape as html_escape
from pathlib import Path
from urllib.parse import quote
import json
import math
import re
from typing import Any, Mapping
import xml.etree.ElementTree as ET

from .models import BranchRecord, NodeRecord, Position, Psi116Document, ResolverConfig
from .parser import _build_occurrences, _build_spans
from .resolver import analyze_document

UXML_SCHEMA_VERSION = "uxml-topology-v1"
UXML_PROFILE = "UXML-TOPOLOGY-FULL"
PSI116_NAMESPACES = frozenset({
    "http://aveva.com/pipeStress116.xsd",
    "http://aveva.com/pipestress116.xsd",
})


class UxmlPsi116Error(ValueError):
    """One source qualification or exact-record identity failure."""


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise UxmlPsi116Error(code)


def _number(value: object, name: str) -> float | None:
    if value is None:
        return None
    _need(isinstance(value, (int, float)) and not isinstance(value, bool), f"{name}:NOT_NUMERIC")
    number = float(value)
    _need(math.isfinite(number), f"{name}:NONFINITE")
    return number


def _integer(value: object, name: str) -> int | None:
    if value is None:
        return None
    # JS JSON cannot precisely carry Python integers beyond 2**53-1.
    # The XCU reader emits canonical decimal strings only for such values;
    # reconstruct exact Python int without rounding, and never accept 0x10.
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    _need(isinstance(value, int) and not isinstance(value, bool), f"{name}:NOT_INTEGER")
    return value


def _position(value: object) -> Position | None:
    if value is None:
        return None
    _need(isinstance(value, dict) and all(k in value for k in ("x", "y", "z")),
          "POSITION_INVALID")
    xyz = tuple(_number(value[k], "POSITION_" + k) for k in ("x", "y", "z"))
    _need(all(axis is not None for axis in xyz), "POSITION_NULL_AXIS")
    return Position(*xyz)


def _raw_xml(record: Mapping[str, Any], namespace: str,
             declarations: Mapping[str, str]) -> str:
    """Python ET canonical Node serialization, including tail like parser.py.

    The raw <Node> fragment is linked by an original-source recordKey. It may
    inherit prefix declarations from PipeStressExport; supply only those XML
    declarations, not the source document or other candidate XML, to ET.
    """
    raw, tail = record.get("rawXml"), record.get("rawTail")
    _need(isinstance(raw, str) and raw.lstrip().startswith("<"),
          "PSI116_RAW_NODE_FRAGMENT_MISSING")
    _need(isinstance(tail, str), "PSI116_RAW_NODE_TAIL_MISSING")
    extra = "".join(
        " " + key + '="' + html_escape(str(value), quote=True) + '"'
        for key, value in declarations.items()
        if key == "xmlns" or key.startswith("xmlns:")
    )
    # The default namespace is authoritative, whether the source used a prefix.
    if "xmlns" not in declarations:
        extra += ' xmlns="' + html_escape(namespace, quote=True) + '"'
    try:
        wrapper = ET.fromstring("<__uxml_record_container" + extra + ">"
                                + raw + tail + "</__uxml_record_container>")
    except ET.ParseError as error:
        raise UxmlPsi116Error("PSI116_RAW_NODE_XML_INVALID") from error
    _need(len(wrapper) == 1 and wrapper[0].tag.rsplit("}", 1)[-1] == "Node",
          "PSI116_RAW_FRAGMENT_NOT_NODE")
    ET.register_namespace("", namespace)
    return ET.tostring(wrapper[0], encoding="unicode")


def _refs(component: dict, record: dict, sha: str,
          ports_by_component: dict[str, list[dict]]) -> None:
    index, source_index, number = (record["branchIndex"], record["sourceIndex"],
                                    record["nodeNumber"])
    key = f"B{index}:N{number if number is not None else 'none'}:S{source_index}"
    _need(record.get("recordKey") == key, "PSI116_RECORD_KEY_MISMATCH:" + key)
    expected = {
        "format": "PSI116", "fileSha256": sha, "recordKey": key,
        "branchName": record["branchName"], "nodeNumber": number,
        "endpoint": record["endpoint"],
    }
    _need(component.get("sourceRefs") == [expected],
          "PSI116_COMPONENT_SOURCE_REF_MISMATCH:" + key)
    _need(component.get("id") == "PSI116-" + key,
          "PSI116_COMPONENT_ID_MISMATCH:" + key)
    ports = ports_by_component.get(component["id"], [])
    _need(len(ports) == (1 if record["position"] is not None else 0),
          "PSI116_POSITION_PORT_COUNT_MISMATCH:" + key)
    for port in ports:
        _need(port.get("sourceRefs") == [expected], "PSI116_PORT_SOURCE_REF_MISMATCH:" + key)


def document_from_uxml(uxml: dict, *, source_name: str | None = None) -> Psi116Document:
    # Separate additive InputXML branch; PSI116 semantics below are unchanged.
    if isinstance(uxml, dict) and len(uxml.get("sources") or []) == 1 and (
        uxml["sources"][0].get("format") == "INPUT_XML"
    ):
        return _document_from_caesar_inputxml(uxml, source_name=source_name)
    _need(isinstance(uxml, dict), "UXML_DOCUMENT_REQUIRED")
    _need(uxml.get("schemaVersion") == UXML_SCHEMA_VERSION and
          uxml.get("profile") == UXML_PROFILE, "UXML_PROFILE_NOT_TOPOLOGY_FULL")
    sources = uxml.get("sources")
    _need(isinstance(sources, list) and len(sources) == 1 and
          sources[0].get("format") == "PSI116", "UXML_ONE_PSI116_SOURCE_REQUIRED")
    source = sources[0]
    source_text = source.get("sourceText")
    namespace = source.get("namespace")
    declared_sha = source.get("hash")
    _need(isinstance(source_text, str) and source_text, "UXML_SOURCE_TEXT_MISSING")
    _need(namespace in PSI116_NAMESPACES, "PSI116_NAMESPACE_NOT_VERIFIED")
    _need(isinstance(declared_sha, str) and len(declared_sha) == 64,
          "UXML_SOURCE_SHA256_INVALID")
    actual_sha = sha256(source_text.encode("utf-8")).hexdigest()
    _need(actual_sha == declared_sha, "UXML_ORIGINAL_SOURCE_SHA256_MISMATCH")
    scope = uxml.get("psi116") or {}
    _need(scope.get("sourceSha256") == declared_sha and
          scope.get("namespace") == namespace, "UXML_PSI116_PROVENANCE_MISMATCH")
    declarations = source.get("namespaceDeclarations") or {}
    _need(isinstance(declarations, dict), "UXML_XMLNS_DECLARATIONS_INVALID")
    branches = uxml.get("pipelines") or []
    components = uxml.get("components") or []
    ports = uxml.get("ports") or []
    _need(isinstance(branches, list) and isinstance(components, list) and
          isinstance(ports, list), "UXML_SOURCE_RECORD_COLLECTION_INVALID")

    by_component: dict[str, list[dict]] = {}
    for port in ports:
        _need(isinstance(port, dict) and isinstance(port.get("componentId"), str),
              "UXML_PORT_INVALID")
        by_component.setdefault(port["componentId"], []).append(port)

    by_branch: dict[int, list[dict]] = {}
    seen = set()
    for component in components:
        _need(isinstance(component, dict), "UXML_COMPONENT_INVALID")
        fields = component.get("rawAttributes", {}).get("psi116")
        _need(isinstance(fields, dict), "UXML_PSI116_RECORD_FIELDS_MISSING")
        index = _integer(fields.get("branchIndex"), "BRANCH_INDEX")
        seq = _integer(fields.get("sourceIndex"), "SOURCE_INDEX")
        _need(index is not None and index >= 0 and seq is not None and seq >= 0,
              "UXML_PSI116_INDEX_NEGATIVE")
        _need((index, seq) not in seen, "UXML_PSI116_DUPLICATE_SOURCE_RECORD")
        seen.add((index, seq))
        _refs(component, fields, declared_sha, by_component)
        by_branch.setdefault(index, []).append(fields)
    _need(len(components) == sum(len(v) for v in by_branch.values()),
          "UXML_NODE_RECORD_COUNT_MISMATCH")
    _need(len(ports) == sum(bool(record.get("position") is not None)
                            for rows in by_branch.values() for record in rows),
          "UXML_UNBOUND_EXTRA_PORT")

    output_branches = []
    for index, branch in enumerate(branches):
        attrs = branch.get("rawAttributes", {})
        _need(attrs.get("branchIndex") == index and
              branch.get("id") == "PSI116-BRANCH-" + str(index),
              "UXML_PSI116_BRANCH_ORDER_MISMATCH")
        branch_name = attrs.get("branchName")
        _need(isinstance(branch_name, str), "UXML_BRANCH_NAME_MISSING")
        rows = sorted(by_branch.get(index, []), key=lambda rec: rec["sourceIndex"])
        _need([row["sourceIndex"] for row in rows] == list(range(len(rows))),
              "UXML_PSI116_NONCONTIGUOUS_NODE_INDEX")
        records = []
        for row in rows:
            _need(row.get("branchName") == branch_name, "UXML_NODE_BRANCH_NAME_MISMATCH")
            record = NodeRecord(
                branch_index=index, branch_name=branch_name,
                source_index=row["sourceIndex"],
                node_number=_integer(row["nodeNumber"], "NODE_NUMBER"),
                node_name=row["nodeName"],
                endpoint=_integer(row["endpoint"], "ENDPOINT"),
                component_type=row["componentType"],
                raw_component_type=row["rawComponentType"],
                component_ref_no=row["componentRefNo"],
                connection_type=row["connectionType"],
                position=_position(row["position"]),
                rigid=_integer(row["rigid"], "RIGID"),
                weight=_number(row["weight"], "WEIGHT"),
                outside_diameter=_number(row["outsideDiameter"], "OUTSIDE_DIAMETER"),
                wall_thickness=_number(row["wallThickness"], "WALL_THICKNESS"),
                bend_radius=_number(row["bendRadius"], "BEND_RADIUS"),
                alpha_angle=_number(row["alphaAngle"], "ALPHA_ANGLE"),
                has_restraint=bool(row["hasRestraint"]),
                raw_xml=_raw_xml(row, namespace, declarations),
            )
            records.append(record)
        output_branches.append(BranchRecord(index, branch_name, tuple(records)))
    _need(set(by_branch).issubset(set(range(len(output_branches)))),
          "UXML_ORPHAN_BRANCH_INDEX")
    _need(scope.get("branchCount") == len(output_branches) and
          scope.get("sourceNodeRecordCount") == len(components),
          "UXML_PSI116_DECLARED_COUNTS_MISMATCH")
    occurrences = _build_occurrences(output_branches)
    spans = _build_spans(output_branches, occurrences)
    return Psi116Document(
        source_path=source_name or "<memory>",
        source_text=source_text,
        source_sha256=declared_sha,
        namespace=namespace,
        branches=tuple(output_branches),
        occurrences=tuple(occurrences),
        spans=tuple(spans),
    )


def resolve_from_uxml(uxml: dict, config: ResolverConfig | None = None,
                      *, source_name: str | None = None):
    """Same TopoFix analyzer; no modifications to parser.py or resolver.py."""
    if isinstance(uxml, dict) and (uxml.get('sources') or [{}])[0].get('format') == 'INPUT_XML':
        runs=(uxml.get('inputXml') or {}).get('runs') or []
        if len(runs)>1 and any(not r.get('anchored') for r in runs):
            raise UxmlPsi116Error('INPUT_XML_CROSS_UNANCHORED_RUN_GAP_PROXIMITY_JOIN_REFUSED')
    return analyze_document(document_from_uxml(uxml, source_name=source_name), config)


@dataclass(frozen=True)
class InputXmlNodeRecord(NodeRecord):
    """Original InputXML ordinal key survives engine-compatible projection."""
    inputxml_record_key: str = ""
    inputxml_endpoint: str = ""
    inputxml_run_id: str = ""
    inputxml_anchored: bool = False
    # Engine has one physical NodeRecord per route point. Retain EVERY
    # original PIPINGELEMENT source key merged at that point.
    inputxml_record_keys: tuple[str, ...] = ()


def _caesar_int(value: str, label: str) -> int:
    _need(isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+(?:\.0+)?", value) is not None,
          "INPUT_XML_INVALID_NODE_NUMBER:" + label)
    return int(value.split(".", 1)[0])


def _caesar_original_rows(source_text: str) -> tuple[list[ET.Element], str]:
    try:
        root = ET.fromstring(source_text.lstrip("\ufeff"))
    except ET.ParseError as err:
        raise UxmlPsi116Error("INPUT_XML_ORIGINAL_PARSE_FAILED") from err
    _need(root.tag.rsplit("}", 1)[-1] == "CAESARII", "INPUT_XML_CAESAR_ROOT_REQUIRED")
    rows = [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "PIPINGELEMENT"]
    _need(bool(rows), "INPUT_XML_PIPINGELEMENT_REQUIRED")
    namespace = root.tag.partition("}")[0].lstrip("{") if "}" in root.tag else ""
    return rows, namespace


def _caesar_hub_delta(attrs: Mapping[str, str], label: str) -> Position:
    axes = []
    for axis in "XYZ":
        raw = attrs.get("DELTA_" + axis)
        _need(isinstance(raw, str) and raw, "INPUT_XML_DELTA_REQUIRED:" + label + ":" + axis)
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise UxmlPsi116Error("INPUT_XML_DELTA_NONNUMERIC:" + label + ":" + axis) from exc
        _need(math.isfinite(number), "INPUT_XML_DELTA_NONFINITE:" + label + ":" + axis)
        axes.append(0. if abs(number + 1.0101) < 0.00001 else number)
    return Position(axes[0], -axes[2], axes[1])


def _caesar_hub_absolute(attrs: Mapping[str, str], prefix: str) -> Position | None:
    values = [attrs.get(prefix + "_" + axis) for axis in "XYZ"]
    if all(v is None for v in values):
        return None
    _need(all(v is not None for v in values), "INPUT_XML_INCOMPLETE_ABSOLUTE_ANCHOR")
    nums = [float(v) for v in values]
    _need(all(math.isfinite(v) for v in nums), "INPUT_XML_NONFINITE_ABSOLUTE_ANCHOR")
    return Position(nums[0], -nums[2], nums[1])


def _close(a: Position, b: Position, tolerance: float = .001) -> bool:
    return a.distance_to(b) <= tolerance


def _record_key(index: int, from_node: str, to_node: str) -> str:
    # Python quote's default safe '/' differs from JS encodeURIComponent.
    # encodeURIComponent leaves unescaped A-Z a-z 0-9 - _ . ! ~ * ' ( ).
    safe = "-_.!~*'()"
    return f"E{index}:F{quote(from_node, safe=safe)}:T{quote(to_node, safe=safe)}"


def _original_s3_physical(attrs: Mapping[str, str], field: str, index: int,
                          context: dict[str, dict]) -> dict:
    """Check inherited numerical context against ORIGINAL InputXML attributes."""
    raw = attrs.get(field, "")
    if raw:
        try:
            explicit = float(raw)
        except (TypeError, ValueError) as exc:
            raise UxmlPsi116Error("INPUT_XML_PHYSICAL_NONNUMERIC:" + field) from exc
        _need(math.isfinite(explicit), "INPUT_XML_PHYSICAL_NONFINITE:" + field)
    else:
        explicit = -1.0101
    source_field = "PIPINGELEMENT@" + field
    if raw and abs(explicit + 1.0101) >= .00001:
        evidence = {"value": explicit, "mode": "EXPLICIT",
                    "sourceElementIndex": index, "sourceField": source_field}
        context[field] = evidence
        return evidence
    prior = context.get(field)
    if prior:
        return {**prior, "mode": "INHERITED"}
    return {"value": None, "mode": "SOURCE_UNAVAILABLE",
            "sourceElementIndex": None, "sourceField": source_field}


def _original_s3_children(element: ET.Element, index: int) -> tuple[dict | None, list[dict]]:
    children = [c for c in element if isinstance(c.tag, str)]
    def local(child: ET.Element) -> str:
        return child.tag.rsplit("}", 1)[-1].upper()
    bend = next((c for c in children if local(c) == "BEND"), None)
    bend_evidence = None
    if bend is not None:
        radius_raw = bend.attrib.get("RADIUS", "")
        if radius_raw:
            try:
                radius = float(radius_raw)
            except ValueError as exc:
                raise UxmlPsi116Error("INPUT_XML_BEND_RADIUS_INVALID") from exc
            if math.isfinite(radius) and abs(radius + 1.0101) >= .00001:
                bend_evidence = {
                    "radius": radius, "endpoint": "TO",
                    "sourceElementIndex": index,
                    "sourceField": "PIPINGELEMENT/BEND@RADIUS",
                    "toNode": element.attrib.get("TO_NODE", ""),
                    "rawAttributes": dict(bend.attrib),
                }
    sif_evidence = []
    for child in children:
        if local(child) != "SIF":
            continue
        raw_type = child.attrib.get("TYPE", "")
        try:
            code = float(raw_type) if raw_type else None
        except ValueError:
            code = None
        if code is None or not math.isfinite(code) or abs(code + 1.0101) < .00001:
            continue
        sif_evidence.append({
            "typeCode": code, "node": child.attrib.get("NODE", ""),
            "sourceElementIndex": index,
            "sourceField": "PIPINGELEMENT/SIF@TYPE",
            "rawAttributes": dict(child.attrib),
        })
    return bend_evidence, sif_evidence


def _document_from_caesar_inputxml(uxml: dict, *,
                                   source_name: str | None = None) -> Psi116Document:
    """Reconcile only verified InputXML → TopoFix projection defects.

    All positions, physical inheritance, bend/SIF source identity are independently
    checked against original InputXML bytes. No PSI116 path or engine changes.
    Source-only SIF=5 means OLET, NOT source-verified TEE; never fabricate TEE.
    """
    _need(uxml.get("schemaVersion") == UXML_SCHEMA_VERSION and
          uxml.get("profile") == UXML_PROFILE, "INPUT_XML_NOT_TOPOLOGY_FULL")
    _need(len(uxml.get("sources") or []) == 1, "INPUT_XML_SINGLE_SOURCE_REQUIRED")
    source = uxml["sources"][0]
    source_text, digest = source.get("sourceText"), source.get("hash")
    _need(source.get("format") == "INPUT_XML", "INPUT_XML_SOURCE_FORMAT_INVALID")
    _need(isinstance(source_text, str) and source_text, "INPUT_XML_ORIGINAL_TEXT_REQUIRED")
    _need(isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest),
          "INPUT_XML_SOURCE_SHA256_REQUIRED")
    _need(sha256(source_text.encode("utf-8")).hexdigest() == digest,
          "INPUT_XML_ORIGINAL_SOURCE_SHA256_MISMATCH")
    scope = uxml.get("inputXml") or {}
    frame = uxml.get("coordinateFrame") or {}
    _need(scope.get("sourceSha256") == digest and
          scope.get("coordinateAuthority") == "ANCHORED_OR_UNANCHORED_DELTA_GRAPH",
          "INPUT_XML_DELTA_PROVENANCE_MISMATCH")
    _need(scope.get("sourceFrame") == "CAESAR_INPUTXML_XYZ_MM" and
          scope.get("hubFrame") == "PSI116_XYZ_MM" and
          frame.get("source") == "CAESAR_INPUTXML_XYZ_MM" and
          frame.get("hub") == "PSI116_XYZ_MM" and
          frame.get("transform") == "(X,-Z,Y)",
          "INPUT_XML_COORDINATE_FRAME_MISMATCH")
    rows, namespace = _caesar_original_rows(source_text)
    comps, ports = uxml.get("components"), uxml.get("ports")
    _need(isinstance(comps, list) and isinstance(ports, list) and
          len(comps) == len(rows) and scope.get("elementCount") == len(rows),
          "INPUT_XML_PIPINGELEMENT_COUNT_MISMATCH")
    _need(len(ports) == 2 * len(rows), "INPUT_XML_PORTS_PER_ELEMENT_MISMATCH")
    runs = scope.get("runs")
    _need(isinstance(runs, list) and runs, "INPUT_XML_RUN_FRAME_DECLARATIONS_REQUIRED")
    run_by_index: dict[int, tuple[int, dict]] = {}
    for run_index, run in enumerate(runs):
        _need(isinstance(run, dict) and run.get("id") == f"RUN-{run_index:04d}" and
              isinstance(run.get("anchored"), bool),
              "INPUT_XML_RUN_IDENTITY_INVALID")
        _need(run.get("hubFrame") == "PSI116_XYZ_MM" and
              run.get("sourceFrame") == "CAESAR_INPUTXML_XYZ_MM" and
              run.get("crossUnanchoredRunPolicy") == "REFUSE_CROSS_RUN_GAP_PROXIMITY_JOIN",
              "INPUT_XML_RUN_FRAME_INVALID")
        indices = run.get("elementIndices")
        _need(isinstance(indices, list) and len(indices) == run.get("edgeCount"),
              "INPUT_XML_RUN_ELEMENT_INDEX_INVALID")
        for ix in indices:
            _need(isinstance(ix, int) and ix not in run_by_index and 0 <= ix < len(rows),
                  "INPUT_XML_DUPLICATE_OR_INVALID_RUN_ELEMENT_INDEX")
            run_by_index[ix] = (run_index, run)
    _need(set(run_by_index) == set(range(len(rows))), "INPUT_XML_RUN_COVERAGE_INCOMPLETE")
    ports_by_component: dict[str, list[dict]] = {}
    for port in ports:
        _need(isinstance(port, dict) and isinstance(port.get("componentId"), str),
              "INPUT_XML_PORT_INVALID")
        ports_by_component.setdefault(port["componentId"], []).append(port)

    # A SIF in original InputXML is an ownership witness, but SIF=5 is OLET
    # (not TEE). Derive a synthetic BRAN route stub only when source has a
    # separate route starting at the same SIF node; preserve literal code.
    source_sifs: dict[str, tuple[str, int]] = {}
    for idx, element in enumerate(rows):
        _, items = _original_s3_children(element, idx)
        for item in items:
            if item["typeCode"] == 3:
                source_sifs[item["node"]] = ("TEE", idx)
            elif item["typeCode"] == 5:
                source_sifs[item["node"]] = ("OLET", idx)

    branches_raw: list[list[InputXmlNodeRecord]] = []
    branch_run_ids: list[str] = []
    visited_nodes: dict[tuple[int, str], Position] = {}
    literal_anchors: dict[tuple[int, str], Position] = {}
    seen_keys: set[str] = set()
    current_run_index: int | None = None
    current_to: str | None = None
    context: dict[str, dict] = {}
    route_index: int | None = None

    for index, (element, comp) in enumerate(zip(rows, comps)):
        attrs = element.attrib
        from_node, to_node = attrs.get("FROM_NODE"), attrs.get("TO_NODE")
        _need(isinstance(from_node, str) and from_node and
              isinstance(to_node, str) and to_node,
              "INPUT_XML_RECORD_NODE_ID_MISSING")
        key = _record_key(index, from_node, to_node)
        _need(key not in seen_keys, "INPUT_XML_DUPLICATE_RECORD_KEY")
        seen_keys.add(key)
        run_index, run = run_by_index[index]
        run_id, anchored = run["id"], run["anchored"]
        expected = {
            "format": "INPUT_XML", "fileSha256": digest, "recordKey": key,
            "elementIndex": index, "fromNode": from_node, "toNode": to_node,
            "runId": run_id, "anchored": anchored,
        }
        _need(isinstance(comp, dict) and comp.get("id") == f"IX-S3-E{index}" and
              comp.get("sourceRefs") == [expected],
              "INPUT_XML_COMPONENT_SOURCE_REF_MISMATCH:" + key)
        info = (comp.get("rawAttributes") or {}).get("inputXml") or {}
        _need(info.get("recordKey") == key and info.get("elementIndex") == index and
              info.get("fromNode") == from_node and info.get("toNode") == to_node and
              info.get("runId") == run_id and info.get("anchored") is anchored,
              "INPUT_XML_RAW_RECORD_ID_MISMATCH:" + key)

        new_route = (route_index is None or current_run_index != run_index
                     or current_to != from_node)
        if new_route:
            route_index = len(branches_raw)
            branches_raw.append([])
            branch_run_ids.append(run_id)
            context = {}
        current_run_index, current_to = run_index, to_node
        fields = {
            "outsideDiameter": _original_s3_physical(attrs, "DIAMETER", index, context),
            "wallThickness": _original_s3_physical(attrs, "WALL_THICK", index, context),
        }
        _need(info.get("physicalEvidence") == fields and
              info.get("outsideDiameter") == fields["outsideDiameter"]["value"] and
              info.get("wallThickness") == fields["wallThickness"]["value"],
              "INPUT_XML_PHYSICAL_PROVENANCE_MISMATCH:" + key)
        bend, sifs = _original_s3_children(element, index)
        _need(info.get("bendEvidence") == bend and info.get("sifEvidence") == sifs,
              "INPUT_XML_NESTED_SOURCE_EVIDENCE_MISMATCH:" + key)
        found = ports_by_component.get(comp["id"], [])
        _need(len(found) == 2, "INPUT_XML_PORT_COUNT_MISMATCH:" + key)
        positions: dict[str, Position] = {}
        for port in found:
            refs = port.get("sourceRefs")
            _need(isinstance(refs, list) and len(refs) == 1,
                  "INPUT_XML_PORT_REF_MISSING:" + key)
            ep = refs[0].get("endpoint")
            _need(ep in {"FROM", "TO"} and refs == [{**expected, "endpoint": ep}],
                  "INPUT_XML_PORT_SOURCE_REF_MISMATCH:" + key)
            _need(ep not in positions, "INPUT_XML_DUPLICATE_ENDPOINT:" + key)
            position = _position(port.get("point"))
            _need(position is not None and port.get("runId") == run_id and
                  port.get("anchored") is anchored and
                  port.get("coordinateFrame") == "PSI116_XYZ_MM",
                  "INPUT_XML_PORT_FRAME_MISMATCH:" + key)
            positions[ep] = position
        _need(set(positions) == {"FROM", "TO"}, "INPUT_XML_ENDPOINT_COVERAGE_MISMATCH:" + key)
        _need(info.get("from") == asdict(positions["FROM"]) and
              info.get("to") == asdict(positions["TO"]),
              "INPUT_XML_TYPED_COORDINATE_MISMATCH:" + key)
        step = _caesar_hub_delta(attrs, key)
        declared = Position(positions["TO"].x - positions["FROM"].x,
                            positions["TO"].y - positions["FROM"].y,
                            positions["TO"].z - positions["FROM"].z)
        _need(_close(step, declared), "INPUT_XML_DELTA_SUM_MISMATCH:" + key)
        for ep, node in (("FROM", from_node), ("TO", to_node)):
            tag = (run_index, node)
            val = positions[ep]
            if tag in visited_nodes:
                _need(_close(visited_nodes[tag], val),
                      "INPUT_XML_DELTA_PATH_CONFLICT:" + key + ":" + node)
            else:
                visited_nodes[tag] = val
            absolute = _caesar_hub_absolute(attrs, ep)
            if absolute is not None:
                literal_anchors[tag] = absolute
                _need(_close(absolute, val),
                      "INPUT_XML_ABSOLUTE_ANCHOR_MISMATCH:" + key + ":" + ep)

        # Reconcile original source attribute authority for type, not a
        # guessed equivalent of PSI116 component refs or helper nodes.
        sif_at_to = next((item for item in sifs
                          if item.get("node") == to_node and item["typeCode"] in (3, 5)), None)
        if sif_at_to is not None:
            allowed = "TEE" if sif_at_to["typeCode"] == 3 else "OLET"
            _need(info.get("componentType") == allowed,
                  "INPUT_XML_SIF_COMPONENT_TYPE_CONFLICT:" + key)
        elif bend is not None:
            _need(info.get("componentType") == "BEND",
                  "INPUT_XML_BEND_COMPONENT_TYPE_CONFLICT:" + key)

        od, wall = fields["outsideDiameter"]["value"], fields["wallThickness"]["value"]
        source_ref = attrs.get("REF_NO", "")
        _need(comp.get("refNo", "") in ("", source_ref),
              "INPUT_XML_UNAUTHORIZED_COMPONENT_REFERENCE:" + key)

        def new_record(ep: str) -> InputXmlNodeRecord:
            node = from_node if ep == "FROM" else to_node
            if ep == "FROM":
                sif = source_sifs.get(node) if new_route else None
                if sif is not None and sif[1] != index:
                    kind, connection = "BRAN", sif[0]
                else:
                    kind, connection = "PIPE", ""
                radius = None
                name = attrs.get("FROM_NAME", "")
                endpoint = 1
            else:
                kind, connection = "PIPE", ""
                if sif_at_to is not None:
                    kind = allowed
                    connection = allowed
                elif bend is not None:
                    kind = "ELBO"
                elif info.get("componentType") in {"FLANGE", "RIGI", "VALV", "REDU"}:
                    kind = str(info["componentType"])
                radius = bend["radius"] if bend is not None else None
                name = attrs.get("TO_NAME") or attrs.get("NAME") or ""
                endpoint = 0 if kind in {"TEE", "OLET"} else 2
            has_restraint = any(
                (child.tag.rsplit("}",1)[-1].upper() in {"RESTRAINT","RESTRANT"} and
                 child.attrib.get("NODE") == node and
                 child.attrib.get("TYPE") not in ("-1.010100","-1.0101"))
                for child in element if isinstance(child.tag,str))
            branch_name = f"{run_id}:ROUTE-{route_index:04d}"
            return InputXmlNodeRecord(
                branch_index=route_index,branch_name=branch_name,
                source_index=len(branches_raw[route_index]),
                node_number=_caesar_int(node,key+":"+ep),
                node_name=name,endpoint=endpoint,
                component_type=kind,raw_component_type=('BEND' if kind=='ELBO' else kind),
                component_ref_no=source_ref,connection_type=connection,
                position=positions[ep],rigid=None,weight=None,
                outside_diameter=od,wall_thickness=wall,bend_radius=radius,
                alpha_angle=None,has_restraint=has_restraint,
                raw_xml=ET.tostring(element,encoding="unicode"),
                inputxml_record_key=key,inputxml_endpoint=ep,
                inputxml_run_id=run_id,inputxml_anchored=anchored,
                inputxml_record_keys=(key,),
            )

        source_rows = branches_raw[route_index]
        if new_route:
            source_rows.append(new_record("FROM"))
        else:
            _need(bool(source_rows) and source_rows[-1].node_number ==
                  _caesar_int(from_node,key+":FROM") and
                  _close(source_rows[-1].position,positions["FROM"]),
                  "INPUT_XML_ROUTE_CONTINUITY_CONFLICT:"+key)
            previous = source_rows[-1]
            _need(key not in previous.inputxml_record_keys,
                  "INPUT_XML_DUPLICATE_SOURCE_KEY_ON_NODE:"+key)
            source_rows[-1] = replace(previous,
                inputxml_record_keys=(*previous.inputxml_record_keys,key))
        source_rows.append(new_record("TO"))
    for i, run in enumerate(runs):
        _need(run.get("anchored") is any(key[0] == i for key in literal_anchors),
              "INPUT_XML_FALSE_ANCHORED_OR_UNANCHORED_RUN:" + run["id"])
    branch_records = []
    for i, records in enumerate(branches_raw):
        _need(all(r.source_index==k for k,r in enumerate(records)),
              "INPUT_XML_ROUTE_RECORD_ORDER_INVALID")
        branch_records.append(BranchRecord(i, records[0].branch_name, tuple(records)))
    branches = tuple(branch_records)
    occurrences = _build_occurrences(branches)
    spans = _build_spans(branches,occurrences)
    return Psi116Document(source_path=source_name or "<inputxml>",
        source_text=source_text,source_sha256=digest,namespace=namespace,
        branches=branches,occurrences=tuple(occurrences),spans=tuple(spans))



def resolve_inputxml_run_from_uxml(uxml: dict, run_id: str,
                                   config: ResolverConfig | None = None,
                                   *, source_name: str | None = None):
    """Safe per-run engine execution; no cross-unanchored-run gap judgement."""
    document = document_from_uxml(uxml, source_name=source_name)
    _need((uxml.get("sources") or [{}])[0].get("format") == "INPUT_XML",
          "INPUT_XML_RUN_RESOLUTION_FORMAT_REQUIRED")
    branches = [branch for branch in document.branches
                if branch.nodes and all(r.inputxml_run_id == run_id for r in branch.nodes)]
    _need(bool(branches), "INPUT_XML_RUN_ID_NOT_FOUND:" + str(run_id))
    # Retain ALL route branches inside one connected run (including a tee
    # spur) while excluding every other run's unknown local frame.
    subset = tuple(
        BranchRecord(i, branch.name,
          tuple(replace(row, branch_index=i, source_index=k)
                for k, row in enumerate(branch.nodes)))
        for i, branch in enumerate(branches))
    occurrences = _build_occurrences(subset)
    spans = _build_spans(subset, occurrences)
    local_document = Psi116Document(
        source_path=document.source_path, source_text=document.source_text,
        source_sha256=document.source_sha256, namespace=document.namespace,
        branches=subset, occurrences=tuple(occurrences), spans=tuple(spans))
    return analyze_document(local_document, config)
