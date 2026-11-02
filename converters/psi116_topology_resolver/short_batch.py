"""A6b: explicit independent short-owner group engine. No UI/Worker admission.

Distinct from the historical EXACT-ONE apply_short_element path. Atomic:
the original source is never written, and any error refuses the ENTIRE
candidate. All repairs use the existing native PortModel and proposal
verification; every resulting source occurrence is lineage-checked.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from typing import Sequence
import xml.etree.ElementTree as ET

from .connection_ports import PortModel
from .models import FixAction, ResolutionResult, ResolverConfig
from .resolver import resolve_psi116
from .short_elements import short_elements
from .transaction import (
    AppliedOperation, TransactionPolicy, TopoFixTransactionResult,
    ValidationCheck, _parse_clone, _serialize, _build_locator_index,
    _child, _apply_port_connection, _validate_transaction, _record_sha,
)


MAX_INDEPENDENT_SHORT_BATCH = 32
BATCH_SCHEMA = "psi116-short-independent-batch/v1"


class ShortBatchRefused(ValueError):
    """Named refusal. The caller may bisect; no partial XML can escape."""


def _require(value, code):
    if not value:
        raise ShortBatchRefused(code)


def _records(result):
    return [n for b in result.document.branches for n in b.nodes]


def _rows(before, policy, config):
    _require(isinstance(policy, TransactionPolicy),
             "SHORT_BATCH_POLICY_REQUIRED")
    policy.validate()
    _require(not policy.apply_all_safe and not policy.joint_repairs and
             policy.require_no_blocking_plan_actions is True and
             policy.minimum_confidence == TransactionPolicy().minimum_confidence,
             "SHORT_BATCH_POLICY_WIDENING_REFUSED")
    requests=policy.short_element_requests
    _require(2 <= len(requests) <= MAX_INDEPENDENT_SHORT_BATCH and
             len(policy.selected_action_ids)==len(requests) and
             len(set(policy.selected_action_ids))==len(requests),
             "SHORT_BATCH_EXPLICIT_GROUP_SIZE_REFUSED")
    _require(not any(a.status=="BLOCKED" or a.blockers for a in before.fix_actions),
             "BLOCKING_PLAN_ACTIONS_PRESENT")
    index={r["id"]:r for r in short_elements(before.document,config)}
    selected=[]
    for i,request in enumerate(requests):
        _require(isinstance(request,dict) and
                 set(request)=={"id","sourceSha256","nodeKeys"} and
                 request.get("id")==policy.selected_action_ids[i] and
                 request.get("sourceSha256")==before.document.source_sha256,
                 "SHORT_BATCH_SOURCE_OR_SELECTION_DRIFT")
        row=index.get(request["id"])
        _require(row is not None and row["eligible"] and
                 list(request.get("nodeKeys") or ())==row["nodeKeys"] and
                 row["lengthBasis"]=="SOURCE_STRAIGHT_TWO_PORT_SPAN" and
                 row["lengthMm"] <= 6 + 1e-9,
                 "SHORT_BATCH_NOT_ELIGIBLE_OR_WITNESS_DRIFT")
        selected.append(row)
    return selected


def owner_footprint(before, row, config):
    """Conservative influence zone, not just the removed records.

    Reserve entire selected branch plus positive-number peers, and physical
    contacts within the existing (unmodified) 25-mm repair radius. A branch
    containing an owner's closure may NOT share a batch with another owner
    whose branch, aliases or close contacts overlap its influence zone.
    """
    branch=before.document.branches[row["branchIndex"]]
    nodes=_records(before)
    by_key={n.key:n for n in nodes}
    owned={n.key for n in branch.nodes}
    owned.update(row["nodeKeys"])
    owned.update((row["leftKey"],row["rightKey"]))
    _require(all(k in by_key for k in owned),
             "SHORT_BATCH_FOOTPRINT_SOURCE_MISSING")
    changed=True
    while changed:
        changed=False
        positives={by_key[k].node_number for k in owned
                   if by_key[k].positive}
        for n in nodes:
            if n.key in owned:continue
            if n.positive and n.node_number in positives:
                owned.add(n.key);changed=True
    # Different physical clusters which might participate in a global
    # PortModel candidate/closure are not treated as independent.
    contact=set(owned)
    radius=max(config.connection_tolerance_mm,
               config.joint_repair_threshold_mm,25.)
    for n in nodes:
        if n.key in contact or n.position is None:continue
        if any(by_key[k].position is not None and
               n.position.distance_to(by_key[k].position)<=radius+1e-9
               for k in owned):
            contact.add(n.key)
    return frozenset(contact)


def assert_independent(before, rows, config):
    footprints=[owner_footprint(before,row,config) for row in rows]
    for index,keys in enumerate(footprints):
        for prev in range(index):
            _require(not keys.intersection(footprints[prev]),
                     "SHORT_BATCH_INDEPENDENCE_CONFLICT")
    return footprints


def normalized_owner_evidence(transaction):
    """Source-bound, owner-local evidence for comparison with serial semantics.

    Explicitly excludes revision-dependent SHA, operation IDs and the global
    result's intermediate analysis (different for batched vs serial commits).
    Every owner's deleted keys, touched ports, weight, codes and action are
    retained. No missing or duplicated operation can satisfy the census.
    """
    requests=transaction.policy.short_element_requests
    opmap=defaultdict(list)
    for operation in transaction.operations:
        opmap[operation.action_id].append(operation)
    rows={row["id"]:row for row in
          short_elements(transaction.source_result.document,
                         transaction.resolver_config)}
    evidence=[]
    for request in requests:
        owner=request["id"]
        row=rows.get(owner)
        _require(row is not None and row["eligible"] and
                 row["nodeKeys"]==list(request["nodeKeys"]),
                 "SHORT_BATCH_EVIDENCE_OWNER_DRIFT")
        operations=opmap.pop(owner,[])
        removed={op.source_node_key for op in operations
                 if op.operation=="REMOVE_SELECTED_SHORT_ELEMENT_RECORD"}
        _require(removed==set(request["nodeKeys"]) and
                 len(removed)==len(request["nodeKeys"]) and
                 all(op.operation in {"REMOVE_SELECTED_SHORT_ELEMENT_RECORD",
                                      "CLOSE_COMPONENT_PORT"} for op in operations),
                 "SHORT_BATCH_OWNER_REMOVAL_ACCOUNTING_MISMATCH")
        edits=[{"key":op.source_node_key,"before":op.before,
                "after":op.after,"retained":op.retained_node_key}
               for op in operations if op.operation=="CLOSE_COMPONENT_PORT"]
        affected={i["key"] for i in edits}
        _require(not affected.intersection(removed) and
                 len(affected)==len(edits),
                 "SHORT_BATCH_OWNER_PORT_ACCOUNTING_MISMATCH")
        evidence.append({
            "id":owner,
            "sourceRecordKeys":sorted(removed),
            "portEdits":sorted(edits,key=lambda item:item["key"]),
            "removedWeight":row["weightRemoved"],
            "lengthBasis":row["lengthBasis"],
            "lengthMm":row["lengthMm"],
            "operationCount":len(operations),
            "sourceSha256":request["sourceSha256"],
            "committed":transaction.committed,
        })
    _require(not opmap and len(evidence)==len(requests) and
             len(set(x["id"] for x in evidence))==len(evidence),
             "SHORT_BATCH_OWNER_EVIDENCE_CENSUS_MISMATCH")
    return tuple(evidence)


@dataclass(frozen=True)
class IndependentShortBatchResult(TopoFixTransactionResult):
    owner_evidence: tuple[dict,...] = field(default_factory=tuple)

    def transaction_payload(self):
        result=super().transaction_payload()
        result["batch"]={"schema":BATCH_SCHEMA,
                         "ownerCount":len(self.owner_evidence),
                         "owners":list(self.owner_evidence),
                         "atomic":True}
        return result


def apply_independent_short_batch(
    source: ResolutionResult | str,
    *,policy: TransactionPolicy,config: ResolverConfig | None=None,
) -> IndependentShortBatchResult:
    """One atomic, source-bound transaction for 2..32 disjoint owners.

    On ANY failure, raise ShortBatchRefused and return NO result/XML. The
    original file is never written. The old exactly-one entrypoint is NOT
    called for this group and is unchanged.
    """
    config=config or ResolverConfig()
    config.validate()
    before=source if isinstance(source,ResolutionResult) else resolve_psi116(source,config)
    rows=_rows(before,policy,config)
    assert_independent(before,rows,config)
    original=_records(before)
    original_keys={n.key:n for n in original}
    removed=set(key for row in rows for key in row["nodeKeys"])
    _require(len(removed)==sum(len(row["nodeKeys"]) for row in rows),
             "SHORT_BATCH_DUPLICATE_REMOVE_RECORD")
    original_root=_parse_clone(before.document.source_text)
    locators=_build_locator_index(original_root,before)
    for key in removed:
        node=locators[key]
        node.branch_element.remove(node.node_element)
    intermediate=_serialize(original_root,before.document.namespace)
    middle=resolve_psi116(intermediate,config,
                         source_name=before.document.source_path)
    middle_to_original={}
    original_to_middle={}
    for src_branch,mid_branch in zip(before.document.branches,middle.document.branches):
        kept=[n for n in src_branch.nodes if n.key not in removed]
        _require(len(kept)==len(mid_branch.nodes),
                 "SHORT_BATCH_INTERMEDIATE_RECORD_CENSUS_MISMATCH")
        for prior,updated in zip(kept,mid_branch.nodes):
            # ET.indent/namespace presentation changes on the shared
            # serialize; require EXACT source-record fields/attributes/order,
            # rather than representation-sensitive raw_xml whitespace.
            from .lineage import _canonical
            _require(_canonical(ET.fromstring(prior.raw_xml))==
                     _canonical(ET.fromstring(updated.raw_xml)),
                     "SHORT_BATCH_INTERMEDIATE_SOURCE_RECORD_DRIFT")
            middle_to_original[updated.key]=prior
            original_to_middle[prior.key]=updated
    root=_parse_clone(intermediate)
    middle_locators=_build_locator_index(root,middle)
    stage_ops=[]
    stage_actions=[]
    owner_port_ops=defaultdict(list)
    touched=set(removed)
    retained_by_owner={}
    for row in rows:
        l=original_to_middle[row["leftKey"]]
        r=original_to_middle[row["rightKey"]]
        repair_needed=(l.position.distance_to(r.position)>1e-7 or
             (l.positive and r.positive and l.node_number!=r.node_number))
        retained_by_owner[row["id"]]=row["leftKey"]
        if not repair_needed:
            continue
        ports={l.key,r.key}
        closure=next((a for a in middle.fix_actions if
            a.disposition=="CLOSE_PORT_CONNECTION" and
            {a.proposed_changes[0]["movePortKey"],
             a.proposed_changes[0]["targetPortKey"]}==ports),None)
        _require(closure is not None,"SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED")
        change=closure.proposed_changes[0]
        keys={middle_to_original[k].key for k in change["moveKeys"]}
        target=middle_to_original[change["targetPortKey"]].key
        _require(not touched.intersection(keys|{target}) and
                 not any(key in removed for key in keys),
                 "SHORT_BATCH_REPAIR_WRITE_CONFLICT")
        touched.update(keys|{target})
        retained_by_owner[row["id"]]=target
        try:
            ops=_apply_port_connection(middle,closure,middle_locators,config,
                                       1+len(stage_ops))
        except (KeyError,TypeError,ValueError) as error:
            raise ShortBatchRefused(
                "SHORT_BATCH_NATIVE_PORT_REPAIR_REJECTED:"+type(error).__name__) from error
        stage_ops.extend(ops)
        stage_actions.append(closure)
        owner_port_ops[row["id"]].extend(ops)
    final_xml=_serialize(root,before.document.namespace)
    after=resolve_psi116(final_xml,config,
                         source_name=before.document.source_path+".topofix")
    # The native closure validators run against the SINGLE shared intermediate
    # after all selected removals, and the SINGLE final resolved document.
    stage_checks=_validate_transaction(middle,after,stage_actions,stage_ops)
    actions=tuple(FixAction(
        action_id=row["id"],finding_ids=(),disposition="DROP_SELECTED_SHORT_ELEMENT",
        status="PROPOSED",confidence=1.,
        authority="OWNER_EXPLICIT_SHORT_ELEMENT_SELECTION",
        message=f"Drop selected {row['componentType']} ({row['lengthMm']:.3f} mm) and close its surrounding ports.",
        branch_name=row["branchName"],proposed_changes=(row,))
        for row in rows)
    action_by_key={}
    for row in rows:
        for key in row["nodeKeys"]:
            action_by_key[key]=row["id"]
    operations=[]
    for n in original:
        if n.key not in removed:continue
        operations.append(AppliedOperation(
            operation_id=f"OP-{len(operations)+1:06d}",
            action_id=action_by_key[n.key],
            disposition="DROP_SELECTED_SHORT_ELEMENT",
            operation="REMOVE_SELECTED_SHORT_ELEMENT_RECORD",
            branch_name=n.branch_name,source_node_key=n.key,
            source_node_number=n.node_number,before=n.raw_xml,
            authority="OWNER_EXPLICIT_SHORT_ELEMENT_SELECTION",
            source_xml_sha256=_record_sha(n)))
    # Use ORIGINAL record positions and final raw XML to account for each
    # affected physical port. Never infer edit authority from the group output
    # alone: every mutated key must appear in an original source record.
    middle_owner_changes={}
    for row in rows:
        for stage_op in owner_port_ops[row["id"]]:
            original_record=middle_to_original[stage_op.source_node_key]
            _require(original_record.key not in middle_owner_changes,
                     "SHORT_BATCH_DUPLICATE_PORT_MUTATION")
            middle_owner_changes[original_record.key]=row["id"]
    for src_branch,post_branch in zip(before.document.branches,after.document.branches):
        kept=[n for n in src_branch.nodes if n.key not in removed]
        _require(len(kept)==len(post_branch.nodes),
                 "SHORT_BATCH_FINAL_NODE_COUNT_MISMATCH")
        for prior,updated in zip(kept,post_branch.nodes):
            a=ET.fromstring(prior.raw_xml); b=ET.fromstring(updated.raw_xml)
            fields=("NodeNumber","Position")
            old={name:(_child(a,name).text if _child(a,name) is not None else None)
                 for name in fields}
            new={name:(_child(b,name).text if _child(b,name) is not None else None)
                 for name in fields}
            if old==new:continue
            owner=middle_owner_changes.pop(prior.key,None)
            _require(owner is not None,"SHORT_BATCH_UNDECLARED_PORT_CHANGE")
            operations.append(AppliedOperation(
                operation_id=f"OP-{len(operations)+1:06d}",action_id=owner,
                disposition="DROP_SELECTED_SHORT_ELEMENT",
                operation="CLOSE_COMPONENT_PORT",branch_name=prior.branch_name,
                source_node_key=prior.key,source_node_number=prior.node_number,
                retained_node_key=retained_by_owner[owner],
                retained_node_number=original_keys[retained_by_owner[owner]].node_number,
                before=old,after=new,
                authority="OWNER_EXPLICIT_SHORT_ELEMENT_SELECTION",
                source_xml_sha256=_record_sha(prior)))
    _require(not middle_owner_changes,"SHORT_BATCH_CLOSURE_OPERATION_NOT_APPLIED")
    expected=[n for n in original if n.key not in removed]
    actual=_records(after)
    identity=lambda n:(n.branch_index,n.component_ref_no,n.component_type,n.endpoint)
    before_blocking={f.code for f in before.findings if f.blocking}
    after_blocking={f.code for f in after.findings if f.blocking}
    checks=[]
    for row in rows:
        checks.extend((
            ValidationCheck("SHORT_ELEMENT_LENGTH_BASIS_QUALIFIED",
                row["lengthBasis"]=="SOURCE_STRAIGHT_TWO_PORT_SPAN",True,
                "Source owner qualifies as a straight two-port component.",
                details={"ownerId":row["id"],"lengthBasis":row["lengthBasis"]}),
            ValidationCheck("SHORT_ELEMENT_LENGTH_LE_6",row["lengthMm"]<=6+1e-9,True,
                "Qualified straight component length is ≤6 mm.",
                row["lengthMm"],6,{"ownerId":row["id"],
                "lengthBasis":row["lengthBasis"],"measuredSpanMm":row["measuredSpanMm"]}),
        ))
    checks.extend((
        ValidationCheck("SELECTED_RECORD_REMOVAL_ACCOUNTED",
            len(original)-len(removed)==len(actual),True,
            "Only explicitly selected source records were removed.",
            len(original),len(actual),{"removed":len(removed)}),
        ValidationCheck("RETAINED_COMPONENT_OWNERS_PRESERVED",
            Counter(map(identity,expected))==Counter(map(identity,actual)),True,
            "All retained component/port identities are preserved."),
        ValidationCheck("RESTRAINTS_PRESERVED",
            sum(n.has_restraint for n in original)==sum(n.has_restraint for n in actual),True,
            "No restraint was removed."),
        ValidationCheck("WEIGHT_REMOVAL_ACCOUNTED",
            abs(sum(n.weight or 0 for n in expected)-
                sum(n.weight or 0 for n in actual))<1e-8,True,
            "Weight change equals exactly the selected owners.",
            sum(n.weight or 0 for n in original),sum(n.weight or 0 for n in actual),
            {"selectedWeightRemoved":sum(row["weightRemoved"] for row in rows)}),
        ValidationCheck("NO_NEW_BLOCKING_FINDINGS",
            not (after_blocking-before_blocking) and
            sum(f.blocking for f in after.findings)<=
            sum(f.blocking for f in before.findings),True,
            "No new blocking finding introduced by the selected group."),
    ))
    for row in rows:
        l=original_to_middle[row["leftKey"]]
        r=original_to_middle[row["rightKey"]]
        li=(l.branch_index,l.source_index)
        ri=(r.branch_index,r.source_index)
        final_l=after.document.branches[li[0]].nodes[li[1]]
        final_r=after.document.branches[ri[0]].nodes[ri[1]]
        checks.append(ValidationCheck("CUT_PORTS_CLOSED",
            final_l.position.distance_to(final_r.position)<1e-7,True,
            "Surrounding ports are physically closed after selection.",
            details={"ownerId":row["id"]}))
    checks.extend(replace(c,code="CLOSURE_"+c.code,
                          details={**c.details,"stage":"AFTER_SELECTED_REMOVAL"})
                  for c in stage_checks)
    reject=tuple(c.code for c in checks if c.blocking and not c.passed)
    _require(not reject,"SHORT_BATCH_VALIDATION_REJECTED:"+",".join(reject))
    candidate=IndependentShortBatchResult(before,after,policy,actions,
         tuple(operations),tuple(checks),(),final_xml,config,())
    owners=normalized_owner_evidence(candidate)
    _require(len(owners)==len(rows) and
             sum(x["operationCount"] for x in owners)==len(operations),
             "SHORT_BATCH_PER_OWNER_ACCOUNTING_REJECTED")
    candidate=replace(candidate,owner_evidence=owners)
    # Full source occurrence lineage replays ALL changes from original XML.
    # Includes exact original/after attributes and forbids undeclared writes.
    from .lineage import build_topofix_source_lineage
    try:
        build_topofix_source_lineage(candidate)
    except ValueError as error:
        raise ShortBatchRefused("SHORT_BATCH_LINEAGE_REJECTED:"+str(error)) from error
    return candidate


@dataclass(frozen=True)
class BatchRunReceipt:
    original_sha256: str
    fixed_xml: str
    owner_results: tuple[dict,...]
    successful_batches: tuple[dict,...]
    skipped: tuple[dict,...]


def _single_attempt(source,owner,config):
    """Explicitly retain historical exact-one transaction/refusal semantics."""
    from .transaction import apply_topofix_transaction
    before=resolve_psi116(source,config)
    row=next((r for r in short_elements(before.document,config)
              if r["id"]==owner),None)
    _require(row is not None and row["eligible"],
             "SHORT_ELEMENT_NOT_QUALIFIED_OR_WITNESS_DRIFT")
    policy=TransactionPolicy(
        selected_action_ids=(owner,),
        short_element_requests=({key:row[key] for key in
                                 ("id","sourceSha256","nodeKeys")},))
    return apply_topofix_transaction(before,policy=policy,config=config)



def plan_short_groups(before,owner_ids:Sequence[str],
                      config:ResolverConfig,*,maximum=MAX_INDEPENDENT_SHORT_BATCH):
    """Preserve selection ORDER; adjacent owners only share an independent batch.

    Unknown/ineligible owners are singles so historical refusal codes survive.
    Never reorder a later owner ahead of an interacting earlier one.
    """
    _require(1<=maximum<=MAX_INDEPENDENT_SHORT_BATCH,
             "SHORT_BATCH_GROUP_SIZE_INVALID")
    rowmap={r["id"]:r for r in short_elements(before.document,config)}
    groups=[]
    current=[]
    footprint=[]
    for identifier in owner_ids:
        row=rowmap.get(identifier)
        zone=(owner_footprint(before,row,config)
              if row is not None and row["eligible"] else None)
        if (current and (zone is None or len(current)>=maximum or
            any(zone.intersection(other) for other in footprint))):
            groups.append(tuple(current))
            current=[]
            footprint=[]
        if zone is None:
            groups.append((identifier,))
        else:
            current.append(identifier)
            footprint.append(zone)
    if current:groups.append(tuple(current))
    _require([i for group in groups for i in group]==list(owner_ids),
             "SHORT_BATCH_PLAN_ORDER_DRIFT")
    return tuple(groups)


def apply_short_batch_bisect(source: str,owner_ids:Sequence[str],
                             *,config:ResolverConfig|None=None):
    """Atomic group retries; rejected group never publishes partial bytes.

    Emits one normalized owner evidence entry per accepted owner. A refused
    singleton invokes the historical exact-one engine and records its code.
    Every recursive child begins on the last fully committed source revision.
    """
    config=config or ResolverConfig()
    base=resolve_psi116(source,config)
    _require(len(owner_ids)==len(set(owner_ids)) and
             all(isinstance(item,str) and item.startswith("SHORT:")
                 for item in owner_ids),
             "SHORT_BATCH_INVALID_SELECTION")
    result_source=source
    outcomes=[]
    batches=[]
    skipped=[]
    def recurse(ids):
        nonlocal result_source
        if not ids:return
        if len(ids)==1:
            try:
                txn=_single_attempt(result_source,ids[0],config)
                if not txn.committed:raise ShortBatchRefused(
                    "SHORT_ELEMENT_RECONNECTION_REJECTED:"+",".join(txn.reject_reasons))
            except (ValueError,KeyError) as error:
                code=str(error).split(":",1)[0]
                skipped.append({"id":ids[0],"reason":code})
                outcomes.append({"id":ids[0],"status":"REFUSED","code":code})
                return
            source_before=sha256(result_source.encode("utf-8")).hexdigest()
            result_source=txn.fixed_xml
            record=normalized_owner_evidence(txn)[0]
            outcomes.append({"id":ids[0],"status":"COMMITTED",
                             "sourceSha256":source_before,
                             "evidence":record})
            batches.append({"ids":list(ids),"sourceSha256":source_before,
                            "fixedSha256":sha256(result_source.encode()).hexdigest(),
                            "transaction":txn.transaction_payload(),
                            "validation":txn.validation_payload()})
            return
        if len(ids)>MAX_INDEPENDENT_SHORT_BATCH:
            midpoint=min(MAX_INDEPENDENT_SHORT_BATCH,len(ids)//2)
            recurse(ids[:midpoint]);recurse(ids[midpoint:]);return
        before=resolve_psi116(result_source,config)
        rows={r["id"]:r for r in short_elements(before.document,config)}
        try:
            _require(all(i in rows and rows[i]["eligible"] for i in ids),
                     "SHORT_BATCH_OWNER_INELIGIBLE")
            selected=[rows[i] for i in ids]
            _require(len({r["branchIndex"] for r in selected})==len(ids),
                     "SHORT_BATCH_INDEPENDENCE_CONFLICT")
            requests=tuple({key:rows[i][key] for key in
                            ("id","sourceSha256","nodeKeys")} for i in ids)
            policy=TransactionPolicy(selected_action_ids=tuple(ids),
                                     short_element_requests=requests)
            batch=apply_independent_short_batch(before,policy=policy,config=config)
            _require(batch.committed,"SHORT_BATCH_NOT_COMMITTED")
            evidence=normalized_owner_evidence(batch)
            # Verify EVERY owner before touching result_source. A missing or
            # partial group is a REFUSAL, never a partial success.
            _require(len(evidence)==len(ids) and
                     [item["id"] for item in evidence]==list(ids) and
                     len(batch.owner_evidence)==len(ids) and
                     batch.owner_evidence==evidence,
                     "SHORT_BATCH_OWNER_EVIDENCE_CENSUS_MISMATCH")
        except (ShortBatchRefused,ValueError,KeyError):
            halfway=len(ids)//2
            recurse(ids[:halfway]);recurse(ids[halfway:]);return
        old_sha=sha256(result_source.encode("utf-8")).hexdigest()
        result_source=batch.fixed_xml
        for item in evidence:
            outcomes.append({"id":item["id"],"status":"COMMITTED",
                             "sourceSha256":old_sha,"evidence":item})
        batches.append({"ids":list(ids),"sourceSha256":old_sha,
                        "fixedSha256":sha256(result_source.encode()).hexdigest(),
                        "transaction":batch.transaction_payload(),
                        "validation":batch.validation_payload()})
    for group in plan_short_groups(base,list(owner_ids),config):
        recurse(list(group))
    _require(len(outcomes)==len(owner_ids),"SHORT_BATCH_RUN_OWNER_CENSUS_MISMATCH")
    return BatchRunReceipt(base.document.source_sha256,result_source,
                           tuple(outcomes),tuple(batches),tuple(skipped))
