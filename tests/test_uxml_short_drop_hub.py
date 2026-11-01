"""Synthetic-only UXML short drop: one explicit owner, exact sourceRefs and native equality."""
from copy import deepcopy
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
