"""UXML-S3: real Workspace-produced synthetic source pair, no writer."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from hashlib import sha256
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "converters"))
from psi116_topology_resolver.uxml_adapter import document_from_uxml, resolve_from_uxml, UxmlPsi116Error
from psi116_topology_resolver.uxml_compare import compare_psi116_uxml, compare_cross_format_uxml


class S3CaesarCrossFormat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xcu = Path(os.environ.get("XCU_UXML_ROOT") or "/definitely-not-present")
        cls.ready = (cls.xcu / "tools" / "inputxml-to-uxml.mjs").is_file()

    def reader(self, name, cli):
        source = self.xcu / "tests" / "fixtures" / name
        proc = subprocess.run(["node", str(self.xcu / "tools" / cli), str(source)],
                              cwd=self.xcu,capture_output=True,text=True,timeout=45)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(doc["sources"][0]["hash"], sha256(source.read_bytes()).hexdigest())
        self.assertEqual(doc["sources"][0]["sourceText"].encode("utf8"), source.read_bytes())
        return source, doc

    def pair(self):
        if not self.ready:
            self.skipTest("Pin XCU_UXML_ROOT and all 12 Git blobs to run S3 cross-format")
        psi_path, psi = self.reader("uxml-s3-synthetic.psi116.xml","psi116-to-uxml.mjs")
        input_path, caesar = self.reader(
            "uxml-s3-synthetic.workspace.input.xml","inputxml-to-uxml.mjs")
        return psi_path, psi, input_path, caesar

    def test_pair_has_exact_source_refs_and_absolute_points(self):
        _, psi, _, inp = self.pair()
        self.assertEqual(len(psi["components"]),2)
        self.assertEqual(len(inp["components"]),1)
        self.assertEqual(len(inp["ports"]),2)
        ref = inp["components"][0]["sourceRefs"][0]
        self.assertEqual(ref["recordKey"],"E0:F10.000000:T20.000000")
        self.assertEqual(ref["format"],"INPUT_XML")
        self.assertEqual(inp["ports"][0]["sourceRefs"][0]["endpoint"],"FROM")
        self.assertEqual(inp["ports"][1]["sourceRefs"][0]["endpoint"],"TO")
        self.assertEqual([p["point"]["x"] for p in inp["ports"]],[100,200])
        doc = document_from_uxml(inp)
        self.assertEqual(len(doc.branches[0].nodes),2)
        self.assertEqual([n.node_number for n in doc.branches[0].nodes],[10,20])
        self.assertEqual([n.inputxml_record_key for n in doc.branches[0].nodes],
                         [ref["recordKey"],ref["recordKey"]])
        self.assertEqual(doc.branches[0].nodes[0].position.x,100)
        self.assertIsNotNone(resolve_from_uxml(inp).findings)

    def test_s1_still_direct_equal_unchanged(self):
        psi_path, psi, _, _ = self.pair()
        self.assertEqual(compare_psi116_uxml(psi_path, psi), [])

    def test_cross_format_findings_are_equal_or_every_difference_has_cause(self):
        _, psi, _, inp = self.pair()
        differences = compare_cross_format_uxml(psi, inp)
        # Workspace InputXML has a PIPINGELEMENT but does not carry original
        # PSI116 ComponentRefNo; differences MUST NOT be silently equal.
        self.assertTrue(differences, "Conversion is known to drop source component ref")
        self.assertTrue(any("component_ref_no" in d and "CAUSE:" in d
                            for d in differences),differences)
        self.assertTrue(all("CAUSE:" in d for d in differences),
                        "No unexplained difference allowed: " + str(differences))
        for record in resolve_from_uxml(inp).document.branches[0].nodes:
            self.assertTrue(record.inputxml_record_key.startswith("E0:"))

    def test_source_ref_sha_point_and_ordinal_tamper_are_rejected(self):
        _, _, _, inp = self.pair()
        for name, change in [
            ("sourceRefSha", lambda d: d["components"][0]["sourceRefs"][0].update(
                fileSha256="0"*64)),
            ("wrongRecordKey", lambda d: d["components"][0]["sourceRefs"][0].update(
                recordKey="E5:F10:T20")),
            ("wrongPortPoint", lambda d: d["ports"][0]["point"].update(x=0)),
            ("wrongFileSource", lambda d: d["sources"][0].update(hash="f"*64)),
            ("wrongElementCount", lambda d: d["inputXml"].update(elementCount=300)),
        ]:
            with self.subTest(name=name):
                mutant = deepcopy(inp)
                change(mutant)
                with self.assertRaises((UxmlPsi116Error,KeyError,ValueError)):
                    document_from_uxml(mutant)

    def test_cross_format_cli_exit_and_exact_cause(self):
        psi_path,psi, _,inp = self.pair()
        import tempfile
        with tempfile.TemporaryDirectory(prefix="uxml-s3-compare-") as tmp:
            left = Path(tmp) / "source.json"
            right = Path(tmp) / "input.json"
            left.write_text(json.dumps(psi),encoding="utf8")
            right.write_text(json.dumps(inp),encoding="utf8")
            cmd=[sys.executable,"-m","converters.psi116_topology_resolver.uxml_compare",
                 str(left),str(right),"--cross-format"]
            result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,1,result.stdout+result.stderr)
            self.assertIn("DIFFERENT",result.stdout)
            self.assertIn("component_ref_no",result.stdout)
            self.assertIn("CAUSE:",result.stdout)
            # Independent old CLI unchanged:
            old=subprocess.run([sys.executable,"-m","converters.psi116_topology_resolver.uxml_compare",
                                str(psi_path),str(left)],cwd=ROOT,
                               capture_output=True,text=True,timeout=45)
            self.assertEqual(old.returncode,0,old.stdout+old.stderr)
            self.assertEqual(old.stdout.strip(),"EQUAL")


if __name__ == "__main__":
    unittest.main()
