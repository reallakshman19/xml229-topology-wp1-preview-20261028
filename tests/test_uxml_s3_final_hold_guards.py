"""Final R2: source-backed exact-code guards, synthetic public XCU only.

Never uses private Owner files; never writes an original source. Each refusal
is pinned to a single named code, so an overlapping validation cannot mask a
deleted safeguard. The mixed-run case uses XCU's real strict reader.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from converters.psi116_topology_resolver.uxml_adapter import (
    UxmlPsi116Error, _caesar_original_rows, document_from_uxml,
    resolve_from_uxml, resolve_inputxml_run_from_uxml,
)
from converters.psi116_topology_resolver.uxml_compare import compare_cross_format_uxml

SOURCE = "uxml-s3-synthetic.workspace.input.xml"
DELTA = "uxml-s3-synthetic.workspace.delta-only.input.xml"
PSI = "uxml-s3-synthetic.psi116.xml"


class FinalInputXmlHoldGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xcu = Path(os.environ.get("XCU_UXML_ROOT") or "/nonexistent")
        cls.input_path = cls.xcu / "tests" / "fixtures" / SOURCE
        cls.psi_path = cls.xcu / "tests" / "fixtures" / PSI
        cls.reader = cls.xcu / "tools" / "inputxml-to-uxml.mjs"
        if not cls.reader.is_file() or not cls.input_path.is_file():
            raise unittest.SkipTest("Exact pinned public XCU S3 reader and fixtures required")
        cls.input = cls._strict(cls.input_path, cls.reader)
        cls.delta = cls._strict(cls.xcu / "tests" / "fixtures" / DELTA, cls.reader)
        cls.psi = cls._strict(cls.psi_path, cls.xcu / "tools" / "psi116-to-uxml.mjs")

    @classmethod
    def _strict(cls, source, reader):
        proc = subprocess.run(["node", str(reader), str(source)], cwd=cls.xcu,
                              capture_output=True, text=True, timeout=60)
        if proc.returncode:
            raise AssertionError("PUBLIC_XCU_STRICT_READER_FAILED: " + proc.stderr)
        return json.loads(proc.stdout)

    def exact(self, code, call):
        with self.assertRaises(UxmlPsi116Error) as error:
            call()
        self.assertEqual(str(error.exception), code)

    def hub(self):
        return deepcopy(self.input)

    def key(self, hub, i):
        return hub["components"][i]["sourceRefs"][0]["recordKey"]

    def mixed(self):
        """Remove exactly six absolute anchors from last original PIPINGELEMENT."""
        original = self.input_path.read_text(encoding="utf-8")
        tags = list(re.finditer(r"<PIPINGELEMENT\b[^>]*>", original))
        self.assertEqual(len(tags), 6)
        tag = tags[5]
        updated, removed = re.subn(r'\s+(?:FROM|TO)_[XYZ]="[^"]*"', "", tag.group())
        self.assertEqual(removed, 6)
        modified = original[:tag.start()] + updated + original[tag.end():]
        with tempfile.TemporaryDirectory(prefix="public-s3-mixed-frame-") as folder:
            path = Path(folder) / SOURCE
            path.write_bytes(modified.encode("utf-8"))
            hub = self._strict(path, self.reader)
        runs = hub["inputXml"]["runs"]
        self.assertEqual([(r["id"], r["anchored"]) for r in runs],
                         [("RUN-0000", True), ("RUN-0001", False)])
        return hub

    def _change_last_source_element(self, change, *, strict_reader=False):
        original = self.input_path.read_text(encoding="utf-8")
        tags = list(re.finditer(r"<PIPINGELEMENT\b[^>]*>", original))
        self.assertEqual(len(tags), 6)
        last = tags[5]
        changed = change(last.group())
        self.assertNotEqual(changed, last.group())
        altered = original[:last.start()] + changed + original[last.end():]
        if strict_reader:
            with tempfile.TemporaryDirectory(prefix="public-source-authority-") as folder:
                path = Path(folder) / SOURCE
                path.write_bytes(altered.encode("utf-8"))
                return self._strict(path, self.reader)
        hub = self.hub()
        hub["sources"][0]["sourceText"] = altered
        digest = sha256(altered.encode("utf-8")).hexdigest()
        hub["sources"][0]["hash"] = digest
        hub["inputXml"]["sourceSha256"] = digest
        return hub

    def _change_last_attr(self, attribute, value, *, strict_reader=False):
        def change(tag):
            pattern = r'(' + re.escape(attribute) + r'=")[^"]*(")'
            altered, count = re.subn(pattern, lambda m: m.group(1) + value + m.group(2), tag)
            self.assertEqual(count, 1, attribute)
            return altered
        return self._change_last_source_element(change, strict_reader=strict_reader)

    def test_IA1_honest_xcu_run_partition_is_byte_source_equivalent(self):
        from converters.psi116_topology_resolver.uxml_adapter import (
            _caesar_original_rows, _recompute_inputxml_runs,
        )
        for name, hub, anchored in (
            ("anchored", self.input, True), ("delta-only", self.delta, False),
        ):
            with self.subTest(hub=name):
                rows, _ = _caesar_original_rows(hub["sources"][0]["sourceText"])
                derived = _recompute_inputxml_runs(rows)
                self.assertEqual(len(derived), 2)
                self.assertEqual([run["anchored"] for run in derived],
                                 [anchored, anchored])
                for declared, trusted in zip(hub["inputXml"]["runs"], derived):
                    for field in ("id", "elementIndices", "edgeCount",
                                  "nodeCount", "firstNode", "anchored"):
                        self.assertEqual(declared[field], trusted[field],
                                         f"{name} field={field}")
                document_from_uxml(hub)

    def test_IA1_single_run_delta_only_forgery_partition_refused(self):
        hub = deepcopy(self.delta)
        self.assertEqual(len(hub["inputXml"]["runs"]), 2)
        forged = hub["inputXml"]["runs"][0]
        forged["elementIndices"] = list(range(len(hub["components"])))
        forged["edgeCount"] = len(forged["elementIndices"])
        forged["nodeCount"] += hub["inputXml"]["runs"][1]["nodeCount"]
        hub["inputXml"]["runs"] = [forged]
        for comp in hub["components"]:
            comp["sourceRefs"][0]["runId"] = forged["id"]
            comp["rawAttributes"]["inputXml"]["runId"] = forged["id"]
        for port in hub["ports"]:
            port["runId"] = forged["id"]
            port["sourceRefs"][0]["runId"] = forged["id"]
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: resolve_from_uxml(hub))

    def test_IA1_all_anchored_mixed_runs_forged_as_one_merge_refused(self):
        hub = self.mixed()
        self.assertEqual([run["anchored"] for run in hub["inputXml"]["runs"]],
                         [True, False])
        first, second = hub["inputXml"]["runs"]
        first["elementIndices"] = first["elementIndices"] + second["elementIndices"]
        first["edgeCount"] = len(first["elementIndices"])
        first["nodeCount"] += second["nodeCount"]
        first["anchored"] = True
        hub["inputXml"]["runs"] = [first]
        # Fully forge dependent hub provenance, so only the independently
        # recomputed original-source partition can refuse the false merge.
        for component in hub["components"]:
            ref = component["sourceRefs"][0]
            info = component["rawAttributes"]["inputXml"]
            ref["runId"] = first["id"]
            info["runId"] = first["id"]
            ref["anchored"] = True
            info["anchored"] = True
        for port in hub["ports"]:
            port["runId"] = first["id"]
            port["anchored"] = True
            port["sourceRefs"][0]["runId"] = first["id"]
            port["sourceRefs"][0]["anchored"] = True
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: resolve_from_uxml(hub))
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_IA1_all_anchored_mixed_hub_forgery_partition_refused(self):
        hub = self.mixed()
        self.assertEqual([r["anchored"] for r in hub["inputXml"]["runs"]],
                         [True, False])
        hub["inputXml"]["runs"][1]["anchored"] = True
        for comp in hub["components"]:
            if comp["sourceRefs"][0]["runId"] == "RUN-0001":
                comp["sourceRefs"][0]["anchored"] = True
                comp["rawAttributes"]["inputXml"]["anchored"] = True
        for port in hub["ports"]:
            if port["runId"] == "RUN-0001":
                port["anchored"] = True
                port["sourceRefs"][0]["anchored"] = True
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: resolve_from_uxml(hub))
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_IA1_first_node_forged_even_if_indices_correct(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["firstNode"] = "SYNTHETIC_FORGED_FIRST"
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_IA1_node_count_forged_even_if_membership_correct(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["nodeCount"] += 1
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_IA5_integer_alias_30_vs_30_000000_refuses(self):
        hub = self._change_last_attr("FROM_NODE", "30", strict_reader=True)
        self.assertEqual([run["anchored"] for run in hub["inputXml"]["runs"]],
                         [True, True])
        self.exact("INPUT_XML_NODE_LITERAL_ALIAS",
                   lambda: resolve_from_uxml(hub))
        self.exact("INPUT_XML_NODE_LITERAL_ALIAS",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_IA4_fractional_100_5_node_number_refuses_without_truncation(self):
        hub = self._change_last_attr("FROM_NODE", "100.5")
        self.exact("INPUT_XML_INVALID_NODE_NUMBER:E5:FROM",
                   lambda: document_from_uxml(hub))

    def test_IA4_unknown_run_id_refuses_instead_of_empty_findings(self):
        from converters.psi116_topology_resolver.uxml_adapter import (
            resolve_inputxml_run_from_uxml,
        )
        self.exact("INPUT_XML_RUN_ID_NOT_FOUND:RUN-9999",
                   lambda: resolve_inputxml_run_from_uxml(self.input, "RUN-9999"))

    def test_IA2_incomplete_absolute_anchor_is_named(self):
        hub = self._change_last_source_element(
            lambda tag: re.sub(r'\s+FROM_Y="[^"]*"', "", tag))
        self.exact("INPUT_XML_INCOMPLETE_ABSOLUTE_ANCHOR",
                   lambda: document_from_uxml(hub))

    def test_IA2_invalid_non_numeric_anchor_is_named(self):
        hub = self._change_last_attr("FROM_X", "synthetic-nonnumeric")
        self.exact("INPUT_XML_INVALID_NUMBER:E5:FROM_X",
                   lambda: document_from_uxml(hub))

    def test_IA2_nonfinite_absolute_anchor_is_named(self):
        hub = self._change_last_attr("FROM_X", "1e999")
        self.exact("INPUT_XML_NONFINITE_ABSOLUTE_ANCHOR",
                   lambda: document_from_uxml(hub))

    def test_IA2_literal_sentinel_xyz_is_not_exempt_as_an_anchor(self):
        from converters.psi116_topology_resolver.uxml_adapter import (
            _caesar_original_rows, _recompute_inputxml_runs,
        )
        original = self.input_path.read_text(encoding="utf-8")
        tags = list(re.finditer(r"<PIPINGELEMENT\b[^>]*>", original))
        tag = tags[5]
        altered = tag.group()
        for endpoint in ("FROM", "TO"):
            for axis in "XYZ":
                altered, count = re.subn(
                    endpoint + "_" + axis + r'="[^"]*"',
                    endpoint + "_" + axis + '="-1.010100"', altered)
                self.assertEqual(count, 1)
        text = original[:tag.start()] + altered + original[tag.end():]
        rows, _ = _caesar_original_rows(text)
        runs = _recompute_inputxml_runs(rows)
        self.assertEqual([run["anchored"] for run in runs], [True, True],
                         "XCU point() admits -1.0101 as a literal absolute value")

    def test_B1_M05_mixed_anchored_unanchored_resolve_refusal(self):
        self.exact("INPUT_XML_CROSS_UNANCHORED_RUN_GAP_PROXIMITY_JOIN_REFUSED",
                   lambda: resolve_from_uxml(self.mixed()))

    def test_B1_M12_mixed_anchored_unanchored_crossformat_refusal(self):
        self.exact("CROSS_FORMAT_UNANCHORED_ABSOLUTE_FRAME_COMPARISON_REFUSED",
                   lambda: compare_cross_format_uxml(self.psi, self.mixed()))

    def test_invalid_inputxml_scope_is_named(self):
        hub = self.hub()
        hub["inputXml"] = ["malformed", "scope"]
        self.exact("INPUT_XML_SCOPE_INVALID", lambda: document_from_uxml(hub))

    def test_invalid_coordinate_frame_is_named(self):
        hub = self.hub()
        hub["coordinateFrame"] = ["malformed", "frame"]
        self.exact("INPUT_XML_COORDINATE_FRAME_INVALID",
                   lambda: document_from_uxml(hub))

    def test_B2_coordinate_frame_mismatch(self):
        hub = self.hub()
        hub["coordinateFrame"]["transform"] = "UNVERIFIED"
        self.exact("INPUT_XML_COORDINATE_FRAME_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_B2_caesar_original_root_required(self):
        original = self.input_path.read_text(encoding="utf-8")
        self.assertTrue(original.startswith("<CAESARII "))
        changed = original.replace("<CAESARII ", "<OTHERROOT ", 1)
        self.assertIn("</CAESARII>", changed)
        changed = changed.replace("</CAESARII>", "</OTHERROOT>", 1)
        self.exact("INPUT_XML_CAESAR_ROOT_REQUIRED",
                   lambda: _caesar_original_rows(changed))

    def test_B2_topology_full_profile_required(self):
        hub = self.hub()
        hub["profile"] = "NOT_FULL"
        self.exact("INPUT_XML_NOT_TOPOLOGY_FULL",
                   lambda: document_from_uxml(hub))

    def test_B2_original_source_text_required(self):
        hub = self.hub()
        hub["sources"][0]["sourceText"] = ""
        self.exact("INPUT_XML_ORIGINAL_TEXT_REQUIRED",
                   lambda: document_from_uxml(hub))

    def test_B2_original_sha256_required(self):
        hub = self.hub()
        hub["sources"][0]["hash"] = "not-a-valid-sha256"
        self.exact("INPUT_XML_SOURCE_SHA256_REQUIRED",
                   lambda: document_from_uxml(hub))

    def test_B2_exactly_two_ports_per_input_element(self):
        hub = self.hub()
        hub["ports"].pop()
        self.exact("INPUT_XML_PORTS_PER_ELEMENT_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_B2_run_frame_declarations_required(self):
        hub = self.hub()
        hub["inputXml"]["runs"] = []
        self.exact("INPUT_XML_RUN_FRAME_DECLARATIONS_REQUIRED",
                   lambda: document_from_uxml(hub))

    def test_B2_run_identity_required(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["id"] = "RUN-INVALID"
        self.exact("INPUT_XML_RUN_IDENTITY_INVALID",
                   lambda: document_from_uxml(hub))

    def test_B2_run_frame_cross_unanchored_policy_required(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["crossUnanchoredRunPolicy"] = "ALLOW"
        self.exact("INPUT_XML_RUN_FRAME_INVALID",
                   lambda: document_from_uxml(hub))

    def test_B2_run_element_index_count_required(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["edgeCount"] += 1
        self.exact("INPUT_XML_RUN_ELEMENT_INDEX_INVALID",
                   lambda: document_from_uxml(hub))

    def test_B2_duplicate_or_invalid_run_element_index(self):
        hub = self.hub()
        indices = hub["inputXml"]["runs"][0]["elementIndices"]
        self.assertGreaterEqual(len(indices), 2)
        indices[1] = indices[0]
        self.exact("INPUT_XML_DUPLICATE_OR_INVALID_RUN_ELEMENT_INDEX",
                   lambda: document_from_uxml(hub))

    def test_B2_run_coverage_must_be_complete(self):
        hub = self.hub()
        run = hub["inputXml"]["runs"][0]
        self.assertGreaterEqual(len(run["elementIndices"]), 2)
        run["elementIndices"].pop()
        run["edgeCount"] = len(run["elementIndices"])
        self.exact("INPUT_XML_RUN_COVERAGE_INCOMPLETE",
                   lambda: document_from_uxml(hub))

    def test_B2_raw_record_identity_cannot_drift(self):
        hub = self.hub()
        hub["components"][0]["rawAttributes"]["inputXml"]["elementIndex"] = 999
        self.exact("INPUT_XML_RAW_RECORD_ID_MISMATCH:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_B2_nested_source_bend_evidence_cannot_drift(self):
        hub = self.hub()
        comp = hub["components"][2]
        info = comp["rawAttributes"]["inputXml"]
        self.assertIsNotNone(info["bendEvidence"])
        info["bendEvidence"]["radius"] += 1
        self.exact("INPUT_XML_NESTED_SOURCE_EVIDENCE_MISMATCH:" + self.key(hub, 2),
                   lambda: document_from_uxml(hub))

    def test_B2_port_coordinate_frame_cannot_drift(self):
        hub = self.hub()
        hub["ports"][0]["coordinateFrame"] = "UNVERIFIED"
        self.exact("INPUT_XML_PORT_FRAME_MISMATCH:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_B2_delta_path_conflict_between_shared_node_ports(self):
        hub = self.hub()
        comp = hub["components"][1]
        info = comp["rawAttributes"]["inputXml"]
        self.assertEqual(hub["components"][0]["sourceRefs"][0]["toNode"],
                         comp["sourceRefs"][0]["fromNode"])
        for port in hub["ports"]:
            if port["componentId"] == comp["id"]:
                port["point"]["x"] += 7
        info["from"]["x"] += 7
        info["to"]["x"] += 7
        key = self.key(hub, 1)
        self.exact("INPUT_XML_DELTA_PATH_CONFLICT:" + key + ":" +
                   comp["sourceRefs"][0]["fromNode"],
                   lambda: document_from_uxml(hub))

    def test_B2_bend_component_type_from_original_source(self):
        hub = self.hub()
        comp = hub["components"][2]
        info = comp["rawAttributes"]["inputXml"]
        self.assertIsNotNone(info["bendEvidence"])
        self.assertFalse(any(s.get("node") == info["toNode"] and s.get("typeCode") in (3,5)
                             for s in info.get("sifEvidence", [])))
        info["componentType"] = "PIPE"
        self.exact("INPUT_XML_BEND_COMPONENT_TYPE_CONFLICT:" + self.key(hub, 2),
                   lambda: document_from_uxml(hub))

    def test_B2_run_resolution_requires_inputxml_format(self):
        self.exact("INPUT_XML_RUN_RESOLUTION_FORMAT_REQUIRED",
                   lambda: resolve_inputxml_run_from_uxml(self.psi, "RUN-0000"))

    def test_IA4_crossformat_requires_psi116_source(self):
        hub = deepcopy(self.psi)
        hub["sources"][0]["format"] = "INPUT_XML"
        self.exact("CROSS_FORMAT_PSI116_SOURCE_REQUIRED",
                   lambda: compare_cross_format_uxml(hub, self.input))

    def test_B2_crossformat_requires_inputxml_source(self):
        hub = self.hub()
        hub["sources"][0]["format"] = "PSI116"
        self.exact("CROSS_FORMAT_INPUT_XML_SOURCE_REQUIRED",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_B2_crossformat_requires_verified_hub_frame(self):
        hub = self.hub()
        hub["coordinateFrame"]["transform"] = "UNVERIFIED"
        self.exact("CROSS_FORMAT_HUB_FRAME_UNVERIFIED",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_B3_raw_inputxml_export_cli_refuses_before_missing_xcu_reader(self):
        self._assert_raw_inputxml_cli_holds_without_reader("uxml_export_ops")

    def test_B3_raw_inputxml_patch_cli_refuses_before_missing_xcu_reader(self):
        self._assert_raw_inputxml_cli_holds_without_reader("uxml_patch_psi116")

    def _assert_raw_inputxml_cli_holds_without_reader(self, module):
        original = self.input_path.read_bytes()
        with tempfile.TemporaryDirectory(prefix="public-inputxml-cli-order-") as tmp:
            root = Path(tmp)
            ops = root / "not-created.ops.json"  # deliberately absent
            output = root / "not-created-fixed.xml"
            validation = root / "not-created-validation.json"
            env = os.environ.copy()
            env["XCU_UXML_ROOT"] = str(root / "nonexistent-xcu-reader")
            extra = (["--output", str(output), "--validation", str(validation)]
                     if module == "uxml_patch_psi116" else [])
            process = subprocess.run(
                [sys.executable, "-m", "converters.psi116_topology_resolver." + module,
                 str(self.input_path), str(ops), *extra],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(process.returncode, 1,
                             process.stdout + process.stderr)
            self.assertEqual(process.stdout.strip().splitlines(),
                             ["DIFFERENT", "ERROR: INPUT_XML_APPLY_NOT_ENABLED"])
            self.assertNotIn("XCU_PINNED_READER_REQUIRED",
                             process.stdout + process.stderr)
            for target in (ops, output, validation):
                self.assertFalse(target.exists(), "refusal created " + str(target))
        self.assertEqual(self.input_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
