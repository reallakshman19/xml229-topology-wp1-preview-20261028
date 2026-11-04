"""InputXML export/Apply/CLI HOLD using a REAL public XCU strict S3 hub.

No fabricated bare sources stub: every refusal uses original public bytes,
XCU's pinned sourceRefs, and the actual strict-reader output.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from converters.psi116_topology_resolver.uxml_edit_ops import (
    UxmlPatchError, apply_edit_ops, compare_patch_to_direct, export_edit_ops,
)


class InputXmlReadOnlyGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xcu = Path(os.environ.get("XCU_UXML_ROOT") or "/nonexistent")
        reader = cls.xcu / "tools" / "inputxml-to-uxml.mjs"
        if not reader.is_file():
            raise unittest.SkipTest("Pinned public XCU strict InputXML reader required")
        cls.original = cls.xcu / "tests" / "fixtures" / "uxml-s3-synthetic.workspace.input.xml"
        process = subprocess.run(["node", str(reader), str(cls.original)], cwd=cls.xcu,
                                 capture_output=True, text=True, timeout=60)
        if process.returncode:
            raise AssertionError("PUBLIC_XCU_STRICT_READER_FAILED: " + process.stderr)
        cls.real_hub = json.loads(process.stdout)
        if cls.real_hub["sources"][0]["format"] != "INPUT_XML":
            raise AssertionError("PUBLIC_XCU_INPUTXML_SOURCE_REQUIRED")

    def hub(self):
        return deepcopy(self.real_hub)

    def test_export_never_issues_inputxml_operations(self):
        with self.assertRaises(UxmlPatchError) as caught:
            export_edit_ops(self.hub())
        self.assertEqual(str(caught.exception), "INPUT_XML_APPLY_NOT_ENABLED")

    def test_apply_and_direct_parity_never_touch_original(self):
        with tempfile.TemporaryDirectory(prefix="public-inputxml-held-") as directory:
            original = Path(directory) / "synthetic.input.xml"
            original.write_bytes(self.original.read_bytes())
            content = original.read_bytes()
            hub = self.hub()
            payload = {"schema": "uxml-edit-ops/v1", "sourceFormat": "INPUT_XML",
                       "fileSha256": hub["sources"][0]["hash"], "ops": []}
            for name, call in (
                ("Apply", lambda: apply_edit_ops(original, hub, payload)),
                ("Compare", lambda: compare_patch_to_direct(original, hub, payload)),
            ):
                with self.subTest(api=name):
                    with self.assertRaises(UxmlPatchError) as caught:
                        call()
                    self.assertEqual(str(caught.exception), "INPUT_XML_APPLY_NOT_ENABLED")
                    self.assertEqual(original.read_bytes(), content)

    def test_both_cli_paths_refuse_without_outputs(self):
        with tempfile.TemporaryDirectory(prefix="public-inputxml-cli-held-") as directory:
            folder = Path(directory)
            original = folder / "synthetic.input.xml"
            original.write_bytes(self.original.read_bytes())
            data = original.read_bytes()
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
                    process = subprocess.run(
                        [sys.executable, "-m",
                         "converters.psi116_topology_resolver." + module,
                         str(original), str(opsfile), "--uxml", str(hubfile), *extra],
                        cwd=ROOT, capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(process.returncode, 1,
                                     process.stdout + process.stderr)
                    self.assertIn("INPUT_XML_APPLY_NOT_ENABLED", process.stdout)
                    self.assertTrue(all(not output.exists() for output in outputs
                                        if output != opsfile))
                    if module == "uxml_export_ops":
                        self.assertFalse(opsfile.exists())
                    self.assertEqual(original.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
