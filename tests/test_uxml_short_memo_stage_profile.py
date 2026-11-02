"""Source-bound one-owner paired native stage timing: memo OFF vs ON.

Run with PINNED XCU_UXML_ROOT and UXML_SHORT_MEMO_STAGE_PROFILE=1 only.
The two runs use THE SAME original path/bytes, policy and config and compare
full XML, transaction, validation, canonical operations and refusal evidence.
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

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import TransactionPolicy,apply_topofix_transaction
from psi116_topology_resolver.uxml_edit_ops import export_edit_ops,apply_edit_ops,compare_hub_patch
from psi116_topology_resolver.short_memo import memo_session,stats
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture

def phase(function,*args,**kwargs):
    t=time.perf_counter()
    return_value=function(*args,**kwargs)
    return return_value,round((time.perf_counter()-t)*1000,3)


class MemoStageProfile(unittest.TestCase):
    def test_one_source_660_records_full_direct_export_patch(self):
        if os.environ.get("UXML_SHORT_MEMO_STAGE_PROFILE")!="1":
            self.skipTest("UXML_SHORT_MEMO_STAGE_PROFILE=1 explicitly required")
        reader=Path(os.environ.get("XCU_UXML_ROOT",""))
        if not (reader/"tools"/"psi116-to-uxml.mjs").is_file():
            self.skipTest("XCU_UXML_ROOT required")
        cfg=ResolverConfig()
        with tempfile.TemporaryDirectory(prefix="short-memo-stage-") as temp:
            original=Path(temp)/"original.xml"
            source=interconnected_tee_fixture(60).encode("utf-8")
            original.write_bytes(source)
            out={}
            for enabled in (False,True):
                with memo_session("native-stage",enabled=enabled):
                    before,resolve_ms=phase(resolve_psi116,original,cfg)
                    rows,eligibility_ms=phase(short_elements,before.document,cfg)
                    row=next(r for r in rows if r["eligible"] and
                             r["componentRefNo"]=="SHORT-003")
                    request={k:row[k] for k in ("id","sourceSha256","nodeKeys")}
                    policy=TransactionPolicy(selected_action_ids=(row["id"],),
                        short_element_requests=(request,))
                    started=time.perf_counter()
                    direct,direct_ms=phase(apply_topofix_transaction,before,policy=policy,config=cfg)
                    xcu_start=time.perf_counter()
                    cli=subprocess.run(
                        ["node",str(reader/"tools"/"psi116-to-uxml.mjs"),str(original)],
                        cwd=reader,capture_output=True,text=True,timeout=120)
                    reader_ms=round((time.perf_counter()-xcu_start)*1000,3)
                    self.assertEqual(cli.returncode,0,cli.stderr)
                    uxml=json.loads(cli.stdout)
                    op,export_ms=phase(export_edit_ops,uxml,policy=policy,
                                      source_name=str(original),config=cfg)
                    patched,patch_ms=phase(apply_edit_ops,original,uxml,op,config=cfg)
                    differences,parity_ms=phase(compare_hub_patch,direct,patched)
                    self.assertEqual(differences,[])
                    self.assertTrue(direct.committed and patched.committed)
                    self.assertEqual(direct.fixed_xml,patched.fixed_xml)
                    record={
                        "enabled":enabled,"sourceResolveMs":resolve_ms,
                        "eligibilityMs":eligibility_ms,
                        "nativeDirectMs":direct_ms,"uxmlReaderCliMs":reader_ms,
                        "canonicalExportMs":export_ms,"canonicalApplyMs":patch_ms,
                        "parityMs":parity_ms,
                        "endToEndMs":round((time.perf_counter()-started)*1000,3),
                        "memoStats":stats(),
                        "bytes":patched.fixed_xml,
                        "transaction":patched.transaction_payload(),
                        "validation":patched.validation_payload(),
                        "canonicalOps":op["ops"],
                    }
                    out[enabled]=record
            for key in ("bytes","transaction","validation","canonicalOps"):
                self.assertEqual(out[False][key],out[True][key],key)
            self.assertEqual(original.read_bytes(),source)
            clean={enabled:{key:value for key,value in run.items()
                            if key not in {"bytes","transaction","validation","canonicalOps"}}
                   for enabled,run in out.items()}
            print("UXML_SHORT_MEMO_NATIVE_STAGE_COMPARE="+
                  json.dumps(clean,sort_keys=True))
