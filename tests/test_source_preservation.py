"""Scoped source-preservation regressions; synthetic expectations, not design approval."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver import resolve_psi116
from psi116_topology_resolver.models import ResolverConfig
from psi116_topology_resolver.transaction import (
    TransactionPolicy, _can_remove_plain_pipe, apply_topofix_transaction,
)


def source(reference="UNIQUE-KEEP-REF", name="", wall="8.18"):
    records = []
    for number, kind, ref, xyz, endpoint in [
        (10, "PIPE", reference, "0 0 0", 2),
        (20, "ELBO", "ELBOW-OWNER", "0 0 0", 0),
        (30, "PIPE", "BYSTANDER", "100 0 0", 1),
    ]:
        records.append(
            f"<Node><NodeNumber>{number}</NodeNumber>"
            f"<NodeName>{name if number == 10 else ''}</NodeName>"
            f"<Endpoint>{endpoint}</Endpoint><ComponentType>{kind}</ComponentType>"
            f"<ComponentRefNo>{ref}</ComponentRefNo><Rigid>0</Rigid><Weight>0</Weight>"
            f"<OutsideDiameter>219.1</OutsideDiameter>"
            f"<WallThickness>{wall if number == 10 else '8.18'}</WallThickness>"
            f"<Position>{xyz}</Position></Node>"
        )
    return ('<PipeStressExport xmlns="http://aveva.com/pipeStress116.xsd">'
            '<Pipe><Branch><Branchname>TEST</Branchname>' + ''.join(records) +
            '</Branch></Pipe></PipeStressExport>')


def candidate(result):
    return next(a for a in result.fix_actions if 10 in a.absorbed_node_numbers)


class SourcePreservation(unittest.TestCase):
    def test_reference_bearing_removal_becomes_explicit_manual_preserve_review(self):
        result = resolve_psi116(source())
        action = candidate(result)
        self.assertEqual(action.disposition, "REVIEW_SOURCE_RECORD")
        self.assertEqual(action.proposed_changes, ())
        self.assertEqual(action.confidence, 0)
        self.assertFalse(action.blockers, "Manual review must not veto unrelated safe work")
        self.assertIn("UNIQUE-KEEP-REF", action.message)
        self.assertIn("B0:N10:S0", action.message)
        self.assertIn("B0:N20:S1", action.message)
        self.assertIn("ABSORBED_PIPE_HAS_COMPONENT_REF_NO", action.message)
        self.assertIn("re-export", action.message)
        self.assertIn("rerun", action.message)

    def test_backend_rejects_legacy_removal_plan_and_emits_no_partial_xml(self):
        original = source()
        result = resolve_psi116(original)
        # Explicitly simulate a legacy/stale producer bypassing the new planner.
        legacy = replace(candidate(result), disposition="SAFE_DROP_PIPE_GEOMETRY",
                         confidence=1.0, proposed_changes=({"operation": "DROP_PLAIN_PIPE_NODE"},))
        forged = replace(result, fix_actions=(legacy,))
        txn = apply_topofix_transaction(
            forged, policy=TransactionPolicy(selected_action_ids=(legacy.action_id,)))
        self.assertFalse(txn.committed)
        self.assertIsNone(txn.fixed_xml)
        self.assertIsNone(txn.after_result)
        self.assertEqual(txn.operations, ())
        self.assertTrue(any("ABSORBED_PIPE_HAS_COMPONENT_REF_NO" in r for r in txn.reject_reasons))
        self.assertEqual(result.document.source_text, original)
        self.assertIn("UNIQUE-KEEP-REF", original)

    def test_empty_reference_positive_control_still_has_validated_removal(self):
        result = resolve_psi116(source(reference=""))
        action = candidate(result)
        self.assertEqual(action.disposition, "SAFE_DROP_PIPE_GEOMETRY")
        txn = apply_topofix_transaction(
            result, policy=TransactionPolicy(selected_action_ids=(action.action_id,)))
        self.assertTrue(txn.committed, txn.reject_reasons)
        self.assertEqual(len(txn.checks), 9)
        self.assertTrue(all(c.passed for c in txn.checks))
        self.assertEqual(len(txn.operations), 1)
        self.assertEqual(txn.operations[0].operation, "REMOVE_PLAIN_PIPE_NODE_RECORD")
        self.assertIn("ELBOW-OWNER", txn.fixed_xml)
        self.assertIn("BYSTANDER", txn.fixed_xml)

    def test_existing_vetoes_are_preserved_independently(self):
        result = resolve_psi116(source(reference=""))
        pipe, owner, _ = result.document.branches[0].nodes
        cases = [
            (replace(pipe, node_name="MEANINGFUL-NAME"), "ABSORBED_PIPE_HAS_NODE_NAME"),
            (replace(pipe, has_restraint=True), "ABSORBED_PIPE_HAS_RESTRAINT"),
            (replace(pipe, rigid=1), "ABSORBED_PIPE_HAS_RIGID_EVIDENCE"),
            (replace(pipe, weight=1), "ABSORBED_PIPE_HAS_WEIGHT"),
            (replace(pipe, outside_diameter=220), "ABSORBED_PIPE_DIAMETER_DIFFERS"),
            (replace(pipe, wall_thickness=7), "ABSORBED_PIPE_WALL_DIFFERS"),
        ]
        for record, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(_can_remove_plain_pipe(record, owner, ResolverConfig()),
                                 (False, expected))

    def test_named_and_wall_mismatch_reviews_include_original_values(self):
        result = resolve_psi116(source(reference="PIPE-REF", name="KEEP-NAME", wall="2.87"))
        action = candidate(result)
        self.assertEqual(action.disposition, "REVIEW_SOURCE_RECORD")
        for text in ("KEEP-NAME", "PIPE-REF", "2.87", "8.18"):
            self.assertIn(text, action.message)


if __name__ == "__main__":
    unittest.main()
