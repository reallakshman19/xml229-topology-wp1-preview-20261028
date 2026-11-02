"""Option C short-drop memo safety, isolation, refusal and mutation falsifiers.

Default suite is fast and runs without the pinned XCU reader. The explicit
UXML_SHORT_MEMO_EQUIVALENCE=1 suite runs 5+20 sequential original-authority
transactions with memo forced OFF and ON, including full byte/receipt/refusal
equality. Synthetic interconnected TEE branches only.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver import short_memo as memo
from psi116_topology_resolver.uxml_edit_ops import (
    export_edit_ops, apply_edit_ops, compare_hub_patch,
)
from test_short_elements import fixture
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture


def selected_request(source):
    cfg = ResolverConfig()
    original = resolve_psi116(source, cfg)
    row = next(r for r in short_elements(original.document, cfg) if
               r["eligible"] and r["componentRefNo"] == "SHORT")
    request = {k: row[k] for k in ("id", "sourceSha256", "nodeKeys")}
    return original, TransactionPolicy(
        selected_action_ids=(row["id"],), short_element_requests=(request,)), cfg


def check_refusal(source, policy, cfg):
    try:
        result=apply_topofix_transaction(resolve_psi116(source,cfg),policy=policy,config=cfg)
    except Exception as exc:
        return type(exc).__name__+":"+str(exc)
    return "COMMITTED" if result.committed else (
        "REFUSED:"+json.dumps(result.reject_reasons))


class ShortMemoSafety(unittest.TestCase):
    def setUp(self):
        memo.clear_memo()
    def tearDown(self):
        memo.clear_memo()

    def test_same_bytes_new_path_reuses_post_closure_analysis_with_exact_receipt_path(self):
        source=fixture()
        cfg=ResolverConfig()
        with memo.memo_session("rewritten-source-path"):
            before=resolve_psi116(source,cfg,source_name="/synthetic/before.xml.topofix")
            after=resolve_psi116(source,cfg,source_name="/synthetic/new-revision.xml")
            self.assertEqual(before.document.source_text,after.document.source_text)
            self.assertEqual(after.document.source_path,"/synthetic/new-revision.xml")
            self.assertEqual(before.findings,after.findings)
            self.assertEqual(before.fix_actions,after.fix_actions)
            self.assertGreaterEqual(memo.stats().get("source_resolve_hit",0),1)
        direct=resolve_psi116(source,cfg,source_name="/synthetic/new-revision.xml")
        self.assertEqual(after,direct,"source path rebind must equal independent parser/analyzer")

    def test_one_owner_memo_is_exact_and_deep_copied(self):
        source = fixture()
        before, policy, cfg=selected_request(source)
        with memo.memo_session("native-1"):
            first=apply_topofix_transaction(before,policy=policy,config=cfg)
            second=apply_topofix_transaction(before,policy=policy,config=cfg)
            self.assertTrue(first.committed)
            self.assertEqual(first.fixed_xml, second.fixed_xml)
            self.assertEqual(first.transaction_payload(), second.transaction_payload())
            self.assertEqual(first.validation_payload(), second.validation_payload())
            self.assertIsNot(first, second)
            self.assertGreaterEqual(memo.stats().get("transaction_hit",0),1)
            self.assertTrue(first.checks[0].details)
            original=second.checks[0].details.copy()
            second.checks[0].details["SYNTHETIC_MUTATION"]="forged"
            again=apply_topofix_transaction(before,policy=policy,config=cfg)
            self.assertEqual(again.checks[0].details,original)
            self.assertNotIn("SYNTHETIC_MUTATION", again.checks[0].details)

    def test_exact_policy_and_source_changes_refuse_even_with_populated_cache(self):
        source=fixture()
        before,policy,cfg=selected_request(source)
        forged_policy=TransactionPolicy(
            selected_action_ids=policy.selected_action_ids,
            short_element_requests=({**policy.short_element_requests[0],
                                     "nodeKeys":["FORGED:SOURCE_KEY"]},))
        changed=source.replace("</Branch>","<!-- synthetic-byte-drift --></Branch>",1)
        self.assertNotEqual(changed,source)
        with memo.memo_session("native-source-and-policy"):
            self.assertTrue(apply_topofix_transaction(before,policy=policy,config=cfg).committed)
            self.assertIn("WITNESS_DRIFT",check_refusal(source,forged_policy,cfg))
            self.assertIn("SOURCE_DRIFT",check_refusal(changed,policy,cfg))

    def test_mutants_key_without_policy_or_bytes_are_killed(self):
        source=fixture()
        before,policy,cfg=selected_request(source)
        forged=TransactionPolicy(
            selected_action_ids=policy.selected_action_ids,
            short_element_requests=({**policy.short_element_requests[0],
                                     "nodeKeys":["FORGED:SOURCE_KEY"]},))
        genuine=memo._key

        # Policy omission is a transaction-key mutant. Its control commits,
        # but a forged nodeKey witness must be independently refused.
        with memo.memo_session("policy-key-control"):
            self.assertTrue(apply_topofix_transaction(
                before,policy=policy,config=cfg).committed)
            with self.assertRaisesRegex(ValueError,"WITNESS_DRIFT"):
                apply_topofix_transaction(before,policy=forged,config=cfg)
        with memo.memo_session("policy-key-mutant"):
            with patch.object(memo,"_key",
                              side_effect=lambda *a,**k:
                                  genuine(*a,**k)[:3]+("",)+genuine(*a,**k)[4:]):
                self.assertTrue(apply_topofix_transaction(
                    before,policy=policy,config=cfg).committed)
                with self.assertRaisesRegex(AssertionError,"ValueError not raised"):
                    with self.assertRaisesRegex(ValueError,"WITNESS_DRIFT"):
                        apply_topofix_transaction(before,policy=forged,config=cfg)
                print("MEMO_MUTANT_KILLED:memo-key-ignores-policy")

        # The old bytes mutant inadvertently poisoned *intermediate* source
        # resolves in its very first native transaction: the post-removal
        # candidate and post-closure candidate collided with the original
        # under a globally byte-blind key, so reconnection rejected before
        # the stale-source assertion. Use two different independently
        # eligible short owners instead of a forged policy for another source.
        first_xml=interconnected_tee_fixture(1)
        second_xml=interconnected_tee_fixture(2)
        self.assertNotEqual(first_xml,second_xml)
        first_state=resolve_psi116(first_xml,cfg)
        second_state=resolve_psi116(second_xml,cfg)
        for state,ref_no in ((first_state,"SHORT-000"),
                             (second_state,"SHORT-001")):
            row=next(r for r in short_elements(state.document,cfg)
                     if r["componentRefNo"]==ref_no)
            self.assertTrue(row["eligible"],ref_no)
            request={k:row[k] for k in ("id","sourceSha256","nodeKeys")}
            independent_policy=TransactionPolicy(
                selected_action_ids=(row["id"],),
                short_element_requests=(request,))
            independent=apply_topofix_transaction(
                state,policy=independent_policy,config=cfg)
            self.assertTrue(independent.committed,
                            (ref_no,independent.reject_reasons))
        with memo.memo_session("byte-key-control"):
            self.assertEqual(resolve_psi116(first_xml,cfg).document.source_text,
                             first_xml)
            self.assertEqual(resolve_psi116(second_xml,cfg).document.source_text,
                             second_xml)
        with memo.memo_session("byte-key-mutant"):
            def ignore_source_bytes(*args,**kwargs):
                key=genuine(*args,**kwargs)
                return key[:2]+("",)+key[3:]
            with patch.object(memo,"_key",side_effect=ignore_source_bytes):
                self.assertEqual(resolve_psi116(first_xml,cfg).document.source_text,
                                 first_xml)
                second=resolve_psi116(second_xml,cfg)
                # A real mutation kill: the production invariant assertion
                # fails with the mutated key, but passes in the control above.
                with self.assertRaisesRegex(AssertionError,
                                            "SOURCE_BYTES_CACHE_COLLISION"):
                    self.assertEqual(second.document.source_text,second_xml,
                                     "SOURCE_BYTES_CACHE_COLLISION")
                self.assertGreaterEqual(
                    memo.stats().get("source_resolve_hit",0),1)
                print("MEMO_MUTANT_KILLED:memo-key-ignores-input-bytes")

    def test_mutants_no_deepcopy_and_no_clear_are_killed(self):
        source=fixture()
        before,policy,cfg=selected_request(source)
        genuine=memo.deepcopy
        with memo.memo_session("copy-mutation"):
            apply_topofix_transaction(before,policy=policy,config=cfg)
            with patch.object(memo,"deepcopy",side_effect=lambda value:value):
                cached=apply_topofix_transaction(before,policy=policy,config=cfg)
                cached.checks[0].details["SYNTHETIC_MUTATION"]="poisoned"
                killed=False
                try:
                    next_result=apply_topofix_transaction(before,policy=policy,config=cfg)
                    self.assertNotIn("SYNTHETIC_MUTATION",next_result.checks[0].details)
                except AssertionError:
                    killed=True
                self.assertTrue(killed,"no-deepcopy mutation must poison cached evidence")
                print("MEMO_MUTANT_KILLED:shared-result-no-deepcopy")
        memo.start_memo("CANCEL_ERROR_SCOPE")
        apply_topofix_transaction(before,policy=policy,config=cfg)
        self.assertTrue(memo.stats())
        with patch.object(memo,"clear_memo",side_effect=lambda:None):
            memo.clear_memo()
            killed=False
            try:self.assertEqual(memo.stats(),{})
            except AssertionError:killed=True
            self.assertTrue(killed,"no-clear mutation must leave authority cache live")
            print("MEMO_MUTANT_KILLED:cancel-error-no-clear")
        memo.clear_memo()
        self.assertEqual(memo.stats(),{})

    def test_bounded_cache_and_one_owner_rule(self):
        source=fixture()
        before,policy,cfg=selected_request(source)
        two=TransactionPolicy(
            selected_action_ids=policy.selected_action_ids+policy.selected_action_ids,
            short_element_requests=policy.short_element_requests+policy.short_element_requests)
        with memo.memo_session("one-owner-only"):
            apply_topofix_transaction(before,policy=policy,config=cfg)
            with self.assertRaisesRegex(ValueError,"Select one source-bound short element"):
                apply_topofix_transaction(before,policy=two,config=cfg)
        self.assertEqual(memo.stats(),{})

    def test_explicit_five_and_twenty_owner_memo_equivalence(self):
        if os.environ.get("UXML_SHORT_MEMO_EQUIVALENCE") != "1":
            self.skipTest("UXML_SHORT_MEMO_EQUIVALENCE=1 and pinned reader required")
        reader=Path(os.environ.get("XCU_UXML_ROOT",""))
        if not (reader/"tools"/"psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned XCU_UXML_ROOT required")
        cfg=ResolverConfig()
        for count in (5,20):
            # Four identical sources for on/off trials, no private data.
            base=interconnected_tee_fixture(60).encode("utf-8")
            choices=[r["id"] for r in short_elements(
                resolve_psi116(base.decode("utf-8"),cfg).document,cfg)
                if r["componentRefNo"].startswith("SHORT-") and r["eligible"]]
            self.assertEqual(len(choices),60)
            selected=choices[3:3+count]
            tracks={}
            for enabled in (False,True):
                with tempfile.TemporaryDirectory(prefix="short-memo-equal-") as tmp:
                    source=Path(tmp)/"source.xml"; source.write_bytes(base)
                    outcomes=[]
                    started=time.perf_counter()
                    with memo.memo_session("selected-"+str(count),enabled=enabled):
                        for identifier in selected:
                            old=source.read_bytes()
                            cli=subprocess.run(
                                ["node",str(reader/"tools"/"psi116-to-uxml.mjs"),str(source)],
                                cwd=reader,capture_output=True,text=True,timeout=120)
                            self.assertEqual(cli.returncode,0,cli.stderr)
                            uxml=json.loads(cli.stdout)
                            before=resolve_psi116(source,cfg)
                            row=next(r for r in short_elements(before.document,cfg)
                                     if r["id"]==identifier)
                            self.assertTrue(row["eligible"],identifier)
                            request={k:row[k] for k in ("id","sourceSha256","nodeKeys")}
                            policy=TransactionPolicy(selected_action_ids=(identifier,),
                                                     short_element_requests=(request,))
                            direct=apply_topofix_transaction(before,policy=policy,config=cfg)
                            canonical=export_edit_ops(uxml,policy=policy,
                                                      source_name=str(source),config=cfg)
                            patched=apply_edit_ops(source,uxml,canonical,config=cfg)
                            self.assertTrue(direct.committed and patched and patched.committed)
                            self.assertEqual(compare_hub_patch(direct,patched),[])
                            self.assertEqual(direct.fixed_xml,patched.fixed_xml)
                            self.assertEqual(source.read_bytes(),old)
                            txn=patched.transaction_payload()
                            # Temporary-directory paths are distinct between
                            # ON/OFF invocations. Only the chosen file path
                            # varies, not any source bytes or authority proof.
                            txn["source"]["path"]="<synthetic-source>"
                            outcomes.append({
                                "xml":patched.fixed_xml,
                                "txn":txn,
                                "validation":patched.validation_payload(),
                                "ops":canonical["ops"],
                                "refusalForForgedPolicy":check_refusal(
                                    patched.fixed_xml,TransactionPolicy(
                                        selected_action_ids=(identifier,),
                                        short_element_requests=({**request,
                                            "nodeKeys":["FORGED_KEY"]},)),cfg),
                            })
                            source.write_bytes(patched.fixed_xml.encode("utf-8"))
                        counters=memo.stats()
                    tracks[enabled]={"outcomes":outcomes,
                                     "elapsedSeconds":round(time.perf_counter()-started,4),
                                     "memoStats":counters}
            self.assertEqual(tracks[True]["outcomes"],tracks[False]["outcomes"])
            print("UXML_SHORT_MEMO_EQUIVALENT_"+str(count)+"="+json.dumps({
                "owners":count,"memoOffSeconds":tracks[False]["elapsedSeconds"],
                "memoOnSeconds":tracks[True]["elapsedSeconds"],
                "memoStats":tracks[True]["memoStats"],
                "byteAndEvidenceEqual":True},sort_keys=True))
