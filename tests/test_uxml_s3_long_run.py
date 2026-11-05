"""Honest CAESAR InputXML scale regression derived from public XCU S3 source.

Only temporary synthetic XML and pinned XCU reader outputs are used.
The downstream-first run is deliberately hostile to recursive union-find:
element k is 10k -> 10k+10, with k decreasing, without absolute XYZ.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from converters.psi116_topology_resolver.models import ResolverConfig
from converters.psi116_topology_resolver.uxml_adapter import (
    _recompute_inputxml_runs, document_from_uxml, resolve_from_uxml,
)


def public_chain_source(original: str, size: int, *, reverse: bool) -> str:
    """Repeat ONE public PIPINGELEMENT header, never use fabricated Owner data."""
    rows = list(re.finditer(r"<PIPINGELEMENT\b[^>]*>.*?</PIPINGELEMENT>",
                            original, flags=re.DOTALL))
    if len(rows) != 6:
        raise AssertionError("EXPECTED_SIX_PUBLIC_SOURCE_ELEMENTS")
    head = re.match(r"<PIPINGELEMENT\b[^>]*>", rows[0].group())
    if not head:
        raise AssertionError("PUBLIC_SOURCE_PIPE_HEADER_REQUIRED")
    template = head.group()
    template, removed = re.subn(
        r'\s+(?:FROM|TO)_[XYZ]="[^"]*"', "", template)
    if removed != 6:
        raise AssertionError("PUBLIC_SOURCE_SIX_ANCHORS_REQUIRED")
    prefix = original[:rows[0].start()]
    suffix = original[rows[-1].end():]
    prefix, count = re.subn(r'NUMELT="6"', f'NUMELT="{size}"', prefix)
    if count != 1:
        raise AssertionError("PUBLIC_SOURCE_ELEMENT_COUNT_RECEIPT_MISSING")
    prefix = prefix.replace('NUMBEND="1"', 'NUMBEND="0"')
    prefix = prefix.replace('NUMISECT="1"', 'NUMISECT="0"')

    headers = []
    order = range(size, 0, -1) if reverse else range(1, size + 1)
    for k in order:
        tag = template
        for name, value in (("FROM_NODE", f"{10 * k:.6f}"),
                            ("TO_NODE", f"{10 * (k + 1):.6f}")):
            tag, changed = re.subn(
                name + r'="[^"]*"', name + '="' + value + '"', tag)
            if changed != 1:
                raise AssertionError("PUBLIC_SOURCE_NODE_ATTRIBUTE_MISSING:" + name)
        headers.append(tag + "</PIPINGELEMENT>")
    return prefix + "\n".join(headers) + suffix


class PublicXcuLongRunRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xcu = Path(os.environ.get("XCU_UXML_ROOT") or "/nonexistent")
        cls.reader = cls.xcu / "tools" / "inputxml-to-uxml.mjs"
        cls.source = cls.xcu / "tests" / "fixtures" / "uxml-s3-synthetic.workspace.input.xml"
        if not cls.reader.is_file() or not cls.source.is_file():
            raise unittest.SkipTest("Pinned XCU strict reader and original public fixture required")
        cls.original = cls.source.read_text(encoding="utf-8")

    def hub(self, n: int, *, reverse: bool):
        with tempfile.TemporaryDirectory(prefix="public-xcu-long-run-") as folder:
            source = Path(folder) / "synthetic-long-run.input.xml"
            out = Path(folder) / "public-strict-hub.json"
            source.write_text(public_chain_source(self.original, n, reverse=reverse),
                              encoding="utf-8")
            with out.open("w", encoding="utf-8") as stdout:
                proc = subprocess.run(["node", str(self.reader), str(source)],
                                      cwd=self.xcu, stdout=stdout,
                                      stderr=subprocess.PIPE, text=True,
                                      timeout=300)
            self.assertEqual(proc.returncode, 0,
                             "PINNED_XCU_STRICT_READER_FAILED:" + proc.stderr[:1500])
            hub = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(len(hub["components"]), n)
        self.assertEqual(len(hub["inputXml"]["runs"]), 1)
        run = hub["inputXml"]["runs"][0]
        self.assertEqual(run["edgeCount"], n)
        self.assertEqual(run["nodeCount"], n + 1)
        self.assertEqual(run["elementIndices"], list(range(n)))
        self.assertFalse(run["anchored"])
        return hub

    @staticmethod
    def _shape(document):
        keys = {key for branch in document.branches
                for record in branch.nodes
                for key in record.inputxml_record_keys}
        nodes = {record.node_number for branch in document.branches
                 for record in branch.nodes}
        return len(keys), len(nodes), len(document.branches)

    def test_B1_reverse_1200_original_source_document_and_real_resolve(self):
        hub = self.hub(1200, reverse=True)
        document = document_from_uxml(hub)
        result = resolve_from_uxml(hub)
        self.assertEqual(self._shape(document)[:2], (1200, 1201))
        self.assertEqual(self._shape(result.document), self._shape(document))
        self.assertIsInstance(result.findings_payload(ResolverConfig())["summary"], dict)
        print("B1_HEAD_REVERSE_N1200=DOCUMENT_OK_RESOLVE_OK", flush=True)

    def test_B1_forward_reverse_5000_document_and_resolve_shape(self):
        shapes = {}
        for reverse in (False, True):
            hub = self.hub(5000, reverse=reverse)
            document = document_from_uxml(hub)
            self.assertEqual(self._shape(document)[:2], (5000, 5001))
            result = resolve_from_uxml(hub)
            self.assertEqual(self._shape(result.document), self._shape(document))
            payload = result.findings_payload(ResolverConfig())
            self.assertIsInstance(payload["summary"]["findingCountsByCode"], dict)
            shapes["reverse" if reverse else "forward"] = (
                type(document).__name__, type(result).__name__,
                self._shape(document)[:2], type(payload["summary"]).__name__)
        self.assertEqual(shapes["forward"], shapes["reverse"])
        print("B1_HEAD_N5000=FORWARD_OK_REVERSE_OK_DOCUMENT_RESOLVE_SHAPE_MATCH", flush=True)

    def test_B1_partition_helper_100000_reverse_order_has_no_recursion(self):
        # No node subprocess: pure source-derived 100k-element partition stress.
        rows = [
            ET.Element("PIPINGELEMENT", {
                "FROM_NODE": f"{10 * k:.6f}",
                "TO_NODE": f"{10 * (k + 1):.6f}",
            })
            for k in range(100000, 0, -1)
        ]
        runs = _recompute_inputxml_runs(rows)
        self.assertEqual(len(runs), 1)
        run = runs[0]
        self.assertEqual(run["elementIndices"], list(range(100000)))
        self.assertEqual(run["edgeCount"], 100000)
        self.assertEqual(run["nodeCount"], 100001)
        self.assertEqual(run["firstNode"], "1000000.000000")
        self.assertFalse(run["anchored"])
        print("B1_HELPER_REVERSE_N100000=OK", flush=True)


if __name__ == "__main__":
    unittest.main()
