"""Synthetic-only UXML short drop: one explicit owner, exact sourceRefs and native equality."""
from copy import deepcopy
from dataclasses import replace as dataclass_replace
from unittest.mock import patch
import re
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.uxml_edit_ops import (
    export_edit_ops, apply_edit_ops, UxmlPatchError, compare_patch_to_direct,
)
from psi116_topology_resolver.uxml_operations_preview import build_operation_preview
from test_short_elements import fixture
from test_uxml_psi116_s1 import verified_synthetic


class UxmlShortDropHub(unittest.TestCase):
    def setUp(self):
        root = os.environ.get("XCU_UXML_ROOT")
        if not root or not (Path(root) / "tools" / "psi116-to-uxml.mjs").is_file():
            self.skipTest("Requires externally pinned XCU_UXML_ROOT reader")
        self.xcu = Path(root)

    def source(self, base):
        path = base / "synthetic-gasket.xml"
        data = verified_synthetic(fixture(3, "GASK", "<Weight>2.5</Weight>")).encode("utf-8")
        path.write_bytes(data)
        result = subprocess.run(["node", str(self.xcu / "tools" / "psi116-to-uxml.mjs"),
                                 str(path)], cwd=self.xcu,
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)
        uxml = json.loads(result.stdout)
        direct = resolve_psi116(path)
        row = next(r for r in short_elements(direct.document, ResolverConfig())
                   if r["componentRefNo"] == "SHORT")
        self.assertTrue(row["eligible"], row["reason"])
        request = {key: row[key] for key in ("id", "sourceSha256", "nodeKeys")}
        policy = TransactionPolicy(selected_action_ids=(row["id"],),
                                   short_element_requests=(request,))
        return path, data, uxml, policy, request

    def test_exact_gasket_owner_and_closure_patch_matches_direct_bytes(self):
        with tempfile.TemporaryDirectory(prefix="uxml-short-synthetic-") as temp:
            path, data, uxml, policy, request = self.source(Path(temp))
            ops = export_edit_ops(uxml, policy=policy, source_name=str(path))
            self.assertEqual(ops["schema"], "uxml-edit-ops/v1")
            self.assertEqual(len(ops["ops"]), 1)
            op = ops["ops"][0]
            self.assertEqual(op["kind"], "DROP_SHORT_ELEMENT")
            self.assertEqual(op["sourceActionId"], request["id"])
            self.assertTrue(set(request["nodeKeys"]).issubset(set(op["targets"])))
            self.assertEqual(op["params"][0]["request"], request)
            fields = {edit["field"] for edit in op["params"][0]["edits"]}
            self.assertIn("Source record", fields)
            self.assertTrue(fields.issubset({"Source record", "NodeNumber", "Position"}))
            patched, differences = compare_patch_to_direct(path, uxml, ops)
            self.assertEqual(differences, [])
            direct = apply_topofix_transaction(resolve_psi116(path), policy=policy)
            self.assertTrue(direct.committed)
            self.assertTrue(patched.committed)
            self.assertEqual(patched.fixed_xml.encode("utf-8"), direct.fixed_xml.encode("utf-8"))
            self.assertEqual(patched.validation_payload(), direct.validation_payload())
            self.assertEqual(path.read_bytes(), data)
            preview = build_operation_preview(uxml, source_name=str(path),
                                              short_requests=[request])
            short_rows = [r for r in preview["ops"] if r["kind"] == "DROP_SHORT_ELEMENT"]
            self.assertEqual(len(short_rows), 1)
            self.assertEqual(short_rows[0]["changes"], op["params"][0]["edits"])
            self.assertEqual({r["recordKey"] for r in short_rows[0]["sourceRecords"]},
                             set(op["targets"]))
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()),
                             ["synthetic-gasket.xml"])

    def test_unknown_kind_widening_and_target_drift_refused_without_output(self):
        with tempfile.TemporaryDirectory(prefix="uxml-short-refuse-") as temp:
            path, data, uxml, policy, request = self.source(Path(temp))
            valid = export_edit_ops(uxml, policy=policy, source_name=str(path))
            for mutation, code in [
                (lambda p: p["ops"][0].update(kind="DELETE_ANY_COMPONENT"), "UXML_SHORT_KIND_REFUSED"),
                (lambda p: p["ops"][0]["targets"].append("B0:N999:S999"),
                 "UXML_SHORT_TARGETS_OR_PARAMS_DIFFER_FROM_AUTHORITY"),
                (lambda p: p["ops"][0]["params"][0].update(lengthMm=100),
                 "UXML_SHORT_TARGETS_OR_PARAMS_DIFFER_FROM_AUTHORITY"),
                (lambda p: p["policy"].update(minimum_confidence=0),
                 "UXML_POLICY_WIDENING_REFUSED"),
                (lambda p: p["policy"].update(short_element_requests=[request, request]),
                 "UXML_SHORT_EXACT_ONE_REQUEST_REQUIRED"),
            ]:
                with self.subTest(code=code):
                    forged = deepcopy(valid)
                    mutation(forged)
                    with self.assertRaisesRegex(UxmlPatchError, code):
                        apply_edit_ops(path, uxml, forged)
                    self.assertEqual(path.read_bytes(), data)
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()),
                             ["synthetic-gasket.xml"])

    def test_loss_contract_vetoes_deleted_owner_and_retained_position_only(self):
        """Kill the short-path loss veto: touched source record/field refuses."""
        with tempfile.TemporaryDirectory(prefix="uxml-short-loss-synthetic-") as temp:
            path, original, uxml, policy, _ = self.source(Path(temp))
            valid = export_edit_ops(uxml, policy=policy, source_name=str(path))
            edits = valid["ops"][0]["params"][0]["edits"]
            removed_key = next(e["recordKey"] for e in edits
                               if e["field"] == "Source record")
            retained_key = next(e["recordKey"] for e in edits
                                if e["field"] == "Position")
            self.assertNotEqual(removed_key, retained_key)
            parsed = resolve_psi116(path)
            paths = __import__(
                "psi116_topology_resolver.uxml_edit_ops",
                fromlist=["_source_record_paths"])._source_record_paths(
                    parsed.document.source_text, parsed)
            self.assertIn(removed_key, paths)
            self.assertIn(retained_key, paths)
            original_losses = deepcopy(uxml["lossContract"])
            for source_path in (paths[removed_key],
                                paths[retained_key] + "/Position[1]"):
                with self.subTest(sourcePath=source_path):
                    tampered = deepcopy(uxml)
                    tampered["lossContract"] = original_losses + [{
                        "details": {"sourcePath": source_path},
                        "code": "SYNTHETIC_LOSS_CONTRACT"}]
                    with self.assertRaisesRegex(
                            UxmlPatchError, "UXML_LOSS_CONTRACT_FIELD_TOUCH"):
                        export_edit_ops(tampered, policy=policy,
                                        source_name=str(path))
                    with self.assertRaisesRegex(
                            UxmlPatchError, "UXML_LOSS_CONTRACT_FIELD_TOUCH"):
                        apply_edit_ops(path, tampered, valid)
                    self.assertEqual(path.read_bytes(), original)
            # Negative control: a retained record's original OD is not
            # rewritten by short-element closure (only Position/NodeNumber).
            safe = deepcopy(uxml)
            safe["lossContract"] = original_losses + [{
                "details": {"sourcePath": paths[retained_key] +
                            "/OutsideDiameter[1]"},
                "code": "SYNTHETIC_UNTOUCHED_FIELD"}]
            exported = export_edit_ops(safe, policy=policy, source_name=str(path))
            patched = apply_edit_ops(path, safe, exported)
            self.assertTrue(patched.committed, patched.reject_reasons)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()),
                             ["synthetic-gasket.xml"])

    def test_python_parity_helper_and_real_worker_snippet_block_mutant(self):
        """Mutant patched bytes cannot be published by the actual Worker snippet."""
        with tempfile.TemporaryDirectory(prefix="uxml-short-patch-mutant-") as temp:
            path, original, uxml, policy, request = self.source(Path(temp))
            native = apply_topofix_transaction(resolve_psi116(path), policy=policy)
            self.assertTrue(native.committed)
            ops = export_edit_ops(uxml, policy=policy, source_name=str(path))
            patched = apply_edit_ops(path, uxml, ops)
            self.assertEqual([], __import__(
                "psi116_topology_resolver.uxml_edit_ops",
                fromlist=["compare_hub_patch"]).compare_hub_patch(native, patched))
            mutant = dataclass_replace(patched, fixed_xml=patched.fixed_xml + " ")
            differences = __import__(
                "psi116_topology_resolver.uxml_edit_ops",
                fromlist=["compare_hub_patch"]).compare_hub_patch(native, mutant)
            self.assertTrue(any("PATCH_BYTES_DIFFER_FROM_DIRECT" in x
                                for x in differences))
            script = (Path(__file__).resolve().parents[1] /
                      "converters/xml-cii-2019-standalone/topology-integration.js"
                      ).read_text(encoding="utf-8")
            match = re.search(r"const TOPOLOGY_SNIPPET = `\n(.*?)\n`;", script, re.S)
            self.assertIsNotNone(match)
            snippet = match.group(1).replace("\\\\", "\\")
            self.assertIn("differences = compare_hub_patch(direct_transaction, patched)",
                          snippet, "Worker MUST consult the Python comparison guard")
            names = ("findings", "plan", "transaction", "validation", "fixed",
                     "lineage", "handoff", "post_findings", "post_plan", "status")
            context = {
                "job_topology_input_path": str(path),
                "job_topology_uxml_json": json.dumps(uxml),
                "job_generate_topofix": True,
                "job_topology_action_ids": [request["id"]],
                "job_short_elements_json": json.dumps([request]),
                "job_short_preview_json": "[]",
                "job_joint_repairs_json": "[]",
                "job_connection_preview_json": "null",
            }
            for name in names:
                context["job_topology_" + name + "_path"] = str(Path(temp) /
                                                               ("out-" + name))
            # The main Worker snippet uses these particular variable names.
            context["job_topology_fixed_path"] = str(Path(temp) / "out-fixed")
            context["job_topology_handoff_path"] = str(Path(temp) / "out-handoff")
            context["job_topology_post_findings_path"] = str(Path(temp) / "out-post-findings")
            context["job_topology_post_plan_path"] = str(Path(temp) / "out-post-plan")
            with patch("psi116_topology_resolver.uxml_edit_ops.apply_edit_ops",
                       return_value=mutant):
                exec(compile(snippet, "<synthetic-worker-short-parity>", "exec"),
                     context)
            status = json.loads(Path(context["job_topology_status_path"]).read_text())
            self.assertEqual(status["hubParity"]["status"], "DIFFERENT")
            self.assertTrue(any("PATCH_BYTES_DIFFER_FROM_DIRECT" in x
                                for x in status["hubParity"]["differences"]))
            self.assertFalse(status["committed"])
            self.assertIn("UXML_PARITY_DIFFERENT_NO_DOWNLOAD", status["rejectReasons"])
            self.assertFalse(Path(context["job_topology_fixed_path"]).exists())
            self.assertFalse(Path(context["job_topology_lineage_path"]).exists())
            self.assertEqual(path.read_bytes(), original)

    def test_perturbed_uxml_cannot_patch_original_and_reports_drift(self):
        with tempfile.TemporaryDirectory(prefix="uxml-short-different-") as temp:
            path, data, uxml, policy, request = self.source(Path(temp))
            ops = export_edit_ops(uxml, policy=policy, source_name=str(path))
            tampered = deepcopy(uxml)
            tampered["sources"][0]["sourceText"] += " "
            with self.assertRaisesRegex(Exception, "UXML_ORIGINAL_SOURCE_SHA256_MISMATCH"):
                apply_edit_ops(path, tampered, ops)
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()),
                             ["synthetic-gasket.xml"])


if __name__ == "__main__":
    unittest.main()
