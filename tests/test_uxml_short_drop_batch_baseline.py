"""Synthetic baseline BEFORE any UXML short-drop batching optimization.

Measure one source-qualified GASK owner in the same 60-TEE interconnected
fixture as test_uxml_short_direct_apply_profile. No original Owner files.
Run only when explicitly enabled and the immutable XCU reader is present:
 UXML_BATCH_BASELINE=1 XCU_UXML_ROOT=... python3 -B -m unittest
    discover -s tests -p test_uxml_short_drop_batch_baseline.py -v

Per-stage times are wall-clock; nested native function times are subsets of
nativeDirectMs and are NOT additive with the canonical export/apply stages.
"""
from __future__ import annotations

from collections import defaultdict
import cProfile
import io
import json
import os
from pathlib import Path
import pstats
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver import short_elements as short_module
from psi116_topology_resolver import transaction as transaction_module
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.uxml_edit_ops import (
    export_edit_ops, apply_edit_ops, compare_hub_patch,
)
from test_uxml_short_direct_apply_profile import interconnected_tee_fixture


def elapsed_ms(func, *args, **kwargs):
    begin = time.perf_counter_ns()
    value = func(*args, **kwargs)
    return value, round((time.perf_counter_ns() - begin) / 1_000_000, 3)


class BatchBaselineNative(unittest.TestCase):
    def test_one_interconnected_short_owner_before_any_engine_change(self):
        if os.environ.get("UXML_BATCH_BASELINE") != "1":
            self.skipTest("UXML_BATCH_BASELINE=1 is required")
        reader = Path(os.environ.get("XCU_UXML_ROOT", ""))
        if not (reader / "tools" / "psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned XCU_UXML_ROOT is required")
        cfg = ResolverConfig()
        with tempfile.TemporaryDirectory(prefix="synthetic-batch-baseline-") as d:
            path = Path(d) / "interconnected.xml"
            original = interconnected_tee_fixture(60).encode("utf-8")
            path.write_bytes(original)
            before, resolve_ms = elapsed_ms(resolve_psi116, path, cfg)
            rows, eligibility_ms = elapsed_ms(short_elements, before.document, cfg)
            choices = [r for r in rows if
                       r["componentRefNo"].startswith("SHORT-") and r["eligible"]]
            self.assertEqual(len(choices), 60)
            row = choices[3]
            request = {k: row[k] for k in ("id", "sourceSha256", "nodeKeys")}
            policy = TransactionPolicy(selected_action_ids=(row["id"],),
                                       short_element_requests=(request,))
            # UXML read is the exact pinned CLI already used in the protected tests.
            start = time.perf_counter_ns()
            result = subprocess.run(
                ["node", str(reader / "tools" / "psi116-to-uxml.mjs"), str(path)],
                cwd=reader, capture_output=True, text=True, timeout=120)
            reader_ms = round((time.perf_counter_ns() - start) / 1_000_000, 3)
            self.assertEqual(result.returncode, 0, result.stderr)
            uxml = json.loads(result.stdout)

            # Capability probe on the untouched baseline native contract:
            # TWO independent branch-owner requests in ONE policy are refused,
            # both at the transaction engine and at canonical UXML export.
            others = choices[3:5]
            two_requests = tuple({k: owner[k]
                                  for k in ("id", "sourceSha256", "nodeKeys")}
                                 for owner in others)
            two_policy = TransactionPolicy(
                selected_action_ids=tuple(owner["id"] for owner in others),
                short_element_requests=two_requests)
            with self.assertRaisesRegex(
                ValueError, "Select one source-bound short element"):
                apply_topofix_transaction(before, policy=two_policy, config=cfg)
            with self.assertRaisesRegex(
                ValueError, "UXML_SHORT_EXACT_ONE_REQUEST_REQUIRED"):
                export_edit_ops(uxml, policy=two_policy,
                                source_name=str(path), config=cfg)
            print("UXML_BATCH_CAPABILITY_BASELINE=" + json.dumps({
                "fixture": "synthetic-interconnected-60-tee",
                "requestedOwners": [owner["id"] for owner in others],
                "native": "REFUSED: Select one source-bound short element per atomic transaction.",
                "canonical": "REFUSED: UXML_SHORT_EXACT_ONE_REQUEST_REQUIRED",
                "sourceBytesUnchanged": path.read_bytes() == original,
            }, sort_keys=True))

            inner_ms = defaultdict(float)
            calls = defaultdict(int)
            def wrapped(name, original_function):
                def invoke(*args, **kwargs):
                    t = time.perf_counter_ns()
                    try:
                        return original_function(*args, **kwargs)
                    finally:
                        inner_ms[name] += (time.perf_counter_ns() - t) / 1_000_000
                        calls[name] += 1
                return invoke

            profile = cProfile.Profile()
            with patch.object(transaction_module, "_parse_clone",
                              wrapped("xmlParse", transaction_module._parse_clone)), \
                 patch.object(transaction_module, "_serialize",
                              wrapped("xmlSerialize", transaction_module._serialize)), \
                 patch.object(short_module, "resolve_psi116",
                              wrapped("postRemovalResolve", short_module.resolve_psi116)), \
                 patch.object(transaction_module, "resolve_psi116",
                              wrapped("postClosureResolve", transaction_module.resolve_psi116)), \
                 patch.object(transaction_module, "apply_topofix_transaction",
                              wrapped("nestedClosureTransaction",
                                      transaction_module.apply_topofix_transaction)):
                profile.enable()
                direct, direct_ms = elapsed_ms(
                    apply_topofix_transaction, before, policy=policy, config=cfg)
                profile.disable()
            self.assertTrue(direct.committed, direct.reject_reasons)
            canonical, export_ms = elapsed_ms(export_edit_ops, uxml, policy=policy,
                                             source_name=str(path), config=cfg)
            self.assertEqual(len(canonical["ops"]), 1)
            patched, apply_ms = elapsed_ms(apply_edit_ops, path, uxml, canonical,
                                           config=cfg)
            self.assertIsNotNone(patched)
            self.assertTrue(patched.committed, patched.reject_reasons)
            mismatches, parity_ms = elapsed_ms(compare_hub_patch, direct, patched)
            self.assertEqual(mismatches, [])
            self.assertEqual(direct.fixed_xml, patched.fixed_xml)
            next_path = Path(d) / "repaired.xml"
            _, write_ms = elapsed_ms(next_path.write_bytes,
                                     patched.fixed_xml.encode("utf-8"))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(next_path.read_bytes(), patched.fixed_xml.encode("utf-8"))
            report = {
                "fixture": "synthetic-interconnected-60-tee",
                "records": sum(len(branch.nodes) for branch in before.document.branches),
                "qualifiedOwners": len(choices),
                "measuredOwnerId": row["id"],
                "sourceBytes": len(original),
                "sourceResolveMs": resolve_ms,
                "eligibilityMs": eligibility_ms,
                "sourceXmlParseMsNested": round(inner_ms["xmlParse"], 3),
                "nativeDirectMs": direct_ms,
                "nativeXmlParseMs": round(inner_ms["xmlParse"], 3),
                "nativePostRemovalResolveMs": round(inner_ms["postRemovalResolve"], 3),
                "nativeClosureTransactionMs": round(inner_ms["nestedClosureTransaction"], 3),
                "nativePostClosureResolveMs": round(inner_ms["postClosureResolve"], 3),
                "nativeSerializeMs": round(inner_ms["xmlSerialize"], 3),
                "nativeCalls": dict(calls),
                "uxmlReaderCliMs": reader_ms,
                "canonicalExportMs": export_ms,
                "canonicalApplyMs": apply_ms,
                "nativeParityCompareMs": parity_ms,
                "outputWriteMs": write_ms,
                "hubFullFlowMs": round(reader_ms + resolve_ms + eligibility_ms +
                                      direct_ms + export_ms + apply_ms + parity_ms +
                                      write_ms, 3),
                "directVsPatchEqual": True,
            }
            stats = io.StringIO()
            pstats.Stats(profile, stream=stats).strip_dirs().sort_stats(
                "cumulative").print_stats(14)
            print("UXML_BATCH_BASELINE_NATIVE=" +
                  json.dumps(report, sort_keys=True))
            print("UXML_BATCH_BASELINE_NATIVE_PROFILE_TOP14\n" +
                  stats.getvalue())
