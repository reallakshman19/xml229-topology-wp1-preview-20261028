"""Final R2: source-backed exact-code guards, synthetic public XCU only.

Never uses private Owner files; never writes an original source. Each refusal
is pinned to a single named code, so an overlapping validation cannot mask a
deleted safeguard. The mixed-run case uses XCU's real strict reader.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from converters.psi116_topology_resolver.uxml_adapter import (
    UxmlPsi116Error, _caesar_original_rows, document_from_uxml,
    resolve_from_uxml, resolve_inputxml_run_from_uxml,
)
from converters.psi116_topology_resolver.uxml_compare import compare_cross_format_uxml

SOURCE = "uxml-s3-synthetic.workspace.input.xml"
DELTA = "uxml-s3-synthetic.workspace.delta-only.input.xml"
PSI = "uxml-s3-synthetic.psi116.xml"


class FinalInputXmlHoldGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xcu = Path(os.environ.get("XCU_UXML_ROOT") or "/nonexistent")
        cls.input_path = cls.xcu / "tests" / "fixtures" / SOURCE
        cls.psi_path = cls.xcu / "tests" / "fixtures" / PSI
        cls.reader = cls.xcu / "tools" / "inputxml-to-uxml.mjs"
        if not cls.reader.is_file() or not cls.input_path.is_file():
            raise unittest.SkipTest("Exact pinned public XCU S3 reader and fixtures required")
        cls.input = cls._strict(cls.input_path, cls.reader)
        cls.delta = cls._strict(cls.xcu / "tests" / "fixtures" / DELTA, cls.reader)
        cls.psi = cls._strict(cls.psi_path, cls.xcu / "tools" / "psi116-to-uxml.mjs")

    @classmethod
    def _strict(cls, source, reader):
        proc = subprocess.run(["node", str(reader), str(source)], cwd=cls.xcu,
                              capture_output=True, text=True, timeout=60)
        if proc.returncode:
            raise AssertionError("PUBLIC_XCU_STRICT_READER_FAILED: " + proc.stderr)
        return json.loads(proc.stdout)

    def exact(self, code, call):
        with self.assertRaises(UxmlPsi116Error) as error:
            call()
        self.assertEqual(str(error.exception), code)

    def hub(self):
        return deepcopy(self.input)

    def key(self, hub, i):
        return hub["components"][i]["sourceRefs"][0]["recordKey"]

    def mixed(self):
        """Remove exactly six absolute anchors from last original PIPINGELEMENT."""
        original = self.input_path.read_text(encoding="utf-8")
        tags = list(re.finditer(r"<PIPINGELEMENT\b[^>]*>", original))
        self.assertEqual(len(tags), 6)
        tag = tags[5]
        updated, removed = re.subn(r'\s+(?:FROM|TO)_[XYZ]="[^"]*"', "", tag.group())
        self.assertEqual(removed, 6)
        modified = original[:tag.start()] + updated + original[tag.end():]
        with tempfile.TemporaryDirectory(prefix="public-s3-mixed-frame-") as folder:
            path = Path(folder) / SOURCE
            path.write_bytes(modified.encode("utf-8"))
            hub = self._strict(path, self.reader)
        runs = hub["inputXml"]["runs"]
        self.assertEqual([(r["id"], r["anchored"]) for r in runs],
                         [("RUN-0000", True), ("RUN-0001", False)])
        return hub

    def _change_last_source_element(self, change, *, strict_reader=False):
        original = self.input_path.read_text(encoding="utf-8")
        tags = list(re.finditer(r"<PIPINGELEMENT\b[^>]*>", original))
        self.assertEqual(len(tags), 6)
        last = tags[5]
        changed = change(last.group())
        self.assertNotEqual(changed, last.group())
        altered = original[:last.start()] + changed + original[last.end():]
        if strict_reader:
            with tempfile.TemporaryDirectory(prefix="public-source-authority-") as folder:
                path = Path(folder) / SOURCE
                path.write_bytes(altered.encode("utf-8"))
                return self._strict(path, self.reader)
        hub = self.hub()
        hub["sources"][0]["sourceText"] = altered
        digest = sha256(altered.encode("utf-8")).hexdigest()
        hub["sources"][0]["hash"] = digest
        hub["inputXml"]["sourceSha256"] = digest
        return hub

    def _change_last_attr(self, attribute, value, *, strict_reader=False):
        def change(tag):
            pattern = r'(' + re.escape(attribute) + r'=")[^"]*(")'
            altered, count = re.subn(pattern, lambda m: m.group(1) + value + m.group(2), tag)
            self.assertEqual(count, 1, attribute)
            return altered
        return self._change_last_source_element(change, strict_reader=strict_reader)

    def test_IA1_honest_xcu_run_partition_is_byte_source_equivalent(self):
        from converters.psi116_topology_resolver.uxml_adapter import (
            _caesar_original_rows, _recompute_inputxml_runs,
        )
        for name, hub, anchored in (
            ("anchored", self.input, True), ("delta-only", self.delta, False),
        ):
            with self.subTest(hub=name):
                rows, _ = _caesar_original_rows(hub["sources"][0]["sourceText"])
                derived = _recompute_inputxml_runs(rows)
                self.assertEqual(len(derived), 2)
                self.assertEqual([run["anchored"] for run in derived],
                                 [anchored, anchored])
                for declared, trusted in zip(hub["inputXml"]["runs"], derived):
                    for field in ("id", "elementIndices", "edgeCount",
                                  "nodeCount", "firstNode", "anchored"):
                        self.assertEqual(declared[field], trusted[field],
                                         f"{name} field={field}")
                document_from_uxml(hub)

    def test_IA1_single_run_delta_only_forgery_partition_refused(self):
        hub = deepcopy(self.delta)
        self.assertEqual(len(hub["inputXml"]["runs"]), 2)
        forged = hub["inputXml"]["runs"][0]
        forged["elementIndices"] = list(range(len(hub["components"])))
        forged["edgeCount"] = len(forged["elementIndices"])
        forged["nodeCount"] += hub["inputXml"]["runs"][1]["nodeCount"]
        hub["inputXml"]["runs"] = [forged]
        for comp in hub["components"]:
            comp["sourceRefs"][0]["runId"] = forged["id"]
            comp["rawAttributes"]["inputXml"]["runId"] = forged["id"]
        for port in hub["ports"]:
            port["runId"] = forged["id"]
            port["sourceRefs"][0]["runId"] = forged["id"]
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: resolve_from_uxml(hub))

    def test_IA1_all_anchored_mixed_runs_forged_as_one_merge_refused(self):
        hub = self.mixed()
        self.assertEqual([run["anchored"] for run in hub["inputXml"]["runs"]],
                         [True, False])
        first, second = hub["inputXml"]["runs"]
        first["elementIndices"] = first["elementIndices"] + second["elementIndices"]
        first["edgeCount"] = len(first["elementIndices"])
        first["nodeCount"] += second["nodeCount"]
        first["anchored"] = True
        hub["inputXml"]["runs"] = [first]
        # Fully forge dependent hub provenance, so only the independently
        # recomputed original-source partition can refuse the false merge.
        for component in hub["components"]:
            ref = component["sourceRefs"][0]
            info = component["rawAttributes"]["inputXml"]
            ref["runId"] = first["id"]
            info["runId"] = first["id"]
            ref["anchored"] = True
            info["anchored"] = True
        for port in hub["ports"]:
            port["runId"] = first["id"]
            port["anchored"] = True
            port["sourceRefs"][0]["runId"] = first["id"]
            port["sourceRefs"][0]["anchored"] = True
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: resolve_from_uxml(hub))
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_IA1_all_anchored_mixed_hub_forgery_partition_refused(self):
        hub = self.mixed()
        self.assertEqual([r["anchored"] for r in hub["inputXml"]["runs"]],
                         [True, False])
        hub["inputXml"]["runs"][1]["anchored"] = True
        for comp in hub["components"]:
            if comp["sourceRefs"][0]["runId"] == "RUN-0001":
                comp["sourceRefs"][0]["anchored"] = True
                comp["rawAttributes"]["inputXml"]["anchored"] = True
        for port in hub["ports"]:
            if port["runId"] == "RUN-0001":
                port["anchored"] = True
                port["sourceRefs"][0]["anchored"] = True
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: resolve_from_uxml(hub))
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_IA1_first_node_forged_even_if_indices_correct(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["firstNode"] = "SYNTHETIC_FORGED_FIRST"
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_IA1_node_count_forged_even_if_membership_correct(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["nodeCount"] += 1
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_IA5_integer_alias_30_vs_30_000000_refuses(self):
        hub = self._change_last_attr("FROM_NODE", "30", strict_reader=True)
        self.assertEqual([run["anchored"] for run in hub["inputXml"]["runs"]],
                         [True, True])
        self.exact("INPUT_XML_NODE_LITERAL_ALIAS",
                   lambda: resolve_from_uxml(hub))
        self.exact("INPUT_XML_NODE_LITERAL_ALIAS",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_IA4_fractional_100_5_node_number_refuses_without_truncation(self):
        hub = self._change_last_attr("FROM_NODE", "100.5")
        self.exact("INPUT_XML_INVALID_NODE_NUMBER:E5:FROM",
                   lambda: document_from_uxml(hub))

    def test_IA4_unknown_run_id_refuses_instead_of_empty_findings(self):
        from converters.psi116_topology_resolver.uxml_adapter import (
            resolve_inputxml_run_from_uxml,
        )
        self.exact("INPUT_XML_RUN_ID_NOT_FOUND:RUN-9999",
                   lambda: resolve_inputxml_run_from_uxml(self.input, "RUN-9999"))

    def test_IA2_incomplete_absolute_anchor_is_named(self):
        hub = self._change_last_source_element(
            lambda tag: re.sub(r'\s+FROM_Y="[^"]*"', "", tag))
        self.exact("INPUT_XML_INCOMPLETE_ABSOLUTE_ANCHOR",
                   lambda: document_from_uxml(hub))

    def test_IA2_invalid_non_numeric_anchor_is_named(self):
        hub = self._change_last_attr("FROM_X", "synthetic-nonnumeric")
        self.exact("INPUT_XML_INVALID_NUMBER:E5:FROM_X",
                   lambda: document_from_uxml(hub))

    def test_IA2_nonfinite_absolute_anchor_is_named(self):
        hub = self._change_last_attr("FROM_X", "1e999")
        self.exact("INPUT_XML_NONFINITE_ABSOLUTE_ANCHOR",
                   lambda: document_from_uxml(hub))

    def test_IA2_literal_sentinel_xyz_is_not_exempt_as_an_anchor(self):
        from converters.psi116_topology_resolver.uxml_adapter import (
            _caesar_original_rows, _recompute_inputxml_runs,
        )
        original = self.input_path.read_text(encoding="utf-8")
        tags = list(re.finditer(r"<PIPINGELEMENT\b[^>]*>", original))
        tag = tags[5]
        altered = tag.group()
        for endpoint in ("FROM", "TO"):
            for axis in "XYZ":
                altered, count = re.subn(
                    endpoint + "_" + axis + r'="[^"]*"',
                    endpoint + "_" + axis + '="-1.010100"', altered)
                self.assertEqual(count, 1)
        text = original[:tag.start()] + altered + original[tag.end():]
        rows, _ = _caesar_original_rows(text)
        runs = _recompute_inputxml_runs(rows)
        self.assertEqual([run["anchored"] for run in runs], [True, True],
                         "XCU point() admits -1.0101 as a literal absolute value")

    def _xcu_honest_variant(self, variant):
        """Change ONLY original public XML anchor spelling/presence/value."""
        original = self.input_path.read_text(encoding="utf-8")
        tags = list(re.finditer(r"<PIPINGELEMENT\b[^>]*>", original))
        self.assertEqual(len(tags), 6)
        output = []
        cursor = 0
        for i, match in enumerate(tags):
            output.append(original[cursor:match.start()])
            tag = match.group()
            if variant == "partial" and i < 5:
                # First source anchor occurs at element 2 FROM (not at
                # first route element 0 FROM). Keep independent run 1 intact.
                if i == 2:
                    tag, removed = re.subn(
                        r'\s+TO_[XYZ]="[^"]*"', "", tag)
                    self.assertEqual(removed, 3)
                else:
                    tag, removed = re.subn(
                        r'\s+(?:FROM|TO)_[XYZ]="[^"]*"', "", tag)
                    self.assertEqual(removed, 6)
            elif variant == "lower":
                tag = re.sub(r'\b(?:FROM|TO)_[XYZ](?==)',
                             lambda m: m.group().lower(), tag)
            elif variant == "padded":
                tag = re.sub(
                    r'((?:FROM|TO)_[XYZ]=")([^"]+)(")',
                    lambda m: m.group(1) + " \t" + m.group(2) + "\t " + m.group(3),
                    tag)
            output.append(tag)
            cursor = match.end()
        self.assertIn(variant, ("partial", "lower", "padded"))
        output.append(original[cursor:])
        with tempfile.TemporaryDirectory(prefix="public-xcu-honest-anchor-") as folder:
            source = Path(folder) / SOURCE
            source.write_text("".join(output), encoding="utf-8")
            return self._strict(source, self.reader)

    @staticmethod
    def _projection_signature(document):
        return tuple(
            (tuple((row.node_number,
                    tuple(row.position.as_list()) if row.position is not None else None,
                    row.component_type, row.outside_diameter, row.wall_thickness)
                   for row in branch.nodes))
            for branch in document.branches
        )

    def _assert_honest_variant_equal(self, variant):
        from converters.psi116_topology_resolver.models import ResolverConfig
        hub = self._xcu_honest_variant(variant)
        canonical_doc = document_from_uxml(self.input)
        changed_doc = document_from_uxml(hub)
        self.assertEqual(self._projection_signature(changed_doc),
                         self._projection_signature(canonical_doc),
                         variant + ": original-source geometry and node identities drifted")
        cfg = ResolverConfig()
        baseline = resolve_from_uxml(self.input).findings_payload(cfg)
        changed = resolve_from_uxml(hub).findings_payload(cfg)
        self.assertEqual(changed["summary"]["findingCountsByCode"],
                         baseline["summary"]["findingCountsByCode"])
        return hub

    def test_T1a_partial_anchored_firstNode_not_first_FROM_accepted(self):
        hub = self._assert_honest_variant_equal("partial")
        self.assertEqual(hub["inputXml"]["runs"][0]["firstNode"], "30.000000")
        self.assertNotEqual(hub["inputXml"]["runs"][0]["firstNode"],
                            hub["components"][0]["sourceRefs"][0]["fromNode"])

    def test_T1b_lowercase_absolute_xyz_accepted(self):
        hub = self._assert_honest_variant_equal("lower")
        self.assertIn("from_x=", hub["sources"][0]["sourceText"])
        self.assertEqual([r["anchored"] for r in hub["inputXml"]["runs"]],
                         [True, True])

    def test_T1c_padded_absolute_xyz_values_accepted(self):
        hub = self._assert_honest_variant_equal("padded")
        self.assertIn('FROM_X=" \t', hub["sources"][0]["sourceText"])
        self.assertEqual([r["anchored"] for r in hub["inputXml"]["runs"]],
                         [True, True])

    def test_T2_bool_element_index_refuses_partition_type(self):
        hub = self.hub()
        self.assertEqual(hub["inputXml"]["runs"][0]["elementIndices"][1], 1)
        hub["inputXml"]["runs"][0]["elementIndices"][1] = True
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_T2_float_nodeCount_refuses_partition_type(self):
        hub = self.hub()
        count = hub["inputXml"]["runs"][0]["nodeCount"]
        hub["inputXml"]["runs"][0]["nodeCount"] = float(count)
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_N4_xcu_reader_accepts_noncanonical_node_literals_topofix_refuses(self):
        for literal in (" 100.000000", "1E2"):
            with self.subTest(source_literal=literal):
                hub = self._change_last_attr("FROM_NODE", literal, strict_reader=True)
                # The XCU reader accepts the source, but its sourceRef may
                # normalize surrounding node-id whitespace. TopoFix checks
                # the ORIGINAL sourceText literal, not the normalized receipt.
                self.assertIn('FROM_NODE="' + literal + '"',
                              hub["sources"][0]["sourceText"])
                self.exact("INPUT_XML_INVALID_NODE_NUMBER:E5:FROM",
                           lambda: document_from_uxml(hub))

    def test_R2_B1a_non_dict_port_source_ref_exact(self):
        hub = self.hub()
        hub["ports"][0]["sourceRefs"] = ["x"]
        self.exact("INPUT_XML_PORT_SOURCE_REF_MISMATCH:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_R2_B1b_non_dict_component_raw_attributes_exact(self):
        hub = self.hub()
        hub["components"][0]["rawAttributes"] = "x"
        self.exact("INPUT_XML_RAW_RECORD_ID_MISMATCH:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_R2_B1c_non_dict_component_inputxml_evidence_exact(self):
        hub = self.hub()
        hub["components"][0]["rawAttributes"]["inputXml"] = [1]
        self.exact("INPUT_XML_RAW_RECORD_ID_MISMATCH:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_R2_B1_all_inputxml_read_paths_are_named_on_type_fuzz(self):
        # Target ALL hub-owned collections and fields used by the InputXML
        # source-backed path, not untrusted private source data. Primitive
        # replacements must not leak AttributeError/TypeError/IndexError.
        paths = (
            ("schemaVersion",), ("profile",), ("sources",),
            ("sources", 0), ("sources", 0, "format"),
            ("sources", 0, "sourceText"), ("sources", 0, "hash"),
            ("inputXml",), ("inputXml", "sourceSha256"),
            ("inputXml", "coordinateAuthority"), ("inputXml", "sourceFrame"),
            ("inputXml", "hubFrame"), ("inputXml", "elementCount"),
            ("inputXml", "runs"), ("inputXml", "runs", 0),
            ("inputXml", "runs", 0, "id"),
            ("inputXml", "runs", 0, "anchored"),
            ("inputXml", "runs", 0, "elementIndices"),
            ("inputXml", "runs", 0, "edgeCount"),
            ("inputXml", "runs", 0, "nodeCount"),
            ("inputXml", "runs", 0, "firstNode"),
            ("inputXml", "runs", 0, "hubFrame"),
            ("inputXml", "runs", 0, "sourceFrame"),
            ("inputXml", "runs", 0, "crossUnanchoredRunPolicy"),
            ("coordinateFrame",), ("coordinateFrame", "source"),
            ("coordinateFrame", "hub"), ("coordinateFrame", "transform"),
            ("components",), ("components", 0),
            ("components", 0, "id"), ("components", 0, "sourceRefs"),
            ("components", 0, "sourceRefs", 0),
            ("components", 0, "refNo"), ("components", 0, "rawAttributes"),
            ("components", 0, "rawAttributes", "inputXml"),
            ("components", 0, "rawAttributes", "inputXml", "recordKey"),
            ("components", 0, "rawAttributes", "inputXml", "elementIndex"),
            ("components", 0, "rawAttributes", "inputXml", "fromNode"),
            ("components", 0, "rawAttributes", "inputXml", "toNode"),
            ("components", 0, "rawAttributes", "inputXml", "runId"),
            ("components", 0, "rawAttributes", "inputXml", "anchored"),
            ("components", 0, "rawAttributes", "inputXml", "physicalEvidence"),
            ("components", 0, "rawAttributes", "inputXml", "outsideDiameter"),
            ("components", 0, "rawAttributes", "inputXml", "wallThickness"),
            ("components", 0, "rawAttributes", "inputXml", "bendEvidence"),
            ("components", 0, "rawAttributes", "inputXml", "sifEvidence"),
            ("components", 0, "rawAttributes", "inputXml", "componentType"),
            ("components", 0, "rawAttributes", "inputXml", "from"),
            ("components", 0, "rawAttributes", "inputXml", "to"),
            ("ports",), ("ports", 0), ("ports", 0, "componentId"),
            ("ports", 0, "sourceRefs"), ("ports", 0, "sourceRefs", 0),
            ("ports", 0, "point"), ("ports", 0, "point", "x"),
            ("ports", 0, "runId"), ("ports", 0, "anchored"),
            ("ports", 0, "coordinateFrame"),
        )
        replacements = (("str", "x"), ("list", ["x"]), ("none", None),
                        ("int", 23), ("bool", True))
        original = self.hub()
        tested = 0
        for path in paths:
            cursor = original
            for part in path:
                cursor = cursor[part]
            for label, new_value in replacements:
                if cursor == new_value:
                    continue
                with self.subTest(path=path, replacement=label):
                    hub = deepcopy(original)
                    parent = hub
                    for part in path[:-1]:
                        parent = parent[part]
                    parent[path[-1]] = deepcopy(new_value)
                    try:
                        document_from_uxml(hub)
                    except UxmlPsi116Error as error:
                        self.assertRegex(str(error), r"^[A-Z][A-Za-z0-9_]*(?::[^\n]+)?$")
                    except Exception as error:
                        self.fail("UNNAMED_INPUT_XML_EXCEPTION " +
                                  repr(path) + " " + label + " " + repr(error))
                    else:
                        self.fail("MALFORMED_INPUT_XML_HUB_ACCEPTED " +
                                  repr(path) + " " + label)
                    tested += 1
        self.assertGreaterEqual(tested, 250, "fuzz matrix coverage unexpectedly shrank")

    def test_R3_C1_nonstring_endpoints_each_named_beyond_first_port(self):
        for port_index in (1, 7, 11):
            for shape in (["FROM"], {"endpoint": "FROM"}):
                with self.subTest(port=port_index, shape=type(shape).__name__):
                    hub = self.hub()
                    port = hub["ports"][port_index]
                    comp_index = next(i for i, c in enumerate(hub["components"])
                                      if c["id"] == port["componentId"])
                    port["sourceRefs"][0]["endpoint"] = deepcopy(shape)
                    self.exact("INPUT_XML_PORT_SOURCE_REF_MISMATCH:" +
                               self.key(hub, comp_index),
                               lambda: document_from_uxml(hub))

    def test_R3_C2_sourceAttributes_shape_refused_for_every_component_in_compare(self):
        from converters.psi116_topology_resolver.uxml_compare import compare_cross_format_uxml
        for component_index in range(len(self.input["components"])):
            for value in ("x", ["x"], 23):
                with self.subTest(component=component_index, value=repr(value)):
                    hub = self.hub()
                    hub["components"][component_index]["rawAttributes"]["inputXml"][
                        "sourceAttributes"] = deepcopy(value)
                    # This property is unused by document projection, but
                    # compare must reject it before building field evidence.
                    document_from_uxml(hub)
                    self.exact("CROSS_FORMAT_SOURCE_ATTRIBUTES_INVALID",
                               lambda: compare_cross_format_uxml(self.psi, hub))

    def test_R3_C3_oversized_honest_reader_node_literal_is_named(self):
        huge = "9" * 4501  # XCU strict reader accepts the public-source mutation
        hub = self._change_last_attr("FROM_NODE", huge, strict_reader=True)
        self.assertIn('FROM_NODE="' + huge + '"',
                      hub["sources"][0]["sourceText"])
        self.exact("INPUT_XML_INVALID_NODE_NUMBER:E5:FROM",
                   lambda: document_from_uxml(hub))

    def test_R3_C4_swapped_run_element_indices_refused(self):
        hub = self.hub()
        a, b = hub["inputXml"]["runs"]
        self.assertEqual((a["elementIndices"][-1], b["elementIndices"][0]),
                         (4, 5))
        a["elementIndices"][-1], b["elementIndices"][0] = (
            b["elementIndices"][0], a["elementIndices"][-1])
        self.assertEqual(sum(run["edgeCount"] for run in hub["inputXml"]["runs"]), 6)
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_R3_C4_component_type_nonstring_later_components_refused(self):
        for component_index in (1, 3, 4, 5):
            for shape in (["PIPE"], {"type": "PIPE"}):
                with self.subTest(component=component_index, value=type(shape).__name__):
                    hub = self.hub()
                    hub["components"][component_index]["rawAttributes"]["inputXml"][
                        "componentType"] = deepcopy(shape)
                    self.exact("INPUT_XML_RAW_RECORD_ID_MISMATCH:" +
                               self.key(hub, component_index),
                               lambda: document_from_uxml(hub))

    def test_R3_C4_compare_frame_dict_guard_refuses(self):
        hub = self.hub()
        hub["coordinateFrame"] = ["PSI116_XYZ_MM"]
        self.exact("CROSS_FORMAT_HUB_FRAME_UNVERIFIED",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_R3_C4_compare_sources_and_entries_refuse(self):
        for which, expected in (
            ("PSI116", "CROSS_FORMAT_PSI116_SOURCE_REQUIRED"),
            ("INPUT_XML", "CROSS_FORMAT_INPUT_XML_SOURCE_REQUIRED"),
        ):
            for shape in ("x", {0: {"format": which}}, ["x"]):
                with self.subTest(which=which, replacement=repr(shape)):
                    psi, hub = deepcopy(self.psi), self.hub()
                    target = psi if which == "PSI116" else hub
                    target["sources"] = deepcopy(shape)
                    self.exact(expected, lambda: compare_cross_format_uxml(psi, hub))
            psi, hub = deepcopy(self.psi), self.hub()
            target = psi if which == "PSI116" else hub
            target["sources"][0] = ["not-a-dict"]
            self.exact(expected, lambda: compare_cross_format_uxml(psi, hub))

    def test_R2_B2_extra_empty_run_requires_same_partition_count(self):
        hub = self.hub()
        self.assertEqual(len(hub["inputXml"]["runs"]), 2)
        phantom = deepcopy(hub["inputXml"]["runs"][1])
        phantom.update(id="RUN-0002", elementIndices=[], edgeCount=0,
                       nodeCount=0, anchored=False, firstNode="")
        hub["inputXml"]["runs"].append(phantom)
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_R2_B3_float_edgeCount_refuses_partition_type(self):
        hub = self.hub()
        count = hub["inputXml"]["runs"][0]["edgeCount"]
        self.assertGreater(count, 1)
        hub["inputXml"]["runs"][0]["edgeCount"] = float(count)
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_R2_B3_bool_edgeCount_refuses_partition_type(self):
        hub = self.hub()
        index = next(i for i, run in enumerate(hub["inputXml"]["runs"])
                     if run["edgeCount"] == 1)
        hub["inputXml"]["runs"][index]["edgeCount"] = True
        self.exact("INPUT_XML_RUN_PARTITION_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_R2_N1_reject_non_ascii_anchor_digits(self):
        from converters.psi116_topology_resolver.uxml_adapter import _caesar_hub_absolute
        self.exact("INPUT_XML_INVALID_NUMBER:E5:FROM_X",
                   lambda: _caesar_hub_absolute(
                       {"FROM_X": "\u0661.0", "FROM_Y": "2", "FROM_Z": "3"},
                       "FROM", 5))

    def test_R2_N1_trim_exact_ecmascript_feFF_yes_u0085_no(self):
        from converters.psi116_topology_resolver.uxml_adapter import _caesar_hub_absolute
        result = _caesar_hub_absolute(
            {"FROM_X": "\ufeff 12.0 \ufeff", "FROM_Y": "2", "FROM_Z": "3"},
            "FROM", 5)
        self.assertEqual(result.as_list(), [12.0, -3.0, 2.0])
        self.exact("INPUT_XML_INVALID_NUMBER:E5:FROM_X",
                   lambda: _caesar_hub_absolute(
                       {"FROM_X": "\u0085" + "12.0", "FROM_Y": "2",
                        "FROM_Z": "3"}, "FROM", 5))

    def test_R2_N2_unverified_hub_metadata_is_explicitly_ignored(self):
        hub = self.hub()
        changed = self.hub()
        for run in changed["inputXml"]["runs"]:
            run["authority"] = ["UNTRUSTED_NOT_READ"]
            run["gapPolicy"] = {"untrusted": True}
        changed["coordinateFrame"]["runCount"] = "FAKE_RUN_COUNT"
        changed["coordinateFrame"]["unanchoredRunCount"] = -1000
        self.assertEqual(
            self._projection_signature(document_from_uxml(hub)),
            self._projection_signature(document_from_uxml(changed)))
        from converters.psi116_topology_resolver.models import ResolverConfig
        cfg = ResolverConfig()
        self.assertEqual(
            resolve_from_uxml(hub).findings_payload(cfg)["summary"]["findingCountsByCode"],
            resolve_from_uxml(changed).findings_payload(cfg)["summary"]["findingCountsByCode"])

    def test_R2_N4_comparator_preserves_named_node_error(self):
        from unittest import mock
        from converters.psi116_topology_resolver import uxml_compare as comparator
        from converters.psi116_topology_resolver.uxml_adapter import UxmlPsi116Error
        original = comparator._caesar_int
        invoked = [0]
        def synthetic_refusal(value, label):
            if label == "CROSS_FORMAT_TO_NODE":
                invoked[0] += 1
                raise UxmlPsi116Error("SYNTHETIC_CROSS_FORMAT_NAMED_REFUSAL")
            return original(value, label)
        with mock.patch.object(comparator, "_caesar_int", synthetic_refusal):
            self.exact("SYNTHETIC_CROSS_FORMAT_NAMED_REFUSAL",
                       lambda: comparator.compare_cross_format_uxml(self.psi, self.input))
        self.assertGreater(invoked[0], 0)

    def test_B1_M05_mixed_anchored_unanchored_resolve_refusal(self):
        self.exact("INPUT_XML_CROSS_UNANCHORED_RUN_GAP_PROXIMITY_JOIN_REFUSED",
                   lambda: resolve_from_uxml(self.mixed()))

    def test_B1_M12_mixed_anchored_unanchored_crossformat_refusal(self):
        self.exact("CROSS_FORMAT_UNANCHORED_ABSOLUTE_FRAME_COMPARISON_REFUSED",
                   lambda: compare_cross_format_uxml(self.psi, self.mixed()))

    def test_invalid_inputxml_scope_is_named(self):
        hub = self.hub()
        hub["inputXml"] = ["malformed", "scope"]
        self.exact("INPUT_XML_SCOPE_INVALID", lambda: document_from_uxml(hub))

    def test_invalid_coordinate_frame_is_named(self):
        hub = self.hub()
        hub["coordinateFrame"] = ["malformed", "frame"]
        self.exact("INPUT_XML_COORDINATE_FRAME_INVALID",
                   lambda: document_from_uxml(hub))

    def test_B2_coordinate_frame_mismatch(self):
        hub = self.hub()
        hub["coordinateFrame"]["transform"] = "UNVERIFIED"
        self.exact("INPUT_XML_COORDINATE_FRAME_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_B2_caesar_original_root_required(self):
        original = self.input_path.read_text(encoding="utf-8")
        self.assertTrue(original.startswith("<CAESARII "))
        changed = original.replace("<CAESARII ", "<OTHERROOT ", 1)
        self.assertIn("</CAESARII>", changed)
        changed = changed.replace("</CAESARII>", "</OTHERROOT>", 1)
        self.exact("INPUT_XML_CAESAR_ROOT_REQUIRED",
                   lambda: _caesar_original_rows(changed))

    def test_B2_topology_full_profile_required(self):
        hub = self.hub()
        hub["profile"] = "NOT_FULL"
        self.exact("INPUT_XML_NOT_TOPOLOGY_FULL",
                   lambda: document_from_uxml(hub))

    def test_B2_original_source_text_required(self):
        hub = self.hub()
        hub["sources"][0]["sourceText"] = ""
        self.exact("INPUT_XML_ORIGINAL_TEXT_REQUIRED",
                   lambda: document_from_uxml(hub))

    def test_B2_original_sha256_required(self):
        hub = self.hub()
        hub["sources"][0]["hash"] = "not-a-valid-sha256"
        self.exact("INPUT_XML_SOURCE_SHA256_REQUIRED",
                   lambda: document_from_uxml(hub))

    def test_B2_exactly_two_ports_per_input_element(self):
        hub = self.hub()
        hub["ports"].pop()
        self.exact("INPUT_XML_PORTS_PER_ELEMENT_MISMATCH",
                   lambda: document_from_uxml(hub))

    def test_B2_run_frame_declarations_required(self):
        hub = self.hub()
        hub["inputXml"]["runs"] = []
        self.exact("INPUT_XML_RUN_FRAME_DECLARATIONS_REQUIRED",
                   lambda: document_from_uxml(hub))

    def test_B2_run_identity_required(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["id"] = "RUN-INVALID"
        self.exact("INPUT_XML_RUN_IDENTITY_INVALID",
                   lambda: document_from_uxml(hub))

    def test_B2_run_frame_cross_unanchored_policy_required(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["crossUnanchoredRunPolicy"] = "ALLOW"
        self.exact("INPUT_XML_RUN_FRAME_INVALID",
                   lambda: document_from_uxml(hub))

    def test_B2_run_element_index_count_required(self):
        hub = self.hub()
        hub["inputXml"]["runs"][0]["edgeCount"] += 1
        self.exact("INPUT_XML_RUN_ELEMENT_INDEX_INVALID",
                   lambda: document_from_uxml(hub))

    def test_B2_duplicate_or_invalid_run_element_index(self):
        hub = self.hub()
        indices = hub["inputXml"]["runs"][0]["elementIndices"]
        self.assertGreaterEqual(len(indices), 2)
        indices[1] = indices[0]
        self.exact("INPUT_XML_DUPLICATE_OR_INVALID_RUN_ELEMENT_INDEX",
                   lambda: document_from_uxml(hub))

    def test_B2_run_coverage_must_be_complete(self):
        hub = self.hub()
        run = hub["inputXml"]["runs"][0]
        self.assertGreaterEqual(len(run["elementIndices"]), 2)
        run["elementIndices"].pop()
        run["edgeCount"] = len(run["elementIndices"])
        self.exact("INPUT_XML_RUN_COVERAGE_INCOMPLETE",
                   lambda: document_from_uxml(hub))

    def test_B2_raw_record_identity_cannot_drift(self):
        hub = self.hub()
        hub["components"][0]["rawAttributes"]["inputXml"]["elementIndex"] = 999
        self.exact("INPUT_XML_RAW_RECORD_ID_MISMATCH:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_B2_nested_source_bend_evidence_cannot_drift(self):
        hub = self.hub()
        comp = hub["components"][2]
        info = comp["rawAttributes"]["inputXml"]
        self.assertIsNotNone(info["bendEvidence"])
        info["bendEvidence"]["radius"] += 1
        self.exact("INPUT_XML_NESTED_SOURCE_EVIDENCE_MISMATCH:" + self.key(hub, 2),
                   lambda: document_from_uxml(hub))

    def test_B2_port_coordinate_frame_cannot_drift(self):
        hub = self.hub()
        hub["ports"][0]["coordinateFrame"] = "UNVERIFIED"
        self.exact("INPUT_XML_PORT_FRAME_MISMATCH:" + self.key(hub, 0),
                   lambda: document_from_uxml(hub))

    def test_B2_delta_path_conflict_between_shared_node_ports(self):
        hub = self.hub()
        comp = hub["components"][1]
        info = comp["rawAttributes"]["inputXml"]
        self.assertEqual(hub["components"][0]["sourceRefs"][0]["toNode"],
                         comp["sourceRefs"][0]["fromNode"])
        for port in hub["ports"]:
            if port["componentId"] == comp["id"]:
                port["point"]["x"] += 7
        info["from"]["x"] += 7
        info["to"]["x"] += 7
        key = self.key(hub, 1)
        self.exact("INPUT_XML_DELTA_PATH_CONFLICT:" + key + ":" +
                   comp["sourceRefs"][0]["fromNode"],
                   lambda: document_from_uxml(hub))

    def test_B2_bend_component_type_from_original_source(self):
        hub = self.hub()
        comp = hub["components"][2]
        info = comp["rawAttributes"]["inputXml"]
        self.assertIsNotNone(info["bendEvidence"])
        self.assertFalse(any(s.get("node") == info["toNode"] and s.get("typeCode") in (3,5)
                             for s in info.get("sifEvidence", [])))
        info["componentType"] = "PIPE"
        self.exact("INPUT_XML_BEND_COMPONENT_TYPE_CONFLICT:" + self.key(hub, 2),
                   lambda: document_from_uxml(hub))

    def test_B2_run_resolution_requires_inputxml_format(self):
        self.exact("INPUT_XML_RUN_RESOLUTION_FORMAT_REQUIRED",
                   lambda: resolve_inputxml_run_from_uxml(self.psi, "RUN-0000"))

    def test_IA4_crossformat_requires_psi116_source(self):
        hub = deepcopy(self.psi)
        hub["sources"][0]["format"] = "INPUT_XML"
        self.exact("CROSS_FORMAT_PSI116_SOURCE_REQUIRED",
                   lambda: compare_cross_format_uxml(hub, self.input))

    def test_B2_crossformat_requires_inputxml_source(self):
        hub = self.hub()
        hub["sources"][0]["format"] = "PSI116"
        self.exact("CROSS_FORMAT_INPUT_XML_SOURCE_REQUIRED",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_B2_crossformat_requires_verified_hub_frame(self):
        hub = self.hub()
        hub["coordinateFrame"]["transform"] = "UNVERIFIED"
        self.exact("CROSS_FORMAT_HUB_FRAME_UNVERIFIED",
                   lambda: compare_cross_format_uxml(self.psi, hub))

    def test_B3_raw_inputxml_export_cli_refuses_before_missing_xcu_reader(self):
        self._assert_raw_inputxml_cli_holds_without_reader("uxml_export_ops")

    def test_B3_raw_inputxml_patch_cli_refuses_before_missing_xcu_reader(self):
        self._assert_raw_inputxml_cli_holds_without_reader("uxml_patch_psi116")

    def _assert_raw_inputxml_cli_holds_without_reader(self, module):
        original = self.input_path.read_bytes()
        with tempfile.TemporaryDirectory(prefix="public-inputxml-cli-order-") as tmp:
            root = Path(tmp)
            ops = root / "not-created.ops.json"  # deliberately absent
            output = root / "not-created-fixed.xml"
            validation = root / "not-created-validation.json"
            env = os.environ.copy()
            env["XCU_UXML_ROOT"] = str(root / "nonexistent-xcu-reader")
            extra = (["--output", str(output), "--validation", str(validation)]
                     if module == "uxml_patch_psi116" else [])
            process = subprocess.run(
                [sys.executable, "-m", "converters.psi116_topology_resolver." + module,
                 str(self.input_path), str(ops), *extra],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(process.returncode, 1,
                             process.stdout + process.stderr)
            self.assertEqual(process.stdout.strip().splitlines(),
                             ["DIFFERENT", "ERROR: INPUT_XML_APPLY_NOT_ENABLED"])
            self.assertNotIn("XCU_PINNED_READER_REQUIRED",
                             process.stdout + process.stderr)
            for target in (ops, output, validation):
                self.assertFalse(target.exists(), "refusal created " + str(target))
        self.assertEqual(self.input_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
