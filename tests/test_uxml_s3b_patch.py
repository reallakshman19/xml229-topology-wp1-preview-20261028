"""S3B synthetic original-byte InputXML patch, named refusals, strict XCU reread."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "converters"))
from psi116_topology_resolver.transaction import TransactionPolicy
from psi116_topology_resolver.uxml_adapter import (
    resolve_from_uxml, resolve_inputxml_run_from_uxml,
)
from psi116_topology_resolver.uxml_patch_inputxml import InputXmlPatchError, patch_inputxml


class InputXmlS3BPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xcu = Path(os.environ.get("XCU_UXML_ROOT") or "/nonexistent")
        if not (cls.xcu / "tools" / "inputxml-to-uxml.mjs").is_file():
            raise unittest.SkipTest("Requires exact pinned external XCU reader")

    def read(self, file: Path) -> dict:
        cmd = ["node", str(self.xcu/"tools/inputxml-to-uxml.mjs"),str(file)]
        p = subprocess.run(cmd,cwd=self.xcu,capture_output=True,text=True,timeout=45)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        return json.loads(p.stdout)

    def synthetic_source(self) -> str:
        """Five physical pipe segments, one nonadjacent coincident source node.

        Source is derived from the real Workspace InputXML synthetic fixture's
        PIPINGELEMENT lexical template. No source SIF/BEND is manufactured.
        Different source REF_NO values keep distinct pipe occurrences so the
        unchanged resolver can authorize a same-route nonadjacent alias.
        """
        src=(self.xcu/"tests/fixtures/uxml-s3-synthetic.workspace.input.xml").read_text()
        elements=re.findall(r"<PIPINGELEMENT\b.*?</PIPINGELEMENT>",src,re.S)
        self.assertEqual(len(elements),6)
        template=elements[5]
        coords=[
            (10,20,(0,0,0),(100,0,0)),
            (20,30,(100,0,0),(150,100,0)),
            (30,35,(150,100,0),(200,50,0)),
            (35,40,(200,50,0),(100,0,0)),
            (40,50,(100,0,0),(300,0,0)),
        ]
        generated=[]
        for ix,(start,end,p,q) in enumerate(coords):
            edge=template
            attrs={
                "FROM_NODE":f"{start:.6f}",
                "TO_NODE":f"{end:.6f}",
                **{f"FROM_{axis}":f"{value:.6f}" for axis,value in zip("XYZ",p)},
                **{f"TO_{axis}":f"{value:.6f}" for axis,value in zip("XYZ",q)},
                **{f"DELTA_{axis}":f"{value:.6f}" if value else "-1.010100"
                   for axis,value in zip("XYZ",(q[axis]-p[axis] for axis in range(3)))},
            }
            for field,val in attrs.items():
                edge,replacements=re.subn(
                    r'\b'+field+r'="[^"]*"',
                    lambda match, field=field,val=val:field+'="'+val+'"',
                    edge,count=1)
                self.assertEqual(replacements,1,field)
            edge=edge.replace("FROM_NAME=\"RESTART\"","FROM_NAME=\"\"").replace(
                "TO_NAME=\"RESTART-END\"","TO_NAME=\"\"")
            edge=edge.replace(' NAME="RESTART-END"',f' NAME="PIPE-{ix}"')
            edge=edge.replace(" LINE_ID=\"S3-RESTART\"",
                              f' LINE_ID="S3B-ALIAS" REF_NO="SEG-{ix}"')
            generated.append(edge)
        start=src.index("<PIPINGELEMENT")
        end=src.index("</PIPINGMODEL>")
        header=src[:start].replace('NUMELT="6"','NUMELT="5"')
        header=header.replace('NUMBEND="1"','NUMBEND="0"')
        header=header.replace('NUMISECT="1"','NUMISECT="0"')
        return header+"\n".join(generated)+"\n"+src[end:]

    def fixture(self, base: Path):
        original=base/"original.input.xml"
        original.write_bytes(self.synthetic_source().encode("utf8"))
        hub=self.read(original)
        result=resolve_from_uxml(hub)
        aliases=[a for a in result.fix_actions
                 if a.disposition=="ALIAS_COINCIDENT_NODE" and
                 a.status=="PROPOSED" and not a.blockers]
        self.assertEqual(len(aliases),1,
                         [(a.disposition,a.status,a.message) for a in result.fix_actions])
        alias=aliases[0]
        self.assertEqual((alias.owner_node_number,alias.absorbed_node_numbers),(20,(40,)))
        node_by_key={r.key:r for branch in result.document.branches for r in branch.nodes}
        finding_by_id={f.finding_id:f for f in result.findings}
        keys=sorted({key for fid in alias.finding_ids
                     for key in finding_by_id[fid].node_keys})
        targets=sorted({original_key for key in keys
                        for original_key in node_by_key[key].inputxml_record_keys})
        self.assertTrue(targets)
        policy=json.loads(json.dumps(asdict(TransactionPolicy(
            selected_action_ids=(alias.action_id,)))))
        payload={"schema":"uxml-edit-ops/v1","sourceFormat":"INPUT_XML",
                 "fileSha256":hub["sources"][0]["hash"],"policy":policy,
                 "ops":[{"opId":"UXML-OP-"+alias.action_id,
                         "kind":"ALIAS_COINCIDENT_NODE",
                         "sourceActionId":alias.action_id,
                         "fileSha256":hub["sources"][0]["hash"],
                         "targets":targets,
                         "params":[dict(x) for x in alias.proposed_changes]}]}
        return original,hub,payload

    def run_cli(self, original: Path, hub: dict, payload: dict, base: Path):
        hub_path=base/"hub.json"
        ops_path=base/"ops.json"
        output=base/"fixed.input.xml"
        validation=base/"validation.json"
        hub_path.write_text(json.dumps(hub),encoding="utf8")
        ops_path.write_text(json.dumps(payload),encoding="utf8")
        cmd=[sys.executable,"-m","converters.psi116_topology_resolver.uxml_patch_inputxml",
             str(original),str(ops_path),"--uxml",str(hub_path),
             "--xcu-root",str(self.xcu),"--output",str(output),
             "--validation",str(validation)]
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=60)
        return p,output,validation

    def test_approved_alias_patch_is_byte_local_and_reread_all_checks_pass(self):
        with tempfile.TemporaryDirectory(prefix="uxml-s3b-yes-") as td:
            base=Path(td)
            original,hub,payload=self.fixture(base)
            prior=original.read_bytes()
            patched,report=patch_inputxml(original,hub,payload,self.xcu)
            self.assertNotEqual(patched,prior)
            self.assertEqual(report["summary"]["blockingFailureCount"],0)
            self.assertEqual(report["summary"]["passedCheckCount"],
                             report["summary"]["checkCount"])
            self.assertEqual(report["editCount"],2)
            self.assertEqual(report["editedOriginalRecords"],[3,4])
            p,out,validation=self.run_cli(original,hub,payload,base)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertEqual(p.stdout.strip(),"EQUAL")
            self.assertEqual(out.read_bytes(),patched)
            self.assertEqual(json.loads(validation.read_text()),json.loads(json.dumps(report)))
            self.assertEqual(original.read_bytes(),prior,"original must never be overwritten")
            # Exactly two source attributes carry physical node 40 across a route.
            self.assertEqual(patched,prior.replace(
                b'TO_NODE="40.000000"',b'TO_NODE="20.000000"').replace(
                b'FROM_NODE="40.000000"',b'FROM_NODE="20.000000"'))
            before=re.findall(rb"<PIPINGELEMENT\b.*?</PIPINGELEMENT>",prior,re.S)
            after=re.findall(rb"<PIPINGELEMENT\b.*?</PIPINGELEMENT>",patched,re.S)
            self.assertEqual(len(before),len(after))
            self.assertEqual(before[:3],after[:3],"every untouched record is byte-identical")
            self.assertNotEqual(before[3:],after[3:])
            self.assertIn("SELECTED_FINDINGS_RESOLVED",
                          [c["code"] for c in report["checks"]])
            fresh=base/"fresh.input.xml"
            fresh.write_bytes(patched)
            new_hub=self.read(fresh)
            later=resolve_from_uxml(new_hub)
            self.assertFalse(any(f.code=="COINCIDENT_NODE_ALIAS_CANDIDATE"
                                 for f in later.findings))

    def test_named_refusals_never_emit_any_output_file(self):
        with tempfile.TemporaryDirectory(prefix="uxml-s3b-no-") as td:
            root=Path(td)
            original,hub,payload=self.fixture(root)
            immutable=original.read_bytes()
            variants=[]
            altered=deepcopy(payload)
            altered["fileSha256"]="0"*64
            variants.append(("wrong-envelope-sha",hub,altered,original,
                             "INPUT_XML_FILE_SHA256_MISMATCH"))
            altered=deepcopy(payload)
            altered["ops"][0]["fileSha256"]="0"*64
            variants.append(("wrong-op-sha",hub,altered,original,
                             "INPUT_XML_OP_ID_OR_SHA_INVALID"))
            altered=deepcopy(payload)
            altered["ops"][0]["targets"][0]="E987:F10:T20"
            variants.append(("unknown-record",hub,altered,original,
                             "INPUT_XML_UNKNOWN_RECORD_KEY"))
            altered=deepcopy(payload)
            altered["policy"]["minimum_confidence"]=0
            variants.append(("widen-threshold",hub,altered,original,
                             "UXML_POLICY_WIDENING_REFUSED"))
            altered=deepcopy(payload)
            altered["policy"]["require_no_blocking_plan_actions"]=False
            variants.append(("disable-blocking",hub,altered,original,
                             "UXML_POLICY_WIDENING_REFUSED"))
            altered=deepcopy(payload)
            altered["ops"][0]["kind"]="REVIEW_CONNECTION"
            variants.append(("review-only",hub,altered,original,
                             "INPUT_XML_REVIEW_ONLY_OR_UNSUPPORTED_ACTION"))
            altered=deepcopy(hub)
            altered["lossContract"].append({
                "details":{"path":"/CAESARII/PIPINGMODEL/PIPINGELEMENT[3]",
                           "field":"@TO_NODE","raw":"40.000000"}})
            variants.append(("loss-field",altered,payload,original,
                             "INPUT_XML_LOSS_CONTRACT_FIELD_TOUCH"))
            # Forging only a UXML component source ref must fail original proof.
            altered=deepcopy(hub)
            altered["components"][2]["sourceRefs"][0]["recordKey"]="E999:F21:T31"
            variants.append(("tampered-record-ref",altered,payload,original,
                             "INPUT_XML_COMPONENT_SOURCE_REF_MISMATCH"))
            changed=root/"tampered.input.xml"
            changed.write_bytes(immutable.replace(
                b'FROM_NODE="40.000000"',b'FROM_NODE="41.000000"'))
            variants.append(("stale-file-bytes",hub,payload,changed,
                             "INPUT_XML_STALE_ORIGINAL_SHA256"))
            for name,bad_hub,bad_ops,src,reason in variants:
                with self.subTest(name=name):
                    trial=root/name
                    trial.mkdir()
                    p,out,report=self.run_cli(src,bad_hub,bad_ops,trial)
                    self.assertEqual(p.returncode,1,p.stdout+p.stderr)
                    self.assertIn(reason,p.stdout)
                    self.assertFalse(out.exists(),name)
                    self.assertFalse(report.exists(),name)
                    self.assertEqual(original.read_bytes(),immutable)

    def test_public_inputxml_only_findings_still_run_without_cross_run_join(self):
        for name,count in (("GREInputxml.xml",100),("PLB314Inputxml.xml",53)):
            with self.subTest(name=name):
                hub=self.read(self.xcu/"docs"/name)
                self.assertEqual(len(hub["components"]),count)
                self.assertEqual(len(hub["inputXml"]["runs"]),1)
                run=hub["inputXml"]["runs"][0]
                self.assertFalse(run["anchored"])
                result=resolve_inputxml_run_from_uxml(hub,run["id"])
                self.assertIsNotNone(result.findings_payload(
                    __import__("psi116_topology_resolver.models",fromlist=["ResolverConfig"])
                    .ResolverConfig())["summary"]["findingCountsByCode"])

if __name__=="__main__":
    unittest.main()
