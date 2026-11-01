"""UXML-S2: independent direct-transaction comparator on pinned XCU synthetic XML.

The reader MUST come from an externally pinned XCU checkout (never vendored).
Native no-reader CI explicitly skips cross-repo tests; separate UXML-S2
workflow runs them with all seven Git blobs verified at exact XCU head.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver.models import ResolverConfig
from psi116_topology_resolver.resolver import resolve_psi116
from psi116_topology_resolver.transaction import (
    TransactionPolicy, apply_topofix_transaction, MUTATING_DISPOSITIONS,
)
from psi116_topology_resolver import uxml_edit_ops as bridge
from test_uxml_psi116_s1 import examples, verified_synthetic
from test_port_policy import pipe_flange
from test_source_preservation import source as preservation_source

REPO = Path(__file__).resolve().parents[1]


class UxmlS2PatchBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.environ.get("XCU_UXML_ROOT")
        cls.xcu_root = Path(root) if root else None
        cls.available = bool(cls.xcu_root and
                             (cls.xcu_root / "tools" / "psi116-to-uxml.mjs").is_file())

    def fixture(self, text: str, directory: Path, name: str):
        if not self.available:
            self.skipTest("Requires externally pinned XCU_UXML_ROOT reader")
        original = directory / (name + ".xml")
        original.write_bytes(verified_synthetic(text).encode("utf-8"))
        proc = subprocess.run(["node", str(self.xcu_root / "tools" / "psi116-to-uxml.mjs"),
                               str(original)], cwd=self.xcu_root,
                              capture_output=True, text=True, timeout=45)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        uxml = json.loads(proc.stdout)
        uxml_path = directory / (name + ".uxml.json")
        uxml_path.write_text(proc.stdout, encoding="utf-8")
        return original, uxml, uxml_path

    def first_positive(self, base: Path):
        file, uxml, path = self.fixture(pipe_flange(25), base, "port25")
        payload = bridge.export_edit_ops(uxml, source_name=str(file))
        self.assertGreater(len(payload["ops"]), 0, "known approved port repair required")
        direct = apply_topofix_transaction(resolve_psi116(file),
                    policy=bridge._policy_from_json(payload["policy"]))
        self.assertTrue(direct.committed, direct.reject_reasons)
        return file, uxml, path, payload, direct

    def test_every_synthetic_source_matches_original_transaction_xml_bytes_and_full_validation(self):
        if not self.available:
            self.skipTest("Requires pinned XCU reader")
        positive = 0
        with tempfile.TemporaryDirectory(prefix="uxml-s2-all-") as directory:
            base = Path(directory)
            for name, source in examples().items():
                with self.subTest(fixture=name):
                    file, uxml, _ = self.fixture(source, base, name)
                    ops = bridge.export_edit_ops(uxml, source_name=str(file))
                    self.assertEqual(ops["schema"], bridge.EDIT_OP_SCHEMA)
                    self.assertEqual(ops["fileSha256"], uxml["sources"][0]["hash"])
                    self.assertEqual(len(ops["ops"]),
                        len(set(op["sourceActionId"] for op in ops["ops"])))
                    for op in ops["ops"]:
                        self.assertIn(op["kind"], MUTATING_DISPOSITIONS)
                        self.assertTrue(op["targets"])
                        self.assertEqual(op["params"],
                          [dict(c) for c in next(a for a in resolve_psi116(file).fix_actions
                              if a.action_id == op["sourceActionId"]).proposed_changes])
                    patched, differences = bridge.compare_patch_to_direct(file, uxml, ops)
                    self.assertEqual(differences, [], "\n".join(differences))
                    if patched is None:
                        self.assertFalse(ops["ops"])
                    else:
                        direct = apply_topofix_transaction(resolve_psi116(file),
                            policy=bridge._policy_from_json(ops["policy"]))
                        self.assertEqual(patched.fixed_xml.encode("utf-8")
                            if patched.fixed_xml else None,
                            direct.fixed_xml.encode("utf-8")
                            if direct.fixed_xml else None)
                        self.assertEqual(patched.validation_payload(), direct.validation_payload())
                        if patched.committed:
                            positive += 1
                    self.assertEqual(file.read_bytes(),
                                     verified_synthetic(source).encode("utf-8"))
        self.assertGreater(positive, 0, "benchmark must not only test no-op/rejected cases")

    def test_file_sha_record_not_found_and_wrong_existing_target_are_refused(self):
        with tempfile.TemporaryDirectory(prefix="uxml-s2-negative-") as temp:
            file, uxml, _, ops, _ = self.first_positive(Path(temp))
            wrong = deepcopy(ops)
            wrong["ops"][0]["fileSha256"] = "0" * 64
            with self.assertRaisesRegex(bridge.UxmlPatchError, "UXML_FILE_SHA256_MISMATCH"):
                bridge.apply_edit_ops(file, uxml, wrong)
            wrong = deepcopy(ops)
            wrong["ops"][0]["targets"][0] = "B999:N999:S999"
            with self.assertRaisesRegex(bridge.UxmlPatchError, "UXML_TARGET_RECORD_NOT_FOUND"):
                bridge.apply_edit_ops(file, uxml, wrong)
            wrong = deepcopy(ops)
            expected = wrong["ops"][0]["targets"]
            alternative = next(c["sourceRefs"][0]["recordKey"] for c in uxml["components"]
                               if c["sourceRefs"][0]["recordKey"] not in expected)
            wrong["ops"][0]["targets"][0] = alternative
            with self.assertRaisesRegex(bridge.UxmlPatchError, "UXML_TARGETS_DIFFER_FROM_AUTHORITY"):
                bridge.apply_edit_ops(file, uxml, wrong)
            wrong = deepcopy(ops)
            wrong["fileSha256"] = "0" * 64
            with self.assertRaisesRegex(bridge.UxmlPatchError, "UXML_FILE_SHA256_MISMATCH"):
                bridge.apply_edit_ops(file, uxml, wrong)

    def test_duplicate_source_ref_and_any_skipped_selected_operation_refused(self):
        with tempfile.TemporaryDirectory(prefix="uxml-s2-duplicate-") as temp:
            file, uxml, _, ops, direct = self.first_positive(Path(temp))
            bad = deepcopy(uxml)
            bad["components"].append(deepcopy(bad["components"][0]))
            with self.assertRaisesRegex(ValueError, "AMBIGUOUS|DUPLICATE_SOURCE_RECORD"):
                bridge.apply_edit_ops(file, bad, ops)
            missing = deepcopy(ops)
            missing["ops"] = missing["ops"][1:]
            with self.assertRaisesRegex(bridge.UxmlPatchError, "UXML_SELECTED_OPS_SET_MISMATCH"):
                bridge.apply_edit_ops(file, uxml, missing)
            self.assertIsNotNone(direct.fixed_xml)

    def test_loss_contract_vetoes_touching_field_but_not_unrelated_source_metadata(self):
        with tempfile.TemporaryDirectory(prefix="uxml-s2-loss-") as temp:
            file, uxml, _, ops, _ = self.first_positive(Path(temp))
            result = bridge.resolve_from_uxml(uxml)
            action = next(a for a in result.fix_actions
                          if a.action_id == ops["ops"][0]["sourceActionId"])
            writes = bridge._write_targets(result, action)
            self.assertTrue(writes)
            key = sorted(writes)[0]
            target_path = bridge._source_record_paths(result.document.source_text, result)[key]
            bad = deepcopy(uxml)
            bad["lossContract"].append({"details":{"sourcePath":target_path + "/Position[0]/@raw"}})
            with self.assertRaisesRegex(bridge.UxmlPatchError, "UXML_LOSS_CONTRACT_FIELD_TOUCH"):
                bridge.apply_edit_ops(file, bad, ops)
            # An unknown field elsewhere must not become an unrelated global veto.
            other = deepcopy(uxml)
            other["lossContract"].append({"details":{"sourcePath":"/PipeStressExport[0]/@raw"}})
            _, differences = bridge.compare_patch_to_direct(file, other, ops)
            self.assertEqual(differences, [])

    def test_deliberate_red_skipping_writer_mutation_fails_exact_equality(self):
        with tempfile.TemporaryDirectory(prefix="uxml-s2-writer-red-") as temp:
            file, uxml, _, ops, direct = self.first_positive(Path(temp))
            real, equal = bridge.compare_patch_to_direct(file, uxml, ops)
            self.assertEqual(equal, [])
            self.assertNotEqual(direct.fixed_xml, file.read_bytes().decode("utf-8"))
            # A patched writer that skips its authorized edit and emits the
            # unmodified original must fail the byte oracle.
            mutant = replace(real, fixed_xml=file.read_bytes().decode("utf-8"))
            with patch.object(bridge, "apply_edit_ops", return_value=mutant):
                _, differences = bridge.compare_patch_to_direct(file, uxml, ops)
            self.assertTrue(any("/fixedXml" in line for line in differences))
            self.assertTrue(any("/validation" in line for line in differences))


    def test_low_confidence_action_is_refused_even_when_payload_requests_zero_threshold(self):
        with tempfile.TemporaryDirectory(prefix="uxml-s2-lowconfidence-") as temp:
            file, uxml, _, ops, _ = self.first_positive(Path(temp))
            original=bridge.resolve_from_uxml(uxml,source_name=str(file))
            selected_ids={op["sourceActionId"] for op in ops["ops"]}
            downgraded=replace(original, fix_actions=tuple(
                replace(action,confidence=0.5) if action.action_id in selected_ids
                else action for action in original.fix_actions))
            malicious=deepcopy(ops)
            malicious["policy"]["minimum_confidence"]=0.0
            with patch.object(bridge,"resolve_from_uxml",return_value=downgraded):
                with self.assertRaisesRegex(bridge.UxmlPatchError,
                        "UXML_POLICY_WIDENING_REFUSED:minimum_confidence"):
                    bridge.apply_edit_ops(file,uxml,malicious)
            # Native threshold still rejects a mocked low-confidence action,
            # even without the malicious override.
            with patch.object(bridge,"resolve_from_uxml",return_value=downgraded):
                with self.assertRaisesRegex(bridge.UxmlPatchError,
                        "UXML_ACTION_OUTSIDE_CURRENT_AUTO_POLICY"):
                    bridge.apply_edit_ops(file,uxml,ops)

    def test_two_real_cli_entrypoints_export_and_patch_with_equal_reports(self):
        with tempfile.TemporaryDirectory(prefix="uxml-s2-cli-") as temp:
            base = Path(temp)
            file, uxml, uxml_path, ops, direct = self.first_positive(base)
            ops_path = base / "authorized.ops.json"
            fixed_path = base / "patched-copy.xml"
            report_path = base / "validation.json"
            commands = [
                [sys.executable, "-m",
                 "converters.psi116_topology_resolver.uxml_export_ops",
                 str(file), str(ops_path), "--uxml", str(uxml_path)],
                [sys.executable, "-m",
                 "converters.psi116_topology_resolver.uxml_patch_psi116",
                 str(file), str(ops_path), "--uxml", str(uxml_path),
                 "--output", str(fixed_path), "--validation", str(report_path)],
            ]
            for command in commands:
                proc = subprocess.run(command, cwd=REPO,capture_output=True,
                                      text=True,timeout=40)
                self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                self.assertEqual(proc.stdout.strip(), "EQUAL")
            self.assertEqual(fixed_path.read_bytes(), direct.fixed_xml.encode("utf-8"))
            self.assertEqual(json.loads(report_path.read_text()),
                             json.loads(json.dumps(direct.validation_payload())),
                             "JSON report round-trip must preserve all native checks")
            self.assertEqual(json.loads(ops_path.read_text()), ops)
            # A false target cannot emit an output and prints an exact reason.
            fake = deepcopy(ops)
            fake["ops"][0]["targets"][0] = "B7:N9999:S99"
            ops_path.write_text(json.dumps(fake), encoding="utf-8")
            fixed_path.unlink()
            bad = subprocess.run(commands[1],cwd=REPO,capture_output=True,
                                 text=True,timeout=40)
            self.assertEqual(bad.returncode, 1)
            self.assertIn("DIFFERENT", bad.stdout)
            self.assertIn("UXML_TARGET_RECORD_NOT_FOUND", bad.stdout)
            self.assertFalse(fixed_path.exists())
            self.assertEqual(file.read_bytes(), verified_synthetic(pipe_flange(25)).encode("utf-8"))



class UxmlS2FixedPolicyRefusal(unittest.TestCase):
    """Pure policy parser regressions run even without the external XCU reader."""

    def test_red_minimum_confidence_cannot_be_lowered_or_raised(self):
        from dataclasses import asdict
        for value in (0.0, 1.0):
            with self.subTest(requested=value):
                payload=json.loads(json.dumps(asdict(TransactionPolicy(
                    selected_action_ids=("ACT-000001",),
                    minimum_confidence=value))))
                with self.assertRaisesRegex(bridge.UxmlPatchError,
                        "UXML_POLICY_WIDENING_REFUSED:minimum_confidence"):
                    bridge._policy_from_json(payload)
                with self.assertRaisesRegex(bridge.UxmlPatchError,
                        "UXML_POLICY_WIDENING_REFUSED:minimum_confidence"):
                    bridge.export_edit_ops({},policy=TransactionPolicy(
                        apply_all_safe=True,minimum_confidence=value))

    def test_red_cannot_disable_blocking_plan_preflight(self):
        from dataclasses import asdict
        payload=json.loads(json.dumps(asdict(TransactionPolicy(
            selected_action_ids=("ACT-000001",),
            require_no_blocking_plan_actions=False))))
        with self.assertRaisesRegex(bridge.UxmlPatchError,
                "UXML_POLICY_WIDENING_REFUSED:require_no_blocking_plan_actions"):
            bridge._policy_from_json(payload)
        with self.assertRaisesRegex(bridge.UxmlPatchError,
                "UXML_POLICY_WIDENING_REFUSED:require_no_blocking_plan_actions"):
            bridge.export_edit_ops({},policy=TransactionPolicy(
                apply_all_safe=True,require_no_blocking_plan_actions=False))


    def test_imported_export_cli_catches_reader_timeout_without_nameerror(self):
        import contextlib
        import io
        from psi116_topology_resolver import uxml_export_ops
        out=io.StringIO()
        with tempfile.TemporaryDirectory(prefix="uxml-s2-import-") as temp:
            src=Path(temp)/"original.xml"
            ops=Path(temp)/"ops.json"
            with patch.object(uxml_export_ops,"load_pinned_uxml",
                    side_effect=subprocess.TimeoutExpired(["node"],10)):
                with contextlib.redirect_stdout(out):
                    code=uxml_export_ops.main([str(src),str(ops)])
        self.assertEqual(code,1)
        self.assertIn("DIFFERENT",out.getvalue())
        self.assertIn("ERROR:",out.getvalue())

    def test_patch_cli_rejects_any_input_output_collision_and_two_outputs_same_path(self):
        import contextlib
        import io
        from psi116_topology_resolver import uxml_patch_psi116
        with tempfile.TemporaryDirectory(prefix="uxml-s2-input-collision-") as temp:
            root=Path(temp)
            original=root/"original.xml"
            ops=root/"ops.json"
            uxml=root/"source.uxml.json"
            validation=root/"validation.json"
            original.write_text("<original/>")
            ops.write_text('{"sentinel":1}')
            uxml.write_text('{"sentinel":2}')
            before={f:f.read_bytes() for f in (original,ops,uxml)}
            for option in ("--output","--validation"):
                for kind,path in (("original",original),("ops",ops),("uxml",uxml)):
                    with self.subTest(option=option,protected=kind):
                        buf=io.StringIO()
                        with contextlib.redirect_stdout(buf):
                            rc=uxml_patch_psi116.main([str(original),str(ops),
                                "--uxml",str(uxml),option,str(path)])
                        self.assertEqual(rc,1)
                        expected=("UXML_ORIGINAL_OVERWRITE_FORBIDDEN" if kind=="original"
                                  else "UXML_PROTECTED_INPUT_OVERWRITE_FORBIDDEN:"+kind)
                        self.assertIn(expected,buf.getvalue())
                        for f,data in before.items():
                            self.assertEqual(f.read_bytes(),data)
            buf=io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc=uxml_patch_psi116.main([str(original),str(ops),
                    "--uxml",str(uxml),"--output",str(validation),
                    "--validation",str(validation)])
            self.assertEqual(rc,1)
            self.assertIn("UXML_OUTPUT_VALIDATION_PATH_COLLISION",buf.getvalue())
            self.assertFalse(validation.exists())

    def test_export_cli_protects_supplied_uxml_source_file(self):
        import contextlib
        import io
        from psi116_topology_resolver import uxml_export_ops
        with tempfile.TemporaryDirectory(prefix="uxml-s2-export-collision-") as temp:
            original=Path(temp)/"original.xml"
            uxml=Path(temp)/"source.uxml.json"
            original.write_text("<original/>")
            uxml.write_text('{"sentinel":2}')
            out=io.StringIO()
            with contextlib.redirect_stdout(out):
                rc=uxml_export_ops.main([str(original),str(uxml),
                                        "--uxml",str(uxml)])
            self.assertEqual(rc,1)
            self.assertIn("UXML_INPUT_UXML_OVERWRITE_FORBIDDEN",out.getvalue())
            self.assertEqual(uxml.read_text(),'{"sentinel":2}')



if __name__ == "__main__":
    unittest.main()
