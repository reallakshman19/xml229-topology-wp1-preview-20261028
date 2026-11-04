"""Lane A InputXML is analysis-only; original-file writes belong to XCU.

Synthetic-only refusal witnesses. No XCU installation is needed for this guard.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
from converters.psi116_topology_resolver.uxml_edit_ops import (
    UxmlPatchError, apply_edit_ops, compare_patch_to_direct, export_edit_ops,
)


class InputXmlReadOnlyGate(unittest.TestCase):
    def hub(self):
        return {"sources": [{"format": "INPUT_XML", "hash": "0" * 64}]}

    def test_export_never_issues_inputxml_operations(self):
        with self.assertRaisesRegex(UxmlPatchError, "^INPUT_XML_APPLY_NOT_ENABLED$"):
            export_edit_ops(self.hub())

    def test_apply_and_direct_parity_never_touch_original(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-inputxml-held-") as directory:
            original = Path(directory) / "synthetic.input.xml"
            content = b'<?xml version="1.0"?><CAESARII/>\n'
            original.write_bytes(content)
            payload = {"schema": "uxml-edit-ops/v1", "sourceFormat": "INPUT_XML",
                       "fileSha256": "0" * 64, "ops": []}
            for call in (
                lambda: apply_edit_ops(original, self.hub(), payload),
                lambda: compare_patch_to_direct(original, self.hub(), payload),
            ):
                with self.subTest(api=repr(call)):
                    with self.assertRaisesRegex(UxmlPatchError, "^INPUT_XML_APPLY_NOT_ENABLED$"):
                        call()
                    self.assertEqual(original.read_bytes(), content)

    def test_both_cli_paths_refuse_without_outputs(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-inputxml-cli-held-") as directory:
            folder = Path(directory)
            original = folder / "synthetic.input.xml"
            data = b'<?xml version="1.0"?><CAESARII/>\n'
            original.write_bytes(data)
            hubfile = folder / "synthetic.uxml.json"
            hubfile.write_text(json.dumps(self.hub()), encoding="utf-8")
            opsfile = folder / "ops.json"
            for module, extra, outputs in (
                ("uxml_export_ops", [], [opsfile]),
                ("uxml_patch_psi116",
                 ["--output", str(folder / "patched.xml"),
                  "--validation", str(folder / "validation.json")],
                 [folder / "patched.xml", folder / "validation.json"]),
            ):
                with self.subTest(module=module):
                    if module == "uxml_patch_psi116":
                        opsfile.write_text(json.dumps({"ops": []}), encoding="utf-8")
                    proc = subprocess.run(
                        [sys.executable, "-m",
                         "converters.psi116_topology_resolver." + module,
                         str(original), str(opsfile), "--uxml", str(hubfile), *extra],
                        cwd=ROOT, capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                    self.assertIn("INPUT_XML_APPLY_NOT_ENABLED", proc.stdout)
                    self.assertTrue(all(not output.exists() for output in outputs
                                        if output != opsfile))
                    if module == "uxml_export_ops":
                        self.assertFalse(opsfile.exists())
                    self.assertEqual(original.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
