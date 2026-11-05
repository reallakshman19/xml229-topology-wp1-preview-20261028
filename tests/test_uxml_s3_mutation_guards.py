"""Exact-code kill tests for S3 read-only InputXML guards (PUBLIC XCU fixtures only).

Every test verifies ONE named refusal rather than treating arbitrary ValueError
as a pass. No original file is written or published; no Owner sources are used.
"""
from __future__ import annotations

from copy import deepcopy
import json
import importlib
import inspect
import io
from unittest import mock
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from converters.psi116_topology_resolver.uxml_adapter import (
    UxmlPsi116Error, document_from_uxml, resolve_from_uxml,
)
from converters.psi116_topology_resolver.uxml_compare import compare_cross_format_uxml
from converters.psi116_topology_resolver.uxml_edit_ops import (
    UxmlPatchError, apply_edit_ops, compare_patch_to_direct, export_edit_ops,
)
from converters.psi116_topology_resolver.resolver import resolve_psi116
from converters.psi116_topology_resolver.transaction import (
    TransactionPolicy, apply_topofix_transaction,
)

PSI_NAME = "uxml-s3-synthetic.psi116.xml"
INPUT_NAME = "uxml-s3-synthetic.workspace.input.xml"
DELTA_NAME = "uxml-s3-synthetic.workspace.delta-only.input.xml"


class S3ExactCodeGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xcu = Path(os.environ.get("XCU_UXML_ROOT") or "/nonexistent")
        if not (cls.xcu / "tools" / "inputxml-to-uxml.mjs").is_file():
            raise unittest.SkipTest("Pinned XCU strict S3 reader required for public source-backed mutation tests")
        def read(source_name, cli):
            source = cls.xcu / "tests" / "fixtures" / source_name
            process = subprocess.run(["node", str(cls.xcu/"tools"/cli), str(source)],
                                     cwd=cls.xcu, capture_output=True, text=True, timeout=60)
            if process.returncode:
                raise AssertionError("PUBLIC_XCU_FIXTURE_READER_FAILED: " + process.stderr)
            return json.loads(process.stdout)
        cls.psi = read(PSI_NAME, "psi116-to-uxml.mjs")
        cls.input = read(INPUT_NAME, "inputxml-to-uxml.mjs")
        cls.delta = read(DELTA_NAME, "inputxml-to-uxml.mjs")
        cls.original = cls.xcu / "tests" / "fixtures" / INPUT_NAME

    def exact(self, code, function, error=UxmlPsi116Error):
        with self.assertRaises(error) as caught:
            function()
        self.assertEqual(str(caught.exception), code)

    def key(self, hub, index):
        return hub["components"][index]["sourceRefs"][0]["recordKey"]

    def test_malformed_non_dict_source_entry_is_named_refusal(self):
        hub = deepcopy(self.input)
        hub["sources"][0] = ["malformed", "source"]
        self.exact("UXML_SOURCE_ENTRY_INVALID", lambda: document_from_uxml(hub))
        self.exact("UXML_SOURCE_ENTRY_INVALID", lambda: resolve_from_uxml(hub))

    def test_M04_inputxml_nonfirst_source_still_refuses_edit_export(self):
        hub = deepcopy(self.input)
        hub["sources"] = [deepcopy(self.psi["sources"][0]), hub["sources"][0]]
        self.exact("INPUT_XML_APPLY_NOT_ENABLED",
                   lambda: export_edit_ops(hub), UxmlPatchError)

    def test_M04_real_public_inputxml_hub_refuses_every_ops_api(self):
        hub = deepcopy(self.input)
        self.exact("INPUT_XML_APPLY_NOT_ENABLED", lambda: export_edit_ops(hub), UxmlPatchError)
        payload = {"schema":"uxml-edit-ops/v1", "sourceFormat":"INPUT_XML",
                   "fileSha256":hub["sources"][0]["hash"],"ops":[]}
        original = self.original.read_bytes()
        self.exact("INPUT_XML_APPLY_NOT_ENABLED",
                   lambda: apply_edit_ops(self.original, hub, payload), UxmlPatchError)
        self.exact("INPUT_XML_APPLY_NOT_ENABLED",
                   lambda: compare_patch_to_direct(self.original, hub, payload), UxmlPatchError)
        self.assertEqual(self.original.read_bytes(), original)

    def test_M05_all_unanchored_cross_runs_refuse_global_resolution(self):
        hub = deepcopy(self.delta)
        runs = hub["inputXml"]["runs"]
        self.assertGreater(len(runs), 1, "the public delta fixture must include separate runs")
        for run in runs:
            run["anchored"] = False
        self.exact("INPUT_XML_CROSS_UNANCHORED_RUN_GAP_PROXIMITY_JOIN_REFUSED",
                   lambda: resolve_from_uxml(hub))

    def test_M06_changed_source_text_with_original_sha_refused(self):
        hub = deepcopy(self.input)
        hub["sources"][0]["sourceText"] += " "
        self.exact("INPUT_XML_ORIGINAL_SOURCE_SHA256_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_M07_delta_provenance_refuses_mismatched_source_sha(self):
        hub = deepcopy(self.input)
        hub["inputXml"]["sourceSha256"] = "0" * 64
        self.exact("INPUT_XML_DELTA_PROVENANCE_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_M09_delta_sum_guard_has_no_secondary_coordinate_drift(self):
        hub = deepcopy(self.delta)
        self.assertTrue(all(not r["anchored"] for r in hub["inputXml"]["runs"]))
        comp = hub["components"][-1]
        info = comp["rawAttributes"]["inputXml"]
        port = next(p for p in hub["ports"]
                    if p["componentId"] == comp["id"] and
                    p["sourceRefs"][0]["endpoint"] == "TO")
        port["point"]["x"] += 7
        info["to"]["x"] += 7  # typed coordinate remains sourceRef-consistent
        self.exact("INPUT_XML_DELTA_SUM_MISMATCH:" + self.key(hub, len(hub["components"])-1),
                   lambda: document_from_uxml(hub))

    def test_M10_absolute_anchor_refuses_coherently_shifted_ports(self):
        hub = deepcopy(self.input)
        anchored = next(run["id"] for run in hub["inputXml"]["runs"] if run["anchored"])
        components = {c["id"]: c for c in hub["components"]
                      if c["sourceRefs"][0]["runId"] == anchored}
        self.assertTrue(components)
        for port in hub["ports"]:
            if port["componentId"] in components:
                port["point"]["x"] += 7
        for comp in components.values():
            info = comp["rawAttributes"]["inputXml"]
            info["from"]["x"] += 7
            info["to"]["x"] += 7
        # Delta lengths are unchanged and every shared node is shifted together;
        # only literal original absolute anchors remain at their old coordinates.
        root = ET.fromstring(hub["sources"][0]["sourceText"])
        rows = [element for element in root.iter()
                if element.tag.rsplit("}", 1)[-1].upper() == "PIPINGELEMENT"]
        expected = None
        for index, comp in enumerate(hub["components"]):
            if comp["sourceRefs"][0]["runId"] != anchored:
                continue
            for endpoint in ("FROM", "TO"):
                if all(rows[index].get(endpoint + axis) is not None
                       for axis in ("_X", "_Y", "_Z")):
                    expected = ("INPUT_XML_ABSOLUTE_ANCHOR_MISMATCH:" +
                                self.key(hub, index) + ":" + endpoint)
                    break
            if expected is not None:
                break
        self.assertIsNotNone(expected, "public anchored run must have a literal XYZ")
        self.exact(expected, lambda: document_from_uxml(hub))

    def test_M11_false_anchored_run_requires_real_original_absolute_anchor(self):
        hub = deepcopy(self.delta)
        run = next(row for row in hub["inputXml"]["runs"] if not row["anchored"])
        run["anchored"] = True
        for comp in hub["components"]:
            if comp["sourceRefs"][0]["runId"] != run["id"]:
                continue
            comp["sourceRefs"][0]["anchored"] = True
            comp["rawAttributes"]["inputXml"]["anchored"] = True
        for port in hub["ports"]:
            if port["sourceRefs"][0]["runId"] == run["id"]:
                port["sourceRefs"][0]["anchored"] = True
                port["anchored"] = True
        # The source-derived run-partition gate now refuses a forged anchor
        # before any downstream, redundant false-anchor consistency check.
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_M12_all_unanchored_cross_format_refuses_absolute_comparison(self):
        hub = deepcopy(self.delta)
        self.assertTrue(all(not run["anchored"] for run in hub["inputXml"]["runs"]))
        self.exact("CROSS_FORMAT_UNANCHORED_ABSOLUTE_FRAME_COMPARISON_REFUSED",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_M13_cross_format_checks_first_source_is_psi116(self):
        bad_psi = deepcopy(self.psi)
        bad_psi["sources"][0]["format"] = "INPUT_XML"
        self.exact("CROSS_FORMAT_PSI116_SOURCE_REQUIRED",
                   lambda: compare_cross_format_uxml(bad_psi, self.input))

    def test_M15_port_source_ref_exact_sha_and_endpoint(self):
        hub = deepcopy(self.input)
        hub["ports"][0]["sourceRefs"][0]["fileSha256"] = "0" * 64
        self.exact("INPUT_XML_PORT_SOURCE_REF_MISMATCH:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_M16_inherited_physical_provenance_keeps_original_evidence(self):
        hub = deepcopy(self.input)
        target = hub["components"][1]["rawAttributes"]["inputXml"]
        target["physicalEvidence"]["outsideDiameter"]["value"] = 777
        self.exact("INPUT_XML_PHYSICAL_PROVENANCE_MISMATCH:" + self.key(hub, 1),
                   lambda: document_from_uxml(hub))

    def test_M17_sif_type_conflict_must_not_forge_tee(self):
        hub = deepcopy(self.input)
        row = next((i for i, comp in enumerate(hub["components"])
                    if any(sif.get("typeCode") == 5 and
                           sif.get("node") == comp["rawAttributes"]["inputXml"].get("toNode")
                           for sif in (comp["rawAttributes"]["inputXml"].get("sifEvidence") or []))),
                   None)
        self.assertIsNotNone(row, "public source must include a TO-owned OLET SIF type 5")
        hub["components"][row]["rawAttributes"]["inputXml"]["componentType"] = "TEE"
        self.exact("INPUT_XML_SIF_COMPONENT_TYPE_CONFLICT:" + self.key(hub, row),
                   lambda: document_from_uxml(hub))

    def test_M18_original_refno_not_invented_by_hub(self):
        hub = deepcopy(self.input)
        hub["components"][0]["refNo"] = "SYNTHETIC_FORGED_REF"
        self.exact("INPUT_XML_UNAUTHORIZED_COMPONENT_REFERENCE:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_R1_native_apply_refuses_real_inputxml_uxml_result(self):
        result = resolve_from_uxml(self.input)
        self.exact("INPUT_XML_APPLY_NOT_ENABLED",
                   lambda: apply_topofix_transaction(
                       result, policy=TransactionPolicy(apply_all_safe=True)),
                   ValueError)

    def test_R1_native_apply_refuses_real_raw_inputxml_path(self):
        original = self.original.read_bytes()
        self.exact("INPUT_XML_APPLY_NOT_ENABLED",
                   lambda: apply_topofix_transaction(
                       self.original, policy=TransactionPolicy(apply_all_safe=True)),
                   ValueError)
        self.assertEqual(self.original.read_bytes(), original)

    def test_R1_native_apply_refuses_raw_inputxml_text(self):
        source_text = self.original.read_text(encoding="utf-8")
        self.exact("INPUT_XML_APPLY_NOT_ENABLED",
                   lambda: apply_topofix_transaction(
                       source_text, policy=TransactionPolicy(apply_all_safe=True)),
                   ValueError)

    def test_R2_native_resolver_api_refuses_inputxml_path(self):
        self.exact("INPUT_XML_NATIVE_PSI116_RESOLVER_NOT_ENABLED",
                   lambda: resolve_psi116(self.original), ValueError)

    def test_R2_native_resolver_cli_refuses_without_sidecars(self):
        original = self.original.read_bytes()
        with tempfile.TemporaryDirectory(prefix="public-inputxml-native-refuse-") as folder:
            process = subprocess.run(
                [sys.executable, "-m", "converters.psi116_topology_resolver.resolver",
                 str(self.original), "--output-dir", folder],
                cwd=ROOT, capture_output=True, text=True, timeout=60,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("INPUT_XML_NATIVE_PSI116_RESOLVER_NOT_ENABLED",
                          process.stderr + process.stdout)
            self.assertEqual(list(Path(folder).iterdir()), [])
        self.assertEqual(self.original.read_bytes(), original)



class S3Step2BDeleteOneGuardMutants(unittest.TestCase):
    """Real executable single-guard bypass mutants, not static source inspection.

    Every matrix witness first executes GREEN unchanged, then runs with one
    exact named _need/raise guard bypassed. A surviving mutant makes this suite
    fail. No source files or installed modules are changed on disk.
    """
    @classmethod
    def setUpClass(cls):
        cls.cases = importlib.import_module("test_uxml_s3_final_hold_guards")
        cls.cases.FinalInputXmlHoldGuards.setUpClass()

    def scenario(self, test_name):
        return getattr(self.cases.FinalInputXmlHoldGuards(), test_name)

    def must_go_red(self, scenario):
        try:
            scenario()
        except Exception as error:
            self.assertNotIsInstance(error, unittest.SkipTest)
            return
        self.fail("DELETE_ONE_GUARD_MUTANT_SURVIVED: " + scenario.__name__)

    def test_16_adapter_named_guard_deletions_have_green_control_red_mutant(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        matrix = (
            ("INPUT_XML_RUN_PARTITION_MISMATCH",
             "test_IA1_single_run_delta_only_forgery_partition_refused"),
            ("INPUT_XML_NODE_LITERAL_ALIAS",
             "test_IA5_integer_alias_30_vs_30_000000_refuses"),
            ("INPUT_XML_INVALID_NODE_NUMBER",
             "test_IA4_fractional_100_5_node_number_refuses_without_truncation"),
            ("INPUT_XML_RUN_ID_NOT_FOUND",
             "test_IA4_unknown_run_id_refuses_instead_of_empty_findings"),
            ("INPUT_XML_INCOMPLETE_ABSOLUTE_ANCHOR",
             "test_IA2_incomplete_absolute_anchor_is_named"),
            ("INPUT_XML_INVALID_NUMBER",
             "test_IA2_invalid_non_numeric_anchor_is_named"),
            ("INPUT_XML_NONFINITE_ABSOLUTE_ANCHOR",
             "test_IA2_nonfinite_absolute_anchor_is_named"),
            ("INPUT_XML_RUN_IDENTITY_INVALID",
             "test_B2_run_identity_required"),
            ("INPUT_XML_RUN_COVERAGE_INCOMPLETE",
             "test_B2_run_coverage_must_be_complete"),
            ("INPUT_XML_RUN_FRAME_INVALID",
             "test_B2_run_frame_cross_unanchored_policy_required"),
            ("INPUT_XML_RAW_RECORD_ID_MISMATCH",
             "test_B2_raw_record_identity_cannot_drift"),
            ("INPUT_XML_NESTED_SOURCE_EVIDENCE_MISMATCH",
             "test_B2_nested_source_bend_evidence_cannot_drift"),
            ("INPUT_XML_PORT_FRAME_MISMATCH",
             "test_B2_port_coordinate_frame_cannot_drift"),
            ("INPUT_XML_DELTA_PATH_CONFLICT",
             "test_B2_delta_path_conflict_between_shared_node_ports"),
            ("INPUT_XML_BEND_COMPONENT_TYPE_CONFLICT",
             "test_B2_bend_component_type_from_original_source"),
            ("INPUT_XML_CROSS_UNANCHORED_RUN_GAP_PROXIMITY_JOIN_REFUSED",
             "test_B1_M05_mixed_anchored_unanchored_resolve_refusal"),
        )
        self.assertEqual(len(matrix), 16)
        original_need = adapter._need
        for code, name in matrix:
            with self.subTest(guard=code):
                witness = self.scenario(name)
                witness()  # GREEN control
                if code == "INPUT_XML_CROSS_UNANCHORED_RUN_GAP_PROXIMITY_JOIN_REFUSED":
                    original = inspect.getsource(adapter.resolve_from_uxml)
                    needle = ("raise UxmlPsi116Error("
                              "'INPUT_XML_CROSS_UNANCHORED_RUN_GAP_PROXIMITY_JOIN_REFUSED')")
                    self.assertEqual(original.count(needle), 1)
                    modified = original.replace(needle, "pass  # DELETE_ONE_GUARD")
                    scope = {}
                    exec(compile(modified, "<mutant-run-proximity>", "exec"),
                         adapter.__dict__, scope)
                    with mock.patch.object(self.cases, "resolve_from_uxml",
                                           scope["resolve_from_uxml"]):
                        self.must_go_red(witness)
                    continue
                deleted = [0]
                def delete_one(ok, reason):
                    if (not ok and deleted[0] == 0 and
                            reason.split(":", 1)[0] == code):
                        deleted[0] += 1
                        return None  # DELETE ONE failing named _need guard
                    return original_need(ok, reason)
                with mock.patch.object(adapter, "_need", side_effect=delete_one):
                    self.must_go_red(witness)
                self.assertEqual(deleted, [1], code + ":MUTANT_NEVER_EXERCISED")
                print("MUTANT_RED:ADAPTER:" + code)

    def test_4_crossformat_checks_each_have_green_control_red_mutant(self):
        from converters.psi116_topology_resolver import uxml_compare as compare
        matrix = (
            ("CROSS_FORMAT_PSI116_SOURCE_REQUIRED",
             "test_IA4_crossformat_requires_psi116_source"),
            ("CROSS_FORMAT_INPUT_XML_SOURCE_REQUIRED",
             "test_B2_crossformat_requires_inputxml_source"),
            ("CROSS_FORMAT_HUB_FRAME_UNVERIFIED",
             "test_B2_crossformat_requires_verified_hub_frame"),
            ("CROSS_FORMAT_UNANCHORED_ABSOLUTE_FRAME_COMPARISON_REFUSED",
             "test_B1_M12_mixed_anchored_unanchored_crossformat_refusal"),
        )
        self.assertEqual(len(matrix), 4)
        source = inspect.getsource(compare.compare_cross_format_uxml)
        marker = ('    _need = lambda condition, code: (\n'
                  '        None if condition else (_ for _ in ()).throw(UxmlPsi116Error(code)))')
        self.assertEqual(source.count(marker), 1)
        for code, name in matrix:
            with self.subTest(compare_guard=code):
                witness = self.scenario(name)
                witness()  # GREEN control
                mutant_source = source.replace(
                    marker, marker + "\n    _original_gate = _need"
                    + "\n    _need = lambda condition, code: ("
                    + "None if code == " + repr(code)
                    + " else _original_gate(condition, code))")
                scope = {}
                exec(compile(mutant_source, "<mutant-crossformat>", "exec"),
                     compare.__dict__, scope)
                with mock.patch.object(self.cases, "compare_cross_format_uxml",
                                       scope["compare_cross_format_uxml"]):
                    self.must_go_red(witness)
                print("MUTANT_RED:COMPARE:" + code)

    def test_native_apply_guard_deleted_witness_goes_red(self):
        from converters.psi116_topology_resolver import transaction
        witness = lambda: self._require_native_inputxml_apply_hold(transaction)
        witness()
        with mock.patch.object(transaction, "_refuse_inputxml_native_apply",
                               lambda source: None):
            self.must_go_red(witness)
        print("MUTANT_RED:NATIVE_APPLY:INPUT_XML_APPLY_NOT_ENABLED")

    def _require_native_inputxml_apply_hold(self, transaction):
        source = self.cases.FinalInputXmlHoldGuards.input_path
        with self.assertRaises(ValueError) as rejected:
            transaction.apply_topofix_transaction(
                source, policy=transaction.TransactionPolicy(apply_all_safe=True))
        self.assertEqual(str(rejected.exception), "INPUT_XML_APPLY_NOT_ENABLED")

    def test_two_cli_entrypoint_guards_deleted_witnesses_go_red(self):
        from converters.psi116_topology_resolver import (
            uxml_export_ops, uxml_patch_psi116,
        )
        for module in (uxml_export_ops, uxml_patch_psi116):
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory(prefix="public-s3-cli-mutant-") as tmp:
                    source = self.cases.FinalInputXmlHoldGuards.input_path
                    ops = Path(tmp) / "ops.json"
                    argv = [str(source), str(ops), "--xcu-root", str(Path(tmp)/"missing-xcu")]
                    def witness():
                        capture = io.StringIO()
                        with mock.patch("sys.stdout", capture):
                            returned = module.main(argv)
                        self.assertEqual(returned, 1)
                        self.assertEqual(capture.getvalue().strip().splitlines(),
                                         ["DIFFERENT", "ERROR: INPUT_XML_APPLY_NOT_ENABLED"])
                        self.assertFalse(ops.exists())
                    witness()  # GREEN control
                    with mock.patch.object(module, "_refuse_inputxml_native_apply",
                                           lambda original: None):
                        self.must_go_red(witness)
                print("MUTANT_RED:CLI:" + module.__name__)


if __name__ == "__main__":
    unittest.main()
