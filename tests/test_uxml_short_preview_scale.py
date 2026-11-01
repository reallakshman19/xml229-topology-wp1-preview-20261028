"""Public synthetic-only 89-owner short-preview benchmark and native exactness."""
from __future__ import annotations

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
from psi116_topology_resolver.uxml_edit_ops import export_edit_ops
from psi116_topology_resolver.uxml_operations_preview import build_operation_preview
from unittest.mock import patch
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
        if os.environ.get("UXML_SCALE_BENCHMARK") != "1":
            self.skipTest("Run explicitly with UXML_SCALE_BENCHMARK=1")
        self.reader = os.environ.get("XCU_UXML_ROOT")
        if not self.reader or not (Path(self.reader) / "tools" / "psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned XCU_UXML_ROOT required")

    def test_89_owner_full_source_canonical_byte_and_refusal_identity(self):
        """No branch shortcut: both passes use unchanged full native code."""
        cfg=ResolverConfig()
        with tempfile.TemporaryDirectory(prefix="uxml-full-89-synthetic-") as temp:
            original=Path(temp)/"public-synthetic-89.xml"
            raw=synthetic_owners(89).encode("utf-8")
            original.write_bytes(raw)
            cli=subprocess.run(["node",str(Path(self.reader)/"tools"/"psi116-to-uxml.mjs"),
                                str(original)],cwd=self.reader,
                               capture_output=True,text=True,timeout=90)
            self.assertEqual(cli.returncode,0,cli.stderr)
            uxml=json.loads(cli.stdout)
            rows=[r for r in short_elements(resolve_psi116(original).document,cfg)
                  if r["componentRefNo"].startswith("SHORT-")]
            self.assertEqual(len(rows),89)
            self.assertTrue(all(r["eligible"] for r in rows))
            requests=[{k:r[k] for k in ("id","sourceSha256","nodeKeys")}
                      for r in rows]
            policies=[TransactionPolicy(selected_action_ids=(req["id"],),
                      short_element_requests=(req,)) for req in requests]
            canonical=lambda op:json.dumps(op,sort_keys=True,ensure_ascii=False).encode("utf-8")
            start=time.perf_counter()
            old=[]
            for policy in policies:
                try:
                    payload=export_edit_ops(uxml,policy=policy,
                                           source_name=str(original),config=cfg)
                    old.append(("READY",canonical(payload["ops"][0])))
                except ValueError as error:
                    old.append(("REFUSED",str(error)))
            old_s=time.perf_counter()-start
            observed=[]
            progress=[]
            original_export=export_edit_ops
            def checked_export(payload,**kwargs):
                pol=kwargs.get("policy")
                track=pol is not None and bool(pol.short_element_requests)
                try:
                    value=original_export(payload,**kwargs)
                    if track:
                        observed.append(("READY",canonical(value["ops"][0])))
                    return value
                except ValueError as error:
                    if track:observed.append(("REFUSED",str(error)))
                    raise
            start=time.perf_counter()
            with patch("psi116_topology_resolver.uxml_operations_preview.export_edit_ops",
                       side_effect=checked_export):
                projected=build_operation_preview(
                    uxml,source_name=str(original),config=cfg,
                    short_requests=requests,
                    progress=lambda completed,total:progress.append((completed,total)))
            new_s=time.perf_counter()-start
            self.assertEqual(observed,old,"all 89 full-source ops/refusals byte-identical")
            self.assertEqual(len(observed),89)
            self.assertEqual(projected["shortPreview"]["selectedIds"],
                             [r["id"] for r in requests])
            self.assertEqual(projected["shortPreview"]["acceptedIds"],
                             [r["id"] for r in requests])
            self.assertEqual(projected["shortPreview"]["refused"],[])
            self.assertEqual(len([x for x in projected["ops"]
                                  if x["kind"]=="DROP_SHORT_ELEMENT"]),89)
            self.assertEqual(progress,
                [(min(index,89),89) for index in range(4,90,4)]+[(89,89)])
            self.assertEqual(original.read_bytes(),raw)
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()),
                             [original.name])
            self.assertGreater(old_s,0)
            print(f"SYNTHETIC_89_SHORT_PREVIEW_BASELINE_SECONDS={old_s:.5f}")
            print(f"SYNTHETIC_89_SHORT_PREVIEW_SINGLE_SESSION_SECONDS={new_s:.5f}")
            print(f"SYNTHETIC_89_SHORT_PREVIEW_TIMING_RATIO={old_s/new_s:.2f}x")
            print("SYNTHETIC_89_SHORT_PREVIEW_FULL_NATIVE_PARITY=89/89")
