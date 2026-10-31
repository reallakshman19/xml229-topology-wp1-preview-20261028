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

    def test_junction_owner_finding_counts_match_psi116(self):
        """RED on old S3 heads: the original InputXML run falsely infers a junction owner.

        Same synthetic Workspace-replayed pair, same unchanged engine.  Assert the
        junction finding FIRST so the old failure is the missing reviewer proof,
        then verify the three related findings and the exact 13-field HOLD.
        """
        from psi116_topology_resolver.uxml_adapter import resolve_from_uxml
        from psi116_topology_resolver.models import ResolverConfig
        psi=self.doc("uxml-s3-synthetic.psi116.xml","psi116-to-uxml.mjs")
        inp=self.doc("uxml-s3-synthetic.workspace.input.xml")
        config=ResolverConfig()
        get_counts=lambda hub: resolve_from_uxml(hub).findings_payload(config)["summary"]["findingCountsByCode"]
        psi_counts,input_counts=get_counts(psi),get_counts(inp)
        junction="JUNCTION_OWNER_INFERRED_FROM_PORT_SET"
        self.assertEqual(psi_counts.get(junction,0),0,"synthetic PSI116 declares no inferred junction")
        self.assertEqual(input_counts.get(junction,0),0,
            "InputXML SIF@TYPE=5 is OLET; old S3 spur projected a false junction owner")
        expected={
            "BRANCH_END_UNVERIFIED":5,
            "ELBO_HELPER_PORTS_MISSING":1,
            "ELBO_OWNER_ENDPOINT_MISSING":1,
            junction:0,
        }
        for label,actual in (("PSI116",psi_counts),("InputXML",input_counts)):
            self.assertEqual({code:actual.get(code,0) for code in expected},expected,label)
        differences=compare_cross_format_uxml(psi,inp)
        self.assertEqual(len(differences),13,differences)
        self.assertTrue(all("UNEXPLAINED CLASS=B_WORKSPACE_CONVERSION_LOSS" in row
                            for row in differences),differences)
        self.assertEqual(sum("field=component_ref_no" in row for row in differences),9)
        self.assertEqual(sum("SIF@TYPE=5" in row for row in differences),4)

    def test_cross_format_evidence_discloses_sif_type_and_no_forged_tee(self):
        psi=self.doc("uxml-s3-synthetic.psi116.xml","psi116-to-uxml.mjs")
        inp,doc=self.records()
        differences=compare_cross_format_uxml(psi,inp)
        self.assertTrue(any("UNEXPLAINED" in row and "SIF@TYPE" in row
                            for row in differences),differences)
        self.assertTrue(all(("UNEXPLAINED" in row or "EVIDENCE_ONLY" in row)
                            for row in differences),differences)

    def test_50mm_real_source_change_appears_as_unexplained_geometry_drift(self):
        import ast,tempfile,re
        psi=self.doc("uxml-s3-synthetic.psi116.xml","psi116-to-uxml.mjs")
        before=self.doc("uxml-s3-synthetic.workspace.input.xml")
        source_ref=before["components"][5]["sourceRefs"][0]
        self.assertEqual(source_ref["recordKey"],"E5:F100.000000:T110.000000",
            "synthetic last PIPINGELEMENT is exact source ordinal five")
        self.assertEqual(source_ref["elementIndex"],5)
        original=(self.xcu/"tests/fixtures/uxml-s3-synthetic.workspace.input.xml").read_text()
        elements=list(re.finditer(r'<PIPINGELEMENT\b[^>]+>',original))
        self.assertEqual(len(elements),6)
        last=elements[5]
        original_tag=last.group(0)
        self.assertIn('FROM_NODE="100.000000"',original_tag)
        self.assertIn('TO_NODE="110.000000"',original_tag)
        expected_fields={"DELTA_X":("100.000000","150.000000"),
                         "TO_X":("1100.000000","1150.000000")}
        tag=original_tag
        for field,(before_value,after_value) in expected_fields.items():
            field_re=r'(\b'+field+r'=\")([^\"]+)(\")'
            match=re.search(field_re,tag)
            self.assertIsNotNone(match,field)
            self.assertEqual(match.group(2),before_value,field+" original source")
            tag=tag[:match.start(2)]+after_value+tag[match.end(2):]
        for field,(_,after_value) in expected_fields.items():
            self.assertRegex(tag,r'\b'+field+r'="'+after_value+r'"')
        changed_source=original[:last.start()]+tag+original[last.end():]
        with tempfile.TemporaryDirectory(prefix="uxml-s3-geometric-red-") as td:
            target=Path(td)/"changed.input.xml"
            target.write_bytes(changed_source.encode("utf8"))
            p=subprocess.run(["node",str(self.xcu/"tools/inputxml-to-uxml.mjs"),str(target)],
                cwd=self.xcu,capture_output=True,text=True,timeout=45)
            self.assertEqual(p.returncode,0,p.stderr)
            changed=json.loads(p.stdout)
        self.assertEqual(changed["components"][5]["sourceRefs"][0]["recordKey"],
                         source_ref["recordKey"],"same source record despite changed file SHA")
        self.assertNotEqual(changed["sources"][0]["hash"],before["sources"][0]["hash"])
        before_node=document_from_uxml(before).branches[-1].nodes[-1]
        after_node=document_from_uxml(changed).branches[-1].nodes[-1]
        self.assertEqual((before_node.node_number,after_node.node_number),(110,110))
        self.assertEqual(before_node.position.as_list(),[1100.0,0.0,0.0])
        self.assertEqual(after_node.position.as_list(),[1150.0,0.0,0.0])
        differences=compare_cross_format_uxml(psi,changed)
        position_rows=[row for row in differences if " NODE_POSITION:" in row]
        self.assertEqual(len(position_rows),1,differences)
        exact=re.fullmatch(
            r'UNEXPLAINED CLASS=C_SOURCE_DIFFERENCE NODE_POSITION:node=110 slot=0 '
            r'POSITION PSI116=(\[[^\]]+\]) INPUT_XML=(\[[^\]]+\]) deltaMm=50\.000; '
            r'CAUSE: geometric coordinates differ in the SAME PSI116_XYZ_MM hub frame; '
            r'EVIDENCE: PSI116 Node@Position; InputXML PIPINGELEMENT DELTA_X/Y/Z & FROM/TO_X/Y/Z at Node=110',
            position_rows[0])
        self.assertIsNotNone(exact,position_rows[0])
        self.assertEqual(ast.literal_eval(exact.group(1)),[1100.0,0.0,0.0],
                         "PSI116 unchanged hub NODE_POSITION")
        self.assertEqual(ast.literal_eval(exact.group(2)),[1150.0,0.0,0.0],
                         "InputXML mutated hub NODE_POSITION")
        self.assertFalse(any(" NODE_POSITION:" in row for row in
                             compare_cross_format_uxml(psi,before)),
                         "unmutated synthetic pair has no geometric difference")

    def _verify_public_caesar14_sample(self, name: str, count: int):
        # These two XCU docs are public InputXML-only samples. No matching
        # PSI116 source is available; reporting PSI116 findings would invent data.
        sample=self.xcu/"docs"/name
        p=subprocess.run(["node",str(self.xcu/"tools/inputxml-to-uxml.mjs"),str(sample)],
                         cwd=self.xcu,capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr)
        inp=json.loads(p.stdout)
        self.assertEqual(inp["inputXml"]["elementCount"],count)
        self.assertEqual(len(inp["components"]),count)
        self.assertEqual(len(inp["inputXml"]["runs"]),1)
        self.assertFalse(inp["inputXml"]["runs"][0]["anchored"])
        doc=document_from_uxml(inp)
        self.assertTrue(doc.branches)
        from psi116_topology_resolver.uxml_adapter import resolve_from_uxml
        from psi116_topology_resolver.models import ResolverConfig
        result=resolve_from_uxml(inp)
        counts=result.findings_payload(ResolverConfig())["summary"]["findingCountsByCode"]
        print(f"PUBLIC_CAESAR14 {name}: InputXML_PIPINGELEMENTS={count} "
              f"inputxml_findings_by_code={dict(sorted(counts.items()))} "
              "PSI116_COUNTS=NOT_AVAILABLE no paired PSI source",flush=True)
        return counts

    def test_public_GRE_delta_only_inputxml_engine(self):
        self._verify_public_caesar14_sample("GREInputxml.xml",100)

    def test_public_PLB314_delta_only_inputxml_engine(self):
        self._verify_public_caesar14_sample("PLB314Inputxml.xml",53)

if __name__=="__main__":unittest.main()
