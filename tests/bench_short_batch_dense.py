"""Explicit public A6b dense 5/20/89 owner speed and byte/evidence gate.

Not discovered by default. No private models. Run with A6B_DENSE_BENCH=1.
"""
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch
import json
import os
import sys
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
import psi116_topology_resolver.short_batch as batch
from psi116_topology_resolver import ResolverConfig,resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from test_short_batch_graph import (
    dense_fixture,eligible_owners,contiguous_plan,size_histogram,
    conflict_reasons,
)
from test_short_batch_engine import serial_reference

def old_plan(before,ids,cfg,*,maximum=32):
    lookup={r["id"]:r for r in short_elements(before.document,cfg)}
    if not all(i in lookup and lookup[i]["eligible"] for i in ids):
        raise AssertionError("DENSE_BASELINE_REQUIRES_ELIGIBLE")
    return contiguous_plan(before,[lookup[i] for i in ids],cfg,maximum)

def normalized(receipt):
    return [{key:val for key,val in item["evidence"].items()
             if key!="sourceSha256"} for item in receipt.owner_results
            if item["status"]=="COMMITTED"]

class DenseNativeBench(unittest.TestCase):
    def test_dense_public_graph_preserves_exact_5_20_89_bytes_and_evidence(self):
        if os.getenv("A6B_DENSE_BENCH")!="1":
            raise RuntimeError("A6B_DENSE_BENCH=1 required (not auto-discovered)")
        cfg=ResolverConfig()
        for n in (5,20,89):
            source=dense_fixture(24,4)
            before=resolve_psi116(source,cfg)
            owners=eligible_owners(before,cfg,n)
            ids=[r["id"] for r in owners]
            old_groups=contiguous_plan(before,owners,cfg)
            new_groups=batch.plan_short_groups(before,ids,cfg)
            edges=conflict_reasons(before,owners,cfg)
            self.assertEqual(sum(len(g) for g in new_groups),n)
            self.assertLessEqual(max(map(len,new_groups)),32)
            t=time.perf_counter()
            serial,expected=serial_reference(source,ids,cfg)
            serial_ms=round((time.perf_counter()-t)*1000,2)
            t=time.perf_counter()
            with patch.object(batch,"plan_short_groups",side_effect=old_plan):
                old=batch.apply_short_batch_bisect(source,ids,config=cfg)
            old_ms=round((time.perf_counter()-t)*1000,2)
            t=time.perf_counter()
            actual=batch.apply_short_batch_bisect(source,ids,config=cfg)
            graph_ms=round((time.perf_counter()-t)*1000,2)
            self.assertFalse(old.skipped,("LEGACY_REFUSALS",n,old.skipped))
            self.assertFalse(actual.skipped,("GRAPH_REFUSALS",n,actual.skipped))
            self.assertEqual(old.fixed_xml,serial,"DENSE_OLD_BYTES_DRIFT")
            self.assertEqual(actual.fixed_xml,serial,"DENSE_GRAPH_BYTES_DRIFT")
            self.assertEqual(normalized(old),expected,"DENSE_OLD_EVIDENCE_DRIFT")
            self.assertEqual(normalized(actual),expected,"DENSE_GRAPH_EVIDENCE_DRIFT")
            self.assertEqual([item["id"] for item in actual.owner_results],ids,
                             "DENSE_GRAPH_ORIGINAL_ORDER_CENSUS_DRIFT")
            result={"owners":n,"serialMs":serial_ms,"oldMs":old_ms,
                    "graphMs":graph_ms,"oldGroups":len(old_groups),
                    "newGroups":len(new_groups),
                    "oldSizeDistribution":size_histogram(old_groups),
                    "newSizeDistribution":size_histogram(new_groups),
                    "conflicts":edges,"oldActualCommittedBatches":
                    size_histogram([b["ids"] for b in old.successful_batches]),
                    "graphActualCommittedBatches":
                    size_histogram([b["ids"] for b in actual.successful_batches]),
                    "bytesEqual":True,"evidenceEqual":True,
                    "refusalsOld":len(old.skipped),
                    "refusalsGraph":len(actual.skipped)}
            print("A6B_DENSE_QUAL="+json.dumps(result,sort_keys=True),flush=True)
