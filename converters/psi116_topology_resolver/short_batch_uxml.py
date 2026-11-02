"""A6b: one authority-complete, sourceRef/loss-qualified UXML batch witness.

This is a separate explicit route, NOT an override of historical UXML S2
single-owner export/apply. No file is written. A rejected group yields no
candidate to the caller; bisect may retry source-bound owners individually.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from .models import ResolverConfig
from .resolver import resolve_psi116
from .short_batch import apply_independent_short_batch, normalized_owner_evidence
from .short_elements import short_elements
from .transaction import TransactionPolicy, _build_locator_index, _parse_clone
from .uxml_adapter import resolve_from_uxml
from .short_memo import uxml_resolve
from .uxml_edit_ops import (
    UxmlPatchError, _require, _source_sha, _source_refs_by_key,
    _source_record_paths, _enforce_today_auto_policy, compare_hub_patch,
)

BATCH_UXML_WITNESS_SCHEMA = "uxml-short-batch-canonical-witness/v1"


def _canonical_op(row,request,ops,uxml,records,paths,refs,sha):
    """Canonical original-source operations for ONE owner, no native replay.

    Replicates the existing one-owner field-level and loss-contract veto
    while deriving effects from the independent group native transaction.
    """
    edits=[]
    for change in ops:
        _require(change.action_id==request["id"] and
                 change.operation in {"REMOVE_SELECTED_SHORT_ELEMENT_RECORD",
                                      "CLOSE_COMPONENT_PORT"},
                 "UXML_SHORT_BATCH_UNEXPECTED_MUTATION_KIND")
        if change.operation=="REMOVE_SELECTED_SHORT_ELEMENT_RECORD":
            _require(change.source_node_key in row["nodeKeys"],
                     "UXML_SHORT_BATCH_DELETE_TARGET_MISMATCH")
            edits.append({"recordKey":change.source_node_key,"field":"Source record",
                          "before":"Present","after":"Removed"})
        else:
            _require(isinstance(change.before,dict) and isinstance(change.after,dict) and
                     set(change.before)==set(change.after)=={"NodeNumber","Position"},
                     "UXML_SHORT_BATCH_PORT_FIELDS_INVALID")
            for field in ("NodeNumber","Position"):
                if change.before[field]!=change.after[field]:
                    edits.append({"recordKey":change.source_node_key,"field":field,
                                  "before":change.before[field],"after":change.after[field]})
    _require({e["recordKey"] for e in edits if e["field"]=="Source record"}==
             set(row["nodeKeys"]), "UXML_SHORT_BATCH_DELETE_SET_MISMATCH")
    edits.sort(key=lambda e:(e["recordKey"],e["field"]))
    targets=sorted({e["recordKey"] for e in edits})
    _require(bool(targets) and all(k in refs for k in targets),
             "UXML_SHORT_BATCH_SOURCE_REF_NOT_FOUND")
    touched={key:set() for key in targets}
    for e in edits:
        touched[e["recordKey"]].add(
            "*" if e["field"]=="Source record" else e["field"])
    losses=uxml.get("lossContract")
    _require(isinstance(losses,list),"UXML_LOSS_CONTRACT_MISSING")
    removed_with_record=set()
    for key,fields in touched.items():
        _require(key in records and key in paths,
                 "UXML_SHORT_BATCH_ORIGINAL_RECORD_NOT_FOUND:"+key)
        _require(records[key].connection_type!="CLOS",
                 "UXML_CLOS_WRITE_HELD:"+key)
        for loss in losses:
            _require(isinstance(loss,dict) and
                     isinstance(loss.get("details"),dict) and
                     isinstance(loss["details"].get("sourcePath"),str),
                     "UXML_LOSS_CONTRACT_INVALID")
            loss_path,node_path=loss["details"]["sourcePath"],paths[key]
            if loss_path!=node_path and not loss_path.startswith(node_path+"/"):
                continue
            if ("*" in fields and loss_path.startswith(node_path+"/") and
                    loss.get("code")=="PSI116_RAW_SOURCE_ONLY_NOT_SEMANTICALLY_CARRIED"):
                segment=loss_path[len(node_path)+1:].split("/",1)[0]
                field=segment.split("[",1)[0]
                _require(bool(field) and segment.startswith(field+"[") and
                         segment.endswith("]") and
                         segment[len(field)+1:-1].isascii() and
                         segment[len(field)+1:-1].isdigit(),
                         "UXML_LOSS_CONTRACT_FIELD_TOUCH:"+key)
                removed_with_record.add((key,field))
                continue
            if "*" in fields or any(loss_path.startswith(
                    node_path+"/"+field+"[") for field in fields):
                raise UxmlPatchError("UXML_LOSS_CONTRACT_FIELD_TOUCH:"+key)
    return {
        "opId":"UXML-OP-"+request["id"],"kind":"DROP_SHORT_ELEMENT",
        "sourceActionId":request["id"],"fileSha256":sha,
        "targets":targets,
        "removedWithRecord":[{"recordKey":k,"field":f}
                             for k,f in sorted(removed_with_record)],
        "params":[{
            "request":{"id":row["id"],"sourceSha256":sha,
                       "nodeKeys":list(row["nodeKeys"])},
            "leftKey":row["leftKey"],"rightKey":row["rightKey"],
            "lengthBasis":row["lengthBasis"],"lengthMm":row["lengthMm"],
            "edits":edits,
        }],
    }


def qualify_short_batch_uxml(original: str|Path,uxml:dict,
                             *,policy:TransactionPolicy,
                             config:ResolverConfig|None=None,
                             direct_transaction=None):
    """One pinned UXML adapter + one UXML-native transaction for a group.

    Independent original-source native transaction is mandatory. A single
    canonical, group-wide sourceRef/loss comparison checks *every* owner
    before any result can be emitted, and direct/UXML full receipts/bytes
    must agree. No source file writes, no reconstructed UXML XML writer.
    """
    config=config or ResolverConfig()
    config.validate()
    _require(isinstance(policy,TransactionPolicy) and
             not policy.joint_repairs and not policy.apply_all_safe and
             policy.require_no_blocking_plan_actions is True and
             policy.minimum_confidence==TransactionPolicy().minimum_confidence,
             "UXML_SHORT_BATCH_POLICY_WIDENING_REFUSED")
    path=Path(original)
    source=path.read_bytes()
    sha=sha256(source).hexdigest()
    _require(isinstance(uxml,dict) and _source_sha(uxml)==sha,
             "UXML_FILE_SHA256_MISMATCH")
    refs=_source_refs_by_key(uxml,sha)
    before=resolve_psi116(path,config)
    _require(before.document.source_sha256==sha,"UXML_ORIGINAL_BYTES_MISMATCH")
    # B1 isolation: use the actual UXML-fed document, not direct source
    # evidence. Reconstructed weight/position/type must influence this path.
    adapted=uxml_resolve(uxml,config,source_name=str(path),
                         resolver=resolve_from_uxml)
    _require(adapted.document.source_text.encode("utf-8")==source,
             "UXML_ORIGINAL_BYTES_MISMATCH")
    original_locators=_build_locator_index(_parse_clone(
        before.document.source_text),before)
    direct=direct_transaction or apply_independent_short_batch(
        before,policy=policy,config=config)
    patched=apply_independent_short_batch(
        adapted,policy=policy,config=config)
    _require(direct.committed and patched.committed,
             "UXML_SHORT_BATCH_NATIVE_REFUSED")
    # One group-wide sourceRef/loss witness: do not reconstruct XML from
    # UXML. All proposed edit targets must exist at original source path.
    records={n.key:n for b in adapted.document.branches for n in b.nodes}
    paths=_source_record_paths(adapted.document.source_text,adapted)
    row_map={r["id"]:r for r in short_elements(adapted.document,config)}
    op_by_owner=defaultdict(list)
    for op in patched.operations:op_by_owner[op.action_id].append(op)
    ops=[]
    seen_targets={}
    for request in policy.short_element_requests:
        owner=request["id"]
        row=row_map.get(owner)
        _require(row is not None and row["eligible"] and
                 request["sourceSha256"]==sha and
                 row["nodeKeys"]==list(request["nodeKeys"]),
                 "UXML_SHORT_BATCH_NOT_ELIGIBLE_OR_WITNESS_DRIFT")
        _require(owner in op_by_owner,"UXML_SHORT_BATCH_OWNER_OP_MISSING")
        op=_canonical_op(row,request,op_by_owner.pop(owner),
                         uxml,records,paths,refs,sha)
        for key in op["targets"]:
            _require(key not in seen_targets,
                     "UXML_SHORT_BATCH_CROSS_OWNER_TARGET:"+key)
            seen_targets[key]=owner
            locator=original_locators.get(key)
            source_ref=refs[key]
            _require(locator is not None,
                     "UXML_ORIGINAL_RECORD_KEY_MISMATCH:"+key)
            record=locator.record
            _require(source_ref.get("branchName")==record.branch_name and
                (source_ref.get("nodeNumber") is None and record.node_number is None or
                 str(source_ref.get("nodeNumber"))==str(record.node_number)) and
                (source_ref.get("endpoint") is None and record.endpoint is None or
                 str(source_ref.get("endpoint"))==str(record.endpoint)),
                "UXML_ORIGINAL_SOURCE_REF_MISMATCH:"+key)
        ops.append(op)
    _require(not op_by_owner and len(ops)==len(policy.short_element_requests),
             "UXML_SHORT_BATCH_OWNER_OP_CENSUS_MISMATCH")
    owner_evidence=normalized_owner_evidence(patched)
    _require(len(owner_evidence)==len(ops) and
             {row["id"] for row in owner_evidence}==
             {op["sourceActionId"] for op in ops},
             "UXML_SHORT_BATCH_OWNER_EVIDENCE_DRIFT")
    differences=compare_hub_patch(direct,patched)
    _require(not differences,
             "UXML_SHORT_BATCH_INDEPENDENT_PARITY_DIFFERENT")
    canonical_payload={
        "schema":BATCH_UXML_WITNESS_SCHEMA,
        "sourceSha256":sha,
        "ownerIds":list(policy.selected_action_ids),
        "ops":ops,
        "sourceRefCount":len(seen_targets),
        "lossContractChecked":True,
        "originalSourceCompared":True,
        "nativeVsUxmlParity":"EQUAL",
        "transactionSha256":sha256(json.dumps(
            patched.transaction_payload(),sort_keys=True,
            separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest(),
    }
    return direct,patched,canonical_payload
