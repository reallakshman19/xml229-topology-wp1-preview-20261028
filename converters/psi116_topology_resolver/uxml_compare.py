"""UXML-S1 read-only exact equivalence: existing PSI116 parser vs XCU UXML hub.

Usage: python -m converters.psi116_topology_resolver.uxml_compare <psi116.xml> <uxml.json>
Print EQUAL on matching NodeRecords, occurrences/spans, findings and CLOS
closureBindingWitnesses. Any difference is explicit, deterministic and fails.
No writer or original-source mutation is ever invoked.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import argparse
import json
import sys

from .models import ResolverConfig
from .parser import read_psi116_xml
from .resolver import analyze_document
from .uxml_adapter import document_from_uxml, resolve_from_uxml


def _diff(path, left, right, out):
    if type(left) is not type(right):
        out.append(f"{path}: TYPES {type(left).__name__} != {type(right).__name__}")
        return
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            address = path + "/" + str(key)
            if key not in left: out.append(address + ": DIRECT_MISSING")
            elif key not in right: out.append(address + ": UXML_MISSING")
            else: _diff(address, left[key], right[key], out)
    elif isinstance(left, (list, tuple)):
        if len(left) != len(right):
            out.append(f"{path}: LENGTH direct={len(left)} uxml={len(right)}")
        for index in range(min(len(left), len(right))):
            _diff(path + "/" + str(index), left[index], right[index], out)
    elif left != right:
        out.append(f"{path}: direct={left!r} uxml={right!r}")


def compare_psi116_uxml(source: str | Path, uxml: dict) -> list[str]:
    source = Path(source)
    config = ResolverConfig()
    direct_doc = read_psi116_xml(source)
    adapted_doc = document_from_uxml(uxml, source_name=str(source))
    direct_result = analyze_document(direct_doc, config)
    adapted_result = resolve_from_uxml(uxml, config, source_name=str(source))

    def records(document):
        return [[asdict(node) for node in branch.nodes] for branch in document.branches]
    left = {
        "records": records(direct_doc),
        "occurrences": [asdict(item) for item in direct_doc.occurrences],
        "spans": [asdict(item) for item in direct_doc.spans],
        "source": {
            "sha256": direct_doc.source_sha256,
            "namespace": direct_doc.namespace,
            "sourceText": direct_doc.source_text,
        },
        "findings": direct_result.findings_payload(config),
        "fix_actions": direct_result.fix_plan_payload(config),
    }
    right = {
        "records": records(adapted_doc),
        "occurrences": [asdict(item) for item in adapted_doc.occurrences],
        "spans": [asdict(item) for item in adapted_doc.spans],
        "source": {
            "sha256": adapted_doc.source_sha256,
            "namespace": adapted_doc.namespace,
            "sourceText": adapted_doc.source_text,
        },
        "findings": adapted_result.findings_payload(config),
        "fix_actions": adapted_result.fix_plan_payload(config),
    }
    differences = []
    _diff("", left, right, differences)
    return differences



def compare_cross_format_uxml(psi_uxml: dict, input_uxml: dict) -> list[str]:
    """Enumerate exact source/semantic/finding differences, never forge equality.

    Same model through two different source formats. RecordKey and SHA are
    *intentionally different*; compare engineering semantics and findings,
    then explain source losses and the Workspace CAESAR axis transform.
    """
    psi_doc = document_from_uxml(psi_uxml)
    input_doc = document_from_uxml(input_uxml)
    psi_result = resolve_from_uxml(psi_uxml)
    input_result = resolve_from_uxml(input_uxml)
    config = ResolverConfig()
    diffs = []

    psi_records = [r for b in psi_doc.branches for r in b.nodes]
    input_records = [r for b in input_doc.branches for r in b.nodes]
    if len(psi_records) != len(input_records):
        diffs.append(
            f"RECORD_COUNT: PSI116={len(psi_records)} INPUT_XML={len(input_records)}; "
            "CAUSE: Workspace PIPINGELEMENT is an endpoint pair/span, not "
            "one PSI116 source Node; converter may omit helper/duplicate nodes")

    def by_number(records):
        out = {}
        for record in records:
            if record.node_number is not None:
                out.setdefault(record.node_number, []).append(record)
        return out
    pnums, inums = by_number(psi_records), by_number(input_records)
    for number in sorted(set(pnums) | set(inums)):
        x, y = pnums.get(number, []), inums.get(number, [])
        if not x or not y:
            diffs.append(f"NODE:{number}: PSI116_OCCURRENCES={len(x)} INPUT_XML_OCCURRENCES={len(y)}; "
                         "CAUSE: Workspace route selection, renumbering or PIPINGELEMENT endpoint expansion")
            continue
        if len(x) != len(y):
            diffs.append(f"NODE:{number}: REPEATED_SOURCE_OCCURRENCES PSI116={len(x)} INPUT_XML={len(y)}; "
                         "CAUSE: converted InputXML endpoints repeat intermediate route nodes")
        xp, yp = x[0], y[0]
        fields = ("component_type", "raw_component_type", "component_ref_no",
                  "connection_type", "node_name", "rigid", "weight",
                  "outside_diameter", "wall_thickness", "bend_radius",
                  "alpha_angle", "has_restraint")
        for field in fields:
            xv, yv = getattr(xp, field), getattr(yp, field)
            if xv != yv:
                diffs.append(f"NODE:{number}:{field}: PSI116={xv!r} INPUT_XML={yv!r}; "
                             "CAUSE: original PSI116 node field missing, inferred, "
                             "or reassigned by Workspace CleanXML → 5C conversion")
        if xp.position is not None and yp.position is not None:
            expected = (xp.position.x, xp.position.z, -xp.position.y)
            actual = (yp.position.x, yp.position.y, yp.position.z)
            if any(abs(a-b) > 0.00001 for a,b in zip(expected,actual)):
                diffs.append(f"NODE:{number}:POSITION: expected Workspace CAESAR "
                             f"X,Z,-Y frame={expected!r}, actual={actual!r}; "
                             "CAUSE: coordinate transform, node re-use, or source geometry loss")

    pfind = psi_result.findings_payload(config)
    ifind = input_result.findings_payload(config)
    pcounts = pfind["summary"].get("findingCountsByCode", {})
    icounts = ifind["summary"].get("findingCountsByCode", {})
    for code in sorted(set(pcounts) | set(icounts)):
        if pcounts.get(code, 0) != icounts.get(code, 0):
            diffs.append(f"FINDING_COUNT:{code}: PSI116={pcounts.get(code,0)} "
                         f"INPUT_XML={icounts.get(code,0)}; CAUSE: converted endpoint "
                         "expansion / missing node semantics enumerated above")
    # Every finding in each format is accounted for, even where the engines
    # generated different source-specific node keys or span identifiers.
    def finding_bag(payload):
        from collections import Counter
        return Counter((
            f.get("code"), f.get("severity"),
            tuple(f.get("node_numbers") or f.get("nodeNumbers") or ()),
            round(float(f.get("length_mm") or f.get("lengthMm") or 0), 6)
        ) for f in payload.get("findings", []))
    pa, ia = finding_bag(pfind), finding_bag(ifind)
    for item in sorted(set(pa) | set(ia),key=str):
        if pa[item] != ia[item]:
            diffs.append(f"FINDING_DETAIL:{item!r}: PSI116={pa[item]} "
                         f"INPUT_XML={ia[item]}; CAUSE: source element/endpoint "
                         "multiplicity, missing fields or conversion semantics")
    pw = pfind.get("closureBindingWitnesses", [])
    iw = ifind.get("closureBindingWitnesses", [])
    if pw != iw:
        diffs.append(f"CLOSURE_WITNESSES: PSI116={len(pw)} INPUT_XML={len(iw)}; "
                     "CAUSE: Workspace InputXML has no lossless PSI116 CLOS "
                     "declaration/source-ref identity in this S3 read-only scope")
    return diffs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("psi116_xml", type=Path,
                        help="Direct PSI116 source XML, or PSI116 UXML with --cross-format")
    parser.add_argument("uxml_json", type=Path,
                        help="UXML JSON; with --cross-format use INPUT_XML-sourced UXML JSON")
    parser.add_argument("--cross-format", action="store_true",
                        help="Compare same model PSI116 UXML vs CAESAR InputXML UXML")
    args = parser.parse_args(argv)
    try:
        uxml = json.loads(args.uxml_json.read_text(encoding="utf-8"))
        differences = (compare_cross_format_uxml(
            json.loads(args.psi116_xml.read_text(encoding="utf-8")), uxml)
            if args.cross_format else compare_psi116_uxml(args.psi116_xml, uxml))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("DIFFERENT")
        print("ERROR: " + str(exc))
        return 1
    if differences:
        print("DIFFERENT")
        for diff in differences:
            print(diff)
        return 1
    print("EQUAL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
