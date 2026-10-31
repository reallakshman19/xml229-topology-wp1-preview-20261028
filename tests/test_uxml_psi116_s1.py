"""UXML-S1 cross-repo PSI116 parity against TopoFix's existing synthetic cases.

Run only when XCU_UXML_ROOT points to an ephemeral, exact-commit pinned XCU
checkout (CI download). No source reader is vendored in the TopoFix repository.
Every comparison uses the original Python parser/resolver for its oracle.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver import read_psi116_xml, ResolverConfig
from psi116_topology_resolver.uxml_compare import compare_psi116_uxml
from psi116_topology_resolver.uxml_adapter import document_from_uxml, resolve_from_uxml

from test_port_policy import node, doc, pipe_flange
from test_closure_witness import gap_case
from test_joint_repair import fixture as joint_fixture
from test_connection_gaps import example as gap_example
from test_short_elements import fixture as short_fixture
from test_junction_authority import fixture as junction_fixture
from test_source_preservation import source as preservation_fixture

VERIFIED = "http://aveva.com/pipeStress116.xsd"


def verified_synthetic(source: str) -> str:
    if 'xmlns="' + VERIFIED + '"' in source:
        return source
    assert '<PipeStressExport' in source
    return source.replace('<PipeStressExport',
                          '<PipeStressExport xmlns="' + VERIFIED + '"', 1)


def examples() -> dict[str, str]:
    """Representative exported fixture factories across the native TopoFix tests."""
    return {
        "port_exact": pipe_flange(0),
        "port_25": pipe_flange(25),
        "port_25_0001": pipe_flange(25.0001),
        "port_cross": pipe_flange(25, True),
        "clos_bound": gap_case(True),
        "clos_open": gap_case(False),
        "clos_unqualified": doc(
            node(-1, "BRAN", "B", 1, "0 0 0", "<ConnectionType>CLOS</ConnectionType>")
            + node(10, "FBLI", "BL", 1, "0 0 0")),
        "clos_bad_position": doc(
            node(10, "PIPE", "P", 1, "", "<ConnectionType>CLOS</ConnectionType>")),
        "joint_24_9": joint_fixture(124.9),
        "joint_25_0001": joint_fixture(125.0001),
        "gap_default": gap_example(),
        "gap_offset": gap_example("203.5 0 0"),
        "short_gask": short_fixture(3),
        "short_flange": short_fixture(6, "FLAN"),
        "short_over_limit": short_fixture(6.001),
        "junction_tee": junction_fixture("TEE", "TEE", 50, 25),
        "junction_olet": junction_fixture("OLET", "OLET", 50, 0),
        "junction_mismatch": junction_fixture("TEE", "OLET", 50, 25),
        "source_preserve": preservation_fixture(),
        "source_wall_changed": preservation_fixture(wall="2.87"),
        "duplicate_none_numbers": doc(
            node(-1, "BRAN", "", 1, "0 0 0")
            + node(-1, "ATTA", "S", 0, "10 0 0")
            + node(20, "PIPE", "P", 2, "100 0 0")),
    }


class UxmlPsi116Equivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ.get("XCU_UXML_ROOT", ""))
        cls.available = bool(os.environ.get("XCU_UXML_ROOT")) and (
            cls.root / "tools" / "psi116-to-uxml.mjs").is_file()

    def to_uxml(self, source: str, tempdir: Path, name: str = "synthetic"):
        file = tempdir / (name + ".xml")
        output = tempdir / (name + ".uxml.json")
        file.write_bytes(source.encode("utf-8"))
        proc = subprocess.run([
            "node", str(self.root / "tools" / "psi116-to-uxml.mjs"), str(file)
        ], cwd=self.root, capture_output=True, text=True, timeout=45)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(proc.stderr, proc.stderr)
        data = json.loads(proc.stdout)
        output.write_text(proc.stdout, encoding="utf-8")
        self.assertEqual(data["sources"][0]["hash"],
                         sha256(file.read_bytes()).hexdigest())
        return file, output, data

    def test_all_public_synthetic_topofix_fixture_factories_are_exact(self):
        if not self.available:
            self.skipTest("Only pinned XCU reader environment runs cross-repo native test")
        with tempfile.TemporaryDirectory(prefix="topofix-uxml-synthetic-") as temp:
            base = Path(temp)
            for name, xml in examples().items():
                with self.subTest(name=name):
                    verified = verified_synthetic(xml)
                    file, _, uxml = self.to_uxml(verified, base, name)
                    differences = compare_psi116_uxml(file, uxml)
                    self.assertEqual(differences, [], "\n".join(differences[:30]))
                    direct = read_psi116_xml(file)
                    adapted = document_from_uxml(uxml, source_name=str(file))
                    self.assertEqual(tuple(node.key for b in direct.branches for node in b.nodes),
                                     tuple(node.key for b in adapted.branches for node in b.nodes))

    def test_clos_witnesses_survive_lossless_source_node_transfer(self):
        if not self.available:
            self.skipTest("Only pinned XCU reader environment runs cross-repo native test")
        with tempfile.TemporaryDirectory(prefix="topofix-uxml-clos-") as temp:
            file, _, uxml = self.to_uxml(verified_synthetic(gap_case(True)), Path(temp))
            direct = read_psi116_xml(file)
            adapted = resolve_from_uxml(uxml, source_name=str(file))
            rows = adapted.findings_payload(ResolverConfig())["closureBindingWitnesses"]
            self.assertIn("B0:N6880:S1", [r["sourceKey"] for r in rows])
            self.assertEqual(adapted.document.source_sha256, direct.source_sha256)
            self.assertEqual(compare_psi116_uxml(file, uxml), [])

    def test_reader_clos_mutant_is_rejected_by_record_and_witness_comparison(self):
        if not self.available:
            self.skipTest("Only pinned XCU reader environment runs cross-repo native test")
        with tempfile.TemporaryDirectory(prefix="topofix-uxml-red-") as temp:
            file, _, uxml = self.to_uxml(verified_synthetic(gap_case(True)), Path(temp))
            self.assertEqual(compare_psi116_uxml(file, uxml), [])
            for c in uxml["components"]:
                fields = c["rawAttributes"]["psi116"]
                if fields["connectionType"] == "CLOS":
                    fields["connectionType"] = ""  # Deliberate source-reader omission.
            self.assertTrue(compare_psi116_uxml(file, uxml),
                            "Deleting CLOS must NOT yield an EQUAL report")


    def test_real_compare_cli_prints_equal_or_exact_clos_difference(self):
        if not self.available:
            self.skipTest("Only pinned XCU reader environment runs cross-repo native test")
        with tempfile.TemporaryDirectory(prefix="topofix-uxml-cli-") as temp:
            base = Path(temp)
            file, payload_file, uxml = self.to_uxml(
                verified_synthetic(gap_case(True)), base)
            module = "converters.psi116_topology_resolver.uxml_compare"
            command = [sys.executable, "-m", module, str(file), str(payload_file)]
            good = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                                  capture_output=True, text=True, timeout=45)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(good.stdout.strip(), "EQUAL")
            for component in uxml["components"]:
                record = component["rawAttributes"]["psi116"]
                if record["connectionType"] == "CLOS":
                    record["connectionType"] = ""
            payload_file.write_text(json.dumps(uxml), encoding="utf-8")
            red = subprocess.run(command, cwd=Path(__file__).resolve().parents[1],
                                 capture_output=True, text=True, timeout=45)
            self.assertEqual(red.returncode, 1)
            self.assertIn("DIFFERENT", red.stdout)
            self.assertIn("closureBindingWitnesses", red.stdout)


if __name__ == "__main__":
    unittest.main()
