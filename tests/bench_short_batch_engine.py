"""Explicit A6b 5/20/89-like engine vs historical one-owner byte/evidence."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_batch import (
    apply_short_batch_bisect, apply_independent_short_batch,
    normalized_owner_evidence,verify_independent_short_batch_pre_final,
    plan_short_groups,
)
from test_short_batch_engine import owner_ids,owner_policy,serial_reference
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture


class BatchRealEngineEquivalence(unittest.TestCase):
    def test_exact_5_20_89_sequential_bytes_and_owner_evidence(self):
        if os.environ.get("A6B_ENGINE_BENCH")!="1":
            raise RuntimeError("Set A6B_ENGINE_BENCH=1")
        cfg=ResolverConfig()
        for count in (5,20,89):
            size=60 if count<89 else 96
            original=interconnected_tee_fixture(size)
            before=resolve_psi116(original,cfg)
            ids=owner_ids(before,cfg,count)
            self.assertEqual(len(ids),count)
            start=time.perf_counter()
            expected_xml,expected_owners=serial_reference(original,ids,cfg)
            sequential_ms=round((time.perf_counter()-start)*1000,3)
            start=time.perf_counter()
            outcome=apply_short_batch_bisect(original,ids,config=cfg)
            batch_ms=round((time.perf_counter()-start)*1000,3)
            self.assertEqual(outcome.fixed_xml,expected_xml,
                             "BATCH_BYTES_NOT_EQUAL_SEQUENTIAL")
            self.assertFalse(outcome.skipped)
            self.assertEqual(len(outcome.owner_results),count)
            self.assertTrue(all(r["status"]=="COMMITTED"
                                for r in outcome.owner_results))
            observed=[{key:value for key,value in item["evidence"].items()
                       if key!="sourceSha256"} for item in outcome.owner_results]
            self.assertEqual(observed,expected_owners,
                             "BATCH_OWNER_EVIDENCE_NOT_EQUAL_SEQUENTIAL")
            self.assertEqual(sum(len(b["ids"]) for b in outcome.successful_batches),count)
            self.assertTrue(all(len(b["ids"])<=32
                                for b in outcome.successful_batches))
            print("A6B_ENGINE_BATCH_EQUIVALENCE="+json.dumps({
                "owners":count,"sequentialMs":sequential_ms,
                "batchMs":batch_ms,
                "speedup":round(sequential_ms/batch_ms,2),
                "batchSizes":[len(b["ids"]) for b in outcome.successful_batches],
                "bytesEqual":True,"ownerEvidenceEqual":True,
            },sort_keys=True))

    def test_group_prefinal_replay_and_single_atom(self):
        cfg=ResolverConfig()
        original=interconnected_tee_fixture(20)
        before=resolve_psi116(original,cfg)
        ids=owner_ids(before,cfg,20)
        p=owner_policy(before,ids,cfg)
        tx=apply_independent_short_batch(before,policy=p,config=cfg)
        proof=verify_independent_short_batch_pre_final(
            original,tx,reviewed_action_ids=ids)
        self.assertEqual(proof["ownerEvidenceCount"],20)
        self.assertEqual(proof["fixedXmlSha256"],
                         tx.transaction_payload()["fixedXmlSha256"])
        print("A6B_BATCH_NATIVE_PREFINAL_20=PASS")
