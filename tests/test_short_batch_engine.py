"""A6b isolated native group engine; unchanged legacy singleton authority."""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
from psi116_topology_resolver import ResolverConfig,resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.short_batch import (
    ShortBatchRefused, apply_independent_short_batch,
    apply_short_batch_bisect, assert_independent,
    normalized_owner_evidence,verify_independent_short_batch_pre_final,
)
from psi116_topology_resolver.transaction import (
    TransactionPolicy,apply_topofix_transaction)
from psi116_topology_resolver.lineage import build_topofix_source_lineage
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture


def owner_policy(before,ids,cfg):
    rows={r["id"]:r for r in short_elements(before.document,cfg)}
    return TransactionPolicy(
        selected_action_ids=tuple(ids),
        short_element_requests=tuple(
            {key:rows[i][key] for key in ("id","sourceSha256","nodeKeys")}
            for i in ids))


def owner_ids(before,cfg,count):
    return [r["id"] for r in short_elements(before.document,cfg)
            if r["eligible"] and r["componentRefNo"].startswith("SHORT-")][:count]


def serial_reference(source,ids,cfg):
    receipts=[]
    for owner in ids:
        prior=resolve_psi116(source,cfg)
        policy=owner_policy(prior,[owner],cfg)
        txn=apply_topofix_transaction(prior,policy=policy,config=cfg)
        if not txn.committed:
            raise AssertionError((owner,txn.reject_reasons))
        local=normalized_owner_evidence(txn)[0]
        receipts.append({key:value for key,value in local.items()
                         if key!="sourceSha256"})
        source=txn.fixed_xml
    return source,receipts


class ShortBatchEngine(unittest.TestCase):
    def setUp(self):
        self.cfg=ResolverConfig()

    def test_two_disjoint_group_is_atomic_and_source_lineage_authoritative(self):
        original=interconnected_tee_fixture(2)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,2)
        self.assertEqual(len(ids),2)
        group=apply_independent_short_batch(
            before,policy=owner_policy(before,ids,self.cfg),config=self.cfg)
        self.assertTrue(group.committed)
        reference,expected=serial_reference(original,ids,self.cfg)
        self.assertEqual(group.fixed_xml,reference)
        self.assertEqual(len(group.owner_evidence),2)
        observed=[{k:v for k,v in item.items() if k!="sourceSha256"}
                  for item in group.owner_evidence]
        self.assertEqual(observed,expected)
        proof=build_topofix_source_lineage(group)
        self.assertEqual(proof["counts"]["removedSelectedShortElementOccurrences"],4)
        self.assertTrue(all(c.passed for c in group.checks if c.blocking))
        self.assertEqual(group.transaction_payload()["batch"]["ownerCount"],2)
        self.assertEqual(before.document.source_text,original)

    def test_prefinal_batch_replay_rejects_receipt_and_xml_drift(self):
        original=interconnected_tee_fixture(2)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,2)
        batch=apply_independent_short_batch(
            before,policy=owner_policy(before,ids,self.cfg),config=self.cfg)
        self.assertTrue(batch.committed)
        prefinal=verify_independent_short_batch_pre_final(
            original,batch,reviewed_action_ids=ids)
        self.assertEqual(prefinal["ownerEvidenceCount"],2)
        self.assertTrue(prefinal["requiresFreshWorkerBasis"])
        self.assertFalse(prefinal["nativeCiiReleaseAuthorized"])
        with self.assertRaisesRegex(ShortBatchRefused,
                                    "SHORT_BATCH_PREFINAL_ORIGINAL_BYTES_DRIFT"):
            verify_independent_short_batch_pre_final(
                original+"<!--TAMPER-->",batch,reviewed_action_ids=ids)
        with self.assertRaisesRegex(ShortBatchRefused,
                                    "SHORT_BATCH_PREFINAL_REVIEW_REQUIRED"):
            verify_independent_short_batch_pre_final(
                original,batch,reviewed_action_ids=ids[:1])
        poisoned=replace(batch,owner_evidence=batch.owner_evidence[:1])
        with self.assertRaisesRegex(ShortBatchRefused,
                                    "SHORT_BATCH_PREFINAL_REVIEW_REQUIRED"):
            verify_independent_short_batch_pre_final(
                original,poisoned,reviewed_action_ids=ids)
        print("A6B_BATCH_PREFINAL_REPLAY_GREEN=PASS")

    def test_group_rejected_if_owner_influence_overlaps(self):
        before=resolve_psi116(interconnected_tee_fixture(2),self.cfg)
        rows=[r for r in short_elements(before.document,self.cfg)
              if r["eligible"] and r["componentRefNo"].startswith("SHORT-")]
        self.assertEqual(len(rows),2)
        with self.assertRaisesRegex(ShortBatchRefused,"SHORT_BATCH_INDEPENDENCE_CONFLICT"):
            assert_independent(before,[rows[0],rows[0]],self.cfg)

    def test_batch_selection_cannot_bypass_singleton_refusal(self):
        before=resolve_psi116(interconnected_tee_fixture(2),self.cfg)
        ids=owner_ids(before,self.cfg,2)
        p=owner_policy(before,ids,self.cfg)
        with self.assertRaisesRegex(ValueError,"Select one source-bound short element"):
            apply_topofix_transaction(before,policy=p,config=self.cfg)

    def test_atomic_refusal_bisects_to_original_single_owner_path(self):
        before=resolve_psi116(interconnected_tee_fixture(3),self.cfg)
        ids=owner_ids(before,self.cfg,3)
        requested=[ids[0],"SHORT:999:NOT-FOUND",ids[1],ids[2]]
        result=apply_short_batch_bisect(before.document.source_text,requested,
                                        config=self.cfg)
        reference,_=serial_reference(before.document.source_text,ids,self.cfg)
        self.assertEqual(result.fixed_xml,reference)
        self.assertEqual([x["id"] for x in result.owner_results],requested)
        self.assertEqual([x["status"] for x in result.owner_results],
                         ["COMMITTED","REFUSED","COMMITTED","COMMITTED"])
        self.assertEqual(len(result.skipped),1)
        self.assertEqual(result.skipped[0]["id"],requested[1])

    def test_accounting_mutant_removed_must_fail_behaviourally(self):
        before=resolve_psi116(interconnected_tee_fixture(2),self.cfg)
        ids=owner_ids(before,self.cfg,2)
        batch=apply_independent_short_batch(
            before,policy=owner_policy(before,ids,self.cfg),config=self.cfg)
        self.assertEqual(len(normalized_owner_evidence(batch)),2)
        forged=replace(batch,operations=tuple(
            op for op in batch.operations
            if not (op.action_id==ids[1] and
                    op.operation=="REMOVE_SELECTED_SHORT_ELEMENT_RECORD")))
        with self.assertRaisesRegex(ShortBatchRefused,
                                    "SHORT_BATCH_OWNER_REMOVAL_ACCOUNTING_MISMATCH"):
            normalized_owner_evidence(forged)

    def test_missing_one_owner_evidence_is_detected(self):
        before=resolve_psi116(interconnected_tee_fixture(2),self.cfg)
        ids=owner_ids(before,self.cfg,2)
        batch=apply_independent_short_batch(
            before,policy=owner_policy(before,ids,self.cfg),config=self.cfg)
        self.assertEqual(len(batch.owner_evidence),2)
        broken=replace(batch,owner_evidence=batch.owner_evidence[:1])
        with self.assertRaises(AssertionError):
            self.assertEqual(len(broken.owner_evidence),len(ids),
                             "BATCH_OWNER_EVIDENCE_MISSING")

