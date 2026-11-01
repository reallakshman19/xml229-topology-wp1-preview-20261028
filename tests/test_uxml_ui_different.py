"""UXML-UI independent DIFFERENT-path Python gate (public synthetic only).

Execute the exact embedded Pyodide topology stage in native Python against
an XCU-produced UXML with a deliberately displaced source coordinate.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "converters"))
from test_uxml_psi116_s1 import verified_synthetic
from test_port_policy import pipe_flange
from psi116_topology_resolver.uxml_edit_ops import export_edit_ops


class UxmlUiDifferentOriginalSourceGate(unittest.TestCase):
    def test_coordinate_divergence_blocks_commit_and_writes_no_corrected_xml(self):
        xcu = os.environ.get("XCU_UXML_ROOT")
        if not xcu or not (Path(xcu) / "tools/psi116-to-uxml.mjs").is_file():
            self.skipTest("Requires pinned external XCU_UXML_ROOT reader")

        with tempfile.TemporaryDirectory(prefix="uxml-ui-different-synthetic-") as scratch:
            root = Path(scratch)
            source = root / "synthetic.xml"
            original_bytes = verified_synthetic(pipe_flange(25)).encode("utf-8")
            source.write_bytes(original_bytes)
            cli = subprocess.run(
                ["node", str(Path(xcu) / "tools/psi116-to-uxml.mjs"), str(source)],
                capture_output=True, text=True, timeout=45, check=False,
            )
            self.assertEqual(cli.returncode, 0, cli.stderr)
            original_uxml = json.loads(cli.stdout)
            ops = export_edit_ops(original_uxml, source_name=str(source))
            self.assertTrue(ops["ops"], "fixture must have an actual safe Auto-fix")

            # Keep original file, SHA and sourceRefs unchanged. Perturb only
            # the canonical UXML coordinate of an actual write-target record.
            altered = deepcopy(original_uxml)
            targets = {key for op in ops["ops"] for key in op["targets"]}
            changed = 0
            for component in altered["components"]:
                row = component["rawAttributes"]["psi116"]
                if row["recordKey"] in targets and row["position"] is not None:
                    row["position"]["x"] += 500.0
                    changed += 1
                    break
            self.assertEqual(changed, 1, "a single real source-target coordinate must change")

            # This is the actual pre-Final Python snippet executed in the Worker.
            js = (REPO / "converters/xml-cii-2019-standalone/topology-integration.js").read_text(
                encoding="utf-8"
            )
            match = re.search(r"const TOPOLOGY_SNIPPET = \x60\n(.*?)\n\x60;", js, re.S)
            self.assertIsNotNone(match, "must test published Worker Python, not a model")
            snippet = match.group(1).replace("\\\\", "\\")
            names = ("findings", "plan", "transaction", "validation", "fixed",
                     "lineage", "postFindings", "postPlan", "handoff", "status")
            paths = {name: root / (name + ".json" if name != "fixed" else "patched.xml")
                     for name in names}
            values = {
                "job_topology_input_path": str(source),
                "job_topology_uxml_json": json.dumps(altered),
                "job_generate_topofix": True,
                "job_topology_action_ids": [op["sourceActionId"] for op in ops["ops"]],
                "job_connection_preview_json": "null",
                "job_joint_repairs_json": "[]",
                "job_short_elements_json": "[]",
            }
            values.update({
                "job_topology_" + key.replace("postFindings", "post_findings")
                .replace("postPlan", "post_plan") + "_path": str(path)
                for key, path in paths.items()
            })
            # The JS stage uses snake_case identifiers for post-output paths.
            values["job_topology_post_findings_path"] = str(paths["postFindings"])
            values["job_topology_post_plan_path"] = str(paths["postPlan"])
            values["job_topology_handoff_path"] = str(paths["handoff"])

            exec(compile(snippet, "<real-topology-stage>", "exec"), values)
            status = json.loads(paths["status"].read_text(encoding="utf-8"))
            self.assertEqual(status["hubParity"]["status"], "DIFFERENT")
            self.assertTrue(status["hubParity"]["differences"])
            self.assertFalse(status["committed"])
            self.assertIn("UXML_PARITY_DIFFERENT_NO_DOWNLOAD", status["rejectReasons"])
            self.assertEqual(status["fixedPath"], "")
            self.assertEqual(status["lineagePath"], "")
            self.assertEqual(status["handoffPath"], "")
            for name in ("fixed", "lineage", "postFindings", "postPlan", "handoff"):
                with self.subTest(output=name):
                    self.assertFalse(paths[name].exists(),
                        "differing hub must not write a corrected/downloadable file")
            self.assertEqual(source.read_bytes(), original_bytes,
                             "original input must remain byte-identical")


if __name__ == "__main__":
    unittest.main()
