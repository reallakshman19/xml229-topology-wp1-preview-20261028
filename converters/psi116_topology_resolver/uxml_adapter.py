"""UXML-S1: consume XCU-owned uxml-topology-v1 PSI116 source records.

No copy of the JavaScript reader exists here. This adapter reconstitutes only
immutable TopoFix Python NodeRecord/BranchRecord, then calls the existing
_build_occurrences, _build_spans and analyze_document. Never emit XML or patch.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from html import escape as html_escape
from pathlib import Path
import json
import math
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
