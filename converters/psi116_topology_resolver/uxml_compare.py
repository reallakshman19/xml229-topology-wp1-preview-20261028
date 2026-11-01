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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("psi116_xml", type=Path)
    parser.add_argument("uxml_json", type=Path)
    args = parser.parse_args(argv)
    try:
        uxml = json.loads(args.uxml_json.read_text(encoding="utf-8"))
        differences = compare_psi116_uxml(args.psi116_xml, uxml)
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
