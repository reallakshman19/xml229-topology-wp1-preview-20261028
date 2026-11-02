"""A6b pinned XCU batch canonical witness qualification; opt-in, no new skips."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
from psi116_topology_resolver import ResolverConfig,resolve_psi116
from psi116_topology_resolver.short_batch import (
    apply_independent_short_batch,ShortBatchRefused)
from psi116_topology_resolver.short_batch_uxml import (
    qualify_short_batch_uxml,BATCH_UXML_WITNESS_SCHEMA)
from psi116_topology_resolver.uxml_edit_ops import UxmlPatchError
from test_short_batch_engine import owner_ids,owner_policy,serial_reference
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture


class CanonicalUxmlGroup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("A6B_ENGINE_QUAL")!="1":
            raise RuntimeError("Explicit A6B_ENGINE_QUAL=1 required")
        cls.reader=Path(os.environ["XCU_UXML_ROOT"])
        if not (cls.reader/"tools"/"psi116-to-uxml.mjs").is_file():
            raise RuntimeError("Pinned XCU_UXML_ROOT required")
        cls.cfg=ResolverConfig()

    def fixture(self,owners):
        ctx=tempfile.TemporaryDirectory(prefix="a6b-canonical-synthetic-")
        path=Path(ctx.name)/"original.xml"
        path.write_text(interconnected_tee_fixture(max(2,owners)),encoding="utf-8")
        direct=resolve_psi116(path,self.cfg)
        ids=owner_ids(direct,self.cfg,owners)
        self.assertEqual(len(ids),owners)
        policy=owner_policy(direct,ids,self.cfg)
        reader=subprocess.run(
            ["node",str(self.reader/"tools"/"psi116-to-uxml.mjs"),str(path)],
            cwd=self.reader,capture_output=True,text=True,timeout=120)
        self.assertEqual(reader.returncode,0,reader.stderr)
        return ctx,path,direct,ids,policy,json.loads(reader.stdout)

    def test_two_owner_real_source_ref_loss_canonical_and_direct_parity(self):
        ctx,path,before,ids,policy,uxml=self.fixture(2)
        try:
            original=path.read_bytes()
            direct,patched,witness=qualify_short_batch_uxml(
                path,uxml,policy=policy,config=self.cfg)
            self.assertEqual(direct.fixed_xml,patched.fixed_xml)
            self.assertEqual(witness["schema"],BATCH_UXML_WITNESS_SCHEMA)
            self.assertTrue(witness["lossContractChecked"])
            self.assertTrue(witness["originalSourceCompared"])
            self.assertEqual(witness["nativeVsUxmlParity"],"EQUAL")
            self.assertEqual(witness["ownerIds"],ids)
            self.assertEqual(len(witness["ops"]),2)
            self.assertEqual(len({x["sourceActionId"] for x in witness["ops"]}),2)
            self.assertEqual(path.read_bytes(),original)
            serial,_=serial_reference(before.document.source_text,ids,self.cfg)
            self.assertEqual(direct.fixed_xml,serial)
            print("A6B_CANONICAL_BATCH_GREEN="+json.dumps({
                "owners":2,"ops":len(witness["ops"]),
                "bytesEqual":True,"lossContractChecked":True,
                "nativeUxmlIndependent":True},sort_keys=True))
        finally:ctx.cleanup()

    def test_tampered_weight_source_ref_and_loss_refused(self):
        ctx,path,before,ids,policy,uxml=self.fixture(2)
        try:
            clean,_patched,_witness=qualify_short_batch_uxml(
                path,uxml,policy=policy,config=self.cfg)
            self.assertTrue(clean.committed)
            target=next(c for c in uxml["components"] if
                c["rawAttributes"]["psi116"].get("componentRefNo")=="FLAN-0")
            forged=deepcopy(uxml)
            row=next(c["rawAttributes"]["psi116"] for c in forged["components"]
                     if c["id"]==target["id"])
            row["weight"]=(row.get("weight") or 0)+999
            with self.assertRaises((ShortBatchRefused,UxmlPatchError)) as killed:
                qualify_short_batch_uxml(path,forged,policy=policy,config=self.cfg)
            print("A6B_CANONICAL_TAMPER_RED:"+type(killed.exception).__name__+":"+
                  str(killed.exception).split(":",1)[0])
            forged=deepcopy(uxml)
            target=next(c for c in forged["components"] if
                c["rawAttributes"]["psi116"].get("componentRefNo")=="SHORT-000")
            target["sourceRefs"][0]["fileSha256"]="0"*64
            with self.assertRaisesRegex(UxmlPatchError,"UXML_SOURCE_REF_SHA_MISMATCH"):
                qualify_short_batch_uxml(path,forged,policy=policy,config=self.cfg)
            print("A6B_CANONICAL_SOURCE_REF_RED:UXML_SOURCE_REF_SHA_MISMATCH")
            forged=deepcopy(uxml)
            self.assertTrue(isinstance(forged.get("lossContract"),list))
            ref=target["sourceRefs"][0]
            # Loss-contract refusal checked using EXACT original source path,
            # not an invented UXML record key. Any loss on a deleted owner is
            # a hard veto unless it is the permitted raw-only child disclosure.
            from psi116_topology_resolver.uxml_edit_ops import _source_record_paths
            original_paths=_source_record_paths(before.document.source_text,before)
            ref_key=next(iter(policy.short_element_requests[0]["nodeKeys"]))
            forged["lossContract"].append({
                "code":"SYNTHETIC_OWNER_PATH_UNREPRESENTED",
                "details":{"sourcePath":original_paths[ref_key]}})
            with self.assertRaisesRegex(UxmlPatchError,"UXML_LOSS_CONTRACT_FIELD_TOUCH"):
                qualify_short_batch_uxml(path,forged,policy=policy,config=self.cfg)
            print("A6B_CANONICAL_LOSS_RED:UXML_LOSS_CONTRACT_FIELD_TOUCH")
        finally:ctx.cleanup()

    def test_source_and_uxml_group_timing_5_20_and_89_like(self):
        # Full test deliberately runs only when the env gate requests it.
        # Native sequential benchmark elsewhere verifies 5/20/89-like byte
        # equality, so here verify once per group XCU canonical and output.
        for count in (5,20,32):
            ctx,path,before,ids,policy,uxml=self.fixture(count)
            try:
                t=time.perf_counter()
                direct,patched,witness=qualify_short_batch_uxml(
                    path,uxml,policy=policy,config=self.cfg)
                elapsed=round((time.perf_counter()-t)*1000,3)
                self.assertEqual(direct.fixed_xml,patched.fixed_xml)
                self.assertEqual(len(witness["ops"]),count)
                print("A6B_CANONICAL_GROUP_TIMING="+json.dumps({
                    "owners":count,"elapsedMs":elapsed,"bytesEqual":True,
                    "canonicalOps":len(witness["ops"])},sort_keys=True))
            finally:ctx.cleanup()
