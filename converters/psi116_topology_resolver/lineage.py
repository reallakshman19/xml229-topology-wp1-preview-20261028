"""PSI116 L2: exact original->reviewed TopoFix source identity handoff.

Only a pre-Final topology sidecar. Does not approve mass, reuse a Worker basis,
or authorize native CII. All retained original Node occurrences remain
individually identified, even if they share a renumbered connected node.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
from hashlib import sha256
import json
import xml.etree.ElementTree as ET

from .models import ResolverConfig
from .resolver import resolve_psi116
from .transaction import TransactionPolicy, TopoFixTransactionResult, apply_topofix_transaction

SCHEMA = "psi116-topofix-source-lineage/v1"
QUALIFIED_SCHEMA = "psi116-topofix-prefinal-handoff/v1"


class TopoFixLineageError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(ok: bool, code: str) -> None:
    if not ok:
        raise TopoFixLineageError(code)


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _child(node: ET.Element, tag: str) -> ET.Element | None:
    return next((c for c in node if _local_name(c) == tag), None)


def _branches(root: ET.Element) -> list[ET.Element]:
    return [n for n in root.iter() if _local_name(n) == "Branch"]


def _nodes(branch: ET.Element) -> list[ET.Element]:
    return [n for n in branch if _local_name(n) == "Node"]


def _canonical(element: ET.Element) -> object:
    """All XML fields, attributes, child order and nonblank text, not just geometry."""
    return [_local_name(element), sorted(element.attrib.items()),
            (element.text or "").strip(),
            [_canonical(n) for n in element if isinstance(n.tag, str)]]


def _digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                             sort_keys=True).encode("utf-8")).hexdigest()


def _node_digest(node: ET.Element) -> str:
    return _digest(_canonical(node))


def _xml_root(value: str) -> ET.Element:
    try:
        root = ET.fromstring(value)
    except ET.ParseError:
        raise TopoFixLineageError("TOPOFIX_LINEAGE_XML_MALFORMED") from None
    require(_local_name(root) == "PipeStressExport", "TOPOFIX_LINEAGE_SOURCE_KIND")
    return root


def _operation_index(transaction: TopoFixTransactionResult):
    indexed = {}
    for operation in transaction.operations:
        if operation.operation == "NO_XML_CHANGE":
            require(not operation.source_node_key,
                    "TOPOFIX_LINEAGE_OPERATION_KEY_DRIFT")
            continue
        require(operation.operation in {
            "ALIAS_NODE_NUMBER", "SET_RIGID_ZERO",
            "REMOVE_PLAIN_PIPE_NODE_RECORD"
        } and operation.source_node_key and
            operation.source_node_key not in indexed,
            "TOPOFIX_LINEAGE_OPERATION_KEY_DRIFT")
        indexed[operation.source_node_key] = operation
    return indexed


def _mutated_source_node(node: ET.Element, operation) -> ET.Element:
    expected = copy.deepcopy(node)
    if operation is None:
        return expected
    if operation.operation == "ALIAS_NODE_NUMBER":
        field = _child(expected, "NodeNumber")
        require(field is not None and (field.text or "") == str(operation.before),
                "TOPOFIX_LINEAGE_OPERATION_BEFORE_DRIFT")
        field.text = str(operation.after)
    elif operation.operation == "SET_RIGID_ZERO":
        field = _child(expected, "Rigid")
        require((field.text if field is not None else None) == operation.before and
                operation.after == "0", "TOPOFIX_LINEAGE_OPERATION_BEFORE_DRIFT")
        if field is None:
            namespace = expected.tag.rsplit("}", 1)[0] + "}" if "}" in expected.tag else ""
            field = ET.Element(namespace + "Rigid")
            expected.insert(0, field)
        field.text = "0"
    else:
        raise TopoFixLineageError("TOPOFIX_LINEAGE_OPERATION_UNSUPPORTED")
    return expected


def build_topofix_source_lineage(transaction: TopoFixTransactionResult) -> dict:
    """Derive complete source occurrence mapping from committed transaction."""
    require(transaction.committed and transaction.fixed_xml is not None and
            transaction.after_result is not None and
            all(c.passed for c in transaction.checks if c.blocking),
            "TOPOFIX_LINEAGE_UNCOMMITTED")
    original = _branches(_xml_root(transaction.source_result.document.source_text))
    fixed = _branches(_xml_root(transaction.fixed_xml))
    require(len(original) == len(fixed) ==
            len(transaction.source_result.document.branches),
            "TOPOFIX_LINEAGE_BRANCH_DRIFT")
    operation_index = _operation_index(transaction)
    known_keys = set()
    rows = []
    removed = 0
    changed = 0
    for bi, (source_branch, fixed_branch, record_branch) in enumerate(
            zip(original, fixed, transaction.source_result.document.branches)):
        before = _nodes(source_branch)
        after = _nodes(fixed_branch)
        require(len(before) == len(record_branch.nodes),
                "TOPOFIX_LINEAGE_SOURCE_CENSUS_DRIFT")
        position = 0
        for ordinal, (node, record) in enumerate(zip(before, record_branch.nodes)):
            require(record.source_index == ordinal,
                    "TOPOFIX_LINEAGE_ORDINAL_DRIFT")
            key = record.key
            known_keys.add(key)
            op = operation_index.get(key)
            removed_here = op is not None and op.operation == "REMOVE_PLAIN_PIPE_NODE_RECORD"
            if removed_here:
                require(record.semantic_type == "PIPE",
                        "TOPOFIX_LINEAGE_UNSAFE_REMOVAL")
                status = "REMOVED_PLAIN_PIPE"
                fixed_ordinal = None
                fixed_digest = None
                removed += 1
            else:
                require(position < len(after),
                        "TOPOFIX_LINEAGE_FINAL_CENSUS_DRIFT")
                expected = _mutated_source_node(node, op)
                require(_canonical(expected) == _canonical(after[position]),
                        "TOPOFIX_LINEAGE_UNDECLARED_XML_CHANGE")
                status = ("RENUMBERED_CONNECTION" if op is not None and
                          op.operation == "ALIAS_NODE_NUMBER" else
                          "RIGID_RECLASSIFIED" if op is not None else "RETAINED")
                fixed_ordinal = position
                fixed_digest = _node_digest(after[position])
                position += 1
                changed += op is not None
            rows.append({
                "branchOccurrenceIndex": bi,
                "sourceNodeOrdinal": ordinal,
                "sourceNodeKey": key,
                "sourceNodeSha256": _node_digest(node),
                "status": status,
                "fixedNodeOrdinal": fixed_ordinal,
                "fixedNodeSha256": fixed_digest,
                "operationId": op.operation_id if op is not None else None,
            })
        require(position == len(after), "TOPOFIX_LINEAGE_FINAL_CENSUS_DRIFT")
    require(set(operation_index) <= known_keys,
            "TOPOFIX_LINEAGE_UNKNOWN_OPERATION_SOURCE")
    transaction_receipt = transaction.transaction_payload()
    return {
        "schema": SCHEMA,
        "sourceXmlSha256": transaction.source_result.document.source_sha256,
        "fixedXmlSha256": sha256(transaction.fixed_xml.encode("utf-8")).hexdigest(),
        "transactionSha256": _digest(transaction_receipt),
        "reviewedActionIds": list(transaction_receipt["selectedActions"]),
        "counts": {"sourceNodeOccurrences": len(rows),
                   "fixedNodeOccurrences": len(rows) - removed,
                   "retainedNodeOccurrences": len(rows) - removed,
                   "removedPlainPipeOccurrences": removed,
                   "changedRetainedOccurrences": changed},
        "sourceOccurrenceMap": rows,
        "sourceXmlMutated": False,
        "state": "PRE_FINAL_ONLY",
        "requiresFreshWorkerBasis": True,
        "acceptedFinalTransferred": False,
        "nativeCiiReleaseAuthorized": False,
    }


def verify_topofix_pre_final(
    original_xml: str,
    fixed_xml: str,
    transaction_receipt: dict,
    validation_receipt: dict,
    lineage_receipt: dict,
    *,
    reviewed_action_ids: tuple[str, ...] | list[str],
    existing_final_intent_sha256: str | None = None,
    existing_worker_basis_id: str | None = None,
) -> dict:
    """Independent source replay + action review; only qualifies a *new* basis.

    Must not be called as a route around existing Final/Native CII gates.
    """
    require(not existing_final_intent_sha256 and not existing_worker_basis_id,
            "TOPOFIX_REQUIRES_FRESH_FINAL_BASIS")
    require(isinstance(transaction_receipt, dict) and
            isinstance(validation_receipt, dict) and
            isinstance(lineage_receipt, dict),
            "TOPOFIX_LINEAGE_RECEIPT_MISSING")
    require(transaction_receipt.get("committed") is True and
            transaction_receipt.get("atomic") is True and
            transaction_receipt.get("sourceXmlMutated") is False and
            validation_receipt.get("committed") is True,
            "TOPOFIX_LINEAGE_UNCOMMITTED")
    config = transaction_receipt.get("resolverConfig")
    policy = transaction_receipt.get("policy")
    selected = transaction_receipt.get("selectedActions")
    reviewed = list(reviewed_action_ids)
    require(isinstance(config, dict) and isinstance(policy, dict) and
            isinstance(selected, list) and len(selected) > 0 and
            len(set(selected)) == len(selected) and
            len(reviewed) == len(selected) and set(reviewed) == set(selected) and
            policy.get("apply_all_safe") is False and
            isinstance(policy.get("selected_action_ids"), (list, tuple)) and
            len(policy["selected_action_ids"]) == len(selected) and
            len(set(policy["selected_action_ids"])) == len(selected) and
            set(policy["selected_action_ids"]) == set(selected) and
            policy.get("require_no_blocking_plan_actions") is True,
            "TOPOFIX_LINEAGE_REVIEW_REQUIRED")
    try:
        cfg = ResolverConfig(**config)
        cfg.validate()
        p = TransactionPolicy(**policy)
        p.validate()
        baseline = resolve_psi116(
            original_xml, cfg,
            source_name=transaction_receipt.get("source", {}).get("path") or "source.xml")
        reproduction = apply_topofix_transaction(baseline, policy=p, config=cfg)
    except (TypeError, ValueError, KeyError):
        raise TopoFixLineageError("TOPOFIX_LINEAGE_POLICY_INVALID") from None
    require(reproduction.committed, "TOPOFIX_LINEAGE_REPLAY_REJECTED")
    require(reproduction.fixed_xml == fixed_xml, "TOPOFIX_LINEAGE_FIXED_XML_DRIFT")
    require(json.loads(json.dumps(reproduction.transaction_payload())) ==
            json.loads(json.dumps(transaction_receipt)),
            "TOPOFIX_LINEAGE_TRANSACTION_REPLAY_DRIFT")
    require(json.loads(json.dumps(reproduction.validation_payload())) ==
            json.loads(json.dumps(validation_receipt)),
            "TOPOFIX_LINEAGE_VALIDATION_REPLAY_DRIFT")
    derived = build_topofix_source_lineage(reproduction)
    require(derived == lineage_receipt,
            "TOPOFIX_LINEAGE_RECEIPT_DRIFT")
    # This is a *qualification to start a new Worker*, never a mass release.
    return {"schema": QUALIFIED_SCHEMA,
            "originalSourceXmlSha256": derived["sourceXmlSha256"],
            "newSourceXmlSha256": derived["fixedXmlSha256"],
            "transactionSha256": derived["transactionSha256"],
            "sourceNodeOccurrenceCount": derived["counts"]["sourceNodeOccurrences"],
            "fixedNodeOccurrenceCount": derived["counts"]["fixedNodeOccurrences"],
            "reviewedActionIds": reviewed,
            "requiresFreshWorkerBasis": True,
            "acceptedFinalTransferred": False,
            "nativeCiiReleaseAuthorized": False}
