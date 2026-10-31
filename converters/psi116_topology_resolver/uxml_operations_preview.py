"""UXML-PREVIEW: presentation-only projection of the *published* S2 edit ops.

No new transaction, mutation or approval route. Uses export_edit_ops as the
exclusive list of proposed Auto-eligible operations, and reads original source
record semantics to describe the exact fields that S2's existing transaction
would edit. Unknown or unrepresentable operations fail closed.
"""
from __future__ import annotations

from collections import Counter
from typing import Any
import xml.etree.ElementTree as ET

from .models import ResolverConfig
from .transaction import TransactionPolicy
from .uxml_adapter import resolve_from_uxml
from .uxml_edit_ops import export_edit_ops

SCHEMA = "uxml-operations-preview/v1"
NAMES = {
    "ALIAS_COINCIDENT_NODE": "Alias coincident node",
    "CONTRACT_PRESERVE_OWNER": "Preserve owner; alias node",
    "SAFE_DROP_PIPE_GEOMETRY": "Remove dispensable pipe record",
    "REMOVE_FALSE_RIGID": "Clear incorrect rigid flag",
    "CLOSE_PORT_CONNECTION": "Close compatible connection ports",
}
class OperationsPreviewError(ValueError):
    """A missing exact change witness is never a blank 'safe' row."""


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise OperationsPreviewError(code)


def _source_text(record: Any, field: str) -> str | None:
    """Read an ORIGINAL Node field without rebuilding, writing or guessing."""
    element = ET.fromstring(record.raw_xml)
    for child in element:
        if isinstance(child.tag, str) and child.tag.rsplit("}", 1)[-1] == field:
            return child.text
    return None


def _preview_fields(op: dict, action: Any, records: dict[str, Any]) -> list[dict]:
    kind = op["kind"]
    changes: list[dict] = []
    if kind in {"ALIAS_COINCIDENT_NODE", "CONTRACT_PRESERVE_OWNER",
                "SAFE_DROP_PIPE_GEOMETRY"}:
        targets = [records[key] for key in op["targets"]
                   if records[key].node_number in action.absorbed_node_numbers]
        _need(bool(targets), "UXML_PREVIEW_ABSORBED_RECORD_MISSING")
        for record in targets:
            if kind == "SAFE_DROP_PIPE_GEOMETRY":
                changes.append({"recordKey": record.key, "field": "Source record",
                                "before": "Present", "after": "Removed"})
            else:
                before = _source_text(record, "NodeNumber")
                after = str(action.owner_node_number)
                if before != after:
                    changes.append({"recordKey": record.key, "field": "NodeNumber",
                                    "before": before, "after": after})
    elif kind == "REMOVE_FALSE_RIGID":
        _need(len(op["targets"]) == 1, "UXML_PREVIEW_RIGID_TARGET_AMBIGUOUS")
        record = records[op["targets"][0]]
        before = _source_text(record, "Rigid")
        if before != "0":
            changes.append({"recordKey": record.key, "field": "Rigid",
                            "before": before, "after": "0"})
    elif kind == "CLOSE_PORT_CONNECTION":
        params = op["params"]
        _need(len(params) == 1 and isinstance(params[0], dict),
              "UXML_PREVIEW_PORT_WITNESS_MISSING")
        request = params[0]
        _need(all(key in request for key in ("movePortKey", "targetPortKey",
                                              "moveKeys", "delta", "aliases")),
              "UXML_PREVIEW_PORT_FIELDS_MISSING")
        moving = records[request["movePortKey"]]
        target = records[request["targetPortKey"]]
        delta = request["delta"]
        _need(moving.position is not None and target.position is not None and
              isinstance(delta, list) and len(delta) == 3 and
              isinstance(request["moveKeys"], list) and
              isinstance(request["aliases"], dict),
              "UXML_PREVIEW_PORT_POSITION_INVALID")
        for key in request["moveKeys"]:
            _need(key in records and key in op["targets"],
                  "UXML_PREVIEW_MOVE_KEY_NOT_IN_OP")
            record = records[key]
            _need(record.position is not None, "UXML_PREVIEW_MOVE_POSITION_MISSING")
            before = _source_text(record, "Position")
            _need(before is not None, "UXML_PREVIEW_ORIGINAL_POSITION_MISSING")
            xyz = record.position.as_list()
            if not any(abs(value) > 1e-9 for value in delta):
                after = before
            elif record.position.distance_to(moving.position) <= 1e-6:
                after = _source_text(target, "Position")
            else:
                after = " ".join(format(value + amount, ".15g")
                                 for value, amount in zip(xyz, delta))
            _need(after is not None, "UXML_PREVIEW_TARGET_POSITION_MISSING")
            if before != after:
                changes.append({"recordKey": key, "field": "Position",
                                "before": before, "after": after})
            if key in request["aliases"]:
                number_before = _source_text(record, "NodeNumber")
                number_after = str(request["aliases"][key])
                if number_before != number_after:
                    changes.append({"recordKey": key, "field": "NodeNumber",
                                    "before": number_before, "after": number_after})
    else:
        raise OperationsPreviewError("UXML_PREVIEW_UNSUPPORTED_AUTO_KIND:" + kind)
    _need(bool(changes), "UXML_PREVIEW_OPERATION_WITHOUT_CHANGED_FIELD:" + op["opId"])
    return changes


def build_operation_preview(uxml: dict, *,
                            source_name: str = "<memory>",
                            config: ResolverConfig | None = None) -> dict:
    """Read-only; one preview row for each actual export_edit_ops/v1 op.

    No XML clone is modified; no transaction is started or outputs written.
    Does not broaden the source's Auto-fix selection policy.
    """
    config = config or ResolverConfig()
    payload = export_edit_ops(uxml, source_name=source_name, config=config)
    _need(payload.get("schema") == "uxml-edit-ops/v1",
          "UXML_PREVIEW_OP_SCHEMA_MISMATCH")
    resolved = resolve_from_uxml(uxml, config, source_name=source_name)
    records = {record.key: record for branch in resolved.document.branches
               for record in branch.nodes}
    actions = {action.action_id: action for action in resolved.fix_actions}
    ids_by_key: dict[str, set[str]] = {}
    refs_by_key: dict[str, dict] = {}
    for collection in ("components", "ports"):
        for item in uxml.get(collection, []):
            refs = item.get("sourceRefs", [])
            for ref in refs:
                key = ref["recordKey"]
                ids_by_key.setdefault(key, set()).add(item["id"])
                if collection == "components":
                    _need(key not in refs_by_key, "UXML_PREVIEW_AMBIGUOUS_SOURCE_REF")
                    refs_by_key[key] = ref

    rows, edited_keys = [], set()
    for op in payload["ops"]:
        _need(op["kind"] in NAMES, "UXML_PREVIEW_REVIEW_OPERATION_REFUSED")
        action = actions.get(op["sourceActionId"])
        _need(action is not None and
              action.disposition == op["kind"] and
              action.status == "PROPOSED" and not action.blockers and
              action.confidence >= TransactionPolicy().minimum_confidence,
              "UXML_PREVIEW_POLICY_WITNESS_MISMATCH")
        _need(all(key in records and key in refs_by_key for key in op["targets"]),
              "UXML_PREVIEW_MISSING_SOURCE_REF")
        changes = _preview_fields(op, action, records)
        edited_keys.update(change["recordKey"] for change in changes)
        rows.append({
            "opId": op["opId"], "kind": op["kind"], "kindName": NAMES[op["kind"]],
            "sourceActionId": op["sourceActionId"],
            "uxmlIds": sorted(set().union(*(ids_by_key.get(key, set())
                                           for key in op["targets"]))),
            "sourceRecords": [
                {"format": refs_by_key[key]["format"], "recordKey": key,
                 "changed": key in {change["recordKey"] for change in changes}}
                for key in op["targets"]
            ],
            "changes": changes,
            "policyReason": "PROPOSED; no action blockers; confidence " +
                            format(action.confidence, ".3g") +
                            " >= 0.95; S2 sourceRefs/loss-contract checked. " +
                            "Execution still requires native validation.",
        })
    by_kind = dict(sorted(Counter(row["kind"] for row in rows).items()))
    _need(len(edited_keys) <= len(records), "UXML_PREVIEW_RECORD_COUNT_INVALID")
    return {
        "schema": SCHEMA,
        "sourceSha256": payload["fileSha256"],
        "summary": {
            "totalOps": len(payload["ops"]),
            "byKind": by_kind,
            "sourceRecordCount": len(records),
            "untouchedRecordCount": len(records) - len(edited_keys),
        },
        "ops": rows,
    }
