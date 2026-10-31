"""UXML-S2 PSI116 edit ops and source-qualified patch route.

The XCU-owned UXML has immutable original text and exact sourceRefs. Operations
carry authority, never replacement XML. After strict preflight, the ORIGINAL
PSI116 is mutated by transaction.apply_topofix_transaction() and its existing
validation; there is no XML writer assembled from UXML objects here.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping
import xml.etree.ElementTree as ET

from .models import FixAction, ResolutionResult, ResolverConfig
from .resolver import resolve_psi116
from .transaction import (
    MUTATING_DISPOSITIONS, TransactionPolicy, TopoFixTransactionResult,
    _build_locator_index, _finding_node_keys, _parse_clone, _selected_actions,
    apply_topofix_transaction,
)
from .uxml_adapter import resolve_from_uxml
from .uxml_compare import _diff

EDIT_OP_SCHEMA = "uxml-edit-ops/v1"
EDIT_OP_FIELDS = frozenset({"opId", "kind", "sourceActionId", "fileSha256", "targets", "params"})
PAYLOAD_FIELDS = frozenset({"schema", "sourceFormat", "fileSha256", "policy", "ops"})
POLICY_FIELDS = frozenset(asdict(TransactionPolicy(apply_all_safe=True)))
FIELD_TOUCHES = {
    "ALIAS_COINCIDENT_NODE": frozenset({"NodeNumber"}),
    "CONTRACT_PRESERVE_OWNER": frozenset({"NodeNumber"}),
    "SAFE_DROP_PIPE_GEOMETRY": frozenset({"*"}),
    "REMOVE_FALSE_RIGID": frozenset({"Rigid"}),
    "CLOSE_CONFIRMED_PIPE_JOINT": frozenset({"NodeNumber", "Position"}),
    "CLOSE_PORT_CONNECTION": frozenset({"NodeNumber", "Position"}),
    "CLOSE_CONFIRMED_PORT_CONNECTION": frozenset({"NodeNumber", "Position"}),
}


class UxmlPatchError(ValueError):
    """Named, fail-closed refusal before output or original-source modification."""


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise UxmlPatchError(reason)


def _source_sha(uxml: Mapping[str, Any]) -> str:
    sources = uxml.get("sources")
    _require(isinstance(sources, list) and len(sources) == 1 and
             isinstance(sources[0], dict) and sources[0].get("format") == "PSI116",
             "UXML_PSI116_SOURCE_REQUIRED")
    source_sha = sources[0].get("hash")
    _require(isinstance(source_sha, str) and len(source_sha) == 64 and
             all(letter in "0123456789abcdef" for letter in source_sha),
             "UXML_FILE_SHA256_INVALID")
    return source_sha



def _enforce_today_auto_policy(minimum_confidence: object,
                               require_no_blocking_plan_actions: object) -> None:
    """Current native Auto-fix guard is not an ops-envelope option."""
    native = TransactionPolicy()
    _require(type(minimum_confidence) in (int, float) and
             minimum_confidence == native.minimum_confidence,
             "UXML_POLICY_WIDENING_REFUSED:minimum_confidence")
    _require(require_no_blocking_plan_actions is True and
             native.require_no_blocking_plan_actions is True,
             "UXML_POLICY_WIDENING_REFUSED:require_no_blocking_plan_actions")

def _policy_from_json(value: object) -> TransactionPolicy:
    _require(isinstance(value, dict) and set(value) == POLICY_FIELDS,
             "UXML_EDIT_POLICY_SCHEMA_INVALID")
    _require(value["joint_repairs"] == [] and value["short_element_requests"] == [],
             "UXML_MANUAL_REPAIR_NOT_AUTHORIZED")
    _require(type(value["apply_all_safe"]) is bool and
             type(value["require_no_blocking_plan_actions"]) is bool and
             type(value["minimum_confidence"]) in (float, int) and
             isinstance(value["selected_action_ids"], list) and
             all(isinstance(a, str) for a in value["selected_action_ids"]),
             "UXML_EDIT_POLICY_FIELDS_INVALID")
    _enforce_today_auto_policy(value["minimum_confidence"],
                               value["require_no_blocking_plan_actions"])
    # A run never pulls in newly planned actions that were absent from the ops:
    # selected exact action IDs are mandatory, even when exporting all safe.
    _require(value["apply_all_safe"] is False, "UXML_EDIT_POLICY_EXPLICIT_IDS_REQUIRED")
    _require(len(value["selected_action_ids"]) == len(set(value["selected_action_ids"])),
             "UXML_EDIT_POLICY_DUPLICATE_ACTION")
    policy = TransactionPolicy(
        selected_action_ids=tuple(value["selected_action_ids"]),
        minimum_confidence=value["minimum_confidence"],
        apply_all_safe=False,
        require_no_blocking_plan_actions=value["require_no_blocking_plan_actions"],
    )
    if policy.selected_action_ids:
        policy.validate()
    return policy


def _source_refs_by_key(uxml: Mapping[str, Any], sha: str) -> dict[str, dict]:
    components = uxml.get("components")
    _require(isinstance(components, list), "UXML_COMPONENTS_REQUIRED")
    found: dict[str, dict] = {}
    for component in components:
        _require(isinstance(component, dict), "UXML_COMPONENT_INVALID")
        refs = component.get("sourceRefs")
        _require(isinstance(refs, list) and len(refs) == 1 and
                 isinstance(refs[0], dict), "UXML_SOURCE_REF_INVALID")
        ref = refs[0]
        _require(ref.get("format") == "PSI116" and ref.get("fileSha256") == sha,
                 "UXML_SOURCE_REF_SHA_MISMATCH")
        key = ref.get("recordKey")
        _require(isinstance(key, str) and key, "UXML_SOURCE_REF_KEY_MISSING")
        _require(key not in found, "UXML_TARGET_RECORD_AMBIGUOUS:" + key)
        found[key] = ref
    return found


def _params_keys(params: list[dict]) -> set[str]:
    """Existing action proposal's explicit, exact source-record identities."""
    keys: set[str] = set()
    for change in params:
        if not isinstance(change, dict):
            raise UxmlPatchError("UXML_PROPOSED_CHANGE_INVALID")
        for field in ("moveKey", "targetKey", "movePortKey", "targetPortKey"):
            if field in change:
                _require(isinstance(change[field], str),
                         "UXML_PROPOSED_SOURCE_KEY_INVALID:" + field)
                keys.add(change[field])
        for field in ("moveKeys",):
            if field in change:
                _require(isinstance(change[field], list) and
                         all(isinstance(key, str) for key in change[field]),
                         "UXML_PROPOSED_SOURCE_KEYS_INVALID:" + field)
                keys.update(change[field])
        if "aliases" in change:
            _require(isinstance(change["aliases"], dict),
                     "UXML_PROPOSED_ALIASES_INVALID")
            keys.update(change["aliases"])
    return keys


def _action_targets(result: ResolutionResult, action: FixAction) -> list[str]:
    keys = set(_finding_node_keys(result, action))
    keys.update(_params_keys([dict(change) for change in action.proposed_changes]))
    _require(bool(keys), "UXML_ACTION_WITHOUT_SOURCE_REFS:" + action.action_id)
    return sorted(keys)


def _write_targets(result: ResolutionResult, action: FixAction) -> set[str]:
    keys = set(_finding_node_keys(result, action))
    records = {record.key: record for branch in result.document.branches
               for record in branch.nodes}
    if action.disposition in {"ALIAS_COINCIDENT_NODE", "CONTRACT_PRESERVE_OWNER",
                              "SAFE_DROP_PIPE_GEOMETRY"}:
        return {key for key in keys if key in records and
                records[key].node_number in action.absorbed_node_numbers}
    if action.disposition == "REMOVE_FALSE_RIGID":
        return keys
    params = [dict(change) for change in action.proposed_changes]
    if action.disposition == "CLOSE_CONFIRMED_PIPE_JOINT":
        return {params[0]["moveKey"]}
    if action.disposition in {"CLOSE_PORT_CONNECTION", "CLOSE_CONFIRMED_PORT_CONNECTION"}:
        return set(params[0]["moveKeys"])
    raise UxmlPatchError("UXML_UNSUPPORTED_MUTATING_KIND:" + action.disposition)


def _source_record_paths(source_text: str, result: ResolutionResult) -> dict[str, str]:
    """Walk the ORIGINAL tree to map XCU lossContract paths to exact sourceRefs.

    This is a read-only lookup, not a converter and not a source serializer.
    """
    root = ET.fromstring(source_text)
    record_paths: dict[str, str] = {}
    branch_count = 0
    for branch in root.iter():
        if branch.tag.rsplit("}", 1)[-1] != "Branch":
            continue
        nodes = [node for node in branch if node.tag.rsplit("}", 1)[-1] == "Node"]
        _require(branch_count < len(result.document.branches),
                 "UXML_ORIGINAL_BRANCH_COUNT_DRIFT")
        records = result.document.branches[branch_count].nodes
        _require(len(nodes) == len(records), "UXML_ORIGINAL_RECORD_COUNT_DRIFT")
        # For a path prefix, use exact raw-child sibling indexes (XCU mapper
        # uses XML element indexes, not filtered Node-only source indexes).
        branch_count += 1
    _require(branch_count == len(result.document.branches),
             "UXML_ORIGINAL_BRANCH_COUNT_DRIFT")

    branch_index = 0
    def walk(element: ET.Element, path: str) -> None:
        nonlocal branch_index
        if element.tag.rsplit("}", 1)[-1] == "Branch":
            current_branch = branch_index
            branch_index += 1
            sequence = 0
            for child_idx, child in enumerate(element):
                if child.tag.rsplit("}", 1)[-1] == "Node":
                    key = result.document.branches[current_branch].nodes[sequence].key
                    record_paths[key] = path + "/Node[" + str(child_idx) + "]"
                    sequence += 1
        for child_idx, child in enumerate(element):
            name = child.tag.rsplit("}", 1)[-1] if isinstance(child.tag, str) else ""
            if name:
                walk(child, path + "/" + name + "[" + str(child_idx) + "]")
    walk(root, "/" + root.tag.rsplit("}", 1)[-1] + "[0]")
    return record_paths


def _loss_veto(uxml: Mapping[str, Any], result: ResolutionResult,
               actions: list[FixAction], sha: str) -> None:
    losses = uxml.get("lossContract")
    _require(isinstance(losses, list), "UXML_LOSS_CONTRACT_MISSING")
    if not actions:
        return
    record_paths = _source_record_paths(result.document.source_text, result)
    records = {record.key: record for branch in result.document.branches
               for record in branch.nodes}
    for action in actions:
        writes = _write_targets(result, action)
        _require(bool(writes), "UXML_ACTION_WRITE_TARGET_MISSING:" + action.action_id)
        for key in writes:
            _require(key in records, "UXML_WRITE_TARGET_NOT_FOUND:" + key)
            _require(records[key].connection_type != "CLOS",
                     "UXML_CLOS_WRITE_HELD:" + key)
            node_path = record_paths.get(key)
            _require(node_path is not None, "UXML_LOSS_TARGET_PATH_MISSING:" + key)
            for loss in losses:
                _require(isinstance(loss, dict) and
                         isinstance(loss.get("details"), dict) and
                         isinstance(loss["details"].get("sourcePath"), str),
                         "UXML_LOSS_CONTRACT_INVALID")
                path = loss["details"]["sourcePath"]
                if not (path == node_path or path.startswith(node_path + "/")):
                    continue
                if "*" in FIELD_TOUCHES[action.disposition]:
                    raise UxmlPatchError("UXML_LOSS_CONTRACT_FIELD_TOUCH:" + key + ":" + path)
                for field in FIELD_TOUCHES[action.disposition]:
                    if path.startswith(node_path + "/" + field + "["):
                        raise UxmlPatchError("UXML_LOSS_CONTRACT_FIELD_TOUCH:" + key + ":" + path)


def export_edit_ops(
    uxml: dict, *, policy: TransactionPolicy | None = None,
    source_name: str = "<memory>", config: ResolverConfig | None = None,
) -> dict[str, object]:
    """One operation for each selected, currently proposed mutating action."""
    config = config or ResolverConfig()
    requested = policy if policy is not None else TransactionPolicy(apply_all_safe=True)
    _require(isinstance(requested, TransactionPolicy),
             "UXML_EDIT_POLICY_TYPE_INVALID")
    _enforce_today_auto_policy(requested.minimum_confidence,
                               requested.require_no_blocking_plan_actions)
    _require(not requested.joint_repairs and not requested.short_element_requests,
             "UXML_MANUAL_REPAIR_NOT_AUTHORIZED")
    result = resolve_from_uxml(uxml, config, source_name=source_name)
    sha = _source_sha(uxml)
    candidates = _selected_actions(result, requested)
    actions = [a for a in candidates if a.disposition in MUTATING_DISPOSITIONS]
    _require(all(a.status == "PROPOSED" and not a.blockers and
                 a.confidence >= requested.minimum_confidence for a in actions),
             "UXML_ACTION_OUTSIDE_CURRENT_AUTO_POLICY")
    _require(all(a.disposition not in
                 {"CLOSE_CONFIRMED_PIPE_JOINT", "CLOSE_CONFIRMED_PORT_CONNECTION"}
                 for a in actions), "UXML_MANUAL_CONFIRMATION_NOT_AUTHORIZED")
    refs = _source_refs_by_key(uxml, sha)
    operations = []
    for action in actions:
        targets = _action_targets(result, action)
        for key in targets:
            _require(key in refs, "UXML_TARGET_RECORD_NOT_FOUND:" + key)
        operations.append({
            "opId": "UXML-OP-" + action.action_id,
            "kind": action.disposition,
            "sourceActionId": action.action_id,
            "fileSha256": sha,
            "targets": targets,
            "params": [dict(change) for change in action.proposed_changes],
        })
    # Even at export time, refuse attempts to mutate raw-only fields.
    _loss_veto(uxml, result, actions, sha)
    exact_policy = TransactionPolicy(
        selected_action_ids=tuple(a.action_id for a in actions),
        minimum_confidence=requested.minimum_confidence,
        require_no_blocking_plan_actions=requested.require_no_blocking_plan_actions,
    )
    # Canonical JSON shape (tuple fields become arrays) before any Python API
    # user or CLI consumes the envelope, matching read-back from JSON bytes.
    policy_json = json.loads(json.dumps(asdict(exact_policy)))
    return {"schema": EDIT_OP_SCHEMA, "sourceFormat": "PSI116",
            "fileSha256": sha, "policy": policy_json,
            "ops": operations}


def _validate_ops(uxml: dict, payload: Mapping[str, Any],
                  result: ResolutionResult) -> TransactionPolicy:
    _require(isinstance(payload, dict) and set(payload) == PAYLOAD_FIELDS and
             payload.get("schema") == EDIT_OP_SCHEMA and
             payload.get("sourceFormat") == "PSI116",
             "UXML_EDIT_OPS_SCHEMA_INVALID")
    sha = _source_sha(uxml)
    _require(payload.get("fileSha256") == sha,
             "UXML_FILE_SHA256_MISMATCH")
    policy = _policy_from_json(payload["policy"])
    supplied = payload.get("ops")
    _require(isinstance(supplied, list), "UXML_EDIT_OPS_LIST_REQUIRED")
    refs = _source_refs_by_key(uxml, sha)
    by_id = {a.action_id: a for a in result.fix_actions}
    selected = []
    observed_ids = []
    for op in supplied:
        _require(isinstance(op, dict) and set(op) == EDIT_OP_FIELDS,
                 "UXML_EDIT_OP_SCHEMA_INVALID")
        identifier = op.get("sourceActionId")
        _require(isinstance(identifier, str) and identifier in by_id,
                 "UXML_SOURCE_ACTION_NOT_FOUND:" + str(identifier))
        _require(op.get("opId") == "UXML-OP-" + identifier,
                 "UXML_OP_ID_MISMATCH:" + identifier)
        _require(op.get("fileSha256") == sha, "UXML_FILE_SHA256_MISMATCH")
        action = by_id[identifier]
        _require(action.disposition in MUTATING_DISPOSITIONS and
                 op.get("kind") == action.disposition and
                 action.status == "PROPOSED" and not action.blockers and
                 action.confidence >= policy.minimum_confidence,
                 "UXML_ACTION_OUTSIDE_CURRENT_AUTO_POLICY:" + identifier)
        _require(action.disposition not in
                 {"CLOSE_CONFIRMED_PIPE_JOINT", "CLOSE_CONFIRMED_PORT_CONNECTION"},
                 "UXML_MANUAL_CONFIRMATION_NOT_AUTHORIZED")
        targets = op.get("targets")
        _require(isinstance(targets, list) and
                 all(isinstance(key, str) for key in targets) and
                 len(set(targets)) == len(targets),
                 "UXML_TARGETS_INVALID:" + identifier)
        for key in targets:
            _require(key in refs, "UXML_TARGET_RECORD_NOT_FOUND:" + key)
        _require(targets == _action_targets(result, action),
                 "UXML_TARGETS_DIFFER_FROM_AUTHORITY:" + identifier)
        _require(op.get("params") == [dict(change) for change in action.proposed_changes],
                 "UXML_PARAMS_DIFFER_FROM_PROPOSED_CHANGES:" + identifier)
        observed_ids.append(identifier)
        selected.append(action)
    _require(len(set(observed_ids)) == len(observed_ids),
             "UXML_DUPLICATE_SOURCE_ACTION")
    _require(tuple(sorted(observed_ids)) == tuple(sorted(policy.selected_action_ids)),
             "UXML_SELECTED_OPS_SET_MISMATCH")
    _loss_veto(uxml, result, selected, sha)
    return policy


def apply_edit_ops(
    original: str | Path, uxml: dict, payload: dict,
    *, config: ResolverConfig | None = None,
) -> TopoFixTransactionResult | None:
    """Patch the original PSI116 source using only existing TopoFix operations.

    Caller must write fixed_xml to a NEW output path. No original write occurs.
    Empty op list returns None (no mutation/validation to run).
    """
    config = config or ResolverConfig()
    original_path = Path(original)
    data = original_path.read_bytes()
    sha = sha256(data).hexdigest()
    _require(payload.get("fileSha256") == sha and _source_sha(uxml) == sha,
             "UXML_FILE_SHA256_MISMATCH")
    # Explicit duplicate-sourceRef reason before the adapter's broader
    # source-index validation obscures the ambiguous target identity.
    _source_refs_by_key(uxml, sha)
    result = resolve_from_uxml(uxml, config, source_name=str(original_path))
    _require(result.document.source_text.encode("utf-8") == data,
             "UXML_ORIGINAL_BYTES_MISMATCH")
    policy = _validate_ops(uxml, payload, result)
    if not payload["ops"]:
        return None

    # Independently parse ORIGINAL bytes, rather than looking up a key in
    # UXML-derived locators and comparing that key back to itself.
    original_result = resolve_psi116(original_path, config)
    original_locators = _build_locator_index(
        _parse_clone(original_result.document.source_text), original_result)
    source_refs = _source_refs_by_key(uxml, sha)
    for op in payload["ops"]:
        for key in op["targets"]:
            locator = original_locators.get(key)
            _require(locator is not None,
                     "UXML_ORIGINAL_RECORD_KEY_MISMATCH:" + key)
            record, source_ref = locator.record, source_refs[key]
            _require(source_ref.get("branchName") == record.branch_name and
                     (source_ref.get("nodeNumber") is None and record.node_number is None
                      or str(source_ref.get("nodeNumber")) == str(record.node_number)) and
                     (source_ref.get("endpoint") is None and record.endpoint is None
                      or str(source_ref.get("endpoint")) == str(record.endpoint)),
                     "UXML_ORIGINAL_SOURCE_REF_MISMATCH:" + key)

    # Do not reinterpret any FixAction, reconstruct any normalized XML, or
    # bypass native validation. Existing transaction.py has sole write authority.
    return apply_topofix_transaction(result, policy=policy, config=config)


def compare_patch_to_direct(original: str | Path, uxml: dict,
                            payload: dict, *, config: ResolverConfig | None = None
                            ) -> tuple[TopoFixTransactionResult | None, list[str]]:
    """Exact byte output + exact validation report benchmark, named diffs."""
    config = config or ResolverConfig()
    patched = apply_edit_ops(original, uxml, payload, config=config)
    if patched is None:
        return None, []
    policy = _policy_from_json(payload["policy"])
    direct = apply_topofix_transaction(resolve_psi116(Path(original), config),
                                      policy=policy, config=config)
    differences: list[str] = []
    if patched.fixed_xml != direct.fixed_xml:
        differences.append("/fixedXml: PATCH_BYTES_DIFFER_FROM_DIRECT")
        left = patched.fixed_xml or ""
        right = direct.fixed_xml or ""
        for offset, pair in enumerate(zip(left.encode("utf-8"), right.encode("utf-8"))):
            if pair[0] != pair[1]:
                differences.append("/fixedXml/byte/" + str(offset) +
                                   ": patch=" + str(pair[0]) +
                                   " direct=" + str(pair[1]))
                break
        if len(left.encode("utf-8")) != len(right.encode("utf-8")):
            differences.append("/fixedXml/length: patch=" + str(len(left.encode("utf-8"))) +
                               " direct=" + str(len(right.encode("utf-8"))))
    _diff("/validation", direct.validation_payload(), patched.validation_payload(), differences)
    return patched, differences
