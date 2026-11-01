"""UXML-S3B: original-byte CAESAR II InputXML patch-back, never a rebuild.

Authorized operation: uxml-edit-ops/v1 ALIAS_COINCIDENT_NODE only.
The original file and its XCU-owned strict UXML sourceRef are immutable inputs.
Only exact FROM_NODE/TO_NODE XML attribute value spans can be edited.
Every candidate is reread with the externally pinned XCU InputXML reader and
validated by the unchanged TopoFix engine/transaction checks before outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping
import xml.etree.ElementTree as ET

from .models import ResolverConfig
from .transaction import (
    AppliedOperation, TransactionPolicy, ValidationCheck, _finding_node_keys,
    _preflight, _selected_actions, _validate_transaction,
)
from .uxml_adapter import (
    UxmlPsi116Error, _caesar_int, _caesar_original_rows, _record_key, resolve_from_uxml,
)

SCHEMA = "uxml-edit-ops/v1"
REPORT_SCHEMA = "inputxml-topofix-validation/v1"
POLICY_FIELDS = frozenset(asdict(TransactionPolicy()))
PAYLOAD_FIELDS = frozenset({"schema", "sourceFormat", "fileSha256", "policy", "ops"})
OP_FIELDS = frozenset({"opId", "kind", "sourceActionId", "fileSha256", "targets", "params"})
# Quoted XML values may contain >. Parse the tag without interpreting those as ends.
TAG = re.compile(rb"""<PIPINGELEMENT\b(?:"[^"]*"|'[^']*'|[^"'>])*>""", re.I)
FIELD = re.compile(rb"""\s+(FROM_NODE|TO_NODE)\s*=\s*(["'])(.*?)\2""", re.S)


# XCU pin manifest and verifier follow the source-owned checkout, not vendored code.

# Git blob identities from the externally pinned XCU #244 commit, not copies
# of XCU reader source. A partial or modified local XCU root is NOT trusted.
XCU_S3B_COMMIT = "980f325323b87a9daaa8ee6523c6d85132b9208f"
XCU_BLOBS = {
    "package.json": "8b0cc1e976ef2cd3cd10f344b37463738d22ea3d",
    "uxml/UxmlConstants.js": "457b970f9cbccd29d38cecd0842614c339108107",
    "uxml/UxmlProfileDetector.js": "b4edfc1b47337a0ad62d2a01c0c8f2ff86844803",
    "uxml/UxmlTypes.js": "5bac50ca692c483c3800ae7ec712710e7ae08572",
    "uxml/UxmlValidationGate.js": "7a6070f9b77602f227a30d7e06a3e425d17c9c16",
    "uxml/UxmlPsi116SchemaMapper.js": "978a63141fb94ef9cad3c8eaa637a37675a605f9",
    "uxml/UxmlInputXmlSchemaMapper.js": "1e730b594c536d955a5d1a24190d0ca4dc147d27",
    "uxml/UxmlInputXmlDeltaGraph.js": "8b45016bccf2a759108dfa6efc9827cc1c2eba7d",
    "utils/line-no-metadata.js": "8315e966d5911ba60703ee3726166e3a3035c6df",
    "tools/psi116-to-uxml.mjs": "7148fc20000963c5a32be27a7787705745e1d30b",
    "tools/inputxml-to-uxml.mjs": "7f32736308a0baea86b95c3281bb0bbd71d12176",
    "tests/fixtures/uxml-s3-synthetic.psi116.xml": "f262e6a4affb5c5a929b12c415a04569b79dbe46",
    "tests/fixtures/uxml-s3-synthetic.workspace.input.xml": "ed141547b7b8cb4ee0cc4c07b1d888850681749e",
    "tests/fixtures/uxml-s3-synthetic.workspace.delta-only.input.xml": "4888341e419b0efbd5deb93c012fdbe672014773",
    "docs/GREInputxml.xml": "e7dc8ff9b1082d489609980bb495ced048a81679",
    "docs/PLB314Inputxml.xml": "b0bdcf853992cee6ae7911e7a4c035c6b7ff7990",
}


def pinned_reader(path: Path, root: Path) -> dict:
    for relative, expected in XCU_BLOBS.items():
        f = root / relative
        need(f.is_file(), "INPUT_XML_PINNED_XCU_BLOB_MISSING:" + relative)
        content = f.read_bytes()
        blob = sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()
        need(blob == expected, "INPUT_XML_PINNED_XCU_BLOB_MISMATCH:" + relative)
    tool = root / "tools" / "inputxml-to-uxml.mjs"
    try:
        p = subprocess.run(["node", str(tool), str(path)],
                           cwd=root, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise InputXmlPatchError("INPUT_XML_PINNED_NODE_RUNTIME_REQUIRED") from exc
    need(p.returncode == 0, "INPUT_XML_PINNED_READER_FAILED:" +
         (p.stderr.strip() or str(p.returncode)))
    data = json.loads(p.stdout)
    need(isinstance(data, dict), "INPUT_XML_PINNED_READER_RESULT_INVALID")
    return data

class InputXmlPatchError(ValueError):
    """Specific fail-closed refusal; no output or validation file is emitted."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise InputXmlPatchError(code)


def verify_policy(obj: object) -> TransactionPolicy:
    need(isinstance(obj, dict) and set(obj) == POLICY_FIELDS,
         "INPUT_XML_EDIT_POLICY_SCHEMA_INVALID")
    native = TransactionPolicy()
    need(type(obj["minimum_confidence"]) in (int, float) and
         obj["minimum_confidence"] == native.minimum_confidence,
         "UXML_POLICY_WIDENING_REFUSED:minimum_confidence")
    need(obj["require_no_blocking_plan_actions"] is True and
         native.require_no_blocking_plan_actions is True,
         "UXML_POLICY_WIDENING_REFUSED:require_no_blocking_plan_actions")
    need(obj["apply_all_safe"] is False,
         "INPUT_XML_EXPLICIT_ACTION_IDS_REQUIRED")
    need(obj["joint_repairs"] == [] and obj["short_element_requests"] == [],
         "INPUT_XML_MANUAL_REPAIRS_REFUSED")
    ids = obj["selected_action_ids"]
    need(isinstance(ids, list) and ids and
         all(isinstance(v, str) and v for v in ids) and
         len(ids) == len(set(ids)), "INPUT_XML_ACTION_IDS_INVALID")
    policy = TransactionPolicy(selected_action_ids=tuple(ids))
    policy.validate()
    return policy


def exact_original_refs(uxml: dict, data: bytes) -> tuple[list[ET.Element], dict[str, dict]]:
    sha = sha256(data).hexdigest()
    sources = uxml.get("sources")
    need(isinstance(sources, list) and len(sources) == 1 and
         sources[0].get("format") == "INPUT_XML",
         "INPUT_XML_SINGLE_ORIGINAL_SOURCE_REQUIRED")
    need(sources[0].get("hash") == sha and
         sources[0].get("sourceText", "").encode("utf-8") == data,
         "INPUT_XML_STALE_ORIGINAL_SHA256")
    # This adapter independently verifies all original sourceRefs, ports,
    # literal SIF/BEND physical fields and original delta geometry.
    resolved = resolve_from_uxml(uxml)
    rows, _ = _caesar_original_rows(resolved.document.source_text)
    comps = uxml.get("components")
    need(isinstance(comps, list) and len(comps) == len(rows),
         "INPUT_XML_ORIGINAL_ELEMENT_COUNT_DRIFT")
    refs: dict[str, dict] = {}
    for index, (row, comp) in enumerate(zip(rows, comps)):
        from_node, to_node = row.attrib.get("FROM_NODE"), row.attrib.get("TO_NODE")
        key = _record_key(index, from_node, to_node)
        source_refs = comp.get("sourceRefs")
        need(isinstance(source_refs, list) and len(source_refs) == 1,
             "INPUT_XML_SOURCE_REF_INVALID")
        ref = source_refs[0]
        need(ref.get("format") == "INPUT_XML" and
             ref.get("fileSha256") == sha and
             ref.get("elementIndex") == index and
             ref.get("recordKey") == key and
             ref.get("fromNode") == from_node and ref.get("toNode") == to_node,
             "INPUT_XML_SOURCE_REF_ORIGINAL_MISMATCH:" + key)
        need(key not in refs, "INPUT_XML_AMBIGUOUS_RECORD_KEY:" + key)
        refs[key] = ref
    return rows, refs


def byte_record_spans(data: bytes, rows: list[ET.Element]) -> list[dict]:
    # A byte locator, NOT a competing XML reader. Refuse comments/CDATA,
    # namespaces, duplicate lexical candidates or unresolvable attribute spans.
    try:
        text = data.decode("utf-8")
        need(text.encode("utf-8") == data, "INPUT_XML_NON_UTF8_SOURCE_REFUSED")
    except UnicodeDecodeError as exc:
        raise InputXmlPatchError("INPUT_XML_NON_UTF8_SOURCE_REFUSED") from exc
    matches = list(TAG.finditer(data))
    need(len(matches) == len(rows), "INPUT_XML_BYTE_RECORD_ORDINAL_AMBIGUOUS")
    found = []
    for index, (match, row) in enumerate(zip(matches, rows)):
        tag = match.group()
        attrs: dict[str, tuple[int, int, str]] = {}
        for found_attr in FIELD.finditer(tag):
            name = found_attr.group(1).decode("ascii").upper()
            need(name not in attrs, "INPUT_XML_DUPLICATE_NODE_ATTRIBUTE:" + str(index))
            raw = found_attr.group(3)
            try:
                value = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise InputXmlPatchError("INPUT_XML_NODE_VALUE_NON_UTF8") from exc
            attrs[name] = (match.start() + found_attr.start(3),
                           match.start() + found_attr.end(3), value)
        need(set(attrs) == {"FROM_NODE", "TO_NODE"} and all(
             attrs[name][2] == row.attrib.get(name) for name in attrs),
             "INPUT_XML_BYTE_ATTRIBUTE_SOURCE_MISMATCH:E" + str(index))
        found.append(attrs)
    return found


def _format_like(original: str, target: int) -> bytes:
    need(re.fullmatch(r"[+]?[0-9]+(?:\.[0-9]+)?", original) is not None,
         "INPUT_XML_NONCANONICAL_NODE_NUMBER")
    digits = len(original.split(".", 1)[1]) if "." in original else 0
    return (f"{target:.{digits}f}" if digits else str(target)).encode("ascii")


def _target_field_losses(uxml: dict, writes: list[tuple[int, str, int, int]]) -> None:
    losses = uxml.get("lossContract")
    need(isinstance(losses, list), "INPUT_XML_LOSS_CONTRACT_MISSING")
    for index, field, before, _ in writes:
        path = f"/CAESARII/PIPINGMODEL/PIPINGELEMENT[{index}]"
        for loss in losses:
            need(isinstance(loss, dict) and isinstance(loss.get("details"), dict),
                 "INPUT_XML_LOSS_CONTRACT_INVALID")
            info = loss["details"]
            source_path = info.get("path") or info.get("sourcePath") or ""
            source_field = info.get("field") or ""
            if source_path == path and source_field.upper() == "@" + field:
                raise InputXmlPatchError("INPUT_XML_LOSS_CONTRACT_FIELD_TOUCH:" +
                                         path + ":@" + field)
        # Never change a source node referenced in unrepresented descendants
        # such as SIF, RESTRANT, HANGER or vendor records.
        children = uxml["components"][index]["rawAttributes"]["inputXml"]
        for item in children.get("sifEvidence") or []:
            if item.get("node") and str(item["node"]).split(".", 1)[0] == str(before):
                raise InputXmlPatchError("INPUT_XML_CLASS_B_SIF_OWNER_TOUCH_REFUSED")
        for child in children.get("restraints") or []:
            for attr, val in (child.get("attributes") or {}).items():
                if attr.upper() in {"NODE", "CNODE"} and str(val).split(".", 1)[0] == str(before):
                    raise InputXmlPatchError("INPUT_XML_RAW_CHILD_NODE_REFERENCE_TOUCH_REFUSED")


def _get_actions(uxml: dict, payload: dict, result) -> tuple[TransactionPolicy, tuple, list[tuple[int, str, int, int]]]:
    need(isinstance(payload, dict) and set(payload) == PAYLOAD_FIELDS and
         payload.get("schema") == SCHEMA and
         payload.get("sourceFormat") == "INPUT_XML",
         "INPUT_XML_EDIT_OPS_SCHEMA_INVALID")
    sha = uxml["sources"][0]["hash"]
    need(payload.get("fileSha256") == sha, "INPUT_XML_FILE_SHA256_MISMATCH")
    policy = verify_policy(payload["policy"])
    ops = payload.get("ops")
    need(isinstance(ops, list) and len(ops) == len(policy.selected_action_ids),
         "INPUT_XML_SELECTED_OPS_SET_MISMATCH")
    actions = _selected_actions(result, policy)
    need(not _preflight(result, actions, policy),
         "INPUT_XML_NATIVE_POLICY_BLOCKED:" + ",".join(_preflight(result, actions, policy)))
    records = {r.key: r for branch in result.document.branches for r in branch.nodes}
    findings = {f.finding_id: f for f in result.findings}
    components = uxml["components"]
    key_index = {c["sourceRefs"][0]["recordKey"]: ix for ix, c in enumerate(components)}
    by_id = {a.action_id: a for a in actions}
    observed = []
    writes: list[tuple[int, str, int, int]] = []
    for op in ops:
        need(isinstance(op, dict) and set(op) == OP_FIELDS, "INPUT_XML_OP_FIELDS_INVALID")
        identifier = op.get("sourceActionId")
        need(identifier in by_id and
             op.get("opId") == "UXML-OP-" + str(identifier) and
             op.get("fileSha256") == sha, "INPUT_XML_OP_ID_OR_SHA_INVALID")
        action = by_id[identifier]
        need(action.disposition == "ALIAS_COINCIDENT_NODE" and
             op.get("kind") == action.disposition and
             action.status == "PROPOSED" and not action.blockers and
             action.confidence >= policy.minimum_confidence,
             "INPUT_XML_REVIEW_ONLY_OR_UNSUPPORTED_ACTION:" + str(identifier))
        need(op.get("params") == [dict(x) for x in action.proposed_changes],
             "INPUT_XML_OP_PARAMS_NOT_SOURCE_AUTHORIZED:" + str(identifier))
        keys = {key for fid in action.finding_ids for key in findings[fid].node_keys}
        record_keys = sorted({
            source_key for key in keys for source_key in
            records[key].inputxml_record_keys
        })
        for key in op.get("targets", []):
            need(key in key_index, "INPUT_XML_UNKNOWN_RECORD_KEY:" + str(key))
        need(op.get("targets") == record_keys,
             "INPUT_XML_OP_TARGETS_NOT_SOURCE_AUTHORIZED:" + str(identifier))
        need(action.owner_node_number is not None and
             len(action.absorbed_node_numbers) == 1,
             "INPUT_XML_ALIAS_OWNER_OR_ABSORBED_AMBIGUOUS")
        old = action.absorbed_node_numbers[0]
        new = action.owner_node_number
        need(old != new and old > 0 and new > 0, "INPUT_XML_ALIAS_NODE_INVALID")
        captured = 0
        for row in (records[k] for k in keys if records[k].node_number == old):
            for source_key in row.inputxml_record_keys:
                idx = key_index[source_key]
                attrs = components[idx]["rawAttributes"]["inputXml"]["sourceAttributes"]
                for field in ("FROM_NODE", "TO_NODE"):
                    if attrs.get(field) and attrs[field].split(".", 1)[0] == str(old):
                        candidate = (idx, field, old, new)
                        if candidate not in writes:
                            writes.append(candidate)
                            captured += 1
        need(captured > 0, "INPUT_XML_ALIAS_NO_SOURCE_ATTRIBUTE")
        observed.append(identifier)
    need(set(observed) == set(policy.selected_action_ids) and
         len(observed) == len(set(observed)),
         "INPUT_XML_ACTION_IDS_NOT_EXACT")
    need(len({(i, f) for i, f, _, _ in writes}) == len(writes),
         "INPUT_XML_CONFLICTING_SOURCE_FIELD_WRITES")
    # No silently unrenumbered occurrence anywhere in the original file.
    old_sources = Counter((_caesar_int(v, "SOURCE_NODE"), idx, fld)
        for idx, c in enumerate(components)
        for fld in ("FROM_NODE", "TO_NODE")
        for v in [c["rawAttributes"]["inputXml"]["sourceAttributes"].get(fld)]
        if v is not None)
    for action in actions:
        old = action.absorbed_node_numbers[0]
        before = {(i, fld) for (num, i, fld) in old_sources if num == old}
        selected = {(i, fld) for i, fld, num, _ in writes if num == old}
        need(before == selected, "INPUT_XML_ALIAS_UNACCOUNTED_SOURCE_OCCURRENCE")
    _target_field_losses(uxml, writes)
    return policy, actions, writes


def patch_inputxml(original: Path, uxml: dict, payload: dict,
                   xcu_root: Path, config: ResolverConfig | None = None) -> tuple[bytes, dict]:
    config = config or ResolverConfig()
    data = original.read_bytes()
    # Independently regenerate from actual original bytes: never let a
    # caller remove lossContract warnings or forge a UXML permission.
    canonical = pinned_reader(original, xcu_root)
    need(canonical == uxml, "INPUT_XML_UXML_NOT_FROM_PINNED_ORIGINAL")
    rows, refs = exact_original_refs(uxml, data)
    result = resolve_from_uxml(uxml, config, source_name=str(original))
    need(result.document.source_text.encode("utf-8") == data,
         "INPUT_XML_ORIGINAL_BYTES_MISMATCH")
    policy, actions, writes = _get_actions(uxml, payload, result)
    need(bool(writes), "INPUT_XML_NO_AUTHORIZED_EDIT")
    span_attrs = byte_record_spans(data, rows)
    replacements: list[tuple[int, int, bytes]] = []
    for index, field, old, new in writes:
        source_ref = uxml["components"][index]["sourceRefs"][0]
        need(refs.get(source_ref["recordKey"]) == source_ref,
             "INPUT_XML_ORIGINAL_RECORD_IDENTITY_MISMATCH")
        start, end, literal = span_attrs[index][field]
        need(_caesar_int(literal, "PATCH_FIELD") == old,
             "INPUT_XML_ORIGINAL_NODE_FIELD_DRIFT")
        replacements.append((start, end, _format_like(literal, new)))
    replacements.sort()
    need(all(a[1] <= b[0] for a, b in zip(replacements, replacements[1:])),
         "INPUT_XML_OVERLAPPING_EDITS_REFUSED")
    candidate = data
    for start, end, repl in reversed(replacements):
        candidate = candidate[:start] + repl + candidate[end:]
    need(candidate != data, "INPUT_XML_EDIT_DID_NOT_CHANGE_SOURCE")
    with tempfile.TemporaryDirectory(prefix="topofix-inputxml-reread-") as tmp:
        path = Path(tmp) / "patched.input.xml"
        path.write_bytes(candidate)
        reread = pinned_reader(path, xcu_root)
    need(reread.get("sources", [{}])[0].get("hash") == sha256(candidate).hexdigest(),
         "INPUT_XML_PATCHED_SOURCE_SHA_NOT_VERIFIED")
    # Verify all newly issued source refs against patched *original* bytes.
    after = resolve_from_uxml(reread, config)
    patched_rows, _ = _caesar_original_rows(reread["sources"][0]["sourceText"])
    before_attrs = [dict(row.attrib) for row in rows]
    after_attrs = [dict(row.attrib) for row in patched_rows]
    expected = [dict(a) for a in before_attrs]
    for index, field, _, new in writes:
        expected[index][field] = _format_like(before_attrs[index][field], new).decode("ascii")
    # Only the explicitly selected node number attributes can differ.
    need(after_attrs == expected, "INPUT_XML_OTHER_SOURCE_ATTRIBUTE_CHANGED")
    # Native transaction validation is used unchanged, with source-bound
    # ALIAS_NODE_NUMBER receipts. This also verifies all selected findings.
    action_by_absorbed = {}
    for action in actions:
        for node in action.absorbed_node_numbers:
            need(node not in action_by_absorbed,
                 "INPUT_XML_OVERLAPPING_ABSORBED_ACTIONS_REFUSED")
            action_by_absorbed[node] = action
    operations = tuple(AppliedOperation(
        operation_id=f"OP-{n:06d}", action_id=action_by_absorbed[old].action_id,
        disposition="ALIAS_COINCIDENT_NODE", operation="ALIAS_NODE_NUMBER",
        branch_name=action_by_absorbed[old].branch_name,
        source_node_number=old, retained_node_number=new,
        before=old, after=new, authority=action_by_absorbed[old].authority,
        source_xml_sha256=sha256(data).hexdigest())
        for n, (_, _, old, new) in enumerate(writes, 1))
    native = _validate_transaction(result, after, actions, operations)
    before_identifiers = {_caesar_int(r.attrib[f], "BEFORE_NODE") for r in rows
                          for f in ("FROM_NODE", "TO_NODE")}
    after_identifiers = {_caesar_int(r.attrib[f], "AFTER_NODE") for r in patched_rows
                         for f in ("FROM_NODE", "TO_NODE")}
    expected_ids = set(before_identifiers)
    for _, _, old, new in writes:
        expected_ids.discard(old)
        expected_ids.add(new)
    unchanged_records = set(range(len(rows))) - {i for i, _, _, _ in writes}
    old_record_spans = [row["rawAttributes"]["inputXml"]["rawXml"]
                        for row in uxml["components"]]
    new_record_spans = [row["rawAttributes"]["inputXml"]["rawXml"]
                        for row in reread["components"]]
    checks = list(native) + [
        ValidationCheck("ORIGINAL_FILE_SHA256_BOUND", True, True,
                        "Original bytes and every sourceRef were verified before edits."),
        ValidationCheck("NO_REBUILD_AND_UNTOUCHED_RECORDS_BYTE_IDENTICAL",
                        all(old_record_spans[i] == new_record_spans[i]
                            for i in unchanged_records), True,
                        "All unselected original PIPINGELEMENT fragments remain byte-identical.",
                        len(unchanged_records), len(unchanged_records)),
        ValidationCheck("PIPINGELEMENT_COUNT_PRESERVED",
                        len(rows) == len(patched_rows), True,
                        "Every original InputXML PIPINGELEMENT retained.",
                        len(rows), len(patched_rows)),
        ValidationCheck("RESTRAINT_COUNT_PRESERVED_EXACT",
                        len([e for row in rows for e in row if
                             e.tag.rsplit('}', 1)[-1] in ('RESTRAINT', 'RESTRANT')]) ==
                        len([e for row in patched_rows for e in row if
                             e.tag.rsplit('}', 1)[-1] in ('RESTRAINT', 'RESTRANT')]),
                        True, "All original restraint elements retained."),
        ValidationCheck("NODE_IDENTIFIER_ACCOUNTING",
                        after_identifiers == expected_ids, True,
                        "Every absorbed source node is replaced with its approved owner.",
                        sorted(before_identifiers), sorted(after_identifiers)),
        ValidationCheck("TWO_PORTS_PER_ELEMENT_PRESERVED",
                        len(reread.get("ports") or []) == 2 * len(rows), True,
                        "Each PIPINGELEMENT retains FROM and TO occurrences."),
        ValidationCheck("PINNED_UXML_REREAD_AND_FINDINGS",
                        True, True,
                        "XCU pinned reader and original TopoFix findings engine reran."),
    ]
    failures = [x.code for x in checks if x.blocking and not x.passed]
    need(not failures, "INPUT_XML_POST_PATCH_VALIDATION_FAILED:" + ",".join(failures))
    report = {
        "schema": REPORT_SCHEMA, "committed": True,
        "originalSha256": sha256(data).hexdigest(),
        "patchedSha256": sha256(candidate).hexdigest(),
        "sourceFormat": "INPUT_XML", "policy": asdict(policy),
        "appliedActionIds": [a.action_id for a in actions],
        "editedOriginalRecords": sorted({i for i, _, _, _ in writes}),
        "editCount": len(writes),
        "checks": [asdict(check) for check in checks],
        "summary": {"checkCount": len(checks),
                    "passedCheckCount": sum(check.passed for check in checks),
                    "blockingFailureCount": 0},
    }
    return candidate, report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("original", type=Path)
    p.add_argument("ops_json", type=Path)
    p.add_argument("--uxml", type=Path, required=True)
    p.add_argument("--xcu-root", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--validation", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        protected = (a.original, a.ops_json, a.uxml)
        need(a.output.resolve() not in {f.resolve() for f in protected} and
             a.validation.resolve() not in {f.resolve() for f in protected},
             "INPUT_XML_PROTECTED_SOURCE_OVERWRITE_REFUSED")
        need(a.output.resolve() != a.validation.resolve(),
             "INPUT_XML_OUTPUT_VALIDATION_PATH_COLLISION")
        need(not a.output.exists() and not a.validation.exists(),
             "INPUT_XML_OUTPUT_ALREADY_EXISTS_REFUSED")
        xcu = a.xcu_root or Path(os.environ.get("XCU_UXML_ROOT") or "/not-pinned")
        candidate, report = patch_inputxml(
            a.original, json.loads(a.uxml.read_text(encoding="utf-8")),
            json.loads(a.ops_json.read_text(encoding="utf-8")), xcu)
        # All checks complete, then emit only into new exclusive output paths.
        try:
            with a.output.open("xb") as out:
                out.write(candidate)
            with a.validation.open("x", encoding="utf-8") as out:
                json.dump(report, out, indent=2, sort_keys=True)
                out.write("\n")
        except OSError:
            a.output.unlink(missing_ok=True)
            a.validation.unlink(missing_ok=True)
            raise
        print("EQUAL")
        return 0
    except (InputXmlPatchError, UxmlPsi116Error, OSError, ValueError,
            KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print("DIFFERENT")
        print("ERROR: " + str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
