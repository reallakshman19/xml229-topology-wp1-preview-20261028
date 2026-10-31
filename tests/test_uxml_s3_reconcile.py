"""S3 final: RED-first tests for real InputXML source-backed projection repairs.

Tests fail on initial S3 head 86fd3042. Every field assertion names the
originating InputXML evidence, and NONE assumes equivalence to private data.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"converters"))
from psi116_topology_resolver.uxml_adapter import document_from_uxml
from psi116_topology_resolver.uxml_compare import compare_cross_format_uxml

class SourceBackedReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xcu=Path(os.environ.get("XCU_UXML_ROOT") or "/nonexistent")
        if not (cls.xcu/"tools/inputxml-to-uxml.mjs").is_file():
            raise unittest.SkipTest("Cross-repo tests require XCU_UXML_ROOT exact Git blob pins")

    def doc(self, source, cli="inputxml-to-uxml.mjs"):
        p=subprocess.run(["node",str(self.xcu/"tools"/cli),
                          str(self.xcu/"tests/fixtures"/source)],
                         cwd=self.xcu,capture_output=True,text=True,timeout=45)
        self.assertEqual(p.returncode,0,p.stderr)
        return json.loads(p.stdout)

    def records(self):
        inp=self.doc("uxml-s3-synthetic.workspace.input.xml")
        doc=document_from_uxml(inp)
        return inp,doc

    def test_source_inherited_physical_properties_are_retained(self):
        inp,doc=self.records()
        by_no={r.node_number:r for b in doc.branches for r in b.nodes}
        for node in (30,50,60):
            self.assertEqual(by_no[node].outside_diameter,100,
                f"node {node}: original first route element PIPINGELEMENT[0]@DIAMETER=100")
            self.assertAlmostEqual(by_no[node].wall_thickness,6.02,
                msg=f"node {node}: original PIPINGELEMENT[0]@WALL_THICK=6.02")
        self.assertEqual(inp["components"][2]["rawAttributes"]["inputXml"]["physicalEvidence"]["outsideDiameter"]["sourceElementIndex"],0)

    def test_source_nested_bend_is_owned_by_to_endpoint(self):
        inp,doc=self.records()
        by_no={r.node_number:r for b in doc.branches for r in b.nodes}
        self.assertEqual(by_no[50].component_type,"ELBO",
            "PIPINGELEMENT[2]/BEND belongs to TO_NODE=50")
        self.assertEqual(by_no[50].raw_component_type,"BEND",
            "original XML carries literal BEND; normalized engine uses ELBO")
        self.assertEqual(by_no[50].bend_radius,150,
            "PIPINGELEMENT[2]/BEND@RADIUS=150")
        self.assertEqual(inp["components"][2]["rawAttributes"]["inputXml"]["bendEvidence"]["endpoint"],"TO")

    def test_interior_endpoints_deduplicated_only_within_route(self):
        inp,doc=self.records()
        self.assertEqual(len(inp["components"]),6)
        self.assertEqual(len(doc.branches),3,
            "route changes at element 4 tee fork and element 5 restart")
        self.assertEqual([len(branch.nodes) for branch in doc.branches],[5,2,2],
            "6 elements project to exactly nine original route endpoint records, not twelve")
        self.assertEqual(sum(r.node_number==20 for b in doc.branches for r in b.nodes),2,
            "tee junction occurs once in main route, once in separate explicit tee branch")
        self.assertEqual(sum(r.node_number==30 for b in doc.branches for r in b.nodes),1)
        self.assertEqual(sum(r.node_number==50 for b in doc.branches for r in b.nodes),1)
        all_keys={ref["recordKey"] for component in inp["components"] for ref in component["sourceRefs"]}
        retained={key for b in doc.branches for row in b.nodes
                    for key in row.inputxml_record_keys}
        self.assertEqual(retained,all_keys,"dedup must retain EVERY original element sourceRef")

    def test_cross_format_evidence_discloses_sif_type_and_no_forged_tee(self):
        psi=self.doc("uxml-s3-synthetic.psi116.xml","psi116-to-uxml.mjs")
        inp,doc=self.records()
        differences=compare_cross_format_uxml(psi,inp)
        self.assertTrue(any("UNEXPLAINED" in row and "SIF@TYPE" in row
                            for row in differences),differences)
        self.assertTrue(all(("UNEXPLAINED" in row or "EVIDENCE_ONLY" in row)
                            for row in differences),differences)

    def test_50mm_real_source_change_appears_as_unexplained_geometry_drift(self):
        import hashlib,tempfile
        psi=self.doc("uxml-s3-synthetic.psi116.xml","psi116-to-uxml.mjs")
        original=(self.xcu/"tests/fixtures/uxml-s3-synthetic.workspace.input.xml").read_text()
        # Last disconnected route: update BOTH source absolute TO_X and DELTA_X
        # to retain internally consistent source geometry; compare must still FAIL.
        import re
        # Preserve all original lexical XML/namespace bytes: change only two
        # source attributes on the final PIPINGELEMENT, +50 mm each.
        physical=list(re.finditer(r'<PIPINGELEMENT\b[^>]+>',original))
        self.assertEqual(len(physical),6)
        last=physical[-1]
        original_tag=last.group(0)
        tag=original_tag
        for field in ("TO_X","DELTA_X"):
            match=re.search(r'(\b'+field+r'=")([^"]+)(")',tag)
            self.assertIsNotNone(match)
            changed=format(float(match.group(2))+50,".6f")
            tag=tag[:match.start(2)]+changed+tag[match.end(2):]
        changed_source=original[:last.start()]+tag+original[last.end():]
        # For comparison of genuine changed source semantics, only synthetic.
        with tempfile.TemporaryDirectory(prefix="uxml-s3-geometric-red-") as td:
            target=Path(td)/"changed.input.xml"
            target.write_bytes(changed_source.encode("utf8"))
            p=subprocess.run(["node",str(self.xcu/"tools/inputxml-to-uxml.mjs"),str(target)],
              cwd=self.xcu,capture_output=True,text=True,timeout=45)
            self.assertEqual(p.returncode,0,p.stderr)
            differences=compare_cross_format_uxml(psi,json.loads(p.stdout))
        self.assertTrue(any("POSITION" in row and "UNEXPLAINED" in row and
                            ("50" in row or "1150" in row)
                            for row in differences),differences)
        self.assertTrue(differences,"source-backed fifty-mm mutation must never compare EQUAL")
if __name__=="__main__":unittest.main()
