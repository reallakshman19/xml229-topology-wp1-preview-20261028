"""Synthetic interconnected native bulk: per-owner timing/profile, no product changes."""
from __future__ import annotations
import cProfile
import io
import json
import os
import pstats
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.uxml_edit_ops import (
    export_edit_ops, apply_edit_ops, compare_hub_patch,
)
from test_port_policy import doc, node
from test_uxml_psi116_s1 import verified_synthetic


def interconnected_tee_fixture(count=60):
    """Public 60-owner fixture: parent TEE, sharing positive BRAN identity."""
    branches = []
    for i in range(count):
        x, k = 1500 * i, 1000 * (i + 1)
        parent = (
            node(-1, "TEE", f"TEE-{i}", 1, f"{x} 0 0") +
            node(k+50, "TEE", f"TEE-{i}", 0, f"{x+100} 0 0") +
            node(-1, "TEE", f"TEE-{i}", 2, f"{x+200} 0 0") +
            node(-1, "TEE", f"TEE-{i}", 3, f"{x+100} 100 0")
        )
        side = (
            node(k+50, "BRAN", f"BRAN-{i}", 1, f"{x+100} 0 0",
                 "<ConnectionType>TEE</ConnectionType>") +
            node(k+10, "PIPE", f"PIPE-{i}", 1, f"{x+100} 0 0") +
            node(k+20, "PIPE", f"PIPE-{i}", 2, f"{x+300} 0 0") +
            node(-1, "GASK", f"SHORT-{i:03d}", 1, f"{x+300} 0 0") +
            node(k+30, "RIGID", f"SHORT-{i:03d}", 2, f"{x+303} 0 0") +
            node(-1, "FLAN", f"FLAN-{i}", 1, f"{x+303} 0 0") +
            node(k+40, "RIGID", f"FLAN-{i}", 2, f"{x+389} 0 0")
        )
        branches.extend([parent, side])
    return verified_synthetic(doc(*branches))


class InterconnectedDirectApplyProfile(unittest.TestCase):
    def test_five_sequential_native_bulk_steps_preserve_full_canonical_authority(self):
        if os.environ.get("UXML_DIRECT_APPLY_BENCHMARK") != "1":
            self.skipTest("Explicit UXML_DIRECT_APPLY_BENCHMARK=1 required")
        reader = os.environ.get("XCU_UXML_ROOT")
        if not reader or not (Path(reader) / "tools" / "psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned XCU_UXML_ROOT is required")
        cfg = ResolverConfig()
        with tempfile.TemporaryDirectory(prefix="public-interconnected-bulk-") as temp:
            source = Path(temp) / "synthetic-original.xml"
            original = interconnected_tee_fixture().encode("utf-8")
            source.write_bytes(original)
            base = resolve_psi116(source, cfg)
            rows = [r for r in short_elements(base.document, cfg)
                    if r["componentRefNo"].startswith("SHORT-")]
            self.assertEqual(len(rows), 60)
            self.assertTrue(all(row["eligible"] for row in rows))
            selected = [row["id"] for row in rows[3:8]]
            profile = cProfile.Profile()
            per_step = []
            overall = time.perf_counter()
            for index, identifier in enumerate(selected, start=1):
                started = time.perf_counter()
                xcu_started = time.perf_counter()
                cli = subprocess.run(
                    ["node", str(Path(reader) / "tools" / "psi116-to-uxml.mjs"), str(source)],
                    cwd=reader, capture_output=True, text=True, timeout=120)
                self.assertEqual(cli.returncode, 0, cli.stderr)
                uxml = json.loads(cli.stdout)
                reader_ms = round((time.perf_counter() - xcu_started) * 1000)
                current = resolve_psi116(source, cfg)
                row = next(r for r in short_elements(current.document, cfg)
                           if r["id"] == identifier)
                self.assertTrue(row["eligible"], identifier)
                request = {k: row[k] for k in ("id", "sourceSha256", "nodeKeys")}
                policy = TransactionPolicy(
                    selected_action_ids=(identifier,),
                    short_element_requests=(request,))
                if index <= 3:
                    profile.enable()
                direct_started = time.perf_counter()
                direct = apply_topofix_transaction(current, policy=policy, config=cfg)
                direct_ms = round((time.perf_counter() - direct_started) * 1000)
                export_started = time.perf_counter()
                envelope = export_edit_ops(uxml, policy=policy,
                                           source_name=str(source), config=cfg)
                export_ms = round((time.perf_counter() - export_started) * 1000)
                self.assertEqual(len(envelope["ops"]), 1)
                self.assertEqual(envelope["ops"][0]["sourceActionId"], identifier)
                self.assertIn("removedWithRecord", envelope["ops"][0])
                patch_started = time.perf_counter()
                patched = apply_edit_ops(source, uxml, envelope, config=cfg)
                patch_ms = round((time.perf_counter() - patch_started) * 1000)
                if index <= 3:
                    profile.disable()
                self.assertIsNotNone(patched)
                self.assertTrue(direct.committed)
                self.assertTrue(patched.committed)
                self.assertEqual(compare_hub_patch(direct, patched), [])
                self.assertEqual(direct.fixed_xml, patched.fixed_xml)
                self.assertEqual(source.read_bytes(), original if index == 1 else prior_bytes)
                next_path = Path(temp) / f"synthetic-revision-{index}.xml"
                next_path.write_text(patched.fixed_xml, encoding="utf-8")
                per_step.append({
                    "step": index,
                    "elapsedMs": round((time.perf_counter() - started) * 1000),
                    "xcuReaderMs": reader_ms,
                    "directNativeMs": direct_ms,
                    "canonicalExportMs": export_ms,
                    "canonicalApplyMs": patch_ms,
                })
                source = next_path
                prior_bytes = source.read_bytes()
            summary = io.StringIO()
            pstats.Stats(profile, stream=summary).strip_dirs().sort_stats(
                "cumulative").print_stats(18)
            print("SYNTHETIC_INTERCONNECTED_DIRECT_BULK_STEPS=" +
                  json.dumps(per_step, sort_keys=True))
            print("SYNTHETIC_INTERCONNECTED_DIRECT_BULK_TOTAL_SECONDS=" +
                  format(time.perf_counter() - overall, ".5f"))
            print("SYNTHETIC_INTERCONNECTED_DIRECT_BULK_PROFILE_CUMULATIVE\n" +
                  summary.getvalue())
            self.assertEqual(len(per_step), 5)
            self.assertEqual([p["step"] for p in per_step], [1, 2, 3, 4, 5])
