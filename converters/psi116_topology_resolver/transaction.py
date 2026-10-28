from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Iterable, Sequence
import xml.etree.ElementTree as ET

from .models import FixAction, Finding, NodeRecord, ResolutionResult, ResolverConfig
from .resolver import resolve_psi116

SCHEMA_TRANSACTION = "psi116-topofix-transaction/v1"
SCHEMA_VALIDATION = "psi116-topofix-validation/v1"
MUTATING_DISPOSITIONS = frozenset({
    "ALIAS_COINCIDENT_NODE",
    "CONTRACT_PRESERVE_OWNER",
    "SAFE_DROP_PIPE_GEOMETRY",
    "REMOVE_FALSE_RIGID",
})
EVIDENCE_ONLY_DISPOSITIONS = frozenset({"KEEP", "MERGE_CARRIER_WITH_COMPONENT"})


@dataclass(frozen=True)
class TransactionPolicy:
    selected_action_ids: tuple[str, ...] = ()
    apply_all_safe: bool = False
    minimum_confidence: float = 0.95
    require_no_blocking_plan_actions: bool = True

    def validate(self) -> None:
        if not math.isfinite(float(self.minimum_confidence)) or not 0 <= self.minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be between 0 and 1.")
        if self.apply_all_safe and self.selected_action_ids:
            raise ValueError("Use either selected_action_ids or apply_all_safe, not both.")
        if not self.apply_all_safe and not self.selected_action_ids:
            raise ValueError("At least one explicit action ID is required unless apply_all_safe is enabled.")


@dataclass(frozen=True)
class AppliedOperation:
    operation_id: str
    action_id: str
    disposition: str
    operation: str
    branch_name: str
    source_node_key: str = ""
    source_node_number: int | None = None
    retained_node_key: str = ""
    retained_node_number: int | None = None
    before: object = None
    after: object = None
    authority: str = ""
    source_xml_sha256: str = ""


@dataclass(frozen=True)
class ValidationCheck:
    code: str
    passed: bool
    blocking: bool
    message: str
    before: object = None
    after: object = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TopoFixTransactionResult:
    source_result: ResolutionResult
    after_result: ResolutionResult | None
    policy: TransactionPolicy
    selected_actions: tuple[FixAction, ...]
    operations: tuple[AppliedOperation, ...]
    checks: tuple[ValidationCheck, ...]
    reject_reasons: tuple[str, ...]
    fixed_xml: str | None
    resolver_config: ResolverConfig = field(default_factory=ResolverConfig)

    @property
    def committed(self) -> bool:
        return not self.reject_reasons and self.fixed_xml is not None

    def transaction_payload(self) -> dict[str, object]:
        return {
            "schema": SCHEMA_TRANSACTION,
            "source": {
                "path": self.source_result.document.source_path,
                "sha256": self.source_result.document.source_sha256,
                "namespace": self.source_result.document.namespace,
            },
            "policy": asdict(self.policy),
            "resolverConfig": asdict(self.resolver_config),
            "committed": self.committed,
            "atomic": True,
            "sourceXmlMutated": False,
            "fixedXmlEmitted": self.committed,
            "fixedXmlSha256": sha256(self.fixed_xml.encode("utf-8")).hexdigest() if self.fixed_xml else "",
            "summary": {
                "selectedActionCount": len(self.selected_actions),
                "appliedOperationCount": len(self.operations),
                "mutatingOperationCount": sum(op.operation != "NO_XML_CHANGE" for op in self.operations),
                "rejectedCheckCount": sum(not check.passed and check.blocking for check in self.checks),
            },
            "selectedActions": [action.action_id for action in self.selected_actions],
            "operations": [asdict(operation) for operation in self.operations],
            "rejectReasons": list(self.reject_reasons),
        }

    def validation_payload(self) -> dict[str, object]:
        return {
            "schema": SCHEMA_VALIDATION,
            "sourceSha256": self.source_result.document.source_sha256,
            "fixedXmlSha256": sha256(self.fixed_xml.encode("utf-8")).hexdigest() if self.fixed_xml else "",
            "committed": self.committed,
            "summary": {
                "checkCount": len(self.checks),
                "passedCheckCount": sum(check.passed for check in self.checks),
                "blockingFailureCount": sum(not check.passed and check.blocking for check in self.checks),
            },
            "checks": [asdict(check) for check in self.checks],
            "rejectReasons": list(self.reject_reasons),
        }


@dataclass
class _NodeLocator:
    record: NodeRecord
    branch_element: ET.Element
    node_element: ET.Element


def _local_name(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _iter_named(root: ET.Element, name: str) -> Iterable[ET.Element]:
    for element in root.iter():
        if _local_name(element.tag) == name:
            yield element


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _set_child_text(element: ET.Element, name: str, value: object) -> object:
    child = _child(element, name)
    if child is None:
        namespace = element.tag[1:].split("}", 1)[0] if isinstance(element.tag, str) and element.tag.startswith("{") else ""
        child = ET.Element(f"{{{namespace}}}{name}" if namespace else name)
        element.insert(0, child)
        before = None
    else:
        before = child.text
    child.text = str(value)
    return before


def _parse_clone(source_text: str) -> ET.Element:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    return ET.fromstring(source_text, parser=parser)


def _serialize(root: ET.Element, namespace: str) -> str:
    if namespace:
        ET.register_namespace("", namespace)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=True)
    return data.decode("utf-8") + ("" if data.endswith(b"\n") else "\n")


def _build_locator_index(root: ET.Element, result: ResolutionResult) -> dict[str, _NodeLocator]:
    branch_elements = list(_iter_named(root, "Branch"))
    if len(branch_elements) != len(result.document.branches):
        raise ValueError("Mutable XML branch count does not match parsed PSI116 document.")
    locators: dict[str, _NodeLocator] = {}
    for branch_record, branch_element in zip(result.document.branches, branch_elements):
        node_elements = [child for child in branch_element if _local_name(child.tag) == "Node"]
        if len(node_elements) != len(branch_record.nodes):
            raise ValueError(f"Mutable XML node count does not match branch {branch_record.name}.")
        for record, node_element in zip(branch_record.nodes, node_elements):
            locators[record.key] = _NodeLocator(record, branch_element, node_element)
    return locators


def _selected_actions(result: ResolutionResult, policy: TransactionPolicy) -> tuple[FixAction, ...]:
    policy.validate()
    by_id = {action.action_id: action for action in result.fix_actions}
    if policy.apply_all_safe:
        actions = tuple(
            action for action in result.fix_actions
            if action.status == "PROPOSED" and not action.blockers and action.confidence >= policy.minimum_confidence
        )
    else:
        unknown = sorted(set(policy.selected_action_ids) - set(by_id))
        if unknown:
            raise ValueError(f"Unknown topology fix action IDs: {', '.join(unknown)}")
        actions = tuple(by_id[action_id] for action_id in policy.selected_action_ids)
    return tuple(sorted(actions, key=lambda action: action.action_id))


def _finding_node_keys(result: ResolutionResult, action: FixAction) -> tuple[str, ...]:
    by_id = {finding.finding_id: finding for finding in result.findings}
    return tuple(sorted({key for finding_id in action.finding_ids for key in by_id[finding_id].node_keys}))


def _record_sha(record: NodeRecord) -> str:
    """Digest exact XML node semantics, not process-global namespace prefixes.

    ET.register_namespace() affects serializing raw fragments and must never
    silently change a previously reviewed TopoFix operation receipt.
    """
    element = ET.fromstring(record.raw_xml)

    def semantic(node: ET.Element):
        return [node.tag, sorted(node.attrib.items()),
                (node.text or "").strip(),
                [semantic(child) for child in node if isinstance(child.tag, str)]]

    canonical = json.dumps(semantic(element), sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _compatible_number(left: float | None, right: float | None, tolerance: float = 1e-9) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return abs(left - right) <= tolerance


def _can_remove_plain_pipe(record: NodeRecord, owner: NodeRecord, config: ResolverConfig) -> tuple[bool, str]:
    if record.semantic_type != "PIPE":
        return False, "ABSORBED_NODE_NOT_PIPE"
    if record.has_restraint:
        return False, "ABSORBED_PIPE_HAS_RESTRAINT"
    if record.rigid not in {None, 0}:
        return False, "ABSORBED_PIPE_HAS_RIGID_EVIDENCE"
    if record.weight is not None and abs(record.weight) > 1e-12:
        return False, "ABSORBED_PIPE_HAS_WEIGHT"
    if record.node_name:
        return False, "ABSORBED_PIPE_HAS_NODE_NAME"
    if record.position is None or owner.position is None or record.position.distance_to(owner.position) > config.connection_tolerance_mm:
        return False, "ABSORBED_PIPE_NOT_COINCIDENT_WITH_OWNER"
    if not _compatible_number(record.outside_diameter, owner.outside_diameter):
        return False, "ABSORBED_PIPE_DIAMETER_DIFFERS"
    if not _compatible_number(record.wall_thickness, owner.wall_thickness):
        return False, "ABSORBED_PIPE_WALL_DIFFERS"
    return True, "PLAIN_PIPE_WITHOUT_ENGINEERING_SEMANTICS"


def _preflight(result: ResolutionResult, actions: Sequence[FixAction], policy: TransactionPolicy) -> list[str]:
    reasons: list[str] = []
    if policy.require_no_blocking_plan_actions:
        blocked = [action.action_id for action in result.fix_actions if action.status == "BLOCKED" or action.blockers]
        if blocked:
            reasons.append("BLOCKING_PLAN_ACTIONS_PRESENT")
    used_keys: dict[str, str] = {}
    for action in actions:
        if action.status != "PROPOSED":
            reasons.append(f"ACTION_NOT_PROPOSED:{action.action_id}")
        if action.blockers:
            reasons.append(f"ACTION_HAS_BLOCKERS:{action.action_id}")
        if action.confidence < policy.minimum_confidence:
            reasons.append(f"ACTION_CONFIDENCE_BELOW_POLICY:{action.action_id}")
        if action.disposition not in MUTATING_DISPOSITIONS | EVIDENCE_ONLY_DISPOSITIONS:
            reasons.append(f"UNSUPPORTED_DISPOSITION:{action.action_id}:{action.disposition}")
        if action.disposition in MUTATING_DISPOSITIONS:
            for key in _finding_node_keys(result, action):
                prior = used_keys.get(key)
                if prior and prior != action.action_id:
                    reasons.append(f"CONFLICTING_NODE_ACTIONS:{prior}:{action.action_id}:{key}")
                used_keys[key] = action.action_id
    return sorted(set(reasons))


def _owner_locator(result: ResolutionResult, action: FixAction, locators: dict[str, _NodeLocator]) -> _NodeLocator:
    keys = _finding_node_keys(result, action)
    candidates = [locators[key] for key in keys if key in locators and locators[key].record.node_number == action.owner_node_number]
    if not candidates:
        raise ValueError(f"Action {action.action_id} owner Node {action.owner_node_number} is not resolvable.")
    return max(candidates, key=lambda locator: (locator.record.semantic_type != "PIPE", locator.record.endpoint == 0, -locator.record.source_index))


def _absorbed_locators(result: ResolutionResult, action: FixAction, locators: dict[str, _NodeLocator]) -> list[_NodeLocator]:
    numbers = set(action.absorbed_node_numbers)
    keys = set(_finding_node_keys(result, action))
    return [locator for key, locator in locators.items() if key in keys and locator.record.node_number in numbers]


def _apply_alias_or_contract(
    result: ResolutionResult,
    action: FixAction,
    locators: dict[str, _NodeLocator],
    config: ResolverConfig,
    operation_start: int,
) -> list[AppliedOperation]:
    owner = _owner_locator(result, action, locators)
    absorbed = _absorbed_locators(result, action, locators)
    if not absorbed:
        raise ValueError(f"Action {action.action_id} has no resolvable absorbed nodes.")
    operations: list[AppliedOperation] = []
    for locator in sorted(absorbed, key=lambda item: item.record.key):
        record = locator.record
        if record.position is None or owner.record.position is None:
            raise ValueError(f"Action {action.action_id} has a node without position evidence.")
        if record.position.distance_to(owner.record.position) > config.connection_tolerance_mm:
            raise ValueError(f"Action {action.action_id} exceeds the connection tolerance.")
        node_number = _child(locator.node_element, "NodeNumber")
        if node_number is None:
            raise ValueError(f"Action {action.action_id} absorbed node has no NodeNumber element.")
        before = node_number.text
        node_number.text = str(owner.record.node_number)
        operations.append(AppliedOperation(
            operation_id=f"OP-{operation_start + len(operations):06d}",
            action_id=action.action_id,
            disposition=action.disposition,
            operation="ALIAS_NODE_NUMBER",
            branch_name=record.branch_name,
            source_node_key=record.key,
            source_node_number=record.node_number,
            retained_node_key=owner.record.key,
            retained_node_number=owner.record.node_number,
            before=before,
            after=owner.record.node_number,
            authority=action.authority,
            source_xml_sha256=_record_sha(record),
        ))
    return operations


def _apply_safe_drop(
    result: ResolutionResult,
    action: FixAction,
    locators: dict[str, _NodeLocator],
    config: ResolverConfig,
    operation_id: str,
) -> AppliedOperation:
    owner = _owner_locator(result, action, locators)
    absorbed = _absorbed_locators(result, action, locators)
    if len(absorbed) != 1:
        raise ValueError(f"Action {action.action_id} must resolve exactly one disposable pipe node.")
    locator = absorbed[0]
    safe, authority = _can_remove_plain_pipe(locator.record, owner.record, config)
    if not safe:
        raise ValueError(f"Action {action.action_id} cannot remove {locator.record.key}: {authority}")
    locator.branch_element.remove(locator.node_element)
    return AppliedOperation(
        operation_id=operation_id,
        action_id=action.action_id,
        disposition=action.disposition,
        operation="REMOVE_PLAIN_PIPE_NODE_RECORD",
        branch_name=locator.record.branch_name,
        source_node_key=locator.record.key,
        source_node_number=locator.record.node_number,
        retained_node_key=owner.record.key,
        retained_node_number=owner.record.node_number,
        before=locator.record.node_number,
        after=None,
        authority=authority,
        source_xml_sha256=_record_sha(locator.record),
    )


def _apply_remove_false_rigid(
    result: ResolutionResult,
    action: FixAction,
    locators: dict[str, _NodeLocator],
    operation_id: str,
) -> AppliedOperation:
    keys = _finding_node_keys(result, action)
    candidates = [locators[key] for key in keys if key in locators]
    if len(candidates) != 1:
        raise ValueError(f"Action {action.action_id} must resolve exactly one rigid node.")
    locator = candidates[0]
    before = _set_child_text(locator.node_element, "Rigid", 0)
    return AppliedOperation(
        operation_id=operation_id,
        action_id=action.action_id,
        disposition=action.disposition,
        operation="SET_RIGID_ZERO",
        branch_name=locator.record.branch_name,
        source_node_key=locator.record.key,
        source_node_number=locator.record.node_number,
        retained_node_key=locator.record.key,
        retained_node_number=locator.record.node_number,
        before=before,
        after="0",
        authority=action.authority,
        source_xml_sha256=_record_sha(locator.record),
    )


def _snapshot(result: ResolutionResult) -> dict[str, object]:
    document = result.document
    nodes = [node for branch in document.branches for node in branch.nodes]
    special_refs = Counter(
        (occurrence.semantic_type, occurrence.component_ref_no)
        for occurrence in document.occurrences
        if occurrence.semantic_type != "PIPE"
    )
    return {
        "branchCount": len(document.branches),
        "nodeRecordCount": len(nodes),
        "positiveNodeRecordCount": sum(node.positive for node in nodes),
        "restraintCount": sum(node.has_restraint for node in nodes),
        "weightSum": sum(node.weight or 0.0 for node in nodes),
        "specialOccurrenceRefs": sorted((kind, ref, count) for (kind, ref), count in special_refs.items()),
        "blockingFindingCount": sum(finding.blocking for finding in result.findings),
        "blockingFindingCodes": sorted({finding.code for finding in result.findings if finding.blocking}),
    }


def _selected_findings_resolved(before: ResolutionResult, after: ResolutionResult, actions: Sequence[FixAction]) -> tuple[bool, list[str]]:
    after_alias_sets = [set(finding.node_numbers) for finding in after.findings if finding.code == "COINCIDENT_NODE_ALIAS_CANDIDATE"]
    after_rigid_numbers = {number for finding in after.findings if finding.code == "NON_RIGID_COMPONENT_CLASSIFIED_RIGID" for number in finding.node_numbers}
    unresolved: list[str] = []
    for action in actions:
        if action.disposition in {"ALIAS_COINCIDENT_NODE", "CONTRACT_PRESERVE_OWNER", "SAFE_DROP_PIPE_GEOMETRY"}:
            original = set(action.node_numbers)
            if any(original <= candidate or candidate <= original for candidate in after_alias_sets):
                unresolved.append(action.action_id)
        elif action.disposition == "REMOVE_FALSE_RIGID" and set(action.node_numbers) & after_rigid_numbers:
            unresolved.append(action.action_id)
    return not unresolved, unresolved


def _validate_transaction(
    before: ResolutionResult,
    after: ResolutionResult,
    actions: Sequence[FixAction],
    operations: Sequence[AppliedOperation],
) -> tuple[ValidationCheck, ...]:
    before_snapshot = _snapshot(before)
    after_snapshot = _snapshot(after)
    removed = sum(operation.operation == "REMOVE_PLAIN_PIPE_NODE_RECORD" for operation in operations)
    resolved, unresolved_actions = _selected_findings_resolved(before, after, actions)
    before_blocking = set(before_snapshot["blockingFindingCodes"])
    after_blocking = set(after_snapshot["blockingFindingCodes"])
    checks = [
        ValidationCheck("BRANCH_COUNT_PRESERVED", before_snapshot["branchCount"] == after_snapshot["branchCount"], True, "Branch count must remain unchanged.", before_snapshot["branchCount"], after_snapshot["branchCount"]),
        ValidationCheck("SPECIAL_COMPONENT_OCCURRENCES_PRESERVED", before_snapshot["specialOccurrenceRefs"] == after_snapshot["specialOccurrenceRefs"], True, "All non-pipe component occurrence references must remain present.", before_snapshot["specialOccurrenceRefs"], after_snapshot["specialOccurrenceRefs"]),
        ValidationCheck("RESTRAINT_COUNT_PRESERVED", before_snapshot["restraintCount"] == after_snapshot["restraintCount"], True, "Restraint evidence must be preserved.", before_snapshot["restraintCount"], after_snapshot["restraintCount"]),
        ValidationCheck("WEIGHT_SUM_PRESERVED", abs(float(before_snapshot["weightSum"]) - float(after_snapshot["weightSum"])) <= 1e-9, True, "Total source weight must remain unchanged.", before_snapshot["weightSum"], after_snapshot["weightSum"]),
        ValidationCheck("NODE_REMOVAL_ACCOUNTED", int(before_snapshot["nodeRecordCount"]) - removed == int(after_snapshot["nodeRecordCount"]), True, "Node count change must equal explicit removal operations.", before_snapshot["nodeRecordCount"], after_snapshot["nodeRecordCount"], {"removedOperationCount": removed}),
        ValidationCheck("NO_NEW_BLOCKING_FINDINGS", not (after_blocking - before_blocking), True, "Transaction must not introduce a new blocking topology finding code.", sorted(before_blocking), sorted(after_blocking)),
        ValidationCheck("BLOCKING_FINDING_COUNT_NOT_INCREASED", int(after_snapshot["blockingFindingCount"]) <= int(before_snapshot["blockingFindingCount"]), True, "Blocking finding count must not increase.", before_snapshot["blockingFindingCount"], after_snapshot["blockingFindingCount"]),
        ValidationCheck("SELECTED_FINDINGS_RESOLVED", resolved, True, "Every selected mutating action must disappear from the rebuilt topology evidence.", details={"unresolvedActionIds": unresolved_actions}),
        ValidationCheck("NO_NEW_OVERLAP_FINDINGS", not any(finding.code in {"DUPLICATE_ROUTE_SPAN", "COLLINEAR_ROUTE_OVERLAP", "COINCIDENT_NODE_IDENTITY_AMBIGUOUS"} and finding.blocking for finding in after.findings), True, "Transaction must not create an unresolved overlap or ambiguous coincidence."),
    ]
    return tuple(checks)


def apply_topofix_transaction(
    source: str | Path | ResolutionResult,
    *,
    policy: TransactionPolicy,
    config: ResolverConfig | None = None,
) -> TopoFixTransactionResult:
    config = config or ResolverConfig()
    config.validate()
    before = source if isinstance(source, ResolutionResult) else resolve_psi116(source, config)
    actions = _selected_actions(before, policy)
    preflight_reasons = _preflight(before, actions, policy)
    if preflight_reasons:
        return TopoFixTransactionResult(before, None, policy, actions, (), (), tuple(preflight_reasons), None, config)

    root = _parse_clone(before.document.source_text)
    locators = _build_locator_index(root, before)
    operations: list[AppliedOperation] = []
    try:
        for action in actions:
            if action.disposition in EVIDENCE_ONLY_DISPOSITIONS:
                operations.append(AppliedOperation(
                    operation_id=f"OP-{len(operations) + 1:06d}",
                    action_id=action.action_id,
                    disposition=action.disposition,
                    operation="NO_XML_CHANGE",
                    branch_name=action.branch_name,
                    authority=action.authority,
                ))
            elif action.disposition in {"ALIAS_COINCIDENT_NODE", "CONTRACT_PRESERVE_OWNER"}:
                operations.extend(_apply_alias_or_contract(before, action, locators, config, len(operations) + 1))
            elif action.disposition == "SAFE_DROP_PIPE_GEOMETRY":
                operations.append(_apply_safe_drop(before, action, locators, config, f"OP-{len(operations) + 1:06d}"))
            elif action.disposition == "REMOVE_FALSE_RIGID":
                operations.append(_apply_remove_false_rigid(before, action, locators, f"OP-{len(operations) + 1:06d}"))
            else:
                raise ValueError(f"Unsupported selected disposition {action.disposition}.")
    except (KeyError, TypeError, ValueError) as error:
        return TopoFixTransactionResult(before, None, policy, actions, tuple(operations), (), (f"APPLY_FAILED:{error}",), None, config)

    candidate_xml = _serialize(root, before.document.namespace)
    after = resolve_psi116(candidate_xml, config, source_name=f"{before.document.source_path}.topofix")
    checks = _validate_transaction(before, after, actions, operations)
    reject_reasons = tuple(check.code for check in checks if check.blocking and not check.passed)
    return TopoFixTransactionResult(
        source_result=before,
        after_result=after,
        policy=policy,
        selected_actions=actions,
        operations=tuple(operations),
        checks=checks,
        reject_reasons=reject_reasons,
        fixed_xml=candidate_xml if not reject_reasons else None,
        resolver_config=config,
    )


def write_topofix_outputs(
    transaction: TopoFixTransactionResult,
    output_dir: str | Path,
    *,
    stem: str | None = None,
) -> tuple[Path, Path, Path | None]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    resolved_stem = stem or Path(transaction.source_result.document.source_path).stem or "psi116"
    transaction_path = directory / f"{resolved_stem}.topofix-transaction.json"
    validation_path = directory / f"{resolved_stem}.topofix-validation.json"
    fixed_path = directory / f"{resolved_stem}.topofix.xml"
    transaction_path.write_text(json.dumps(transaction.transaction_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation_path.write_text(json.dumps(transaction.validation_payload(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lineage_path = directory / f"{resolved_stem}.topofix-lineage.json"
    if transaction.committed and transaction.fixed_xml is not None:
        from .lineage import build_topofix_source_lineage, verify_topofix_pre_final
        lineage = build_topofix_source_lineage(transaction)
        verify_topofix_pre_final(
            transaction.source_result.document.source_text,
            transaction.fixed_xml,
            transaction.transaction_payload(),
            transaction.validation_payload(),
            lineage, reviewed_action_ids=transaction.policy.selected_action_ids,
        )
        fixed_path.write_text(transaction.fixed_xml, encoding="utf-8")
        lineage_path.write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return transaction_path, validation_path, fixed_path
    if fixed_path.exists():
        fixed_path.unlink()
    if lineage_path.exists():
        lineage_path.unlink()
    return transaction_path, validation_path, None
