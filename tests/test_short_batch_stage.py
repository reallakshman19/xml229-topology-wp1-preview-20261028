"""A6b stage output guards without browser, pinned reader or Owner data."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_batch_stage import run_explicit_batch_job
from test_short_batch_engine import owner_ids,owner_policy,serial_reference
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture


def sidecars(folder):
    return {key:str(folder/(key+".json" if key!="fixed" else "fixed.xml"))
            for key in ("findings","plan","transaction","validation",
                        "fixed","lineage","handoff","postFindings","postPlan","status")}


class StageReceipt(unittest.TestCase):
    def test_direct_group_stage_pre_final_receipts_and_exact_bytes(self):
        with tempfile.TemporaryDirectory(prefix="a6b-stage-") as name:
            path=Path(name)/"original.xml"
            original=interconnected_tee_fixture(3)
            path.write_text(original,encoding="utf-8")
            before=resolve_psi116(path)
            ids=owner_ids(before,ResolverConfig(),3)
            policy=owner_policy(before,ids,ResolverConfig())
            paths=sidecars(Path(name))
            status=run_explicit_batch_job(str(path),None,ids,
                list(policy.short_element_requests),paths)
            self.assertTrue(status["committed"],status)
            self.assertEqual(status["hubParity"]["status"],"OFF")
            fixed=Path(paths["fixed"]).read_text(encoding="utf-8")
            sequential,_=serial_reference(original,ids,ResolverConfig())
            self.assertEqual(fixed,sequential)
            self.assertEqual(path.read_text(encoding="utf-8"),original)
            tx=json.loads(Path(paths["transaction"]).read_text())
            check=json.loads(Path(paths["validation"]).read_text())
            handoff=json.loads(Path(paths["handoff"]).read_text())
            self.assertEqual(tx["batch"]["ownerCount"],3)
            self.assertEqual(len(tx["batch"]["ownerRevisions"]),3)
            self.assertTrue(check["committed"])
            self.assertEqual(handoff["ownerEvidenceCount"],3)
            self.assertTrue(handoff["requiresFreshWorkerBasis"])
            self.assertFalse(handoff["nativeCiiReleaseAuthorized"])
            self.assertEqual(status["rejectReasons"],[])

    def test_refused_group_never_emits_corrected_xml(self):
        with tempfile.TemporaryDirectory(prefix="a6b-stage-refuse-") as name:
            path=Path(name)/"original.xml"
            path.write_text(interconnected_tee_fixture(2),encoding="utf-8")
            baseline=path.read_bytes()
            before=resolve_psi116(path)
            ids=owner_ids(before,ResolverConfig(),2)
            policy=owner_policy(before,ids,ResolverConfig())
            forged=list(policy.short_element_requests)
            forged[1]={**forged[1],"nodeKeys":["SYNTHETIC_FORGED_KEY"]}
            paths=sidecars(Path(name))
            status=run_explicit_batch_job(str(path),None,ids,forged,paths)
            self.assertFalse(status["committed"])
            self.assertTrue(status["rejectReasons"])
            self.assertFalse(Path(paths["fixed"]).exists())
            self.assertEqual(path.read_bytes(),baseline)
            self.assertEqual(status["appliedEditOps"],None)
            print("A6B_STAGE_REFUSED_NO_PARTIAL_XML=PASS")
