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
             "test_IA1_all_anchored_mixed_runs_forged_as_one_merge_refused"),
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
                    print("MUTANT_RED:ADAPTER:" + code)
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

    @staticmethod
    def _source_guard_mutant(adapter, original, removed, case_name):
        if original.count(removed) != 1:
            raise AssertionError("SINGLE_EDIT_MUTANT_TARGET_NOT_UNIQUE:" + case_name)
        scope = {}
        exec(compile(original.replace(removed, ""), "<mutant-" + case_name + ">", "exec"),
             adapter.__dict__, scope)
        return scope["_document_from_caesar_inputxml"]

    def test_R2_B1_three_nested_type_guards_green_then_red(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        source = inspect.getsource(adapter._document_from_caesar_inputxml)
        matrix = (
            ("PORT_REF_DICT",
             '            _need(isinstance(refs[0], dict),\n'
             '                  "INPUT_XML_PORT_SOURCE_REF_MISMATCH:" + key)\n',
             "test_R2_B1a_non_dict_port_source_ref_exact"),
            ("RAW_ATTRIBUTES_DICT",
             '        _need(isinstance(raw_attributes, dict),\n'
             '              "INPUT_XML_RAW_RECORD_ID_MISMATCH:" + key)\n',
             "test_R2_B1b_non_dict_component_raw_attributes_exact"),
            ("INPUTXML_EVIDENCE_DICT",
             '        _need(isinstance(info, dict),\n'
             '              "INPUT_XML_RAW_RECORD_ID_MISMATCH:" + key)\n',
             "test_R2_B1c_non_dict_component_inputxml_evidence_exact"),
        )
        for name, single_guard, witness_name in matrix:
            with self.subTest(guard=name):
                witness = self.scenario(witness_name)
                witness()  # GREEN, exact named exception
                mutant = self._source_guard_mutant(adapter, source, single_guard, name)
                with mock.patch.object(adapter, "_document_from_caesar_inputxml", mutant):
                    self.must_go_red(witness)
                    if name == "PORT_REF_DICT":
                        self.must_go_red(self.scenario(
                            "test_R2_B1_all_inputxml_read_paths_are_named_on_type_fuzz"))
                print("MUTANT_RED:R2_B1:" + name, flush=True)

    def test_R2_B2_partition_count_guard_deleted_green_then_red(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        witness = self.scenario("test_R2_B2_extra_empty_run_requires_same_partition_count")
        witness()  # GREEN exact INPUT_XML_RUN_PARTITION_MISMATCH
        source = inspect.getsource(adapter._document_from_caesar_inputxml)
        deleted = "len(runs) == len(source_runs) and "
        mutant = self._source_guard_mutant(adapter, source, deleted, "B2_RUN_COUNT")
        with mock.patch.object(adapter, "_document_from_caesar_inputxml", mutant):
            self.must_go_red(witness)
        print("MUTANT_RED:R2_B2:PARTITION_RUN_COUNT", flush=True)

    def test_R2_B3_edgeCount_type_guard_deleted_float_and_bool_go_red(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        witnesses = (
            self.scenario("test_R2_B3_float_edgeCount_refuses_partition_type"),
            self.scenario("test_R2_B3_bool_edgeCount_refuses_partition_type"),
        )
        for witness in witnesses:
            witness()  # GREEN named partition refusal
        source = inspect.getsource(adapter._document_from_caesar_inputxml)
        deleted = 'type(run.get("edgeCount")) is int and\n              '
        mutant = self._source_guard_mutant(adapter, source, deleted, "B3_EDGECOUNT_TYPE")
        with mock.patch.object(adapter, "_document_from_caesar_inputxml", mutant):
            for label, witness in zip(("FLOAT", "BOOL"), witnesses):
                self.must_go_red(witness)
                print("MUTANT_RED:R2_B3:" + label + "_EDGECOUNT_TYPE", flush=True)

    @staticmethod
    def _r3_compiled_mutant(module, original_function, deleted, replacement, name):
        source = inspect.getsource(original_function)
        if source.count(deleted) != 1:
            raise AssertionError("R3_SINGLE_EDIT_NOT_UNIQUE:" + name)
        ns = {}
        exec(compile(source.replace(deleted, replacement), "<R3-" + name + ">", "exec"),
             module.__dict__, ns)
        return ns[original_function.__name__]

    def test_R3_C1_endpoint_guard_and_wide_fuzz_kill_one_edit(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        witness = self.scenario("test_R3_C1_nonstring_endpoints_each_named_beyond_first_port")
        wider = self.scenario("test_R2_B1_all_inputxml_read_paths_are_named_on_type_fuzz")
        witness()
        wider()
        deleted = 'isinstance(ep, str) and '
        mutant = self._r3_compiled_mutant(
            adapter, adapter._document_from_caesar_inputxml, deleted, "", "C1_ENDPOINT")
        with mock.patch.object(adapter, "_document_from_caesar_inputxml", mutant):
            self.must_go_red(witness)
            self.must_go_red(wider)
        print("MUTANT_RED:R3_C1:ENDPOINT_TYPE", flush=True)
        print("MUTANT_RED:R3_C5:WIDE_ENDPOINT_FUZZ", flush=True)

    def test_R3_C2_sourceAttributes_guard_and_wide_fuzz_kill_one_edit(self):
        from converters.psi116_topology_resolver import uxml_compare as compare
        witness = self.scenario(
            "test_R3_C2_sourceAttributes_shape_refused_for_every_component_in_compare")
        wider = self.scenario("test_R2_B1_all_inputxml_read_paths_are_named_on_type_fuzz")
        witness()
        wider()
        deleted = (
            '        _need(info.get("sourceAttributes") is None or\n'
            '              isinstance(info.get("sourceAttributes"), dict),\n'
            '              "CROSS_FORMAT_SOURCE_ATTRIBUTES_INVALID")\n'
        )
        mutant = self._r3_compiled_mutant(
            compare, compare.compare_cross_format_uxml,
            deleted, "", "C2_SOURCE_ATTRIBUTES")
        with mock.patch.object(compare, "compare_cross_format_uxml", mutant), \
             mock.patch.object(self.cases, "compare_cross_format_uxml", mutant):
            self.must_go_red(witness)
            self.must_go_red(wider)
        print("MUTANT_RED:R3_C2:SOURCE_ATTRIBUTES", flush=True)
        print("MUTANT_RED:R3_C5:WIDE_SOURCE_ATTRIBUTES_FUZZ", flush=True)

    def test_R3_C3_oversized_integer_guard_kills_single_edit(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        witness = self.scenario("test_R3_C3_oversized_honest_reader_node_literal_is_named")
        witness()
        deleted = (
            '    _need(len(value.split(".", 1)[0].lstrip("+-")) <= 9,\n'
            '          "INPUT_XML_INVALID_NODE_NUMBER:" + label)\n'
        )
        mutant = self._r3_compiled_mutant(
            adapter, adapter._caesar_int, deleted, "", "C3_DIGIT_BOUND")
        with mock.patch.object(adapter, "_caesar_int", mutant):
            self.must_go_red(witness)
        print("MUTANT_RED:R3_C3:OVERSIZED_INTEGER", flush=True)

    def test_R3_C4_four_guard_families_each_have_exact_green_red(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        from converters.psi116_topology_resolver import uxml_compare as compare
        docs = (
            ("RUN_ELEMENT_INDICES",
             "test_R3_C4_swapped_run_element_indices_refused",
             adapter, adapter._document_from_caesar_inputxml,
             '"id", "elementIndices", "edgeCount",',
             '"id", "edgeCount",',
             "_document_from_caesar_inputxml"),
            ("COMPONENT_TYPE_STR",
             "test_R3_C4_component_type_nonstring_later_components_refused",
             adapter, adapter._document_from_caesar_inputxml,
             '        _need(isinstance(info.get("componentType"), str),\n'
             '              "INPUT_XML_RAW_RECORD_ID_MISMATCH:" + key)\n',
             "",
             "_document_from_caesar_inputxml"),
        )
        for label, case, module, original, before, after, target in docs:
            with self.subTest(guard=label):
                witness = self.scenario(case)
                witness()
                mutant = self._r3_compiled_mutant(module, original, before, after, label)
                with mock.patch.object(module, target, mutant):
                    self.must_go_red(witness)
                print("MUTANT_RED:R3_C4:" + label, flush=True)

        original = compare.compare_cross_format_uxml
        source_guards = (
            ("FRAME_DICT", "test_R3_C4_compare_frame_dict_guard_refuses",
             '    _need(isinstance(frame, dict), "CROSS_FORMAT_HUB_FRAME_UNVERIFIED")\n'),
            ("PSI_SOURCES_LIST", "test_R3_C4_compare_sources_and_entries_refuse",
             '          isinstance(psi_uxml.get("sources"), list) and\n'),
            ("PSI_SOURCE_ENTRY", "test_R3_C4_compare_sources_and_entries_refuse",
             '          isinstance(psi_uxml["sources"][0], dict) and\n'),
            ("INPUT_SOURCES_LIST", "test_R3_C4_compare_sources_and_entries_refuse",
             '          isinstance(input_uxml.get("sources"), list) and\n'),
            ("INPUT_SOURCE_ENTRY", "test_R3_C4_compare_sources_and_entries_refuse",
             '          isinstance(input_uxml["sources"][0], dict) and\n'),
        )
        for label, case, deleted in source_guards:
            with self.subTest(guard=label):
                witness = self.scenario(case)
                witness()
                mutant = self._r3_compiled_mutant(
                    compare, original, deleted, "", label)
                with mock.patch.object(compare, "compare_cross_format_uxml", mutant), \
                     mock.patch.object(self.cases, "compare_cross_format_uxml", mutant):
                    self.must_go_red(witness)
                print("MUTANT_RED:R3_C4:" + label, flush=True)

    def test_A3_T1_to_only_anchor_from_only_mutant_red(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        witness = self.scenario("test_A3_T1_to_only_absolute_anchor_is_source_verified")
        witness()  # GREEN real public XCU strict reader and document/resolve
        mutant = self._r3_compiled_mutant(
            adapter, adapter._recompute_inputxml_runs,
            '_caesar_hub_absolute(attrs, "TO", index)))',
            "None))", "A3_T1_FROM_ONLY")
        with mock.patch.object(adapter, "_recompute_inputxml_runs", mutant):
            self.must_go_red(witness)
        print("MUTANT_RED:A3:T1_FROM_ONLY_ANCHOR", flush=True)

    def test_A3_T2_closed_cycle_union_find_mutant_red(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        witness = self.scenario("test_A3_T2_closed_loop_matches_xcu_partition_identity")
        witness()  # GREEN XCU reader order/indices/counts/firstNode/doc/resolve
        mutant = self._r3_compiled_mutant(
            adapter, adapter._recompute_inputxml_runs,
            '        if start != end:\n            parent[end] = start\n',
            '        if start == end:\n'
            '            parent.clear()  # MUTANT: destroy cycle union\n'
            '        if start != end:\n'
            '            parent[end] = start\n', "A3_T2_CYCLE_BREAK")
        with mock.patch.object(adapter, "_recompute_inputxml_runs", mutant):
            self.must_go_red(witness)
        print("MUTANT_RED:A3:T2_CYCLE_UNION", flush=True)

    def test_A3_T3_nine_digit_off_by_one_mutant_red(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        witness = self.scenario("test_A3_T3_exact_9_digit_caesar_node_boundary")
        witness()  # GREEN 999999999 accepted; 1000000000 named refusal
        mutant = self._r3_compiled_mutant(
            adapter, adapter._caesar_int,
            'len(value.split(".", 1)[0].lstrip("+-")) <= 9',
            'len(value.split(".", 1)[0].lstrip("+-")) <= 10',
            "A3_T3_BOUND_PLUS_ONE")
        with mock.patch.object(adapter, "_caesar_int", mutant):
            self.must_go_red(witness)
        print("MUTANT_RED:A3:T3_BOUND_OFF_BY_ONE", flush=True)

    def test_A3_T4_psi_hub_scope_and_branch_shape_mutants_red(self):
        from converters.psi116_topology_resolver import uxml_compare as compare
        witness = self.scenario("test_A3_T4_malformed_psi_hubs_named_in_compare_and_cli")
        witness()  # GREEN direct compare + CLI for 5 public malformed shapes
        guards = (
            ("SCOPE", '    _need(isinstance(psi_uxml.get("psi116"), dict),\n'
             '          "UXML_PSI116_PROVENANCE_MISMATCH")\n'),
            ("BRANCH_ENTRY", '    _need(isinstance(psi_uxml.get("pipelines"), list) and\n'
             '          all(isinstance(row, dict) for row in psi_uxml["pipelines"]),\n'
             '          "UXML_SOURCE_RECORD_COLLECTION_INVALID")\n'),
        )
        for label, removed in guards:
            with self.subTest(guard=label):
                mutant = self._r3_compiled_mutant(
                    compare, compare.compare_cross_format_uxml,
                    removed, "", "A3_T4_" + label)
                with mock.patch.object(compare, "compare_cross_format_uxml", mutant), \
                     mock.patch.object(self.cases, "compare_cross_format_uxml", mutant):
                    self.must_go_red(witness)
                print("MUTANT_RED:A3:T4_" + label, flush=True)

    def test_T1_honest_source_variants_each_kill_the_matching_mutant(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter

        # A7: falsely anchor a run at its first FROM, instead of the first
        # explicit XYZ anchor at element 2's FROM in the public source.
        witness = self.scenario("test_T1a_partial_anchored_firstNode_not_first_FROM_accepted")
        witness()  # GREEN exact document/finding parity
        source_recompute = adapter._recompute_inputxml_runs
        changed = [0]
        def wrong_first_node(rows):
            runs = source_recompute(rows)
            for run in runs:
                if run["anchored"]:
                    first = rows[run["elementIndices"][0]].attrib["FROM_NODE"]
                    if run["firstNode"] != first:
                        run["firstNode"] = first
                        changed[0] += 1
            return runs
        with mock.patch.object(adapter, "_recompute_inputxml_runs",
                               side_effect=wrong_first_node):
            self.must_go_red(witness)
        self.assertGreater(changed[0], 0, "T1a mutant was not exercised")
        print("MUTANT_RED:T1:A7_FIRST_ANCHOR_NOT_FIRST_FROM", flush=True)

        # A13: a case-sensitive original-source anchor lookup silently drops
        # the reader-accepted lowercase from_x/to_x attributes.
        witness = self.scenario("test_T1b_lowercase_absolute_xyz_accepted")
        witness()  # GREEN
        source_absolute = adapter._caesar_hub_absolute
        changed = [0]
        def uppercase_only(attrs, prefix, index=None):
            keys = {prefix + "_" + axis for axis in "XYZ"}
            dropped = {k for k in attrs if k.upper() in keys and k not in keys}
            if dropped:
                changed[0] += 1
            return source_absolute({k:v for k,v in attrs.items() if k not in dropped},
                                   prefix,index)
        with mock.patch.object(adapter, "_caesar_hub_absolute",
                               side_effect=uppercase_only):
            self.must_go_red(witness)
        self.assertGreater(changed[0], 0, "T1b mutant was not exercised")
        print("MUTANT_RED:T1:A13_LOWERCASE_SOURCE_ANCHORS", flush=True)

        # A14: a reader-incompatible untrimmed numeric interpretation drops
        # whitespace-padded XYZ values that XCU explicitly trims.
        witness = self.scenario("test_T1c_padded_absolute_xyz_values_accepted")
        witness()  # GREEN
        changed = [0]
        def no_trim(attrs, prefix, index=None):
            keys = {prefix + "_" + axis for axis in "XYZ"}
            if any(k.upper() in keys and v != v.strip() for k,v in attrs.items()):
                changed[0] += 1
                return None
            return source_absolute(attrs,prefix,index)
        with mock.patch.object(adapter, "_caesar_hub_absolute",
                               side_effect=no_trim):
            self.must_go_red(witness)
        self.assertGreater(changed[0], 0, "T1c mutant was not exercised")
        print("MUTANT_RED:T1:A14_PADDED_SOURCE_ANCHORS", flush=True)

    def test_T2_typed_hub_fields_each_kill_one_guard_deletion(self):
        from converters.psi116_topology_resolver import uxml_adapter as adapter
        original_need = adapter._need
        for name in ("test_T2_bool_element_index_refuses_partition_type",
                     "test_T2_float_nodeCount_refuses_partition_type"):
            with self.subTest(test=name):
                witness = self.scenario(name)
                witness()  # GREEN typed rejection
                deleted = [0]
                def drop_first_partition_guard(ok, reason):
                    if (not ok and not deleted[0] and
                            reason == "INPUT_XML_RUN_PARTITION_MISMATCH"):
                        deleted[0] += 1
                        return None  # one specific typed-receipt _need deletion
                    return original_need(ok, reason)
                with mock.patch.object(adapter, "_need",
                                       side_effect=drop_first_partition_guard):
                    self.must_go_red(witness)
                self.assertEqual(deleted, [1], "T2 mutant not exercised")
                print("MUTANT_RED:T2:" + name, flush=True)

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
