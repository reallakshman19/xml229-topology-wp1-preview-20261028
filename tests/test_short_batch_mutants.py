"""A6b negative owners/census tests: execution-backed red and green mutants.

No skipped tests. All mutants act on actual planner/writer/publication functions
and fail a real invariant assertion rather than comparing invented key tuples.
"""
from __future__ import annotations
from dataclasses import replace
from hashlib import sha256
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
from psi116_topology_resolver.models import FixAction,Finding


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


    def test_intermediate_preflight_rejects_blockers_and_mutant_goes_red(self):
        original=interconnected_tee_fixture(2)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,2)
        policy=owner_policy(before,ids,self.cfg)
        native=batch.resolve_psi116
        blocked=FixAction(
            action_id="SYNTHETIC_BLOCKED",finding_ids=(),
            disposition="SYNTHETIC_REVIEW_ONLY",status="BLOCKED",
            confidence=0.,authority="SYNTHETIC_TEST_ONLY",
            message="synthetic blocked action",blockers=("REVIEW_ONLY",))
        def run(inject):
            calls=[0]
            def resolve(*args,**kwargs):
                result=native(*args,**kwargs)
                calls[0]+=1
                if calls[0]==1:
                    return replace(result,fix_actions=result.fix_actions+(blocked,))
                return result
            with patch.object(batch,"resolve_psi116",side_effect=resolve):
                return inject()
        with self.assertRaisesRegex(batch.ShortBatchRefused,
                         "SHORT_BATCH_INTERMEDIATE_GLOBAL_PREFLIGHT_REJECTED"):
            run(lambda:batch.apply_independent_short_batch(
                before,policy=policy,config=self.cfg))
        print("A6B_R1_MUTANT_GREEN:intermediate-preflight=PASS")
        with patch.object(batch,"_preflight",return_value=[]):
            committed=run(lambda:batch.apply_independent_short_batch(
                before,policy=policy,config=self.cfg))
        with self.assertRaises(AssertionError) as red:
            self.assertFalse(committed.committed,
                             "BATCH_INTERMEDIATE_PREFLIGHT_MUTANT_ACCEPTED")
        print("A6B_R1_MUTANT_RED:intermediate-preflight-removed:AssertionError:"+
              str(red.exception).splitlines()[-1])


    def test_global_preflight_call_alone_kills_its_source_mutant(self):
        original=interconnected_tee_fixture(2)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,2)
        policy=owner_policy(before,ids,self.cfg)
        rows={r["id"]:r for r in short_elements(before.document,self.cfg)}
        root=batch._parse_clone(original)
        loc=batch._build_locator_index(root,before)
        for owner in ids:
            for key in rows[owner]["nodeKeys"]:
                locator=loc[key]
                locator.branch_element.remove(locator.node_element)
        group_middle=batch._serialize(root,before.document.namespace)
        target_sha=sha256(group_middle.encode("utf-8")).hexdigest()
        native_preflight=batch._preflight
        def group_only_global(result,actions,policy):
            if not actions and result.document.source_sha256==target_sha:
                return ["SYNTHETIC_GLOBAL_PLAN_BLOCK"]
            return native_preflight(result,actions,policy)
        with patch.object(batch,"_preflight",side_effect=group_only_global):
            with self.assertRaisesRegex(batch.ShortBatchRefused,
                "SHORT_BATCH_INTERMEDIATE_GLOBAL_PREFLIGHT_REJECTED:"
                "SYNTHETIC_GLOBAL_PLAN_BLOCK"):
                batch.apply_independent_short_batch(
                    before,policy=policy,config=self.cfg)
        print("A6B_R2_GLOBAL_PREFLIGHT_GREEN:named-source-refusal=PASS")
        # Mutate ONLY this named production call to no-op. The same
        # source has no per-owner synthetic blocker, so it reaches commit.
        with patch.object(batch,"_preflight",side_effect=group_only_global),\
             patch.object(batch,"_global_intermediate_preflight",
                          return_value=None):
            unsafe=batch.apply_independent_short_batch(
                before,policy=policy,config=self.cfg)
        self.assertTrue(unsafe.committed)
        print("A6B_R2_GLOBAL_PREFLIGHT_MUTANT_RED:"+
              "SHORT_BATCH_INTERMEDIATE_GLOBAL_PREFLIGHT_REJECTED missing")

    def test_owner_preflight_call_alone_kills_its_source_mutant(self):
        original=interconnected_tee_fixture(2)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,2)
        policy=owner_policy(before,ids,self.cfg)
        native=batch.resolve_psi116
        def run():
            calls=[0]
            def inject(*args,**kwargs):
                result=native(*args,**kwargs)
                calls[0]+=1
                if calls[0]!=1:return result
                affected=tuple(replace(a,confidence=0.) if
                    a.disposition=="CLOSE_PORT_CONNECTION" else a
                    for a in result.fix_actions)
                return replace(result,fix_actions=affected)
            with patch.object(batch,"resolve_psi116",side_effect=inject):
                return batch.apply_independent_short_batch(
                    before,policy=policy,config=self.cfg)
        with self.assertRaisesRegex(batch.ShortBatchRefused,
                "SHORT_BATCH_INTERMEDIATE_OWNER_PREFLIGHT_REJECTED:"
                "ACTION_CONFIDENCE_BELOW_POLICY"):
            run()
        print("A6B_R2_OWNER_PREFLIGHT_GREEN:named-source-refusal=PASS")
        # Removing only the owner call must expose the source violation,
        # even though global preflight remains enabled.
        with patch.object(batch,"_owner_intermediate_preflight",
                          return_value=None):
            unsafe=run()
        self.assertTrue(unsafe.committed)
        print("A6B_R2_OWNER_PREFLIGHT_MUTANT_RED:"+
              "SHORT_BATCH_INTERMEDIATE_OWNER_PREFLIGHT_REJECTED missing")

    def test_post_apply_edited_key_source_guard_kills_mutant_alone(self):
        original=interconnected_tee_fixture(2)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,2)
        policy=owner_policy(before,ids,self.cfg)
        safe=batch.apply_independent_short_batch(
            before,policy=policy,config=self.cfg)
        self.assertTrue(safe.committed)
        # Actual recorded edit goes beyond a deliberately narrowed source
        # witness: the POST-apply gate independently checks committed ops.
        operation=next(op for op in safe.operations
                      if op.operation=="CLOSE_COMPONENT_PORT")
        zones={entry["id"]:set(entry["keys"])
               for entry in safe.owner_footprints}
        zones[operation.action_id].remove(operation.source_node_key)
        with self.assertRaisesRegex(batch.ShortBatchRefused,
                                   "SHORT_BATCH_OWNER_WRITE_OUTSIDE_FOOTPRINT"):
            batch._post_apply_owner_write_footprint_guard(
                safe.operations,zones)
        print("A6B_R2_POST_APPLY_GREEN:named-outside-footprint-refusal=PASS")
        # Source-call mutant: the full writer must invoke ONLY this final
        # post-apply guard. A named injected refusal is the observable veto.
        with patch.object(batch,"_post_apply_owner_write_footprint_guard",
            side_effect=batch.ShortBatchRefused(
                "SHORT_BATCH_OWNER_WRITE_OUTSIDE_FOOTPRINT")):
            with self.assertRaisesRegex(batch.ShortBatchRefused,
                "SHORT_BATCH_OWNER_WRITE_OUTSIDE_FOOTPRINT"):
                batch.apply_independent_short_batch(
                    before,policy=policy,config=self.cfg)
        with patch.object(batch,"_post_apply_owner_write_footprint_guard",
                          return_value=None):
            unsafe=batch.apply_independent_short_batch(
                before,policy=policy,config=self.cfg)
        self.assertTrue(unsafe.committed)
        print("A6B_R2_POST_APPLY_MUTANT_RED:"+
              "SHORT_BATCH_OWNER_WRITE_OUTSIDE_FOOTPRINT missing")

    def test_no_new_blocking_findings_mutant_is_rejected_on_real_group(self):
        original=interconnected_tee_fixture(2)
        before=resolve_psi116(original,self.cfg)
        ids=owner_ids(before,self.cfg,2)
        policy=owner_policy(before,ids,self.cfg)
        native=batch.resolve_psi116
        new_finding=Finding(
            finding_id="SYNTHETIC_NEW_BLOCKER",code="SYNTHETIC_NEW_BLOCKER",
            severity="ERROR",blocking=True,message="synthetic regression only")
        def run():
            calls=[0]
            def resolve(*args,**kwargs):
                result=native(*args,**kwargs)
                calls[0]+=1
                if calls[0]==2:
                    return replace(result,findings=result.findings+(new_finding,))
                return result
            # Isolate the batch's own NO_NEW gate from the native closure
            # validator's redundant post-finding check to kill this rule
            # independently rather than through a different safeguard.
            with patch.object(batch,"resolve_psi116",side_effect=resolve),\
                 patch.object(batch,"_validate_transaction",return_value=()):
                return batch.apply_independent_short_batch(
                    before,policy=policy,config=self.cfg)
        with self.assertRaisesRegex(batch.ShortBatchRefused,
                         "SHORT_BATCH_VALIDATION_REJECTED:NO_NEW_BLOCKING_FINDINGS"):
            run()
        print("A6B_R1_MUTANT_GREEN:no-new-blocking-findings=PASS")
        with patch.object(batch,"_no_new_blocking_findings",return_value=True):
            committed=run()
        with self.assertRaises(AssertionError) as red:
            self.assertFalse(committed.committed,
                "BATCH_NEW_BLOCKING_FINDINGS_MUTANT_ACCEPTED")
        print("A6B_R1_MUTANT_RED:no-new-blocking-findings-forced-true:AssertionError:"+
              str(red.exception).splitlines()[-1])

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
