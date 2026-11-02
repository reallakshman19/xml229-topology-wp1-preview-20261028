"""A6b negative owners/census tests: execution-backed red and green mutants.

No skipped tests. All mutants act on actual planner/writer/publication functions
and fail a real invariant assertion rather than comparing invented key tuples.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
import psi116_topology_resolver.short_batch as batch
from psi116_topology_resolver import ResolverConfig,resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from test_short_batch_engine import owner_ids,owner_policy,serial_reference
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture
from test_uxml_psi116_s1 import verified_synthetic
from test_port_policy import doc,node


def interacting_fixture():
    # TWO eligible source owners in ONE physical branch. Only grouping is
    # exercised here; they must never be grouped together.
    nodes=(
        node(10,"PIPE","P0",1,"0 0 0")+
        node(20,"PIPE","P0",2,"100 0 0")+
        node(-1,"GASK","SHORT-A",1,"100 0 0")+
        node(30,"RIGID","SHORT-A",2,"103 0 0")+
        node(-1,"FLAN","F0",1,"103 0 0")+
        node(40,"RIGID","F0",2,"189 0 0")+
        node(50,"PIPE","P1",1,"189 0 0")+
        node(60,"PIPE","P1",2,"300 0 0")+
        node(-1,"GASK","SHORT-B",1,"300 0 0")+
        node(70,"RIGID","SHORT-B",2,"303 0 0")+
        node(-1,"FLAN","F1",1,"303 0 0")+
        node(80,"RIGID","F1",2,"390 0 0")
    )
    return verified_synthetic(doc(nodes))


class ShortBatchSafetyMutants(unittest.TestCase):
    def setUp(self):self.cfg=ResolverConfig()

    def test_interacting_owner_planner_and_removed_footprint_mutant(self):
        before=resolve_psi116(interacting_fixture(),self.cfg)
        rows=[r for r in short_elements(before.document,self.cfg)
              if r["componentRefNo"] in ("SHORT-A","SHORT-B")]
        self.assertEqual(len(rows),2,[(r["id"],r["reason"]) for r in rows])
        self.assertTrue(all(r["eligible"] for r in rows),
                        [(r["id"],r["reason"]) for r in rows])
        ids=[r["id"] for r in rows]
        planned=batch.plan_short_groups(before,ids,self.cfg)
        self.assertEqual(planned,((ids[0],),(ids[1],)))
        print("A6B_MUTANT_GREEN:independence-planner=PASS")
        with patch.object(batch,"owner_footprint",return_value=frozenset()):
            broken=batch.plan_short_groups(before,ids,self.cfg)
            with self.assertRaises(AssertionError) as red:
                self.assertEqual(broken,planned,
                                 "BATCH_INDEPENDENCE_MUTANT_INTERACTING_TOGETHER")
        print("A6B_MUTANT_RED:independence-check-removed:AssertionError:"+
              str(red.exception).splitlines()[-1])
        # The atomic engine independently enforces overlap as a second gate.
        with self.assertRaisesRegex(batch.ShortBatchRefused,
                                    "SHORT_BATCH_INDEPENDENCE_CONFLICT"):
            batch.apply_independent_short_batch(
                before,policy=owner_policy(before,ids,self.cfg),config=self.cfg)

    def test_one_bad_inside_batch_isolated_by_bisect_unaffected_owners_equal_serial(self):
        original=interconnected_tee_fixture(4)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,4)
        bad=ids[1]
        genuine_batch=batch.apply_independent_short_batch
        genuine_single=batch._single_attempt
        failed_group_sizes=[]
        def refuse_group(source,*,policy,config):
            if bad in policy.selected_action_ids:
                failed_group_sizes.append(len(policy.selected_action_ids))
                raise batch.ShortBatchRefused("SYNTHETIC_REJECTED_GROUP")
            return genuine_batch(source,policy=policy,config=config)
        def refuse_bad(source,identifier,config):
            if identifier==bad:
                raise ValueError("SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED")
            return genuine_single(source,identifier,config)
        with patch.object(batch,"apply_independent_short_batch",side_effect=refuse_group),\
             patch.object(batch,"_single_attempt",side_effect=refuse_bad):
            result=batch.apply_short_batch_bisect(original,ids,config=self.cfg)
        ref,_=serial_reference(original,[i for i in ids if i!=bad],self.cfg)
        self.assertEqual(result.fixed_xml,ref)
        self.assertIn(4,failed_group_sizes,
                      "bisect must actually attempt the original bad group")
        self.assertIn(2,failed_group_sizes,
                      "bisect must recursively split that group")
        self.assertEqual([o["status"] for o in result.owner_results],
                         ["COMMITTED","REFUSED","COMMITTED","COMMITTED"])
        self.assertEqual(result.skipped[0]["reason"],
                         "SHORT_ELEMENT_RECONNECTION_NOT_QUALIFIED")
        print("A6B_MUTANT_GREEN:bisect-atomic-refusal=PASS")

    def test_rejected_partial_writer_cannot_be_accepted_as_whole_group(self):
        original=interconnected_tee_fixture(4)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,4)
        genuine=batch.apply_independent_short_batch
        attempts=[]
        def partial(source,*,policy,config):
            requested=tuple(policy.selected_action_ids)
            if len(requested)>1:
                attempts.append(requested)
                # ACTUAL partial writer: valid native singleton output,
                # but maliciously returned as a whole-group result.
                singleton=batch._single_attempt(
                    source.document.source_text,requested[0],config)
                return batch.IndependentShortBatchResult(
                    singleton.source_result,singleton.after_result,
                    singleton.policy,singleton.selected_actions,
                    singleton.operations,singleton.checks,
                    singleton.reject_reasons,singleton.fixed_xml,
                    singleton.resolver_config,
                    batch.normalized_owner_evidence(singleton))
            return genuine(source,policy=policy,config=config)
        with patch.object(batch,"apply_independent_short_batch",side_effect=partial):
            result=batch.apply_short_batch_bisect(original,ids,config=self.cfg)
        reference,_=serial_reference(original,ids,self.cfg)
        self.assertEqual(result.fixed_xml,reference)
        self.assertTrue(attempts)
        self.assertTrue(all(len(b["ids"])==1 for b in result.successful_batches),
                        "partial group must bisect; never publish a group")
        print("A6B_MUTANT_GREEN:commit-partial-group-refused-and-bisected=PASS")
        # Remove the ACTUAL two census guards, then run the SAME malicious
        # partial writer: it must return a receipt missing three owners and
        # the caller's real owner-list assertion must go RED.
        real_require=batch._require
        def missing_guards(value,code):
            if code in ("SHORT_BATCH_OWNER_EVIDENCE_CENSUS_MISMATCH",
                        "SHORT_BATCH_RUN_OWNER_CENSUS_MISMATCH"):
                return None
            return real_require(value,code)
        with patch.object(batch,"_require",side_effect=missing_guards),\
             patch.object(batch,"apply_independent_short_batch",side_effect=partial):
            broken=batch.apply_short_batch_bisect(original,ids,config=self.cfg)
        with self.assertRaises(AssertionError) as killed:
            self.assertEqual([o["id"] for o in broken.owner_results],ids,
                             "BATCH_COMMIT_PARTIAL_MUTANT_HAS_MISSING_OWNERS")
        print("A6B_MUTANT_RED:commit-partial-instead-of-bisect:AssertionError:"+
              str(killed.exception).splitlines()[-1])

    def test_missing_owner_evidence_and_accounting_drift_cause_bisect(self):
        original=interconnected_tee_fixture(3)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,3)
        real=batch.apply_independent_short_batch
        for name,mutate in (
            ("missing-owner",lambda tx:replace(
                tx,owner_evidence=tx.owner_evidence[:-1])),
            ("wrong-accounting",lambda tx:replace(
                tx,owner_evidence=(dict(tx.owner_evidence[0],
                                        removedWeight=999999),)+
                                  tx.owner_evidence[1:])),
        ):
            tried=[]
            def forged(source,*,policy,config):
                tx=real(source,policy=policy,config=config)
                tried.append(tuple(policy.selected_action_ids))
                return mutate(tx)
            with patch.object(batch,"apply_independent_short_batch",
                              side_effect=forged):
                outcome=batch.apply_short_batch_bisect(original,ids,
                                                       config=self.cfg)
            ref,_=serial_reference(original,ids,self.cfg)
            self.assertEqual(outcome.fixed_xml,ref)
            self.assertTrue(tried)
            self.assertTrue(all(len(group["ids"])==1
                                for group in outcome.successful_batches),
                            "corrupted batch evidence cannot be published")
            print("A6B_MUTANT_GREEN:"+name+"-refused-and-bisected=PASS")
            # Execute a named mutation of the REAL accounting gate.
            # The corrupted group receipt must then violate its own owner
            # evidence census, not an invented constant-vs-constant check.
            real_require=batch._require
            def bypass_census(value,code):
                if code=="SHORT_BATCH_OWNER_EVIDENCE_CENSUS_MISMATCH":
                    return None
                return real_require(value,code)
            with patch.object(batch,"_require",side_effect=bypass_census),\
                 patch.object(batch,"apply_independent_short_batch",
                              side_effect=forged):
                broken=batch.apply_short_batch_bisect(original,ids,
                                                       config=self.cfg)
            with self.assertRaises(AssertionError) as killed:
                for receipt in broken.successful_batches:
                    owners=receipt["transaction"]["batch"]["owners"]
                    self.assertEqual(len(owners),len(receipt["ids"]),
                                     "BATCH_"+name+"_ACCEPTED")
                    for owner in owners:
                        matched=next(r["evidence"] for r in broken.owner_results
                                     if r["id"]==owner["id"])
                        self.assertEqual(owner["removedWeight"],
                                         matched["removedWeight"],
                                         "BATCH_"+name+"_ACCEPTED")
            print("A6B_MUTANT_RED:"+name+":AssertionError:"+
                  str(killed.exception).splitlines()[-1])
