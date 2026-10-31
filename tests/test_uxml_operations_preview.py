"""UXML-PREVIEW: public synthetic authoritative S2 envelope vs read-only rows.

No Owner files. The external XCU reader is required for qualified comparisons.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "converters"))
from psi116_topology_resolver.resolver import resolve_psi116
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.uxml_edit_ops import export_edit_ops
from psi116_topology_resolver.uxml_operations_preview import build_operation_preview
from test_uxml_psi116_s1 import verified_synthetic
from test_port_policy import pipe_flange


class UxmlPreviewReadOnlyContract(unittest.TestCase):
    def test_every_preview_row_matches_export_ops_and_native_before_after(self):
        root = os.environ.get("XCU_UXML_ROOT")
        if not root or not (Path(root)/"tools"/"psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned external XCU_UXML_ROOT required for qualified fixture")
        with tempfile.TemporaryDirectory(prefix="uxml-preview-public-") as temp:
            original = Path(temp)/"synthetic.xml"
            raw = verified_synthetic(pipe_flange(25)).encode("utf-8")
            original.write_bytes(raw)
            cli = subprocess.run(
                ["node", str(Path(root)/"tools"/"psi116-to-uxml.mjs"), str(original)],
                cwd=root, capture_output=True, text=True, timeout=45, check=False,
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            uxml = json.loads(cli.stdout)
            ops = export_edit_ops(uxml, source_name=str(original))
            self.assertGreater(len(ops["ops"]), 0,
                               "fixture must produce a real source-bound Auto fix")
            rows = build_operation_preview(uxml, source_name=str(original))
            self.assertEqual(rows["schema"], "uxml-operations-preview/v1")
            self.assertEqual(rows["sourceSha256"], ops["fileSha256"])
            self.assertEqual(rows["summary"]["totalOps"], len(ops["ops"]))
            self.assertEqual(
                rows["summary"]["byKind"],
                dict(sorted(Counter(op["kind"] for op in ops["ops"]).items())),
            )
            self.assertEqual(
                [row["opId"] for row in rows["ops"]],
                [op["opId"] for op in ops["ops"]],
            )
            self.assertEqual(
                [row["kind"] for row in rows["ops"]],
                [op["kind"] for op in ops["ops"]],
            )
            self.assertEqual(
                [[rec["recordKey"] for rec in row["sourceRecords"]]
                 for row in rows["ops"]],
                [op["targets"] for op in ops["ops"]],
            )
            by_id = {op["opId"]: op for op in ops["ops"]}
            edited = set()
            for row in rows["ops"]:
                source = by_id[row["opId"]]
                self.assertEqual(row["sourceActionId"], source["sourceActionId"])
                self.assertTrue(row["uxmlIds"])
                self.assertGreaterEqual(len(row["changes"]), 1)
                self.assertIn("0.95", row["policyReason"])
                self.assertNotIn("CONFLICTS_WITH_CLOS", row["kind"])
                for change in row["changes"]:
                    edited.add(change["recordKey"])
                    self.assertIn(change["recordKey"], source["targets"])
                    self.assertIn(change["field"], ("Position", "NodeNumber",
                                                    "Rigid", "Source record"))
                    self.assertNotEqual(change["before"], change["after"])

            # Use existing native public transaction as a truth oracle; it may
            # modify its own isolated clone, never the original source file.
            selected = tuple(op["sourceActionId"] for op in ops["ops"])
            direct = apply_topofix_transaction(resolve_psi116(original),
                    policy=TransactionPolicy(selected_action_ids=selected))
            self.assertTrue(direct.committed, direct.reject_reasons)
            native_changes = {}
            for applied in direct.operations:
                fields = set(applied.after) if isinstance(applied.after, dict) \
                         else ({'NodeNumber'} if applied.operation == 'ALIAS_NODE_NUMBER'
                               else {'Rigid'} if applied.operation == 'SET_RIGID_ZERO'
                               else {'Source record'})
                for field in fields:
                    before = applied.before.get(field) if isinstance(applied.before, dict) \
                             else applied.before
                    after = applied.after.get(field) if isinstance(applied.after, dict) \
                            else applied.after
                    if before is None and field == 'Source record':
                        before,after = 'Present','Removed'
                    if before is not None and after is not None:
                        before,after = str(before),str(after)
                    if before != after:
                        native_changes[(applied.action_id,applied.source_node_key,field)] = \
                            (before,after)
            shown_changes = {}
            for row in rows["ops"]:
                for change in row["changes"]:
                    shown_changes[(row["sourceActionId"],change["recordKey"],change["field"])] = \
                        (change["before"],change["after"])
            self.assertEqual(shown_changes, native_changes)
            self.assertEqual(rows["summary"]["untouchedRecordCount"],
                len(uxml["components"])-len(edited))
            self.assertEqual(original.read_bytes(),raw,
                             "read-only preview must never modify original bytes")
            self.assertEqual(sorted(item.name for item in Path(temp).iterdir()),
                             ["synthetic.xml"],"no patch/validation/output files written")

    def test_preview_builder_throw_keeps_hub_equal_and_native_auto_eligible(self):
        """Execute real embedded Python; only a read-only renderer is injected."""
        root = os.environ.get("XCU_UXML_ROOT")
        if not root or not (Path(root)/"tools"/"psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned external XCU_UXML_ROOT required for hub parity test")
        with tempfile.TemporaryDirectory(prefix="uxml-preview-failure-synthetic-") as temp:
            scratch = Path(temp)
            source = scratch/"synthetic.xml"
            raw = verified_synthetic(pipe_flange(25)).encode("utf-8")
            source.write_bytes(raw)
            cli = subprocess.run(
                ["node", str(Path(root)/"tools"/"psi116-to-uxml.mjs"), str(source)],
                cwd=root, capture_output=True, text=True, timeout=45, check=False,
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            doc = json.loads(cli.stdout)

            script = (REPO/"converters/xml-cii-2019-standalone/topology-integration.js").read_text(
                encoding="utf-8")
            match = re.search(r"const TOPOLOGY_SNIPPET = \x60\n(.*?)\n\x60;", script, re.S)
            self.assertIsNotNone(match, "Use actual published Pyodide code")
            snippet = match.group(1).replace("\\\\", "\\")
            paths = {name: scratch/(name + ".json") for name in
                     ("findings", "plan", "status")}
            context = {
                "job_topology_input_path": str(source),
                "job_topology_uxml_json": json.dumps(doc),
                "job_generate_topofix": False,
                "job_topology_findings_path": str(paths["findings"]),
                "job_topology_plan_path": str(paths["plan"]),
                "job_topology_status_path": str(paths["status"]),
                "job_connection_preview_json": "null",
            }
            with patch(
                "psi116_topology_resolver.uxml_operations_preview.build_operation_preview",
                side_effect=RuntimeError("SYNTHETIC_PREVIEW_BUILDER_THROW"),
            ):
                exec(compile(snippet, "<published-pyodide-topology-snippet>", "exec"),
                     context)
            status = json.loads(paths["status"].read_text(encoding="utf-8"))
            self.assertEqual(status["hubParity"], {"status": "EQUAL", "differences": []})
            self.assertEqual(
                status["opsPreview"]["error"],
                "UXML_OPS_PREVIEW_UNAVAILABLE:RuntimeError:SYNTHETIC_PREVIEW_BUILDER_THROW")
            self.assertFalse(status["committed"], "analyze is not an Apply call")
            plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
            self.assertTrue(any(
                action["status"] == "PROPOSED" and not action["blockers"] and
                action["confidence"] >= TransactionPolicy().minimum_confidence and
                action["disposition"] == "CLOSE_PORT_CONNECTION"
                for action in plan["actions"]),
                "native Auto-eligible actions must survive a preview display failure")
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual(
                sorted(item.name for item in scratch.iterdir()),
                ["findings.json", "plan.json", "status.json", "synthetic.xml"],
                "display failure must not write corrected XML or mutation receipts",
            )

    def test_preview_is_not_a_mutation_or_review_queue_api(self):
        import inspect
        import psi116_topology_resolver.uxml_operations_preview as module
        code=inspect.getsource(module)
        self.assertNotIn("apply_topofix_transaction",code)
        self.assertNotIn("write_topofix_outputs",code)
        self.assertNotIn("CONFLICTS_WITH_CLOS",module.NAMES)
        self.assertNotIn("CLOSE_CONFIRMED_PORT_CONNECTION",module.NAMES)


if __name__ == "__main__":
    unittest.main()
