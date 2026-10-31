"""UXML-S1: consume XCU-owned uxml-topology-v1 PSI116 source records.

No copy of the JavaScript reader exists here. This adapter reconstitutes only
immutable TopoFix Python NodeRecord/BranchRecord, then calls the existing
_build_occurrences, _build_spans and analyze_document. Never emit XML or patch.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from html import escape as html_escape
from pathlib import Path
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
    return analyze_document(document_from_uxml(uxml, source_name=source_name), config)


@dataclass(frozen=True)
class InputXmlNodeRecord(NodeRecord):
    """Engine-compatible source record retaining the real InputXML source key.

    The existing engine uses the legacy B:N:S derived key for findings.
    This additional immutable field is patch provenance, not an engine rewrite.
    """
    inputxml_record_key: str = ""
    inputxml_endpoint: str = ""


def _caesar_int(value: str, label: str) -> int:
    _need(isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value) is not None,
          "INPUT_XML_INVALID_NODE_NUMBER:" + label)
    return int(value)


def _caesar_original_rows(source_text: str) -> tuple[list[ET.Element], str]:
    try:
        root = ET.fromstring(source_text.lstrip("\ufeff"))
    except ET.ParseError as err:
        raise UxmlPsi116Error("INPUT_XML_ORIGINAL_PARSE_FAILED") from err
    _need(root.tag.rsplit("}", 1)[-1] == "CAESARII",
          "INPUT_XML_CAESAR_ROOT_REQUIRED")
    rows = [item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "PIPINGELEMENT"]
    _need(bool(rows), "INPUT_XML_PIPINGELEMENT_REQUIRED")
    namespace = root.tag.partition("}")[0].lstrip("{") if "}" in root.tag else ""
    return rows, namespace


def _document_from_caesar_inputxml(uxml: dict, *,
                                   source_name: str | None = None) -> Psi116Document:
    """Strict InputXML read-only projection into the existing TopoFix engine.

    No geometry synthesis, no InputXML writer, no new findings algorithm.
    All mutable-source identity remains E{index}:F{from}:T{to} and source SHA.
    Absolute points must agree with the ORIGINAL PIPINGELEMENT fields.
    """
    _need(uxml.get("schemaVersion") == UXML_SCHEMA_VERSION and
          uxml.get("profile") == UXML_PROFILE, "INPUT_XML_NOT_TOPOLOGY_FULL")
    _need(len(uxml.get("sources") or []) == 1, "INPUT_XML_SINGLE_SOURCE_REQUIRED")
    source = uxml["sources"][0]
    text = source.get("sourceText")
    sha = source.get("hash")
    _need(isinstance(text, str) and text, "INPUT_XML_ORIGINAL_TEXT_REQUIRED")
    _need(isinstance(sha, str) and re.fullmatch(r"[a-f0-9]{64}", sha) is not None,
          "INPUT_XML_SOURCE_SHA256_REQUIRED")
    _need(sha256(text.encode("utf-8")).hexdigest() == sha,
          "INPUT_XML_ORIGINAL_SOURCE_SHA256_MISMATCH")
    scope = uxml.get("inputXml") or {}
    _need(scope.get("sourceSha256") == sha and
          scope.get("coordinateAuthority") == "EXPLICIT_ABSOLUTE_FROM_TO_SOURCE_ATTRS_ONLY",
          "INPUT_XML_PROVENANCE_NOT_AUTHORITATIVE")
    rows, namespace = _caesar_original_rows(text)
    comps = uxml.get("components")
    ports = uxml.get("ports")
    _need(isinstance(comps, list) and isinstance(ports, list) and len(comps) == len(rows)
          and scope.get("elementCount") == len(rows),
          "INPUT_XML_PIPINGELEMENT_COUNT_MISMATCH")
    ports_by_comp = {}
    for port in ports:
        _need(isinstance(port, dict), "INPUT_XML_PORT_INVALID")
        ports_by_comp.setdefault(port.get("componentId"), []).append(port)
    _need(len(ports) == 2 * len(rows), "INPUT_XML_PORTS_PER_ELEMENT_MISMATCH")
    used_keys, source_records = set(), []
    for index, (element, component) in enumerate(zip(rows, comps)):
        attrs = element.attrib
        from_node = attrs.get("FROM_NODE")
        to_node = attrs.get("TO_NODE")
        _need(from_node and to_node, "INPUT_XML_RECORD_NODE_ID_MISSING")
        from urllib.parse import quote
        key = f"E{index}:F{quote(from_node, safe='~')}:T{quote(to_node, safe='~')}"
        _need(key not in used_keys, "INPUT_XML_DUPLICATE_RECORD_KEY")
        used_keys.add(key)
        expected = {"format": "INPUT_XML", "fileSha256": sha, "recordKey": key,
                    "elementIndex": index, "fromNode": from_node, "toNode": to_node}
        _need(component.get("sourceRefs") == [expected] and
              component.get("id") == "IX-S3-E" + str(index),
              "INPUT_XML_COMPONENT_SOURCE_REF_MISMATCH:" + key)
        info = (component.get("rawAttributes") or {}).get("inputXml") or {}
        _need(info.get("recordKey") == key and info.get("elementIndex") == index and
              info.get("fromNode") == from_node and info.get("toNode") == to_node,
              "INPUT_XML_RAW_RECORD_ID_MISMATCH:" + key)
        original_from = Position(*(float(attrs["FROM_" + axis]) for axis in "XYZ"))
        original_to = Position(*(float(attrs["TO_" + axis]) for axis in "XYZ"))
        original_points = {"FROM": original_from, "TO": original_to}
        canonical = {"FROM": "EP1", "TO": "EP2"}
        found_ports = ports_by_comp.get(component["id"], [])
        _need(len(found_ports) == 2, "INPUT_XML_PORT_COUNT_MISMATCH:" + key)
        positions = {}
        for port in found_ports:
            refs = port.get("sourceRefs")
            _need(isinstance(refs, list) and len(refs) == 1,
                  "INPUT_XML_PORT_SOURCE_REF_MISSING:" + key)
            endpoint = refs[0].get("endpoint")
            _need(endpoint in original_points and
                  refs == [{**expected, "endpoint": endpoint}],
                  "INPUT_XML_PORT_SOURCE_REF_MISMATCH:" + key)
            _need(endpoint not in positions, "INPUT_XML_DUPLICATE_ENDPOINT:" + key)
            pos = _position(port.get("point"))
            _need(pos == original_points[endpoint],
                  "INPUT_XML_PORT_ABSOLUTE_POINT_MISMATCH:" + key + ":" + endpoint)
            positions[endpoint] = pos
        _need(set(positions) == set(original_points),
              "INPUT_XML_ENDPOINT_COVERAGE_MISMATCH:" + key)
        _need(info.get("from") == asdict(original_from) and
              info.get("to") == asdict(original_to),
              "INPUT_XML_TYPED_COORDINATE_MISMATCH:" + key)
        od = _number(info.get("outsideDiameter"), "INPUT_XML_OUTSIDE_DIAMETER")
        wall = _number(info.get("wallThickness"), "INPUT_XML_WALL_THICKNESS")
        for field, claimed in (("DIAMETER", od), ("WALL_THICK", wall)):
            raw = attrs.get(field, "")
            if raw and raw != "-1.0101" and raw != "-1.010100":
                _need(claimed == float(raw),
                      "INPUT_XML_SOURCE_DIMENSION_MISMATCH:" + key + ":" + field)
        kind = info.get("componentType") or "PIPE"
        raw_type = info.get("rawComponentType") or kind
        ref_no = component.get("refNo") or "INPUT_XML-E" + str(index)
        # Real InputXML has element (span) records, not PSI116 nodes. Preserve
        # each true endpoint separately and retain the exact element key on both.
        for number, endpoint in enumerate(("FROM", "TO"), start=1):
            name = from_node if endpoint == "FROM" else to_node
            is_restraint = any(
                str(item.get("attributes", {}).get("NODE", "")) == name
                for item in (info.get("restraints") or [])
            )
            source_records.append(InputXmlNodeRecord(
                branch_index=0,
                branch_name=component.get("pipelineRef") or "CAESAR-INPUTXML",
                source_index=2 * index + (number - 1),
                node_number=_caesar_int(name, key + ":" + endpoint),
                node_name=info.get("fromName", "") if endpoint == "FROM"
                    else info.get("toName", ""),
                endpoint=number, component_type=str(kind).upper(),
                raw_component_type=str(raw_type).upper(),component_ref_no=ref_no,
                connection_type="",
                position=positions[endpoint], rigid=None,weight=None,
                outside_diameter=od,wall_thickness=wall,
                bend_radius=None,alpha_angle=None,has_restraint=is_restraint,
                raw_xml=ET.tostring(element, encoding="unicode"),
                inputxml_record_key=key,
                inputxml_endpoint=endpoint,
            ))
    branch_name = source_records[0].branch_name
    _need(all(item.branch_name == branch_name for item in source_records),
          "INPUT_XML_MULTIPLE_PIPELINES_NOT_YET_SUPPORTED")
    branches = (BranchRecord(0, branch_name, tuple(source_records)),)
    occurrences = _build_occurrences(branches)
    spans = _build_spans(branches, occurrences)
    return Psi116Document(
        source_path=source_name or "<inputxml>",
        source_text=text, source_sha256=sha, namespace=namespace,
        branches=branches, occurrences=tuple(occurrences), spans=tuple(spans),
    )
