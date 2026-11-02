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
        changed=source.replace("</Branch>","<!-- byte-mutation --></Branch>",1)
        genuine=memo._key
        for label,alter,request,expected in [
            ("memo-key-ignores-policy",lambda key:key[:3]+("",)+key[4:],
             (before,forged),"WITNESS_DRIFT"),
            ("memo-key-ignores-input-bytes",lambda key:key[:2]+("",)+key[3:],
             (resolve_psi116(changed,cfg),policy),"SOURCE_DRIFT"),
        ]:
            with self.subTest(label=label):
                with memo.memo_session("mutant-key-"+label):
                    self.assertTrue(apply_topofix_transaction(
                        before,policy=policy,config=cfg).committed)
                    value,mismatched=request
                    with self.assertRaisesRegex(ValueError,expected):
                        apply_topofix_transaction(value,policy=mismatched,config=cfg)
                with memo.memo_session("mutant-key-"+label):
                    with patch.object(memo,"_key",side_effect=lambda *a,**k:alter(genuine(*a,**k))):
                        self.assertTrue(apply_topofix_transaction(
                            before,policy=policy,config=cfg).committed)
                        value,mismatched=request
                        killed=False
                        try:
                            with self.assertRaisesRegex(ValueError,expected):
                                apply_topofix_transaction(value,policy=mismatched,config=cfg)
                        except AssertionError:
                            killed=True
                        self.assertTrue(killed,label+" mutant must make refusal test fail")
                        print("MEMO_MUTANT_KILLED:"+label)

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
                            outcomes.append({
                                "xml":patched.fixed_xml,
                                "txn":patched.transaction_payload(),
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
