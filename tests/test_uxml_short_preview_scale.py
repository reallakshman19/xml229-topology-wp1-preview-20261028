"""Public synthetic-only 89-owner short-preview benchmark and native exactness."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import TransactionPolicy
from psi116_topology_resolver.uxml_adapter import resolve_from_uxml
from psi116_topology_resolver.uxml_edit_ops import export_edit_ops
from psi116_topology_resolver.uxml_operations_preview import (
    _ShortPreviewSourceScope, build_operation_preview,
)
from test_port_policy import doc, node
from test_uxml_psi116_s1 import verified_synthetic


def synthetic_owners(count=89):
    branches = []
    for i in range(count):
        x = i * 500
        n = 1000 * (i + 1)
        ref = f"SHORT-{i:03d}"
        branches.append(
            node(n + 10, "PIPE", f"PIPE-{i}", 1, f"{x} 0 0") +
            node(n + 20, "PIPE", f"PIPE-{i}", 2, f"{x+100} 0 0") +
            node(-1, "GASK", ref, 1, f"{x+100} 0 0") +
            node(n + 30, "RIGID", ref, 2, f"{x+103} 0 0") +
            node(-1, "FLAN", f"FLAN-{i}", 1, f"{x+103} 0 0") +
            node(n + 40, "RIGID", f"FLAN-{i}", 2, f"{x+189} 0 0"))
    return verified_synthetic(doc(*branches))


class UxmlShortPreviewScale(unittest.TestCase):
    def setUp(self):
        self.reader = os.environ.get("XCU_UXML_ROOT")
        if not self.reader or not (Path(self.reader) / "tools" / "psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned XCU_UXML_ROOT required for source-bound speed trial")

    def test_89_owner_source_bound_native_op_byte_identity_and_5x_wall_speed(self):
        cfg = ResolverConfig()
        with tempfile.TemporaryDirectory(prefix="uxml-short-scale-synthetic-") as temp:
            original = Path(temp) / "public-synthetic-89.xml"
            raw = synthetic_owners(89).encode("utf-8")
            original.write_bytes(raw)
            cli = subprocess.run(["node", str(Path(self.reader) / "tools" / "psi116-to-uxml.mjs"),
                                   str(original)], cwd=self.reader,
                                  capture_output=True, text=True, timeout=90)
            self.assertEqual(cli.returncode, 0, cli.stderr)
            uxml = json.loads(cli.stdout)
            before = resolve_psi116(original)
            rows = [r for r in short_elements(before.document, cfg)
                    if r["componentRefNo"].startswith("SHORT-")]
            self.assertEqual(len(rows), 89)
            self.assertTrue(all(r["eligible"] for r in rows), rows)
            requests = [{k: row[k] for k in ("id", "sourceSha256", "nodeKeys")}
                        for row in rows]
            policies = [TransactionPolicy(selected_action_ids=(req["id"],),
                         short_element_requests=(req,)) for req in requests]

            # Baseline = the exact 347ff15b per-owner full-source transaction
            # path. Its operation dicts are the independent byte oracle.
            start = time.perf_counter()
            baseline = [export_edit_ops(uxml, policy=policy, source_name=str(original),
                        config=cfg)["ops"][0] for policy in policies]
            before_seconds = time.perf_counter() - start

            start = time.perf_counter()
            resolved = resolve_from_uxml(uxml, cfg, source_name=str(original))
            scope = _ShortPreviewSourceScope(uxml, resolved, cfg)
            by_id = {row["id"]: row for row in scope.rows}
            fast = []
            for req, policy in zip(requests, policies):
                witness = scope.native_witness(by_id[req["id"]])
                self.assertIsNotNone(witness,
                                     "public separated branches must qualify for safe native slice")
                fast.append(export_edit_ops(
                    uxml, policy=policy, source_name=str(original), config=cfg,
                    _preview_result=resolved, _preview_short_rows=scope.rows,
                    _preview_native=witness, _preview_indexes=scope.indexes)["ops"][0])
            after_seconds = time.perf_counter() - start

            self.assertEqual(
                [json.dumps(op, sort_keys=True, ensure_ascii=False).encode("utf-8")
                 for op in fast],
                [json.dumps(op, sort_keys=True, ensure_ascii=False).encode("utf-8")
                 for op in baseline],
                "EVERY canonical source-bound op must remain byte-for-byte identical")
            self.assertGreater(before_seconds, 0)
            print(f"SYNTHETIC_89_SHORT_PREVIEW_BASELINE_SECONDS={before_seconds:.5f}")
            print(f"SYNTHETIC_89_SHORT_PREVIEW_OPTIMIZED_SECONDS={after_seconds:.5f}")
            print(f"SYNTHETIC_89_SHORT_PREVIEW_SPEEDUP={before_seconds/after_seconds:.2f}x")
            self.assertGreaterEqual(before_seconds / after_seconds, 5.0,
                                    "must be >=5x faster on same fixture and runner")

            projected = build_operation_preview(uxml, source_name=str(original),
                                                config=cfg, short_requests=requests)
            self.assertEqual(projected["shortPreview"]["selectedIds"],
                             [r["id"] for r in requests])
            self.assertEqual(projected["shortPreview"]["acceptedIds"],
                             [r["id"] for r in requests])
            self.assertEqual(projected["shortPreview"]["refused"], [])
            short_rows = [op for op in projected["ops"]
                          if op["kind"] == "DROP_SHORT_ELEMENT"]
            self.assertEqual(len(short_rows), 89)
            for shown, op in zip(short_rows, baseline):
                self.assertEqual(shown["sourceActionId"], op["sourceActionId"])
                self.assertEqual(shown["changes"], op["params"][0]["edits"])
                self.assertEqual(shown["removedWithRecord"], op["removedWithRecord"])
            self.assertEqual(original.read_bytes(), raw)
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()),
                             [original.name])
