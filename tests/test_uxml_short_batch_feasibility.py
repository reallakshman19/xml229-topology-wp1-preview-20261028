"""Step-1 ONLY: synthetic independent-owner batch feasibility probe.

This is NOT production authorization, a canonical UXML batch operation, a
transaction result, or a replacement for validated sourceRefs/loss evidence.
It refuses interaction; its single-tree candidate MUST match byte-for-byte
the existing independent sequential native transaction before optimization.
For full owner approval, the browser/canonical witness must be measured later.

UXML_SHORT_BATCH_FEASIBILITY=1 with pinned XCU_UXML_ROOT enables the probe.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.connection_ports import PortModel
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import (
    TransactionPolicy,apply_topofix_transaction,_parse_clone,
    _build_locator_index,_serialize,_child,_set_child_text)
from psi116_topology_resolver.uxml_adapter import resolve_from_uxml
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture


def elapsed(function,*args,**kw):
    begin=time.perf_counter()
    value=function(*args,**kw)
    return value,round((time.perf_counter()-begin)*1000,3)


def independence_zones(before,rows):
    """Conservative: include ENTIRE owner branch and all global shared IDs.

    This intentionally over-refuses contacts rather than infer independence.
    Read influence includes every node in the branch plus positive NodeNumber
    aliases elsewhere; output footprint includes dropped and moved ports.
    """
    all_nodes=[node for branch in before.document.branches for node in branch.nodes]
    by_num=defaultdict(set)
    for node in all_nodes:
        if node.positive:by_num[node.node_number].add(node.key)
    zones=[]
    for row in rows:
        branch=before.document.branches[row["branchIndex"]]
        zone=set(node.key for node in branch.nodes)
        zone.update(row["nodeKeys"])
        zone.update((row["leftKey"],row["rightKey"]))
        for node in branch.nodes:
            if node.positive:zone.update(by_num[node.node_number])
        zones.append(zone)
    for i,zone in enumerate(zones):
        for j in range(i):
            if zone & zones[j]:
                raise ValueError("BATCH_INDEPENDENCE_CONFLICT:%d:%d"%(j,i))
    return zones


def disposable_single_tree_candidate(before,rows,config):
    """No production shortcut; fail closed on any missing independent witness."""
    timings={}
    t=time.perf_counter()
    independence_zones(before,rows)
    selected=set()
    for row in rows:
        assert row["eligible"] and row["lengthBasis"]=="SOURCE_STRAIGHT_TWO_PORT_SPAN"
        assert row["sourceSha256"]==before.document.source_sha256
        assert row["lengthMm"]<=6+1e-9
        selected.update(row["nodeKeys"])
    timings["selectAndIndependenceMs"]=round((time.perf_counter()-t)*1000,3)
    t=time.perf_counter()
    source_document=before.document
    reduced=replace(source_document,branches=tuple(
        replace(b,nodes=tuple(n for n in b.nodes if n.key not in selected))
        for b in source_document.branches))
    model=PortModel(reduced,config)
    repairs=[]
    affected=set(selected)
    for row in rows:
        left=model.port_by_key.get(row["leftKey"])
        right=model.port_by_key.get(row["rightKey"])
        if left is None or right is None:raise ValueError("BATCH_SURROUNDING_PORT_MISSING")
        proposal=model.repair(left,right)
        read_write=set(proposal["moveKeys"])|{proposal["targetPortKey"],proposal["movePortKey"]}
        if affected.intersection(read_write):raise ValueError("BATCH_CROSS_OWNER_WRITE_CONFLICT")
        affected.update(read_write)
        repairs.append(proposal)
    timings["repairWitnessMs"]=round((time.perf_counter()-t)*1000,3)
    t=time.perf_counter()
    root=_parse_clone(source_document.source_text)
    locator=_build_locator_index(root,before)
    for row in rows:
        for key in row["nodeKeys"]:
            target=locator[key]
            target.branch_element.remove(target.node_element)
    for proposal in repairs:
        moving=locator[proposal["movePortKey"]]
        target=locator[proposal["targetPortKey"]]
        delta=proposal["delta"]
        for key in proposal["moveKeys"]:
            loc=locator[key];node=loc.record
            original=_child(loc.node_element,"Position").text
            if not any(abs(v)>1e-9 for v in delta):
                pos=original
            elif node.position.distance_to(moving.record.position)<=1e-6:
                pos=_child(target.node_element,"Position").text
            else:
                pos=" ".join(format(v+d,".15g")
                             for v,d in zip(node.position.as_list(),delta))
            if pos!=original:
                _set_child_text(loc.node_element,"Position",pos)
            if key in proposal["aliases"]:
                _set_child_text(loc.node_element,"NodeNumber",
                                proposal["aliases"][key])
    candidate=_serialize(root,source_document.namespace)
    timings["singleParseEditSerializeMs"]=round((time.perf_counter()-t)*1000,3)
    after,analyze_ms=elapsed(resolve_psi116,candidate,config)
    timings["afterAnalyzeMs"]=analyze_ms
    return candidate,after,timings


def serial_native(original,ids,cfg):
    source=original
    stages=defaultdict(float)
    started=time.perf_counter()
    for identifier in ids:
        before,ms=elapsed(resolve_psi116,source,cfg);stages["resolveMs"]+=ms
        rows,ms=elapsed(short_elements,before.document,cfg);stages["eligibilityMs"]+=ms
        row=next(r for r in rows if r["id"]==identifier)
        if not row["eligible"]:raise AssertionError(("SEQ_INELIGIBLE",identifier,row["reason"]))
        policy=TransactionPolicy(
            selected_action_ids=(identifier,),
            short_element_requests=({k:row[k] for k in ("id","sourceSha256","nodeKeys")},))
        txn,ms=elapsed(apply_topofix_transaction,before,policy=policy,config=cfg)
        stages["nativeTransactionMs"]+=ms
        if not txn.committed:raise AssertionError(("SEQ_REJECTED",identifier,txn.reject_reasons))
        source=txn.fixed_xml
    return source,{k:round(v,3) for k,v in stages.items()},round((time.perf_counter()-started)*1000,3)


def prototype_batched(original,ids,size,cfg,*,reader=None):
    source=original
    stages=defaultdict(float)
    started=time.perf_counter()
    for chunk_start in range(0,len(ids),size):
        chunk=ids[chunk_start:chunk_start+size]
        before,ms=elapsed(resolve_psi116,source,cfg);stages["resolveMs"]+=ms
        rows,ms=elapsed(short_elements,before.document,cfg);stages["eligibilityMs"]+=ms
        selected=[next(r for r in rows if r["id"]==identifier) for identifier in chunk]
        if reader is not None:
            with tempfile.TemporaryDirectory(prefix="a6b-prototype-uxml-") as d:
                path=Path(d)/"source.xml";path.write_text(source,encoding="utf-8")
                t=time.perf_counter()
                result=subprocess.run(
                    ["node",str(reader/"tools"/"psi116-to-uxml.mjs"),str(path)],
                    cwd=reader,capture_output=True,text=True,timeout=120)
                if result.returncode:raise AssertionError(result.stderr)
                uxml=json.loads(result.stdout)
                stages["uxmlReaderMs"]+=(time.perf_counter()-t)*1000
                u_before,ms=elapsed(resolve_from_uxml,uxml,cfg,source_name=str(path))
                stages["uxmlResolveMs"]+=ms
                if u_before.document.source_text!=source:
                    raise AssertionError("UXML_ORIGINAL_SOURCE_WITNESS_DIFFERENT")
                candidate,_,parts=disposable_single_tree_candidate(u_before,selected,cfg)
        else:
            candidate,_,parts=disposable_single_tree_candidate(before,selected,cfg)
        for k,v in parts.items():stages[k]+=v
        source=candidate
    return source,{k:round(v,3) for k,v in stages.items()},round((time.perf_counter()-started)*1000,3)


class BatchFeasibility(unittest.TestCase):
    def test_step1_native_and_uxml_simulated_prototype_vs_sequential(self):
        if os.environ.get("UXML_SHORT_BATCH_FEASIBILITY")!="1":
            self.skipTest("UXML_SHORT_BATCH_FEASIBILITY=1 required")
        reader=Path(os.environ.get("XCU_UXML_ROOT",""))
        if not (reader/"tools"/"psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned XCU_UXML_ROOT required")
        cfg=ResolverConfig()
        report=[]
        for count in (5,20,89):
            # 96 branches to supply an 89-owner stress set; 60-TEE also
            # tested for the original 5 and 20 selections.
            fixture_count=60 if count<89 else 96
            source=interconnected_tee_fixture(fixture_count)
            before=resolve_psi116(source,cfg)
            rows=[r for r in short_elements(before.document,cfg)
                  if r["componentRefNo"].startswith("SHORT-") and r["eligible"]]
            self.assertEqual(len(rows),fixture_count)
            ids=[r["id"] for r in rows[3:3+count]]
            self.assertEqual(len(ids),count)
            serial,steps,serial_ms=serial_native(source,ids,cfg)
            for group in sorted(set((8,16,32,count))):
                native,native_stage,native_ms=prototype_batched(source,ids,group,cfg)
                same=native==serial
                entry={"owners":count,"group":group,
                    "serialNativeMs":serial_ms,"serialNativeStages":steps,
                    "candidateNativeMs":native_ms,"candidateNativeStages":native_stage,
                    "nativeBytesEqual":same}
                if not same:
                    print("A6B_STEP1_NATIVE_DIFFERENT="+json.dumps(entry,sort_keys=True))
                    self.fail("BATCH_BYTES_NOT_EQUAL_SERIAL:%s:%s"%(count,group))
                # This is NOT a real canonical batch witness. A single
                # UXML parse+projection and a speculative native candidate
                # are profiled; production path is explicitly NOT_IMPLEMENTED.
                uxml,uxml_stage,uxml_ms=prototype_batched(
                    source,ids,group,cfg,reader=reader)
                entry.update({"candidateUxmlMs":uxml_ms,
                              "candidateUxmlStages":uxml_stage,
                              "uxmlBytesEqual":uxml==serial,
                              "canonicalBatchWitness":"NOT_IMPLEMENTED",
                              "pyodide":"NOT_RUN"})
                print("A6B_STEP1_PROBE="+json.dumps(entry,sort_keys=True))
                self.assertEqual(uxml,serial,
                    "BATCH_UXML_CANDIDATE_BYTES_DIFFERENT:%s:%s"%(count,group))
