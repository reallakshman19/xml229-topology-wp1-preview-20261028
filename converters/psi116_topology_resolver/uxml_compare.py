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
from .uxml_adapter import (
    _caesar_int, _verified_inputxml_document_runs, document_from_uxml,
    resolve_from_uxml,
)


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
    """Strict, evidence-bound comparison; no conversion-loss allow-list.

    Compare ALL source node occurrences, within PSI116 hub XYZ, and every
    semantic finding. Original source formats/SHAs intentionally differ.
    Any material discrepancy is UNEXPLAINED, hence CLI DIFFERENT (exit 1).
    This function never auto-approves or patches engineering source files.
    """
    from collections import Counter, defaultdict
    from .uxml_adapter import UxmlPsi116Error
    _need = lambda condition, code: (
        None if condition else (_ for _ in ()).throw(UxmlPsi116Error(code)))
    _need(isinstance(psi_uxml, dict) and
          isinstance(psi_uxml.get("sources"), list) and
          len(psi_uxml["sources"]) == 1 and
          isinstance(psi_uxml["sources"][0], dict) and
          psi_uxml["sources"][0].get("format") == "PSI116",
          "CROSS_FORMAT_PSI116_SOURCE_REQUIRED")
    _need(isinstance(input_uxml, dict) and
          isinstance(input_uxml.get("sources"), list) and
          len(input_uxml["sources"]) == 1 and
          isinstance(input_uxml["sources"][0], dict) and
          input_uxml["sources"][0].get("format") == "INPUT_XML",
          "CROSS_FORMAT_INPUT_XML_SOURCE_REQUIRED")
    frame = input_uxml.get("coordinateFrame") or {}
    _need(isinstance(frame, dict), "CROSS_FORMAT_HUB_FRAME_UNVERIFIED")
    _need(frame.get("hub") == "PSI116_XYZ_MM" and
          frame.get("transform") == "(X,-Z,Y)",
          "CROSS_FORMAT_HUB_FRAME_UNVERIFIED")
    # Verify original-source partition FIRST. The UXML document's run metadata
    # is not an independent frame authority: a forged all-anchored run must
    # fail before any absolute PSI116 comparison or global-proximity analysis.
    input_doc = document_from_uxml(input_uxml)
    trusted_runs = _verified_inputxml_document_runs(input_doc)
    _need(bool(trusted_runs) and all(anchored for _, anchored in trusted_runs),
          "CROSS_FORMAT_UNANCHORED_ABSOLUTE_FRAME_COMPARISON_REFUSED")

    psi_doc = document_from_uxml(psi_uxml)
    psi_result = resolve_from_uxml(psi_uxml)
    input_result = resolve_from_uxml(input_uxml)
    config = ResolverConfig()
    diffs: list[str] = []

    def add(kind: str, detail: str, classification: str,
            cause: str, evidence: str) -> None:
        diffs.append(
            f"UNEXPLAINED CLASS={classification} {kind}:{detail}; "
            f"CAUSE: {cause}; EVIDENCE: {evidence}")

    def records_by_number(doc):
        grouped=defaultdict(list)
        for branch in doc.branches:
            for row in branch.nodes:
                grouped[row.node_number].append(row)
        for records in grouped.values():
            records.sort(key=lambda row:(row.branch_index,row.source_index))
        return grouped
    pnums, inums=records_by_number(psi_doc),records_by_number(input_doc)
    source_evidence=defaultdict(list)
    for comp in input_uxml.get("components") or []:
        info=(comp.get("rawAttributes") or {}).get("inputXml") or {}
        literal=info.get("toNode")
        try:
            node_number=_caesar_int(literal, "CROSS_FORMAT_TO_NODE") if isinstance(literal,str) else None
        except UxmlPsi116Error:
            # Strict source-node refusals must never be swallowed by the
            # broad ValueError fallback; source validation normally runs first.
            raise
        except (ValueError, TypeError):
            continue
        source_evidence[node_number].append(info)

    for number in sorted(set(pnums)|set(inums),key=lambda x:(x is None,x or -1)):
        left,right=pnums.get(number,[]),inums.get(number,[])
        if len(left)!=len(right):
            add("NODE_OCCURRENCES",f"node={number} PSI116={len(left)} INPUT_XML={len(right)}",
                "A_PROJECTION_OR_B_CONVERSION_UNRESOLVED",
                "source route representation or transformation yields differing occurrences",
                f"PSI116 NodeNumber={number}; InputXML FROM_NODE/TO_NODE={number}; "
                "compare every occurrence, do not silently collapse")
        for index in range(max(len(left),len(right))):
            if index>=len(left) or index>=len(right):
                add("NODE_OCCURRENCE_MISSING",f"node={number} slot={index} "
                    f"PSI116={index<len(left)} INPUT_XML={index<len(right)}",
                    "A_PROJECTION_OR_B_CONVERSION_UNRESOLVED",
                    "one occurrence absent in paired source projection",
                    f"PSI116 NodeNumber={number}; InputXML PIPINGELEMENT FROM_NODE/TO_NODE")
                continue
            x,y=left[index],right[index]
            infos=source_evidence.get(number,[])
            sif=[(i,item) for i in infos for item in i.get("sifEvidence") or []
                 if item.get("typeCode") in (3,5) and
                 item.get("node") == i.get("toNode")]
            bend=[(i,item) for i in infos for item in
                  ([i.get("bendEvidence")] if i.get("bendEvidence") else [])]
            if sif:
                owner,item=sif[0]
                type_evidence=f"PIPINGELEMENT[{owner.get('elementIndex')}]/SIF@TYPE="+str(item["typeCode"])
            elif bend:
                owner,item=bend[0]
                type_evidence=f"PIPINGELEMENT[{owner.get('elementIndex')}]/BEND@RADIUS="+str(item["radius"])
            else:
                type_evidence=f"InputXML PIPINGELEMENT TO_NODE={number}, no source SIF or BEND owner"
            fields=("component_type","raw_component_type","component_ref_no",
                    "connection_type","node_name","rigid","weight",
                    "outside_diameter","wall_thickness","bend_radius",
                    "alpha_angle","has_restraint")
            for field in fields:
                xv,yv=getattr(x,field),getattr(y,field)
                if xv==yv:
                    continue
                cls="A_PROJECTION_UNRESOLVED"
                cause="source-backed adapter projection still differs from PSI116 engineering record"
                evidence=f"PSI116 Node[{number}]@{field}; InputXML source records "+ \
                         ",".join(i.get("recordKey","?") for i in infos)
                if field=="component_ref_no":
                    has_ref=any((i.get("sourceAttributes") or {}).get("REF_NO") for i in infos)
                    if not has_ref:
                        cls="B_WORKSPACE_CONVERSION_LOSS"
                        cause="Workspace CleanXML→5C does not emit original PSI116 ComponentRefNo as REF_NO"
                        evidence="InputXML PIPINGELEMENT@REF_NO ABSENT; source-only recordKey preserved"
                elif field in ("component_type","raw_component_type","connection_type") and sif:
                    cls="B_WORKSPACE_CONVERSION_LOSS"
                    cause="Workspace emits a literal SIF category that is not equivalent to the PSI116 component/connection declaration"
                    evidence=type_evidence
                elif field=="node_name" and not getattr(y,"node_name"):
                    cls="B_WORKSPACE_CONVERSION_LOSS"
                    cause="Workspace InputXML has no original FROM_NAME/TO_NAME at this endpoint"
                    evidence=f"PIPINGELEMENT NAME/TO_NAME only; NodeNumber={number}"
                elif field=="bend_radius" and bend:
                    cls="A_PROJECTION_UNRESOLVED"
                    cause="InputXML carries BEND radius but adapter does not match PSI116"
                    evidence=type_evidence
                elif field in ("outside_diameter","wall_thickness"):
                    physical=[i.get("physicalEvidence") or {} for i in infos]
                    evidence="; ".join(str(row.get("outsideDiameter" if field=="outside_diameter" else "wallThickness")) for row in physical)
                add("NODE_FIELD",f"node={number} slot={index} field={field} PSI116={xv!r} INPUT_XML={yv!r}",
                    cls,cause,evidence)
            if x.position is None or y.position is None:
                if x.position!=y.position:
                    add("NODE_POSITION",f"node={number} slot={index}",
                        "C_SOURCE_DIFFERENCE","missing physical position in one source",
                        "PSI116 Node@Position versus InputXML delta-chain absolute port")
            elif x.position.distance_to(y.position)>.001:
                add("NODE_POSITION",f"node={number} slot={index} POSITION PSI116={x.position.as_list()} "
                    f"INPUT_XML={y.position.as_list()} deltaMm={x.position.distance_to(y.position):.3f}",
                    "C_SOURCE_DIFFERENCE",
                    "geometric coordinates differ in the SAME PSI116_XYZ_MM hub frame",
                    f"PSI116 Node@Position; InputXML PIPINGELEMENT DELTA_X/Y/Z & FROM/TO_X/Y/Z at Node={number}")

    pfind=psi_result.findings_payload(config)
    ifind=input_result.findings_payload(config)
    pcounts=pfind["summary"]["findingCountsByCode"]
    icounts=ifind["summary"]["findingCountsByCode"]
    for code in sorted(set(pcounts)|set(icounts)):
        a,b=pcounts.get(code,0),icounts.get(code,0)
        if a!=b:
            add("FINDING_COUNT",f"{code} PSI116={a} INPUT_XML={b}",
                "A_PROJECTION_OR_B_CONVERSION_UNRESOLVED",
                "TopoFix unchanged engine emits different code frequency from paired source projections",
                f"findingCode={code}; original source evidence above; no suppression or allow-list")
    def finding_bag(payload):
        return Counter((
            item.get("code"),item.get("severity"),
            tuple(item.get("node_numbers") or item.get("nodeNumbers") or ()),
            round(float(item.get("length_mm") or item.get("lengthMm") or 0),3))
            for item in payload.get("findings",[]))
    pbag,ibag=finding_bag(pfind),finding_bag(ifind)
    for key in sorted(set(pbag)|set(ibag),key=str):
        if pbag[key]!=ibag[key]:
            add("FINDING_DETAIL",f"{key!r} PSI116={pbag[key]} INPUT_XML={ibag[key]}",
                "A_PROJECTION_OR_B_CONVERSION_UNRESOLVED",
                "unchanged engine reports different finding content under source projection",
                "finding code, severity, ALL node_numbers and measured length")
    pc=pfind.get("closureBindingWitnesses",[])
    ic=ifind.get("closureBindingWitnesses",[])
    if pc!=ic:
        add("CLOSURE_WITNESSES",f"PSI116={len(pc)} INPUT_XML={len(ic)}",
            "B_WORKSPACE_CONVERSION_LOSS",
            "InputXML source does not preserve lossless PSI116 CLOS binding declarations",
            "PSI116 ConnectionType=CLOS and InputXML source raw fields; no inferred CLOS")
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
